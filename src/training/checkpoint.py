"""
Modul manajemen checkpoint dan ekspor model Mini-BERT Bahasa Indonesia.

Menyediakan:
1. Penyimpanan atomic (atomic save) melalui berkas sementara (.tmp) lalu os.replace.
2. Format checkpoint training komprehensif untuk resume batas epoch (model, optimizer, scheduler, RNG, generator, history).
3. Pemulihan RNG states dengan penanganan device yang tepat.
4. Validasi metadata ketat sebelum proses resume dimulai:
   - Validasi keberadaan metadata wajib
   - Validasi hash data (train/val file hash dan parameter subset) serta hash vocabulary
   - Validasi seluruh hyperparameter model_config
   - Validasi hyperparameter kritis training_config (batch size, epochs, lr, decay, warmup, seed, precision)
   - Logging peringatan pada perbedaan device (portabilitas) tanpa menjanjikan identik bit-per-bit
5. Menggunakan weights_only=True secara aman untuk mencegah deserialisasi kode arbitrer.
6. Ekspor terpisah model inferensi siap pakai dengan penanda status 'trained'.
"""

import hashlib
import json
import logging
import os
import random
from typing import Any, Dict, List, Optional, Tuple

import torch
import torch.nn as nn
from torch.optim import Optimizer
from torch.optim.lr_scheduler import LambdaLR

from src.models.bert import MiniBertForMaskedLM
from src.models.config import MiniBertConfig
from src.training.config import TrainingConfig

logger = logging.getLogger(__name__)


def compute_file_sha256(file_path: str) -> str:
    """Menghitung SHA-256 dari berkas fisik di disk."""
    if not os.path.exists(file_path):
        return "FILE_NOT_FOUND"
    hasher = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(65536):
            hasher.update(chunk)
    return hasher.hexdigest()


class CheckpointManager:
    """
    Pengelola checkpoint pelatihan dan ekspor model inferensi.
    """

    def __init__(self, output_dir: str, overwrite: bool = False):
        self.output_dir = output_dir
        self.overwrite = overwrite
        self.checkpoints_dir = os.path.join(output_dir, "checkpoints")
        os.makedirs(self.checkpoints_dir, exist_ok=True)

    @staticmethod
    def _atomic_torch_save(obj: Any, target_path: str) -> None:
        """Menyimpan objek torch secara aman via berkas sementara .tmp lalu replace atomik."""
        target_dir = os.path.dirname(os.path.abspath(target_path))
        os.makedirs(target_dir, exist_ok=True)
        tmp_path = target_path + ".tmp"

        torch.save(obj, tmp_path)
        # Flush ke disk dan ganti berkas target secara atomik
        os.replace(tmp_path, target_path)

    def save_training_checkpoint(
        self,
        model: MiniBertForMaskedLM,
        optimizer: Optimizer,
        scheduler: LambdaLR,
        epoch_completed: int,
        global_step: int,
        best_val_loss: float,
        best_epoch: Optional[int] = None,
        best_global_step: Optional[int] = None,
        train_config: Optional[TrainingConfig] = None,
        history: Optional[List[Dict[str, Any]]] = None,
        best_model_state_dict: Optional[Dict[str, torch.Tensor]] = None,
        dataloader_generator: Optional[torch.Generator] = None,
        is_best: bool = False,
        filename: Optional[str] = None,
    ) -> str:
        """
        Menyimpan checkpoint lengkap untuk melanjutkan pelatihan (resume) pada batas epoch.
        """
        if filename is None:
            filename = f"checkpoint_epoch_{epoch_completed:03d}.pt"

        if best_epoch is None and is_best:
            best_epoch = epoch_completed
        if best_global_step is None and is_best:
            best_global_step = global_step
        if history is None:
            history = []
        if best_model_state_dict is None and is_best:
            best_model_state_dict = {k: v.cpu().clone() for k, v in model.state_dict().items()}

        target_path = os.path.join(self.checkpoints_dir, filename)

        # Kumpulkan RNG states
        rng_states: Dict[str, Any] = {
            "python_random": random.getstate(),
            "torch_cpu": torch.get_rng_state().cpu(),
            "torch_cuda": torch.cuda.get_rng_state_all() if torch.cuda.is_available() else None,
        }

        if dataloader_generator is not None:
            rng_states["dataloader_generator"] = dataloader_generator.get_state().cpu()

        # Rekam hash data artefacts dan konfigurasi subset
        train_path = os.path.join(train_config.data_dir, train_config.train_file)
        val_path = os.path.join(train_config.data_dir, train_config.val_file)
        data_hashes = {
            "train_file": compute_file_sha256(train_path),
            "val_file": compute_file_sha256(val_path),
            "vocab_sha256": train_config.expected_vocab_sha256,
            "is_subset": (train_config.max_train_samples is not None or train_config.max_val_samples is not None),
            "max_train_samples": train_config.max_train_samples,
            "max_val_samples": train_config.max_val_samples,
        }

        # Model config aktual dari model yang sedang dilatih
        model_config_dict = model.config.to_dict()

        checkpoint = {
            "epoch_completed": epoch_completed,
            "next_epoch": epoch_completed + 1,
            "global_step": global_step,
            "best_val_loss": best_val_loss,
            "best_epoch": best_epoch,
            "best_global_step": best_global_step,
            "model_state_dict": {k: v.cpu() for k, v in model.state_dict().items()},
            "best_model_state_dict": {k: v.cpu() for k, v in best_model_state_dict.items()} if best_model_state_dict is not None else None,
            "optimizer_state_dict": optimizer.state_dict(),
            "scheduler_state_dict": scheduler.state_dict(),
            "training_config": train_config.to_dict(),
            "model_config": model_config_dict,
            "vocab_sha256": train_config.expected_vocab_sha256,
            "data_hashes": data_hashes,
            "rng_states": rng_states,
            "history": list(history),
        }

        self._atomic_torch_save(checkpoint, target_path)

        # Hormati konfigurasi save_last_checkpoint
        if train_config.save_last_checkpoint:
            last_path = os.path.join(self.checkpoints_dir, "last_checkpoint.pt")
            self._atomic_torch_save(checkpoint, last_path)

        # Hormati konfigurasi save_best_model untuk best_checkpoint.pt
        if train_config.save_best_model and is_best:
            best_path = os.path.join(self.checkpoints_dir, "best_checkpoint.pt")
            self._atomic_torch_save(checkpoint, best_path)

        return target_path

    @staticmethod
    def load_training_checkpoint(
        checkpoint_path: str,
        current_config: TrainingConfig,
        model: MiniBertForMaskedLM,
        optimizer: Optimizer,
        scheduler: LambdaLR,
        dataloader_generator: Optional[torch.Generator] = None,
        device: str = "cpu",
    ) -> Dict[str, Any]:
        """
        Memuat dan memvalidasi checkpoint training secara ketat sebelum mengubah state model/optimizer/RNG.
        Menggunakan weights_only=True untuk keamanan serialisasi PyTorch.
        """
        if not os.path.exists(checkpoint_path):
            raise FileNotFoundError(f"Berkas checkpoint '{checkpoint_path}' tidak ditemukan.")

        # Pemuatan aman menggunakan weights_only=True
        checkpoint = torch.load(checkpoint_path, map_location="cpu", weights_only=True)

        if not isinstance(checkpoint, dict):
            raise ValueError(f"Checkpoint '{checkpoint_path}' tidak valid: format bukan dictionary.")

        # 1. Validasi keberadaan metadata penting
        required_keys = [
            "epoch_completed",
            "next_epoch",
            "global_step",
            "model_state_dict",
            "optimizer_state_dict",
            "scheduler_state_dict",
            "training_config",
            "model_config",
            "vocab_sha256",
            "data_hashes",
            "rng_states",
            "history",
        ]
        missing_keys = [k for k in required_keys if k not in checkpoint]
        if missing_keys:
            raise ValueError(
                f"Checkpoint '{checkpoint_path}' tidak valid: Kunci metadata wajib hilang: {missing_keys}."
            )

        # 2. Validasi kesesuaian hash vocabulary
        saved_vocab_hash = checkpoint["vocab_sha256"]
        if saved_vocab_hash != current_config.expected_vocab_sha256:
            raise ValueError(
                f"Integritas resume ditolak: Hash vocabulary pada checkpoint ({saved_vocab_hash}) "
                f"berbeda dengan konfigurasi saat ini ({current_config.expected_vocab_sha256})."
            )

        # 3. Validasi hash data dan konfigurasi subset
        saved_data_hashes = checkpoint["data_hashes"]
        if not isinstance(saved_data_hashes, dict):
            raise ValueError("Metadata 'data_hashes' pada checkpoint harus berupa dictionary.")

        curr_train_path = os.path.join(current_config.data_dir, current_config.train_file)
        curr_val_path = os.path.join(current_config.data_dir, current_config.val_file)

        curr_train_hash = compute_file_sha256(curr_train_path)
        curr_val_hash = compute_file_sha256(curr_val_path)

        if saved_data_hashes.get("train_file") != curr_train_hash:
            raise ValueError(
                f"Integritas data resume ditolak: Hash berkas train telah berubah "
                f"(Saved: {saved_data_hashes.get('train_file')} vs Current: {curr_train_hash})."
            )

        if saved_data_hashes.get("val_file") != curr_val_hash:
            raise ValueError(
                f"Integritas data resume ditolak: Hash berkas validation telah berubah "
                f"(Saved: {saved_data_hashes.get('val_file')} vs Current: {curr_val_hash})."
            )

        if saved_data_hashes.get("max_train_samples") != current_config.max_train_samples:
            raise ValueError(
                f"Integritas data resume ditolak: Parameter max_train_samples berbeda "
                f"(Saved: {saved_data_hashes.get('max_train_samples')} vs Current: {current_config.max_train_samples})."
            )

        if saved_data_hashes.get("max_val_samples") != current_config.max_val_samples:
            raise ValueError(
                f"Integritas data resume ditolak: Parameter max_val_samples berbeda "
                f"(Saved: {saved_data_hashes.get('max_val_samples')} vs Current: {current_config.max_val_samples})."
            )

        # 4. Validasi seluruh hyperparameter model_config
        saved_model_cfg = checkpoint["model_config"]
        curr_model_cfg = model.config.to_dict()

        for k, v in curr_model_cfg.items():
            if k not in saved_model_cfg:
                raise ValueError(f"Integritas model resume ditolak: Kunci konfigurasi '{k}' hilang dari checkpoint.")
            if saved_model_cfg[k] != v:
                raise ValueError(
                    f"Integritas model resume ditolak: Konfigurasi model '{k}' tidak cocok "
                    f"(Checkpoint: {saved_model_cfg[k]} vs Config: {v})."
                )

        # 5. Validasi konfigurasi training kritis
        saved_train_cfg = checkpoint["training_config"]
        critical_train_fields = [
            "batch_size",
            "epochs",
            "learning_rate",
            "weight_decay",
            "warmup_ratio",
            "min_learning_rate",
            "lr_scheduler_type",
            "precision",
            "model_seed",
            "shuffle_seed",
            "masking_seed",
            "eval_seed",
            "max_train_samples",
            "max_val_samples",
        ]
        curr_train_dict = current_config.to_dict()
        for f in critical_train_fields:
            saved_val = saved_train_cfg.get(f)
            curr_val = curr_train_dict.get(f)
            if saved_val != curr_val:
                raise ValueError(
                    f"Integritas training config kritis ditolak: Parameter '{f}' berbeda "
                    f"(Checkpoint: {saved_val} vs Config Saat Ini: {curr_val}). "
                    f"Perubahan parameter kritis ini merusak kelanjutan scheduler atau data."
                )

        # Periksa perbedaan device (diizinkan untuk portabilitas, dicatat sebagai warning)
        saved_device = saved_train_cfg.get("device")
        curr_device = current_config.device
        if saved_device != curr_device:
            print(
                f"[Peringatan Portabilitas] Perbedaan device terdeteksi saat resume: "
                f"Checkpoint dibuat pada device '{saved_device}', saat ini dijalankan pada device '{curr_device}'. "
                f"Kesetaraan numerik bit-per-bit tidak dijamin lintas backend hardware."
            )

        # 6. SEMUA VALIDASI LULUS: Sekarang pulihkan state
        model.load_state_dict(checkpoint["model_state_dict"], strict=True)
        model.tie_weights()
        model.to(device)

        optimizer.load_state_dict(checkpoint["optimizer_state_dict"])
        scheduler.load_state_dict(checkpoint["scheduler_state_dict"])

        # Pulihkan RNG states
        rng_states = checkpoint["rng_states"]
        if "python_random" in rng_states and rng_states["python_random"] is not None:
            random.setstate(rng_states["python_random"])

        if "torch_cpu" in rng_states and rng_states["torch_cpu"] is not None:
            cpu_state = rng_states["torch_cpu"]
            if isinstance(cpu_state, torch.Tensor):
                cpu_state = cpu_state.cpu()
            torch.set_rng_state(cpu_state)

        if torch.cuda.is_available() and "torch_cuda" in rng_states and rng_states["torch_cuda"] is not None:
            torch.cuda.set_rng_state_all(rng_states["torch_cuda"])

        if dataloader_generator is not None and "dataloader_generator" in rng_states and rng_states["dataloader_generator"] is not None:
            gen_state = rng_states["dataloader_generator"]
            if isinstance(gen_state, torch.Tensor):
                gen_state = gen_state.cpu()
            dataloader_generator.set_state(gen_state)

        return {
            "epoch_completed": checkpoint["epoch_completed"],
            "next_epoch": checkpoint["next_epoch"],
            "global_step": checkpoint["global_step"],
            "best_val_loss": checkpoint.get("best_val_loss", float("inf")),
            "best_epoch": checkpoint.get("best_epoch"),
            "best_global_step": checkpoint.get("best_global_step"),
            "history": list(checkpoint.get("history", [])),
            "best_model_state_dict": checkpoint.get("best_model_state_dict"),
        }

    def export_inference_model(
        self,
        model: MiniBertForMaskedLM,
        export_subdir: str = "best_model",
        global_step: int = 1,
    ) -> str:
        """
        Mengekspor model untuk inferensi mandiri (kompatibel dengan MiniBertForMaskedLM.from_pretrained).
        Status 'trained' HANYA diberikan jika model benar-benar telah menerima pembaruan training (global_step > 0).
        """
        export_dir = os.path.join(self.output_dir, export_subdir)
        os.makedirs(export_dir, exist_ok=True)

        status = "trained" if global_step > 0 else "random_init"

        model.save_pretrained(
            save_directory=export_dir,
            filename="model.pt",
            checkpoint_status=status,
        )

        return export_dir
