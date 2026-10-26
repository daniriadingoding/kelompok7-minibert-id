# Laporan Smoke Test GPU Mini-BERT Bahasa Indonesia

Dokumen ini mencatat hasil pengujian empiris eksekusi forward, loss, dan backward pass model Mini-BERT Bahasa Indonesia pada GPU laptop Anggota 2 menggunakan satu batch nyata dari split Train.

---

## 1. Lingkungan Hardware dan Pustaka

- **Python Interpreter**: 3.13.2
- **PyTorch Version**: 2.6.0+cu124
- **PyTorch CUDA Build / Runtime**: 12.4 *(Catatan: Ini adalah versi build runtime PyTorch, bukan versi driver host).*
- **NVIDIA Host Driver**: 617.42
- **GPU Hardware**: NVIDIA GeForce RTX 4060 Laptop GPU (8.188 MiB VRAM)

---

## 2. Arsitektur Model dan Metadata Batch Nyata

- **Konfigurasi Model**: 2 Layers, 4 Heads, d_model=128, d_ff=512, Vocab=8.000 token.
- **Hash Vocabulary**: `d2be29d07e76fe0cd15c3fe1b765325a5397a5e5fe30b2c6a5a019c976c552f2`
- **Jumlah Parameter Unik**: 1,453,760 parameter (weight tying aktif).
- **Ukuran Batch Uji**: 4 contoh, sequence length 64 token.
- **Jumlah Target Prediksi MLM**: 28 token dari 256 posisi (10.94%), posisi lain berlabel `-100`.

---

## 3. Hasil Pengukuran Terukur

| Metrik Evaluasi | Hasil Terukur | Keterangan |
| :--- | :---: | :--- |
| **Logits Forward Pass** | **Finite (True)** | Bentuk tensor [4, 64, 8000], tidak ada NaN atau Inf. |
| **Loss CrossEntropy** | **9.0048** | Sangat konsisten dengan batas teoritis acak ln(8000) = 8.9872. |
| **Verifikasi Gradien Backward** | **100% Finite** | 41/41 parameter memiliki gradien valid non-None dan finite. |
| **Peak Allocated VRAM** | **51.25 MB** | Memori fisik yang dialokasikan langsung untuk tensor model dan aktivasi. |
| **Peak Reserved VRAM** | **70.0 MB** | Total memori yang dicadangkan oleh PyTorch CUDA caching allocator. |
| **Waktu Eksekusi 1 Batch** | **148.16 ms** | Pengukuran murni forward, loss, dan backward pass dengan sinkronisasi CUDA. |

---

## 4. Penjelasan dan Batasan Evaluasi

1. **Bukan Estimasi Durasi Training**:
   Waktu eksekusi 1 batch (148 ms) murni merupakan smoke test verifikasi saluran komputasi forward dan backward pada GPU. Angka ini bukan estimasi durasi training penuh satu epoch atau durasi total.
2. **Bukan Estimasi Kebutuhan Memori Training Penuh**:
   Pengukuran memori 51.25 MB allocated pada satu batch kecil (B=4) tanpa optimizer bukan merupakan estimasi kebutuhan memori training penuh. Optimizer seperti AdamW membutuhkan alokasi memori tambahan sebesar 2x lipat ukuran parameter float32 untuk menyimpan first dan second momentum states, serta akumulasi aktivasi backward yang bertambah seiring membesarnya batch size.
3. **Status Bobot Acak**:
   Bobot model saat pengujian adalah bobot inisialisasi acak normal (mean=0.0, std=0.02). Loss aktual 9.0048 sangat konsisten dengan entropi teoritis 8.000 kelas acak (ln(8000) = 8.9872).
