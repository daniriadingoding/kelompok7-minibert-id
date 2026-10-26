"""
Modul konfigurasi arsitektur Mini-BERT Bahasa Indonesia.
Menyimpan seluruh hyperparameter model secara terpusat dengan validasi ketat.
"""

import hashlib
import json
import math
import os
from dataclasses import asdict, dataclass
from typing import Any, Dict, Optional


@dataclass
class MiniBertConfig:
    """
    Konfigurasi hyperparameter untuk Mini-BERT Bahasa Indonesia dari nol.
    """

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
    vocab_sha256: Optional[str] = None

    def __post_init__(self) -> None:
        self.validate()

    def validate(self) -> None:
        """
        Validasi tipe data dan rentang nilai seluruh hyperparameter.
        Menolak nilai non-positif, NaN, Inf, atau tipe data yang tidak sesuai.
        """
        # 1. Validasi dimensi integer positif
        int_fields = {
            "vocab_size": self.vocab_size,
            "d_model": self.d_model,
            "num_layers": self.num_layers,
            "num_heads": self.num_heads,
            "d_ff": self.d_ff,
            "max_position_embeddings": self.max_position_embeddings,
        }
        for name, val in int_fields.items():
            if isinstance(val, bool) or not isinstance(val, int) or val <= 0:
                raise ValueError(
                    f"Parameter '{name}' harus berupa integer positif, diperoleh: {val} (tipe: {type(val).__name__})."
                )

        # 2. Validasi keterbagian attention head
        if self.d_model % self.num_heads != 0:
            raise ValueError(
                f"d_model ({self.d_model}) harus habis dibagi num_heads ({self.num_heads}), "
                f"sisa pembagian: {self.d_model % self.num_heads}."
            )

        # 3. Validasi pad_token_id
        if (
            isinstance(self.pad_token_id, bool)
            or not isinstance(self.pad_token_id, int)
            or not (0 <= self.pad_token_id < self.vocab_size)
        ):
            raise ValueError(
                f"pad_token_id ({self.pad_token_id}) harus berupa integer dalam rentang [0, {self.vocab_size - 1}]."
            )

        # 4. Validasi probabilitas dropout
        float_dropout_fields = {
            "dropout": self.dropout,
            "attention_dropout": self.attention_dropout,
        }
        for name, val in float_dropout_fields.items():
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                raise ValueError(
                    f"Parameter '{name}' harus berupa angka, diperoleh tipe: {type(val).__name__}."
                )
            float_val = float(val)
            if math.isnan(float_val) or math.isinf(float_val) or not (0.0 <= float_val < 1.0):
                raise ValueError(
                    f"Parameter '{name}' harus berupa angka finite pada rentang [0.0, 1.0), diperoleh: {val}."
                )

        # 5. Validasi LayerNorm epsilon dan initializer range
        positive_floats = {
            "layer_norm_eps": self.layer_norm_eps,
            "initializer_range": self.initializer_range,
        }
        for name, val in positive_floats.items():
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                raise ValueError(
                    f"Parameter '{name}' harus berupa angka, diperoleh tipe: {type(val).__name__}."
                )
            float_val = float(val)
            if math.isnan(float_val) or math.isinf(float_val) or float_val <= 0.0:
                raise ValueError(
                    f"Parameter '{name}' harus berupa angka positif finite, diperoleh: {val}."
                )

        # 6. Validasi tipe vocab_sha256 jika ada
        if self.vocab_sha256 is not None:
            if not isinstance(self.vocab_sha256, str) or len(self.vocab_sha256.strip()) == 0:
                raise ValueError(
                    f"vocab_sha256 harus berupa string heksadesimal non-kosong jika diatur, diperoleh: {self.vocab_sha256}."
                )

    def to_dict(self) -> Dict[str, Any]:
        """Mengonversi konfigurasi menjadi kamus Python."""
        return asdict(self)

    def to_json_string(self) -> str:
        """Mengonversi konfigurasi menjadi string JSON berformat rapi."""
        return json.dumps(self.to_dict(), indent=2, ensure_ascii=False)

    def to_json_file(self, file_path: str) -> None:
        """Menyimpan konfigurasi ke berkas JSON pada file_path."""
        os.makedirs(os.path.dirname(os.path.abspath(file_path)), exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(self.to_json_string())

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "MiniBertConfig":
        """Membangun objek MiniBertConfig dari kamus dictionary."""
        valid_keys = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_keys}
        return cls(**filtered)

    @classmethod
    def from_json_file(cls, file_path: str) -> "MiniBertConfig":
        """Memuat konfigurasi dari berkas JSON."""
        if not os.path.exists(file_path):
            raise FileNotFoundError(f"Berkas konfigurasi '{file_path}' tidak ditemukan.")
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return cls.from_dict(data)

    @classmethod
    def from_tokenizer_directory(
        cls,
        tokenizer_dir: str,
        **overrides: Any,
    ) -> "MiniBertConfig":
        """
        Membangun konfigurasi yang otomatis mencocokkan artefak tokenizer:
        Membaca vocab.json, menghitung hash kanonikal SHA-256 yang identik dengan tokenizer,
        dan menetapkan vocab_size serta pad_token_id.
        Menolak override yang bertentangan dengan artefak fisik tokenizer.
        """
        vocab_path = os.path.join(tokenizer_dir, "vocab.json")
        config_path = os.path.join(tokenizer_dir, "tokenizer_config.json")

        if not os.path.exists(vocab_path):
            raise FileNotFoundError(f"Berkas vocabulary '{vocab_path}' tidak ditemukan.")

        with open(vocab_path, "r", encoding="utf-8") as f:
            vocab: Dict[str, int] = json.load(f)

        vocab_hash = cls.compute_vocab_hash(vocab)
        vocab_size = len(vocab)
        pad_token_id = vocab.get("[PAD]", 0)

        # Periksa apakah ada konfigurasi tokenizer untuk max_length
        max_position = 64
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                tok_cfg = json.load(f)
            max_position = tok_cfg.get("max_length", max_position)

        # Validasi ketat terhadap override agar tidak bertentangan dengan artefak fisik
        if "vocab_size" in overrides and overrides["vocab_size"] != vocab_size:
            raise ValueError(
                f"Override vocab_size ({overrides['vocab_size']}) bertentangan dengan ukuran vocabulary artefak ({vocab_size})."
            )
        if "pad_token_id" in overrides and overrides["pad_token_id"] != pad_token_id:
            raise ValueError(
                f"Override pad_token_id ({overrides['pad_token_id']}) bertentangan dengan pad_token_id artefak ({pad_token_id})."
            )
        if "vocab_sha256" in overrides and overrides["vocab_sha256"] != vocab_hash:
            raise ValueError(
                f"Override vocab_sha256 ({overrides['vocab_sha256']}) bertentangan dengan hash artefak ({vocab_hash})."
            )

        config_args: Dict[str, Any] = {
            "vocab_size": vocab_size,
            "pad_token_id": pad_token_id,
            "max_position_embeddings": max_position,
            "vocab_sha256": vocab_hash,
        }
        config_args.update(overrides)
        return cls(**config_args)

    @staticmethod
    def compute_vocab_hash(vocab: Dict[str, int]) -> str:
        """
        Menghitung hash SHA-256 kanonikal dari pasangan (token, ID) yang terurut berdasarkan ID.
        Algoritma ini identik secara eksak dengan perhitungan di WordLevelTokenizer dan build_vocab.
        """
        sorted_pairs = sorted(vocab.items(), key=lambda x: x[1])
        serialized = json.dumps(sorted_pairs, ensure_ascii=False)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()
