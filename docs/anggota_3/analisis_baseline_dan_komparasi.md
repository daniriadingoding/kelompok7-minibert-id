# ANALISIS KOMPREHENSIF PELATIHAN BASELINE GPU MINI-BERT, EVALUASI KOMPARASI LR 1E-3, DAN PANDUAN EVALUASI FINAL TEST

* **Tanggal Dokumen**: 24 Oktober 2026
* **Penulis**: Anggota 3 (Training Loop, Hyperparameter Tuning, & Evaluasi Lead)
* **Penerima**: Seluruh Anggota Kelompok 7 & Tim Penilai Akademik
* **Status Model**: Selesai Dilatih (Baseline LR 3e-4 & Pembanding LR 1e-3). Model Final **Resmi Dikunci pada LR 1e-3 Epoch 5**.
* **Status Split Test**: **Steril, Belum Pernah Dibuka atau Dievaluasi**. Evaluasi Final Menunggu Eksekusi GPU Anggota 2.
* **Berkas Sumber Data**:
  - `runs/baseline_gpu/training_history.json` & `.csv`
  - `runs/lr_1e3_gpu/training_history.json` & `.csv`
  - `runs/lr_1e3_gpu/best_model/model.pt` & `config.json`

---

## 1. Verifikasi Integritas Data & Hasil Aktual Kedua Run

Seluruh angka riwayat pelatihan diekstraksi langsung dari berkas JSON aktual di disk tanpa pembulatan subjektif. Kedua run dijalankan pada korpus penuh (27.002 train chunks, 2.685 val chunks) selama 5 epoch (4.220 optimizer steps):

### A. Tabel Perkembangan Per-Epoch Baseline (`LR = 3e-4`):
| Epoch | Global Step | Learning Rate | Train Loss | Train Top-1 | Train Top-5 | Val Loss | Val Top-1 | Val Top-5 | Durasi Train | Status Model |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1** | 844 | 2.67e-04 | 7.2275 | 6.29% | 17.01% | 6.6225 | 9.11% | 21.08% | 15.84 s | Best (Ep 1) |
| **2** | 1.688 | 2.00e-04 | 6.5266 | 9.44% | 22.49% | 6.3302 | 11.42% | 25.06% | 15.10 s | Best (Ep 2) |
| **3** | 2.532 | 1.33e-04 | 6.2990 | 11.11% | 24.82% | 6.1648 | 12.47% | 26.95% | 15.12 s | Best (Ep 3) |
| **4** | 3.376 | 6.66e-05 | 6.1782 | 12.23% | 25.79% | 6.0694 | 13.29% | 27.78% | 15.85 s | Best (Ep 4) |
| **5** | **4.220** | **0.00e+00** | **6.0957** | **12.95%** | **26.75%** | **6.0361** | **13.79%** | **28.24%** | **14.99 s** | **Best (Ep 5)** |

### B. Tabel Perkembangan Per-Epoch Pembanding (`LR = 1e-3` — Terpilih):
| Epoch | Global Step | Learning Rate | Train Loss | Train Top-1 | Train Top-5 | Val Loss | Val Top-1 | Val Top-5 | Durasi Train | Status Model |
| :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **1** | 844 | 8.89e-04 | 6.8974 | 8.00% | 19.82% | 6.2417 | 12.47% | 25.96% | 31.62 s | Best (Ep 1) |
| **2** | 1.688 | 6.66e-04 | 6.0780 | 13.21% | 26.81% | 5.8671 | 15.28% | 29.70% | 32.51 s | Best (Ep 2) |
| **3** | 2.532 | 4.44e-04 | 5.7982 | 15.07% | 29.16% | 5.6863 | 16.41% | 31.19% | 26.93 s | Best (Ep 3) |
| **4** | 3.376 | 2.22e-04 | 5.6362 | 16.15% | 30.17% | 5.5545 | 17.53% | 32.21% | 22.18 s | Best (Ep 4) |
| **5** | **4.220** | **0.00e+00** | **5.5143** | **16.96%** | **31.24%** | **5.4962** | **18.05%** | **32.66%** | **22.24 s** | **Best (Ep 5)** |

---

## 2. Tabel Perbandingan Berpasangan: Baseline vs Pembanding

Evaluasi dilakukan pada 20.627 target token validasi deterministik yang identik:

| Metrik Evaluasi | Baseline (`LR = 3e-4`) | Pembanding (`LR = 1e-3`) | Selisih Absolut (Poin Persentase / Nats) | Perubahan Relatif (%) |
| :--- | :---: | :---: | :---: | :---: |
| **Best Epoch** | Epoch 5 | Epoch 5 | 0 | Identik |
| **Total Optimizer Steps** | 4.220 | 4.220 | 0 | Identik |
| **Final Validation Loss** | 6.0361 nats | **5.4962 nats** | **-0.5399 nats** | -8.94% (Lebih Rendah) |
| **Effective Masked Perplexity** | 418.27 | **243.77** | **-174.50 poin** | -41.72% (Lebih Ramping) |
| **Final Validation Top-1 Acc** | 13.79% | **18.05%** | **+4.26 poin persentase (pp)** | +30.89% (Lebih Akurat) |
| **Final Validation Top-5 Acc** | 28.24% | **32.66%** | **+4.42 poin persentase (pp)** | +15.65% (Lebih Akurat) |
| **Final Train Loss** | 6.0957 nats | **5.5143 nats** | **-0.5814 nats** | -9.54% |
| **Final Train Top-1 Acc** | 12.95% | **16.96%** | **+4.01 poin persentase (pp)** | +30.97% |
| **Final Train Top-5 Acc** | 26.75% | **31.24%** | **+4.49 poin persentase (pp)** | +16.79% |
| **Total Waktu Komputasi** | 80.19 detik | 140.86 detik | +60.67 detik | Terukur riil di laptop host |

*Catatan Metrik: Seluruh selisih akurasi dinyatakan dalam **poin persentase (pp)** untuk membedakannya secara tegas dari persentase kenaikan relatif.*

---

## 3. Grafik Perbandingan Kurva Pelatihan

Grafik perbandingan beresolusi tinggi telah dibuat dan disimpan di:
`docs/anggota_3/kurva_perbandingan_lr.png`

![Kurva Perbandingan Pelatihan](file:///c:/Data%20C/%28%21%29%20Kampus/Semester%207/Gen%20AI/KELOMPOK%207/docs/anggota_3/kurva_perbandingan_lr.png)

*Gambar 1: Perbandingan Kurva Validation Loss, Akurasi Top-1, dan Akurasi Top-5 antara Baseline (LR 3e-4) dan Model Terpilih (LR 1e-3).*

---

## 4. Analisis Kritis Kurva & Dinamika Pelatihan

### A. Mengapa Validation Loss Lebih Rendah dari Train Loss?
Pada kedua eksperimen, validation loss selalu terukur lebih rendah dari train loss pada epoch yang bersesuaian. **Hal ini bukan kebocoran data (*data leakage*)**, melainkan disebabkan oleh karakteristik regularisasi:
1. **Dropout Aktif vs Nonaktif**: Pada training, `dropout=0.1` dan `attention_dropout=0.1` aktif mematikan 10% aktivasi secara stokhastik. Hal ini memberikan derau pada pemodelan sehingga menaikkan nilai Cross-Entropy. Saat validasi (`model.eval()`), seluruh dropout dinonaktifkan sehingga model bekerja pada kapasitas deterministik penuh (100%).
2. **Masking Tetap 80/10/10 yang Deterministik**: Perlu dicatat bahwa **mode evaluasi tetap menggunakan aturan masking 80/10/10** (80% `[MASK]`, 10% token acak, 10% token asli). Namun, pada evaluasi, pengacakan dikendalikan oleh seed deterministik berbasis SHA-256 (`eval_seed=42_doc_id_chunk_index`), menjamin konsistensi evaluasi.
3. **Agregasi Berjalan (*Running Batch Average*)**: Train loss dirata-ratakan saat bobot masih terus diperbarui di sepanjang 844 batch per epoch. Sementara itu, evaluasi validasi baru dijalankan pada akhir epoch setelah seluruh langkah optimasi epoch tersebut diaplikasikan.

### B. Evaluasi Gejala Overfitting
* Pada rentang 5 epoch ini, **tidak terlihat kenaikan validation loss** pada kedua run. Validation loss terus menurun secara monoton dari Epoch 1 hingga Epoch 5.
* **Pernyataan Hati-hati**: Fakta bahwa kurva validation loss belum berbalik naik (*inflection point*) membuktikan bahwa **gejala overfitting belum teramati pada durasi 5 epoch ini**. Namun, ini **bukan bukti ketiadaan overfitting secara absolut** jika pelatihan dilanjutkan ke 10 atau 20 epoch.

### C. Catatan Perbedaan Durasi Eksekusi
* Total waktu eksekusi run baseline adalah 80.19 detik (~16 detik/epoch), sedangkan run pembanding adalah 140.86 detik (~28 detik/epoch).
* Karena arsitektur model, ukuran batch (32), dan jumlah FLOPs matematis kedua model identik, perbedaan durasi ini murni mencerminkan kondisi runtime aktual pada perangkat host saat eksekusi berlangsung (tanpa membuat asumsi spekulatif mengenai throttling tanpa pengukuran telemetri sensor).

### D. Peringatan: Penurunan Loss Bukan Bukti Pemahaman Bahasa
Penurunan loss dari 8.987 ke 5.4962 membuktikan kemampuan optimasi matematis model dalam memetakan probabilitas kandidat kata dari 8.000 vocabulary. Namun, **kita tidak boleh mengklaim model memahami semantik bahasa Indonesia** murni dari penurunan loss ini. Akurasi Top-1 masih berada pada 18.05% (~82% tebakan pertama salah), dan prediksi masih memiliki bias prior yang kuat terhadap kata-kata umum.

---

## 5. Evaluasi Baseline Frekuensi Token Unigram (Train Only)

Baseline frekuensi dihitung murni dari **1.436.788 token pada split TRAIN** (tanpa special tokens):
* **Top-5 Token Train**: `','` (6.03%), `'.'` (5.08%), `'yang'` (2.74%), `'dan'` (2.62%), `'-'` (1.76%).
* **Hasil Uji pada 20.627 Target Validasi**:

| Metrik Evaluasi | Baseline Frekuensi Unigram | Baseline Model (`LR=3e-4`) | Model Terpilih (`LR=1e-3`) | Keunggulan Model Terpilih vs Frekuensi |
| :--- | :---: | :---: | :---: | :---: |
| **Validation Loss** | 6.7852 nats | 6.0361 nats | **5.4962 nats** | **-1.2890 nats (Lebih Rendah)** |
| **Effective Perplexity** | 884.66 | 418.27 | **243.77** | **-640.89 poin (-72.4%)** |
| **Top-1 Accuracy** | 6.60% | 13.79% | **18.05%** | **+11.45 pp (2.73x Lipat)** |
| **Top-5 Accuracy** | 18.95% | 28.24% | **32.66%** | **+13.71 pp (1.72x Lipat)** |

Grafik perbandingan baseline frekuensi tersedia di:
`docs/anggota_3/perbandingan_baseline_vs_frekuensi.png`

---

## 6. Dekomposisi Kinerja: Target Kata Leksikal vs Tanda Baca

Metrik utama tetap dievaluasi atas seluruh $N_{\text{total}} = 20.627$ target validasi. Dekomposisi berikut membedah kinerja dengan pembilang dan penyebut transparan:

* **Penyebut Keseluruhan**: $N_{\text{total}} = 20.627$ target token.
* **Penyebut Subkelompok Kata Leksikal**: $N_{\text{word}} = 17.125$ target (83.02%).
* **Penyebut Subkelompok Tanda Baca**: $N_{\text{punct}} = 3.502$ target (16.98%).

| Kategori Evaluasi | Penyebut Target | Model Baseline (`LR=3e-4`) Top-1 | Model Terpilih (`LR=1e-3`) Top-1 | Baseline Frekuensi Top-1 |
| :--- | :---: | :---: | :---: | :---: |
| **Keseluruhan** | **20.627** | 13.79% (2.844) | **18.05% (3.723)** | 6.60% (1.362) |
| **Tanda Baca** | **3.502** | 48.66% (1.704) | **53.88% (1.887)** | 38.89% (1.362) |
| **Kata Leksikal** | **17.125** | 6.66% (1.140) | **10.72% (1.836)** | 0.00% (0) |

### Wawasan Dekomposisi:
1. Peningkatan learning rate ke `1e-3` berhasil mendongkrak akurasi kata leksikal dari **6.66% menjadi 10.72% (+4.06 pp)**, membuktikan bahwa model mempelajari asosiasi kata riil, bukan sekadar memprediksi tanda baca.
2. Meskipun demikian, pada tanda baca akurasi mencapai **53.88%** (karena keteraturan batas klausa yang sangat kuat). Hal ini menjelaskan mengapa pada contoh inferensi terbuka kalimat pendek, tanda baca dan stopwords masih mendominasi probabilitas logit teratas.

---

## 7. Verifikasi Struktur Tensor & Model Checkpoint

Berdasarkan berkas aktual `runs/lr_1e3_gpu/best_model/model.pt` dan `src/models/bert.py`:
* **Jumlah Tensor State Dict**: Tepat **42 tensor** (bukan 25).
* **Jumlah Parameter Trainable Unik**: 1.453.760 parameter (41 tensor parameter independen; tensor ke-42 `cls.decoder.weight` terikat memori via *weight tying* dengan `embeddings.word_embeddings.weight`).
* **SHA-256 Bobot Model Terpilih (`model.pt`)**: `0c0de0b0b88f51b5d7dfc474a3dc8bcbfe6d86d3c527e30869fd28eccb1ef8b8` (5.828.097 bytes).
* **SHA-256 Konfigurasi Model (`config.json`)**: `521a31762dea889dc6ae865d9ad20816b90cecc35eb8212b2b725445a51f3026` (349 bytes).

---

## 8. Keterbatasan Metodologis Proyek

Dalam menganalisis performa Mini-BERT ini, kami mencatat 4 keterbatasan inheren yang harus dipahami:
1. **Keterbatasan Satu Seed (*Single Seed Stochasticity*)**:
   - Model dilatih dengan satu set seed (`model_seed=42`, `shuffle_seed=42`, `masking_seed=42`). Walaupun penurunan loss terbukti stabil pada kedua eksperimen, eksperimen multi-seed (3-5 seed) idealnya diperlukan untuk menghitung interval kepercayaan (*confidence interval*) dan signifikansi statistik.
2. **Keterbatasan Kosakata Word-Level (*Word-Level Vocabulary*)**:
   - Tokenizer berbasis kata utuh (*word-level*) 8.000 kata tidak memiliki mekanisme pemecahan subword (BPE/WordPiece). Akibatnya, afiksasi khas bahasa Indonesia (`ber-`, `meng-...-kan`, `di-...-i`) atau kata serapan baru di luar 8.000 kata langsung dipetakan ke `[UNK]`.
3. **Pengecualian Target UNK (*UNK Target Exclusion*)**:
   - Token `[UNK]` (ID=1) sengaja dikecualikan dari masking MLM (`labels = -100`) sesuai kontrak data pilot. Model tidak pernah dilatih memprediksi kata di luar 8.000 kata.
4. **Dominasi Tanda Baca (*Punctuation Dominance*)**:
   - Tanda koma dan titik mencakup 11.11% token latih dan menyumbang lebih dari separuh tebakan Top-1 yang benar karena keteraturan posisinya dalam kalimat.

---

## 9. Skrip & Panduan Evaluasi Final Test untuk Anggota 2

Skrip evaluasi final telah dibuat secara terpisah di [`src/training/evaluate_test.py`](file:///c:/Data%20C/%28%21%29%20Kampus/Semester%207/Gen%20AI/KELOMPOK%207/src/training/evaluate_test.py).

### Karakteristik Skrip Evaluasi:
* Memuat model terpilih `runs/lr_1e3_gpu/best_model` menggunakan loader tervalidasi.
* Menangani 3.427 chunk sumber menjadi 3.426 chunk siap MLM (1 chunk dengan 0 kandidat reguler disaring otomatis sesuai kontrak manifest).
* Menggunakan `MLMDataCollator` mode `eval` dengan `eval_seed=42`.
* Beroperasi pada `model.eval()` dan `torch.inference_mode()` murni tanpa pembaruan optimizer.
* Telah diuji logika evaluasinya pada data validasi dan menghasilkan angka yang cocok bit-per-bit (Loss 5.496226, Top-1 18.0492%, Top-5 32.6562%).

### Perintah Eksekusi GPU untuk Anggota 2:
Jalankan perintah berikut pada terminal PowerShell di laptop RTX 4060:

```powershell
.\.venv-gpu\Scripts\python.exe -m src.training.evaluate_test --model-dir runs/lr_1e3_gpu/best_model --test-file test_chunks.jsonl --device cuda
```

Laporan hasil evaluasi final akan otomatis disimpan ke:
- `runs/lr_1e3_gpu/final_test_evaluation.json`
- `runs/lr_1e3_gpu/final_test_evaluation.csv`
