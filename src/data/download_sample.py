"""
Script untuk mengambil sampel terukur artikel Wikipedia Bahasa Indonesia
(wikimedia/wikipedia: 20231101.id) menggunakan mode streaming dan shuffle buffer.
"""

import argparse
import datetime
import json
import logging
import os
import sys
import time
from typing import Dict, Any, Tuple, List, Iterable, Optional

sys.stdout.reconfigure(encoding="utf-8")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger("sample_collector")

DATASET_ID = "wikimedia/wikipedia"
CONFIG_NAME = "20231101.id"
VERIFIED_REVISION = "b04c8d1ceb2f5cd4588862100d08de323dccfbaa"

DEFAULT_SAMPLE_SIZE = 300
DEFAULT_BUFFER_SIZE = 1000
DEFAULT_SEED = 42
DEFAULT_MAX_EXAMINED = 3000
DEFAULT_MAX_INIT_RETRIES = 3


def validate_sampling_arguments(
    target_samples: int,
    buffer_size: int,
    max_examined_limit: int,
    max_init_retries: int
) -> None:
    """Memvalidasi parameter sampling agar masuk akal."""
    if target_samples <= 0:
        raise ValueError(f"target_samples harus > 0, diterima: {target_samples}")
    if buffer_size < 0:
        raise ValueError(f"buffer_size harus >= 0, diterima: {buffer_size}")
    if max_examined_limit < target_samples:
        raise ValueError(
            f"max_examined_limit ({max_examined_limit}) tidak boleh lebih kecil dari target_samples ({target_samples})"
        )
    if max_init_retries < 1:
        raise ValueError(f"max_init_retries harus >= 1, diterima: {max_init_retries}")


def validate_existing_sample_file(
    jsonl_path: str,
    meta_path: str,
    expected_count: int
) -> Tuple[bool, str]:
    """
    Memeriksa integritas berkas sampel dan metadata yang sudah ada.
    Mengembalikan (is_valid, reason).
    """
    if not os.path.exists(jsonl_path):
        return False, "Berkas JSONL belum ada"

    valid_lines = 0
    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                line_str = line.strip()
                if line_str:
                    rec = json.loads(line_str)
                    if not isinstance(rec, dict) or not rec.get("id"):
                        return False, f"Format rekaman tidak valid pada baris {line_no}"
                    valid_lines += 1
    except Exception as err:
        return False, f"Gagal membaca/mem-parse JSONL: {err}"

    if valid_lines != expected_count:
        return False, f"Jumlah rekaman ({valid_lines}) tidak cocok dengan target ({expected_count})"

    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                meta = json.load(f)
                if meta.get("status") != "complete":
                    return False, f"Status metadata adalah '{meta.get('status')}', bukan 'complete'"
                if meta.get("actual_samples") != expected_count:
                    return False, f"Metadata actual_samples ({meta.get('actual_samples')}) tidak cocok"
        except Exception as err:
            return False, f"Metadata rusak: {err}"
    else:
        return False, "Berkas metadata pendamping belum ada"

    return True, "Valid dan lengkap"


def sample_records_from_iterable(
    stream: Iterable[Dict[str, Any]],
    target_samples: int,
    max_examined_limit: int
) -> Tuple[List[Dict[str, Any]], int, int, int, str]:
    """
    Fungsi logika murni untuk memproses aliran data.
    Mengembalikan (collected_samples, examined_count, duplicate_count, empty_count, status).
    """
    collected = []
    seen_ids = set()
    seen_titles = set()
    examined_count = 0
    duplicate_count = 0
    empty_count = 0
    status = "partial"

    for item in stream:
        examined_count += 1

        item_id = item.get("id")
        item_title = item.get("title")
        item_text = item.get("text")

        # Cek tipe dan keberadaan nilai
        str_id = str(item_id).strip() if item_id is not None else ""
        str_title = str(item_title).strip() if item_title is not None else ""
        str_text = str(item_text).strip() if item_text is not None else ""

        # Rekaman kosong
        if not str_text or not str_id:
            empty_count += 1
            if examined_count >= max_examined_limit:
                logger.warning(
                    f"Batas pemeriksaan mutlak ({max_examined_limit}) tercapai. Menghentikan iterasi."
                )
                break
            continue

        # Rekaman duplikat
        if str_id in seen_ids or (str_title and str_title in seen_titles):
            duplicate_count += 1
            if examined_count >= max_examined_limit:
                logger.warning(
                    f"Batas pemeriksaan mutlak ({max_examined_limit}) tercapai. Menghentikan iterasi."
                )
                break
            continue

        sample_record = {
            "id": str_id,
            "url": str(item.get("url", "")),
            "title": str_title,
            "text": str(item.get("text", ""))
        }
        collected.append(sample_record)
        seen_ids.add(str_id)
        if str_title:
            seen_titles.add(str_title)

        if len(collected) >= target_samples:
            status = "complete"
            break

        if examined_count >= max_examined_limit:
            logger.warning(
                f"Batas pemeriksaan mutlak ({max_examined_limit}) tercapai. Menghentikan iterasi."
            )
            break

    if len(collected) >= target_samples:
        status = "complete"

    return collected, examined_count, duplicate_count, empty_count, status


def collect_sample(
    output_dir: str = "data/sample",
    target_samples: int = DEFAULT_SAMPLE_SIZE,
    buffer_size: int = DEFAULT_BUFFER_SIZE,
    seed: int = DEFAULT_SEED,
    max_examined_limit: int = DEFAULT_MAX_EXAMINED,
    max_init_retries: int = DEFAULT_MAX_INIT_RETRIES,
    output_filename: Optional[str] = None,
    meta_filename: Optional[str] = None,
    force: bool = False
) -> str:
    """
    Mengambil sampel artikel unik menggunakan streaming dan shuffle buffer.
    """
    validate_sampling_arguments(
        target_samples=target_samples,
        buffer_size=buffer_size,
        max_examined_limit=max_examined_limit,
        max_init_retries=max_init_retries
    )

    os.makedirs(output_dir, exist_ok=True)
    jsonl_filename = output_filename if output_filename else f"wiki_sample_{target_samples}.jsonl"
    meta_filename_str = meta_filename if meta_filename else "sample_metadata.json"
    jsonl_output = os.path.join(output_dir, jsonl_filename)
    meta_output = os.path.join(output_dir, meta_filename_str)

    # Validasi berkas yang sudah ada sebelum memutuskan skip
    if not force and os.path.exists(jsonl_output):
        is_valid, reason = validate_existing_sample_file(jsonl_output, meta_output, target_samples)
        if is_valid:
            logger.info(f"File sampel '{jsonl_output}' sudah lengkap dan valid. Sampling dilewati.")
            return jsonl_output
        else:
            logger.warning(f"File sampel ada namun tidak valid ({reason}). Mengunduh ulang...")

    logger.info(f"Inisialisasi stream: dataset '{DATASET_ID}', konfigurasi '{CONFIG_NAME}'")
    logger.info(f"Revision terverifikasi: {VERIFIED_REVISION}")
    logger.info(f"Target: {target_samples}, Buffer: {buffer_size}, Seed: {seed}, Max Examined: {max_examined_limit}")
    logger.info("Catatan: Shuffle buffer mengacak data dalam jendela lokal buffer, bukan sampel acak seragam dari seluruh 666k artikel.")

    try:
        from datasets import load_dataset
    except ImportError as e:
        logger.error("Library 'datasets' belum terpasang di .venv.")
        raise e

    dataset_stream = None
    last_error = None

    # Retry inisialisasi koneksi stream
    for attempt in range(1, max_init_retries + 1):
        try:
            logger.info(f"Membuka koneksi stream ke Hugging Face (Percobaan {attempt}/{max_init_retries})...")
            dataset_stream = load_dataset(
                DATASET_ID,
                CONFIG_NAME,
                split="train",
                streaming=True,
                revision=VERIFIED_REVISION,
                trust_remote_code=False
            )
            if buffer_size > 0:
                dataset_stream = dataset_stream.shuffle(seed=seed, buffer_size=buffer_size)
            logger.info("Stream berhasil terhubung.")
            break
        except Exception as err:
            logger.warning(f"Percobaan inisialisasi stream {attempt} gagal: {err}")
            last_error = err
            time.sleep(2 * attempt)

    if dataset_stream is None:
        raise RuntimeError(f"Gagal total inisialisasi koneksi stream setelah {max_init_retries} percobaan: {last_error}")

    start_time = time.time()
    collected_samples = []
    examined_count = 0
    duplicate_count = 0
    empty_count = 0
    status = "partial"

    try:
        collected_samples, examined_count, duplicate_count, empty_count, status = sample_records_from_iterable(
            stream=dataset_stream,
            target_samples=target_samples,
            max_examined_limit=max_examined_limit
        )
    except Exception as iter_err:
        logger.error(f"Error saat iterasi streaming: {iter_err}")
        status = "partial"
        if len(collected_samples) == 0:
            raise iter_err
        logger.warning(f"Menyimpan sampel parsial yang sempat terkumpul: {len(collected_samples)} artikel")

    duration_sec = round(time.time() - start_time, 2)
    logger.info(f"Selesai streaming dalam {duration_sec}s. Status: {status.upper()} ({len(collected_samples)}/{target_samples})")

    # Tulis berkas JSONL
    with open(jsonl_output, "w", encoding="utf-8") as f:
        for record in collected_samples:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    file_size_bytes = os.path.getsize(jsonl_output) if os.path.exists(jsonl_output) else 0

    # Simpan metadata
    metadata = {
        "dataset_id": DATASET_ID,
        "config_name": CONFIG_NAME,
        "verified_revision": VERIFIED_REVISION,
        "collection_timestamp": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "status": status,
        "sampling_method": "streaming_shuffle_buffer",
        "buffer_size": buffer_size,
        "seed": seed,
        "target_samples": target_samples,
        "actual_samples": len(collected_samples),
        "total_examined": examined_count,
        "duplicate_skipped": duplicate_count,
        "empty_skipped": empty_count,
        "max_examined_limit": max_examined_limit,
        "duration_seconds": duration_sec,
        "output_file": jsonl_output,
        "file_size_bytes": file_size_bytes,
        "notes": (
            "Streaming menggunakan request parsial HTTP range via datasets/pyarrow. "
            "Shuffle buffer bersifat lokal dan tidak menjamin keacakan seragam sempurna dari seluruh 666k artikel."
        )
    }

    with open(meta_output, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2, ensure_ascii=False)

    logger.info(f"Metadata berhasil disimpan ke '{meta_output}' dengan status '{status}'.")
    return jsonl_output


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Ambil sampel artikel Wikipedia Bahasa Indonesia")
    parser.add_argument("--output-dir", type=str, default="data/sample", help="Direktori penyimpanan")
    parser.add_argument("--num-samples", type=int, default=DEFAULT_SAMPLE_SIZE, help="Target sampel unik")
    parser.add_argument("--buffer-size", type=int, default=DEFAULT_BUFFER_SIZE, help="Ukuran shuffle buffer")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Seed keacakan")
    parser.add_argument("--max-examined", type=int, default=DEFAULT_MAX_EXAMINED, help="Batas pemeriksaan baris")
    parser.add_argument("--output-file", type=str, default=None, help="Nama berkas JSONL spesifik")
    parser.add_argument("--meta-file", type=str, default=None, help="Nama berkas metadata spesifik")
    parser.add_argument("--force", action="store_true", help="Paksa download ulang")
    args = parser.parse_args()

    collect_sample(
        output_dir=args.output_dir,
        target_samples=args.num_samples,
        buffer_size=args.buffer_size,
        seed=args.seed,
        max_examined_limit=args.max_examined,
        output_filename=args.output_file,
        meta_filename=args.meta_file,
        force=args.force
    )
