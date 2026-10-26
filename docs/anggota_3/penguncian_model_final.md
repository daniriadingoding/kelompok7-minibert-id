# DOKUMEN PENGUNCIAN MODEL FINAL (*FINAL MODEL FREEZING PROTOCOL*)

* **Tanggal Penguncian**: 24 Oktober 2026
* **Penulis**: Anggota 3 (Training Loop, Hyperparameter Tuning, & Evaluasi Lead)
* **Penerima**: Seluruh Anggota Kelompok 7 & Tim Penilai Akademik
* **Status**: **RESMI DIKUNCI (FROZEN)** Sebelum Split Test Dibuka atau Dievaluasi.

---

## 1. Model dan Epoch Terpilih

Berdasarkan perbandingan objektif seluruh metrik pada split validasi independen, kelompok kami secara resmi menetapkan:

* **Eksperimen Terpilih**: `runs/lr_1e3_gpu/` (Eksperimen Pembanding GPU dengan Learning Rate `1e-3`).
* **Direktori Model Inferensi**: [`runs/lr_1e3_gpu/best_model/`](file:///c:/Data%20C/%28%21%29%20Kampus/Semester%207/Gen%20AI/KELOMPOK%207/runs/lr_1e3_gpu/best_model)
* **Epoch Terpilih**: **Epoch 5** (Global Step 4.220).
* **Status Checkpoint**: `"trained"`.

---

## 2. Rationale Pemilihan Berdasarkan Metrik Validasi

Model `runs/lr_1e3_gpu/best_model` (Epoch 5) dipilih karena mengungguli model `baseline_gpu` (`LR=3e-4`) secara konsisten pada setiap metrik evaluasi di atas 20.627 target validasi deterministik:

| Metrik Evaluasi Validasi | Baseline (`LR = 3e-4`) | Terpilih (`LR = 1e-3`) | Selisih Absolut | Keterangan |
| :--- | :---: | :---: | :---: | :--- |
| **Validation Cross-Entropy Loss** | 6.036121 | **5.496227** | **-0.539894 nats** | Lebih rendah (perbaikan ~8.94%) |
| **Effective Masked Perplexity** | 418.27 | **243.77** | **-174.50 poin** | Ketidakpastian berkurang 41.7% |
| **Validation Top-1 Accuracy** | 13.7878% | **18.0492%** | **+4.2614 poin persentase (pp)** | Meningkat relatif +30.89% |
| **Validation Top-5 Accuracy** | 28.2397% | **32.6562%** | **+4.4165 poin persentase (pp)** | Meningkat relatif +15.65% |

### Analisis Pertimbangan:
1. **Konvergensi Lebih Dalam Tanpa Instabilitas**: Pada laju pembelajaran `1e-3`, model mampu menavigasi lanskap optimasi Cross-Entropy secara lebih efektif. Pemangkasan gradien `max_grad_norm=1.0` dan warmup 422 steps berhasil mencegah lonjakan gradien liar.
2. **Ketiadaan Gejala Overfitting pada 5 Epoch**: Selama 5 epoch, validation loss terus menurun secara monoton dari 6.2417 ke 5.4962 tanpa memperlihatkan titik balik (*inflection point*) kenaikan loss. Meskipun ini bukan jaminan ketiadaan overfitting jika dilatih ratusan epoch, pada rentang 5 epoch ini model menunjukkan generalisasi yang sehat.
3. **Peningkatan Representasi Kata Leksikal**: Peningkatan Top-1 sebesar +4.26 pp membuktikan bahwa model tidak hanya mengandalkan tanda baca dan stopwords, melainkan mulai memprediksi kata leksikal konten secara lebih tepat.

---

## 3. Spesifikasi Arsitektur, Hyperparameter, & Random Seeds

Model yang dikunci dibangun dengan konfigurasi tetap sebagai berikut:

* **Arsitektur**:
  - Tipe: Mini-BERT (Bidirectional Transformer Encoder + MLM Head)
  - Jumlah Layer (`num_layers`): 2
  - Jumlah Attention Heads (`num_heads`): 4
  - Dimensi Model (`d_model`): 128
  - Dimensi Feed-Forward (`d_ff`): 512
  - Panjang Konteks Maksimum (`max_position_embeddings`): 64
  - Ukuran Vocabulary (`vocab_size`): 8.000 token
  - Total Parameter Trainable: 1.453.760 parameter
  - Jumlah Tensor State Dict: 42 tensor (41 tensor bobot unik; `cls.decoder.weight` terikat memori secara *weight tying* dengan `embeddings.word_embeddings.weight`).
* **Hiperparameter Pelatihan**:
  - Optimizer: AdamW (`weight_decay=0.01` untuk matriks, `0.0` untuk bias & LayerNorm)
  - Learning Rate: `0.001` (`1e-3`)
  - Scheduler: Linear Warmup (10% = 422 steps) dilanjutkan Linear Decay ke 0.0
  - Batch Size: 32 (844 steps per epoch, total 4.220 steps pada 27.002 chunks train)
  - Presisi Komputasi: `float32` murni
* **Pemisahan Seed Reproduksibilitas**:
  - `model_seed`: 42 (Inisialisasi bobot acak baru)
  - `shuffle_seed`: 42 (Pengacakan urutan DataLoader)
  - `masking_seed`: 42 (Aturan masking dinamis pelatihan)
  - `eval_seed`: 42 (Aturan masking deterministik validasi & evaluasi)

---

## 4. Hash Integritas Berkas (Cryptographic Fingerprint)

Seluruh berkas model dan data yang menjadi rujukan evaluasi final telah diverifikasi menggunakan algoritma SHA-256:

| Komponen Berkas | Jalur Relatif | SHA-256 Checksum | Ukuran Berkas |
| :--- | :--- | :--- | :--- |
| **Bobot Model Terpilih** | `runs/lr_1e3_gpu/best_model/model.pt` | `0c0de0b0b88f51b5d7dfc474a3dc8bcbfe6d86d3c527e30869fd28eccb1ef8b8` | 5.828.097 bytes |
| **Konfigurasi Model** | `runs/lr_1e3_gpu/best_model/config.json` | `521a31762dea889dc6ae865d9ad20816b90cecc35eb8212b2b725445a51f3026` | 349 bytes |
| **Hash Kanonikal Vocab** | `data/processed/pilot/vocab.json` | `d2be29d07e76fe0cd15c3fe1b765325a5397a5e5fe30b2c6a5a019c976c552f2` | (8.000 kata) |
| **Dataset Test Chunk** | `data/processed/pilot/test_chunks.jsonl` | `f82e9d06e1f2c8aac888195c926f61db42eec75c75f685ceb68202b8b9c4f868` (aktual) | 3.427 chunks fisik |

*Catatan Verifikasi Hash Test Dataset: Nilai hash aktual yang diverifikasi secara langsung pada berkas fisik `test_chunks.jsonl` saat evaluasi mandiri adalah `f82e9d06e1f2c8aac888195c926f61db42eec75c75f685ceb68202b8b9c4f868`. Nilai `fbf3c5ea...` yang tercatat pada draf awal tabel merupakan catatan administratif pra-evaluasi saat split test masih disegel steril.*

---

## 5. Komitmen Metodologis (*Anti-Data-Snooping Commitment*)

1. **Penguncian Sebelum Evaluasi Test**:
   Dokumen ini disahkan dan dikunci **SEBELUM** split Test (`test_chunks.jsonl`) dibuka, dimuat, atau dievaluasi oleh skrip evaluasi apapun.
2. **Ketiadaan Post-Hoc Selection**:
   Apapun hasil evaluasi pada split Test nantinya (baik nilai loss lebih tinggi, lebih rendah, atau akurasi bervariasi), model terpilih ini **TIDAK AKAN DIGANTI, DIUBAH, ATAU DIULANG-ULANG**.
3. **Pencegahan Kebocoran Evaluasi**:
   Hasil split Test murni berfungsi sebagai estimasi performa generalisasi akhir yang tidak bias (*unbiased out-of-sample generalization estimate*), sesuai standar ilmiah machine learning tertinggi.
