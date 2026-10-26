# Mini-BERT Bahasa Indonesia — Data Pipeline & Preprocessing (Pilot)

Repositori ini memuat implementasi *end-to-end* pipeline data, pembersihan korpus, tokenizer tingkat kata (*word-level*), pembagian partisi deterministik, pemotongan urutan (*sequence chunking*), PyTorch Dataset, MLM Data Collator, dan DataLoader untuk **Mini-BERT Bahasa Indonesia (Masked Language Model)** yang dilatih dari nol (*from scratch*).

---

## 1. Persiapan Lingkungan (*Environment Setup*)

Proyek ini menggunakan Python 3.12. Dependensi dipisahkan menjadi dua berkas modular:

```bash
# 1. Pasang dependensi data pipeline (datasets, pyarrow, fsspec)
pip install -r requirements-data.txt

# 2. Pasang dependensi PyTorch CPU (untuk lingkungan CPU Anggota 1)
pip install -r requirements-pytorch.txt
```

> **Catatan GPU**: Pada laptop training GPU Anggota 2 (RTX 4060 Laptop 8GB VRAM), pasang PyTorch dengan dukungan CUDA melalui perintah resmi:
> `pip install torch --index-url https://download.pytorch.org/whl/cu121`

---

## 2. Cara Memuat Tokenizer, Dataset, Collator, dan DataLoader

```python
import torch
from src.data.tokenizer import WordLevelTokenizer
from src.data.dataset import PrechunkedMLMDataset, MLMDataCollator, get_mlm_dataloader

# 1. Muat Tokenizer
tokenizer = WordLevelTokenizer.from_pretrained("data/processed/pilot")

# 2. Muat Dataset Siap MLM (Otomatis menyaring chunk tanpa target)
train_dataset = PrechunkedMLMDataset("data/processed/pilot/train_chunks.jsonl")
val_dataset = PrechunkedMLMDataset("data/processed/pilot/val_chunks.jsonl")

# 3. Inisialisasi Collator Masking MLM (15% dynamic masking)
train_collator = MLMDataCollator(mode="train", train_seed=42)
val_collator = MLMDataCollator(mode="eval", eval_seed=42)  # Deterministik stabil

# 4. Buat DataLoader (default num_workers=0 untuk Windows)
train_loader = get_mlm_dataloader(train_dataset, batch_size=32, shuffle=True, collator=train_collator)
val_loader = get_mlm_dataloader(val_dataset, batch_size=32, shuffle=False, collator=val_collator)

for batch in train_loader:
    # PERHATIAN PENTING: Batch memuat metadata pelacakan `doc_ids` dan `chunk_indices`.
    # Hanya kirimkan `input_ids` dan `attention_mask` ke forward model!
    input_ids = batch["input_ids"]           # torch.long [32, 64]
    attention_mask = batch["attention_mask"] # torch.long [32, 64]
    labels = batch["labels"]                 # torch.long [32, 64]
    
    # Metadata (JANGAN dikirim ke forward model):
    doc_ids = batch["doc_ids"]               # List of doc IDs
    chunk_indices = batch["chunk_indices"]   # torch.long [32]
    
    # Contoh forward pass (Anggota 2 & 3):
    # logits = model(input_ids=input_ids, attention_mask=attention_mask)
    break
```

---

## 3. Spesifikasi Vocabulary & Parameter Input

- **Ukuran Vocabulary**: **8.000 kata** (termasuk 5 token khusus).
- **SHA-256 Hash Vocabulary**: `8a4ca39b69b596e1a47dfdcb373bf9bcf51e7f603d32ef3c8d45138127027d78`
- **Token Khusus Terkunci**:
  - `[PAD]` = 0
  - `[UNK]` = 1
  - `[CLS]` = 2
  - `[SEP]` = 3
  - `[MASK]` = 4
- **Panjang Urutan (`max_length`)**: **64 token** (1 `[CLS]` + maksimal 62 token isi + 1 `[SEP]`).

---

## 4. Jumlah Dataset Siap MLM Per Split

Dari 3.000 artikel pilot bersih, 9 artikel $< 10$ kata disaring ke manifest eksklusi. Hasil pemotongan sequence menghasilkan:

| Split | Dokumen Sumber | Total Raw Chunks | Chunks Dikeluarkan (0 Target) | **MLM-Ready Chunks** | Total Batch (`batch_size=32`) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| **Train** | 2.393 | 27.002 | 0 | **27.002** | **844 batch** |
| **Validation** | 299 | 2.685 | 0 | **2.685** | **84 batch** |
| **Test** | 299 | 3.427 | 1 (`doc_id=3792`) | **3.426** | **108 batch** |

*Catatan: 1 chunk pada split Test dikeluarkan dari indeks MLM karena seluruh isinya adalah nama Latin langka yang menjadi `[UNK]`, dicatat di `data/processed/pilot/mlm_excluded_chunks_manifest.json`.*

---

## 5. Aturan Masking MLM & Penjaminan Seed

1. **Kandidat Target**: Hanya token reguler non-khusus (ID $\ge 5$). Token khusus `[PAD]`, `[UNK]`, `[CLS]`, `[SEP]`, `[MASK]` tidak pernah menjadi target.
2. **Proporsi Target**: Sekitar **15%** dari kandidat reguler dipilih (minimal 1 target per contoh).
3. **Distribusi Masking (80/10/10)**:
   - 80% diganti dengan `[MASK]` (ID 4).
   - 10% diganti dengan token acak reguler (ID 5..7999).
   - 10% dipertahankan sebagai token asli.
4. **Pemisahan Seed Masking vs Seed Shuffle**:
   - **Seed Shuffle DataLoader** (`torch.manual_seed()`): Mengontrol urutan pengambilan sampel.
   - **Seed Masking Collator** (`train_seed`/`epoch_seed` dan `eval_seed`): Mengontrol token target mana yang dimasking. Keduanya independen.
   - **Mode Train**: Mendukung `collator.set_train_seed(epoch_seed)` untuk variasi dinamis antarepoch namun tetap dapat direproduksi.
   - **Mode Eval**: Menggunakan generator acak lokal berbasis digest SHA-256 dari `f"{eval_seed}_{doc_id}_{chunk_index}"`. Masking evaluasi dijamin 100% deterministik terlepas dari batch size atau urutan batch.

---

## 6. Contoh Batch Aktual Sebelum vs Sesudah Masking

Contoh potongan chunk dari dokumen `doc_id="2716"` (Artikel: *Spanyol*):

```text
Teks Asli:
[CLS] spanyol ( ) , secara resmi dikenal dengan sebutan kerajaan spanyol ...

Teks Setelah Masking MLM:
[CLS] spanyol ( ) , secara resmi [MASK] [MASK] sebutan kerajaan spanyol ...
```

**Rincian Posisi Target dan Label**:
- `Pos  7 | Orig:  172 ('dikenal')   -> Masked:    4 ('[MASK]') | Label:  172  (Kasus 80%)`
- `Pos  8 | Orig:   15 ('dengan')    -> Masked:    4 ('[MASK]') | Label:   15  (Kasus 80%)`
- `Pos 33 | Orig:   15 ('dengan')    -> Masked: 6739 ('padri')   | Label:   15  (Kasus 10% acak)`
- `Pos 54 | Orig:  488 ('kepulauan') -> Masked:  488 ('kepulauan')| Label:  488  (Kasus 10% tetap)`
- Seluruh 55 posisi non-target lainnya memiliki `Label = -100`.

---

## 7. Penjelasan `attention_mask` dan `labels`

- **`attention_mask`**: Tensor `torch.long [B, 64]` bernilai `1` untuk token aktif dan `0` untuk padding `[PAD]`. Masking MLM **tidak mengubah nilai attention mask**.
- **`labels`**: Tensor `torch.long [B, 64]` berisi Token ID asli pada posisi target dan `-100` pada posisi non-target. Pada PyTorch `nn.CrossEntropyLoss(ignore_index=-100)`, posisi bernilai `-100` diabaikan sehingga gradient hanya dihitung pada posisi token yang dimasking.

---

## 8. Paket Lengkap Berkas Serah Terima Anggota 1

Untuk melanjutkan pengujian integrasi bersama arsitektur Mini-BERT (Anggota 2) dan training loop (Anggota 3):

1. **Modul Kode Inti (`src/data/`)**:
   - `src/data/cleaner.py` (Cleaner v1.1.0, idempotensi 100%)
   - `src/data/tokenizer.py` (`WordLevelTokenizer`)
   - `src/data/chunker.py` (Sequence chunker max_length=64)
   - `src/data/split_dataset.py` (Partisi dokumen 80/10/10)
   - `src/data/dataset.py` (`PrechunkedMLMDataset`, `MLMDataCollator`, `get_mlm_dataloader`)
2. **Artefak Tokenizer & Data Pre-chunked (`data/processed/pilot/`)**:
   - `vocab.json` (8.000 kata)
   - `tokenizer_config.json` (Konfigurasi & hash)
   - `train_chunks.jsonl` (27.002 chunks)
   - `val_chunks.jsonl` (2.685 chunks)
   - `test_chunks.jsonl` (3.427 chunks)
3. **Manifest Pelacakan Data**:
   - `data/pilot/excluded_articles_manifest.json` (9 artikel $< 10$ kata)
   - `data/processed/pilot/split_manifest.json` (Partisi & bukti 0 kebocoran leksikal)
   - `data/processed/pilot/chunking_manifest.json` (Statistik sequence chunking)
   - `data/processed/pilot/mlm_excluded_chunks_manifest.json` (1 chunk 0 target)
4. **Konfigurasi Dependensi Lingkungan**:
   - `requirements-data.txt` (Dependensi data dasar)
   - `requirements-pytorch.txt` (Khusus PyTorch CPU Anggota 1; Anggota 2 memasang versi CUDA mandiri)
5. **Rangkaian Pengujian Unit Otomatis (36 Tests Lolos)**:
   - `tests/test_cleaner.py`
   - `tests/test_sampling_logic.py`
   - `tests/test_tokenizer_and_pipeline.py`
   - `tests/test_dataset_and_collator.py`
6. **Dokumentasi & Arsip Percakapan AI Asli**:
   - `docs/data_contract_pilot.md` (Dokumen kontrak data v1.1.0)
   - `docs/log_interaksi_tahap1.md` s/d `tahap5.md`
   - `docs/ai_interaction_transcript.jsonl` (Arsip transkrip JSONL asli 736 KB)
   - `docs/ai_interaction_transcript_full.jsonl` (Arsip transkrip lengkap 1.104 KB)

---

## 9. Menjalankan Seluruh Pengujian Unit (*Unit Tests*)

Repositori ini dilengkapi dengan 36 unit test otomatis:

```bash
.\.venv\Scripts\python.exe -m unittest discover tests
# Ran 36 tests in ~4.0s - OK
```

---

## 10. Batasan Korpus Pilot

- Dataset 3.000 artikel ini bertujuan memvalidasi kebenaran pipeline data secara *end-to-end*. Korpus ini **bukan sampel representatif seluruh Wikipedia Bahasa Indonesia**.
- Tokenizer berbasis kata menghasilkan UNK rate ~12,6% pada validasi, yang memadai untuk pilot namun dapat dievaluasi menggunakan subword (BPE/WordPiece) untuk dataset skala penuh.
- Panjang urutan awal dikunci pada `max_length = 64` untuk efisiensi komputasi awal.
