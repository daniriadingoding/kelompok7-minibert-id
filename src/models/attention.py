"""
Modul Multi-Head Self-Attention untuk Mini-BERT Bahasa Indonesia dari nol.
Dibangun menggunakan nn.Linear dan operasi tensor PyTorch dasar,
tanpa menggunakan nn.MultiheadAttention atau implementasi eksternal.
"""

import math
from typing import Optional

import torch
import torch.nn as nn

from src.models.config import MiniBertConfig


class MultiHeadSelfAttention(nn.Module):
    """
    Mekanisme Multi-Head Self-Attention dua arah (bidirectional) dari nol.
    Memproyeksikan Query, Key, dan Value, menghitung scaled dot-product attention,
    menerapkan padding mask pada posisi key menggunakan masked_fill,
    dan menggabungkan output seluruh head.
    """

    def __init__(self, config: MiniBertConfig):
        super().__init__()
        self.config = config
        self.d_model = config.d_model
        self.num_heads = config.num_heads
        self.head_dim = config.d_model // config.num_heads
        self.scale = 1.0 / math.sqrt(self.head_dim)

        self.query = nn.Linear(self.d_model, self.d_model)
        self.key = nn.Linear(self.d_model, self.d_model)
        self.value = nn.Linear(self.d_model, self.d_model)
        self.out_proj = nn.Linear(self.d_model, self.d_model)

        self.dropout = nn.Dropout(config.attention_dropout)

    def forward(
        self,
        hidden_states: torch.Tensor,
        attention_mask: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Forward pass Multi-Head Self-Attention.

        Argumen:
            hidden_states: Tensor input representasi dengan bentuk [batch_size, seq_len, d_model].
            attention_mask: Tensor mask biner [batch_size, seq_len], bernilai 1 untuk token valid
                dan 0 untuk token padding [PAD]. Token [MASK] tetap bernilai 1.

        Kembalian:
            Tensor konteks hasil atensi berukuran [batch_size, seq_len, d_model].
        """
        if not isinstance(hidden_states, torch.Tensor):
            raise TypeError(
                f"hidden_states harus berupa torch.Tensor, diperoleh tipe {type(hidden_states).__name__}."
            )

        if hidden_states.ndim != 3:
            raise ValueError(
                f"hidden_states harus bertata letak 3 dimensi [batch_size, seq_len, d_model], "
                f"diperoleh tensor {hidden_states.ndim} dimensi dengan bentuk {list(hidden_states.shape)}."
            )

        batch_size, seq_len, d_model = hidden_states.shape
        if d_model != self.d_model:
            raise ValueError(
                f"Dimensi terakhir hidden_states ({d_model}) tidak cocok dengan d_model konfigurasi ({self.d_model})."
            )

        if batch_size == 0 or seq_len == 0:
            raise ValueError(
                f"hidden_states tidak boleh kosong, diperoleh bentuk [{batch_size}, {seq_len}, {d_model}]."
            )

        # 1. Proyeksi linear untuk Q, K, dan V: [B, L, D]
        q = self.query(hidden_states)
        k = self.key(hidden_states)
        v = self.value(hidden_states)

        # 2. Reshape dan transpose untuk membagi attention heads: [B, num_heads, L, head_dim]
        q = q.view(batch_size, seq_len, self.num_heads, self.head_dim).transpose(1, 2)
        k = k.view(batch_size, seq_len, self.num_heads, self.head_dim).transpose(1, 2)
        v = v.view(batch_size, seq_len, self.num_heads, self.head_dim).transpose(1, 2)

        # 3. Scaled dot-product attention scores: [B, num_heads, L, L]
        scores = torch.matmul(q, k.transpose(-2, -1)) * self.scale

        # 4. Penanganan padding mask dengan masked_fill
        if attention_mask is not None:
            if not isinstance(attention_mask, torch.Tensor):
                raise TypeError(
                    f"attention_mask harus berupa torch.Tensor, diperoleh tipe {type(attention_mask).__name__}."
                )

            if attention_mask.ndim != 2 or attention_mask.shape != (batch_size, seq_len):
                raise ValueError(
                    f"attention_mask harus berukuran [{batch_size}, {seq_len}], "
                    f"diperoleh bentuk {list(attention_mask.shape)}."
                )

            # Validasi nilai mask hanya boleh 0 atau 1
            is_binary = torch.all((attention_mask == 0) | (attention_mask == 1))
            if not is_binary:
                raise ValueError("attention_mask hanya boleh memuat nilai biner 0 atau 1.")

            # Tolak sampel yang seluruh perhatiannya nol (tidak ada token valid sama sekali)
            mask_sums = attention_mask.sum(dim=-1)
            if (mask_sums == 0).any():
                zero_indices = (mask_sums == 0).nonzero(as_tuple=True)[0].tolist()
                raise ValueError(
                    f"Terdapat sampel dengan seluruh attention_mask bernilai 0 pada indeks: {zero_indices}. "
                    f"Setiap sampel harus memiliki minimal satu token valid."
                )

            # Masking pada posisi key:
            # key_padding_mask bernilai True pada posisi di mana token adalah padding (attention_mask == 0)
            # Nilai -10000.0 digunakan agar softmax mengarahkan bobot token padding mendekati 0.0 secara numerik stabil.
            # Catatan penting: Nilai masking ini tidak otomatis menjamin seluruh operasi bebas dari NaN
            # jika representasi input atau bobot awal sudah memuat nilai non-finite.
            key_padding_mask = (attention_mask == 0).unsqueeze(1).unsqueeze(2)  # [B, 1, 1, L]
            scores = scores.masked_fill(key_padding_mask, -10000.0)

        # 5. Softmax pada dimensi key (dim=-1)
        probs = torch.softmax(scores, dim=-1)
        probs = self.dropout(probs)

        # 6. Perkalian matriks dengan Value: [B, num_heads, L, head_dim]
        context = torch.matmul(probs, v)

        # 7. Penggabungan head kembali ke bentuk [B, L, D]
        context = context.transpose(1, 2).contiguous().view(batch_size, seq_len, self.d_model)

        # 8. Proyeksi linear akhir
        output = self.out_proj(context)
        return output
