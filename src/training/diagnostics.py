"""
Modul Diagnostik CPU Mini-BERT Bahasa Indonesia (Tahap 3):

1. run_overfit_check:
   - Mengambil 1 batch kecil (B=4) dari split Train.
   - Membekukan masking dan target tensor (tidak diacak ulang).
   - Mematikan dropout (dropout=0.0) pada model diagnostik.
   - Menjalankan maksimal 100 optimizer steps dengan learning rate diagnostik.
   - Memverifikasi apakah loss menurun drastis dan akurasi meningkat.
   - Hasil dicatat secara transparan sebagai artefak diagnostik, dan bobot TIDAK digunakan untuk baseline.

2. run_smoke_run:
   - Menggunakan subset tetap kecil: 32 chunk train dan 16 chunk validation.
   - Split Test sama sekali tidak dibuka atau disentuh.
   - Menjalankan 2 epoch singkat untuk memeriksa logging, history, best/last checkpoint, dan resume.
   - Menyimpan hasil sebagai diagnostic/smoke di runs/cpu_smoke_run/.
"""

import json
import os
import sys
import time
from typing import Any, Dict

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Subset

from src.data.dataset import PrechunkedMLMDataset, MLMDataCollator
from src.models.bert import MiniBertForMaskedLM
from src.training.config import TrainingConfig
from src.training.metrics import compute_batch_mlm_metrics
from src.training.optimizer import create_optimizer, perform_optimizer_step
from src.training.trainer import Trainer


def run_overfit_check(
    config_path: str = "configs/cpu_overfit_diagnostic.json",
    max_steps: int = 100,
    target_loss_threshold: float = 0.5,
) -> Dict[str, Any]:
    """
    Diagnostik A: Overfit check pada satu batch kecil dengan masking tetap dan dropout dinonaktifkan.
    """
    print("\n" + "=" * 70)
    print("=== TAHAP 3A: DIAGNOSTIK OVERFIT CHECK (1 BATCH CPU) ===")
    print("=" * 70)

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Berkas konfigurasi '{config_path}' tidak ditemukan.")

    config = TrainingConfig.from_json_file(config_path)
    os.makedirs(config.output_dir, exist_ok=True)

    # 1. Pastikan dropout dan attention_dropout = 0.0
    config.dropout = 0.0
    config.attention_dropout = 0.0
    config.device = "cpu"

    device = torch.device("cpu")
    torch.manual_seed(config.model_seed)

    # 2. Inisialisasi Model Diagnostik
    model_cfg = config.get_model_config()
    model = MiniBertForMaskedLM(model_cfg).to(device)
    model.train()

    # 3. Ambil tepat 1 batch dari split Train
    train_path = os.path.join(config.data_dir, config.train_file)
    train_ds = PrechunkedMLMDataset(train_path, vocab_size=config.vocab_size, filter_zero_candidates=True)
    collator = MLMDataCollator(vocab_size=config.vocab_size, mode="train", train_seed=config.masking_seed)

    loader = DataLoader(train_ds, batch_size=config.batch_size, shuffle=False, collate_fn=collator)
    batch = next(iter(loader))

    # 4. Bekukan hasil masking batch ini
    frozen_input_ids = batch["input_ids"].to(device).clone()
    frozen_attention_mask = batch["attention_mask"].to(device).clone()
    frozen_labels = batch["labels"].to(device).clone()

    num_targets = (frozen_labels != -100).sum().item()
    print(f"Batch Diagnostik: Batch Size = {config.batch_size}, Total Token Target Masked = {num_targets}")

    # 5. Inisialisasi Optimizer AdamW (tanpa weight decay untuk mempermudah memorization)
    optimizer, _ = create_optimizer(model, learning_rate=config.learning_rate, weight_decay=0.0)
    loss_fn = nn.CrossEntropyLoss(ignore_index=-100)

    # 6. Catat kondisi awal (Step 0)
    with torch.no_grad():
        initial_logits = model(frozen_input_ids, frozen_attention_mask)
        initial_metrics = compute_batch_mlm_metrics(initial_logits, frozen_labels, vocab_size=config.vocab_size)

    initial_loss = initial_metrics["loss"]
    initial_top1 = initial_metrics["top1_acc"]
    initial_top5 = initial_metrics["top5_acc"]

    print(f"Step 000 (Awal)  | Loss: {initial_loss:.4f} | Top-1: {initial_top1*100:.2f}% | Top-5: {initial_top5*100:.2f}%")

    start_time = time.time()
    steps_history = []
    current_loss = initial_loss
    current_top1 = initial_top1
    current_top5 = initial_top5

    # 7. Loop Optimasi hingga max_steps
    for step in range(1, max_steps + 1):
        optimizer.zero_grad(set_to_none=True)

        logits = model(frozen_input_ids, frozen_attention_mask)
        loss = loss_fn(logits.view(-1, config.vocab_size), frozen_labels.view(-1))

        perform_optimizer_step(model, optimizer, loss, max_grad_norm=config.max_grad_norm)

        with torch.no_grad():
            m = compute_batch_mlm_metrics(logits, frozen_labels, vocab_size=config.vocab_size)
            current_loss = m["loss"]
            current_top1 = m["top1_acc"]
            current_top5 = m["top5_acc"]

        record = {
            "step": step,
            "loss": current_loss,
            "top1_acc": current_top1,
            "top5_acc": current_top5,
        }
        steps_history.append(record)

        if step % 10 == 0 or step == max_steps or current_loss <= target_loss_threshold:
            print(
                f"Step {step:03d}/{max_steps:03d} | Loss: {current_loss:.4f} | "
                f"Top-1: {current_top1*100:.2f}% | Top-5: {current_top5*100:.2f}%"
            )

        if current_loss <= target_loss_threshold:
            print(f"[Konvergensi Tercapai] Loss berhasil turun di bawah threshold {target_loss_threshold} pada step {step}!")
            break

    duration = time.time() - start_time
    loss_decreased = current_loss < initial_loss
    relative_reduction = (initial_loss - current_loss) / initial_loss if initial_loss > 0 else 0.0

    report = {
        "status": "COMPLETED",
        "diagnostic_type": "single_batch_overfit_check",
        "config_used": config_path,
        "device": "cpu",
        "batch_size": config.batch_size,
        "num_targets_in_batch": num_targets,
        "total_steps_executed": len(steps_history),
        "duration_sec": duration,
        "initial_loss": initial_loss,
        "final_loss": current_loss,
        "initial_top1_acc": initial_top1,
        "final_top1_acc": current_top1,
        "final_top5_acc": current_top5,
        "loss_decreased": loss_decreased,
        "relative_loss_reduction_pct": relative_reduction * 100.0,
        "converged_under_threshold": current_loss <= target_loss_threshold,
        "history_every_10_steps": [r for r in steps_history if r["step"] % 10 == 0 or r["step"] == len(steps_history)],
        "note": (
            "Bobot model hasil overfit check ini adalah artefak diagnostik dan TIDAK digunakan "
            "untuk memulai eksperimen baseline utama."
        ),
    }

    report_path = os.path.join(config.output_dir, "overfit_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n[Ringkasan Overfit Check]")
    print(f"- Loss Awal : {initial_loss:.4f} -> Loss Akhir : {current_loss:.4f} (Turun {relative_reduction*100:.2f}%)")
    print(f"- Top-1 Acc : {initial_top1*100:.2f}% -> Top-1 Akhir : {current_top1*100:.2f}%")
    print(f"- Top-5 Acc : {initial_top5*100:.2f}% -> Top-5 Akhir : {current_top5*100:.2f}%")
    print(f"- Durasi    : {duration:.2f} detik")
    print(f"- Laporan tersimpan di: {report_path}")

    return report


def run_smoke_run(
    config_path: str = "configs/cpu_smoke.json",
    train_subset_size: int = 32,
    val_subset_size: int = 16,
) -> Dict[str, Any]:
    """
    Diagnostik B: Smoke run 2 epoch pada subset kecil (32 train, 16 val) tanpa menyentuh split Test.
    """
    print("\n" + "=" * 70)
    print("=== TAHAP 3B: DIAGNOSTIK SMOKE RUN (SUBSET KECIL CPU) ===")
    print("=" * 70)

    if not os.path.exists(config_path):
        raise FileNotFoundError(f"Berkas konfigurasi '{config_path}' tidak ditemukan.")

    config = TrainingConfig.from_json_file(config_path)
    config.device = "cpu"
    config.overwrite_output_dir = True

    # 1. Siapkan subset data riil tanpa menyentuh split Test
    train_full = PrechunkedMLMDataset(
        jsonl_path=os.path.join(config.data_dir, config.train_file),
        vocab_size=config.vocab_size,
        filter_zero_candidates=True,
    )
    val_full = PrechunkedMLMDataset(
        jsonl_path=os.path.join(config.data_dir, config.val_file),
        vocab_size=config.vocab_size,
        filter_zero_candidates=True,
    )

    # Ambil indeks subset tetap deterministik
    train_subset = Subset(train_full, list(range(min(train_subset_size, len(train_full)))))
    val_subset = Subset(val_full, list(range(min(val_subset_size, len(val_full)))))

    # Pastikan split test sama sekali tidak dimuat
    assert "test" not in config.train_file and "test" not in config.val_file

    print(f"Subset Smoke Run: {len(train_subset)} Train chunks, {len(val_subset)} Val chunks")
    print(f"Total Epoch: {config.epochs} | Batch Size: {config.batch_size}")

    start_time = time.time()

    # 2. Jalankan pelatihan 2 epoch
    trainer = Trainer(
        config=config,
        train_dataset=train_subset,
        val_dataset=val_subset,
    )
    history = trainer.train()

    duration = time.time() - start_time

    # 3. Verifikasi berkas keluaran
    checkpoints_dir = os.path.join(config.output_dir, "checkpoints")
    ckpt_e1 = os.path.join(checkpoints_dir, "checkpoint_epoch_001.pt")
    ckpt_e2 = os.path.join(checkpoints_dir, "checkpoint_epoch_002.pt")
    best_ckpt = os.path.join(checkpoints_dir, "best_checkpoint.pt")
    last_ckpt = os.path.join(checkpoints_dir, "last_checkpoint.pt")
    best_model_dir = os.path.join(config.output_dir, "best_model")
    history_json = os.path.join(config.output_dir, "training_history.json")
    history_csv = os.path.join(config.output_dir, "training_history.csv")

    files_exist = {
        "checkpoint_epoch_001": os.path.exists(ckpt_e1),
        "checkpoint_epoch_002": os.path.exists(ckpt_e2),
        "best_checkpoint": os.path.exists(best_ckpt),
        "last_checkpoint": os.path.exists(last_ckpt),
        "best_model_dir": os.path.exists(best_model_dir) and os.path.exists(os.path.join(best_model_dir, "model.pt")),
        "training_history_json": os.path.exists(history_json),
        "training_history_csv": os.path.exists(history_csv),
    }

    # 4. Verifikasi resume dari checkpoint_epoch_001
    print("\n[Verifikasi Resume Checkpoint]")
    resume_config = TrainingConfig.from_json_file(config_path)
    resume_config.output_dir = os.path.join(config.output_dir, "resume_verification")
    resume_config.overwrite_output_dir = True
    resume_config.epochs = 2

    resume_trainer = Trainer(
        config=resume_config,
        train_dataset=train_subset,
        val_dataset=val_subset,
    )
    resume_trainer.resume_from_checkpoint(ckpt_e1)
    resume_history = resume_trainer.train()

    resume_verified = (
        len(resume_history) == 1 and
        resume_history[0]["epoch"] == 2
    )

    report = {
        "status": "COMPLETED",
        "diagnostic_type": "cpu_smoke_run",
        "config_used": config_path,
        "device": "cpu",
        "train_samples": len(train_subset),
        "val_samples": len(val_subset),
        "epochs": config.epochs,
        "total_duration_sec": duration,
        "history": history,
        "artifacts_verified": files_exist,
        "all_artifacts_present": all(files_exist.values()),
        "resume_verification": {
            "checkpoint_loaded": ckpt_e1,
            "resumed_epochs_run": len(resume_history),
            "resumed_epoch_number": resume_history[0]["epoch"] if resume_history else None,
            "resume_verified": resume_verified,
        },
        "note": (
            "Hasil ini merupakan run diagnostik/smoke pada subset mikro CPU untuk memvalidasi saluran pipeline, "
            "bukan hasil eksperimen utama pada dataset penuh."
        ),
    }

    smoke_report_path = os.path.join(config.output_dir, "smoke_report.json")
    with open(smoke_report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    print(f"\n[Ringkasan Smoke Run]")
    print(f"- Total Durasi      : {duration:.2f} detik")
    print(f"- Seluruh Artefak Ada: {all(files_exist.values())}")
    print(f"- Resume Terverifikasi: {resume_verified}")
    print(f"- Laporan tersimpan di: {smoke_report_path}")

    return report


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"
    if mode in {"overfit", "all"}:
        run_overfit_check()
    if mode in {"smoke", "all"}:
        run_smoke_run()
