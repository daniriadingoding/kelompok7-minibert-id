"""
Modul konfigurasi eksperimen pelatihan Mini-BERT Bahasa Indonesia.
Menyimpan seluruh parameter pelatihan, optimasi, scheduler, seed, dan jalur berkas
secara terpusat dengan validasi tipe data dan rentang nilai yang ketat.
"""

import json
import math
import os
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, Optional

from src.models.config import MiniBertConfig

EXPECTED_VOCAB_SHA256 = "d2be29d07e76fe0cd15c3fe1b765325a5397a5e5fe30b2c6a5a019c976c552f2"


@dataclass
class TrainingConfig:
    """
    Konfigurasi lengkap untuk eksperimen pelatihan Mini-BERT Bahasa Indonesia.
    """

    # Jalur data dan artefak
    data_dir: str = "data/processed/pilot"
    train_file: str = "train_chunks.jsonl"
    val_file: str = "val_chunks.jsonl"
    vocab_file: str = "vocab.json"
    expected_vocab_sha256: str = EXPECTED_VOCAB_SHA256
    max_train_samples: Optional[int] = None
    max_val_samples: Optional[int] = None

    # Arsitektur model Mini-BERT (harus selaras dengan MiniBertConfig)
    vocab_size: int = 8000
    pad_token_id: int = 0
    d_model: int = 128
    num_layers: int = 2
    num_heads: int = 4
    d_ff: int = 512
    max_position_embeddings: int = 64
    dropout: float = 0.1
    attention_dropout: float = 0.1
    layer_norm_eps: float = 1e-12
    initializer_range: float = 0.02

    # Hyperparameter Pelatihan
    batch_size: int = 32
    epochs: int = 5
    learning_rate: float = 3e-4
    weight_decay: float = 0.01
    warmup_ratio: float = 0.1
    min_learning_rate: float = 0.0
    lr_scheduler_type: str = "linear"
    max_grad_norm: float = 1.0
    device: str = "auto"
    precision: str = "float32"
    num_workers: int = 0

    # Reproduksibilitas dan Pemisahan Seed
    model_seed: int = 42
    shuffle_seed: int = 42
    masking_seed: int = 42
    eval_seed: int = 42

    # Manajemen Checkpoint dan Logging
    output_dir: str = "runs/baseline_run"
    checkpoint_interval_epochs: int = 1
    save_best_model: bool = True
    save_last_checkpoint: bool = True
    log_every_n_steps: int = 10
    overwrite_output_dir: bool = False

    # Metadata eksperimen
    experiment_name: str = "baseline_minibert"
    description: str = "Pelatihan baseline Mini-BERT Masked Language Model"

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """Memvalidasi integritas nilai parameter sebelum digunakan."""
        # 1. Validasi integer positif
        int_fields = {
            "vocab_size": self.vocab_size,
            "d_model": self.d_model,
            "num_layers": self.num_layers,
            "num_heads": self.num_heads,
            "d_ff": self.d_ff,
            "max_position_embeddings": self.max_position_embeddings,
            "batch_size": self.batch_size,
            "epochs": self.epochs,
            "checkpoint_interval_epochs": self.checkpoint_interval_epochs,
            "log_every_n_steps": self.log_every_n_steps,
        }
        for name, val in int_fields.items():
            if isinstance(val, bool) or not isinstance(val, int) or val <= 0:
                raise ValueError(
                    f"Parameter '{name}' harus berupa integer positif (> 0), ditemukan: {val}."
                )

        # 2. Validasi integer non-negatif
        non_neg_ints = {
            "pad_token_id": self.pad_token_id,
            "num_workers": self.num_workers,
            "model_seed": self.model_seed,
            "shuffle_seed": self.shuffle_seed,
            "masking_seed": self.masking_seed,
            "eval_seed": self.eval_seed,
        }
        for name, val in non_neg_ints.items():
            if isinstance(val, bool) or not isinstance(val, int) or val < 0:
                raise ValueError(
                    f"Parameter '{name}' harus berupa integer non-negatif (>= 0), ditemukan: {val}."
                )

        # Validasi batas sampel subset jika diatur
        for name, val in [("max_train_samples", self.max_train_samples), ("max_val_samples", self.max_val_samples)]:
            if val is not None:
                if isinstance(val, bool) or not isinstance(val, int) or val <= 0:
                    raise ValueError(
                        f"Parameter '{name}' harus berupa integer positif (> 0) jika diatur, ditemukan: {val}."
                    )

        # 3. Validasi floating point positif dan finite
        if not (isinstance(self.learning_rate, (int, float)) and math.isfinite(self.learning_rate) and self.learning_rate > 0):
            raise ValueError(
                f"Parameter 'learning_rate' harus berupa float positif finite, ditemukan: {self.learning_rate}."
            )

        if not (isinstance(self.weight_decay, (int, float)) and math.isfinite(self.weight_decay) and self.weight_decay >= 0):
            raise ValueError(
                f"Parameter 'weight_decay' harus berupa float non-negatif finite, ditemukan: {self.weight_decay}."
            )

        if not (isinstance(self.max_grad_norm, (int, float)) and math.isfinite(self.max_grad_norm) and self.max_grad_norm > 0):
            raise ValueError(
                f"Parameter 'max_grad_norm' harus berupa float positif finite, ditemukan: {self.max_grad_norm}."
            )

        # 4. Validasi rasio warmup [0.0, 1.0]
        if not (isinstance(self.warmup_ratio, (int, float)) and math.isfinite(self.warmup_ratio) and 0.0 <= self.warmup_ratio <= 1.0):
            raise ValueError(
                f"Parameter 'warmup_ratio' harus berada dalam rentang [0.0, 1.0], ditemukan: {self.warmup_ratio}."
            )

        # 5. Validasi string opsi
        valid_devices = {"auto", "cpu", "cuda"}
        if self.device not in valid_devices:
            raise ValueError(
                f"Parameter 'device' harus salah satu dari {valid_devices}, ditemukan: '{self.device}'."
            )

        valid_precisions = {"float32"}
        if self.precision not in valid_precisions:
            raise ValueError(
                f"Parameter 'precision' hanya mendukung {valid_precisions} untuk baseline saat ini, ditemukan: '{self.precision}'."
            )

        valid_schedulers = {"linear"}
        if self.lr_scheduler_type not in valid_schedulers:
            raise ValueError(
                f"Parameter 'lr_scheduler_type' hanya mendukung {valid_schedulers}, ditemukan: '{self.lr_scheduler_type}'."
            )

        # 6. Validasi hash format
        if not isinstance(self.expected_vocab_sha256, str) or len(self.expected_vocab_sha256.strip()) != 64:
            raise ValueError("Parameter 'expected_vocab_sha256' harus berupa string SHA-256 heksadesimal 64 karakter.")

    def get_model_config(self) -> MiniBertConfig:
        """Mengonversi parameter arsitektur menjadi instance MiniBertConfig resmi."""
        return MiniBertConfig(
            vocab_size=self.vocab_size,
            pad_token_id=self.pad_token_id,
            d_model=self.d_model,
            num_layers=self.num_layers,
            num_heads=self.num_heads,
            d_ff=self.d_ff,
            max_position_embeddings=self.max_position_embeddings,
            dropout=self.dropout,
            attention_dropout=self.attention_dropout,
            layer_norm_eps=self.layer_norm_eps,
            initializer_range=self.initializer_range,
            vocab_sha256=self.expected_vocab_sha256,
        )

    def to_dict(self) -> Dict[str, Any]:
        """Mengonversi konfigurasi menjadi kamus Python."""
        return asdict(self)

    def to_json_file(self, file_path: str) -> None:
        """Menyimpan konfigurasi ke berkas JSON dengan pembuatan direktori otomatis."""
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2, ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TrainingConfig":
        """Membangun objek TrainingConfig dari kamus dictionary."""
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)

    @classmethod
    def from_json_file(cls, file_path: str) -> "TrainingConfig":
        """Memuat konfigurasi dari berkas JSON."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Berkas konfigurasi '{file_path}' tidak ditemukan.")
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)
