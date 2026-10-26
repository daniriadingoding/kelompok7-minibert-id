"""
Modul Masked Language Model (MLM) Prediction Head untuk Mini-BERT Bahasa Indonesia dari nol.
Memetakan representasi kontekstual akhir encoder menjadi logits distribusi vocabulary.
"""

import torch
import torch.nn as nn

from src.models.config import MiniBertConfig


class BertMLMHead(nn.Module):
    """
    Kepala prediksi Masked Language Modeling:
    Transformasi: Linear(d_model, d_model) -> GELU -> LayerNorm -> Proyeksi Linear ke vocab_size.
    Proyeksi vocabulary mendukung weight tying dengan token embeddings.
    """

    def __init__(self, config: MiniBertConfig):
        super().__init__()
        self.config = config

        self.dense = nn.Linear(config.d_model, config.d_model)
        self.act_fn = nn.GELU()
        self.layer_norm = nn.LayerNorm(config.d_model, eps=config.layer_norm_eps)

        # Proyeksi linear ke ukuran vocabulary
        self.decoder = nn.Linear(config.d_model, config.vocab_size, bias=True)

    def forward(self, hidden_states: torch.Tensor) -> torch.Tensor:
        """
        Forward pass MLM Head.

        Argumen:
            hidden_states: Tensor output encoder dengan bentuk [batch_size, seq_len, d_model].

        Kembalian:
            Logits mentah vocabulary berukuran [batch_size, seq_len, vocab_size].
            Tanpa aplikasi softmax sebelum loss function.
        """
        x = self.dense(hidden_states)
        x = self.act_fn(x)
        x = self.layer_norm(x)
        logits = self.decoder(x)
        return logits
