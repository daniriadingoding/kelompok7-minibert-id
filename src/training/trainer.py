"""
Modul Trainer untuk Mini-BERT Bahasa Indonesia.

Mengatur:
1. Pipeline pelatihan lengkap dengan pemisahan seed model, shuffle, dan masking.
2. Pengambilan batch DataLoader yang mengisolasi tensor input dari metadata pelacakan.
3. Evaluasi validasi deterministik per-epoch dengan akumulator metrik berbobot.
4. Manajemen checkpoint resume dan ekspor model inferensi terbaik (murni dari epoch terbaik).
5. Pencatatan riwayat metrik (training history) per epoch secara atomik ke JSON dan CSV.
6. Penjaminan penuh bahwa split Test tidak pernah diakses oleh siklus training/tuning.
7. Dukungan pembatasan sampel subset deterministik untuk smoke run.
"""

import csv
import json
import os
import time
from typing import Any, Dict, List, Optional, Tuple

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Subset

from src.data.dataset import PrechunkedMLMDataset, MLMDataCollator
from src.data.tokenizer import WordLevelTokenizer
from src.models.bert import MiniBertForMaskedLM
from src.training.checkpoint import CheckpointManager
from src.training.config import TrainingConfig
from src.training.metrics import MLMMetricAccumulator
from src.training.optimizer import create_optimizer, perform_optimizer_step
from src.training.scheduler import get_linear_schedule_with_warmup


class Trainer:
    """
    Engine utama pelatihan Mini-BERT Masked Language Model.
    """

    def __init__(
        self,
        config: TrainingConfig,
        model: Optional[MiniBertForMaskedLM] = None,
        train_dataset: Optional[Any] = None,
        val_dataset: Optional[Any] = None,
        is_resume: bool = False,
    ):
        self.config = config
        self.is_resume = is_resume

        # 1. Tentukan device eksekusi secara eksplisit
        if config.device == "auto":
            self.device = torch.device("cuda" if torch.cuda.is_available() else "cpu")
        else:
            self.device = torch.device(config.device)

        # 2. Inisialisasi seed model dasar
        torch.manual_seed(config.model_seed)
        if torch.cuda.is_available():
            torch.cuda.manual_seed_all(config.model_seed)

        # 3. Inisialisasi Model
        if model is not None:
            self.model = model.to(self.device)
        else:
            model_cfg = config.get_model_config()
            self.model = MiniBertForMaskedLM(model_cfg).to(self.device)

        # 4. Inisialisasi Generator DataLoader (terpisah untuk kontrol shuffle)
        self.dataloader_generator = torch.Generator(device="cpu").manual_seed(config.shuffle_seed)

        # 5. Inisialisasi Collator Masking
        self.train_collator = MLMDataCollator(
            vocab_size=config.vocab_size,
            mode="train",
            train_seed=config.masking_seed,
        )
        self.val_collator = MLMDataCollator(
            vocab_size=config.vocab_size,
            mode="eval",
            eval_seed=config.eval_seed,
        )

        # 6. Inisialisasi Dataset Siap MLM (Hanya Train dan Val, Test diisolasi)
        train_path = os.path.join(config.data_dir, config.train_file)
        val_path = os.path.join(config.data_dir, config.val_file)

        raw_train_ds = train_dataset or PrechunkedMLMDataset(
            jsonl_path=train_path,
            vocab_size=config.vocab_size,
            max_length=config.max_position_embeddings,
            filter_zero_candidates=True,
        )
        raw_val_ds = val_dataset or PrechunkedMLMDataset(
            jsonl_path=val_path,
            vocab_size=config.vocab_size,
            max_length=config.max_position_embeddings,
            filter_zero_candidates=True,
        )

        # Terapkan pembatasan subset jika diatur dalam config (misal untuk smoke run)
        if config.max_train_samples is not None and train_dataset is None:
            train_limit = min(config.max_train_samples, len(raw_train_ds))
            self.train_dataset = Subset(raw_train_ds, list(range(train_limit)))
        else:
            self.train_dataset = raw_train_ds

        if config.max_val_samples is not None and val_dataset is None:
            val_limit = min(config.max_val_samples, len(raw_val_ds))
            self.val_dataset = Subset(raw_val_ds, list(range(val_limit)))
        else:
            self.val_dataset = raw_val_ds

        # 7. Inisialisasi DataLoader
        self.train_loader = DataLoader(
            self.train_dataset,
            batch_size=config.batch_size,
            shuffle=True,
            generator=self.dataloader_generator,
            collate_fn=self.train_collator,
            num_workers=config.num_workers,
            pin_memory=False,
        )
        self.val_loader = DataLoader(
            self.val_dataset,
            batch_size=config.batch_size,
            shuffle=False,
            collate_fn=self.val_collator,
            num_workers=config.num_workers,
            pin_memory=False,
        )

        # 8. Inisialisasi Optimizer AdamW
        self.optimizer, self.optimizer_summary = create_optimizer(
            model=self.model,
            learning_rate=config.learning_rate,
            weight_decay=config.weight_decay,
        )

        # 9. Inisialisasi Scheduler
        steps_per_epoch = len(self.train_loader)
        total_training_steps = max(1, steps_per_epoch * config.epochs)
        warmup_steps = int(total_training_steps * config.warmup_ratio)

        self.scheduler = get_linear_schedule_with_warmup(
            optimizer=self.optimizer,
            num_warmup_steps=warmup_steps,
            num_training_steps=total_training_steps,
            min_lr_ratio=config.min_learning_rate,
        )

        # 10. Pengelola Checkpoint dan Direktori Output
        # Pembedaan eksplisit: mode run baru vs resume vs overwrite
        output_exists = os.path.exists(config.output_dir) and bool(os.listdir(config.output_dir))
        if output_exists and not config.overwrite_output_dir and not self.is_resume:
            raise FileExistsError(
                f"Direktori output '{config.output_dir}' sudah ada dan tidak kosong. "
                f"Gunakan direktori baru atau aktifkan overwrite_output_dir=True untuk run baru, "
                f"atau tentukan checkpoint resume untuk melanjutkan run yang ada."
            )

        os.makedirs(config.output_dir, exist_ok=True)
        self.checkpoint_manager = CheckpointManager(
            output_dir=config.output_dir,
            overwrite=config.overwrite_output_dir,
        )

        # Pelacak Status Pelatihan
        self.start_epoch = 1
        self.global_step = 0
        self.best_val_loss = float("inf")
        self.best_epoch: Optional[int] = None
        self.best_global_step: Optional[int] = None
        self.best_model_state_dict: Optional[Dict[str, torch.Tensor]] = None
        self.history: List[Dict[str, Any]] = []

    def resume_from_checkpoint(self, checkpoint_path: str) -> None:
        """
        Melanjutkan status pelatihan dari berkas checkpoint batas epoch dengan validasi integritas riwayat.
        """
        # Periksa apakah direktori output memuat training_history.json yang berkonflik
        json_path = os.path.join(self.config.output_dir, "training_history.json")
        if os.path.exists(json_path):
            with open(json_path, "r", encoding="utf-8") as f:
                disk_data = json.load(f)
            disk_hist = disk_data.get("history", [])
            max_disk_epoch = max([item["epoch"] for item in disk_hist], default=0)

            # Muat header checkpoint sementara untuk memeriksa epoch yang akan di-resume
            temp_ckpt = torch.load(checkpoint_path, map_location="cpu", weights_only=True)
            ckpt_epoch = temp_ckpt.get("epoch_completed", 0)

            if max_disk_epoch > ckpt_epoch:
                raise ValueError(
                    f"Konflik riwayat resume: Direktori '{self.config.output_dir}' memuat riwayat hingga Epoch {max_disk_epoch}, "
                    f"sedangkan checkpoint yang di-resume adalah Epoch {ckpt_epoch}. "
                    f"Untuk menghindari pencampuran cabang riwayat lama, tentukan direktori run baru."
                )

        resume_info = self.checkpoint_manager.load_training_checkpoint(
            checkpoint_path=checkpoint_path,
            current_config=self.config,
            model=self.model,
            optimizer=self.optimizer,
            scheduler=self.scheduler,
            dataloader_generator=self.dataloader_generator,
            device=str(self.device),
        )

        self.start_epoch = resume_info["next_epoch"]
        self.global_step = resume_info["global_step"]
        self.best_val_loss = resume_info["best_val_loss"]
        self.best_epoch = resume_info.get("best_epoch")
        self.best_global_step = resume_info.get("best_global_step")
        self.history = list(resume_info.get("history", []))

        # Pulihkan bobot model terbaik yang tercatat
        if resume_info.get("best_model_state_dict") is not None:
            self.best_model_state_dict = resume_info["best_model_state_dict"]
        elif self.best_epoch is not None and self.best_epoch <= resume_info["epoch_completed"]:
            # Jika best_model_state_dict tidak ada tapi best_checkpoint.pt ada di folder
            best_ckpt_path = os.path.join(self.checkpoint_manager.checkpoints_dir, "best_checkpoint.pt")
            if os.path.exists(best_ckpt_path):
                b_ckpt = torch.load(best_ckpt_path, map_location="cpu", weights_only=True)
                self.best_model_state_dict = b_ckpt.get("model_state_dict")

        # Simpan kembali history yang telah dipangkas sesuai epoch resume secara atomik
        self._save_history()

        print(
            f"[Resume] Melanjutkan pelatihan dari Epoch {self.start_epoch} (Global Step {self.global_step}) | "
            f"Best Val Loss Sebelumnya: {self.best_val_loss:.4f} (Epoch {self.best_epoch})"
        )

    def train_one_epoch(self, epoch: int) -> Dict[str, Any]:
        """
        Mengeksekusi satu epoch pelatihan penuh pada split Train.
        """
        self.model.train()
        # Perbarui seed masking collator untuk variasi dinamis antarepoch yang terulang
        self.train_collator.set_train_seed(self.config.masking_seed + epoch)

        accumulator = MLMMetricAccumulator(vocab_size=self.config.vocab_size)
        loss_fn = nn.CrossEntropyLoss(ignore_index=-100)

        epoch_start_time = time.time()

        for batch_idx, batch in enumerate(self.train_loader):
            # PERHATIAN KONTRAK: Hanya kirimkan input_ids dan attention_mask ke model
            input_ids = batch["input_ids"].to(self.device)
            attention_mask = batch["attention_mask"].to(self.device)
            labels = batch["labels"].to(self.device)

            # zero_grad(set_to_none=True) untuk performa memori optimal
            self.optimizer.zero_grad(set_to_none=True)

            logits = self.model(input_ids=input_ids, attention_mask=attention_mask)
            loss = loss_fn(logits.view(-1, self.config.vocab_size), labels.view(-1))

            # Eksekusi backward, validasi gradien, clipping, dan optimizer step
            grad_norm = perform_optimizer_step(
                model=self.model,
                optimizer=self.optimizer,
                loss=loss,
                max_grad_norm=self.config.max_grad_norm,
            )

            # Scheduler melangkah hanya setelah optimizer step berhasil
            self.scheduler.step()
            self.global_step += 1

            # Akumulasi metrik
            with torch.no_grad():
                accumulator.update(logits, labels)

            # Logging berkala
            if (batch_idx + 1) % self.config.log_every_n_steps == 0 or (batch_idx + 1) == len(self.train_loader):
                current_lr = self.optimizer.param_groups[0]["lr"]
                batch_loss = loss.item()
                if batch_idx < 10 or (batch_idx + 1) % (self.config.log_every_n_steps * 5) == 0:
                    print(
                        f"Epoch {epoch:02d} | Batch {batch_idx + 1:04d}/{len(self.train_loader):04d} | "
                        f"Loss: {batch_loss:.4f} | GradNorm: {grad_norm:.2f} | LR: {current_lr:.6e}"
                    )

        epoch_duration = time.time() - epoch_start_time
        metrics = accumulator.compute()
        metrics["epoch_duration_sec"] = epoch_duration
        metrics["learning_rate"] = self.optimizer.param_groups[0]["lr"]
        return metrics

    def evaluate(self) -> Dict[str, Any]:
        """
        Mengeksekusi evaluasi validasi penuh pada split Val secara deterministik.
        """
        self.model.eval()
        accumulator = MLMMetricAccumulator(vocab_size=self.config.vocab_size)

        eval_start_time = time.time()

        with torch.inference_mode():
            for batch in self.val_loader:
                input_ids = batch["input_ids"].to(self.device)
                attention_mask = batch["attention_mask"].to(self.device)
                labels = batch["labels"].to(self.device)

                logits = self.model(input_ids=input_ids, attention_mask=attention_mask)
                accumulator.update(logits, labels)

        eval_duration = time.time() - eval_start_time
        metrics = accumulator.compute()
        metrics["eval_duration_sec"] = eval_duration
        return metrics

    def train(self) -> List[Dict[str, Any]]:
        """
        Menjalankan loop pelatihan lengkap melintasi seluruh epoch yang dikonfigurasi.
        """
        print(f"=== Memulai Pelatihan Mini-BERT ({self.config.experiment_name}) ===")
        print(f"Device: {self.device} | Total Epochs: {self.config.epochs} | Batch Size: {self.config.batch_size}")
        print(f"Train Chunks: {len(self.train_dataset):,} | Val Chunks: {len(self.val_dataset):,}")
        print(f"Optimizer: AdamW (LR: {self.config.learning_rate}, Weight Decay: {self.config.weight_decay})")

        total_start_time = time.time()

        for epoch in range(self.start_epoch, self.config.epochs + 1):
            print(f"\n--- Epoch {epoch}/{self.config.epochs} ---")

            # 1. Pelatihan 1 Epoch
            train_metrics = self.train_one_epoch(epoch)

            # 2. Evaluasi Validasi
            val_metrics = self.evaluate()

            is_best = val_metrics["loss"] < self.best_val_loss
            if is_best:
                self.best_val_loss = val_metrics["loss"]
                self.best_epoch = epoch
                self.best_global_step = self.global_step
                # Simpan salinan bobot model terbaik secara aman (klon ke CPU tanpa mengubah model aktif)
                self.best_model_state_dict = {k: v.cpu().clone() for k, v in self.model.state_dict().items()}

            epoch_record = {
                "epoch": epoch,
                "global_step": self.global_step,
                "learning_rate": train_metrics["learning_rate"],
                "train_loss": train_metrics["loss"],
                "train_top1_acc": train_metrics["top1_acc"],
                "train_top5_acc": train_metrics["top5_acc"],
                "train_exp_masked_loss": train_metrics["exp_masked_loss"],
                "train_targets": train_metrics["total_targets"],
                "train_duration_sec": train_metrics["epoch_duration_sec"],
                "val_loss": val_metrics["loss"],
                "val_top1_acc": val_metrics["top1_acc"],
                "val_top5_acc": val_metrics["top5_acc"],
                "val_exp_masked_loss": val_metrics["exp_masked_loss"],
                "val_targets": val_metrics["total_targets"],
                "val_duration_sec": val_metrics["eval_duration_sec"],
                "is_best": is_best,
            }
            self.history.append(epoch_record)

            print(
                f"[Epoch {epoch:02d} Selesai] "
                f"Train Loss: {train_metrics['loss']:.4f} (Top-1: {train_metrics['top1_acc']*100:.2f}%) | "
                f"Val Loss: {val_metrics['loss']:.4f} (Top-1: {val_metrics['top1_acc']*100:.2f}%) | "
                f"Best Val Loss: {self.best_val_loss:.4f} (Epoch {self.best_epoch}) {'*' if is_best else ''}"
            )

            # 3. Simpan Riwayat Metrik (JSON dan CSV) SETELAH SETIAP EPOCH secara atomik
            self._save_history()

            # 4. Simpan Checkpoint Pelatihan pada batas epoch
            if epoch % self.config.checkpoint_interval_epochs == 0 or is_best or epoch == self.config.epochs:
                self.checkpoint_manager.save_training_checkpoint(
                    model=self.model,
                    optimizer=self.optimizer,
                    scheduler=self.scheduler,
                    epoch_completed=epoch,
                    global_step=self.global_step,
                    best_val_loss=self.best_val_loss,
                    best_epoch=self.best_epoch,
                    best_global_step=self.best_global_step,
                    train_config=self.config,
                    history=self.history,
                    best_model_state_dict=self.best_model_state_dict,
                    dataloader_generator=self.dataloader_generator,
                    is_best=is_best,
                )

        total_duration = time.time() - total_start_time
        print(f"\n[Selesai] Pelatihan tuntas dalam {total_duration:.2f} detik.")

        # 5. Ekspor Model Inferensi Terbaik (MURNI dari bobot epoch terbaik)
        if self.config.save_best_model and self.best_model_state_dict is not None and self.global_step > 0:
            temp_model = MiniBertForMaskedLM(self.model.config)
            temp_model.load_state_dict(self.best_model_state_dict, strict=True)
            temp_model.tie_weights()

            export_path = self.checkpoint_manager.export_inference_model(
                model=temp_model,
                export_subdir="best_model",
                global_step=self.best_global_step or self.global_step,
            )
            print(
                f"[Ekspor] Model inferensi terbaik (Epoch {self.best_epoch}, "
                f"Val Loss: {self.best_val_loss:.4f}) berhasil diekspor ke: {export_path}"
            )

        return self.history

    def _save_history(self) -> None:
        """Menyimpan riwayat metrik pelatihan ke format JSON dan CSV secara atomik."""
        # 1. Simpan JSON secara atomik
        json_path = os.path.join(self.config.output_dir, "training_history.json")
        json_tmp = json_path + ".tmp"

        payload = {
            "config": self.config.to_dict(),
            "total_epochs": len(self.history),
            "best_val_loss": self.best_val_loss,
            "best_epoch": self.best_epoch,
            "best_global_step": self.best_global_step,
            "history": self.history,
        }
        with open(json_tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        os.replace(json_tmp, json_path)

        # 2. Simpan CSV secara atomik
        csv_path = os.path.join(self.config.output_dir, "training_history.csv")
        csv_tmp = csv_path + ".tmp"
        if self.history:
            fieldnames = list(self.history[0].keys())
            with open(csv_tmp, "w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=fieldnames)
                writer.writeheader()
                writer.writerows(self.history)
            os.replace(csv_tmp, csv_path)
