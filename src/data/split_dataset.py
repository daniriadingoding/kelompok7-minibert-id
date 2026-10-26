"""
Script untuk melakukan penyaringan kelayakan data awal (< 10 kata)
dan pembagian partisi tingkat dokumen (80/10/10) secara deterministik (seed 42).
Mencegah data leakage dengan mengelompokkan dokumen dan memastikan 0 irisan ID/hash.
"""

import argparse
import hashlib
import json
import os
import random
import sys
import unicodedata
import re
from typing import Dict, Any, List, Tuple

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.stdout.reconfigure(encoding="utf-8")

from src.data.cleaner import CLEANER_VERSION

DEFAULT_SEED = 42
DEFAULT_MIN_WORDS = 10
SPLIT_RATIOS = {"train": 0.80, "val": 0.10, "test": 0.10}


def normalize_for_leakage_check(text: str) -> str:
    """Normalisasi teks untuk memeriksa identitas leksikal antardokumen."""
    text = unicodedata.normalize("NFC", text).lower()
    tokens = re.findall(r"\b\w+\b", text)
    return " ".join(tokens)


def split_document_dataset(
    input_file: str = "data/pilot/wiki_pilot_3000_cleaned.jsonl",
    output_dir: str = "data/processed/pilot",
    excluded_manifest_path: str = "data/pilot/excluded_articles_manifest.json",
    min_words: int = DEFAULT_MIN_WORDS,
    seed: int = DEFAULT_SEED
) -> Dict[str, Any]:
    """
    Menyaring artikel layak dan membagi partisi dokumen train/val/test secara deterministik.
    """
    if not os.path.exists(input_file):
        raise FileNotFoundError(f"Berkas input '{input_file}' tidak ditemukan.")

    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(os.path.dirname(excluded_manifest_path), exist_ok=True)

    # Hitung hash SHA-256 dari berkas input
    hasher = hashlib.sha256()
    with open(input_file, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    input_file_sha256 = hasher.hexdigest()

    records = []
    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            line_str = line.strip()
            if line_str:
                records.append(json.loads(line_str))

    total_records = len(records)

    # 1. Penyaringan Artikel Layak (Batas minimum kata)
    eligible_records = []
    excluded_records = []

    for r in records:
        txt = r.get("text", "")
        words = txt.split()
        word_count = len(words)
        char_count = len(txt)

        if word_count < min_words:
            excluded_records.append({
                "id": r["id"],
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "word_count": word_count,
                "char_count": char_count,
                "reason": f"Panjang teks di bawah batas minimum kelayakan ({word_count} < {min_words} kata)",
                "preview": txt[:120]
            })
        else:
            eligible_records.append(r)

    # Simpan Manifest Artikel yang Dikeluarkan
    with open(excluded_manifest_path, "w", encoding="utf-8") as f:
        json.dump({
            "total_raw_records": total_records,
            "min_words_threshold": min_words,
            "excluded_count": len(excluded_records),
            "eligible_count": len(eligible_records),
            "excluded_articles": excluded_records
        }, f, indent=2, ensure_ascii=False)

    print(f"[Penyaringan] Dari {total_records} artikel, {len(eligible_records)} layak, {len(excluded_records)} dikeluarkan (< {min_words} kata).")

    # 2. Pengecekan Duplikasi Teks Ter-normalisasi untuk Pengelompokan (Cluster)
    norm_text_to_docs: Dict[str, List[Dict[str, Any]]] = {}
    for r in eligible_records:
        norm_txt = normalize_for_leakage_check(r["text"])
        norm_hash = hashlib.sha256(norm_txt.encode("utf-8")).hexdigest()
        if norm_hash not in norm_text_to_docs:
            norm_text_to_docs[norm_hash] = []
        norm_text_to_docs[norm_hash].append(r)

    # Setiap cluster mewakili satu unit independen partisi
    clusters = list(norm_text_to_docs.values())
    # Urutkan deterministik berdasarkan ID artikel pertama dalam cluster sebelum pengacakan
    clusters.sort(key=lambda c: str(c[0]["id"]))

    # Pengacakan terkontrol dengan seed tetap
    rng = random.Random(seed)
    rng.shuffle(clusters)

    # Hitung target kuota cluster
    total_clusters = len(clusters)
    n_train_clusters = int(round(total_clusters * SPLIT_RATIOS["train"]))
    n_val_clusters = int(round(total_clusters * SPLIT_RATIOS["val"]))
    # Sisanya masuk test untuk mencegah selisih pembulatan
    n_test_clusters = total_clusters - n_train_clusters - n_val_clusters

    train_clusters = clusters[:n_train_clusters]
    val_clusters = clusters[n_train_clusters:n_train_clusters + n_val_clusters]
    test_clusters = clusters[n_train_clusters + n_val_clusters:]

    # Kumpulkan dokumen per split
    splits_docs = {
        "train": [doc for c in train_clusters for doc in c],
        "val": [doc for c in val_clusters for doc in c],
        "test": [doc for c in test_clusters for doc in c]
    }

    # 3. Verifikasi 0 Irisan (Zero Leakage Check)
    split_ids = {s: set(r["id"] for r in docs) for s, docs in splits_docs.items()}
    split_norm_hashes = {
        s: set(hashlib.sha256(normalize_for_leakage_check(r["text"]).encode("utf-8")).hexdigest() for r in docs)
        for s, docs in splits_docs.items()
    }

    train_val_id_overlap = split_ids["train"].intersection(split_ids["val"])
    train_test_id_overlap = split_ids["train"].intersection(split_ids["test"])
    val_test_id_overlap = split_ids["val"].intersection(split_ids["test"])

    train_val_hash_overlap = split_norm_hashes["train"].intersection(split_norm_hashes["val"])
    train_test_hash_overlap = split_norm_hashes["train"].intersection(split_norm_hashes["test"])
    val_test_hash_overlap = split_norm_hashes["val"].intersection(split_norm_hashes["test"])

    assert len(train_val_id_overlap) == 0, f"Leakage ID train-val: {train_val_id_overlap}"
    assert len(train_test_id_overlap) == 0, f"Leakage ID train-test: {train_test_id_overlap}"
    assert len(val_test_id_overlap) == 0, f"Leakage ID val-test: {val_test_id_overlap}"

    assert len(train_val_hash_overlap) == 0, f"Leakage Hash train-val: {train_val_hash_overlap}"
    assert len(train_test_hash_overlap) == 0, f"Leakage Hash train-test: {train_test_hash_overlap}"
    assert len(val_test_hash_overlap) == 0, f"Leakage Hash val-test: {val_test_hash_overlap}"

    # 4. Tulis berkas train.jsonl, val.jsonl, test.jsonl
    split_stats = {}
    for split_name, docs in splits_docs.items():
        split_path = os.path.join(output_dir, f"{split_name}.jsonl")
        word_counts = [len(r["text"].split()) for r in docs]
        char_counts = [len(r["text"]) for r in docs]

        with open(split_path, "w", encoding="utf-8") as f:
            for r in docs:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")

        split_stats[split_name] = {
            "document_count": len(docs),
            "ratio_of_eligible": round(len(docs) / len(eligible_records), 4),
            "total_words_approx": sum(word_counts),
            "total_chars": sum(char_counts),
            "file_path": split_path
        }
        print(f"[{split_name.upper()}] {len(docs)} dokumen ({split_stats[split_name]['total_words_approx']:,} kata) ditulis ke {split_path}")

    # 5. Simpan Manifest Partisi
    manifest_data = {
        "dataset_name": "wikimedia/wikipedia: 20231101.id (pilot)",
        "cleaner_version": CLEANER_VERSION,
        "input_cleaned_file": input_file,
        "input_cleaned_file_sha256": input_file_sha256,
        "seed": seed,
        "split_ratios_target": SPLIT_RATIOS,
        "min_words_filter": min_words,
        "total_source_records": total_records,
        "excluded_records_count": len(excluded_records),
        "eligible_records_count": len(eligible_records),
        "split_statistics": split_stats,
        "deduplication_notes": (
            "Deduplikasi berbasis hash SHA-256 teks normalisasi (lowercase, NFC, tanda baca diabaikan) "
            "mengelompokkan dokumen identik sebelum split untuk mencegah exact lexical leakage. "
            "Keterbatasan: Deduplikasi persis ini tidak mendeteksi near-duplicate (dokumen dengan sedikit variasi kata/kalimat), "
            "paraphrase, atau kutipan berulang sebagian. Oleh karena itu, tidak diklaim menghilangkan 100% potensi semantic overlap."
        ),
        "verification": {
            "train_val_id_overlap": len(train_val_id_overlap),
            "train_test_id_overlap": len(train_test_id_overlap),
            "val_test_id_overlap": len(val_test_id_overlap),
            "train_val_hash_overlap": len(train_val_hash_overlap),
            "train_test_hash_overlap": len(train_test_hash_overlap),
            "val_test_hash_overlap": len(val_test_hash_overlap),
            "leakage_status": "ZERO_LEAKAGE_CONFIRMED"
        },
        "split_ids": {
            s: sorted(list(ids)) for s, ids in split_ids.items()
        }
    }

    manifest_output_path = os.path.join(output_dir, "split_manifest.json")
    with open(manifest_output_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2, ensure_ascii=False)

    print(f"[Sukses] Manifest split tersimpan di: {manifest_output_path}")
    return manifest_data


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Bagi dataset pilot menjadi train/val/test tingkat dokumen")
    parser.add_argument("--input", type=str, default="data/pilot/wiki_pilot_3000_cleaned.jsonl", help="Path berkas input cleaned")
    parser.add_argument("--output-dir", type=str, default="data/processed/pilot", help="Direktori output partisi")
    parser.add_argument("--min-words", type=int, default=DEFAULT_MIN_WORDS, help="Ambang batas minimum kata")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Seed keacakan")
    args = parser.parse_args()

    split_document_dataset(
        input_file=args.input,
        output_dir=args.output_dir,
        min_words=args.min_words,
        seed=args.seed
    )
