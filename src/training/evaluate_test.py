"""
Skrip Evaluasi Final Independen untuk Model Mini-BERT Bahasa Indonesia pada Split Test.

Karakteristik & Integritas:
1. Memuat model terpilih melalui loader tervalidasi MiniBertForMaskedLM.from_pretrained.
2. Menggunakan PrechunkedMLMDataset dan MLMDataCollator dalam mode 'eval' (eval_seed=42).
3. Menangani 3.427 chunk sumber menjadi 3.426 chunk siap MLM sesuai mlm_excluded_chunks_manifest.json (1 chunk tanpa kandidat reguler disaring otomatis).
4. Menghitung Cross-Entropy Loss, Top-1 Accuracy, dan Top-5 Accuracy berbobot pada seluruh 8.000 vocabulary.
5. Beroperasi murni pada torch.inference_mode() dan model.eval() tanpa pembaruan optimizer atau mutasi bobot.
6. Menyimpan laporan metrik lengkap beserta seluruh hash integritas (model.pt, config.json, vocab.json, data test) ke format JSON dan CSV.
"""

import argparse
import csv
import datetime
import json
import os
import sys
import time
from typing import Any, Dict

import torch
from torch.utils.data import DataLoader

from src.data.dataset import PrechunkedMLMDataset, MLMDataCollator
from src.models.bert import MiniBertForMaskedLM
from src.models.config import MiniBertConfig
from src.training.checkpoint import compute_file_sha256
from src.training.metrics import MLMMetricAccumulator


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Evaluasi Final Mini-BERT Bahasa Indonesia pada Split Test (Steril & Independen)."
    )
    parser.add_argument(
        "--model-dir",
        type=str,
        default="runs/lr_1e3_gpu/best_model",
        help="Direktori model inferensi yang memuat model.pt dan config.json.",
    )
    parser.add_argument(
        "--data-dir",
        type=str,
        default="data/processed/pilot",
        help="Direktori yang memuat berkas test chunk dan vocab.",
    )
    parser.add_argument(
        "--test-file",
        type=str,
        default="test_chunks.jsonl",
        help="Nama berkas chunk uji (misal test_chunks.jsonl atau val_chunks.jsonl untuk uji coba).",
    )
    parser.add_argument(
        "--tokenizer-dir",
        type=str,
        default="data/processed/pilot",
        help="Direktori tokenizer untuk validasi vocab hash.",
    )
    parser.add_argument(
        "--device",
        type=str,
        default="auto",
        choices=["auto", "cpu", "cuda"],
        help="Pilihan device komputasi ('auto', 'cpu', 'cuda').",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=32,
        help="Ukuran batch evaluasi.",
    )
    parser.add_argument(
        "--eval-seed",
        type=int,
        default=42,
        help="Seed deterministik collator evaluasi.",
    )
    parser.add_argument(
        "--output-file",
        type=str,
        default=None,
        help="Jalur berkas output laporan JSON (default: <model-dir>/../final_test_evaluation.json).",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    start_time = time.time()

    # 1. Tentukan Device
    if args.device == "auto":
        device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
    else:
        device = torch.device(args.device)

    print("================================================================================")
    print("      EVALUASI FINAL STERIL MINI-BERT BAHASA INDONESIA PADA SPLIT TEST          ")
    print("================================================================================")
    print(f"Device Komputasi : {device}")
    print(f"Direktori Model  : {args.model_dir}")
    print(f"Berkas Evaluasi  : {os.path.join(args.data_dir, args.test_file)}")
    print(f"Batch Size       : {args.batch_size} | Eval Seed: {args.eval_seed}")
    print("--------------------------------------------------------------------------------")

    # 2. Validasi Keberadaan Berkas dan Integritas Hash
    model_pt_path = os.path.join(args.model_dir, "model.pt")
    config_json_path = os.path.join(args.model_dir, "config.json")
    test_path = os.path.join(args.data_dir, args.test_file)
    vocab_path = os.path.join(args.tokenizer_dir, "vocab.json")

    for path, desc in [
        (model_pt_path, "Bobot model (model.pt)"),
        (config_json_path, "Konfigurasi model (config.json)"),
        (test_path, f"Berkas data ({args.test_file})"),
        (vocab_path, "Vocabulary (vocab.json)"),
    ]:
        if not os.path.exists(path):
            raise FileNotFoundError(f"Berkas {desc} tidak ditemukan di: '{path}'.")

    model_pt_sha256 = compute_file_sha256(model_pt_path)
    config_json_sha256 = compute_file_sha256(config_json_path)
    test_file_sha256 = compute_file_sha256(test_path)

    with open(vocab_path, "r", encoding="utf-8") as f:
        vocab_dict = json.load(f)
    canonical_vocab_hash = MiniBertConfig.compute_vocab_hash(vocab_dict)

    print("[Integritas Hash]")
    print(f"  - model.pt SHA-256   : {model_pt_sha256}")
    print(f"  - config.json SHA-256: {config_json_sha256}")
    print(f"  - vocab canonical    : {canonical_vocab_hash}")
    print(f"  - data file SHA-256  : {test_file_sha256}")
    print("--------------------------------------------------------------------------------")

    # 3. Muat Model via Loader Tervalidasi
    model = MiniBertForMaskedLM.from_pretrained(
        load_directory=args.model_dir,
        tokenizer_dir=args.tokenizer_dir,
        require_tokenizer=True,
    )
    model.to(device)
    model.eval()

    # 4. Muat Dataset dan Tangani Penyaringan Zero-Candidates (3.427 -> 3.426 pada Test)
    # Hitung jumlah baris fisik
    total_raw_chunks = 0
    with open(test_path, "r", encoding="utf-8") as f:
        for _ in f:
            total_raw_chunks += 1

    dataset = PrechunkedMLMDataset(
        jsonl_path=test_path,
        vocab_size=model.config.vocab_size,
        max_length=model.config.max_position_embeddings,
        filter_zero_candidates=True,
    )

    num_evaluated_chunks = len(dataset)
    num_excluded_chunks = len(dataset.excluded_chunks)

    print(f"[Dataset Chunks]")
    print(f"  - Total Chunk Fisik Sumber : {total_raw_chunks:,}")
    print(f"  - Chunk Siap Evaluasi MLM  : {num_evaluated_chunks:,}")
    print(f"  - Chunk Dikeluarkan (Zero) : {num_excluded_chunks:,}")
    if num_excluded_chunks > 0:
        for exc in dataset.excluded_chunks:
            print(f"    * doc_id={exc['doc_id']}, chunk_index={exc['chunk_index']} ({exc['reason']})")
    print("--------------------------------------------------------------------------------")

    # 5. Inisialisasi Data Collator & DataLoader
    collator = MLMDataCollator(
        vocab_size=model.config.vocab_size,
        mode="eval",
        eval_seed=args.eval_seed,
    )

    dataloader = DataLoader(
        dataset,
        batch_size=args.batch_size,
        shuffle=False,
        collate_fn=collator,
        num_workers=0,
        pin_memory=False,
    )

    # 6. Eksekusi Evaluasi Deterministik
    print("Menjalankan inferensi evaluasi...")
    accumulator = MLMMetricAccumulator(vocab_size=model.config.vocab_size)

    with torch.inference_mode():
        for batch_idx, batch in enumerate(dataloader):
            input_ids = batch["input_ids"].to(device)
            attention_mask = batch["attention_mask"].to(device)
            labels = batch["labels"].to(device)

            logits = model(input_ids=input_ids, attention_mask=attention_mask)
            accumulator.update(logits, labels)

    eval_duration = time.time() - start_time
    metrics = accumulator.compute()

    # 7. Tampilkan Hasil
    print("================================================================================")
    print("                           HASIL EVALUASI FINAL                                 ")
    print("================================================================================")
    print(f"Total Target Token Evaluasi : {metrics['total_targets']:,}")
    print(f"Masked Cross-Entropy Loss   : {metrics['loss']:.6f} nats")
    print(f"Effective Masked Perplexity : {metrics['exp_masked_loss']:.4f}")
    print(f"Top-1 Accuracy              : {metrics['top1_acc'] * 100:.4f}% ({metrics['total_top1_correct']:,}/{metrics['total_targets']:,})")
    print(f"Top-5 Accuracy              : {metrics['top5_acc'] * 100:.4f}% ({metrics['total_top5_correct']:,}/{metrics['total_targets']:,})")
    print(f"Durasi Komputasi            : {eval_duration:.2f} detik ({num_evaluated_chunks / eval_duration:.1f} chunks/detik)")
    print("================================================================================")

    # 8. Simpan Laporan Evaluasi Lengkap
    if args.output_file is None:
        run_parent = os.path.dirname(os.path.abspath(args.model_dir))
        output_json_path = os.path.join(run_parent, "final_test_evaluation.json")
        output_csv_path = os.path.join(run_parent, "final_test_evaluation.csv")
    else:
        output_json_path = args.output_file
        output_csv_path = os.path.splitext(output_json_path)[0] + ".csv"

    report = {
        "evaluation_name": "final_test_evaluation",
        "timestamp_utc": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "model_metadata": {
            "model_dir": args.model_dir,
            "checkpoint_status": getattr(model, "checkpoint_status", "unknown"),
            "model_pt_sha256": model_pt_sha256,
            "config_json_sha256": config_json_sha256,
            "vocab_canonical_sha256": canonical_vocab_hash,
            "model_config": model.config.to_dict(),
        },
        "data_metadata": {
            "data_dir": args.data_dir,
            "test_file": args.test_file,
            "test_file_sha256": test_file_sha256,
            "total_raw_chunks": total_raw_chunks,
            "evaluated_chunks": num_evaluated_chunks,
            "excluded_chunks_count": num_excluded_chunks,
            "excluded_chunks": dataset.excluded_chunks,
        },
        "evaluation_parameters": {
            "device": str(device),
            "batch_size": args.batch_size,
            "eval_seed": args.eval_seed,
            "mlm_probability": 0.15,
            "masking_rule": "80_10_10_deterministic",
        },
        "metrics": {
            "masked_loss": metrics["loss"],
            "exp_masked_loss": metrics["exp_masked_loss"],
            "top1_accuracy": metrics["top1_acc"],
            "top5_accuracy": metrics["top5_acc"],
            "top1_correct": metrics["total_top1_correct"],
            "top5_correct": metrics["total_top5_correct"],
            "total_targets": metrics["total_targets"],
            "evaluated_chunks": num_evaluated_chunks,
            "evaluation_duration_sec": eval_duration,
        },
    }

    os.makedirs(os.path.dirname(os.path.abspath(output_json_path)), exist_ok=True)
    with open(output_json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"[Laporan Tersimpan] JSON : {output_json_path}")

    # Simpan juga baris ringkas ke CSV
    csv_row = {
        "timestamp_utc": report["timestamp_utc"],
        "model_dir": args.model_dir,
        "test_file": args.test_file,
        "device": str(device),
        "total_targets": metrics["total_targets"],
        "masked_loss": metrics["loss"],
        "exp_masked_loss": metrics["exp_masked_loss"],
        "top1_acc_pct": metrics["top1_acc"] * 100,
        "top5_acc_pct": metrics["top5_acc"] * 100,
        "duration_sec": eval_duration,
    }
    with open(output_csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(csv_row.keys()))
        writer.writeheader()
        writer.writerow(csv_row)
    print(f"[Laporan Tersimpan] CSV  : {output_csv_path}")
    print("Selesai.")


if __name__ == "__main__":
    main()
