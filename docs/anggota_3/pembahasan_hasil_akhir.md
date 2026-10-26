# PEMBAHASAN HASIL AKHIR DAN ANALISIS EVALUASI MODEL MINI-BERT BAHASA INDONESIA

* **Penulis**: Anggota 3 (Training Loop, Hyperparameter Tuning, & Evaluasi Lead)
* **Pelaksana Eksekusi GPU**: Anggota 2 (Lenovo Legion Slim 5, RTX 4060 Laptop GPU 8GB) menggunakan skrip dan konfigurasi mandiri Anggota 3
* **Model Terpilih**: `runs/lr_1e3_gpu/best_model` (Epoch 5, 4.220 optimizer steps)
* **Status**: Pembahasan Akhir Lengkap Pasca-Evaluasi Test Split (Frozen & Final)
* **Tautan Berkas Terkait**:
  - Dokumen Penguncian Model: [`docs/anggota_3/penguncian_model_final.md`](file:///c:/Data%20C/(!)%20Kampus/Semester%207/Gen%20AI/KELOMPOK%207/docs/anggota_3/penguncian_model_final.md)
  - Laporan Evaluasi Final Test: [`docs/anggota_3/laporan_evaluasi_final_test.md`](file:///c:/Data%20C/(!)%20Kampus/Semester%207/Gen%20AI/KELOMPOK%207/docs/anggota_3/laporan_evaluasi_final_test.md)
  - Log Terminal Evaluasi Test: [`docs/anggota_3/final_test_terminal.log`](file:///c:/Data%20C/(!)%20Kampus/Semester%207/Gen%20AI/KELOMPOK%207/docs/anggota_3/final_test_terminal.log)
  - Logika Evaluator Independen: [`src/training/evaluate_test.py`](file:///c:/Data%20C/(!)%20Kampus/Semester%207/Gen%20AI/KELOMPOK%207/src/training/evaluate_test.py)

---

## 1. Tujuan Eksperimen dan Konfigurasi yang Dikontrol

Eksperimen ini bertujuan untuk melatih dan mengevaluasi model representasi bahasa dua-arah (*bidirectional encoder*) berukuran kompak (**Mini-BERT**) untuk bahasa Indonesia secara mandiri dari nol (*from scratch*) menggunakan paradigma *Masked Language Modeling* (MLM).

Untuk memastikan keabsahan ilmiah perbandingan hiperparameter, seluruh variabel arsitektural dan prosedural dikontrol secara ketat agar identik antar-eksperimen:

1. **Arsitektur Model Mini-BERT**:
   - Jumlah Layer Encoder (`num_layers`): 2 layer Transformer Encoder.
   - Jumlah Attention Heads (`num_heads`): 4 heads.
   - Dimensi Tersembunyi (`d_model`): 128.
   - Dimensi Feed-Forward (`d_ff`): 512.
   - Panjang Konteks Maksimum (`max_position_embeddings`): 64 token.
   - Ukuran Kosakata (`vocab_size`): 8.000 kata (*word-level*).
   - Total Parameter Model: 1.453.760 parameter (41 parameter matriks/vektor independen; bobot keluaran `cls.decoder.weight` terikat memori secara *weight tying* dengan matriks embedding `embeddings.word_embeddings.weight`).
2. **Kondisi Pelatihan yang Dikontrol**:
   - Ukuran Batch (`batch_size`): 32 chunk per batch.
   - Durasi Pelatihan (`epochs`): 5 epoch (844 steps per epoch, total 4.220 optimizer steps).
   - Korpus Latih: 27.002 chunk teks bahasa Indonesia (setara 1.436.788 token isi).
   - Korpus Validasi: 2.685 chunk teks (20.627 target bertopeng deterministik).
   - Optimizer & Regularisasi: AdamW dengan pemisahan *weight decay* (0.01 untuk matriks bobot, 0.0 untuk bias dan LayerNorm), pemangkasan gradien `max_grad_norm=1.0`, serta *dropout* 0.1.
   - Jadwal Laju Pembelajaran (*LR Scheduler*): Linear Warmup selama 10% langkah awal (422 steps), dilanjutkan Linear Decay menuju 0.0 pada akhir langkah ke-4.220.
   - Presisi Perhitungan: `float32` murni.
   - Random Seed Reproduksibilitas: `seed=42` untuk inisialisasi bobot (`model_seed`), pengurutan DataLoader (`shuffle_seed`), masking pelatihan (`masking_seed`), dan masking evaluasi (`eval_seed`).

### Variabel Bebas (Independen):
Satu-satunya variabel yang divariasikan adalah **Laju Pembelajaran Puncak (*Peak Learning Rate*)**:
- **Baseline GPU**: $\text{LR} = 3 \times 10^{-4}$ (`0.0003`), draf konfigurasi titik awal.
- **Eksperimen Pembanding GPU**: $\text{LR} = 1 \times 10^{-3}$ (`0.0010`), pengujian laju pembelajaran yang lebih agresif.

---

## 2. Perbandingan Kinerja Pelatihan: Baseline vs Eksperimen Pembanding

Kedua model dilatih pada akselerator GPU yang sama (NVIDIA GeForce RTX 4060 Laptop GPU 8GB) selama 5 epoch penuh.

### A. Tabel Hasil Evaluasi Validasi (Penyebut: Identik 20.627 Target Bertopeng)

| Metrik Evaluasi | Baseline ($\text{LR} = 3 \times 10^{-4}$) | Pembanding ($\text{LR} = 1 \times 10^{-3}$) | Selisih Absolut | Keterangan Satuan |
| :--- | :---: | :---: | :---: | :--- |
| **Best Epoch** | Epoch 5 | Epoch 5 | 0 | Titik terendah val loss |
| **Masked Cross-Entropy Loss** | 6.0361 nats | **5.4962 nats** | **-0.5399 nats** | Lebih rendah (perbaikan 8.94%) |
| **$\exp(\text{masked loss})$** | 418.27 | **243.77** | **-174.50 poin** | Skala eksponensial loss |
| **Validation Top-1 Accuracy** | 13.79% (2.844/20.627) | **18.05% (3.723/20.627)** | **+4.26 pp** | Poin persentase (*percentage points*) |
| **Validation Top-5 Accuracy** | 28.24% (5.825/20.627) | **32.66% (6.736/20.627)** | **+4.42 pp** | Poin persentase (*percentage points*) |
| **Final Train Loss (Online)** | 6.0957 nats | **5.5143 nats** | **-0.5814 nats** | Diukur dinamis selama training |
| **Final Train Top-1 (Online)** | 12.95% | **16.96%** | **+4.01 pp** | Poin persentase |
| **Final Train Top-5 (Online)** | 26.75% | **31.24%** | **+4.49 pp** | Poin persentase |
| **Total Waktu Pelatihan** | 80.19 detik | 140.86 detik | +60.67 detik | Waktu terukur aktual pada mesin host |

*Catatan: Selisih akurasi disajikan dalam **poin persentase (pp)**, bukan persentase kenaikan relatif.*

### B. Visualisasi Kurva Pelatihan
Kurva perbandingan per-epoch disajikan pada gambar berikut:
[`docs/anggota_3/kurva_perbandingan_lr.png`](file:///c:/Data%20C/(!)%20Kampus/Semester%207/Gen%20AI/KELOMPOK%207/docs/anggota_3/kurva_perbandingan_lr.png)

![Kurva Perbandingan Pelatihan](file:///c:/Data%20C/(!)%20Kampus/Semester%207/Gen%20AI/KELOMPOK%207/docs/anggota_3/kurva_perbandingan_lr.png)

---

## 3. Alasan Pemilihan Model Berdasarkan Validasi (*Model Selection Rationale*)

Sesuai metodologi baku pembelajaran mesin, penetapan model terbaik wajib diputuskan berdasarkan metrik pada **split validasi** sebelum split test dibuka:

1. **Keunggulan Konsisten di Seluruh Metrik**:
   Model pembanding $\text{LR} = 1 \times 10^{-3}$ pada Epoch 5 mengungguli Baseline $\text{LR} = 3 \times 10^{-4}$ secara menyeluruh: loss validasi lebih rendah sebesar **0.5399 nats**, akurasi Top-1 lebih tinggi sebesar **+4.26 pp**, dan Top-5 lebih tinggi sebesar **+4.42 pp**.
2. **Stabilitas Konvergensi Tanpa Titik Balik (*Inflection Point*)**:
   Selama lima epoch pelatihan, loss validasi kedua model terus menurun secara monoton tanpa mengalami kenaikan. Hal ini menunjukkan bahwa laju pembelajaran yang lebih tinggi ($10^{-3}$) mampu mengeksplorasi permukaan optimasi loss Cross-Entropy secara lebih cepat tanpa menimbulkan divergensi gradien berkat proteksi `max_grad_norm=1.0`.
3. **Penguncian Model Resmi (*Model Freezing Protocol*)**:
   Setelah keunggulan validasi diverifikasi, checkpoint `runs/lr_1e3_gpu/best_model` (Epoch 5) secara resmi dikunci dalam dokumen [`docs/anggota_3/penguncian_model_final.md`](file:///c:/Data%20C/(!)%20Kampus/Semester%207/Gen%20AI/KELOMPOK%207/docs/anggota_3/penguncian_model_final.md) dengan komitmen bahwa pilihan ini tidak akan diganti atau ditinjau ulang terlepas dari apapun hasil pada split test.

---

## 4. Hasil Evaluasi Final pada Split Test

Setelah model dikunci rapat, skrip evaluator independen [`src/training/evaluate_test.py`](file:///c:/Data%20C/(!)%20Kampus/Semester%207/Gen%20AI/KELOMPOK%207/src/training/evaluate_test.py) dieksekusi oleh Anggota 2 pada perangkat GPU RTX 4060.

### A. Penanganan Data dan Jumlah Target
- **Chunk Sumber Fisik**: 3.427 chunk pada `data/processed/pilot/test_chunks.jsonl`.
- **Penyaringan Manifest**: Sesuai kontrak `mlm_excluded_chunks_manifest.json`, tepat 1 chunk disaring otomatis (`doc_id="3792"`, `chunk_index=3`) karena seluruh 24 token isinya adalah token khusus/`[UNK]` tanpa kandidat token reguler.
- **Chunk Siap Evaluasi MLM**: **3.426 chunk**.
- **Total Target Token Bertopeng**: **27.071 target**.

### B. Metrik Hasil Evaluasi Split Test
- **Masked Cross-Entropy Loss**: **5.494842 nats**
- **$\exp(\text{masked-token loss})$**: **243.4330**
- **Top-1 Accuracy**: **17.4430%** (4.722 tebakan tepat dari 27.071 target)
- **Top-5 Accuracy**: **31.7535%** (8.596 target berada di 5 prediksi teratas dari 27.071 target)
- **Durasi Inferensi Evaluasi**: 1.04 detik (~3.281,1 chunk/detik)

### C. Tabel Komparasi Antar-Split Model Terpilih (LR 1e-3, Epoch 5)

| Split Evaluasi | Kondisi Pengukuran | Total Target Token | Masked Loss (nats) | Top-1 Accuracy (%) | Top-5 Accuracy (%) |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Train (Epoch 5)** | Online (bobot terus bergerak, dropout 0.1 aktif, masking dinamis)* | 216.579 | 5.5143 | 16.96% (36.723) | 31.24% (67.655) |
| **Validasi (Epoch 5)** | Frozen (eval mode, dropout 0.0, masking deterministik seed 42)** | 20.627 | 5.4962 | 18.05% (3.723) | 32.66% (6.736) |
| **Test (Final Test)** | Frozen (eval mode, dropout 0.0, masking deterministik seed 42)** | 27.071 | **5.4948** | **17.44% (4.722)** | **31.75% (8.596)** |

*\* Catatan Train: Diukur secara rata-rata bergerak selama pelatihan berlangsung, bukan evaluasi ulang model statis.*
*\*\* Catatan Validasi & Test: Diukur secara inferensi murni (`model.eval()`, `torch.inference_mode()`) pada bobot statis tanpa mutasi.*

Visualisasi komparasi antar-split disajikan pada gambar berikut:
[`docs/anggota_3/evaluasi_final_split_test.png`](file:///c:/Data%20C/(!)%20Kampus/Semester%207/Gen%20AI/KELOMPOK%207/docs/anggota_3/evaluasi_final_split_test.png)

![Evaluasi Antar Split Test](file:///c:/Data%20C/(!)%20Kampus/Semester%207/Gen%20AI/KELOMPOK%207/docs/anggota_3/evaluasi_final_split_test.png)

---

## 5. Perbandingan dengan Baseline Frekuensi Unigram

Untuk membuktikan secara empiris bahwa model benar-benar mempelajari asosiasi kontekstual dan bukan sekadar menghafal kata-kata paling sering, kami menguji **Baseline Frekuensi Unigram**:
- **Sumber Data Frekuensi**: Dihitung murni dari **1.436.788 token isi pada split TRAIN**.
- **Top-5 Token Paling Banyak Muncul di Train**:
  1. `','` (koma): 86.599 kemunculan (6.03%)
  2. `'.'` (titik): 73.013 kemunculan (5.08%)
  3. `'yang'`: 39.434 kemunculan (2.74%)
  4. `'dan'`: 37.612 kemunculan (2.62%)
  5. `'-'` (tanda hubung): 25.289 kemunculan (1.76%)
- **Aturan Prediksi Baseline Frekuensi**: Setiap kali token ditopengkan, prediktor frekuensi selalu menebak token terbanyak peringkat ke-1 (`','`) untuk Top-1, dan lima token terbanyak di atas untuk Top-5.

### Hasil Uji pada 20.627 Target Validasi (Sumber: `scratch/frequency_baseline_results.json`):

| Metrik Evaluasi Validasi | Baseline Frekuensi Unigram | Baseline Model ($\text{LR} = 3 \times 10^{-4}$) | Model Terpilih ($\text{LR} = 1 \times 10^{-3}$) | Keunggulan Model Terpilih vs Frekuensi |
| :--- | :---: | :---: | :---: | :---: |
| **Masked Loss** | 6.7852 nats | 6.0361 nats | **5.4962 nats** | **-1.2890 nats** (Ketidakpastian jauh lebih rendah) |
| **Top-1 Accuracy** | 6.60% (1.362/20.627) | 13.79% (2.844/20.627) | **18.05% (3.723/20.627)** | **+11.45 pp** (Meningkat 2.73x lipat) |
| **Top-5 Accuracy** | 18.95% (3.908/20.627) | 28.24% (5.825/20.627) | **32.66% (6.736/20.627)** | **+13.71 pp** (Meningkat 1.72x lipat) |

Grafik perbandingan performa model terhadap batas bawah unigram disajikan pada:
[`docs/anggota_3/perbandingan_baseline_vs_frekuensi.png`](file:///c:/Data%20C/(!)%20Kampus/Semester%207/Gen%20AI/KELOMPOK%207/docs/anggota_3/perbandingan_baseline_vs_frekuensi.png)

---

## 6. Pembahasan Kesalahan dan Dekomposisi Prediksi (*Error Analysis*)

Untuk memahami secara mendalam ke mana kapasitas representasi model dialokasikan, kami melakukan dekomposisi target validasi berdasarkan kategori token.

### A. Definisi Operasional Kategori Target
Agar tidak ambigu, klasifikasi target didefinisikan sebagai berikut:
1. **Target Tanda Baca (*Punctuation Targets*)**: Didefinisikan secara tegas sebagai token yang termasuk dalam himpunan karakter tanda baca ASCII: `{",", ".", "-", "\"", "'", ":", ";", "(", ")", "/", "?", "!"}`.
2. **Target Non-Tanda-Baca (*Non-Punctuation Targets*)**: Seluruh token target selain tanda baca di atas. Kategori ini mencakup kata konten leksikal (nomina, verba, adjektiva), kata tugas/fungsi gramatikal (konjungsi seperti *yang*, *dan*, preposisi seperti *di*, *ke*), serta angka numerik.

### B. Hasil Dekomposisi Kinerja pada 20.627 Target Validasi

| Kategori Target | Jumlah Target (Penyebut) | Top-1 Accuracy Model Baseline | Top-1 Accuracy Model Terpilih | Baseline Frekuensi Top-1 |
| :--- | :---: | :---: | :---: | :---: |
| **Target Tanda Baca** | 3.502 target (16.98%) | 48.66% (1.704) | **53.88% (1.887)** | 38.89% (1.362) |
| **Target Non-Tanda-Baca** | 17.125 target (83.02%) | 6.66% (1.140) | **10.72% (1.836)** | 0.00% (0) |
| **Total Keseluruhan** | **20.627 target (100.0%)** | 13.79% (2.844) | **18.05% (3.723)** | 6.60% (1.362) |

### C. Analisis Pola Keberhasilan dan Kegagalan Model:
1. **Peningkatan Kemampuan Prediksi Kata Non-Tanda-Baca**:
   Peningkatan laju pembelajaran ke $10^{-3}$ menaikkan akurasi target non-tanda-baca dari **6.66% menjadi 10.72% (+4.06 pp)**. Ini membuktikan bahwa model tidak hanya memprediksi tanda baca, melainkan mulai menggeneralisasi struktur kata bahasa Indonesia.
2. **Dominasi Posisi Tanda Baca**:
   Akurasi pada tanda baca mencapai **53.88%**, menyumbang 50.68% dari seluruh tebakan Top-1 yang benar (1.887 dari total 3.723 tebakan benar). Hal ini wajar dalam arsitektur encoder karena posisi tanda baca (seperti koma sebelum konjungsi atau titik di akhir kalimat) memiliki regularitas sintaksis yang sangat tinggi.
3. **Analisis Kegagalan Prediksi (*Failure Modes*)**:
   - **Bias Frekuensi Tinggi (*High-Frequency Prior Bias*)**: Pada konteks semantik terbuka di mana petunjuk leksikal minim, model cenderung memprioritaskan kata-kata umum seperti `yang`, `dan`, `di`, atau tanda baca.
   - **Tingkat Kesalahan Kata Konten**: Pada 89.28% target non-tanda-baca, tebakan pertama model masih salah. Meskipun demikian, pemeriksaan pada kandidat Top-5 (akurasi non-tanda-baca ~20-25%) memperlihatkan bahwa model sering kali menebak kata dengan kelas kata atau kategori semantik yang relevan, meskipun bukan kata eksak yang ditopengkan.
   - **Keterbatasan Kedalaman Representasi**: Dengan hanya 2 layer Transformer dan dimensi 128, model kesulitan menangkap relasi anafora atau dependensi antarklausa yang panjang.

---

## 7. Pembedaan Hasil Terukur vs Dugaan Penyebab (*Measured vs Speculative*)

Dalam pelaporan ilmiah, sangat penting untuk memisahkan fakta yang terukur dari hipotesis penyebab:

1. **Selisih Durasi Pelatihan**:
   - *Fakta Terukur*: Baseline berdurasi 80.19 detik (~16.0 s/epoch), sedangkan LR 1e-3 berdurasi 140.86 detik (~28.2 s/epoch) pada laptop Anggota 2.
   - *Batasan Analisis*: Karena kedua model memiliki jumlah operasi floating-point (FLOPs), arsitektur (1.45M parameter), dan jumlah batch (844 steps) yang persis identik, perbedaan durasi ini mencerminkan kondisi runtime aktual pada perangkat saat eksekusi. Kami tidak membuat klaim spekulatif mengenai penyebab pasti (seperti thermal throttling atau GPU scheduling) karena tidak adanya data logging sensor telemetri hardware selama eksekusi.
2. **Validation Loss Lebih Rendah dari Train Loss**:
   - *Fakta Terukur*: Validation loss (5.4962 nats) lebih rendah daripada train loss (5.5143 nats).
   - *Penyebab Teknis*: Hal ini merupakan fenomena standar akibat regularisasi: saat pelatihan, dropout 0.1 aktif mematikan 10% unit secara acak (menambah derau) dan train loss dirata-ratakan sepanjang 844 batch saat bobot masih berpindah. Saat evaluasi, dropout dinonaktifkan sepenuhnya (`model.eval()`) sehingga model beroperasi pada kapasitas penuh. Ini bukan indikasi kebocoran data (*data leakage*).

---

## 8. Keterbatasan Metodologis Proyek (*Methodological Limitations*)

Kelompok kami mengidentifikasi enam keterbatasan metodologis inheren yang harus diperhatikan dalam menafsirkan temuan proyek ini:

1. **Keterbatasan Eksperimen Satu Seed (*Single Seed Stochasticity*)**:
   Seluruh eksperimen dijalankan menggunakan satu nilai seed (`seed=42`). Tanpa adanya pengulangan pada beberapa seed acak (misal 3-5 seed), kami tidak dapat menghitung deviasi standar, interval kepercayaan (*confidence interval*), atau menjalankan uji signifikansi statistik (seperti paired t-test).
2. **Keterbatasan Kosakata Kata Utuh (*Word-Level Vocabulary*)**:
   Penggunaan tokenizer berbasis kata utuh (*word-level*) 8.000 kata tanpa algoritma subword (seperti BPE, WordPiece, atau SentencePiece) menyebabkan seluruh kata di luar 8.000 kata paling umum, termasuk bentuk infleksi/derivasi afiksasi kompleks khas bahasa Indonesia (`mempertanggungjawabkannya`, `keberlanjutan`), langsung dipetakan ke token khusus `[UNK]`.
3. **Pengecualian Target `[UNK]` pada MLM**:
   Sesuai kontrak data, token `[UNK]` (ID=1) sengaja dikecualikan dari proses masking MLM (`labels = -100`) agar model tidak dilatih memprediksi token placeholder yang ambigu. Model murni hanya dievaluasi pada kata-kata yang ada dalam kosakata 8.000 kata.
4. **Dominasi Tanda Baca dan Kata Tugas**:
   Proporsi kemunculan tanda baca dan stopwords yang tinggi dalam korpus bahasa alami menyebabkan sebagian besar kontribusi akurasi berasal dari token-token sintaksis tersebut.
5. **Skala Korpus Pilot**:
   Pelatihan dibatasi pada korpus pilot (~27 ribu chunk teks). Ukuran ini relatif kecil untuk melatih model bahasa Transformer dari nol, sehingga generalisasi pada domain khusus di luar korpus pilot tetap terbatas.
6. **Protokol Masking 80/10/10**:
   Masking dilakukan dengan rasio standar BERT: 80% diganti token `[MASK]`, 10% diganti token acak dari kosakata, dan 10% dipertahankan asli. Keberadaan 10% token acak menuntut model mengenali ketidakwajaran konteks, sementara evaluasi murni difokuskan pada token bertopeng (~15% dari total token reguler).

---

## 9. Ketepatan Terminologi Ilmiah

Untuk menjaga integritas ilmiah, kami menegaskan batasan terminologi berikut:
- **Bukan Perplexity Teks Penuh**: Nilai $\exp(\text{masked-token loss}) = 243.43$ adalah eksponensial dari rata-rata cross-entropy loss pada token bertopeng (*effective masked perplexity*). Metrik ini **tidak boleh disebut sebagai perplexity autoregresif teks penuh** atau *pseudo-perplexity* standar, karena MLM hanya mengevaluasi ~15% token target, bukan seluruh urutan token.
- **Bukan Bukti Pemahaman Bahasa**: Penurunan loss dan perolehan Top-1 sebesar 17.44% membuktikan bahwa model mampu memetakan probabilitas statistik antarkata dari korpus latih secara lebih baik daripada tebakan acak (1/8.000 = 0.0125%) atau frekuensi unigram (6.60%). Namun, hal ini **bukan bukti bahwa model memahami semantik bahasa Indonesia** layaknya model bahasa skala besar.
- **Kesimpulan Generalisasi Proporsional**: Kedekatan nilai loss validasi (5.4962) dan test (5.4948) mengindikasikan bahwa estimasi performa out-of-sample konsisten pada protokol evaluasi dan korpus ini, namun tidak membuktikan ketiadaan kebocoran data (*data leakage*) secara mutlak.

---

## 10. Ringkasan Hasil Final Terverifikasi

| Parameter Proyek | Status / Nilai Terverifikasi | Sumber Berkas Resmi |
| :--- | :--- | :--- |
| **Model Terpilih** | `runs/lr_1e3_gpu/best_model` (Epoch 5) | `runs/lr_1e3_gpu/best_model/` |
| **Arsitektur Model** | Mini-BERT 2 Layer, 4 Heads, $d_{\text{model}}=128$, $d_{\text{ff}}=512$ | `src/models/bert.py`, `config.json` |
| **Total Parameter** | 1.453.760 parameter (42 tensors di state dict) | `best_model/model.pt` (5.828.097 bytes) |
| **SHA-256 Model** | `0c0de0b0b88f51b5d7dfc474a3dc8bcbfe6d86d3c527e30869fd28eccb1ef8b8` | Dokumen Penguncian Model |
| **SHA-256 Config** | `521a31762dea889dc6ae865d9ad20816b90cecc35eb8212b2b725445a51f3026` | `best_model/config.json` |
| **SHA-256 Vocab** | `d2be29d07e76fe0cd15c3fe1b765325a5397a5e5fe30b2c6a5a019c976c552f2` | `data/processed/pilot/vocab.json` |
| **Dataset Test Siap MLM** | 3.426 chunk dievaluasi (1 chunk doc 3792 disaring) | `data/processed/pilot/test_chunks.jsonl` |
| **Total Target Bertopeng** | 27.071 target reguler | `runs/lr_1e3_gpu/final_test_evaluation.json` |
| **Final Test Loss** | **5.494842 nats** | `runs/lr_1e3_gpu/final_test_evaluation.json` |
| **Final Test Top-1 Acc** | **17.4430%** (4.722 / 27.071 target) | `runs/lr_1e3_gpu/final_test_evaluation.json` |
| **Final Test Top-5 Acc** | **31.7535%** (8.596 / 27.071 target) | `runs/lr_1e3_gpu/final_test_evaluation.json` |
| **Exp(masked loss)** | 243.4330 | `runs/lr_1e3_gpu/final_test_evaluation.json` |
