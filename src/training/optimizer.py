"""
Modul konfigurasi dan eksekusi optimizer AdamW untuk Mini-BERT Bahasa Indonesia.

Menjamin:
1. Setiap parameter trainable terdaftar tepat satu kali.
2. Parameter bersama (tied weights) pada cls.decoder.weight ditangani tanpa duplikasi pendaftaran.
3. Pemisahan parameter weight decay (0.01) dan no-decay (0.0) untuk bias dan LayerNorm.
4. Token embedding dan positional embedding menerima weight decay.
5. Verifikasi jumlah parameter unik di dalam optimizer sama persis dengan model.num_parameters().
6. Pemeriksaan gradien dan loss finite sebelum pembaruan bobot, dengan gradient clipping.
"""

import math
from typing import Any, Dict, List, Set, Tuple

import torch
import torch.nn as nn
from torch.optim import AdamW


def create_optimizer(
    model: nn.Module,
    learning_rate: float = 3e-4,
    weight_decay: float = 0.01,
    betas: Tuple[float, float] = (0.9, 0.999),
    eps: float = 1e-8,
) -> Tuple[AdamW, Dict[str, Any]]:
    """
    Membangun instance AdamW dengan pemisahan decay/no-decay dan proteksi weight tying.

    Kebijakan Pemisahan:
    - No-Decay (weight_decay = 0.0):
      * Seluruh parameter bias (*.bias)
      * Seluruh parameter LayerNorm (weight dan bias pada nn.LayerNorm)
      * Seluruh parameter tensor 1-dimensi
    - Decay (weight_decay = weight_decay):
      * Token Embeddings (embeddings.word_embeddings.weight)
      * Positional Embeddings (embeddings.position_embeddings.weight)
      * Seluruh bobot proyeksi matriks 2-dimensi (Linear weights)
    - Tied Weights Handling:
      * cls.decoder.weight merujuk ke memori word_embeddings.weight yang sama (data_ptr identik).
      * Parameter ini dideteksi dan dilewati agar tidak didaftarkan dua kali di optimizer.

    Argumen:
        model: Instance MiniBertForMaskedLM
        learning_rate: Nilai base learning rate
        weight_decay: Nilai weight decay untuk kelompok decay
        betas: Koefisien momentum AdamW (beta1, beta2)
        eps: Epsilon stabilitas numerik AdamW

    Kembalian:
        Tuple (optimizer, summary_dict)
    """
    decay_params: List[torch.Tensor] = []
    no_decay_params: List[torch.Tensor] = []

    decay_names: List[str] = []
    no_decay_names: List[str] = []
    tied_skipped_names: List[str] = []

    seen_data_ptrs: Set[int] = set()

    for name, param in model.named_parameters(remove_duplicate=False):
        if not param.requires_grad:
            continue

        ptr = param.data_ptr()
        if ptr in seen_data_ptrs:
            # Parameter tied (berbagi memori fisik dengan parameter sebelumnya)
            tied_skipped_names.append(name)
            continue

        seen_data_ptrs.add(ptr)

        # Kebijakan pemisahan no-decay
        is_bias = name.endswith(".bias") or (param.ndim == 1 and "bias" in name.lower())
        is_layernorm = "layernorm" in name.lower() or "layer_norm" in name.lower() or (param.ndim == 1 and not is_bias)

        if is_bias or is_layernorm:
            no_decay_params.append(param)
            no_decay_names.append(name)
        else:
            decay_params.append(param)
            decay_names.append(name)

    param_groups = [
        {
            "params": decay_params,
            "weight_decay": weight_decay,
            "group_name": "decay",
        },
        {
            "params": no_decay_params,
            "weight_decay": 0.0,
            "group_name": "no_decay",
        },
    ]

    optimizer = AdamW(
        param_groups,
        lr=learning_rate,
        betas=betas,
        eps=eps,
    )

    # Validasi ketat kelengkapan dan keunikan parameter
    total_opt_params = sum(p.numel() for group in optimizer.param_groups for p in group["params"])
    total_opt_tensors = sum(len(group["params"]) for group in optimizer.param_groups)

    # Dapatkan jumlah parameter unik model jika model memiliki metode num_parameters
    expected_unique_params = None
    if hasattr(model, "num_parameters"):
        expected_unique_params = model.num_parameters(only_trainable=True)
        if total_opt_params != expected_unique_params:
            raise ValueError(
                f"Inkonsistensi parameter optimizer: Terdaftar {total_opt_params} parameter, "
                f"tetapi model melaporkan {expected_unique_params} parameter unik."
            )

    summary = {
        "learning_rate": learning_rate,
        "weight_decay": weight_decay,
        "total_unique_parameters": total_opt_params,
        "total_tensors_registered": total_opt_tensors,
        "decay_tensors_count": len(decay_params),
        "no_decay_tensors_count": len(no_decay_params),
        "decay_param_names": decay_names,
        "no_decay_param_names": no_decay_names,
        "tied_skipped_names": tied_skipped_names,
    }

    return optimizer, summary


def perform_optimizer_step(
    model: nn.Module,
    optimizer: torch.optim.Optimizer,
    loss: torch.Tensor,
    max_grad_norm: float = 1.0,
) -> float:
    """
    Mengeksekusi backward pass, validasi nilai gradien finite, gradient clipping,
    dan pembaruan bobot optimizer dengan penanganan error numerik.

    Argumen:
        model: Instance model PyTorch
        optimizer: Instance optimizer PyTorch
        loss: Tensor loss skalar
        max_grad_norm: Batas maksimal norma gradien untuk clipping

    Kembalian:
        Nilai float total gradient norm sebelum clipping.
    """
    # 1. Validasi finite loss sebelum backward
    if not torch.isfinite(loss):
        raise FloatingPointError(
            f"Loss bernilai non-finite ({loss.item()}). Proses training dihentikan demi integritas numerik."
        )

    # 2. Backward pass
    loss.backward()

    # 3. Validasi finite gradien pada seluruh parameter yang menerima gradien
    for name, param in model.named_parameters():
        if param.grad is not None:
            if not torch.isfinite(param.grad).all():
                raise FloatingPointError(
                    f"Gradien non-finite (NaN/Inf) terdeteksi pada parameter '{name}' sebelum optimizer.step()."
                )

    # 4. Gradient clipping
    grad_norm = torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=max_grad_norm)
    grad_norm_val = float(grad_norm.item() if isinstance(grad_norm, torch.Tensor) else grad_norm)

    if not math.isfinite(grad_norm_val):
        raise FloatingPointError(
            f"Total gradient norm bernilai non-finite ({grad_norm_val}) setelah clipping."
        )

    # 5. Pembaruan bobot optimizer
    optimizer.step()

    return grad_norm_val
