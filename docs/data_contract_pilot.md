# Kontrak Data, Tokenizer, dan DataLoader Pilot (Mini-BERT Bahasa Indonesia)

**Versi Kontrak**: 1.1.0 (Final Handover Anggota 1 — Siap Pelatihan Model)  
**Tanggal**: 23 Oktober 2026  
**Penanggung Jawab**: Anggota 1 (Data Pipeline & Preprocessing Engineer)  
**Penerima Manfaat**: Anggota 2 (Arsitektur Model & Hardware Lead) & Anggota 3 (Training Loop & Evaluasi Lead)  
**Status**: Lengkap & Terverifikasi (*Production-Ready Baseline*)

---

## 1. Panduan Menyiapkan Lingkungan (*Environment Setup*)

Pekerjaan data pipeline Anggota 1 dikembangkan dan diuji secara independen pada CPU menggunakan dependensi terpisah:

1. **Dependensi Data Dasar** ([`requirements-data.txt`](file:///c:/Semester%207/GEN%20AI/MIDTERM/KELOMPOK%207/requirements-data.txt)):
   ```bash
   pip install -r requirements-data.txt
   # datasets==5.1.0, pyarrow==26.0.0, fsspec==2026.7.0
   ```
2. **Dependensi PyTorch CPU Anggota 1** ([`requirements-pytorch.txt`](file:///c:/Semester%207/GEN%20AI/MIDTERM/KELOMPOK%207/requirements-pytorch.txt)):
   ```bash
   pip install -r requirements-pytorch.txt
   # torch==2.14.1+cpu
   ```
   > **Catatan Hardware**: Perangkat Anggota 1 murni menggunakan PyTorch CPU. Anggota 2 dan 3 yang mengeksekusi pelatihan pada laptop GPU (RTX 4060 Laptop 8GB VRAM) dapat memasang `torch` dengan dukungan CUDA (`cu121`/`cu124`) tanpa perlu mengubah kode pipeline data ini sama sekali.

---

## 2. Lokasi Berkas dan Inventaris Artefak

Semua berkas hasil pemrosesan tersimpan pada direktori deterministik berikut:

```text
data/
├── pilot/
│   ├── wiki_pilot_3000.jsonl                   # Data mentah pilot (3.000 artikel, 12,98 MB)
│   ├── wiki_pilot_3000_cleaned.jsonl           # Data bersih Cleaner v1.1.0 (3.000 artikel, 13,60 MB)
│   └── excluded_articles_manifest.json         # Manifest 9 artikel < 10 kata yang dikeluarkan
└── processed/
    └── pilot/
        ├── train.jsonl                         # Dokumen split train (2.393 artikel)
        ├── val.jsonl                           # Dokumen split val (299 artikel)
        ├── test.jsonl                          # Dokumen split test terkunci (299 artikel)
        ├── split_manifest.json                 # Manifest partisi & verifikasi pemeriksaan kebocoran
        ├── train_chunks.jsonl                  # Chunks train (27.002 sampel, max_length=64)
        ├── val_chunks.jsonl                    # Chunks val (2.685 sampel, max_length=64)
        ├── test_chunks.jsonl                   # Chunks test (3.427 sampel, max_length=64)
        ├── chunking_manifest.json              # Manifest pemotongan dan penanganan sisa chunk
        ├── mlm_excluded_chunks_manifest.json   # Manifest 1 chunk test tanpa target yang dikeluarkan
        ├── vocab.json                          # Mapping kata -> ID (8.000 entri)
        └── tokenizer_config.json               # Konfigurasi, aturan tokenisasi, dan hash
```

---

## 3. Spesifikasi Vocabulary dan Token Khusus

Vocabulary dibangun **secara eksklusif hanya dari split Train** dengan aturan deterministik (frekuensi menurun, lalu urutan alfabetis leksikografis untuk frekuensi sama).

- **Ukuran Vocabulary Aktual**: **8.000 token** (termasuk 5 token khusus).
- **SHA-256 Hash Vocabulary**: `8a4ca39b69b596e1a47dfdcb373bf9bcf51e7f603d32ef3c8d45138127027d78`
- **Mapping Token Khusus**:
  | Token Khusus | Token ID | Deskripsi Fungsional |
  | :--- | :---: | :--- |
  | `[PAD]` | **0** | Padding untuk menyamakan panjang batch hingga `max_length`. |
  | `[UNK]` | **1** | Unknown token untuk kata di luar vocabulary. |
  | `[CLS]` | **2** | Classification token di awal urutan sequence. |
  | `[SEP]` | **3** | Separator token di akhir urutan sequence. |
  | `[MASK]` | **4** | Masking target untuk tugas Masked Language Model (MLM). |

- **Validasi Ketat Integritas Artefak**:
  Kelas `WordLevelTokenizer` secara otomatis memvalidasi bahwa seluruh ID adalah integer non-negatif, kontigu $0 \dots 7.999$, seluruh 5 token khusus ada dengan ID yang tepat, dan menolak artefak cacat dengan pesan `ValueError` tanpa melakukan koreksi mapping diam-diam.

---

## 4. Partisi Dokumen & Hasil Pemeriksaan Kebocoran (*Leakage Check*)

- **Penyaringan Artikel Layak**: Dari 3.000 artikel pilot bersih, 9 artikel dengan $< 10$ kata berbasis spasi dikeluarkan ke manifest eksklusi tanpa menghapus rekaman dari data sumber. Tersisa **2.991 artikel layak**.
- **Hasil Pemeriksaan Kebocoran Spesifik**:
  - Irisan ID Dokumen Train–Val: **0**
  - Irisan ID Dokumen Train–Test: **0**
  - Irisan ID Dokumen Val–Test: **0**
  - Irisan Hash SHA-256 Teks Normalisasi (lowercase, NFC, tanda baca diabaikan) antarsplit: **0**
  - *Keterbatasan Empiris*: Pemeriksaan ini membuktikan tidak ada duplikasi leksikal persis antarpartisi. Namun, metode ini **tidak mendeteksi near-duplicate** (dokumen dengan sedikit variasi kata/kalimat), parafrasa, atau kutipan berulang sebagian.

---

## 5. Jumlah Dataset Siap MLM (*MLM-Ready Chunks*)

Pemeriksaan integritas mendalam menemukan **1 chunk** pada split test (`doc_id="3792"`, `chunk_index=3`, artikel *"Daftar hewan purbakala"*) yang seluruh token isinya merupakan nama genus Latin langka yang tidak ada dalam vocabulary train, sehingga seluruhnya dipetakan ke `[UNK]`. 

Sesuai aturan bahwa kandidat target MLM harus berupa token reguler non-khusus (ID $\ge 5$), chunk tersebut memiliki **0 kandidat target**. Chunk ini secara elegan **dikeluarkan dari indeks PyTorch Dataset siap MLM** dan dicatat dalam [`mlm_excluded_chunks_manifest.json`](file:///c:/Semester%207/GEN%20AI/MIDTERM/KELOMPOK%207/data/processed/pilot/mlm_excluded_chunks_manifest.json), sementara berkas JSONL sumber tetap utuh:

| Split | Raw Chunks | Chunks Dikeluarkan (0 Target) | **MLM-Ready Chunks** | Total Batch Pelatihan (`batch_size=32`) |
| :--- | :---: | :---: | :---: | :---: |
| **Train** | 27.002 | 0 | **27.002** | **844 batch** |
| **Validation** | 2.685 | 0 | **2.685** | **84 batch** |
| **Test** | 3.427 | 1 (`doc_id=3792`) | **3.426** | **108 batch** |

---

## 6. Kontrak Batch dan Aturan Masking MLM (`MLMDataCollator`)

### A. Kontrak Bentuk dan Tipe Data Tensor
Setiap batch yang dihasilkan oleh `MLMDataCollator` memiliki bentuk tensor dan dtype sebagai berikut:
- **`input_ids`**: `torch.long [B, 64]` — Token sequence yang telah dimasking.
- **`attention_mask`**: `torch.long [B, 64]` — Bernilai **1** untuk token aktif (`[CLS]`, kata, `[SEP]`, `[MASK]`) dan **0** untuk padding `[PAD]`. **Nilai attention mask tidak pernah berubah akibat masking**.
- **`labels`**: `torch.long [B, 64]` — Bernilai **Token ID asli** pada setiap posisi target yang dipilih, dan **-100** pada semua posisi lainnya.

### B. Aturan Pemilihan Target Masking
1. **Kandidat Target**: Hanya token reguler yang valid dengan ID $\ge 5$. Token khusus (`[PAD]=0`, `[UNK]=1`, `[CLS]=2`, `[SEP]=3`, `[MASK]=4`) **tidak pernah menjadi target**.
2. **Proporsi Target**: Sekitar **15%** dari kandidat token reguler dipilih secara acak tanpa pengembalian.
3. **Batas Minimum**: Jika sebuah sampel memiliki kandidat reguler, minimal **1 target** dipastikan terpilih.
4. **Distribusi Penggantian Target (Aturan 80/10/10)**:
   - **80%**: Diganti dengan token `[MASK]` (ID=4).
   - **10%**: Diganti dengan token acak reguler non-khusus (ID $5 \dots 7.999$).
   - **10%**: Dipertahankan sebagai token asli.
5. **Integritas Label**: Target yang dipertahankan atau kebetulan diganti dengan token yang sama **tetap memiliki label berupa Token ID aslinya** (loss tetap dihitung).

### C. Mekanisme Reproduksibilitas dan Penjaminan Seed
- **Pemisahan Seed Masking vs Seed Shuffle**:
  * **Seed Shuffle DataLoader** (`torch.manual_seed()` atau generator PyTorch): Hanya mengontrol permutasi urutan pengambilan sampel (`shuffle=True`).
  * **Seed Masking Collator** (`train_seed`/`epoch_seed` via `set_train_seed()` dan `eval_seed`): Mengontrol pemilihan token mana yang dimasking serta token penggantinya.
  * Kedua seed ini **terpisah dan independen**. Mengubah urutan batch tidak akan mengubah hasil masking evaluasi.
- **Mode Pelatihan (`mode='train'`)**: Masking dapat bervariasi antarepoch untuk memperkaya variasi konteks. Metode `collator.set_train_seed(epoch_seed)` disediakan agar eksperimen training dapat direproduksi 100% jika seed dan urutan batch sama.
- **Mode Evaluasi (`mode='eval'`)**: Masking bersifat **deterministik mutlak**. Generator acak tiap sampel diinisialisasi menggunakan digest SHA-256 dari kunci unik:
  $$\text{seed} = \text{SHA256}(f"{eval\_seed}\_{doc\_id}\_{chunk\_index}")[:8]$$
  Hal ini menjamin masking evaluasi pada setiap artikel selalu **100% identik**, tidak peduli berapa ukuran `batch_size`, apakah data diacak (*shuffle*), atau berapa nomor *worker* yang memprosesnya.
- **Dukungan Multiworker**: Direkomendasikan `num_workers=0` untuk stabilitas proses pada Windows OS.

---

## 7. Contoh Batch Aktual Sebelum vs Sesudah Masking

Berikut adalah keluaran aktual dari evaluasi chunk `doc_id="2716"`, `chunk_index=0` (Artikel: *Spanyol*):

```text
Teks Asli (Decoded):
[CLS] spanyol ( ) , secara resmi dikenal dengan sebutan kerajaan spanyol ...

Teks Setelah Masking (Decoded):
[CLS] spanyol ( ) , secara resmi [MASK] [MASK] sebutan kerajaan spanyol ...
```

**Rincian Posisi Target dan Label**:
```text
Posisi Target (9 token terpilih dari 62 token isi ≈ 14.5%):
- Pos  7 | Token Asli:  172 ('dikenal')   -> Masked:    4 ('[MASK]') | Label:  172  (Kasus 80%)
- Pos  8 | Token Asli:   15 ('dengan')    -> Masked:    4 ('[MASK]') | Label:   15  (Kasus 80%)
- Pos 17 | Token Asli:   10 ('di')        -> Masked:    4 ('[MASK]') | Label:   10  (Kasus 80%)
- Pos 23 | Token Asli: 1742 ('portugal')  -> Masked:    4 ('[MASK]') | Label: 1742  (Kasus 80%)
- Pos 25 | Token Asli:  104 ('terdapat')  -> Masked:    4 ('[MASK]') | Label:  104  (Kasus 80%)
- Pos 32 | Token Asli:  979 ('spanyol')   -> Masked:    4 ('[MASK]') | Label:  979  (Kasus 80%)
- Pos 33 | Token Asli:   15 ('dengan')    -> Masked: 6739 ('padri')   | Label:   15  (Kasus 10% acak)
- Pos 54 | Token Asli:  488 ('kepulauan') -> Masked:  488 ('kepulauan')| Label:  488  (Kasus 10% tetap)
- Pos 61 | Token Asli:  151 ('berbagai')  -> Masked:    4 ('[MASK]') | Label:  151  (Kasus 80%)

Posisi Lainnya (55 posisi non-target):
- Posisi 0 ([CLS]), Posisi 63 ([SEP]), dan 53 token kata non-target memiliki Label = -100.
```

---

## 8. Contoh Kode Pemanggilan Lengkap (Untuk Anggota 2 & 3)

```python
import torch
import torch.nn as nn
from src.data.dataset import PrechunkedMLMDataset, MLMDataCollator, get_mlm_dataloader
from src.data.tokenizer import WordLevelTokenizer

# 1. Muat Tokenizer
tokenizer = WordLevelTokenizer.from_pretrained("data/processed/pilot")
print(f"Vocab size: {tokenizer.vocab_size}")  # 8000

# 2. Inisialisasi Dataset Siap MLM
train_dataset = PrechunkedMLMDataset(
    jsonl_path="data/processed/pilot/train_chunks.jsonl",
    vocab_size=8000,
    max_length=64,
    filter_zero_candidates=True
)
val_dataset = PrechunkedMLMDataset(
    jsonl_path="data/processed/pilot/val_chunks.jsonl",
    vocab_size=8000,
    max_length=64,
    filter_zero_candidates=True
)

# 3. Inisialisasi Collator Masking
train_collator = MLMDataCollator(vocab_size=8000, mode="train", train_seed=42)
val_collator = MLMDataCollator(vocab_size=8000, mode="eval", eval_seed=42)

# 4. Inisialisasi DataLoader
train_loader = get_mlm_dataloader(train_dataset, batch_size=32, shuffle=True, collator=train_collator)
val_loader = get_mlm_dataloader(val_dataset, batch_size=32, shuffle=False, collator=val_collator)

# 5. Contoh Iterasi dan Perhitungan Loss Mini-BERT
loss_fn = nn.CrossEntropyLoss(ignore_index=-100)

for batch in train_loader:
    # PERHATIAN PENTING: Batch memuat metadata `doc_ids` dan `chunk_indices`.
    # Hanya kirimkan `input_ids` dan `attention_mask` ke forward model!
    input_ids = batch["input_ids"]           # torch.long [32, 64]
    attention_mask = batch["attention_mask"] # torch.long [32, 64]
    labels = batch["labels"]                 # torch.long [32, 64]
    
    # Metadata pelacakan (JANGAN dikirim ke forward model):
    doc_ids = batch["doc_ids"]               # List of doc IDs
    chunk_indices = batch["chunk_indices"]   # torch.long [32]
    
    # Model forward pass (oleh Anggota 2 & 3):
    # logits = model(input_ids=input_ids, attention_mask=attention_mask)  # [32, 64, 8000]
    # loss = loss_fn(logits.view(-1, 8000), labels.view(-1))
    break
```

---

## 9. Paket Lengkap Berkas Serah Terima Anggota 1

Seluruh paket serah terima data dan kode tersimpan lengkap dan siap pakai:

1. **Kode Sumber Inti (`src/data/`)**:
   - [`src/data/cleaner.py`](file:///c:/Semester%207/GEN%20AI/MIDTERM/KELOMPOK%207/src/data/cleaner.py) (Pembersih korpus v1.1.0, idempotensi 100%)
   - [`src/data/tokenizer.py`](file:///c:/Semester%207/GEN%20AI/MIDTERM/KELOMPOK%207/src/data/tokenizer.py) (`WordLevelTokenizer`, validasi integritas ketat)
   - [`src/data/chunker.py`](file:///c:/Semester%207/GEN%20AI/MIDTERM/KELOMPOK%207/src/data/chunker.py) (Pemotong urutan non-overlapping max_length=64)
   - [`src/data/split_dataset.py`](file:///c:/Semester%207/GEN%20AI/MIDTERM/KELOMPOK%207/src/data/split_dataset.py) (Partisi dokumen deterministik 80/10/10)
   - [`src/data/dataset.py`](file:///c:/Semester%207/GEN%20AI/MIDTERM/KELOMPOK%207/src/data/dataset.py) (`PrechunkedMLMDataset`, `MLMDataCollator`, `get_mlm_dataloader`)
2. **Artefak Tokenizer & Data Pre-chunked (`data/processed/pilot/`)**:
   - `vocab.json` (8.000 kata, SHA-256: `8a4ca39b69b596e1a47dfdcb373bf9bcf51e7f603d32ef3c8d45138127027d78`)
   - `tokenizer_config.json` (Konfigurasi aturan normalisasi, batas panjang, dan hash)
   - `train_chunks.jsonl` (27.002 chunks siap latih)
   - `val_chunks.jsonl` (2.685 chunks siap evaluasi)
   - `test_chunks.jsonl` (3.427 chunks uji terkunci)
3. **Manifest Pelacakan Lengkap**:
   - [`data/pilot/excluded_articles_manifest.json`](file:///c:/Semester%207/GEN%20AI/MIDTERM/KELOMPOK%207/data/pilot/excluded_articles_manifest.json) (9 artikel sumber $< 10$ kata yang dikeluarkan)
   - [`data/processed/pilot/split_manifest.json`](file:///c:/Semester%207/GEN%20AI/MIDTERM/KELOMPOK%207/data/processed/pilot/split_manifest.json) (Manifest partisi dan bukti 0 kebocoran ID/hash)
   - [`data/processed/pilot/chunking_manifest.json`](file:///c:/Semester%207/GEN%20AI/MIDTERM/KELOMPOK%207/data/processed/pilot/chunking_manifest.json) (Statistik pemotongan urutan dan sisa chunk dibuang)
   - [`data/processed/pilot/mlm_excluded_chunks_manifest.json`](file:///c:/Semester%207/GEN%20AI/MIDTERM/KELOMPOK%207/data/processed/pilot/mlm_excluded_chunks_manifest.json) (1 chunk test tanpa target yang dikeluarkan)
4. **Rangkaian Pengujian Unit Otomatis (36 Tests Lolos)**:
   - `tests/test_cleaner.py` (13 tes)
   - `tests/test_sampling_logic.py` (4 tes)
   - `tests/test_tokenizer_and_pipeline.py` (8 tes)
   - `tests/test_dataset_and_collator.py` (11 tes)
5. **Konfigurasi Dependensi Lingkungan**:
   - [`requirements-data.txt`](file:///c:/Semester%207/GEN%20AI/MIDTERM/KELOMPOK%207/requirements-data.txt) (Dependensi dasar)
   - [`requirements-pytorch.txt`](file:///c:/Semester%207/GEN%20AI/MIDTERM/KELOMPOK%207/requirements-pytorch.txt) (Dependensi PyTorch CPU Anggota 1)
6. **Dokumentasi & Arsip Percakapan AI Asli**:
   - [`README.md`](file:///c:/Semester%207/GEN%20AI/MIDTERM/KELOMPOK%207/README.md) (Panduan ringkas serah terima)
   - [`docs/data_contract_pilot.md`](file:///c:/Semester%207/GEN%20AI/MIDTERM/KELOMPOK%207/docs/data_contract_pilot.md) (Kontrak data ini)
   - [`docs/log_interaksi_tahap1.md`](file:///c:/Semester%207/GEN%20AI/MIDTERM/KELOMPOK%207/docs/log_interaksi_tahap1.md) s/d [`tahap5.md`](file:///c:/Semester%207/GEN%20AI/MIDTERM/KELOMPOK%207/docs/log_interaksi_tahap5.md)
   - [`docs/ai_interaction_transcript.jsonl`](file:///c:/Semester%207/GEN%20AI/MIDTERM/KELOMPOK%207/docs/ai_interaction_transcript.jsonl) (Arsip transkrip JSONL percakapan AI 736 KB)
   - [`docs/ai_interaction_transcript_full.jsonl`](file:///c:/Semester%207/GEN%20AI/MIDTERM/KELOMPOK%207/docs/ai_interaction_transcript_full.jsonl) (Arsip transkrip lengkap 1.104 KB)

---

## 10. Batasan dan Keputusan yang Masih Bersifat Sementara

1. **Skala Korpus Pilot**: Dataset 3.000 artikel ini bertujuan memvalidasi pipeline secara *end-to-end*. **Bukan sampel representatif seluruh Wikipedia Bahasa Indonesia**, dan bukan jaminan performa model akhir.
2. **Word-Level Tokenizer**: Dipilih sebagai baseline deterministik untuk proyek awal. Tingkat UNK pada validasi adalah ~12,6%. Jika nantinya dibutuhkan representasi subkata, WordPiece/BPE dapat dieksplorasi pada dataset final.
3. **Sequence Length (`max_length = 64`)**: Ditentukan agar pelatihan Mini-BERT ringan pada CPU dan sangat cepat pada GPU RTX 4060 Laptop milik Anggota 2. Dapat dinaikkan ke 128 jika diperlukan konteks lebih panjang.
4. **Multiworker DataLoader**: Default `num_workers=0` direkomendasikan untuk sistem operasi Windows karena keterbatasan proses fork bawaan OS.

