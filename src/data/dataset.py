"""
Modul PyTorch Dataset, MLM Data Collator, dan DataLoader untuk Mini-BERT Bahasa Indonesia.

Fitur:
- PrechunkedMLMDataset: Memuat sequence chunks tanpa tokenisasi ulang, memvalidasi integritas tensor,
  dan menyaring chunk tanpa kandidat target (seluruh isi [UNK]) ke dalam manifest terpisah.
- MLMDataCollator: Menerapkan 15% dynamic masking (80% [MASK], 10% token acak non-spesial, 10% tetap).
  Target hanya dari ID >= 5 (bukan token khusus 0..4).
  Menghasilkan labels [B, 64] dengan nilai asli di posisi target dan -100 di posisi lain.
- Evaluasi deterministik: Pengacakan eval berbasis hash SHA-256 dari doc_id + chunk_index,
  menjamin hasil identik terlepas dari batch size atau urutan pemuatan.
- Reproduksibilitas train: Mendukung seeding terkontrol antarepoch.
"""

import hashlib
import json
import os
import random
from typing import Dict, List, Any, Optional, Tuple, Union

import torch
from torch.utils.data import Dataset, DataLoader

SPECIAL_TOKEN_IDS = {
    "[PAD]": 0,
    "[UNK]": 1,
    "[CLS]": 2,
    "[SEP]": 3,
    "[MASK]": 4,
}
NUM_SPECIAL_TOKENS = len(SPECIAL_TOKEN_IDS)
PAD_TOKEN_ID = 0
UNK_TOKEN_ID = 1
CLS_TOKEN_ID = 2
SEP_TOKEN_ID = 3
MASK_TOKEN_ID = 4


class PrechunkedMLMDataset(Dataset):
    """
    Dataset PyTorch yang membaca langsung berkas JSONL pre-chunked.
    Menyimpan data asli tanpa memodifikasi berkas sumber.
    """

    def __init__(
        self,
        jsonl_path: str,
        vocab_size: int = 8000,
        max_length: int = 64,
        filter_zero_candidates: bool = True,
    ):
        if not os.path.exists(jsonl_path):
            raise FileNotFoundError(f"Berkas chunk '{jsonl_path}' tidak ditemukan.")

        self.jsonl_path = jsonl_path
        self.vocab_size = vocab_size
        self.max_length = max_length
        self.filter_zero_candidates = filter_zero_candidates

        self.samples: List[Dict[str, Any]] = []
        self.excluded_chunks: List[Dict[str, Any]] = []

        self._load_and_validate()

    def _load_and_validate(self) -> None:
        """Memuat berkas chunk dan memvalidasi struktur tensor serta ketersediaan kandidat MLM."""
        with open(self.jsonl_path, "r", encoding="utf-8") as f:
            for line_idx, line in enumerate(f):
                line_str = line.strip()
                if not line_str:
                    continue

                item = json.loads(line_str)
                doc_id = item.get("doc_id")
                chunk_index = item.get("chunk_index")
                input_ids = item.get("input_ids")
                attention_mask = item.get("attention_mask")

                # 1. Validasi panjang tensor
                if len(input_ids) != self.max_length:
                    raise ValueError(
                        f"Chunk line {line_idx} (doc_id={doc_id}): panjang input_ids "
                        f"({len(input_ids)}) != max_length ({self.max_length})."
                    )
                if len(attention_mask) != self.max_length:
                    raise ValueError(
                        f"Chunk line {line_idx} (doc_id={doc_id}): panjang attention_mask "
                        f"({len(attention_mask)}) != max_length ({self.max_length})."
                    )

                # 2. Validasi rentang ID dan token awal [CLS]
                if input_ids[0] != CLS_TOKEN_ID:
                    raise ValueError(
                        f"Chunk line {line_idx} (doc_id={doc_id}): token pertama harus [CLS] (ID={CLS_TOKEN_ID}), "
                        f"ditemukan ID={input_ids[0]}."
                    )

                for tid in input_ids:
                    if not isinstance(tid, int) or tid < 0 or tid >= self.vocab_size:
                        raise ValueError(
                            f"Chunk line {line_idx} (doc_id={doc_id}): Token ID {tid} di luar rentang "
                            f"0..{self.vocab_size - 1}."
                        )

                # 3. Validasi padding dan attention_mask
                for pos, (tid, mask_val) in enumerate(zip(input_ids, attention_mask)):
                    if tid == PAD_TOKEN_ID and mask_val != 0:
                        raise ValueError(
                            f"Chunk line {line_idx} (doc_id={doc_id}) pos {pos}: token [PAD] harus memiliki mask 0, "
                            f"ditemukan mask={mask_val}."
                        )
                    if tid != PAD_TOKEN_ID and mask_val != 1:
                        raise ValueError(
                            f"Chunk line {line_idx} (doc_id={doc_id}) pos {pos}: token aktif harus memiliki mask 1, "
                            f"ditemukan mask={mask_val}."
                        )

                # 4. Periksa kandidat masking (ID >= 5)
                candidates = [i for i, tid in enumerate(input_ids) if tid >= NUM_SPECIAL_TOKENS]

                if len(candidates) == 0:
                    excluded_record = {
                        "doc_id": doc_id,
                        "chunk_index": chunk_index,
                        "line_index": line_idx,
                        "num_content_tokens": item.get("num_content_tokens", 0),
                        "reason": (
                            "Seluruh token isi adalah [UNK] atau token khusus; tidak ada kandidat token reguler "
                            f"(ID >= {NUM_SPECIAL_TOKENS}) yang layak dijadikan target masking MLM."
                        ),
                        "preview_input_ids": input_ids[:15],
                    }
                    if self.filter_zero_candidates:
                        self.excluded_chunks.append(excluded_record)
                        continue  # Jangan masukkan ke samples aktif
                    else:
                        self.samples.append(item)
                else:
                    self.samples.append(item)

    def __len__(self) -> int:
        return len(self.samples)

    def __getitem__(self, idx: int) -> Dict[str, Any]:
        """
        Mengembalikan kamus salinan data agar data sumber tidak termutasi.
        """
        item = self.samples[idx]
        return {
            "doc_id": item["doc_id"],
            "chunk_index": item["chunk_index"],
            "input_ids": list(item["input_ids"]),
            "attention_mask": list(item["attention_mask"]),
            "num_content_tokens": item.get("num_content_tokens", 0),
        }


class MLMDataCollator:
    """
    Data Collator dinamis untuk Masked Language Model (BERT MLM).
    Menerapkan aturan standard BERT:
    - 15% dari token kandidat reguler (ID >= 5) dipilih sebagai target prediksi.
    - Minimal 1 target dipilih jika terdapat kandidat valid.
    - Distribusi target:
      * 80%: Diganti dengan [MASK] (ID=4)
      * 10%: Diganti dengan token acak reguler (ID 5..vocab_size-1)
      * 10%: Dipertahankan sebagai token asli
    - Token target yang dipertahankan atau diganti tetap memiliki label asli pada posisi tersebut.
    - Token non-target (termasuk [PAD], [CLS], [SEP], [UNK], dan token reguler yang tidak terpilih)
      memiliki label -100 (diabaikan oleh PyTorch CrossEntropyLoss).
    - Mode 'eval': Menggunakan seed deterministik berbasis SHA-256 dari doc_id + chunk_index,
      menjamin hasil evaluasi 100% stabil terlepas dari batch size atau urutan sampling.
    """

    def __init__(
        self,
        vocab_size: int = 8000,
        mask_token_id: int = MASK_TOKEN_ID,
        pad_token_id: int = PAD_TOKEN_ID,
        mlm_probability: float = 0.15,
        mode: str = "train",
        eval_seed: int = 42,
        train_seed: Optional[int] = None,
    ):
        # 1. Validasi mode
        if not isinstance(mode, str) or mode.lower() not in {"train", "eval"}:
            raise ValueError(
                f"Mode collator tidak valid: '{mode}'. Mode hanya menerima 'train' atau 'eval'."
            )
        self.mode = mode.lower()

        # 2. Validasi mlm_probability pada rentang (0, 1]
        if not isinstance(mlm_probability, (int, float)) or mlm_probability <= 0.0 or mlm_probability > 1.0:
            raise ValueError(
                f"mlm_probability={mlm_probability} tidak valid. Harus berada pada rentang terbuka-tertutup (0, 1]."
            )
        self.mlm_probability = float(mlm_probability)

        # 3. Validasi vocab_size
        if not isinstance(vocab_size, int) or vocab_size <= NUM_SPECIAL_TOKENS:
            raise ValueError(
                f"vocab_size={vocab_size} tidak valid. Harus berupa integer > {NUM_SPECIAL_TOKENS}."
            )
        self.vocab_size = vocab_size

        # 4. Validasi konsistensi token ID khusus
        if not isinstance(mask_token_id, int) or not (0 <= mask_token_id < vocab_size):
            raise ValueError(
                f"mask_token_id={mask_token_id} tidak valid. Harus berupa integer dalam rentang 0..{vocab_size - 1}."
            )
        if mask_token_id != MASK_TOKEN_ID:
            raise ValueError(
                f"mask_token_id={mask_token_id} tidak konsisten dengan kontrak token khusus (harus {MASK_TOKEN_ID})."
            )
        self.mask_token_id = mask_token_id

        if not isinstance(pad_token_id, int) or not (0 <= pad_token_id < vocab_size):
            raise ValueError(
                f"pad_token_id={pad_token_id} tidak valid. Harus berupa integer dalam rentang 0..{vocab_size - 1}."
            )
        if pad_token_id != PAD_TOKEN_ID:
            raise ValueError(
                f"pad_token_id={pad_token_id} tidak konsisten dengan kontrak token khusus (harus {PAD_TOKEN_ID})."
            )
        self.pad_token_id = pad_token_id

        self.eval_seed = eval_seed
        self.rng = random.Random(train_seed) if train_seed is not None else random.Random()

    def set_train_seed(self, seed: int) -> None:
        """Mengatur seed acak untuk mode training (berguna untuk reproduksibilitas per-epoch)."""
        self.rng.seed(seed)

    def _get_item_rng(self, doc_id: Any, chunk_index: int) -> random.Random:
        """Menghasilkan generator acak deterministik berbasis SHA-256 untuk mode evaluasi."""
        if self.mode == "eval":
            key = f"{self.eval_seed}_{doc_id}_{chunk_index}"
            digest = hashlib.sha256(key.encode("utf-8")).digest()
            item_seed = int.from_bytes(digest[:8], byteorder="big")
            return random.Random(item_seed)
        else:
            return self.rng

    def __call__(self, batch: List[Dict[str, Any]]) -> Dict[str, Union[torch.Tensor, List[Any]]]:
        batch_input_ids: List[List[int]] = []
        batch_attention_mask: List[List[int]] = []
        batch_labels: List[List[int]] = []
        batch_doc_ids: List[Any] = []
        batch_chunk_indices: List[int] = []

        for item in batch:
            doc_id = item["doc_id"]
            chunk_index = item["chunk_index"]

            # Salinan independen agar sumber tidak termutasi
            input_ids = list(item["input_ids"])
            attention_mask = list(item["attention_mask"])
            seq_len = len(input_ids)
            labels = [-100] * seq_len

            item_rng = self._get_item_rng(doc_id, chunk_index)

            # Kandidat target: Hanya token reguler yang valid (ID >= 5)
            # Menolak PAD(0), UNK(1), CLS(2), SEP(3), MASK(4)
            candidates = [
                i for i, tid in enumerate(input_ids)
                if tid >= NUM_SPECIAL_TOKENS
            ]

            if candidates:
                # Pilih sekitar 15% dari kandidat, minimal 1 target
                k = max(1, int(round(len(candidates) * self.mlm_probability)))
                k = min(k, len(candidates))

                # Ambil k posisi target tanpa pengembalian
                targets = item_rng.sample(candidates, k)

                for idx in targets:
                    orig_token_id = input_ids[idx]
                    labels[idx] = orig_token_id  # Label selalu token asli

                    # Terapkan aturan 80/10/10
                    prob = item_rng.random()
                    if prob < 0.80:
                        # 80%: Ganti dengan [MASK]
                        input_ids[idx] = self.mask_token_id
                    elif prob < 0.90:
                        # 10%: Ganti dengan token acak reguler (ID 5..vocab_size-1)
                        random_replacement_id = item_rng.randint(NUM_SPECIAL_TOKENS, self.vocab_size - 1)
                        input_ids[idx] = random_replacement_id
                    else:
                        # 10%: Tetap token asli
                        input_ids[idx] = orig_token_id

            batch_input_ids.append(input_ids)
            batch_attention_mask.append(attention_mask)
            batch_labels.append(labels)
            batch_doc_ids.append(doc_id)
            batch_chunk_indices.append(chunk_index)

        return {
            "input_ids": torch.tensor(batch_input_ids, dtype=torch.long),
            "attention_mask": torch.tensor(batch_attention_mask, dtype=torch.long),
            "labels": torch.tensor(batch_labels, dtype=torch.long),
            "doc_ids": batch_doc_ids,
            "chunk_indices": torch.tensor(batch_chunk_indices, dtype=torch.long),
        }


def get_mlm_dataloader(
    dataset: PrechunkedMLMDataset,
    batch_size: int = 32,
    shuffle: bool = True,
    collator: Optional[MLMDataCollator] = None,
    num_workers: int = 0,
) -> DataLoader:
    """
    Membuat PyTorch DataLoader siap latih/evaluasi.
    Default num_workers=0 digunakan untuk kesederhanaan dan keandalan pada lingkungan Windows OS.
    """
    if collator is None:
        collator = MLMDataCollator(
            vocab_size=dataset.vocab_size,
            mode="train" if shuffle else "eval"
        )

    return DataLoader(
        dataset,
        batch_size=batch_size,
        shuffle=shuffle,
        collate_fn=collator,
        num_workers=num_workers,
        pin_memory=False,
    )


def generate_mlm_manifests(
    data_dir: str = "data/processed/pilot",
    output_manifest_path: str = "data/processed/pilot/mlm_excluded_chunks_manifest.json",
) -> Dict[str, Any]:
    """
    Memeriksa seluruh split chunk (train, val, test) dan mencatat manifest
    chunk yang dikeluarkan dari indeks siap MLM karena 0 kandidat target.
    """
    splits = ["train", "val", "test"]
    manifest_data = {
        "title": "Manifest Chunk yang Dikeluarkan dari Pelatihan MLM",
        "description": "Mencatat chunk yang memiliki 0 token kandidat reguler (seluruh isi berupa [UNK] atau token khusus).",
        "splits_summary": {},
        "excluded_chunks": []
    }

    for s in splits:
        chunk_file = os.path.join(data_dir, f"{s}_chunks.jsonl")
        ds = PrechunkedMLMDataset(chunk_file, filter_zero_candidates=True)

        manifest_data["splits_summary"][s] = {
            "file": chunk_file,
            "total_raw_chunks": len(ds.samples) + len(ds.excluded_chunks),
            "mlm_ready_chunks": len(ds.samples),
            "excluded_chunks_count": len(ds.excluded_chunks),
        }

        for exc in ds.excluded_chunks:
            exc_record = dict(exc)
            exc_record["split"] = s
            manifest_data["excluded_chunks"].append(exc_record)

    os.makedirs(os.path.dirname(output_manifest_path), exist_ok=True)
    with open(output_manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest_data, f, indent=2, ensure_ascii=False)

    print(f"[Sukses] Manifest MLM excluded chunks disimpan di: {output_manifest_path}")
    for s, summary in manifest_data["splits_summary"].items():
        print(f"[{s.upper()}] Raw Chunks: {summary['total_raw_chunks']:,} | MLM-Ready: {summary['mlm_ready_chunks']:,} | Dikeluarkan: {summary['excluded_chunks_count']}")

    return manifest_data


if __name__ == "__main__":
    generate_mlm_manifests()
