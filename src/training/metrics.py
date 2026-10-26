"""
Modul perhitungan dan akumulasi metrik Masked Language Model (MLM) untuk Mini-BERT Bahasa Indonesia.

Menghitung:
- Masked-Token Loss (CrossEntropyLoss murni pada posisi labels != -100)
- Top-1 Accuracy pada posisi target masked (atas seluruh 8.000 vocabulary)
- Top-5 Accuracy pada posisi target masked (atas seluruh 8.000 vocabulary)
- Agregasi berbobot (weighted aggregation) berdasarkan jumlah target riil antarepoch
- Penolakan eksplisit terhadap batch tanpa target
- Pencatatan nilai exp(masked_loss) dengan batasan terminologis yang jelas
"""

import math
from typing import Dict, Any, Optional

import torch
import torch.nn as nn


def compute_batch_mlm_metrics(
    logits: torch.Tensor,
    labels: torch.Tensor,
    vocab_size: int = 8000,
) -> Dict[str, Any]:
    """
    Menghitung metrik MLM untuk satu batch secara presisi.

    Argumen:
        logits: Tensor [B, L, vocab_size] raw logits keluaran model MiniBERT.
        labels: Tensor [B, L] token ID asli pada posisi target, -100 pada posisi lain.
        vocab_size: Ukuran vocabulary model (default 8000).

    Kembalian:
        Kamus berisi:
        - 'loss_sum': Akumulasi CrossEntropyLoss (sum) murni pada target
        - 'loss': Loss rata-rata batch (loss_sum / num_targets)
        - 'num_targets': Jumlah posisi target valid (labels != -100)
        - 'top1_correct': Jumlah prediksi posisi 1 teratas yang tepat
        - 'top5_correct': Jumlah prediksi dalam 5 teratas yang tepat
        - 'top1_acc': Akurasi Top-1 batch
        - 'top5_acc': Akurasi Top-5 batch
    """
    if logits.dim() != 3:
        raise ValueError(f"Dimensi logits harus 3 ([B, L, V]), ditemukan: {logits.dim()}.")
    if labels.dim() != 2:
        raise ValueError(f"Dimensi labels harus 2 ([B, L]), ditemukan: {labels.dim()}.")

    batch_size, seq_len, v_size = logits.shape
    if labels.shape != (batch_size, seq_len):
        raise ValueError(
            f"Bentuk labels {labels.shape} tidak cocok dengan dimensi logits [B, L] ({batch_size}, {seq_len})."
        )

    # 1. Identifikasi posisi target masked (labels != -100)
    target_mask = (labels != -100)
    num_targets = target_mask.sum().item()

    if num_targets == 0:
        raise ValueError(
            "Batch tidak memuat target prediksi MLM yang valid (seluruh labels bernilai -100). "
            "Batch tanpa target tidak dapat diproses untuk perhitungan metrik."
        )

    # 2. Hitung CrossEntropyLoss dengan reduction='sum' murni pada posisi target
    loss_fn_sum = nn.CrossEntropyLoss(ignore_index=-100, reduction="sum")
    loss_sum = loss_fn_sum(logits.view(-1, v_size), labels.view(-1)).item()
    batch_loss = loss_sum / num_targets

    # 3. Hitung Top-1 Accuracy atas seluruh vocabulary
    preds = logits.argmax(dim=-1)  # [B, L]
    top1_correct = ((preds == labels) & target_mask).sum().item()
    top1_acc = top1_correct / num_targets

    # 4. Hitung Top-5 Accuracy atas seluruh vocabulary
    # Gunakan torch.topk pada dimensi vocabulary
    k = min(5, v_size)
    _, top5_preds = logits.topk(k, dim=-1)  # [B, L, 5]
    labels_expanded = labels.unsqueeze(-1).expand_as(top5_preds)  # [B, L, 5]
    top5_correct = ((top5_preds == labels_expanded).any(dim=-1) & target_mask).sum().item()
    top5_acc = top5_correct / num_targets

    return {
        "loss_sum": loss_sum,
        "loss": batch_loss,
        "num_targets": num_targets,
        "top1_correct": top1_correct,
        "top5_correct": top5_correct,
        "top1_acc": top1_acc,
        "top5_acc": top5_acc,
    }


class MLMMetricAccumulator:
    """
    Akumulator metrik epoch berbobot (weighted epoch metric accumulator).
    Menghindari bias 'unweighted batch averaging' dengan mengumpulkan total loss sum,
    total prediksi benar, dan total jumlah target di sepanjang seluruh batch dalam satu epoch.
    """

    def __init__(self, vocab_size: int = 8000):
        self.vocab_size = vocab_size
        self.reset()

    def reset(self) -> None:
        """Mereset akumulator untuk persiapan epoch baru."""
        self.total_loss_sum: float = 0.0
        self.total_targets: int = 0
        self.total_top1_correct: int = 0
        self.total_top5_correct: int = 0
        self.batch_count: int = 0

    def update(self, logits: torch.Tensor, labels: torch.Tensor) -> Dict[str, Any]:
        """
        Memperbarui akumulator dengan keluaran batch baru.
        Mengembalikan metrik instan dari batch tersebut.
        """
        metrics = compute_batch_mlm_metrics(logits, labels, vocab_size=self.vocab_size)
        self.total_loss_sum += metrics["loss_sum"]
        self.total_targets += metrics["num_targets"]
        self.total_top1_correct += metrics["top1_correct"]
        self.total_top5_correct += metrics["top5_correct"]
        self.batch_count += 1
        return metrics

    def compute(self) -> Dict[str, Any]:
        """
        Menghitung metrik agregat berbobot akhir epoch.
        """
        if self.total_targets == 0:
            raise ValueError("Tidak ada target prediksi MLM yang terkumpul dalam akumulator.")

        epoch_loss = self.total_loss_sum / self.total_targets
        epoch_top1 = self.total_top1_correct / self.total_targets
        epoch_top5 = self.total_top5_correct / self.total_targets

        # Eksponensial masked-token loss (BUKAN full-sentence perplexity dan BUKAN standard pseudo-perplexity)
        try:
            exp_masked_loss = math.exp(epoch_loss)
        except OverflowError:
            exp_masked_loss = float("inf")

        return {
            "loss": epoch_loss,
            "top1_acc": epoch_top1,
            "top5_acc": epoch_top5,
            "exp_masked_loss": exp_masked_loss,
            "total_targets": self.total_targets,
            "total_top1_correct": self.total_top1_correct,
            "total_top5_correct": self.total_top5_correct,
            "batch_count": self.batch_count,
        }
