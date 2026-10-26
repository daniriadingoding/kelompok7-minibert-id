"""
Modul embedding Mini-BERT Bahasa Indonesia dari nol.
Menggabungkan learned token embedding dan learned positional embedding,
dilanjutkan dengan LayerNorm dan Dropout.
"""

from typing import Optional

import torch
import torch.nn as nn

from src.models.config import MiniBertConfig


class BertEmbeddings(nn.Module):
    """
    Lapisan embedding untuk Mini-BERT.
    Menerima token ID, memetakan ke vektor representasi, menjumlahkan dengan
    positional embedding yang dipelajari, dan menormalkan dengan LayerNorm serta Dropout.
    """

    def __init__(self, config: MiniBertConfig):
        super().__init__()
        self.config = config

        self.word_embeddings = nn.Embedding(
            config.vocab_size,
            config.d_model,
            padding_idx=config.pad_token_id,
        )
        self.position_embeddings = nn.Embedding(
            config.max_position_embeddings,
            config.d_model,
        )
        self.layer_norm = nn.LayerNorm(config.d_model, eps=config.layer_norm_eps)
        self.dropout = nn.Dropout(config.dropout)

    def forward(
        self,
        input_ids: torch.Tensor,
        position_ids: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Forward pass untuk embedding.

        Argumen:
            input_ids: Tensor token ID dengan bentuk [batch_size, seq_len].
            position_ids: Tensor posisi opsional dengan bentuk [batch_size, seq_len].
                Jika None, position_ids dibuat otomatis mengikuti device input.

        Kembalian:
            Tensor embedding dengan bentuk [batch_size, seq_len, d_model].
        """
        if not isinstance(input_ids, torch.Tensor):
            raise TypeError(
                f"input_ids harus berupa torch.Tensor, diperoleh tipe {type(input_ids).__name__}."
            )

        if input_ids.ndim != 2:
            raise ValueError(
                f"input_ids harus berupa tensor 2 dimensi berukuran [batch_size, seq_len], "
                f"diperoleh tensor {input_ids.ndim} dimensi dengan bentuk {list(input_ids.shape)}."
            )

        if input_ids.dtype not in (torch.long, torch.int64):
            raise TypeError(
                f"input_ids harus bertipe data torch.long atau torch.int64, diperoleh {input_ids.dtype}."
            )

        batch_size, seq_len = input_ids.shape
        if batch_size == 0 or seq_len == 0:
            raise ValueError(
                f"input_ids tidak boleh kosong, diperoleh bentuk [{batch_size}, {seq_len}]."
            )

        if seq_len > self.config.max_position_embeddings:
            raise ValueError(
                f"Panjang urutan input ({seq_len}) melebihi batas kapasitas maksimum "
                f"positional embeddings ({self.config.max_position_embeddings})."
            )

        if (input_ids < 0).any() or (input_ids >= self.config.vocab_size).any():
            min_val = input_ids.min().item()
            max_val = input_ids.max().item()
            raise ValueError(
                f"Terdapat token ID di luar rentang valid [0, {self.config.vocab_size - 1}]. "
                f"Rentang nilai ditemukan pada tensor: min={min_val}, max={max_val}."
            )

        if position_ids is None:
            # Membuat position_ids pada device yang sama dengan input_ids secara otomatis
            position_ids = torch.arange(
                seq_len,
                dtype=torch.long,
                device=input_ids.device,
            ).unsqueeze(0).expand(batch_size, -1)
        else:
            if not isinstance(position_ids, torch.Tensor):
                raise TypeError(
                    f"position_ids harus berupa torch.Tensor, diperoleh tipe {type(position_ids).__name__}."
                )
            if position_ids.dtype not in (torch.long, torch.int64):
                raise TypeError(
                    f"position_ids harus bertipe torch.long atau torch.int64, diperoleh {position_ids.dtype}."
                )
            if position_ids.device != input_ids.device:
                raise ValueError(
                    f"Device position_ids ({position_ids.device}) harus sama dengan device input_ids ({input_ids.device})."
                )
            if position_ids.shape != (batch_size, seq_len):
                raise ValueError(
                    f"Bentuk position_ids {list(position_ids.shape)} tidak sesuai dengan "
                    f"bentuk input_ids [{batch_size}, {seq_len}]."
                )
            if (position_ids < 0).any() or (position_ids >= self.config.max_position_embeddings).any():
                raise ValueError(
                    f"Terdapat position_ids di luar rentang valid [0, {self.config.max_position_embeddings - 1}]."
                )

        words_embeddings = self.word_embeddings(input_ids)
        positions_embeddings = self.position_embeddings(position_ids)

        embeddings = words_embeddings + positions_embeddings
        embeddings = self.layer_norm(embeddings)
        embeddings = self.dropout(embeddings)
        return embeddings
