"""
Arsitektur lengkap Mini-BERT Bahasa Indonesia untuk Masked Language Modeling dari nol.
Menyatukan BertEmbeddings, BertEncoder, dan BertMLMHead dengan weight tying,
inisialisasi bobot terkontrol, penghitungan parameter unik, serta fungsi save/load terverifikasi.
"""

import json
import os
from typing import Any, Dict, Optional

import torch
import torch.nn as nn

from src.models.config import MiniBertConfig
from src.models.embeddings import BertEmbeddings
from src.models.encoder import BertEncoder
from src.models.mlm_head import BertMLMHead

MODEL_VERSION = "1.0.0"


class MiniBertForMaskedLM(nn.Module):
    """
    Model Mini-BERT utuh untuk tugas Masked Language Model.
    Menerima input_ids dan attention_mask, menghasilkan raw logits berukuran [B, L, vocab_size].
    """

    def __init__(self, config: MiniBertConfig):
        super().__init__()
        self.config = config

        self.embeddings = BertEmbeddings(config)
        self.encoder = BertEncoder(config)
        self.cls = BertMLMHead(config)

        # 1. Inisialisasi bobot acak standar BERT
        self.apply(self._init_weights)

        # 2. Terapkan weight tying setelah inisialisasi bobot dasar
        # Menghubungkan matriks bobot proyeksi vocabulary dengan matriks bobot token embedding
        self.tie_weights()

        # 3. Pastikan vektor baris token [PAD] pada inisialisasi awal bernilai nol
        if self.embeddings.word_embeddings.padding_idx is not None:
            with torch.no_grad():
                self.embeddings.word_embeddings.weight[
                    self.embeddings.word_embeddings.padding_idx
                ].zero_()

    def tie_weights(self) -> None:
        """
        Mengikat bobot decoder proyeksi vocabulary ke token embeddings.
        Bias decoder tetap independen dan tidak diikat.
        """
        self.cls.decoder.weight = self.embeddings.word_embeddings.weight

    def _init_weights(self, module: nn.Module) -> None:
        """
        Inisialisasi bobot acak terdokumentasi:
        - nn.Linear: Distribusi normal dengan mean=0.0 dan std=initializer_range (0.02), bias nol.
        - nn.Embedding: Distribusi normal dengan mean=0.0 dan std=initializer_range (0.02).
        - nn.LayerNorm: Bobot diinisialisasi 1.0 dan bias 0.0.
        """
        if isinstance(module, nn.Linear):
            module.weight.data.normal_(mean=0.0, std=self.config.initializer_range)
            if module.bias is not None:
                module.bias.data.zero_()
        elif isinstance(module, nn.Embedding):
            module.weight.data.normal_(mean=0.0, std=self.config.initializer_range)
            if module.padding_idx is not None:
                module.weight.data[module.padding_idx].zero_()
        elif isinstance(module, nn.LayerNorm):
            module.bias.data.zero_()
            module.weight.data.fill_(1.0)

    def num_parameters(self, only_trainable: bool = True) -> int:
        """
        Menghitung jumlah parameter unik pada model.
        Bobot bersama (tied weights) hanya dihitung satu kali melalui pelacakan data_ptr unik.
        """
        seen_ptrs = set()
        total_params = 0
        for p in self.parameters():
            if only_trainable and not p.requires_grad:
                continue
            ptr = p.data_ptr()
            if ptr not in seen_ptrs:
                seen_ptrs.add(ptr)
                total_params += p.numel()
        return total_params

    def forward(
        self,
        input_ids: torch.Tensor,
        attention_mask: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Forward pass model Mini-BERT.

        Argumen:
            input_ids: Tensor token ID berukuran [batch_size, seq_len].
            attention_mask: Tensor mask perhatian biner [batch_size, seq_len].
                Bernilai 1 untuk token valid dan 0 untuk padding.
                Metadata batch (doc_ids, chunk_indices) tidak dikirimkan ke model.

        Kembalian:
            logits: Tensor logits mentah berukuran [batch_size, seq_len, vocab_size],
                tanpa aplikasi softmax sebelum CrossEntropyLoss.
        """
        embedding_output = self.embeddings(input_ids)
        encoder_output = self.encoder(embedding_output, attention_mask=attention_mask)
        logits = self.cls(encoder_output)
        return logits

    def save_pretrained(
        self,
        save_directory: str,
        filename: str = "model.pt",
        checkpoint_status: str = "random_init",
    ) -> Dict[str, str]:
        """
        Menyimpan konfigurasi dan state_dict model.
        Mencatat versi model, status checkpoint, dan hash vocabulary pada metadata checkpoint.
        Status checkpoint bernilai 'random_init', 'trained', atau string eksplisit lainnya.
        """
        os.makedirs(save_directory, exist_ok=True)

        # 1. Simpan konfigurasi
        config_file = os.path.join(save_directory, "config.json")
        self.config.to_json_file(config_file)

        # 2. Simpan bobot model dengan metadata lengkap
        model_file = os.path.join(save_directory, filename)
        checkpoint = {
            "model_version": MODEL_VERSION,
            "checkpoint_status": checkpoint_status,
            "vocab_sha256": self.config.vocab_sha256,
            "config": self.config.to_dict(),
            "state_dict": self.state_dict(),
        }
        torch.save(checkpoint, model_file)

        return {"config_file": config_file, "model_file": model_file}

    @classmethod
    def from_pretrained(
        cls,
        load_directory: str,
        filename: str = "model.pt",
        tokenizer_dir: Optional[str] = None,
        require_tokenizer: bool = False,
    ) -> "MiniBertForMaskedLM":
        """
        Memuat model dari berkas penyimpanan checkpoint dengan validasi ketat:
        1. Memeriksa keberadaan berkas config.json dan model.pt.
        2. Mencocokkan seluruh field konfigurasi config.json dengan dictionary config dalam model.pt.
        3. Memvalidasi bahwa vocab_sha256 tidak kosong dan cocok antara config dan checkpoint.
        4. Jika require_tokenizer=True atau tokenizer_dir diberikan, memvalidasi kecocokan dengan artefak vocab.json tokenizer.
        5. Memuat state_dict dengan strict=True dan menjamin weight tying tetap aktif.
        6. Mengekstrak metadata checkpoint_status ('random_init', 'trained', atau 'unknown').
        """
        config_file = os.path.join(load_directory, "config.json")
        model_file = os.path.join(load_directory, filename)

        if not os.path.exists(config_file):
            raise FileNotFoundError(f"Berkas konfigurasi '{config_file}' tidak ditemukan.")
        if not os.path.exists(model_file):
            raise FileNotFoundError(f"Berkas bobot model '{model_file}' tidak ditemukan.")

        config = MiniBertConfig.from_json_file(config_file)

        checkpoint = torch.load(model_file, map_location="cpu", weights_only=True)
        if not isinstance(checkpoint, dict):
            raise ValueError(f"Berkas checkpoint '{model_file}' tidak memuat kamus dictionary yang valid.")

        # 1. Validasi keberadaan dan kesesuaian hash vocabulary pada checkpoint
        checkpoint_hash = checkpoint.get("vocab_sha256")
        if not config.vocab_sha256 or not isinstance(config.vocab_sha256, str) or len(config.vocab_sha256.strip()) == 0:
            raise ValueError("Konfigurasi model pada config.json tidak memuat nilai vocab_sha256 yang sah.")
        if not checkpoint_hash or not isinstance(checkpoint_hash, str) or len(checkpoint_hash.strip()) == 0:
            raise ValueError(f"Metadata checkpoint '{model_file}' tidak memuat nilai vocab_sha256 yang sah.")
        if config.vocab_sha256 != checkpoint_hash:
            raise ValueError(
                f"Ketidakcocokan hash vocabulary: config.json memuat '{config.vocab_sha256}' "
                f"sedangkan metadata checkpoint '{model_file}' memuat '{checkpoint_hash}'."
            )

        # 2. Validasi kecocokan dictionary config pada metadata checkpoint
        if "config" not in checkpoint or checkpoint["config"] is None:
            raise ValueError(
                f"Metadata checkpoint '{model_file}' wajib memuat dictionary konfigurasi 'config'."
            )
        checkpoint_config = checkpoint["config"]
        if not isinstance(checkpoint_config, dict):
            raise ValueError(
                f"Metadata 'config' pada checkpoint '{model_file}' harus berupa dictionary, "
                f"tetapi ditemukan tipe {type(checkpoint_config).__name__}."
            )

        expected_cfg_dict = config.to_dict()
        missing_fields = set(expected_cfg_dict.keys()) - set(checkpoint_config.keys())
        if missing_fields:
            raise ValueError(
                f"Metadata config pada checkpoint '{model_file}' tidak lengkap, field hilang: {sorted(missing_fields)}."
            )

        extra_fields = set(checkpoint_config.keys()) - set(expected_cfg_dict.keys())
        if extra_fields:
            raise ValueError(
                f"Metadata config pada checkpoint '{model_file}' memuat field tidak dikenal: {sorted(extra_fields)}."
            )

        for key, expected_val in expected_cfg_dict.items():
            actual_val = checkpoint_config[key]
            if actual_val != expected_val:
                raise ValueError(
                    f"Ketidakcocokan konfigurasi pada parameter '{key}': "
                    f"config.json={expected_val}, checkpoint={actual_val}."
                )

        # 3. Validasi tokenizer
        if require_tokenizer and tokenizer_dir is None:
            raise ValueError("tokenizer_dir wajib diberikan untuk memvalidasi kesesuaian vocabulary model dan tokenizer.")

        if tokenizer_dir is not None:
            vocab_file = os.path.join(tokenizer_dir, "vocab.json")
            if not os.path.exists(vocab_file):
                raise FileNotFoundError(f"Berkas vocabulary tokenizer '{vocab_file}' tidak ditemukan.")
            with open(vocab_file, "r", encoding="utf-8") as f:
                vocab_dict = json.load(f)
            actual_tok_hash = MiniBertConfig.compute_vocab_hash(vocab_dict)
            if actual_tok_hash != config.vocab_sha256:
                raise ValueError(
                    f"Integritas artefak gagal: Hash vocabulary tokenizer ({actual_tok_hash}) "
                    f"tidak cocok dengan hash vocabulary model ({config.vocab_sha256})."
                )

        # 4. Inisialisasi model dan pemuatan bobot strict
        model = cls(config)
        state_dict = checkpoint["state_dict"] if "state_dict" in checkpoint else checkpoint
        model.load_state_dict(state_dict, strict=True)

        # 5. Pastikan tautan memori weight tying tetap aktif
        model.tie_weights()

        # 6. Catat metadata status checkpoint pada instance model
        raw_status = checkpoint.get("checkpoint_status")
        if isinstance(raw_status, str) and raw_status.strip():
            model.checkpoint_status = raw_status.strip()
        else:
            model.checkpoint_status = "unknown"

        return model

