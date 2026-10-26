"""
Script untuk melakukan audit kualitas data awal pada korpus teks.
Menghasilkan laporan terperinci dalam format JSON dan Markdown.
"""

import argparse
import hashlib
import json
import math
import os
import re
import sys
from typing import Dict, List, Any, Optional

sys.stdout.reconfigure(encoding="utf-8")


def calculate_percentile(sorted_list: List[int], p: float) -> float:
    """Menghitung persentil secara deterministik (metode linear interpolation)."""
    if not sorted_list:
        return 0.0
    k = (len(sorted_list) - 1) * p
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        return float(sorted_list[int(k)])
    d0 = sorted_list[int(f)] * (c - k)
    d1 = sorted_list[int(c)] * (k - f)
    return float(d0 + d1)


def audit_sample_data(
    input_file: str = "data/sample/wiki_sample_300.jsonl",
    output_dir: str = "docs"
) -> Dict[str, Any]:
    """
    Menjalankan audit mendalam terhadap integritas, distribusi, dan anomali teks sampel.
    """
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Berkas sampel '{input_file}' tidak ditemukan.")

    os.makedirs(output_dir, exist_ok=True)
    file_size_bytes = os.path.getsize(input_file)
    file_size_kb = round(file_size_bytes / 1024, 2)

    records = []
    corrupt_lines_count = 0
    corrupt_line_errors = []

    with open(input_file, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line_str = line.strip()
            if not line_str:
                continue
            try:
                rec = json.loads(line_str)
                if isinstance(rec, dict):
                    records.append((line_no, rec))
                else:
                    corrupt_lines_count += 1
                    corrupt_line_errors.append(f"Baris {line_no}: format bukan JSON object/dict")
            except json.JSONDecodeError as err:
                corrupt_lines_count += 1
                corrupt_line_errors.append(f"Baris {line_no}: JSONDecodeError - {err}")

    total_records = len(records)
    if total_records == 0:
        raise ValueError("Berkas sampel tidak memuat rekaman JSON valid.")

    # 1. Analisis Kolom (Bedakan: hilang, null, string kosong, tipe salah)
    expected_fields = ["id", "url", "title", "text"]
    column_analysis = {
        field: {
            "present_count": 0,
            "missing_count": 0,
            "null_count": 0,
            "empty_string_count": 0,
            "wrong_type_count": 0,
            "data_types": set()
        }
        for field in expected_fields
    }

    id_list = []
    text_hashes = []
    record_items = []

    # Regex untuk deteksi indikasi anomali
    re_tag_like = re.compile(r"<[^>]+>")
    re_wiki_markup = re.compile(r"(\{\{[^}]*\}\}|\[\[[^\]]*\]\])")
    re_url = re.compile(r"https?://\S+|www\.\S+")
    re_control_char = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
    re_section_heading = re.compile(r"(?im)^ *(?:={2,} *)?(?:Referensi|Pranala luar|Lihat pula|Catatan kaki)(?: *={2,})? *$")

    anomaly_examples = {
        "tag_like": [],
        "wiki_markup": [],
        "url_in_text": [],
        "control_char": [],
        "very_short": [],
        "section_headings": []
    }

    char_lengths = []
    approx_word_counts = []  # Whitespace split, BUKAN tokenizer final

    for line_no, rec in records:
        # Audit tiap kolom secara ketat
        for field in expected_fields:
            if field not in rec:
                column_analysis[field]["missing_count"] += 1
            else:
                val = rec[field]
                if val is None:
                    column_analysis[field]["null_count"] += 1
                elif isinstance(val, str):
                    column_analysis[field]["present_count"] += 1
                    column_analysis[field]["data_types"].add("str")
                    if len(val.strip()) == 0:
                        column_analysis[field]["empty_string_count"] += 1
                else:
                    column_analysis[field]["wrong_type_count"] += 1
                    column_analysis[field]["data_types"].add(type(val).__name__)

        # Ekstraksi nilai tanpa mengubah None menjadi 'None'
        val_id = rec.get("id")
        val_title = rec.get("title")
        val_url = rec.get("url")
        val_text = rec.get("text")

        str_id = str(val_id) if val_id is not None else ""
        str_title = str(val_title) if val_title is not None else ""
        str_url = str(val_url) if val_url is not None else ""
        # Penting: Jika val_text is None, biarkan None agar tidak bias menjadi 'None'
        has_text_content = isinstance(val_text, str) and len(val_text.strip()) > 0

        id_list.append(str_id)
        if isinstance(val_text, str):
            text_hash = hashlib.sha256(val_text.encode("utf-8")).hexdigest()
            text_hashes.append(text_hash)
            c_len = len(val_text)
            words = val_text.split()
            w_len = len(words)
        else:
            text_hashes.append(None)
            c_len = 0
            w_len = 0

        char_lengths.append(c_len)
        approx_word_counts.append(w_len)

        item_meta = {
            "id": str_id,
            "title": str_title,
            "url": str_url,
            "char_len": c_len,
            "approx_words": w_len,
            "text": val_text if isinstance(val_text, str) else ""
        }
        record_items.append(item_meta)

        if not has_text_content:
            continue

        # Pemeriksaan anomali
        text_str = val_text

        # 1. Indikasi mirip tag (<...>)
        tag_matches = re_tag_like.findall(text_str)
        if tag_matches:
            if len(anomaly_examples["tag_like"]) < 3:
                anomaly_examples["tag_like"].append({
                    "id": str_id,
                    "title": str_title,
                    "matches": tag_matches[:5],
                    "context": text_str[:180] + ("..." if c_len > 180 else "")
                })

        # 2. Wiki markup ({{...}} atau [[...]])
        wiki_matches = re_wiki_markup.findall(text_str)
        if wiki_matches:
            if len(anomaly_examples["wiki_markup"]) < 3:
                anomaly_examples["wiki_markup"].append({
                    "id": str_id,
                    "title": str_title,
                    "matches": wiki_matches[:3],
                    "context": text_str[:180] + ("..." if c_len > 180 else "")
                })

        # 3. URL di dalam badan teks
        url_matches = re_url.findall(text_str)
        if url_matches:
            if len(anomaly_examples["url_in_text"]) < 3:
                anomaly_examples["url_in_text"].append({
                    "id": str_id,
                    "title": str_title,
                    "matches": url_matches[:3],
                    "context": text_str[:180] + ("..." if c_len > 180 else "")
                })

        # 4. Karakter kontrol
        ctrl_matches = re_control_char.findall(text_str)
        if ctrl_matches:
            if len(anomaly_examples["control_char"]) < 3:
                anomaly_examples["control_char"].append({
                    "id": str_id,
                    "title": str_title,
                    "char_codes": [ord(c) for c in ctrl_matches[:5]]
                })

        # 5. Teks sangat pendek (< 100 karakter)
        if c_len < 100:
            if len(anomaly_examples["very_short"]) < 3:
                anomaly_examples["very_short"].append({
                    "id": str_id,
                    "title": str_title,
                    "char_len": c_len,
                    "full_text": text_str
                })

        # 6. Heading seksi Referensi / Pranala luar pada baris mandiri
        sec_matches = re_section_heading.findall(text_str)
        if sec_matches:
            if len(anomaly_examples["section_headings"]) < 3:
                anomaly_examples["section_headings"].append({
                    "id": str_id,
                    "title": str_title,
                    "headings": sec_matches[:3]
                })

    # Analisis Keunikan
    unique_ids_count = len(set(filter(None, id_list)))
    valid_hashes = [h for h in text_hashes if h is not None]
    unique_texts_count = len(set(valid_hashes))
    id_duplicates = total_records - unique_ids_count
    text_duplicates = len(valid_hashes) - unique_texts_count

    # Distribusi Karakter
    sorted_chars = sorted(char_lengths)
    char_min = sorted_chars[0]
    char_median = calculate_percentile(sorted_chars, 0.5)
    char_p90 = calculate_percentile(sorted_chars, 0.9)
    char_max = sorted_chars[-1]
    char_mean = round(sum(sorted_chars) / total_records, 2)

    # Distribusi Kata
    sorted_words = sorted(approx_word_counts)
    word_min = sorted_words[0]
    word_median = calculate_percentile(sorted_words, 0.5)
    word_p90 = calculate_percentile(sorted_words, 0.9)
    word_max = sorted_words[-1]
    word_mean = round(sum(sorted_words) / total_records, 2)

    # Pemilihan Stratifikasi Sampel untuk Inspeksi Manual:
    # 1. Pendek (< p10)
    # 2. Sedang (~ median)
    # 3. Panjang (> p90)
    sorted_by_len = sorted(record_items, key=lambda x: x["char_len"])
    short_sample = sorted_by_len[0]
    mid_sample = sorted_by_len[len(sorted_by_len) // 2]
    long_sample = sorted_by_len[-1]

    stratified_samples = {
        "short_article": {
            "id": short_sample["id"],
            "title": short_sample["title"],
            "url": short_sample["url"],
            "char_len": short_sample["char_len"],
            "approx_words": short_sample["approx_words"],
            "preview": short_sample["text"][:300]
        },
        "median_article": {
            "id": mid_sample["id"],
            "title": mid_sample["title"],
            "url": mid_sample["url"],
            "char_len": mid_sample["char_len"],
            "approx_words": mid_sample["approx_words"],
            "preview": mid_sample["text"][:300]
        },
        "long_article": {
            "id": long_sample["id"],
            "title": long_sample["title"],
            "url": long_sample["url"],
            "char_len": long_sample["char_len"],
            "approx_words": long_sample["approx_words"],
            "preview": long_sample["text"][:300]
        }
    }

    # Format Serialisasi
    for fld in expected_fields:
        column_analysis[fld]["data_types"] = list(column_analysis[fld]["data_types"])

    report = {
        "dataset_file": input_file,
        "file_size_bytes": file_size_bytes,
        "file_size_kb": file_size_kb,
        "total_records_loaded": total_records,
        "corrupt_lines_count": corrupt_lines_count,
        "corrupt_line_errors": corrupt_line_errors,
        "column_analysis": column_analysis,
        "integrity_and_uniqueness": {
            "unique_ids_count": unique_ids_count,
            "duplicate_ids_count": id_duplicates,
            "unique_texts_count": unique_texts_count,
            "duplicate_texts_count": text_duplicates
        },
        "character_length_distribution": {
            "min": char_min,
            "median": char_median,
            "p90": char_p90,
            "max": char_max,
            "mean": char_mean
        },
        "approx_word_count_distribution": {
            "note": "Hitungan berbasis pemisahan spasi (whitespace split). Bukan jumlah token tokenizer final.",
            "min": word_min,
            "median": word_median,
            "p90": word_p90,
            "max": word_max,
            "mean": word_mean
        },
        "anomaly_indicators": {
            "note": (
                "Indikasi anomali ini mendata pola teks yang berpotensi memerlukan pembersihan, "
                "bukan keputusan otomatis membuang artikel."
            ),
            "articles_with_tag_like_patterns": len([1 for r in record_items if re_tag_like.search(r["text"])]),
            "articles_with_wiki_markup": len([1 for r in record_items if re_wiki_markup.search(r["text"])]),
            "articles_with_urls_in_body": len([1 for r in record_items if re_url.search(r["text"])]),
            "articles_with_control_chars": len([1 for r in record_items if re_control_char.search(r["text"])]),
            "articles_under_100_chars": len([1 for r in record_items if r["char_len"] < 100]),
            "articles_with_section_headings": len([1 for r in record_items if re_section_heading.search(r["text"])]),
            "examples": anomaly_examples
        },
        "stratified_inspection_samples": stratified_samples
    }

    # Simpan JSON
    json_path = os.path.join(output_dir, "sample_audit_report.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Simpan Markdown
    md_path = os.path.join(output_dir, "sample_audit_report.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Laporan Audit Kualitas Data Sampel Wikipedia Bahasa Indonesia\n\n")
        f.write(f"- **Berkas Data**: `{input_file}`\n")
        f.write(f"- **Ukuran Berkas**: {file_size_kb} KB ({file_size_bytes:,} bytes)\n")
        f.write(f"- **Total Rekaman Valid**: {total_records}\n")
        f.write(f"- **Baris JSON Rusak/Gagal**: {corrupt_lines_count}\n\n")

        f.write("## 1. Analisis Kelengkapan & Tipe Kolom\n\n")
        f.write("| Kolom | Hadir (Valid) | Hilang (Missing Key) | Null (`None`) | String Kosong | Salah Tipe | Tipe Data |\n")
        f.write("| :--- | :---: | :---: | :---: | :---: | :---: | :--- |\n")
        for fld in expected_fields:
            cinfo = report["column_analysis"][fld]
            f.write(
                f"| `{fld}` | {cinfo['present_count']} | {cinfo['missing_count']} | {cinfo['null_count']} | "
                f"{cinfo['empty_string_count']} | {cinfo['wrong_type_count']} | {', '.join(cinfo['data_types'])} |\n"
            )
        f.write("\n")

        f.write("### Keunikan Rekaman (Berdasarkan SHA-256)\n")
        f.write(f"- ID unik: **{unique_ids_count}/{total_records}** (Duplikat: {id_duplicates})\n")
        f.write(f"- Teks unik: **{unique_texts_count}/{len(valid_hashes)}** (Duplikat: {text_duplicates})\n\n")

        f.write("## 2. Distribusi Panjang Karakter & Perkiraan Kata\n\n")
        f.write("> **Catatan**: Perkiraan kata dihitung berbasis *whitespace split*. Angka ini **bukan** jumlah token tokenizer final.\n\n")
        f.write("| Metrik | Panjang Karakter | Perkiraan Kata (Whitespace) |\n")
        f.write("| :--- | :---: | :---: |\n")
        f.write(f"| **Minimum** | {char_min:,} | {word_min:,} |\n")
        f.write(f"| **Median (p50)** | {char_median:,} | {word_median:,} |\n")
        f.write(f"| **Persentil 90 (p90)** | {char_p90:,} | {word_p90:,} |\n")
        f.write(f"| **Maksimum** | {char_max:,} | {word_max:,} |\n")
        f.write(f"| **Rata-rata (Mean)** | {char_mean:,} | {word_mean:,} |\n\n")

        f.write("## 3. Indikasi Anomali & Temuan Teks\n\n")
        f.write("| Indikator Anomali | Jumlah Artikel | Persentase | Catatan Analisis |\n")
        f.write("| :--- | :---: | :---: | :--- |\n")
        anom = report["anomaly_indicators"]
        f.write(f"| Indikasi Pola Mirip Tag (`<...>`) | {anom['articles_with_tag_like_patterns']} | {round(anom['articles_with_tag_like_patterns']/total_records*100, 1)}% | Termasuk tag HTML referensi (`<ref>`), serta kode program non-HTML |\n")
        f.write(f"| Sisa Wiki Markup (`{{}}`, `[[]]`) | {anom['articles_with_wiki_markup']} | {round(anom['articles_with_wiki_markup']/total_records*100, 1)}% | Template kutipan atau tautan internal wiki yang belum terurai |\n")
        f.write(f"| URL di Badan Teks | {anom['articles_with_urls_in_body']} | {round(anom['articles_with_urls_in_body']/total_records*100, 1)}% | Tautan web mentah (`http://`, `https://`) di dalam teks narasi |\n")
        f.write(f"| Karakter Kontrol Non-Printable | {anom['articles_with_control_chars']} | {round(anom['articles_with_control_chars']/total_records*100, 1)}% | Karakter kontrol sistem biner (selain `\\n` dan `\\t`) |\n")
        f.write(f"| Artikel Sangat Pendek (< 100 char) | {anom['articles_under_100_chars']} | {round(anom['articles_under_100_chars']/total_records*100, 1)}% | Potensi rintisan/stub dengan konteks kalimat sangat minim |\n")
        f.write(f"| Heading Seksi Penutup (Referensi, dsb.) | {anom['articles_with_section_headings']} | {round(anom['articles_with_section_headings']/total_records*100, 1)}% | Heading baris mandiri (Referensi, Pranala luar, Lihat pula) |\n\n")

        f.write("### Contoh Konteks Anomali Aktual\n\n")
        for k, items in anom["examples"].items():
            if items:
                f.write(f"#### Kategori Anomali: `{k}`\n")
                for ex in items:
                    f.write(f"- **Artikel `{ex['title']}` (ID: `{ex['id']}`)**:\n")
                    if "matches" in ex:
                        f.write(f"  - Pola ditemukan: `{ex['matches']}`\n")
                    if "context" in ex:
                        f.write(f"  - Cuplikan teks: \"{ex['context']}\"\n")
                    if "headings" in ex:
                        f.write(f"  - Heading baris: `{ex['headings']}`\n")
                f.write("\n")

        f.write("## 4. Sampel Inspeksi Berdasarkan Stratifikasi Panjang\n\n")
        strat = report["stratified_inspection_samples"]

        f.write("### Artikel Terpendek (Rentang Bawah)\n")
        s_art = strat["short_article"]
        f.write(f"- **Judul**: {s_art['title']} (ID: `{s_art['id']}`)\n")
        f.write(f"- **Panjang**: {s_art['char_len']} karakter (~{s_art['approx_words']} kata)\n")
        f.write(f"- **URL**: {s_art['url']}\n")
        f.write(f"- **Cuplikan**:\n> \"{s_art['preview']}\"\n\n")

        f.write("### Artikel Median (Rentang Tengah)\n")
        m_art = strat["median_article"]
        f.write(f"- **Judul**: {m_art['title']} (ID: `{m_art['id']}`)\n")
        f.write(f"- **Panjang**: {m_art['char_len']} karakter (~{m_art['approx_words']} kata)\n")
        f.write(f"- **URL**: {m_art['url']}\n")
        f.write(f"- **Cuplikan**:\n> \"{m_art['preview']}\"\n\n")

        f.write("### Artikel Terpanjang (Rentang Atas)\n")
        l_art = strat["long_article"]
        f.write(f"- **Judul**: {l_art['title']} (ID: `{l_art['id']}`)\n")
        f.write(f"- **Panjang**: {l_art['char_len']} karakter (~{l_art['approx_words']} kata)\n")
        f.write(f"- **URL**: {l_art['url']}\n")
        f.write(f"- **Cuplikan**:\n> \"{l_art['preview']}\"\n\n")

    print(f"[Audit Sukses] Laporan JSON diperbarui di: {json_path}")
    print(f"[Audit Sukses] Laporan Markdown diperbarui di: {md_path}")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Audit kualitas data sampel Wikipedia")
    parser.add_argument("--input", type=str, default="data/sample/wiki_sample_300.jsonl", help="Path berkas JSONL sampel")
    parser.add_argument("--output-dir", type=str, default="docs", help="Direktori penyimpanan laporan")
    args = parser.parse_args()

    audit_sample_data(input_file=args.input, output_dir=args.output_dir)
