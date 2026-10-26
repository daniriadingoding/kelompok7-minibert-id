# Kontrak Model Mini-BERT Bahasa Indonesia

**Versi Dokumen**: 1.1.0 (Final Handover Arsitektur Anggota 2 ke Anggota 3)  
**Tanggal**: 23 Oktober 2026  
**Penanggung Jawab**: Anggota 2 (Arsitektur Model & Hardware Lead)  
**Penerima Manfaat**: Anggota 3 (Training Loop & Evaluasi Lead)  
**Status**: Lengkap, Teruji 100%, Siap Pelatihan (Production-Ready Architecture)  

---

## 1. Spesifikasi Konfigurasi dan Integritas Vocabulary

Arsitektur Mini-BERT Bahasa Indonesia dirancang modular dan mandiri (*from scratch*) menggunakan kelas [`MiniBertConfig`](file:///C:/Users/DANI/Documents/Kuliah/Semester%207/Generative%20AI/Mid%20Project/KELOMPOK%207/src/models/config.py#L14).

### Parameter Hyperparameter Resmi:
- **`vocab_size`**: **8.000 token** (termasuk 5 token khusus 0..4).
- **`pad_token_id`**: **0** (`[PAD]`).
- **`d_model`**: **128** (dimensi vektor tersembunyi / hidden size).
- **`num_layers`**: **2** (jumlah blok Transformer Encoder).
- **`num_heads`**: **4** (jumlah attention heads, `head_dim = 128 // 4 = 32`).
- **`d_ff`**: **512** (dimensi intermediate lapisan Feed-Forward).
- **`max_position_embeddings`**: **64** (kapasitas maksimal urutan sequence).
- **`dropout`**: **0.1** (probabilitas dropout embedding, encoder, dan FFN).
- **`attention_dropout`**: **0.1** (probabilitas dropout pada matriks bobot atensi).
- **`layer_norm_eps`**: **1e-12** (stabilitas numerik LayerNorm).
- **`initializer_range`**: **0.02** (standar deviasi inisialisasi bobot normal).
- **`vocab_sha256`**: `d2be29d07e76fe0cd15c3fe1b765325a5397a5e5fe30b2c6a5a019c976c552f2`

> **Catatan Rekonsiliasi Hash Vocabulary**:  
> Dokumentasi awal pipeline data mencatat string hash `8a4ca39b69b596e1a47dfdcb373bf9bcf51e7f603d32ef3c8d45138127027d78`. Berdasarkan audit kode dan transkrip, nilai tersebut merupakan entri manual tidak terverifikasi pada draf laporan awal. Nilai hash aktual yang dihitung oleh algoritma kanonikal `compute_vocab_hash` pada artefak fisik `vocab.json` dan laporan evaluasi `vocabulary_comparison_report.json` adalah `d2be29d0...`.  
> Uji verifikasi deterministik re-chunking pada 33.114 chunk (27.002 train, 2.685 val, 3.427 test) membuktikan kesesuaian 100% tanpa satupun perbedaan token-ID. Nilai `d2be29d0...` adalah acuan hash sah dan terverifikasi untuk seluruh proses pemodelan.

---

## 2. Antarmuka Forward Model

Pemanggilan model [`MiniBertForMaskedLM`](file:///C:/Users/DANI/Documents/Kuliah/Semester%207/Generative%20AI/Mid%20Project/KELOMPOK%207/src/models/bert.py#L21) dirancang sederhana dan stabil:

```python
logits = model(input_ids=input_ids, attention_mask=attention_mask)
```

### Spesifikasi Tensor:
- **`input_ids`**: `torch.long [batch_size, seq_len]`, rentang nilai token ID `0 <= id < 8000`.
- **`attention_mask`**: `torch.long [batch_size, seq_len]`, bernilai `1` untuk token aktif (`[CLS]`, kata isi, `[SEP]`, `[MASK]`) dan `0` untuk padding `[PAD]`.
- **`logits`**: `torch.float32 [batch_size, seq_len, 8000]`.
  * Logits berupa nilai riil mentah (*raw unnormalized logits*).
  * **Dilarang menerapkan softmax sebelum fungsi loss**, karena `nn.CrossEntropyLoss` di PyTorch menggabungkan LogSoftmax dan NLLLoss secara numerik stabil.
  * Device tensor mengikuti model secara otomatis (tidak ada device yang di-hardcode ke "cuda" di dalam kode model).

---

## 3. Metadata Batch yang Dilarang Dikirim ke Forward Model

Batch dari `DataLoader` memuat kamus dengan 5 kunci:
1. `input_ids` (dikirim ke model)
2. `attention_mask` (dikirim ke model)
3. `labels` (digunakan oleh fungsi loss)
4. `doc_ids` (metadata pelacakan, daftar string/int)
5. `chunk_indices` (metadata pelacakan, tensor indeks chunk)

> **Peringatan Kritis**:  
> Jangan memanggil `model(**batch)`. Memasukkan `doc_ids` atau `chunk_indices` ke forward model akan memicu eksepsi `TypeError`. Ekstrak tensor secara eksplisit seperti contoh pada Bagian 7.

---

## 4. Perhitungan Loss Masked Language Model

Loss dihitung murni pada posisi target prediksi MLM menggunakan PyTorch `CrossEntropyLoss`:

```python
loss_fn = torch.nn.CrossEntropyLoss(ignore_index=-100)

# Reshape logits ke [B * L, vocab_size] dan labels ke [B * L]
loss = loss_fn(logits.view(-1, config.vocab_size), labels.view(-1))
```

- Tensor `labels` telah diatur oleh `MLMDataCollator` Anggota 1 dengan nilai Token ID asli pada posisi target, dan `-100` pada seluruh posisi lainnya.
- Argumen `ignore_index=-100` menjamin posisi non-target dan posisi padding tidak berkontribusi pada gradien atau nilai loss rata-rata.

---

## 5. Ringkasan Parameter dan Kebijakan Bobot

### A. Jumlah Parameter Unik Model
Total parameter model Mini-BERT ini dihitung akurat tanpa menduplikasi parameter weight tying:

| Komponen Arsitektur | Rincian Lapisan | Jumlah Parameter |
| :--- | :--- | :---: |
| **BertEmbeddings** | Word Embeddings (8000 x 128) | 1.024.000 |
| | Positional Embeddings (64 x 128) | 8.192 |
| | LayerNorm Embedding (gamma & beta) | 256 |
| **BertEncoder (2 Layer)** | MultiHeadSelfAttention (Q, K, V, Out) | 131.072 |
| | Attention LayerNorm (2 layer) | 512 |
| | Feed-Forward Network (Dense1 + Dense2) | 262.144 |
| | FFN LayerNorm (2 layer) | 512 |
| **BertMLMHead** | Dense Transform (128 x 128 + bias) | 16.512 |
| | LayerNorm Transform | 256 |
| | Proyeksi Decoder (Weight Tying ke Word Embeddings) | 0 (Bobot Bersama) |
| | Bias Decoder (8000) | 8.000 |
| **Total Parameter Unik** | **Seluruh Model Mini-BERT** | **1.453.760** |

### B. Weight Tying dan Gradien Token `[PAD]`
- Bobot matriks proyeksi vocabulary diikat ke matriks bobot word embeddings (`decoder.weight = word_embeddings.weight`).
- Karena proyeksi vocabulary menghitung logits pada seluruh 8.000 kata untuk setiap posisi target, gradien output head pada penyebut normalisasi softmax dapat memperbarui bobot baris token `[PAD]` (indeks 0).
- Baris token `[PAD]` tidak dijamin selalu bernilai nol selama pelatihan. Ini merupakan perilaku alami dari weight tying dan tidak merusak konvergensi model.

---

## 6. Prosedur Penyimpanan dan Pemuatan Model (Save & Load)

Model menyediakan metode serialisasi dan deserialisasi terverifikasi:

```python
from src.models.bert import MiniBertForMaskedLM

# 1. Menyimpan Model dengan Status Eksplisit
# Untuk baseline acak awal (Anggota 2):
model.save_pretrained("checkpoints/untrained_baseline", filename="model.pt", checkpoint_status="random_init")

# Untuk model hasil pelatihan (Anggota 3):
model.save_pretrained("checkpoints/best_model", filename="model.pt", checkpoint_status="trained")

# 2. Memuat Model
# Memvalidasi konfigurasi dictionary lengkap, memuat state_dict secara strict, menjamin weight tying,
# memeriksa keselarasan hash tokenizer, serta mengekstrak status checkpoint ('random_init', 'trained', atau 'unknown')
loaded_model = MiniBertForMaskedLM.from_pretrained(
    "checkpoints/best_model",
    filename="model.pt",
    tokenizer_dir="data/processed/pilot",
    require_tokenizer=True
)
print("Status Checkpoint:", loaded_model.checkpoint_status)
```

### Mekanisme Penguatan Pemuatan Checkpoint:
1. **Validasi Dictionary Konfigurasi Lengkap**:
   - Checkpoint `model.pt` wajib memuat kunci `"config"` bertipe dictionary.
   - Seluruh field konfigurasi yang diharapkan dicocokkan satu per satu dengan `config.json`.
   - Loader menolak checkpoint jika kunci `"config"` hilang, bukan dictionary, terdapat field yang dihapus/kurang, terdapat field tidak dikenal, atau nilainya berbeda dengan `config.json`.
2. **Validasi Tiga Titik Hash Vocabulary**:
   - Memeriksa keselarasan `vocab_sha256` pada tiga sumber: konfigurasi disk, metadata checkpoint, dan tokenizer aktif pada `tokenizer_dir`.
   - Menolak hash kosong atau ketidakcocokan nilai secara eksplisit.
3. **Pemuatan Bobot Ketat (Strict Loading) dan Weight Tying**:
   - Menggunakan `load_state_dict(..., strict=True)`.
   - Memastikan kembali bahwa memori bobot decoder dan word embeddings terikat (`cls.decoder.weight = embeddings.word_embeddings.weight`).
4. **Ekstraksi Status Checkpoint**:
   - Status dibaca dari metadata `"checkpoint_status"` di dalam `model.pt` (bukan disimpulkan dari nama folder).
   - Nilai status yang sah antara lain `"random_init"`, `"trained"`, atau `"unknown"` jika metadata tidak ditemukan.

---

## 7. Skrip Inferensi Masked Language Model (`predict.py`)

Skrip inferensi mandiri disediakan pada [`src/models/predict.py`](file:///C:/Users/DANI/Documents/Kuliah/Semester%207/Generative%20AI/Mid%20Project/KELOMPOK%207/src/models/predict.py):

```bash
# Menjalankan inferensi CLI
python -m src.models.predict --text "Indonesia adalah negara [MASK] di Asia Tenggara." --top-k 5 --device auto
```

### Karakteristik Inferensi:
1. Menggunakan `model.eval()` dan `torch.inference_mode()`.
2. Menampilkan status checkpoint aktual (`random_init`, `trained`, atau `unknown`) berdasarkan metadata internal berkas model, bukan dari asumsi nama folder.
3. Menerima token `[MASK]` maupun `[mask]` huruf kecil.
4. Menolak masukan tanpa `[MASK]` dan masukan yang melebihi batas panjang (64 token) tanpa pemotongan diam-diam.
5. Menghitung probabilitas absolut melalui softmax ke seluruh vocabulary (8.000 kata) dan mengecualikan token khusus (ID 0..4) dari peringkat top-k.
6. Mendukung masukan dengan beberapa `[MASK]` (setiap posisi dievaluasi secara independen dari konteks input yang sama).
7. Melaporkan jumlah kata di luar vocabulary (`[UNK]`) yang muncul pada kalimat masukan.

---

## 8. Panduan Metrik Evaluasi untuk Anggota 3

Untuk mengevaluasi model secara tepat dan adil selama training dan validasi, Anggota 3 wajib menggunakan metrik berikut:

### 1. Masked-Token Loss:
Nilai CrossEntropyLoss rata-rata yang dihitung murni pada posisi token target (`labels != -100`):
$$\mathcal{L}_{\text{MLM}} = -\frac{1}{N_{\text{target}}} \sum_{i \in \text{targets}} \log P(w_i \mid \text{konteks})$$

### 2. Top-1 dan Top-5 Accuracy pada Posisi Target:
Akurasi dihitung secara eksklusif hanya pada posisi token target (`labels != -100`):
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

### 3. Aturan Agregasi Berbobot (Weighted Aggregation):
Jangan merata-ratakan nilai loss atau akurasi antarbatch secara langsung (unweighted average) jika jumlah token target pada tiap batch sedikit berbeda. Gunakan agregasi berbobot berdasarkan jumlah target riil:
$$\text{Epoch Loss} = \frac{\sum_{\text{batch}} \text{Batch Loss} \times N_{\text{target\_batch}}}{\sum_{\text{batch}} N_{\text{target\_batch}}}$$
$$\text{Epoch Accuracy} = \frac{\sum_{\text{batch}} N_{\text{correct\_batch}}}{\sum_{\text{batch}} N_{\text{target\_batch}}}$$

### 4. Batasan Konseptual Eksponensial Loss Masking:
Nilai $\exp(\mathcal{L}_{\text{MLM}})$ pada pemodelan ini adalah eksponensial dari loss sebagian token yang dipilih secara acak (sekitar 15%). **Anggota 3 tidak boleh menyebut nilai ini sebagai pseudo-perplexity standar ataupun perplexity teks penuh**.
* Perplexity teks penuh (*full-sentence autoregressive perplexity*) mengukur probabilitas gabungan seluruh kalimat secara bertahap dari kiri ke kanan (seperti pada model GPT).
* Pseudo-perplexity standar (misalnya Salazar et al., 2020) mengharuskan masking setiap posisi token satu per satu secara bergantian pada seluruh kalimat utuh.
* Pada model MLM ini, $\exp(\mathcal{L}_{\text{MLM}})$ hanya mengukur ketidakpastian model pada posisi target token acak, sehingga harus dilaporkan secara spesifik sebagai eksponensial loss masked-token tanpa generalisasi berlebihan.

---

## 9. Status Model, Lingkungan, dan Batasan Pengujian

### 9.1 Status Bobot Model Saat Ini
1. Model saat ini berada pada kondisi **bobot acak baru diinisialisasi (untrained baseline)** yang diinisialisasi menggunakan distribusi normal (mean 0.0, standard deviation 0.02).
2. Nilai loss awal terukur adalah ~9.01, konsisten secara teoritis dengan entropi acak dari klasifikasi seragam atas 8.000 kelas ($\ln(8000) \approx 8.987$).
3. Output dari skrip inferensi `predict.py` pada tahap ini menghasilkan token acak. Model belum memiliki kemampuan pemahaman semantik atau bahasa sebelum dilatih oleh Anggota 3.

### 9.2 Lingkungan Eksekusi dan Dependensi Aktual
- **Sistem Operasi**: Windows 11 (build x86_64)
- **Virtual Environment**: `.venv-gpu` (terisolasi penuh dari `.venv` lama)
- **Python Runtime**: 3.13.2 lokal (`C:\Users\DANI\AppData\Local\Programs\Python\Python313\python.exe`)
- **PyTorch**: `torch==2.6.0+cu124`
- **Versi Runtime / Build CUDA PyTorch**: CUDA 12.4 (`torch.version.cuda = '12.4'`)
- **Versi Driver NVIDIA**: 617.42 (mendukung driver level CUDA hingga 13.4)
- **Perangkat Keras**: NVIDIA GeForce RTX 4060 Laptop GPU (Total VRAM 8.188 MiB)
- **Pustaka Data**: `datasets==5.1.0`, `pyarrow==26.0.0`, `fsspec==2026.7.0` (tanpa pustaka `torchvision` karena proyek ini murni pemrosesan teks)

### 9.3 Batasan Pengujian dan Pengukuran Hardware
1. Pengujian GPU yang telah dilakukan adalah **smoke test 1 batch nyata** (B=4, L=64, 28 token target) tanpa optimizer.
2. Logits, loss, dan gradien dari seluruh 41 parameter terbukti finite (bebas dari nilai NaN, Inf, atau None).
3. Pengukuran memori aktual satu batch (Peak Allocated 51.25 MB, Peak Reserved 70.00 MB) **bukan estimasi kebutuhan memori pelatihan penuh**.
4. Pada pelatihan penuh, optimizer AdamW membutuhkan alokasi memori tambahan minimal 2 kali ukuran parameter float32 (untuk momentum pertama dan momentum kedua), buffer gradien akumulasi, serta memori aktivasi yang membesar proporsional dengan batch size.
5. Waktu eksekusi satu batch (~148 ms) mencakup sinkronisasi CUDA eksplisit dan overhead pengukuran terisolasi, bukan representasi throughput pelatihan per detik dalam pipeline kontinu.

---

## 10. Daftar Pekerjaan dan Tanggung Jawab Anggota 3

Tahap arsitektur model dan verifikasi integrasi telah selesai 100%. Hak dan tanggung jawab pelaksanaan tahap selanjutnya berada pada Anggota 3:

1. **Training Loop**:
   - Menyusun perulangan epoch pelatihan dan evaluasi validasi periodik.
   - Menerapkan pemisahan metadata batch (`doc_ids`, `chunk_indices`) dari pemanggilan forward model.
   - Mengatur penanganan `labels` dengan `torch.nn.CrossEntropyLoss(ignore_index=-100)`.
   - Mengimplementasikan gradient clipping (misal `torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)`).

2. **Optimizer dan Learning Rate Scheduler**:
   - Mengonfigurasi optimizer AdamW dengan pemisahan weight decay (weight decay 0.01 untuk bobot bobot matriks, weight decay 0.0 untuk bias dan LayerNorm).
   - Mengonfigurasi learning rate scheduler (misal linear warmup 10% langkah dilanjutkan cosine decay atau linear decay).

3. **Manajemen Checkpoint Pelatihan**:
   - Menyimpan checkpoint pelatihan berkala yang memuat `model_state_dict`, `optimizer_state_dict`, `scheduler_state_dict`, nomor epoch, dan metrik validasi terbaik.
   - Mempertahankan format `config.json` dan metadata `vocab_sha256` agar checkpoint hasil latihan tetap kompatibel dengan `MiniBertForMaskedLM.from_pretrained` dan `src.models.predict`.

4. **Metrik dan Visualisasi**:
   - Menghitung masked-token loss rata-rata berbobot.
   - Menghitung akurasi Top-1 dan Top-5 berbobot pada posisi target (`labels != -100`).
   - Menyajikan grafik perkembangan loss dan akurasi (Train vs Validation).
   - Mencantumkan penjelasan bahwa nilai $\exp(\text{MLM Loss})$ adalah pseudo-perplexity atas token target masked, bukan full autoregressive perplexity.

5. **Evaluasi Akhir dan Pelaporan**:
   - Menjalankan evaluasi final pada split Test (3.427 chunk).
   - Menjalankan uji inferensi kualitatif `python -m src.models.predict` menggunakan checkpoint model terlatih terbaik untuk membuktikan kemampuan prediksi bahasa Indonesia.
