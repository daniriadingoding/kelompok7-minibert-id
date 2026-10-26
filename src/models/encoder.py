"""
Modul Transformer Encoder untuk Mini-BERT Bahasa Indonesia dari nol.
Menyusun tumpukan lapisan encoder menggunakan MultiHeadSelfAttention,
Positionwise Feed-Forward Network, koneksi residual, dan Post-LayerNorm.
"""

from typing import Optional

import torch
import torch.nn as nn

from src.models.attention import MultiHeadSelfAttention
from src.models.config import MiniBertConfig


class PositionwiseFeedForward(nn.Module):
    """
    Lapisan Feed-Forward dua tingkat dengan aktivasi GELU dan Dropout.
    Memetakan representasi d_model ke ruang laten yang lebih besar (d_ff),
    lalu memproyeksikannya kembali ke d_model.
    """

    def __init__(self, config: MiniBertConfig):
        super().__init__()
        self.dense_1 = nn.Linear(config.d_model, config.d_ff)
        self.act_fn = nn.GELU()
        self.dropout = nn.Dropout(config.dropout)
        self.dense_2 = nn.Linear(config.d_ff, config.d_model)

    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
        """
        Forward pass untuk Feed-Forward Network.
        """
        intermediate = self.dense_1(hidden_states)
        intermediate = self.act_fn(intermediate)
        intermediate = self.dropout(intermediate)
        output = self.dense_2(intermediate)
        return output


class TransformerEncoderLayer(nn.Module):
    """
    Satu blok Transformer Encoder dengan arsitektur Post-LayerNorm:
    1. Multi-Head Self-Attention -> Dropout -> Residual Connection -> LayerNorm.
    2. Feed-Forward Network -> Dropout -> Residual Connection -> LayerNorm.

    Penjelasan Penempatan Dropout:
    - Dropout pertama di attention probabilities (setelah softmax pada MultiHeadSelfAttention).
    - Dropout kedua di attention output (pada linear output sebelum residual add).
    - Dropout ketiga di dalam FFN (setelah fungsi aktivasi GELU).
    - Dropout keempat di output FFN (pada proyeksi kedua sebelum residual add kedua).
    Struktur ini memastikan tidak ada tensor yang terkena dropout ganda secara berurutan pada jalur yang sama.
    """

    def __init__(self, config: MiniBertConfig):
        super().__init__()
        self.config = config

        self.attention = MultiHeadSelfAttention(config)
        self.attention_dropout = nn.Dropout(config.dropout)
        self.attention_layer_norm = nn.LayerNorm(config.d_model, eps=config.layer_norm_eps)

        self.feed_forward = PositionwiseFeedForward(config)
        self.output_dropout = nn.Dropout(config.dropout)
        self.output_layer_norm = nn.LayerNorm(config.d_model, eps=config.layer_norm_eps)

    def forward(
        self,
        hidden_states: torch.Tensor,
        attention_mask: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Forward pass untuk satu layer encoder.
        """
        # 1. Sublayer Self-Attention dengan Post-LayerNorm
        attention_output = self.attention(hidden_states, attention_mask=attention_mask)
        attention_output = self.attention_dropout(attention_output)
        hidden_states = self.attention_layer_norm(hidden_states + attention_output)

        # 2. Sublayer Feed-Forward dengan Post-LayerNorm
        ffn_output = self.feed_forward(hidden_states)
        ffn_output = self.output_dropout(ffn_output)
        hidden_states = self.output_layer_norm(hidden_states + ffn_output)

        return hidden_states


class BertEncoder(nn.Module):
    """
    Tumpukan sejumlah num_layers blok TransformerEncoderLayer.
    Menerapkan attention_mask secara konsisten pada setiap blok encoder.
    """

    def __init__(self, config: MiniBertConfig):
        super().__init__()
        self.config = config
        self.layers = nn.ModuleList([
            TransformerEncoderLayer(config) for _ in range(config.num_layers)
        ])

    def forward(
        self,
        hidden_states: torch.Tensor,
        attention_mask: Optional[torch.Tensor] = None,
    ) -> torch.Tensor:
        """
        Forward pass melalui seluruh tumpukan blok encoder.
        """
        for layer in self.layers:
            hidden_states = layer(hidden_states, attention_mask=attention_mask)
        return hidden_states
