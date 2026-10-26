# LOG INTERAKSI LLM — ANGGOTA 3 (KELOMPOK 7)

* **Tanggal Sesi**: 24 Oktober 2026
* **Peran Anggota**: Anggota 3 (Training Loop, Optimizer, Scheduler, Metrik, Checkpoint, & Evaluasi Lead)
* **Topik Modul**: Pembangunan Pipeline Pelatihan Mini-BERT Bahasa Indonesia dari Nol, Rangkaian Pengujian Unit, Diagnostik CPU (Overfit Check & Smoke Run), serta Panduan Serah Terima GPU.
* **Metode Pengembangan**: Vibe Coding Berkolaborasi Aktif dengan LLM (Tanpa Copy-Paste Kode Eksternal / Tutorial Luar)

---

## 1. TAHAP INISIASI & AUDIT LINGKUNGAN (Read-Only)

### A. Rangkuman Prompt & Arah Instruksi:
1. Melakukan audit *read-only* terhadap seluruh dokumen panduan dosen (`[CAK4KBB3 2026-1] Panduan Proyek 1 - Vibe Coding.md`), kontrak data Anggota 1 (`docs/data_contract_pilot.md`), kontrak arsitektur Anggota 2 (`docs/model_contract.md`), serta panduan serah terima (`docs/anggota_2/panduan_serah_terima_anggota3.md`).
2. Memeriksa spesifikasi perangkat lokal:
   - OS: Windows 11 AMD64 (12 Logical Cores Intel).
   - Interpreter: Python 3.13.12 (`C:\Users\Daffa\miniconda3\python.exe`).
   - PyTorch: `2.12.1+cpu` (tanpa akselerasi CUDA pada build lokal).
   - Tidak memodifikasi pustaka dasar Miniconda secara langsung.
3. Memverifikasi rangkaian pengujian bawaan:
   - Seluruh 82 unit test awal (data pipeline + arsitektur model) dieksekusi pada CPU lokal dan lulus 100% dalam 8,02 detik.
4. Merekonsiliasi artefak kanonikal:
   - Mengonfirmasi bahwa hash kanonikal vocabulary yang sah dan terkunci adalah `d2be29d07e76fe0cd15c3fe1b765325a5397a5e5fe30b2c6a5a019c976c552f2` (dihitung dari urutan pasangan token-ID via `MiniBertConfig.compute_vocab_hash`).
   - Mengonfirmasi bahwa split Test memuat 3.426 chunk siap MLM (1 chunk `doc_id="3792"` dikeluarkan karena 0 target token reguler sesuai catatan `mlm_excluded_chunks_manifest.json`).

---

## 2. TAHAP PERANCANGAN DAN IMPLEMENTASI KODE (`src/training/`)

### Modul-Modul yang Dibangun:
1. **`src/training/config.py`**:
   - Kelas `TrainingConfig` berbasis `dataclass` dengan validasi parameter yang menolak nilai non-positif, NaN/Inf, dan konfigurasi cacat.
   - Menyediakan konversi dua arah ke/dari JSON serta bridging ke `MiniBertConfig`.
2. **`src/training/metrics.py`**:
   - Fungsi `compute_batch_mlm_metrics`: Menghitung CrossEntropyLoss murni pada posisi target (`labels != -100`), Top-1 dan Top-5 Accuracy atas seluruh 8.000 vocabulary.
   - Kelas `MLMMetricAccumulator`: Mengumpulkan `loss_sum`, `num_targets`, dan `top1/top5_correct` di seluruh batch untuk menghitung rata-rata berbobot (*weighted epoch metrics*) guna menghindari bias *unweighted batch averaging*.
   - Menolak batch tanpa target dengan pesan eksepsi `ValueError` yang jelas.
   - Melaporkan $\exp(\text{MLM loss})$ secara eksplisit sebagai *exponential of masked-token loss* tanpa mengklaimnya sebagai *full-sentence autoregressive perplexity* atau *standard pseudo-perplexity*.
3. **`src/training/optimizer.py`**:
   - Fungsi `create_optimizer`: Mengonfigurasi AdamW dengan membagi parameter ke dalam dua kelompok:
     * *No-Decay* (`weight_decay = 0.0`): Seluruh parameter bias (`*.bias`) dan LayerNorm.
     * *Decay* (`weight_decay = 0.01`): Token embeddings, positional embeddings, dan bobot matriks proyeksi linier.
     * *Tied Weights Handling*: Matriks bobot `cls.decoder.weight` yang berbagi memori dengan `embeddings.word_embeddings.weight` diproteksi agar terdaftar tepat satu kali di optimizer.
   - Fungsi `perform_optimizer_step`: Memeriksa keabsahan loss finite, menjalankan backward, memvalidasi gradien finite pada setiap parameter, melakukan clipping (`max_norm = 1.0`), dan memperbarui bobot via `optimizer.step()`.
4. **`src/training/scheduler.py`**:
   - Fungsi `get_linear_schedule_with_warmup`: Menghitung rasio learning rate secara linear dari langkah pertama hingga mencapai 100% pada akhir fase warmup, dilanjutkan peluruhan linear menuju 0.0 pada langkah akhir.
   - Menolak konfigurasi cacat (`num_warmup_steps > num_training_steps` atau nilai non-positif).
5. **`src/training/checkpoint.py`**:
   - Kelas `CheckpointManager`: Menerapkan penyimpanan atomik (*atomic save*) melalui berkas temporer `.tmp` yang di-rename via `os.replace` untuk mencegah korupsi berkas saat interupsi daya.
   - Format checkpoint training menyimpan: `model_state_dict`, `optimizer_state_dict`, `scheduler_state_dict`, `epoch_completed`, `next_epoch`, `global_step`, `best_val_loss`, konfigurasi, hash vocabulary, hash artefak data, serta seluruh state RNG (Python random, PyTorch CPU, CUDA jika ada, dan generator shuffle DataLoader).
   - Menyediakan fungsi pemulihan state RNG dengan penempatan device tensor yang tepat.
   - Menyediakan fungsi ekspor `export_inference_model` dengan status `"trained"` hanya jika model telah menerima pembaruan optimasi (`global_step > 0`).
6. **`src/training/trainer.py`**:
   - Mengintegrasikan perulangan epoch training dan evaluasi validasi periodik.
   - Menerapkan pemisahan seed: seed inisialisasi model, seed shuffle generator DataLoader, seed masking train per epoch (`masking_seed + epoch`), dan seed evaluasi deterministik berbasis SHA-256 (`eval_seed`).
   - Memastikan metadata pelacakan (`doc_ids`, `chunk_indices`) tidak dikirimkan ke forward pass model.
   - Memastikan split Test tidak pernah diakses selama pelatihan atau validasi.
   - Menyimpan riwayat metrik ke `training_history.json` dan `training_history.csv`.
7. **`src/training/run_experiment.py`**:
   - Antarmuka baris perintah (CLI) untuk menjalankan pelatihan dengan flag `--config`, `--device`, `--resume-from`, dan `--overwrite`.

---

## 3. TAHAP PENANGANAN EROR & DEBUGGING (Tahap 2)

Selama pengujian unit pipeline di `tests/test_training_pipeline.py`, ditemukan 3 kendala teknis yang diselesaikan secara tuntas:

### Eror 1: `NameError: name 'math' is not defined` pada `optimizer.py`
- **Pesan Eror**: `NameError: name 'math' is not defined. Did you forget to import 'math'?` pada baris validasi `math.isfinite(grad_norm_val)`.
- **Analisis Solusi**: Menambahkan `import math` pada header modul `src/training/optimizer.py`.

### Eror 2: `TypeError: MiniBertForMaskedLM.from_pretrained() got an unexpected keyword argument 'device'`
- **Pesan Eror**: Eksepsi saat memuat model ekspor pada `test_exported_model_compatible_with_inference_loader`.
- **Analisis Solusi**: Berdasarkan arsitektur Anggota 2 pada `src/models/bert.py`, metode `from_pretrained` memuat model ke CPU secara default tanpa menerima argumen `device`. Pemindahan ke device target dilakukan setelah model diinisialisasi melalui `.to(device)`. Parameter dihapus dari pemanggilan fungsi uji.

### Eror 3: Perilaku Deduplikasi Default `model.named_parameters()` pada Tied Weights
- **Pesan Eror**: `AssertionError: 'cls.decoder.weight' not found in []` pada `summary["tied_skipped_names"]`.
- **Analisis Solusi**: Secara default, implementasi bawaan PyTorch `nn.Module.named_parameters()` menggunakan parameter `remove_duplicate=True` sehingga parameter kedua yang memiliki pointer memori identik langsung diabaikan oleh iterator bawaan. Untuk mendeteksi, mencatat, dan mengonfirmasi secara eksplisit bahwa tied weight tertangani dengan aman, parameter dipanggil dengan `model.named_parameters(remove_duplicate=False)`.

### Eror 4: Ketidaksinkronan Total Steps Scheduler pada Uji Resume Batas Epoch
- **Pesan Eror**: Perbedaan loss validasi antara run uninterrupted dan run resumed pada pengujian resume unit test.
- **Analisis Solusi**: Pada pengujian awal, fase pertama dikonfigurasi dengan `epochs=1` sehingga scheduler menghitung total langkah hanya untuk 1 epoch (4 step) yang menyebabkan learning rate meluruh lebih cepat dibanding run uninterrupted yang dikonfigurasi `epochs=2` (8 step). Solusinya, kedua fase pengujian diselaraskan menggunakan `epochs=2` dan fase pertama hanya mengeksekusi `train_one_epoch(1)` sebelum menyimpan checkpoint. Hasilnya, Epoch 2 pada run resumed terbukti 100% konsisten dengan run uninterrupted.

---

## 4. HASIL PENGUJIAN REGRESI LENGKAP (90/90 Unit Tests Lolos)

Pengujian regresi menyeluruh dijalankan pada CPU lokal:

```bash
python -m unittest discover tests
```

**Hasil Konsol:**
```text
Ran 90 tests in 16.597s
OK
```
- 36 Tes Data Pipeline (Anggota 1): Lolos 100%.
- 46 Tes Arsitektur Model & Inferensi (Anggota 2): Lolos 100%.
- 8 Tes Pipeline Training Baru (Anggota 3): Lolos 100%.

---

## 5. HASIL DIAGNOSTIK CPU (Tahap 3)

### A. Diagnostik A: Overfit Check 1 Batch
- **Tujuan**: Membuktikan bahwa arsitektur model, perhitungan CrossEntropyLoss, weight tying, dan optimasi AdamW benar-benar mampu belajar dan meminimalkan loss hingga konvergen pada data tetap.
- **Konfigurasi**: Batch Size = 4 (28 token target masked), Dropout = 0.0, Attention Dropout = 0.0, Weight Decay = 0.0, Learning Rate = 0.003, Device = CPU, Masking dibekukan.
- **Hasil Terukur**:
  * Step 000 (Awal) : Loss = **9.0233** | Top-1 Acc = **0.00%** | Top-5 Acc = **0.00%**
  * Step 010        : Loss = **3.0226** | Top-1 Acc = **92.86%** | Top-5 Acc = **100.00%**
  * Step 018        : Loss = **0.4121** | Top-1 Acc = **100.00%** | Top-5 Acc = **100.00%**
- **Kesimpulan**: Model berhasil konvergen di bawah ambang batas loss 0.5 hanya dalam 18 optimizer step (penurunan relative loss sebesar **95.43%** dalam durasi 0,85 detik).
- **Catatan Integritas**: Bobot hasil overfit check ini murni merupakan artefak diagnostik dan **dibuang (tidak digunakan untuk memulai baseline)**.

### B. Diagnostik B: Smoke Run Subset Kecil CPU
- **Tujuan**: Memverifikasi seluruh alur operasional perulangan epoch, logging, perhitungan metrik berbobot, pembuatan berkas history, penyimpanan atomic checkpoint, dan pemulihan resume tanpa menyentuh split Test.
- **Konfigurasi**: 32 chunk train, 16 chunk val, Batch Size = 4, Total Epoch = 2, Device = CPU.
- **Hasil Terukur**:
  * Epoch 1: Train Loss = 8.9487 (Top-1: 0.85%) | Val Loss = 8.8506 (Top-1: 2.94%)
  * Epoch 2: Train Loss = 8.8391 (Top-1: 4.24%) | Val Loss = 8.8065 (Top-1: 5.88%)
  * Durasi Total: 1.20 detik.
- **Integritas Artefak & Resume**:
  * Seluruh berkas (`checkpoint_epoch_001.pt`, `checkpoint_epoch_002.pt`, `best_checkpoint.pt`, `last_checkpoint.pt`, `training_history.json`, `training_history.csv`, dan `best_model/model.pt`) terbukti dibuat dengan sempurna.
  * Uji coba pemuatan `checkpoint_epoch_001.pt` berhasil melanjutkan Epoch 2 dengan metrik yang konsisten.

---

## 6. KESIAPAN SERAH TERIMA UNTUK ANGGOTA 2 (Tahap 4)

1. Dokumen serah terima telah disusun di [`docs/anggota_3/panduan_eksekusi_gpu.md`](file:///c:/Data%20C/%28%21%29%20Kampus/Semester%207/Gen%20AI/KELOMPOK%207/docs/anggota_3/panduan_eksekusi_gpu.md) berisi instruksi langkah demi langkah untuk mengeksekusi pelatihan GPU pada laptop Lenovo Legion RTX 4060 milik Anggota 2.
2. Draf konfigurasi baseline GPU disiapkan di [`configs/baseline_gpu.json`](file:///c:/Data%20C/%28%21%29%20Kampus/Semester%207/Gen%20AI/KELOMPOK%207/configs/baseline_gpu.json) (Batch Size = 32, Epoch = 5, LR = 3e-4, Warmup = 0.1, Linear Decay, AdamW).
3. Sesuai instruksi: **Pelatihan baseline penuh, eksperimen variasi hyperparameter, dan evaluasi akhir Test set belum dijalankan**, menunggu eksekusi GPU oleh Anggota 2.

---

## 7. TAHAP PENYEMPURNAAN PIPELINE PRA-SERAH TERIMA (Tahap 5 — Revisi 1)

Berdasarkan tinjauan mendalam atas kode aktual dan kebutuhan operasional di GPU Anggota 2, dilakukan 5 perbaikan krusial pada modul `src/training/`:

1. **Ekspor Bobot Murni dari Validation Epoch Terbaik (*Best Model Export Hardening*)**:
   - `Trainer` kini melacak `best_epoch`, `best_global_step`, `best_val_loss`, dan menyimpan `best_model_state_dict` (diduplikasi aman di memori CPU).
   - Ekspor ke `best_model/` dilakukan menggunakan model temporer yang dimuati `best_model_state_dict`, sehingga bobot model aktif, optimizer, scheduler, dan status training terakhir di `last_checkpoint.pt` tidak terganggu.
   - Pilihan `save_best_model` dan `save_last_checkpoint` dihormati secara ketat.

2. **Dukungan Resume pada Direktori yang Sama Tanpa `--overwrite`**:
   - Pemisahan eksplisit antara mode run baru, resume, dan overwrite.
   - Flag `is_resume=True` memungkinkan inisialisasi pada direktori yang sudah ada dan berisi berkas hasil tanpa memerlukan `--overwrite`.
   - Run baru tetap menolak direktori yang tidak kosong jika `--overwrite` tidak diberikan guna mencegah kecelakaan penghapusan data.

3. **Validasi Checkpoint Resume Ketat & Aman (`weights_only=True`)**:
   - Format checkpoint telah diuji dan terbukti 100% kompatibel dengan `weights_only=True` pada PyTorch (mencegah risiko eksekusi kode berbahaya).
   - Seluruh metadata diverifikasi sebelum memodifikasi state model/optimizer/RNG:
     * Kunci metadata wajib (`history`, `data_hashes`, dll.).
     * Hash berkas `train_chunks.jsonl` dan `val_chunks.jsonl` serta hash vocabulary kanonikal.
     * Batas sampel subset (`max_train_samples`, `max_val_samples`).
     * Seluruh kamus konfigurasi `MiniBertConfig` (menolak resume jika struktur arsitektur/dropout berbeda).
     * Hyperparameter kritis training (`batch_size`, `epochs`, `learning_rate`, `weight_decay`, `warmup_ratio`, `seeds`, `precision`).
   - Perbedaan device (misal CPU ke CUDA) diizinkan untuk portabilitas dan dicatat sebagai peringatan (*portability warning*).

4. **Riwayat Metrik Tahan Terputus (Atomic Per-Epoch History)**:
   - `training_history.json` dan `training_history.csv` diperbarui setelah setiap epoch menggunakan mekanisme berkas sementara `.tmp` lalu `os.replace`.
   - Riwayat disertakan dalam checkpoint. Saat resume, riwayat dipulihkan sehingga tidak ada epoch yang hilang atau terduplikasi.
   - Penolakan eksplisit diterapkan jika direktori memuat riwayat dari epoch yang lebih baru dari checkpoint yang di-resume guna mencegah pencampuran cabang run yang rusak.

5. **Subset Deterministik untuk Smoke Run**:
   - Parameter eksplisit `max_train_samples: 32` dan `max_val_samples: 16` ditambahkan pada `TrainingConfig` dan diterapkan via `torch.utils.data.Subset`.
   - Konfigurasi khusus `configs/gpu_smoke.json` dibuat dengan `output_dir: runs/gpu_smoke_run` agar hasil CPU tidak tertimpa.

---

## 8. HASIL VERIFIKASI AKHIR & STATUS REGRESI REVISI 1

### A. Pengujian Unit & Regresi Menyeluruh:
- **Perintah**: `python -m unittest discover tests`
- **Hasil**: **95/95 Unit Test Lolos (OK)** dalam 21.85 detik.
  * 36 Tes Data Pipeline (Anggota 1): Lolos 100%.
  * 46 Tes Arsitektur Model & Inferensi (Anggota 2): Lolos 100%.
  * 13 Tes Pipeline Training Komprehensif (Anggota 3): Lolos 100%.
    - `test_best_model_export_is_best_not_last`: Terbukti bobot ekspor identik dengan bobot epoch 1 (terbaik) dan berbeda dari bobot epoch 2 (terakhir).
    - `test_resume_in_same_directory_without_overwrite`: Terbukti resume berhasil pada direktori yang sama tanpa `--overwrite` dan menghasilkan riwayat 2 epoch tanpa duplikasi.
    - `test_checkpoint_validation_rejections`: Terbukti 6 skenario penolakan (metadata hilang, hash train berubah, LR berubah, dropout berubah, subset berubah, branch conflict) ditolak dengan eksepsi `ValueError` yang tepat.
    - `test_history_saved_per_epoch_and_atomic`: Terbukti berkas riwayat JSON dan CSV ditulis atomik setelah epoch 1.
    - `test_subset_config_limits`: Terbukti pembatasan subset 32 train / 16 val diterapkan deterministik pada DataLoader.

### B. Hasil CPU Smoke Run Aktual (`runs/cpu_smoke_run/`):
- **Perintah**: `python -m src.training.run_experiment --config configs/cpu_smoke.json`
- **Konfigurasi**: 32 train, 16 val, Batch Size 4, Epochs 2, Device CPU.
- **Hasil Terukur**:
  * Epoch 1: Train Loss = 8.9487 (Top-1: 0.85%) | Val Loss = 8.8506 (Top-1: 2.94%)
  * Epoch 2: Train Loss = 8.8391 (Top-1: 4.24%) | Val Loss = 8.8065 (Top-1: 5.88%)
  * Best Val Loss: **8.8065** (Epoch 2, Global Step 16).
  * Durasi Total: 1.13 detik.

### C. Hasil Verifikasi Jalur CLI Resume:
- **Skenario**: Run Fase 1 (1 epoch) -> Uji penolakan run baru tanpa `--overwrite` (Lolos `FileExistsError`) -> Resume via `--resume-from` tanpa `--overwrite` -> Selesai hingga Epoch 2.
- **Hasil**: Riwayat akhir di disk memuat tepat 2 epoch (Epoch 1 & Epoch 2) tanpa duplikasi baris, dan `best_model/model.pt` diekspor dengan status `"trained"`.

---

## 9. TAHAP ANALISIS BASELINE GPU & PENYIAPAN EKSPERIMEN PEMBANDING (Tahap 6)

### A. Rangkuman Penerimaan Hasil Baseline GPU dari Anggota 2:
1. Pelatihan baseline selesai 100% pada laptop Lenovo Legion RTX 4060 Anggota 2 (5 epoch, 4.220 optimizer step, durasi total 80.19 detik).
2. Verifikasi berkas riwayat aktual (`runs/baseline_gpu/training_history.json`):
   * Epoch 1: Train Loss = 7.2275 (Top-1: 6.29%) | Val Loss = 6.6225 (Top-1: 9.11%)
   * Epoch 2: Train Loss = 6.5266 (Top-1: 9.44%) | Val Loss = 6.3302 (Top-1: 11.42%)
   * Epoch 3: Train Loss = 6.2990 (Top-1: 11.11%) | Val Loss = 6.1648 (Top-1: 12.47%)
   * Epoch 4: Train Loss = 6.1782 (Top-1: 12.23%) | Val Loss = 6.0694 (Top-1: 13.29%)
   * Epoch 5: Train Loss = 6.0957 (Top-1: 12.95%) | Val Loss = **6.0361** (Top-1: **13.79%**, Top-5: **28.24%**)
3. Model inferensi terbaik (`runs/baseline_gpu/best_model/model.pt`) berstatus `"trained"` dengan bobot bit-per-bit identik terhadap bobot epoch 5.

### B. Evaluasi Baseline Frekuensi Token Unigram (Train Only):
- Dihitung dari 1.436.788 token pada split Train (tanpa special tokens).
- Top-5 token paling sering di Train: `,` (6.03%), `.` (5.08%), `yang` (2.74%), `dan` (2.62%), `-` (1.76%).
- Dievaluasi pada 20.627 target validasi deterministik yang sama:
  * Baseline Frekuensi Loss: **6.7852** (Perplexity: 884.66).
  * Baseline Frekuensi Top-1: **6.60%** (1.362 / 20.627).
  * Baseline Frekuensi Top-5: **18.95%** (3.908 / 20.627).
- **Pembuktian**: Model Mini-BERT (Loss 6.0361, Top-1 13.79%, Top-5 28.24%) terbukti melampaui tebakan frekuensi unigram secara signifikan (+7.19% Top-1, +9.29% Top-5).

### C. Analisis Dekomposisi Kata Leksikal vs Tanda Baca:
- Target Kata Leksikal (17.125 target / 83.02%): Model mencapai Top-1 **6.66%** dan Top-5 **16.22%** (melampaui frekuensi unigram Top-1 0.00% dan Top-5 6.67%).
- Target Tanda Baca (3.502 target / 16.98%): Model mencapai Top-1 **48.66%** dan Top-5 **87.01%** (melampaui frekuensi unigram Top-1 38.89% dan Top-5 78.98%).
- **Temuan**: Sebanyak 59.9% dari total tebakan Top-1 model yang benar berasal dari tanda baca. Ini menjelaskan mengapa contoh inferensi kualitatif masih didominasi tanda baca (`,` dan `.`) dan kata tugas umum (`di`, `yang`, `dan`).

### D. Rancangan Eksperimen Pembanding LR = 1e-3:
- Berkas konfigurasi: [`configs/lr_1e3_gpu.json`](file:///c:/Data%20C/%28%21%29%20Kampus/Semester%207/Gen%20AI/KELOMPOK%207/configs/lr_1e3_gpu.json).
- Parameter kontrol: 5 epoch, batch size 32, arsitektur sama, seed sama, data sama, output dir `runs/lr_1e3_gpu/`.
- Memulai dari bobot acak baru (`model_seed: 42`).
- Perintah GPU Anggota 2:
  `.\.venv-gpu\Scripts\python.exe -m src.training.run_experiment --config configs/lr_1e3_gpu.json`
- Laporan lengkap dan grafik visualisasi didokumentasikan di [`docs/anggota_3/analisis_baseline_dan_komparasi.md`](file:///c:/Data%20C/%28%21%29%20Kampus/Semester%207/Gen%20AI/KELOMPOK%207/docs/anggota_3/analisis_baseline_dan_komparasi.md).

---

## 10. TAHAP EVALUASI EKSPERIMEN PEMBANDING, PENGUNCIAN MODEL FINAL, & PENYIAPAN EVALUASI TEST (Tahap 7)

### A. Evaluasi Hasil Aktual Eksperimen Pembanding LR 1e-3:
1. Pelatihan LR 1e-3 selesai pada GPU RTX 4060 Anggota 2 (5 epoch, 4.220 steps, durasi 140.86 detik).
2. Verifikasi metrik aktual `runs/lr_1e3_gpu/training_history.json`:
   * Validation Loss terbaik: **5.496227** pada Epoch 5.
   * Validation Top-1 Accuracy: **18.0492%** (3.723 / 20.627 target).
   * Validation Top-5 Accuracy: **32.6562%** (6.736 / 20.627 target).
   * Effective Masked Perplexity: **243.77** (turun 174.50 poin dari baseline).
3. Perbandingan berpasangan terhadap Baseline (LR 3e-4):
   * Validation Loss membaik sebesar **-0.5399 nats**.
   * Validation Top-1 meningkat sebesar **+4.26 poin persentase (pp)** (+30.89% relatif).
   * Validation Top-5 meningkat sebesar **+4.42 poin persentase (pp)** (+15.65% relatif).
   * Akurasi kata leksikal murni naik dari 6.66% ke 10.72% (+4.06 pp).
4. Pembuatan grafik kurva perbandingan resmi di [`docs/anggota_3/kurva_perbandingan_lr.png`](file:///c:/Data%20C/%28%21%29%20Kampus/Semester%207/Gen%20AI/KELOMPOK%207/docs/anggota_3/kurva_perbandingan_lr.png).

### B. Penguncian Model Final (*Model Freezing Protocol*):
- Berdasarkan keunggulan konsisten pada split validasi, model `runs/lr_1e3_gpu/best_model` (Epoch 5) **resmi dikunci sebagai model final**.
- Dokumen penguncian resmi disahkan di [`docs/anggota_3/penguncian_model_final.md`](file:///c:/Data%20C/%28%21%29%20Kampus/Semester%207/Gen%20AI/KELOMPOK%207/docs/anggota_3/penguncian_model_final.md).
- Hash integritas dikunci:
  * `model.pt`: `0c0de0b0b88f51b5d7dfc474a3dc8bcbfe6d86d3c527e30869fd28eccb1ef8b8`
  * `config.json`: `521a31762dea889dc6ae865d9ad20816b90cecc35eb8212b2b725445a51f3026`
  * `vocab.json` canonical: `d2be29d07e76fe0cd15c3fe1b765325a5397a5e5fe30b2c6a5a019c976c552f2`
- Komitmen metodologis: Keputusan pemilihan model ini **tidak akan diubah berdasarkan hasil test** guna mencegah bias *post-hoc data snooping*.

### C. Pembuatan & Pengujian Skrip Evaluator Test Independen:
- Skrip evaluasi final dibangun di [`src/training/evaluate_test.py`](file:///c:/Data%20C/%28%21%29%20Kampus/Semester%207/Gen%20AI/KELOMPOK%207/src/training/evaluate_test.py).
- Karakteristik: Memuat model terpilih murni pada `model.eval()` dan `torch.inference_mode()`, menangani 3.427 chunk sumber menjadi 3.426 chunk siap MLM (1 chunk zero-candidates disaring otomatis sesuai manifest), menggunakan `MLMDataCollator(mode="eval", eval_seed=42)` dengan aturan 80/10/10 deterministik, dan mencatat seluruh hash integritas.
- Pengujian logika evaluator pada split validasi (tanpa membuka test) mereproduksi hasil secara 100% identik bit-per-bit (Loss: 5.496226, Top-1: 18.0492%, Top-5: 32.6562%).
- Split Test tetap steril dan belum dibuka.

### D. Keterbatasan Metodologis yang Didokumentasikan:
1. Satu seed pelatihan (`model_seed: 42`).
2. Kosakata word-level tanpa mekanisme subword.
3. Pengecualian token UNK dari target MLM.
4. Dominasi tanda baca pada logits prior kalimat terbuka pendek.

### E. Kesiapan Serah Terima ke Anggota 2:
- Panduan eksekusi GPU Langkah 4 telah diperbarui di [`docs/anggota_3/panduan_eksekusi_gpu.md`](file:///c:/Data%20C/%28%21%29%20Kampus/Semester%207/Gen%20AI/KELOMPOK%207/docs/anggota_3/panduan_eksekusi_gpu.md).
- Perintah GPU Anggota 2:
  `.\.venv-gpu\Scripts\python.exe -m src.training.evaluate_test --model-dir runs/lr_1e3_gpu/best_model --test-file test_chunks.jsonl --device cuda`

---

## 11. SESI FINALISASI: PENERIMAAN HASIL EVALUASI TEST FINAL & SINTESIS ANALISIS

* **Waktu**: 26 Oktober 2026
* **Pelaksana**: Anggota 3
* **Fokus**: Verifikasi menyeluruh hasil evaluasi split test dari laptop GPU Anggota 2, koreksi laporan, penyusunan dokumen pembahasan akhir, pembuatan grafik akhir antar-split, dan ekspor percakapan Markdown.

### A. Verifikasi Hasil Uji Test Split:
1. Pembacaan berkas hasil aktual:
   - `runs/lr_1e3_gpu/final_test_evaluation.json`
   - `runs/lr_1e3_gpu/final_test_evaluation.csv`
   - `docs/anggota_3/final_test_terminal.log`
2. Konfirmasi Metrik Test ($N = 27.071$ target bertopeng, 3.426 chunk dievaluasi, 1 chunk zero-candidates `doc_id="3792"` disaring):
   - **Masked Cross-Entropy Loss**: `5.494842 nats` (vs Validasi `5.496227 nats`, selisih `-0.0014 nats`).
   - **$\exp(\text{masked-token loss})$**: `243.4330` (vs Validasi `243.77`).
   - **Top-1 Accuracy**: `17.4430%` (4.722 / 27.071 target; vs Validasi `18.05%`, selisih `-0.61 pp`).
   - **Top-5 Accuracy**: `31.7535%` (8.596 / 27.071 target; vs Validasi `32.66%`, selisih `-0.91 pp`).
3. Verifikasi Hash Kriptografis Model:
   - `model.pt`: `0c0de0b0b88f51b5d7dfc474a3dc8bcbfe6d86d3c527e30869fd28eccb1ef8b8` (Lolos verifikasi, identik dengan dokumen penguncian).
   - `config.json`: `521a31762dea889dc6ae865d9ad20816b90cecc35eb8212b2b725445a51f3026` (Lolos verifikasi).
   - `vocab.json`: `d2be29d07e76fe0cd15c3fe1b765325a5397a5e5fe30b2c6a5a019c976c552f2` (Lolos verifikasi).
   - Catatan Transparansi Data Test: SHA-256 byte riil dari berkas fisik `data/processed/pilot/test_chunks.jsonl` adalah `f82e9d06e1f2c8aac888195c926f61db42eec75c75f685ceb68202b8b9c4f868`.

### B. Tindakan Koreksi dan Pembaruan Dokumen:
1. **Koreksi Laporan Evaluasi Test** ([`docs/anggota_3/laporan_evaluasi_final_test.md`](file:///c:/Data%20C/%28%21%29%20Kampus/Semester%207/Gen%20AI/KELOMPOK%207/docs/anggota_3/laporan_evaluasi_final_test.md)):
   - Menghapus klaim overclaiming seperti "generalisasi sangat kuat" atau "membuktikan ketiadaan kebocoran/overfitting".
   - Menyajikan kesimpulan proporsional bahwa performa test konsisten dengan validasi pada korpus dan protokol ini, namun tidak membuktikan ketiadaan data leakage secara mutlak maupun pemahaman semantik bahasa secara umum.
   - Menjelaskan perbedaan kondisi pengukuran: Split train dihitung online selama optimasi (dropout aktif 0.1, bobot terus bergerak, masking dinamis), bukan evaluasi ulang model statis seperti pada validasi dan test.
   - Mengoreksi tautan path lokal laptop Anggota 2 menjadi tautan relatif/absolut workspace.
2. **Penyusunan Dokumen Pembahasan Hasil Akhir** ([`docs/anggota_3/pembahasan_hasil_akhir.md`](file:///c:/Data%20C/%28%21%29%20Kampus/Semester%207/Gen%20AI/KELOMPOK%207/docs/anggota_3/pembahasan_hasil_akhir.md)):
   - Membahas tujuan, variabel terkontrol, perbandingan kuantitatif baseline vs pembanding, alasan penguncian model, hasil test split, komparasi dengan baseline frekuensi unigram (unigram Top-1 6.60% vs model 18.05%), dekomposisi leksikal vs tanda baca (tanda baca 53.88% vs non-tanda-baca 10.72%), error analysis, serta 6 keterbatasan metodologis.
   - Membedakan hasil terukur dari dugaan penyebab.
   - Menegaskan batas terminologi: $\exp(\text{masked loss})$ bukan perplexity autoregresif teks penuh atau pseudo-perplexity standar; target non-tanda-baca dijelaskan cakupannya (konten leksikal, kata fungsi/tugas, dan angka).
3. **Pembuatan Grafik Komparasi Antar-Split** ([`docs/anggota_3/evaluasi_final_split_test.png`](file:///c:/Data%20C/%28%21%29%20Kampus/Semester%207/Gen%20AI/KELOMPOK%207/docs/anggota_3/evaluasi_final_split_test.png)):
   - Visualisasi berdampingan Train vs Validasi vs Test dengan catatan kondisi pengukuran di bagian bawah gambar dan tanpa error bar dari single run.
4. **Ekspor Transkrip Percakapan Markdown** ([`docs/anggota_3/transkrip_percakapan_anggota3.md`](file:///c:/Data%20C/%28%21%29%20Kampus/Semester%207/Gen%20AI/KELOMPOK%207/docs/anggota_3/transkrip_percakapan_anggota3.md)):
   - Sebanyak 756 langkah interaksi diekspor secara transparan ke berkas Markdown terstruktur (208 KB).

---

## 12. RINGKASAN KONTRIBUSI ANGGOTA 3 DAN BATAS KOLABORASI

### A. Kontribusi Nyata Anggota 3:
1. **Pipeline Pelatihan & Modul Pelatihan**:
   - Merancang dan mengimplementasikan seluruh modul `src/training/` (`trainer.py`, `checkpoint.py`, `metrics.py`, `lr_scheduler.py`, `evaluate_test.py`).
   - Menyediakan mekanisme logging langkah per-batch (`log_every_n_steps=25`), akumulasi statistik target bertopeng riil, dan penanganan presisi `float32`.
2. **Mekanisme Checkpointing & Resuming Kuat**:
   - Membangun penyimpanan atomic berbasis temporary file dan copy-on-replace.
   - Menjamin isolasi ekspor `best_model/` murni dari epoch dengan validation loss terbaik tanpa merusak state training `last_checkpoint/`.
   - Mengintegrasikan penyimpanan dan pemulihan RNG state (PyTorch CPU, PyTorch CUDA, Python random, NumPy).
3. **Pengujian Regresi Mandiri (Unit Testing)**:
   - Membangun dan memelihara 95 unit test otomatis (`tests/`) yang memverifikasi matematika metrik, scheduler, checkpointing, tokenizer determinisme, collator MLM, dan evaluasi mandiri.
4. **Eksperimentasi & Tuning Hiperparameter**:
   - Merancang konfigurasi baseline GPU (`LR = 3e-4`) dan eksperimen pembanding (`LR = 1e-3`).
   - Menetapkan protokol penguncian model (*model freezing*) yang ketat sebelum evaluasi test.
5. **Evaluasi Mandiri, Analisis Komparatif, & Visualisasi**:
   - Membangun baseline frekuensi unigram dari data train saja untuk membuktikan keunggulan kontekstual model di atas frekuensi kata.
   - Melakukan dekomposisi kinerja target tanda baca vs target non-tanda-baca.
   - Membangun skrip evaluasi independen `evaluate_test.py` yang steril dari proses optimasi.
   - Menyusun seluruh laporan analisis metodologis, panduan eksekusi GPU, dan visualisasi grafik beresolusi tinggi.

### B. Batas Kolaborasi dan Pengakuan Kontribusi Anggota Lain:
- **Anggota 1**: Bertanggung jawab penuh atas akuisisi data, pembersihan korpus, tokenisasi word-level, pembuatan kosakata kanonikal 8.000 kata, pemecahan split (train, validation, test), serta chunking teks (`src/data/`). Anggota 3 tidak mengklaim pembuatan korpus atau kosakata.
- **Anggota 2**: Bertanggung jawab atas desain awal arsitektur model Mini-BERT (`src/models/`), kontrak model, dan penyediaan perangkat keras akselerasi GPU (Lenovo Legion Slim 5, NVIDIA RTX 4060 Laptop GPU 8GB) yang mengeksekusi kedua run pelatihan (4.220 steps) serta eksekusi inferensi evaluasi split test. Anggota 3 merancang kode dan konfigurasinya, sedangkan eksekusi GPU dilakukan oleh Anggota 2.




