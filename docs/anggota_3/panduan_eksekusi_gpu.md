# PANDUAN EKSEKUSI TRAINING GPU (ANGGOTA 3 KE ANGGOTA 2) — REVISI 1

* **Tanggal Dokumen**: 24 Oktober 2026
* **Penulis**: Anggota 3 (Training Loop, Hyperparameter Tuning, & Evaluasi Lead)
* **Penerima**: Anggota 2 (Arsitektur Model & Hardware Lead — Eksekutor GPU RTX 4060)
* **Status Modul**: Teruji 100% pada CPU Lokal (95/95 Unit Test Lolos, Diagnostik Overfit & CPU Smoke Selesai)
* **Target Eksekusi**: Laptop Lenovo Legion Slim 5 milik Anggota 2 (NVIDIA GeForce RTX 4060 Laptop GPU, 8 GB VRAM)
* **Interpreter Target**: `.\.venv-gpu\Scripts\python.exe`

---

## 1. Ringkasan Modul & Pembaruan Pipeline Training (Revisi 1)

Modul pelatihan di `src/training/` telah disempurnakan dan diperketat sebelum diserahkan untuk eksekusi GPU:

1. **Ekspor Model Terbaik Murni (*True Best Model Export*)**:
   - Direktori `best_model/` murni mengekspor bobot dari epoch dengan nilai *validation loss* terendah (bukan sekadar bobot epoch terakhir).
   - Penentuan model terbaik hanya menggunakan validation split; split Test **tidak pernah disentuh**.
   - Bobot model aktif, optimizer, scheduler, dan RNG state pada akhir pelatihan tetap terjaga utuh pada `last_checkpoint.pt` untuk kebutuhan resume.
   - Laporan metrik (`training_history.json` & CSV) mencatat `best_epoch`, `best_global_step`, dan `best_val_loss`.

2. **Resume ke Direktori Run yang Sama Tanpa `--overwrite`**:
   - Pembedaan eksplisit antara run baru, resume, dan overwrite.
   - Perintah resume dapat langsung menggunakan direktori run asal tanpa flag `--overwrite`.
   - Run baru tetap memproteksi direktori yang sudah berisi hasil (menolak penimpaan tidak sengaja kecuali `--overwrite` eksplisit diberikan).
   - Riwayat metrik lama dipulihkan dari checkpoint dan dipertahankan tanpa duplikasi baris.

3. **Validasi Ketat Integritas Checkpoint Resume (`weights_only=True`)**:
   - Pemuatan checkpoint menggunakan standar aman `weights_only=True`.
   - Validasi pra-pemuatan memverifikasi: metadata wajib lengkap, hash vocabulary kanonikal, hash berkas train dan val, batas subset data, seluruh konfigurasi model (`MiniBertConfig`), serta hyperparameter kritis training (`batch_size`, `epochs`, `learning_rate`, `weight_decay`, `warmup_ratio`, `seeds`, `precision`).
   - Perubahan device dicatat sebagai peringatan portabilitas (kesetaraan numerik bit-per-bit tidak dijanjikan lintas backend hardware).
   - Menolak resume jika direktori target memuat riwayat dari epoch yang lebih baru dari checkpoint (mencegah pencampuran cabang run).

4. **Penyimpanan Riwayat Metrik Per-Epoch Secara Atomik**:
   - Berkas `training_history.json` dan `training_history.csv` diperbarui setelah *setiap epoch* selesai melalui berkas sementara `.tmp` lalu `os.replace`.

5. **Subset Deterministik untuk Smoke Run**:
   - Parameter konfigurasi eksplisit `max_train_samples: 32` dan `max_val_samples: 16` pada `configs/gpu_smoke.json` dan `configs/cpu_smoke.json`.
   - Baseline penuh (`configs/baseline_gpu.json`) menggunakan seluruh 27.002 chunks train dan 2.685 chunks val (`null`).

---

## 2. Verifikasi Integritas Data & Hash Vocabulary Sebelum Training

Jalankan perintah verifikasi berikut pada terminal PowerShell di direktori akar repositori:

```powershell
# Verifikasi Hash SHA-256 Kanonikal Vocabulary menggunakan interpreter GPU
.\.venv-gpu\Scripts\python.exe -c "from src.models.config import MiniBertConfig; cfg = MiniBertConfig.from_tokenizer_directory('data/processed/pilot'); print('Vocab Hash:', cfg.vocab_sha256)"
```

**Hasil yang Wajib Muncul:**
```text
Vocab Hash: d2be29d07e76fe0cd15c3fe1b765325a5397a5e5fe30b2c6a5a019c976c552f2
```

---

## 3. Langkah 1: Uji Singkat GPU Smoke Test (Pra-Baseline)

Jalankan pengujian smoke GPU pada subset kecil (32 train, 16 val, batch size 4, 2 epoch) untuk memverifikasi alokasi VRAM, backward pass, dan optimizer step di CUDA:

```powershell
.\.venv-gpu\Scripts\python.exe -m src.training.run_experiment --config configs/gpu_smoke.json
```

*Catatan: Konfigurasi ini secara otomatis menulis ke direktori terpisah `runs/gpu_smoke_run/` sehingga tidak menimpa hasil smoke CPU lokal.*

**Kriteria Lolos Uji GPU Smoke:**
1. Eksekusi berjalan pada `Device: cuda`.
2. Total chunks train = 32 (8 batch), val = 16 (4 batch).
3. Loss awal berada di kisaran ~9.01 (sesuai entropi acak $\ln(8000) \approx 8.987$).
4. Tidak ada galat `CUDA out of memory` atau tensor NaN/Inf.
5. Selesai dalam beberapa detik dan menghasilkan:
   - `runs/gpu_smoke_run/checkpoints/checkpoint_epoch_001.pt`
   - `runs/gpu_smoke_run/checkpoints/checkpoint_epoch_002.pt`
   - `runs/gpu_smoke_run/checkpoints/last_checkpoint.pt`
   - `runs/gpu_smoke_run/checkpoints/best_checkpoint.pt`
   - `runs/gpu_smoke_run/best_model/model.pt` & `config.json`
   - `runs/gpu_smoke_run/training_history.json` & `training_history.csv`

---

## 4. Langkah 2: Eksekusi Pelatihan Baseline GPU Utama

Setelah uji GPU smoke berhasil, jalankan pelatihan baseline 5 epoch penuh:

```powershell
.\.venv-gpu\Scripts\python.exe -m src.training.run_experiment --config configs/baseline_gpu.json
```

### Rincian Konfigurasi Baseline GPU (`configs/baseline_gpu.json`):
- **Device**: `cuda` (NVIDIA RTX 4060 Laptop 8GB VRAM)
- **Train Data**: 27.002 chunks (`max_train_samples: null`)
- **Val Data**: 2.685 chunks (`max_val_samples: null`)
- **Batch Size**: `32` (~844 batch per epoch)
- **Total Epochs**: `5` (total ~4.220 optimizer steps)
- **Learning Rate**: `3e-4` (`0.0003`)
- **Optimizer**: `AdamW` (Weight decay `0.01` untuk matriks bobot, `0.0` untuk bias & LayerNorm)
- **Warmup Ratio**: `0.1` (422 step warmup linear, dilanjutkan linear decay ke 0.0)
- **Gradient Clipping**: `max_norm = 1.0`
- **Precision**: `float32` murni
- **Random Seeds**: Model Seed = 42, Shuffle Seed = 42, Masking Seed = 42, Eval Seed = 42
- **Direktori Output**: `runs/baseline_gpu/`

> **Estimasi VRAM**: ~1.5 - 2.5 GB (sangat aman di bawah kapasitas 8 GB VRAM RTX 4060).

---

## 5. Prosedur Resume Pelatihan (Jika Terputus)

Jika proses pelatihan baseline terhenti di tengah jalan (misalnya akibat interupsi daya, sistem reboot, atau penghentian manual), **JANGAN MENGULANG DARI AWAL** dan **JANGAN MENAMBAHKAN FLAG `--overwrite`**.

Jalankan perintah resume berikut:

```powershell
.\.venv-gpu\Scripts\python.exe -m src.training.run_experiment --config configs/baseline_gpu.json --resume-from runs/baseline_gpu/checkpoints/last_checkpoint.pt
```

### Batasan dan Perlindungan Mekanisme Resume:
1. **Kesesuaian Konfigurasi Kritis**:
   - Checkpoint memvalidasi bahwa `batch_size`, `learning_rate`, `epochs`, `weight_decay`, `warmup_ratio`, `precision`, dan `seeds` persis sama dengan konfigurasi saat checkpoint disimpan.
   - Jangan mengubah konfigurasi jadwal atau total epoch pada run yang sedang dilanjutkan.
2. **Kesesuaian Data & Vocabulary**:
   - Berkas data `train_chunks.jsonl` dan `val_chunks.jsonl` serta vocabulary harus memiliki hash yang identik.
3. **Pencegahan Konflik Cabang Riwayat**:
   - Jika direktori `runs/baseline_gpu/` sudah memiliki riwayat hingga Epoch 3, Anda tidak dapat me-resume checkpoint Epoch 1 ke direktori yang sama karena akan merusak linearitas riwayat.
4. **Preservasi State**:
   - Bobot model terbaik (`best_model_state_dict` dan `best_val_loss`) sebelum interupsi akan dipulihkan secara utuh sehingga ekspor akhir tetap merefleksikan model terbaik sesungguhnya.

---

## 6. Langkah 3: Eksekusi Eksperimen Pembanding GPU (Learning Rate = 1e-3)

Setelah pelatihan baseline (`LR=3e-4`) selesai dievaluasi, Anggota 3 menyiapkan **satu eksperimen pembanding terisolasi** untuk menguji pengaruh laju pembelajaran yang lebih agresif (`LR=1e-3`) terhadap percepatan konvergensi dan representasi kata leksikal.

> **PENTING**:
> - Pelatihan ini **TIDAK melanjutkan checkpoint baseline**, melainkan **dimulai murni dari bobot acak baru** (`model_seed: 42`).
> - Seluruh parameter lainnya (5 epoch, batch size 32, arsitektur 2 layer, warmup ratio 0.1, precision float32) tetap identik.
> - Menggunakan direktori output baru: `runs/lr_1e3_gpu/`.

Jalankan perintah berikut pada terminal PowerShell:

```powershell
.\.venv-gpu\Scripts\python.exe -m src.training.run_experiment --config configs/lr_1e3_gpu.json
```

*Estimasi Waktu Eksekusi: ~80 - 90 detik di GPU RTX 4060 Laptop.*

### Prosedur Resume Eksperimen Pembanding (Jika Terputus):
Jika eksekusi eksperimen pembanding terhenti di tengah jalan, lanjutkan dengan perintah berikut (tanpa flag `--overwrite`):

```powershell
.\.venv-gpu\Scripts\python.exe -m src.training.run_experiment --config configs/lr_1e3_gpu.json --resume-from runs/lr_1e3_gpu/checkpoints/last_checkpoint.pt
```

---

## 7. Langkah 4: Eksekusi Evaluasi Final pada Split Test (Model Terkunci)

Berdasarkan perbandingan objektif metrik validasi, model **`runs/lr_1e3_gpu/best_model` (Epoch 5)** telah **resmi dikunci** melalui dokumen penguncian model ([penguncian_model_final.md](file:///c:/Data%20C/%28%21%29%20Kampus/Semester%207/Gen%20AI/KELOMPOK%207/docs/anggota_3/penguncian_model_final.md)).

Anggota 2 dipersilakan menjalankan evaluasi final pada split Test steril (`test_chunks.jsonl` — 3.427 chunk fisik, 3.426 chunk siap MLM) menggunakan skrip evaluator independen `src/training/evaluate_test.py`:

```powershell
.\.venv-gpu\Scripts\python.exe -m src.training.evaluate_test --model-dir runs/lr_1e3_gpu/best_model --test-file test_chunks.jsonl --device cuda
```

*Estimasi Waktu Eksekusi: ~5 - 10 detik di GPU RTX 4060 Laptop.*

### Karakteristik & Perlindungan Skrip Evaluasi:
1. Beroperasi murni pada `model.eval()` dan `torch.inference_mode()` tanpa ada pembaruan bobot atau optimizer.
2. Memuat dataset uji dan secara otomatis menyaring 1 chunk sumber (`doc_id="3792"`) yang tidak memiliki kandidat reguler (sesuai `mlm_excluded_chunks_manifest.json`), sehingga mengevaluasi tepat **3.426 chunk MLM siap uji**.
3. Menghitung Cross-Entropy Loss, Akurasi Top-1, dan Akurasi Top-5 berbobot.
4. Laporan hasil evaluasi test otomatis disimpan ke:
   - `runs/lr_1e3_gpu/final_test_evaluation.json`
   - `runs/lr_1e3_gpu/final_test_evaluation.csv`

---

## 8. Berkas & Artefak yang Wajib Dikirim Kembali ke Anggota 3

Setelah eksekusi evaluasi selesai, kirimkan kembali paket berkas berikut kepada Anggota 3 (arsip ZIP tanpa folder `.venv`, dataset mentah, atau file temporer):

1. **Hasil Evaluasi Test Final**:
   - `runs/lr_1e3_gpu/final_test_evaluation.json`
   - `runs/lr_1e3_gpu/final_test_evaluation.csv`
2. **Model Terbaik Terkunci**:
   - `runs/lr_1e3_gpu/best_model/model.pt` & `config.json`
3. **Riwayat Metrik Pelatihan Kedua Run**:
   - `runs/baseline_gpu/training_history.json` & `.csv`
   - `runs/lr_1e3_gpu/training_history.json` & `.csv`
4. **Log Konsol Terminal**:
   - Salinan teks output konsol terminal selama evaluasi test berlangsung.

---

## 9. Kebijakan Integritas & Anti-Data-Snooping

* **Model Tetap Terkunci**: Apapun angka metrik yang dihasilkan pada split Test nantinya, keputusan pemilihan model `runs/lr_1e3_gpu/best_model` **tidak akan diubah, diganti, atau diulang-ulang**, guna menjamin estimasi generalisasi yang sepenuhnya jujur dan bebas bias metodologis.


