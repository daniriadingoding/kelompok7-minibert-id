# LAPORAN HASIL EVALUASI FINAL TEST MODEL MINI-BERT BAHASA INDONESIA

* **Tanggal Evaluasi**: 24 Oktober 2026
* **Pelaksana**: Anggota 2 (Eksekusi GPU pada Lenovo Legion Slim 5) menggunakan skrip dan konfigurasi Anggota 3 (Evaluasi & Training Lead)
* **Model Teruji**: `runs/lr_1e3_gpu/best_model` (Epoch 5, ukuran berkas bobot: 5.828.097 byte)
* **Status Model**: Resmi Dikunci Sebelum Evaluasi Test (*Model Freezing Protocol*, tanpa penyesuaian bobot atau tuning ulang)
* **Berkas Log Terminal**: [`docs/anggota_3/final_test_terminal.log`](file:///c:/Data%20C/(!)%20Kampus/Semester%207/Gen%20AI/KELOMPOK%207/docs/anggota_3/final_test_terminal.log)
* **Laporan JSON Resmi**: [`runs/lr_1e3_gpu/final_test_evaluation.json`](file:///c:/Data%20C/(!)%20Kampus/Semester%207/Gen%20AI/KELOMPOK%207/runs/lr_1e3_gpu/final_test_evaluation.json)
* **Laporan CSV Resmi**: [`runs/lr_1e3_gpu/final_test_evaluation.csv`](file:///c:/Data%20C/(!)%20Kampus/Semester%207/Gen%20AI/KELOMPOK%207/runs/lr_1e3_gpu/final_test_evaluation.csv)

---

## 1. Verifikasi Integritas Pra-Evaluasi

Sebelum evaluasi inferensi dijalankan pada akselerator GPU, seluruh hash kriptografis diverifikasi oleh skrip evaluator:

1. **Bobot Model (`model.pt`)**:
   `0c0de0b0b88f51b5d7dfc474a3dc8bcbfe6d86d3c527e30869fd28eccb1ef8b8` (Ukuran: 5.828.097 byte, Cocok 100% dengan dokumen penguncian model).
2. **Konfigurasi Model (`config.json`)**:
   `521a31762dea889dc6ae865d9ad20816b90cecc35eb8212b2b725445a51f3026` (Ukuran: 349 byte, Cocok 100% dengan dokumen penguncian model).
3. **Hash Kanonikal Kosakata (`vocab.json` / `vocab.txt`)**:
   `d2be29d07e76fe0cd15c3fe1b765325a5397a5e5fe30b2c6a5a019c976c552f2` (8.000 kata, Cocok).
4. **Dataset Split Test (`test_chunks.jsonl`)**:
   `f82e9d06e1f2c8aac888195c926f61db42eec75c75f685ceb68202b8b9c4f868` (Ukuran: 2.196.608 byte).
   *Catatan Verifikasi Hash Data*: Nilai SHA-256 byte di atas adalah hash fisik aktual dari berkas `data/processed/pilot/test_chunks.jsonl` yang dibaca langsung oleh evaluator. Nilai berbeda yang sempat tercatat pada tabel dokumen draf penguncian merupakan kekeliruan administratif saat split test masih terkunci rapat dan belum dibuka.

---

## 2. Lingkungan Eksekusi & Parameter Evaluasi

* **Device Komputasi**: `cuda` (NVIDIA GeForce RTX 4060 Laptop GPU, 8 GB VRAM)
* **Runtime CUDA**: `12.4`
* **Versi PyTorch**: `2.6.0+cu124`
* **Versi Python**: `3.13.2`
* **Batch Size**: `32`
* **Eval Seed**: `42` (Aturan masking deterministik 80/10/10)
* **Status Mode**: `model.eval()` dan `torch.inference_mode()` murni tanpa pembaruan optimizer, pembaruan bobot, atau mutasi state model.

---

## 3. Penyaringan Chunk Dataset Sesuai Manifest

Penyaringan dataset uji berlangsung konsisten sesuai kontrak `data/processed/pilot/mlm_excluded_chunks_manifest.json`:
* **Total Chunk Fisik Sumber**: 3.427 chunk.
* **Chunk Siap Evaluasi MLM**: 3.426 chunk.
* **Chunk Dikeluarkan (Zero Candidates)**: Tepat 1 chunk disaring otomatis:
  * Identitas: `doc_id="3792"`, `chunk_index=3`, baris fisik ke-2.544.
  * Alasan: Seluruh 24 token isi adalah token khusus atau `[UNK]` (ID < 5), sehingga tidak ada kandidat token reguler yang valid sebagai target masking MLM.

---

## 4. Hasil Metrik Evaluasi Final Test

Inferensi selesai dalam waktu 1,04 detik dengan kecepatan komputasi 3.281,1 chunk per detik:

| Metrik Evaluasi | Hasil Terukur pada Split Test | Penyebut / Satuan | Keterangan |
| :--- | :---: | :---: | :--- |
| **Total Target Token Evaluasi** | **27.071** target | Token target | Jumlah token reguler bertopeng deterministik |
| **Masked Cross-Entropy Loss** | **5.494842** | nats / token | Rata-rata Cross-Entropy per token target bertopeng |
| **Exp(masked-token loss)** | **243.4330** | rasio | $\exp(\text{masked loss})$, bukan pseudo-perplexity standar |
| **Top-1 Accuracy** | **17.4430%** | 4.722 / 27.071 target | Persentase prediksi tepat pada peringkat pertama |
| **Top-5 Accuracy** | **31.7535%** | 8.596 / 27.071 target | Persentase target berada dalam 5 kandidat teratas |
| **Durasi Komputasi** | **1,04 detik** | detik | Diukur pada CUDA RTX 4060 Laptop GPU (batch 32) |

---

## 5. Analisis Komparatif Antar-Split (Train vs Validation vs Test)

Tabel berikut menyajikan metrik akhir model terpilih (`runs/lr_1e3_gpu/best_model`, Epoch 5) di seluruh split data:

| Parameter Evaluasi | Split Train (Epoch 5 Online)* | Split Validasi (Epoch 5 Frozen)** | Split Test (Evaluasi Final Frozen)** |
| :--- | :---: | :---: | :---: |
| **Jumlah Chunk Dievaluasi** | 27.002 chunk | 2.685 chunk | 3.426 chunk |
| **Total Target Token** | 216.579 target | 20.627 target | 27.071 target |
| **Masked Cross-Entropy Loss** | 5.5143 nats | 5.4962 nats | **5.4948 nats** |
| **Exp(masked-token loss)** | 248.22 | 243.77 | **243.43** |
| **Top-1 Accuracy** | 16.96% (36.723 / 216.579) | 18.05% (3.723 / 20.627) | **17.44% (4.722 / 27.071)** |
| **Top-5 Accuracy** | 31.24% (67.655 / 216.579) | 32.66% (6.736 / 20.627) | **31.75% (8.596 / 27.071)** |

*\* Catatan Kondisi Pengukuran Split Train: Metrik train dihitung secara online sepanjang proses optimasi epoch 5 saat bobot model masih terus diperbarui antar-batch, dropout aktif (0.1), dan posisi masking bervariasi dinamis. Angka ini BUKAN hasil evaluasi ulang checkpoint final statis dengan kondisi identik seperti validasi atau test.*

*\*\* Catatan Kondisi Pengukuran Validasi dan Test: Diukur menggunakan model final yang sudah dibekukan (frozen) dalam mode inferensi murni (`model.eval()`, `torch.inference_mode()`, dropout dinonaktifkan 0.0), serta menggunakan masking deterministik 80/10/10 berbasis seed 42.*

---

## 6. Pembahasan dan Kesimpulan Proporsional

Berdasarkan data empiris di atas, berikut kesimpulan metodologis yang dapat dipertanggungjawabkan:

1. **Kedekatan Kinerja Antara Validation dan Test**:
   - Selisih masked loss antara split test (**5.4948 nats**) dan validasi (**5.4962 nats**) sangat kecil, yaitu **-0.0014 nats**.
   - Akurasi Top-1 pada split test (**17.44%**) berada dalam rentang yang sangat dekat dengan validasi (**18.05%**), dengan selisih sebesar **-0.61 poin persentase (pp)**.
   - Akurasi Top-5 pada split test (**31.75%**) juga konsisten dengan validasi (**32.66%**), dengan selisih sebesar **-0.91 poin persentase (pp)**.
2. **Batasan Kesimpulan (Non-Overclaim)**:
   - Hasil yang relatif dekat antara validasi dan test pada korpus dan protokol ini **tidak membuktikan ketiadaan kebocoran data (*data leakage*) secara mutlak**, dan **tidak membuktikan bahwa model bebas dari overfitting** dalam skala arsitektur atau korpus yang lebih besar.
   - Hasil ini juga **bukan bukti bahwa model memahami semantik bahasa Indonesia secara komprehensif**. Akurasi Top-1 sebesar 17.44% menunjukkan bahwa sekitar 82.56% tebakan pertama model masih salah, dan sebagian besar keberhasilan tebakan model masih didorong oleh tanda baca berfrekuensi tinggi serta kata tugas umum.
   - Kesimpulan yang sah: Pada batas korpus pilot dan protokol eksperimen yang telah ditetapkan, model menunjukkan stabilitas estimasi performa out-of-sample yang konsisten dengan metrik validasi yang menjadi dasar pemilihannya.
3. **Kepatuhan Protokol Anti-Data-Snooping**:
   - Evaluasi split test hanya dijalankan **satu kali** setelah model `runs/lr_1e3_gpu/best_model` (Epoch 5) resmi dikunci secara tertulis.
   - Tidak ada proses tuning hiperparameter pasca-uji, tidak ada pemilihan checkpoint setelah melihat hasil test, dan tidak ada pengubahan arsitektur model.
