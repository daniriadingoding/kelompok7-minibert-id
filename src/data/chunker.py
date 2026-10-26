"""
Modul pemotongan urutan teks (Sequence Chunker) tanpa tumpang tindih (non-overlapping)
untuk Mini-BERT Bahasa Indonesia.

Fitur:
- Memotong artikel panjang menjadi segmen-segmen input berukuran tetap max_length (default 64).
- Alokasi: 62 token isi + 1 token [CLS] di awal + 1 token [SEP] di akhir = 64 token.
- Mengisi padding [PAD]=0 dan attention_mask (1 untuk token aktif, 0 untuk padding).
- Mempertahankan doc_id dan chunk_index untuk pelacakan silsilah token.
- Menolak contoh yang hanya berisi token khusus (zero content tokens).
- Menangani sisa potongan pendek di akhir artikel (tail chunk) secara terukur dan transparan.
- Memproses berkas split per dokumen tanpa mencampur antarsplit.
"""

import argparse
import json
import os
import sys
from typing import Dict, List, Any, Tuple, Optional

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))
sys.stdout.reconfigure(encoding="utf-8")

from src.data.tokenizer import WordLevelTokenizer, SPECIAL_TOKENS

DEFAULT_MAX_LENGTH = 64
DEFAULT_MIN_CHUNK_TOKENS = 5


def chunk_document(
    doc_id: Any,
    text: str,
    tokenizer: WordLevelTokenizer,
    max_length: int = DEFAULT_MAX_LENGTH,
    min_chunk_tokens: int = DEFAULT_MIN_CHUNK_TOKENS
) -> Tuple[List[Dict[str, Any]], int]:
    """
    Memecah satu dokumen teks menjadi potongan-potongan chunk encoding siap latih.

    Returns:
        chunks: Daftar kamus chunk valid.
        discarded_tail_chunks: Jumlah potongan sisa pendek di akhir dokumen yang dikeluarkan.
    """
    content_max = max_length - 2
    if content_max <= 0:
        raise ValueError(
            f"max_length={max_length} tidak valid untuk chunking. "
            f"Dibutuhkan max_length > 2 agar kapasitas token isi bernilai positif (tersedia {content_max} token isi)."
        )
    raw_tokens = tokenizer.tokenize(text)
    # Filter token khusus yang mungkin ada dalam teks asli
    content_tokens = [t for t in raw_tokens if t not in SPECIAL_TOKENS]

    if not content_tokens:
        # Dokumen tanpa token isi tidak menghasilkan chunk apa pun
        return [], 0

    chunks: List[Dict[str, Any]] = []
    discarded_tail = 0

    # Potong secara non-overlapping dalam blok content_max (62 token)
    total_raw_chunks = (len(content_tokens) + content_max - 1) // content_max

    for chunk_idx in range(total_raw_chunks):
        start_idx = chunk_idx * content_max
        end_idx = min(start_idx + content_max, len(content_tokens))
        chunk_slice = content_tokens[start_idx:end_idx]
        slice_len = len(chunk_slice)

        # Penanganan sisa chunk pendek:
        # Jika chunk_idx > 0 dan panjang potongan < min_chunk_tokens, buang agar model tidak
        # dilatih pada fragmen kalimat tak bermakna yang didominasi padding.
        # Chunk 0 selalu dipertahankan selama memiliki minimal 1 token isi.
        if chunk_idx > 0 and slice_len < min_chunk_tokens:
            discarded_tail += 1
            continue

        # Susun token dengan [CLS] dan [SEP]
        full_tokens = [tokenizer.cls_token] + chunk_slice + [tokenizer.sep_token]
        input_ids = tokenizer.convert_tokens_to_ids(full_tokens)
        attention_mask = [1] * len(input_ids)

        # Padding jika panjang < max_length
        pad_len = max_length - len(input_ids)
        if pad_len > 0:
            input_ids.extend([tokenizer.pad_token_id] * pad_len)
            attention_mask.extend([0] * pad_len)

        chunks.append({
            "doc_id": doc_id,
            "chunk_index": len(chunks),  # indeks sekuensial yang dipertahankan
            "original_chunk_slice": chunk_idx,
            "num_content_tokens": slice_len,
            "input_ids": input_ids,
            "attention_mask": attention_mask,
            "is_padded": pad_len > 0
        })

    # Perbarui total_chunks_in_doc pada seluruh chunk
    total_valid = len(chunks)
    for c in chunks:
        c["total_chunks_in_doc"] = total_valid

    return chunks, discarded_tail


def process_split_chunks(
    input_jsonl: str,
    output_jsonl: str,
    tokenizer: WordLevelTokenizer,
    max_length: int = DEFAULT_MAX_LENGTH,
    min_chunk_tokens: int = DEFAULT_MIN_CHUNK_TOKENS
) -> Dict[str, Any]:
    """
    Memproses seluruh dokumen dalam satu split menjadi kumpulan chunk tanpa tumpang tindih.
    Menyimpan hasil ke berkas JSONL baru.
    """
    if not os.path.exists(input_jsonl):
        raise FileNotFoundError(f"Berkas input split '{input_jsonl}' tidak ditemukan.")

    os.makedirs(os.path.dirname(output_jsonl), exist_ok=True)

    total_docs = 0
    total_chunks_retained = 0
    total_tail_discarded = 0
    docs_with_multiple_chunks = 0
    total_padded_chunks = 0
    total_content_tokens = 0

    with open(input_jsonl, "r", encoding="utf-8") as in_f, open(output_jsonl, "w", encoding="utf-8") as out_f:
        for line in in_f:
            line_str = line.strip()
            if not line_str:
                continue
            total_docs += 1
            doc = json.loads(line_str)
            doc_id = doc.get("id", f"doc_{total_docs}")
            text = doc.get("text", "")

            chunks, discarded_count = chunk_document(
                doc_id=doc_id,
                text=text,
                tokenizer=tokenizer,
                max_length=max_length,
                min_chunk_tokens=min_chunk_tokens
            )

            total_tail_discarded += discarded_count
            if len(chunks) > 1:
                docs_with_multiple_chunks += 1

            for chunk in chunks:
                total_chunks_retained += 1
                total_content_tokens += chunk["num_content_tokens"]
                if chunk["is_padded"]:
                    total_padded_chunks += 1
                out_f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

    stats = {
        "input_file": input_jsonl,
        "output_file": output_jsonl,
        "total_documents": total_docs,
        "total_chunks_retained": total_chunks_retained,
        "total_tail_chunks_discarded": total_tail_discarded,
        "docs_with_multiple_chunks": docs_with_multiple_chunks,
        "docs_single_chunk": total_docs - docs_with_multiple_chunks,
        "total_padded_chunks": total_padded_chunks,
        "total_content_tokens": total_content_tokens,
        "avg_content_tokens_per_chunk": round(total_content_tokens / max(1, total_chunks_retained), 2),
        "max_length": max_length,
        "min_chunk_tokens_threshold": min_chunk_tokens
    }

    print(f"[{os.path.basename(input_jsonl)}] {total_docs} dokumen -> {total_chunks_retained:,} chunks (Dibuang sisa < {min_chunk_tokens}: {total_tail_discarded})")
    return stats


def run_chunking_pipeline(
    data_dir: str = "data/processed/pilot",
    max_length: int = DEFAULT_MAX_LENGTH,
    min_chunk_tokens: int = DEFAULT_MIN_CHUNK_TOKENS
) -> Dict[str, Any]:
    """
    Menjalankan proses chunking untuk seluruh split: train, val, dan test.
    Menyimpan statistik chunking ke chunking_manifest.json.
    """
    tokenizer = WordLevelTokenizer.from_pretrained(data_dir)
    print(f"Memuat tokenizer dari '{data_dir}' (Vocab size: {tokenizer.vocab_size})...")

    splits = ["train", "val", "test"]
    all_stats = {}

    for split in splits:
        in_file = os.path.join(data_dir, f"{split}.jsonl")
        out_file = os.path.join(data_dir, f"{split}_chunks.jsonl")
        stats = process_split_chunks(
            input_jsonl=in_file,
            output_jsonl=out_file,
            tokenizer=tokenizer,
            max_length=max_length,
            min_chunk_tokens=min_chunk_tokens
        )
        all_stats[split] = stats

    manifest_path = os.path.join(data_dir, "chunking_manifest.json")
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(all_stats, f, indent=2, ensure_ascii=False)

    print(f"\n[Sukses] Manifest chunking disimpan di: {manifest_path}")
    return all_stats


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Potong korpus dokumen menjadi chunk urutan Mini-BERT")
    parser.add_argument("--data-dir", type=str, default="data/processed/pilot", help="Direktori penyimpanan split")
    parser.add_argument("--max-length", type=int, default=DEFAULT_MAX_LENGTH, help="Panjang maksimum urutan (termasuk [CLS], [SEP])")
    parser.add_argument("--min-chunk-tokens", type=int, default=DEFAULT_MIN_CHUNK_TOKENS, help="Ambang batas token isi untuk tail chunk")
    args = parser.parse_args()

    run_chunking_pipeline(
        data_dir=args.data_dir,
        max_length=args.max_length,
        min_chunk_tokens=args.min_chunk_tokens
    )
