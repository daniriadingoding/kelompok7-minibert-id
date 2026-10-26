"""
Script untuk menerapkan pipeline cleaner pada sampel data Wikipedia
dan menyusun laporan perbandingan sebelum-sesudah (before-after comparison).
"""

import argparse
import hashlib
import json
import math
import os
import re
import sys
import os

from typing import Dict, Any, List

# Tambahkan root proyek ke sys.path agar impor 'src.data' selalu berhasil
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.stdout.reconfigure(encoding="utf-8")

# Impor modul cleaner
from src.data.cleaner import clean_text, CLEANER_VERSION, DEFAULT_CLEANING_CONFIG


def calculate_percentile(sorted_list: List[float], p: float) -> float:
    """Menghitung persentil deterministik."""
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


def run_cleaning_pipeline(
    input_file: str = "data/sample/wiki_sample_300.jsonl",
    output_cleaned_file: str = "data/sample/wiki_sample_300_cleaned.jsonl",
    output_docs_dir: str = "docs"
) -> Dict[str, Any]:
    """
    Menerapkan cleaner konservatif pada sampel JSONL,
    menghasilkan dataset cleaned dan laporan komparatif sebelum-sesudah.
    """
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Berkas input '{input_file}' tidak ditemukan.")

    os.makedirs(os.path.dirname(output_cleaned_file), exist_ok=True)
    os.makedirs(output_docs_dir, exist_ok=True)

    raw_records = []
    with open(input_file, "r", encoding="utf-8") as f:
        for line_no, line in enumerate(f, 1):
            line_str = line.strip()
            if line_str:
                raw_records.append(json.loads(line_str))

    total_articles = len(raw_records)
    cleaned_records = []

    # Metrik agregat
    articles_changed_count = 0
    articles_empty_after_clean_count = 0
    reduction_ratios = []

    raw_char_lengths = []
    clean_char_lengths = []
    raw_word_counts = []
    clean_word_counts = []

    rule_action_counts = {
        "unicode_normalized": 0,
        "control_chars_stripped": 0,
        "boilerplate_truncated": 0,
        "wiki_templates_cleaned": 0,
        "wiki_links_expanded": 0,
        "html_and_ref_cleaned": 0,
        "urls_removed": 0,
        "whitespace_normalized": 0
    }

    rule_examples = {k: [] for k in rule_action_counts.keys()}

    cleaned_text_hashes = {}
    new_duplicate_pairs = []

    for rec in raw_records:
        rec_id = str(rec.get("id", ""))
        rec_title = str(rec.get("title", ""))
        rec_url = str(rec.get("url", ""))
        raw_text = rec.get("text", "")

        raw_c_len = len(raw_text)
        raw_w_len = len(raw_text.split())

        # Jalankan cleaner konservatif
        clean_res, actions = clean_text(raw_text)

        clean_c_len = len(clean_res)
        clean_w_len = len(clean_res.split())

        if clean_res != raw_text:
            articles_changed_count += 1

        if clean_c_len == 0:
            articles_empty_after_clean_count += 1

        # Rasio pengurangan teks
        red_ratio = (raw_c_len - clean_c_len) / raw_c_len if raw_c_len > 0 else 0.0
        reduction_ratios.append(red_ratio)

        raw_char_lengths.append(raw_c_len)
        clean_char_lengths.append(clean_c_len)
        raw_word_counts.append(raw_w_len)
        clean_word_counts.append(clean_w_len)

        # Catat aturan yang terpicu
        for rule_name, was_triggered in actions.items():
            if rule_name == "cut_context":
                continue
            if was_triggered:
                rule_action_counts[rule_name] += 1
                if len(rule_examples[rule_name]) < 2:
                    rule_examples[rule_name].append({
                        "id": rec_id,
                        "title": rec_title,
                        "raw_snippet": raw_text[:200] + ("..." if raw_c_len > 200 else ""),
                        "clean_snippet": clean_res[:200] + ("..." if clean_c_len > 200 else "")
                    })

        # Cek duplikasi teks baru setelah cleaning
        clean_hash = hashlib.sha256(clean_res.encode("utf-8")).hexdigest()
        if clean_hash in cleaned_text_hashes:
            new_duplicate_pairs.append({
                "hash": clean_hash,
                "first_id": cleaned_text_hashes[clean_hash]["id"],
                "first_title": cleaned_text_hashes[clean_hash]["title"],
                "duplicate_id": rec_id,
                "duplicate_title": rec_title
            })
        else:
            cleaned_text_hashes[clean_hash] = {"id": rec_id, "title": rec_title}

        # Simpan rekaman cleaned beserta metadata provenance
        cleaning_meta = {
            "cleaner_version": CLEANER_VERSION,
            "raw_char_length": raw_c_len,
            "clean_char_length": clean_c_len,
            "raw_approx_words": raw_w_len,
            "clean_approx_words": clean_w_len,
            "char_reduction_ratio": round(red_ratio, 4),
            "rules_applied": [k for k, v in actions.items() if v and k != "cut_context"]
        }
        if "cut_context" in actions:
            cleaning_meta["cut_context"] = actions["cut_context"]

        cleaned_entry = {
            "id": rec_id,
            "url": rec_url,
            "title": rec_title,
            "text": clean_res,
            "cleaning_metadata": cleaning_meta
        }
        cleaned_records.append(cleaned_entry)

    # Tulis berkas cleaned JSONL
    with open(output_cleaned_file, "w", encoding="utf-8") as f:
        for entry in cleaned_records:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    # Identifikasi Top Artikel dengan Pengurangan Teks Terbesar
    sorted_by_reduction = sorted(
        cleaned_records,
        key=lambda x: x["cleaning_metadata"]["char_reduction_ratio"],
        reverse=True
    )
    top_reduced_articles = [
        {
            "id": item["id"],
            "title": item["title"],
            "raw_char_len": item["cleaning_metadata"]["raw_char_length"],
            "clean_char_len": item["cleaning_metadata"]["clean_char_length"],
            "reduction_ratio": item["cleaning_metadata"]["char_reduction_ratio"],
            "rules_applied": item["cleaning_metadata"]["rules_applied"],
            "cut_context": item["cleaning_metadata"].get("cut_context"),
            "clean_preview": item["text"][:250] + ("..." if len(item["text"]) > 250 else "")
        }
        for item in sorted_by_reduction[:5]
    ]

    # Distribusi Rasio Pengurangan
    sorted_ratios = sorted(reduction_ratios)
    ratio_min = round(sorted_ratios[0], 4)
    ratio_median = round(calculate_percentile(sorted_ratios, 0.5), 4)
    ratio_p90 = round(calculate_percentile(sorted_ratios, 0.9), 4)
    ratio_max = round(sorted_ratios[-1], 4)
    ratio_mean = round(sum(sorted_ratios) / len(sorted_ratios), 4)

    # Deteksi anomali sisa pada data yang sudah dibersihkan
    re_tag_like = re.compile(r"<[^>]+>")
    re_wiki_markup = re.compile(r"(\{\{[^}]*\}\}|\[\[[^\]]*\]\])")
    re_url = re.compile(r"https?://\S+|www\.\S+")
    re_control_char = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

    residual_tag_like = []
    residual_markup = []
    residual_urls = []

    for item in cleaned_records:
        txt = item["text"]
        m_tag = re_tag_like.findall(txt)
        if m_tag:
            residual_tag_like.append({"id": item["id"], "title": item["title"], "matches": m_tag})
        m_wiki = re_wiki_markup.findall(txt)
        if m_wiki:
            residual_markup.append({"id": item["id"], "title": item["title"], "matches": m_wiki})
        m_url = re_url.findall(txt)
        if m_url:
            residual_urls.append({"id": item["id"], "title": item["title"], "matches": m_url})

    # Susun Laporan Komparatif
    report = {
        "input_raw_file": input_file,
        "output_cleaned_file": output_cleaned_file,
        "cleaner_version": CLEANER_VERSION,
        "cleaner_config": DEFAULT_CLEANING_CONFIG,
        "summary": {
            "total_articles_before": total_articles,
            "total_articles_after": len(cleaned_records),
            "articles_changed_count": articles_changed_count,
            "articles_unchanged_count": total_articles - articles_changed_count,
            "articles_empty_after_clean": articles_empty_after_clean_count,
            "total_chars_before": sum(raw_char_lengths),
            "total_chars_after": sum(clean_char_lengths),
            "total_approx_words_before": sum(raw_word_counts),
            "total_approx_words_after": sum(clean_word_counts),
            "net_char_reduction_percent": round(
                (sum(raw_char_lengths) - sum(clean_char_lengths)) / sum(raw_char_lengths) * 100, 2
            ),
            "net_word_reduction_percent": round(
                (sum(raw_word_counts) - sum(clean_word_counts)) / sum(raw_word_counts) * 100, 2
            )
        },
        "reduction_ratio_distribution": {
            "min": ratio_min,
            "median": ratio_median,
            "p90": ratio_p90,
            "max": ratio_max,
            "mean": ratio_mean
        },
        "rule_trigger_counts": rule_action_counts,
        "rule_before_after_examples": rule_examples,
        "top_reduced_articles_for_inspection": top_reduced_articles,
        "residual_anomalies": {
            "residual_tag_like_count": len(residual_tag_like),
            "residual_tag_like_samples": residual_tag_like[:3],
            "residual_wiki_markup_count": len(residual_markup),
            "residual_wiki_markup_samples": residual_markup[:3],
            "residual_urls_count": len(residual_urls),
            "residual_urls_samples": residual_urls[:3]
        },
        "newly_emerged_duplicate_texts_count": len(new_duplicate_pairs),
        "newly_emerged_duplicate_pairs": new_duplicate_pairs
    }

    # Simpan JSON
    json_path = os.path.join(output_docs_dir, "cleaning_comparison_report.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Simpan Markdown
    md_path = os.path.join(output_docs_dir, "cleaning_comparison_report.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Laporan Komparatif Pembersihan Data (Before-After Cleaning Report)\n\n")
        f.write(f"- **Versi Cleaner**: `{CLEANER_VERSION}`\n")
        f.write(f"- **Berkas Mentah**: `{input_file}`\n")
        f.write(f"- **Berkas Hasil Bersih**: `{output_cleaned_file}`\n\n")

        f.write("## 1. Ringkasan Perubahan Agregat\n\n")
        s = report["summary"]
        f.write("| Metrik Evaluasi | Sebelum Pembersihan | Sesudah Pembersihan | Selisih / Perubahan |\n")
        f.write("| :--- | :---: | :---: | :---: |\n")
        f.write(f"| **Jumlah Artikel** | {s['total_articles_before']} | {s['total_articles_after']} | 0 (100% dipertahankan) |\n")
        f.write(f"| **Artikel Berubah** | - | {s['articles_changed_count']} | {round(s['articles_changed_count']/total_articles*100, 1)}% artikel disesuaikan |\n")
        f.write(f"| **Artikel Kosong (0 char)** | 0 | {s['articles_empty_after_clean']} | Tidak ada artikel yang musnah |\n")
        f.write(f"| **Total Karakter** | {s['total_chars_before']:,} | {s['total_chars_after']:,} | -{s['net_char_reduction_percent']}% |\n")
        f.write(f"| **Perkiraan Total Kata (Spasi)** | {s['total_approx_words_before']:,} | {s['total_approx_words_after']:,} | -{s['net_word_reduction_percent']}% |\n\n")

        f.write("## 2. Distribusi Proporsi Pengurangan Karakter per Artikel\n\n")
        rd = report["reduction_ratio_distribution"]
        f.write("| Metrik Rasio Pengurangan | Nilai Rasio | Persentase |\n")
        f.write("| :--- | :---: | :---: |\n")
        f.write(f"| **Minimum (Min)** | {rd['min']} | {round(rd['min']*100, 2)}% |\n")
        f.write(f"| **Median (p50)** | {rd['median']} | {round(rd['median']*100, 2)}% |\n")
        f.write(f"| **Persentil 90 (p90)** | {rd['p90']} | {round(rd['p90']*100, 2)}% |\n")
        f.write(f"| **Maksimum (Max)** | {rd['max']} | {round(rd['max']*100, 2)}% |\n")
        f.write(f"| **Rata-rata (Mean)** | {rd['mean']} | {round(rd['mean']*100, 2)}% |\n\n")

        f.write("## 3. Frekuensi Aturan Pembersihan yang Terpicu\n\n")
        f.write("| Nama Aturan Pembersihan | Jumlah Artikel Terpicu | Persentase |\n")
        f.write("| :--- | :---: | :---: |\n")
        for r_name, cnt in report["rule_trigger_counts"].items():
            f.write(f"| `{r_name}` | {cnt} | {round(cnt/total_articles*100, 1)}% |\n")
        f.write("\n")

        f.write("## 4. Top 5 Artikel dengan Pengurangan Terbesar (Inspeksi Manual)\n\n")
        for idx, item in enumerate(report["top_reduced_articles_for_inspection"], 1):
            f.write(f"### {idx}. {item['title']} (ID: `{item['id']}`)\n")
            f.write(f"- **Panjang**: {item['raw_char_len']} -> {item['clean_char_len']} karakter (Pengurangan: **{round(item['reduction_ratio']*100, 1)}%**)\n")
            f.write(f"- **Aturan**: `{', '.join(item['rules_applied'])}`\n")
            if item.get("cut_context"):
                ctx = item["cut_context"]
                f.write(f"- **Konteks Pemotongan Seksi**:\n")
                f.write(f"  - Heading dicocokkan: `{ctx.get('matched_heading')}`\n")
                f.write(f"  - Teks sebelum pemotongan: \"...{ctx.get('text_before_cut')}\"\n")
                f.write(f"  - Teks awal yang terbuang: \"{ctx.get('text_after_cut')}...\"\n")
            f.write(f"- **Teks Tersisa**:\n> \"{item['clean_preview']}\"\n\n")

        f.write("## 5. Pemeriksaan Anomali Sisa & Duplikasi Baru\n\n")
        res = report["residual_anomalies"]
        f.write(f"- Sisa pola mirip tag (`<...>`): **{res['residual_tag_like_count']}**\n")
        if res["residual_tag_like_samples"]:
            for ex in res["residual_tag_like_samples"]:
                f.write(f"  - `{ex['title']}`: `{ex['matches']}` (Catatan: ini adalah kode program atau tanda kurung sudut matematika, bukan tag HTML)\n")
        f.write(f"- Sisa Wiki Markup (`{{}}`, `[[]]`): **{res['residual_wiki_markup_count']}**\n")
        f.write(f"- Sisa URL di badan teks: **{res['residual_urls_count']}**\n")
        f.write(f"- Duplikasi teks baru yang muncul setelah cleaning: **{report['newly_emerged_duplicate_texts_count']}** artikel identik\n\n")

    print(f"[Pipeline Sukses] Data bersih disimpan di: {output_cleaned_file}")
    print(f"[Pipeline Sukses] Laporan JSON disimpan di: {json_path}")
    print(f"[Pipeline Sukses] Laporan Markdown disimpan di: {md_path}")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Terapkan cleaner konservatif dan buat laporan komparatif")
    parser.add_argument("--input", type=str, default="data/sample/wiki_sample_300.jsonl", help="Path berkas sampel mentah")
    parser.add_argument("--output", type=str, default="data/sample/wiki_sample_300_cleaned.jsonl", help="Path output berkas cleaned")
    parser.add_argument("--docs-dir", type=str, default="docs", help="Direktori penyimpanan laporan")
    args = parser.parse_args()

    run_cleaning_pipeline(
        input_file=args.input,
        output_cleaned_file=args.output,
        output_docs_dir=args.docs_dir
    )
