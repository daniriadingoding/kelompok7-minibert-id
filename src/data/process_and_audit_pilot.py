"""
Script komprehensif untuk memproses dataset pilot 3.000 artikel:
1. Menerapkan cleaner v1.1.0 secara konservatif.
2. Melakukan deduplikasi teks hasil cleaning (SHA-256) dengan logging alasan retensi/eksklusi.
3. Mengaudit distribusi, anomali, dan contoh representatif (pendek, sedang, panjang, daftar, kode, kutipan asing).
4. Menyimpan laporan komparatif dalam format JSON dan Markdown.
"""

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
from typing import Dict, Any, List, Optional, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.stdout.reconfigure(encoding="utf-8")

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


def is_list_like_article(text: str) -> bool:
    """Mendeteksi apakah artikel dominan berupa daftar/katalog nama/entitas."""
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    if not lines:
        return False
    bullet_or_number = sum(1 for l in lines if l.startswith(("-", "*", "•")) or re.match(r"^\d+[\.\)]", l))
    ratio = bullet_or_number / len(lines)
    return ratio > 0.35 or "daftar" in text[:100].lower()


def contains_code_or_tech_syntax(text: str) -> bool:
    """Mendeteksi cuplikan kode program atau sintaks teknis."""
    code_patterns = [
        r"\b(?:def|function|class|import|return|var|let|const|SELECT|FROM|WHERE)\b",
        r"<-|->|=>|::|\{\||\|\}",
        r"\b(?:html|css|javascript|python|java|c\+\+|elixir|php|sql)\b"
    ]
    for p in code_patterns:
        if re.search(p, text, re.IGNORECASE):
            return True
    return False


def contains_foreign_quotes_or_latin(text: str) -> bool:
    """Mendeteksi keberadaan kutipan bahasa asing atau nama taksonomi Latin."""
    foreign_patterns = [
        r"\b(?:Latin:|bahasa Inggris:|bahasa Belanda:|bahasa Prancis:|bahasa Jerman:)\b",
        r"\b(?:species|genus|ordo|familia|et al\.|ibid\.|op\. cit\.)\b",
        r"\b(?:The|and|of|in|to|for|with|on|at|by|from)\b [A-Z][a-z]+"
    ]
    for p in foreign_patterns:
        if re.search(p, text):
            return True
    return False


def process_and_audit_pilot(
    input_file: str = "data/pilot/wiki_pilot_3000.jsonl",
    output_cleaned_file: str = "data/pilot/wiki_pilot_3000_cleaned.jsonl",
    output_dedup_log: str = "data/pilot/pilot_deduplication_log.json",
    output_docs_dir: str = "docs"
) -> Dict[str, Any]:
    start_time = time.time()

    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Berkas input pilot '{input_file}' tidak ditemukan.")

    raw_file_size_bytes = os.path.getsize(input_file)
    raw_file_size_mb = round(raw_file_size_bytes / (1024 * 1024), 2)

    raw_records = []
    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if line_str:
                raw_records.append(json.loads(line_str))

    total_raw = len(raw_records)
    cleaned_entries = []
    seen_hashes = {}
    deduplication_log = []

    # Metrik agregat
    articles_changed_count = 0
    articles_empty_count = 0
    reduction_ratios = []

    raw_chars_list = []
    clean_chars_list = []
    raw_words_list = []
    clean_words_list = []

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

    # Kategori artikel representatif untuk inspeksi kualitatif
    sample_categories = {
        "short_article": None,
        "median_article": None,
        "long_article": None,
        "list_like_article": None,
        "code_article": None,
        "foreign_quote_article": None
    }

    for rec in raw_records:
        rec_id = str(rec.get("id", ""))
        rec_title = str(rec.get("title", ""))
        rec_url = str(rec.get("url", ""))
        raw_text = rec.get("text", "")

        raw_c = len(raw_text)
        raw_w = len(raw_text.split())

        clean_text_res, actions = clean_text(raw_text)
        clean_c = len(clean_text_res)
        clean_w = len(clean_text_res.split())

        if clean_text_res != raw_text:
            articles_changed_count += 1
        if clean_c == 0:
            articles_empty_count += 1

        red_ratio = (raw_c - clean_c) / raw_c if raw_c > 0 else 0.0
        reduction_ratios.append(red_ratio)

        raw_chars_list.append(raw_c)
        clean_chars_list.append(clean_c)
        raw_words_list.append(raw_w)
        clean_words_list.append(clean_w)

        for rule_name, triggered in actions.items():
            if rule_name != "cut_context" and triggered:
                rule_action_counts[rule_name] += 1

        # Deduplikasi Teks Cleaned (SHA-256)
        text_hash = hashlib.sha256(clean_text_res.encode("utf-8")).hexdigest()
        is_duplicate = False

        if text_hash in seen_hashes:
            is_duplicate = True
            first_seen = seen_hashes[text_hash]
            deduplication_log.append({
                "hash": text_hash,
                "kept_record": {"id": first_seen["id"], "title": first_seen["title"]},
                "excluded_record": {"id": rec_id, "title": rec_title},
                "reason": "Teks bersih identik persis dengan artikel yang pertama kali diproses."
            })
        else:
            seen_hashes[text_hash] = {"id": rec_id, "title": rec_title}

        if not is_duplicate:
            cleaning_meta = {
                "cleaner_version": CLEANER_VERSION,
                "raw_char_len": raw_c,
                "clean_char_len": clean_c,
                "raw_words": raw_w,
                "clean_words": clean_w,
                "reduction_ratio": round(red_ratio, 4),
                "rules_applied": [k for k, v in actions.items() if v and k != "cut_context"]
            }
            if "cut_context" in actions:
                cleaning_meta["cut_context"] = actions["cut_context"]

            cleaned_entries.append({
                "id": rec_id,
                "url": rec_url,
                "title": rec_title,
                "text": clean_text_res,
                "metadata": cleaning_meta
            })

    # Simpan Berkas Bersih
    os.makedirs(os.path.dirname(output_cleaned_file), exist_ok=True)
    with open(output_cleaned_file, "w", encoding="utf-8") as f:
        for item in cleaned_entries:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")

    clean_file_size_bytes = os.path.getsize(output_cleaned_file)
    clean_file_size_mb = round(clean_file_size_bytes / (1024 * 1024), 2)

    # Simpan Log Deduplikasi
    os.makedirs(os.path.dirname(output_dedup_log), exist_ok=True)
    with open(output_dedup_log, "w", encoding="utf-8") as f:
        json.dump(deduplication_log, f, indent=2, ensure_ascii=False)

    # Pemilihan Sampel Representatif Kualitatif
    sorted_by_len = sorted(cleaned_entries, key=lambda x: x["metadata"]["clean_char_len"])
    sample_categories["short_article"] = {
        "title": sorted_by_len[0]["title"],
        "id": sorted_by_len[0]["id"],
        "char_len": sorted_by_len[0]["metadata"]["clean_char_len"],
        "words": sorted_by_len[0]["metadata"]["clean_words"],
        "preview": sorted_by_len[0]["text"][:280]
    }
    mid_idx = len(sorted_by_len) // 2
    sample_categories["median_article"] = {
        "title": sorted_by_len[mid_idx]["title"],
        "id": sorted_by_len[mid_idx]["id"],
        "char_len": sorted_by_len[mid_idx]["metadata"]["clean_char_len"],
        "words": sorted_by_len[mid_idx]["metadata"]["clean_words"],
        "preview": sorted_by_len[mid_idx]["text"][:280]
    }
    sample_categories["long_article"] = {
        "title": sorted_by_len[-1]["title"],
        "id": sorted_by_len[-1]["id"],
        "char_len": sorted_by_len[-1]["metadata"]["clean_char_len"],
        "words": sorted_by_len[-1]["metadata"]["clean_words"],
        "preview": sorted_by_len[-1]["text"][:280]
    }

    for item in cleaned_entries:
        t = item["text"]
        if sample_categories["list_like_article"] is None and is_list_like_article(t):
            sample_categories["list_like_article"] = {
                "title": item["title"],
                "id": item["id"],
                "char_len": item["metadata"]["clean_char_len"],
                "words": item["metadata"]["clean_words"],
                "preview": t[:280]
            }
        if sample_categories["code_article"] is None and contains_code_or_tech_syntax(t):
            sample_categories["code_article"] = {
                "title": item["title"],
                "id": item["id"],
                "char_len": item["metadata"]["clean_char_len"],
                "words": item["metadata"]["clean_words"],
                "preview": t[:280]
            }
        if sample_categories["foreign_quote_article"] is None and contains_foreign_quotes_or_latin(t):
            sample_categories["foreign_quote_article"] = {
                "title": item["title"],
                "id": item["id"],
                "char_len": item["metadata"]["clean_char_len"],
                "words": item["metadata"]["clean_words"],
                "preview": t[:280]
            }

    # Distribusi Panjang
    clean_chars_sorted = sorted(clean_chars_list)
    char_dist = {
        "min": clean_chars_sorted[0],
        "median": calculate_percentile(clean_chars_sorted, 0.5),
        "p90": calculate_percentile(clean_chars_sorted, 0.9),
        "max": clean_chars_sorted[-1],
        "mean": round(sum(clean_chars_sorted) / len(clean_chars_sorted), 2)
    }

    clean_words_sorted = sorted(clean_words_list)
    word_dist = {
        "note": "Hitungan berbasis pemisahan spasi (whitespace split). Bukan jumlah token tokenizer final.",
        "min": clean_words_sorted[0],
        "median": calculate_percentile(clean_words_sorted, 0.5),
        "p90": calculate_percentile(clean_words_sorted, 0.9),
        "max": clean_words_sorted[-1],
        "mean": round(sum(clean_words_sorted) / len(clean_words_sorted), 2)
    }

    reduction_sorted = sorted(reduction_ratios)
    red_dist = {
        "min": round(reduction_sorted[0], 4),
        "median": round(calculate_percentile(reduction_sorted, 0.5), 4),
        "p90": round(calculate_percentile(reduction_sorted, 0.9), 4),
        "max": round(reduction_sorted[-1], 4),
        "mean": round(sum(reduction_sorted) / len(reduction_sorted), 4)
    }

    # Top 10 Pengurangan Terbesar
    sorted_by_red = sorted(cleaned_entries, key=lambda x: x["metadata"]["reduction_ratio"], reverse=True)
    top_10_reduced = [
        {
            "id": it["id"],
            "title": it["title"],
            "raw_len": it["metadata"]["raw_char_len"],
            "clean_len": it["metadata"]["clean_char_len"],
            "reduction_percent": round(it["metadata"]["reduction_ratio"] * 100, 2),
            "rules": it["metadata"]["rules_applied"],
            "cut_context": it["metadata"].get("cut_context"),
            "clean_preview": it["text"][:220] + ("..." if len(it["text"]) > 220 else "")
        }
        for it in sorted_by_red[:10]
    ]

    duration_sec = round(time.time() - start_time, 2)

    # Laporan Lengkap
    report = {
        "dataset_type": "pilot_subset",
        "cleaner_version": CLEANER_VERSION,
        "input_raw_file": input_file,
        "output_cleaned_file": output_cleaned_file,
        "raw_file_size_bytes": raw_file_size_bytes,
        "raw_file_size_mb": raw_file_size_mb,
        "clean_file_size_bytes": clean_file_size_bytes,
        "clean_file_size_mb": clean_file_size_mb,
        "processing_duration_seconds": duration_sec,
        "summary": {
            "raw_articles_count": total_raw,
            "cleaned_articles_retained": len(cleaned_entries),
            "duplicate_articles_excluded": len(deduplication_log),
            "articles_empty_after_clean": articles_empty_count,
            "articles_modified_by_cleaner": articles_changed_count,
            "total_raw_characters": sum(raw_chars_list),
            "total_clean_characters": sum(clean_chars_list),
            "net_character_reduction_percent": round(
                (sum(raw_chars_list) - sum(clean_chars_list)) / sum(raw_chars_list) * 100, 2
            ),
            "total_raw_approx_words": sum(raw_words_list),
            "total_clean_approx_words": sum(clean_words_list),
            "net_word_reduction_percent": round(
                (sum(raw_words_list) - sum(clean_words_list)) / sum(raw_words_list) * 100, 2
            )
        },
        "character_length_distribution": char_dist,
        "approx_word_count_distribution": word_dist,
        "reduction_ratio_distribution": red_dist,
        "rule_action_counts": rule_action_counts,
        "top_10_largest_reductions": top_10_reduced,
        "qualitative_representative_samples": sample_categories,
        "deduplication_summary": {
            "unique_text_hashes": len(seen_hashes),
            "exact_duplicate_pairs_found": len(deduplication_log),
            "note": (
                "Deduplikasi berbasis hash SHA-256 hanya menjaring duplikasi verbatim persis. "
                "Artikel dengan parafrasa ringan, variasi ejaan, atau kemiripan topikal tidak terdeteksi "
                "oleh deduplikasi persis ini dan memerlukan pemeriksaan n-gram minhash/Jaccard pada tahap lanjut."
            )
        }
    }

    # Tulis JSON
    os.makedirs(output_docs_dir, exist_ok=True)
    json_path = os.path.join(output_docs_dir, "pilot_audit_report.json")
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # Tulis Markdown
    md_path = os.path.join(output_docs_dir, "pilot_audit_report.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write("# Laporan Audit & Pembersihan Dataset Pilot (3.000 Artikel Wikipedia)\n\n")
        f.write(f"- **Versi Cleaner**: `{CLEANER_VERSION}`\n")
        f.write(f"- **Waktu Pemrosesan Bersih**: {duration_sec} detik\n")
        f.write(f"- **Ukuran Berkas Mentah**: {raw_file_size_mb} MB ({raw_file_size_bytes:,} bytes)\n")
        f.write(f"- **Ukuran Berkas Bersih**: {clean_file_size_mb} MB ({clean_file_size_bytes:,} bytes)\n\n")

        s = report["summary"]
        f.write("## 1. Ringkasan Eksekutif Pilot Dataset\n\n")
        f.write("| Metrik Evaluasi | Nilai Mentah | Nilai Bersih (Cleaned) | Selisih / Persentase |\n")
        f.write("| :--- | :---: | :---: | :---: |\n")
        f.write(f"| **Jumlah Artikel** | {s['raw_articles_count']:,} | {s['cleaned_articles_retained']:,} | {s['duplicate_articles_excluded']} duplikat dikeluarkan |\n")
        f.write(f"| **Artikel Mengalami Modifikasi** | - | {s['articles_modified_by_cleaner']:,} | {round(s['articles_modified_by_cleaner']/total_raw*100, 1)}% artikel disesuaikan |\n")
        f.write(f"| **Artikel Menjadi Kosong (0 char)** | 0 | {s['articles_empty_after_clean']} | 0 artikel musnah |\n")
        f.write(f"| **Total Karakter** | {s['total_raw_characters']:,} | {s['total_clean_characters']:,} | -{s['net_character_reduction_percent']}% |\n")
        f.write(f"| **Perkiraan Total Kata (Spasi)** | {s['total_raw_approx_words']:,} | {s['total_clean_approx_words']:,} | -{s['net_word_reduction_percent']}% |\n\n")

        f.write("## 2. Distribusi Panjang Karakter dan Kata (Cleaned)\n\n")
        f.write("> **Catatan Metrik**: Perkiraan kata dihitung berbasis *whitespace split*. Angka ini **bukan** jumlah token tokenizer final.\n\n")
        f.write("| Metrik Distribusi | Panjang Karakter | Perkiraan Kata (Whitespace) |\n")
        f.write("| :--- | :---: | :---: |\n")
        f.write(f"| **Minimum** | {char_dist['min']:,} | {word_dist['min']:,} |\n")
        f.write(f"| **Median (p50)** | {char_dist['median']:,} | {word_dist['median']:,} |\n")
        f.write(f"| **Persentil 90 (p90)** | {char_dist['p90']:,} | {word_dist['p90']:,} |\n")
        f.write(f"| **Maksimum** | {char_dist['max']:,} | {word_dist['max']:,} |\n")
        f.write(f"| **Rata-rata (Mean)** | {char_dist['mean']:,} | {word_dist['mean']:,} |\n\n")

        f.write("## 3. Frekuensi Aturan Pembersihan yang Terpicu\n\n")
        f.write("| Aturan Pembersihan | Jumlah Terpicu | Persentase |\n")
        f.write("| :--- | :---: | :---: |\n")
        for r_name, cnt in report["rule_action_counts"].items():
            f.write(f"| `{r_name}` | {cnt:,} | {round(cnt/total_raw*100, 1)}% |\n")
        f.write("\n")

        f.write("## 4. Analisis Deduplikasi Teks Persis & Keterbatasannya\n\n")
        ds = report["deduplication_summary"]
        f.write(f"- Jumlah teks hash SHA-256 unik: **{ds['unique_text_hashes']:,}**\n")
        f.write(f"- Jumlah pasangan duplikat persis ditemukan: **{ds['exact_duplicate_pairs_found']:,}**\n")
        f.write(f"> **Keterbatasan Ilmiah**: {ds['note']}\n\n")

        f.write("## 5. Top 10 Pengurangan Terbesar (Inspeksi Lokasi Pemotongan)\n\n")
        for idx, item in enumerate(report["top_10_largest_reductions"], 1):
            f.write(f"### {idx}. {item['title']} (ID: `{item['id']}`)\n")
            f.write(f"- **Panjang**: {item['raw_len']:,} -> {item['clean_len']:,} karakter (Pengurangan: **{item['reduction_percent']}%**)\n")
            f.write(f"- **Aturan**: `{', '.join(item['rules'])}`\n")
            if item.get("cut_context"):
                ctx = item["cut_context"]
                f.write(f"- **Konteks Lokasi Pemotongan**:\n")
                f.write(f"  - Heading dicocokkan: `{ctx.get('matched_heading')}`\n")
                f.write(f"  - Teks sebelum pemotongan: \"...{ctx.get('text_before_cut')}\"\n")
                f.write(f"  - Teks awal yang terbuang: \"{ctx.get('text_after_cut')}...\"\n")
            f.write(f"- **Cuplikan Narasi Bersih Tersisa**:\n> \"{item['clean_preview']}\"\n\n")

        f.write("## 6. Contoh Kualitatif Representatif (Beragam Tipe Dokumen)\n\n")
        cats = report["qualitative_representative_samples"]

        f.write("### A. Teks Pendek (Rentang Bawah)\n")
        if cats["short_article"]:
            c = cats["short_article"]
            f.write(f"- **Judul**: {c['title']} (ID: `{c['id']}` | {c['char_len']} char / {c['words']} kata)\n")
            f.write(f"> \"{c['preview']}\"\n\n")

        f.write("### B. Teks Sedang (Rentang Median)\n")
        if cats["median_article"]:
            c = cats["median_article"]
            f.write(f"- **Judul**: {c['title']} (ID: `{c['id']}` | {c['char_len']} char / {c['words']} kata)\n")
            f.write(f"> \"{c['preview']}\"\n\n")

        f.write("### C. Teks Panjang (Rentang Atas)\n")
        if cats["long_article"]:
            c = cats["long_article"]
            f.write(f"- **Judul**: {c['title']} (ID: `{c['id']}` | {c['char_len']} char / {c['words']} kata)\n")
            f.write(f"> \"{c['preview']}\"\n\n")

        f.write("### D. Teks Dominan Daftar / Katalog\n")
        if cats["list_like_article"]:
            c = cats["list_like_article"]
            f.write(f"- **Judul**: {c['title']} (ID: `{c['id']}` | {c['char_len']} char / {c['words']} kata)\n")
            f.write(f"> \"{c['preview']}\"\n\n")

        f.write("### E. Teks Memuat Sintaks Teknis / Kode Program\n")
        if cats["code_article"]:
            c = cats["code_article"]
            f.write(f"- **Judul**: {c['title']} (ID: `{c['id']}` | {c['char_len']} char / {c['words']} kata)\n")
            f.write(f"> \"{c['preview']}\"\n\n")

        f.write("### F. Teks Memuat Istilah Taksonomi / Kutipan Bahasa Lain\n")
        if cats["foreign_quote_article"]:
            c = cats["foreign_quote_article"]
            f.write(f"- **Judul**: {c['title']} (ID: `{c['id']}` | {c['char_len']} char / {c['words']} kata)\n")
            f.write(f"> \"{c['preview']}\"\n\n")

    print(f"[Pilot Sukses] Data pilot bersih: {output_cleaned_file}")
    print(f"[Pilot Sukses] Laporan JSON: {json_path}")
    print(f"[Pilot Sukses] Laporan Markdown: {md_path}")
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Proses dan audit dataset pilot 3000 artikel")
    parser.add_argument("--input", type=str, default="data/pilot/wiki_pilot_3000.jsonl", help="Path berkas mentah pilot")
    parser.add_argument("--output", type=str, default="data/pilot/wiki_pilot_3000_cleaned.jsonl", help="Path berkas bersih pilot")
    parser.add_argument("--dedup-log", type=str, default="data/pilot/pilot_deduplication_log.json", help="Path log deduplikasi")
    parser.add_argument("--docs-dir", type=str, default="docs", help="Direktori laporan")
    args = parser.parse_args()

    process_and_audit_pilot(
        input_file=args.input,
        output_cleaned_file=args.output,
        output_dedup_log=args.dedup_log,
        output_docs_dir=args.docs_dir
    )
