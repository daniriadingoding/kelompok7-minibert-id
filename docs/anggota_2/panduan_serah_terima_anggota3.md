# PANDUAN SERAH TERIMA ARSITEKTUR MODEL (ANGGOTA 2 KE ANGGOTA 3)

* Tanggal Dokumen: 23 Oktober 2026
* Penulis: Anggota 2 (Arsitektur Model & Hardware Lead)
* Penerima: Anggota 3 (Training Loop & Evaluasi Lead)
* Repositori: Proyek 1 Generative AI (Kelompok 7, Mini-BERT Bahasa Indonesia dari Nol)
* Status Arsitektur: Selesai 100%, 79/79 Unit Test Lolos, Siap Pelatihan Penuh

---

## 1. Arsitektur Model dan Jumlah Parameter Unik

Model yang diserahkan adalah arsitektur **Mini-BERT Masked Language Model (MLM)** encoder-only yang dibangun sepenuhnya dari primitif PyTorch (`nn.Linear`, `nn.Embedding`, `nn.LayerNorm`, `nn.Dropout`, dan kalkulasi tensor manual) tanpa memanfaatkan modul kemasan eksternal seperti `BertModel`, `BertForMaskedLM`, `nn.TransformerEncoder`, atau `nn.MultiheadAttention`.

### Struktur Komponen Arsitektur:
1. **BertEmbeddings**:
   - `word_embeddings`: `nn.Embedding(8000, 128, padding_idx=0)`
   - `position_embeddings`: `nn.Embedding(64, 128)`
   - `LayerNorm`: `nn.LayerNorm(128, eps=1e-12)`
   - `Dropout`: `nn.Dropout(p=0.1)`
2. **BertEncoder (2 Layer Transformer Post-LayerNorm)**:
   - Setiap layer terdiri dari `MultiHeadSelfAttention` (4 heads, `head_dim=32`) dan `PositionwiseFeedForward` (`128 -> 512 -> 128` dengan aktivasi GELU).
   - Skema Post-LayerNorm: `x = LayerNorm(x + Dropout(Sublayer(x)))`.
   - Perhitungan atensi menggunakan `scores.masked_fill(key_padding_mask, -10000.0)` untuk menjamin probabilitas atensi pada token padding tepat 0.0 secara stabil.
3. **BertMLMHead**:
   - Proyeksi antara: `Linear(128, 128) -> GELU -> LayerNorm(128, eps=1e-12)`
   - Proyeksi vocabulary: `decoder = Linear(128, 8000)` dengan bias output berdimensi 8.000.

### Weight Tying dan Penghitungan Parameter Unik:
Matriks bobot decoder diikat (*tied*) ke matriks bobot word embeddings:
```python
model.cls.decoder.weight = model.embeddings.word_embeddings.weight
```
Dengan ikatan ini, parameter proyeksi 8.000 x 128 (1.024.000 float) berbagi memori fisik yang sama dan tidak dihitung ganda.

| Komponen | Spesifikasi Teknis | Jumlah Parameter |
| :--- | :--- | :---: |
| Word Embeddings | 8000 x 128 | 1.024.000 |
| Positional Embeddings | 64 x 128 | 8.192 |
| Embedding LayerNorm | gamma & beta (128) | 256 |
| Layer 1 Attention | Q, K, V, Out (4 x [128 x 128 + 128]) | 66.048 |
| Layer 1 Attention LN | gamma & beta (128) | 256 |
| Layer 1 FFN | Dense1 (128x512+512) + Dense2 (512x128+128) | 131.584 |
| Layer 1 FFN LN | gamma & beta (128) | 256 |
| Layer 2 Attention | Q, K, V, Out (4 x [128 x 128 + 128]) | 66.048 |
| Layer 2 Attention LN | gamma & beta (128) | 256 |
| Layer 2 FFN | Dense1 (128x512+512) + Dense2 (512x128+128) | 131.584 |
| Layer 2 FFN LN | gamma & beta (128) | 256 |
| MLM Head Transform | Linear 128 x 128 + 128 | 16.512 |
| MLM Head LN | gamma & beta (128) | 256 |
| Output Decoder Bias | Vector 8000 | 8.000 |
| **Total Parameter Unik** | **Seluruh Model Mini-BERT** | **1.453.760** |

Catatan Perilaku Bobot PAD:
Karena weight tying mengikat word embeddings dengan decoder logits pada 8.000 kelas, proses backward softmax pada posisi target yang dimasking akan mengalirkan gradien pembaruan ke seluruh baris vocabulary, termasuk baris indeks 0 (`[PAD]`). Hal ini wajar dan merupakan karakteristik alami dari weight tying.

---

## 2. Konfigurasi dan Hash Vocabulary yang Berlaku

Seluruh arsitektur diatur melalui kelas [`MiniBertConfig`](file:///C:/Users/DANI/Documents/Kuliah/Semester%207/Generative%20AI/Mid%20Project/KELOMPOK%207/src/models/config.py#L14).

### Parameter Hyperparameter Resmi:
```python
from src.models.config import MiniBertConfig

config = MiniBertConfig(
    vocab_size=8000,
    pad_token_id=0,
    d_model=128,
    num_layers=2,
    num_heads=4,
    d_ff=512,
    max_position_embeddings=64,
    dropout=0.1,
    attention_dropout=0.1,
    layer_norm_eps=1e-12,
    initializer_range=0.02,
    vocab_sha256="d2be29d07e76fe0cd15c3fe1b765325a5397a5e5fe30b2c6a5a019c976c552f2"
)
```

### Hash Vocabulary Kanonikal:
* **Nilai Sah**: `d2be29d07e76fe0cd15c3fe1b765325a5397a5e5fe30b2c6a5a019c976c552f2`
* Nilai ini adalah hasil hash SHA-256 kanonikal dari berkas `data/processed/pilot/vocab.json`.
* Telah diverifikasi deterministik terhadap 33.114 chunk dataset (27.002 Train, 2.685 Val, 3.427 Test) dengan tingkat kecocokan 100%.
* Jika memuat model dari tokenizer, gunakan:
```python
config = MiniBertConfig.from_tokenizer_directory("data/processed/pilot")
```

---

## 3. Contoh Forward Pass dan Perhitungan Loss

### Penanganan Batch DataLoader:
Kamus batch yang dihasilkan oleh `MLMDataCollator` Anggota 1 memuat 5 kunci:
1. `input_ids`: Tensor long berukuran `[B, L]`
2. `attention_mask`: Tensor long berukuran `[B, L]` (nilai 1 untuk token isi, 0 untuk padding)
3. `labels`: Tensor long berukuran `[B, L]` (berisi token ID asli pada posisi target masked, dan -100 pada posisi lainnya)
4. `doc_ids`: Metadata pelacakan (daftar ID string/int)
5. `chunk_indices`: Metadata pelacakan (daftar indeks)

> **Peringatan Penting**:
> Jangan memanggil `model(**batch)` secara langsung. Masukkan hanya `input_ids` dan `attention_mask` ke dalam model.

### Kode Eksekusi Forward dan Loss:
```python
import torch
import torch.nn as nn
from src.models.bert import MiniBertForMaskedLM
from src.models.config import MiniBertConfig

# 1. Pindahkan tensor ke GPU jika tersedia
device = torch.device("cuda" if torch.cuda.is_available() else "cpu")

input_ids = batch["input_ids"].to(device)
attention_mask = batch["attention_mask"].to(device)
labels = batch["labels"].to(device)

# 2. Forward pass menghasilkan raw logits
# Bentuk logits: [batch_size, seq_len, 8000]
logits = model(input_ids=input_ids, attention_mask=attention_mask)

# 3. Perhitungan CrossEntropyLoss dengan mengabaikan indeks -100
loss_fn = nn.CrossEntropyLoss(ignore_index=-100)
loss = loss_fn(logits.view(-1, config.vocab_size), labels.view(-1))

# 4. Backward pass
loss.backward()
```

---

## 4. Cara Menyimpan dan Memuat Checkpoint (Save & Load)

Prosedur pemuatan checkpoint pada [`MiniBertForMaskedLM`](file:///C:/Users/DANI/Documents/Kuliah/Semester%207/Generative%20AI/Mid%20Project/KELOMPOK%207/src/models/bert.py#L21) telah diperkuat secara ketat:
1. Memeriksa keberadaan dan kelengkapan dictionary `"config"` di dalam `model.pt`, serta mencocokkan seluruh field konfigurasi dengan `config.json`.
2. Menolak checkpoint jika dictionary config hilang, bukan dictionary, terdapat field yang dihapus, terdapat field asing, atau nilainya tidak cocok dengan `config.json`.
3. Memeriksa kecocokan hash vocabulary antara checkpoint dan direktori tokenizer aktif.
4. Menolak checkpoint dengan hash kosong atau konfigurasi tertukar.
5. Menjalankan `load_state_dict(..., strict=True)` dan menjamin weight tying tetap aktif setelah pemuatan.
6. Mengekstrak metadata `checkpoint_status` ('random_init', 'trained', atau 'unknown').

### Cara Menyimpan Checkpoint:
```python
# 1. Menyimpan checkpoint smoke test / baseline acak (Anggota 2):
model.save_pretrained("scratch/random_init_smoke_test", filename="model.pt", checkpoint_status="random_init")

# 2. Menyimpan checkpoint hasil training (Wajib diterapkan oleh Anggota 3):
model.save_pretrained("checkpoints/best_model", filename="model.pt", checkpoint_status="trained")
```

### Cara Memuat Checkpoint:
```python
# Memuat checkpoint tervalidasi dengan tokenizer
loaded_model = MiniBertForMaskedLM.from_pretrained(
    "checkpoints/best_model",
    filename="model.pt",
    tokenizer_dir="data/processed/pilot",
    require_tokenizer=True,
    device=device
)
print("Status Checkpoint:", loaded_model.checkpoint_status)
```

> **Catatan untuk Checkpoint Training Penuh**:
> `save_pretrained` di atas dirancang untuk bobot arsitektur model dan metadata status. Untuk keperluan melanjutkan proses training (checkpointing perulangan epoch), Anggota 3 disarankan menyimpan berkas kamus terpisah yang memuat `model_state_dict`, `optimizer_state_dict`, `scheduler_state_dict`, dan nomor epoch.

---

## 5. Perintah Menjalankan Inferensi

Tersedia antarmuka baris perintah (CLI) dan fungsi modular pada [`src/models/predict.py`](file:///C:/Users/DANI/Documents/Kuliah/Semester%207/Generative%20AI/Mid%20Project/KELOMPOK%207/src/models/predict.py):

### Perintah CLI:
```bash
# Menjalankan inferensi pada GPU
python -m src.models.predict --checkpoint-dir scratch/random_init_smoke_test --tokenizer-dir data/processed/pilot --text "Presiden [MASK] meresmikan jembatan baru di Jawa Timur." --top-k 5 --device cuda
```

### Karakteristik Inferensi:
* Mendukung token `[MASK]` maupun `[mask]` huruf kecil.
* Menolak masukan tanpa `[MASK]`.
* Menolak masukan yang melebihi kapasitas maksimum 64 token dengan pesan jelas.
* Menghitung probabilitas absolut melalui softmax ke seluruh 8.000 vocabulary.
* Token khusus (ID 0..4: `[PAD]`, `[UNK]`, `[CLS]`, `[SEP]`, `[MASK]`) dikecualikan dari pemeringkatan top-k tanpa normalisasi ulang, sehingga nilai probabilitas yang ditampilkan mencerminkan proporsi absolut terhadap seluruh vocabulary.
* Untuk beberapa `[MASK]` dalam satu kalimat, prediksi setiap posisi dihitung secara independen dari konteks kalimat yang sama (bukan autoregressive atau join probability).
* Melaporkan jumlah token `[UNK]` pada input agar keterbatasan vocabulary terlihat transparan.

---

## 6. Status Model Saat Ini (Untrained Baseline)

* **Kondisi Bobot**: Model yang ada saat ini merupakan **model acak baru diinisialisasi (untrained baseline)** dengan bobot berdistribusi normal $\mathcal{N}(0, 0.02^2)$.
* **Nilai Loss Awal**: Loss terukur pada batch riil adalah ~9.01, konsisten dengan batas acak teoritis $\ln(8000) \approx 8.987$.
* **Karakteristik Output**: Prediksi kata dari skrip inferensi pada tahap ini masih menghasilkan kata acak. Model belum memiliki kemampuan bahasa alami sebelum Anggota 3 melatih bobotnya pada dataset pilot.

---

## 7. Lingkungan Eksekusi dan Dependensi Aktual

Lingkungan kerja lokal telah diverifikasi dan siap digunakan untuk pelatihan:
* **Perangkat Keras**: Laptop Lenovo Legion Slim 5 (NVIDIA GeForce RTX 4060 Laptop GPU, 8.188 MiB VRAM).
* **Driver GPU**: NVIDIA Driver versi 617.42.
* **Sistem Operasi**: Windows 11 Home 64-bit.
* **Interpreter**: Python 3.13.2 pada `.venv-gpu` (`C:\Users\DANI\Documents\Kuliah\Semester 7\Generative AI\Mid Project\KELOMPOK 7\.venv-gpu\Scripts\python.exe`).
* **PyTorch**: Versi 2.6.0+cu124 (dibangun dengan CUDA runtime PyTorch 12.4).
* **Dependensi Data**: `datasets==5.1.0`, `pyarrow==26.0.0`, `fsspec==2026.7.0`.
* Pustaka `torchvision` tidak dipasang karena proyek ini murni pemrosesan teks.

---

## 8. Batasan Pengujian dan Pengukuran Hardware

1. **Cakupan Uji GPU Anggota 2**:
   Pengujian GPU yang telah dilakukan adalah **smoke test 1 batch terisolasi** (B=4, L=64, 28 token target). Logits, loss, dan gradien dari seluruh 41 parameter terbukti finite (tidak ada NaN, Inf, atau None).
2. **Pengukuran Memori**:
   Peak allocated VRAM pada 1 batch adalah **51.25 MB** (peak reserved: 70.00 MB). Anggota 3 harus memperhatikan bahwa angka ini **bukan estimasi konsumsi memori saat training penuh**.
3. **Kebutuhan Memori Tambahan Saat Training**:
   * Optimizer AdamW menyimpan momentum orde pertama dan orde kedua untuk setiap parameter dalam format 32-bit float, sehingga membutuhkan alokasi memori tambahan minimal 2 kali ukuran parameter.
   * Akumulasi gradien dan penyimpanan aktivasi forward sepanjang komputasi backward pass akan membutuhkan VRAM yang bertambah sebanding dengan batch size yang dipilih.
4. **Waktu Eksekusi**:
   Waktu 1 batch (~148 ms) mencakup sinkronisasi CUDA eksplisit untuk pencatatan benchmarking, bukan throughput inferensi atau training dalam pipeline yang mengalir tanpa sinkronisasi per batch.

---

## 9. Metrik Evaluasi yang Wajib Diterapkan Anggota 3

Untuk mengevaluasi model secara akurat selama masa pelatihan, Anggota 3 wajib menerapkan metrik berikut:

### A. Masked-Token Loss:
Nilai CrossEntropyLoss yang dihitung murni pada posisi target masked (`labels != -100`).

### B. Top-1 dan Top-5 Accuracy pada Posisi Target:
Akurasi dihitung secara ketat hanya pada posisi di mana label valid (`labels != -100`):
```python
# Prediksi token teratas dari logits
preds = logits.argmax(dim=-1) # [B, L]
target_mask = (labels != -100) # [B, L]

num_targets = target_mask.sum().item()
top1_correct = ((preds == labels) & target_mask).sum().item()

# Top-5 Accuracy
_, top5_preds = logits.topk(5, dim=-1) # [B, L, 5]
labels_expanded = labels.unsqueeze(-1).expand_as(top5_preds)
top5_correct = ((top5_preds == labels_expanded).any(dim=-1) & target_mask).sum().item()
```

### C. Agregasi Berbobot (Weighted Aggregation):
Jangan merata-ratakan nilai loss atau akurasi antarbatch secara langsung (unweighted batch average). Karena jumlah token target bervariasi pada setiap batch (rata-rata 15% dari token isi per chunk), agregasi harus dibobot berdasarkan jumlah target riil:
$$\text{Epoch Loss} = \frac{\sum_{\text{batch}} \text{Batch Loss} \times N_{\text{targets\_batch}}}{\sum_{\text{batch}} N_{\text{targets\_batch}}}$$
$$\text{Epoch Accuracy} = \frac{\sum_{\text{batch}} N_{\text{correct\_batch}}}{\sum_{\text{batch}} N_{\text{targets\_batch}}}$$

### D. Batasan Konseptual Eksponensial Loss Masking:
Nilai $\exp(\text{MLM Loss})$ pada pemodelan ini adalah eksponensial dari loss sebagian token yang dipilih secara acak (sekitar 15%). **Anggota 3 tidak boleh menyebut nilai ini sebagai pseudo-perplexity standar ataupun perplexity teks penuh**.
* Perplexity teks penuh (*full-sentence autoregressive perplexity*) mengukur probabilitas gabungan seluruh kalimat secara bertahap dari kiri ke kanan (seperti pada model GPT).
* Pseudo-perplexity standar (misalnya Salazar et al., 2020) mengharuskan masking setiap posisi token satu per satu secara bergantian pada seluruh kalimat utuh.
* Pada model MLM ini, $\exp(\text{MLM Loss})$ hanya mengukur ketidakpastian model pada posisi target token acak, sehingga harus dilaporkan secara spesifik sebagai eksponensial loss masked-token tanpa generalisasi berlebihan.

---

## 10. Daftar Pekerjaan Selanjutnya untuk Anggota 3

Berikut adalah rincian tugas yang menjadi tanggung jawab Anggota 3:
1. **Pembangunan Training Loop**:
   - Menyusun modul `src/training/train.py`.
   - Menghubungkan DataLoader split Train (27.002 chunk) dan split Val (2.685 chunk).
   - Mengatur pemisahan tensor batch (hanya `input_ids` dan `attention_mask` ke model).
   - Menambahkan mekanisme gradient clipping (misal `max_norm=1.0`).
2. **Optimizer dan Learning Rate Scheduler**:
   - Mengonfigurasi AdamW dengan decoupled weight decay (0.01 untuk bobot linear, 0.0 untuk bias dan LayerNorm).
   - Menentukan jadwal learning rate (misal linear warmup 10% total langkah, dilanjutkan cosine annealing).
3. **Strategi Checkpoint**:
   - Menyimpan checkpoint secara periodik setiap epoch atau setiap N langkah.
   - Menyimpan checkpoint model terbaik (*best model*) berdasarkan nilai validation loss terendah.
   - Memastikan checkpoint akhir dapat dimuat kembali dengan `MiniBertForMaskedLM.from_pretrained`.
4. **Visualisasi dan Dokumentasi Metrik**:
   - Mencatat dan memplot kurva Train Loss vs Val Loss per epoch.
   - Mencatat dan memplot kurva Top-1 dan Top-5 Accuracy pada split Train dan Val.
5. **Evaluasi Akhir pada Split Test**:
   - Menghitung loss, Top-1 accuracy, Top-5 accuracy, dan pseudo-perplexity pada seluruh 3.427 chunk split Test.
   - Menjalankan inferensi kualitatif menggunakan `predict.py` dengan beberapa contoh kalimat bahasa Indonesia untuk mendemonstrasikan kemampuan prediksi model terlatih.
