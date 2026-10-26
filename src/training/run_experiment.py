"""
Skrip Baris Perintah (CLI) untuk Menjalankan Eksperimen Pelatihan Mini-BERT Bahasa Indonesia.

Penggunaan:
    python -m src.training.run_experiment --config configs/baseline_gpu.json
    python -m src.training.run_experiment --config configs/cpu_smoke.json --device cpu --overwrite
    python -m src.training.run_experiment --config configs/cpu_smoke.json --resume-from runs/smoke/checkpoints/checkpoint_epoch_001.pt
"""

import argparse
import os
import sys

from src.training.config import TrainingConfig
from src.training.trainer import Trainer


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Jalankan eksperimen pelatihan Mini-BERT Bahasa Indonesia dari Nol."
    )
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Jalur ke berkas JSON konfigurasi eksperimen.",
    )
    parser.add_argument(
        "--device",
        type=str,
        default=None,
        choices=["auto", "cpu", "cuda"],
        help="Timpa pilihan device hardware ('auto', 'cpu', 'cuda').",
    )
    parser.add_argument(
        "--resume-from",
        type=str,
        default=None,
        help="Jalur ke berkas checkpoint (.pt) untuk melanjutkan pelatihan pada batas epoch.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Izinkan penulisan ulang direktori output jika direktori sudah ada dan tidak kosong.",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=None,
        help="Timpa jumlah epoch pelatihan.",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=None,
        help="Timpa ukuran batch pelatihan.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if not os.path.exists(args.config):
        print(f"[ERROR] Berkas konfigurasi '{args.config}' tidak ditemukan.", file=sys.stderr)
        sys.exit(1)

    # 1. Muat konfigurasi dasar
    config = TrainingConfig.from_json_file(args.config)

    # 2. Terapkan penimpaan argumen CLI jika diberikan
    if args.device is not None:
        config.device = args.device
    if args.overwrite:
        config.overwrite_output_dir = True
    if args.epochs is not None:
        config.epochs = args.epochs
    if args.batch_size is not None:
        config.batch_size = args.batch_size

    # Validasi ulang konfigurasi final
    config.validate()

    # 3. Inisialisasi Trainer (sampaikan is_resume jika --resume-from diberikan)
    is_resume = args.resume_from is not None
    trainer = Trainer(config, is_resume=is_resume)

    # 4. Jika ada perintah resume, muat checkpoint sebelum memulai loop
    if is_resume:
        trainer.resume_from_checkpoint(args.resume_from)

    # 5. Jalankan Pelatihan
    trainer.train()


if __name__ == "__main__":
    main()
