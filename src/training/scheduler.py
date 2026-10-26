"""
Modul Learning Rate Scheduler untuk Mini-BERT Bahasa Indonesia.

Mengimplementasikan:
1. Linear Warmup: LR meningkat secara linear dari langkah pertama hingga mencapai base_lr pada akhir warmup.
2. Linear Decay: LR meluruh secara linear dari base_lr menuju min_lr_ratio * base_lr pada akhir pelatihan.
3. Definisi eksplisit jumlah langkah optimizer dan pencegahan off-by-one errors.
4. Validasi ketat terhadap konfigurasi scheduler yang tidak valid.
"""

from typing import Callable
import torch
from torch.optim import Optimizer
from torch.optim.lr_scheduler import LambdaLR


def get_linear_schedule_with_warmup(
    optimizer: Optimizer,
    num_warmup_steps: int,
    num_training_steps: int,
    min_lr_ratio: float = 0.0,
    last_epoch: int = -1,
) -> LambdaLR:
    """
    Membuat learning rate scheduler dengan linear warmup dilanjutkan linear decay.

    Karakteristik Numerik:
    - Langkah Pertama (Optimizer Step 1): LR = base_lr * (1 / max(1, num_warmup_steps)).
    - Akhir Warmup (Optimizer Step num_warmup_steps): LR = base_lr * 1.0 (puncak penuh).
    - Akhir Pelatihan (Optimizer Step num_training_steps): LR = base_lr * min_lr_ratio.
    - Setelah Akhir Pelatihan (Step > num_training_steps): LR tetap pada min_lr_ratio.

    Argumen:
        optimizer: Instance optimizer PyTorch yang dipasangi scheduler.
        num_warmup_steps: Jumlah langkah optimizer untuk fase warmup (integer >= 0).
        num_training_steps: Total jumlah langkah optimizer dalam keseluruhan training (integer > 0).
        min_lr_ratio: Rasio learning rate minimal di akhir run terhadap base_lr (rentang [0.0, 1.0]).
        last_epoch: Indeks epoch terakhir untuk resume (default -1).

    Kembalian:
        torch.optim.lr_scheduler.LambdaLR
    """
    # 1. Validasi integer dan rentang
    if isinstance(num_training_steps, bool) or not isinstance(num_training_steps, int) or num_training_steps <= 0:
        raise ValueError(
            f"num_training_steps harus berupa integer positif (> 0), ditemukan: {num_training_steps}."
        )

    if isinstance(num_warmup_steps, bool) or not isinstance(num_warmup_steps, int) or num_warmup_steps < 0:
        raise ValueError(
            f"num_warmup_steps harus berupa integer non-negatif (>= 0), ditemukan: {num_warmup_steps}."
        )

    if num_warmup_steps > num_training_steps:
        raise ValueError(
            f"num_warmup_steps ({num_warmup_steps}) tidak boleh melebihi num_training_steps ({num_training_steps})."
        )

    if not isinstance(min_lr_ratio, (int, float)) or not (0.0 <= float(min_lr_ratio) <= 1.0):
        raise ValueError(
            f"min_lr_ratio harus berupa float dalam rentang [0.0, 1.0], ditemukan: {min_lr_ratio}."
        )

    min_lr_ratio = float(min_lr_ratio)

    def lr_lambda(current_step: int) -> float:
        # current_step adalah 0-indexed integer (0 sebelum step pertama, 1 setelah step pertama, dst)
        # opt_step merepresentasikan optimizer step ke-N (1-indexed) yang sedang atau akan dieksekusi
        opt_step = current_step + 1

        if num_warmup_steps > 0 and opt_step <= num_warmup_steps:
            # Fase Warmup: Linear dari step 1 hingga step num_warmup_steps
            return float(opt_step) / float(num_warmup_steps)

        # Fase Linear Decay
        if opt_step >= num_training_steps:
            return min_lr_ratio

        decay_steps = num_training_steps - num_warmup_steps
        if decay_steps <= 0:
            return 1.0

        decay_progress = float(opt_step - num_warmup_steps) / float(decay_steps)
        factor = 1.0 - decay_progress * (1.0 - min_lr_ratio)
        return max(min_lr_ratio, factor)

    return LambdaLR(optimizer, lr_lambda, last_epoch=last_epoch)
