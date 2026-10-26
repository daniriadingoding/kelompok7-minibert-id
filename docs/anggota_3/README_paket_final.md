# PANDUAN DAN DAFTAR ISI PAKET SERAH TERIMA FINAL ANGGOTA 3
## Mini-BERT Bahasa Indonesia dari Nol (Generative AI - Kelompok 7)

* **Tanggal Rilis**: 26 Oktober 2026
* **Penulis**: Anggota 3 (Training Loop, Hyperparameter Tuning, & Evaluasi Lead)
* **Penerima**: Anggota 1, Anggota 2, dan Tim Dosen Penilai
* **Nama Arsip**: `handover_anggota3_final.zip`
* **Status Model**: Final & Resmi Dikunci (`runs/lr_1e3_gpu/best_model`, Epoch 5)

---

## 1. Daftar Isi Berkas dalam Paket Serah Terima

Paket ini hanya memuat berkas-berkas dokumentasi analitis, visualisasi resmi, skrip evaluasi mandiri, dan laporan terstruktur tanpa menyertakan dataset mentah, cache virtual environment, atau checkpoint biner besar:

### A. Dokumen Analisis & Evaluasi Utama (`docs/anggota_3/`):
1. `pembahasan_hasil_akhir.md`: Dokumen pembahasan komprehensif pasca-evaluasi test, mencakup tujuan eksperimen, perbandingan baseline vs pembanding, alasan pemilihan model validasi, hasil test split, baseline frekuensi unigram, error analysis, 6 keterbatasan metodologis, dan batasan terminologi.
2. `laporan_evaluasi_final_test.md`: Laporan resmi hasil inferensi split test pada GPU RTX 4060 dengan klaim ilmiah yang proporsional, catatan perbedaan kondisi pengukuran train vs validasi/test, serta konfirmasi integritas hash.
3. `analisis_baseline_dan_komparasi.md`: Analisis mendalam perbandingan baseline LR 3e-4 vs pembanding LR 1e-3, dinamika kurva, dan dekomposisi leksikal vs tanda baca.
4. `penguncian_model_final.md`: Dokumen protokol penguncian model (*model freezing*) yang ditandatangani sebelum split test dibuka.
5. `panduan_eksekusi_gpu.md`: Panduan operasional langkah demi langkah eksekusi GPU untuk Anggota 2.
6. `final_test_terminal.log`: Log keluaran terminal mentah dari eksekusi inferensi test di mesin CUDA Anggota 2.

### B. Grafik Visualisasi Resmi Beresolusi Tinggi (`docs/anggota_3/*.png`):
1. `evaluasi_final_split_test.png`: Visualisasi komparatif akhir Train (Epoch 5 Online) vs Validasi (Frozen) vs Test (Frozen) disertai catatan kondisi pengukuran.
2. `kurva_perbandingan_lr.png`: Kurva 3 panel per-epoch (Validation Loss, Top-1, dan Top-5) membandingkan Baseline LR 3e-4 vs Pembanding LR 1e-3.
3. `kurva_pelatihan_baseline_gpu.png`: Kurva 3 panel dinamika pelatihan Baseline GPU.
4. `perbandingan_baseline_vs_frekuensi.png`: Grafik pembuktian keunggulan model Mini-BERT terhadap batas bawah frekuensi unigram train.

### C. Log & Transkrip Interaksi AI Transparan (`docs/anggota_3/`):
1. `log_interaksi_anggota3.md`: Catatan kronologis terstruktur seluruh tahapan pekerjaan Anggota 3 (12 sesi) beserta rincian kontribusi nyata dan batas kolaborasi antaranggota.
2. `transkrip_percakapan_anggota3.md`: Transkrip percakapan Markdown lengkap dari 756 langkah interaksi AI agent Anggota 3.

### D. Skrip Evaluasi & Metadata Hasil Mentah (`src/training/` & `runs/`):
1. `src/training/`: Seluruh modul implementasi training pipeline karya Anggota 3 (`evaluate_test.py`, `trainer.py`, `checkpoint.py`, `metrics.py`, `scheduler.py`, `optimizer.py`, `config.py`, `diagnostics.py`, `run_experiment.py`, `__init__.py`).
2. `runs/lr_1e3_gpu/final_test_evaluation.json`: Metadata lengkap evaluasi test (metrik, hash kriptografis, chunk manifest, durasi).
3. `runs/lr_1e3_gpu/final_test_evaluation.csv`: Ringkasan satu baris metrik test dalam format CSV terstruktur.
4. `runs/baseline_gpu/` & `runs/lr_1e3_gpu/`: Berkas riwayat pelatihan lengkap (`training_history.json` & `.csv`).

---

## 2. Sumber Angka Resmi & Panduan Sitasi

Untuk penulisan laporan kelompok dan materi presentasi, seluruh angka wajib merujuk pada berkas sumber berikut:

| Parameter Metrik | Nilai Resmi Terverifikasi | Berkas Sumber Otoritatif |
| :--- | :--- | :--- |
| **Model Terpilih** | `runs/lr_1e3_gpu/best_model` (Epoch 5) | `docs/anggota_3/penguncian_model_final.md` |
| **Total Parameter** | 1.453.760 parameter (42 tensors) | `best_model/model.pt` (5.828.097 byte) |
| **Hash SHA-256 Model** | `0c0de0b0b88f51b5d7dfc474a3dc8bcbfe6d86d3c527e30869fd28eccb1ef8b8` | `final_test_evaluation.json` |
| **Hash SHA-256 Vocab** | `d2be29d07e76fe0cd15c3fe1b765325a5397a5e5fe30b2c6a5a019c976c552f2` | `data/processed/pilot/vocab.json` |
| **Hash SHA-256 Test File** | `f82e9d06e1f2c8aac888195c926f61db42eec75c75f685ceb68202b8b9c4f868` | `data/processed/pilot/test_chunks.jsonl` |
| **Target Test Dievaluasi** | 27.071 target (3.426 chunk; 1 chunk doc 3792 disaring) | `final_test_evaluation.json` |
| **Test Masked Loss** | **5.494842 nats** | `final_test_evaluation.json` |
| **Test Exp(masked loss)** | **243.4330** | `final_test_evaluation.json` |
| **Test Top-1 Accuracy** | **17.4430%** (4.722 / 27.071 target) | `final_test_evaluation.json` |
| **Test Top-5 Accuracy** | **31.7535%** (8.596 / 27.071 target) | `final_test_evaluation.json` |
| **Val Loss Terpilih (Ep 5)** | **5.496227 nats** | `runs/lr_1e3_gpu/training_history.json` |
| **Val Top-1 Terpilih (Ep 5)** | **18.0492%** (3.723 / 20.627 target) | `runs/lr_1e3_gpu/training_history.json` |
| **Val Top-5 Terpilih (Ep 5)** | **32.6562%** (6.736 / 20.627 target) | `runs/lr_1e3_gpu/training_history.json` |
| **Baseline Frekuensi Top-1** | **6.60%** (1.362 / 20.627 target) | `scratch/frequency_baseline_results.json` |
| **Baseline Frekuensi Loss** | **6.7852 nats** | `scratch/frequency_baseline_results.json` |

---

## 3. Pedoman Penggunaan Hasil untuk Laporan Akhir Kelompok

1. **Gunakan Satuan Poin Persentase (`pp`)**: Saat membandingkan akurasi antarmodel atau antarsplit, selalu gunakan poin persentase (misal peningkatan Top-1 validasi dari 13.79% ke 18.05% adalah sebesar $+4.26\text{ pp}$).
2. **Kondisi Pengukuran yang Berbeda**: Dalam menyajikan tabel Train vs Validasi vs Test, sertakan catatan bahwa metrik train dihitung online selama optimasi (dropout aktif 0.1, bobot terus bergerak), sedangkan validasi dan test diukur pada model statis beku (dropout nonaktif 0.0).
3. **Ketepatan Terminologi**: Jangan menyebut $\exp(\text{masked loss})$ sebagai "perplexity teks penuh", melainkan sebagai eksponensial dari masked-token cross-entropy loss.
4. **Hindari Overclaiming**: Nyatakan bahwa keselarasan performa validasi dan test membuktikan konsistensi protokol evaluasi pada korpus ini, namun bukan bukti ketiadaan overfitting atau pemahaman bahasa secara absolut.
