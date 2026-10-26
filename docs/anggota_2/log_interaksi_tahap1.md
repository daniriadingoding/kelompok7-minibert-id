# LOG INTERAKSI LLM, KELOMPOK 7 (ANGGOTA 2)

* Tanggal Sesi: 23/10/2026
* Peran: Anggota 2 (Arsitektur Model & Hardware Lead)
* Target Modul: Penyiapan Environment GPU Mandiri (.venv-gpu), MiniBertConfig, BertEmbeddings, dan MultiHeadSelfAttention
* Lingkungan Sistem:
  - Perangkat: Laptop Lenovo Legion Slim 5 (NVIDIA GeForce RTX 4060 Laptop GPU, 8GB VRAM)
  - Driver NVIDIA: 617.42 (Mendukung CUDA runtime hingga 13.4)
  - CPU & RAM: AMD Ryzen 7 7745HX (8 Cores, 16 Threads), 32 GB RAM
  - Interpreter Terpilih: Python 3.13.2 lokal pada C:\Users\DANI\AppData\Local\Programs\Python\Python313\python.exe
  - Virtual Environment: .venv-gpu (terisolasi dari .venv lama)
  - Paket Utama: torch==2.6.0+cu124, datasets==5.1.0, pyarrow==26.0.0, fsspec==2026.7.0

---

## 1. TAHAP INISIASI (Pemeriksaan Awal & Perancangan Arsitektur)

### Prompt Sesi 1 (Diringkas):
> "Saya adalah Anggota 2 dalam proyek kelompok mata kuliah Generative AI. Kamu akan membantu saya membangun arsitektur Mini-BERT dari nol dan mengintegrasikannya dengan pipeline data Anggota 1. Mulai percakapan dengan membaca berkas aktual secara read-only, ringkas ketentuan tugas dan kondisi pipeline, identifikasi ketidaksesuaian, jelaskan rancangan arsitektur dan aliran bentuk tensor, susun urutan implementasi serta nyatakan rencana environment GPU. Jangan menginstal paket atau mengubah berkas pada respons pertama."

### Alasan Khusus:
Memastikan seluruh keputusan teknis dan integrasi berpijak pada data aktual yang diserahkan Anggota 1, mengaudit kompatibilitas lingkungan eksekusi secara independen, dan menghindari asumsi tanpa verifikasi sistem.

### Output Model Sesi 1:
- Mengidentifikasi bahwa .venv bawaan merujuk path absolut Anggota 1 sehingga rusak pada laptop ini.
- Memverifikasi keberadaan Python 3.13.2 dan GPU RTX 4060 Laptop.
- Menjelaskan aliran tensor Mini-BERT dengan Post-LayerNorm dan weight tying.
- Merancang tahapan kerja modular dari konfigurasi hingga pengujian komponen dasar.

---

## 2. TAHAP PENANGANAN KOREKSI & PERSIAPAN ENVIRONMENT GPU

### Prompt Sesi 2 (Dikutip Aktual):
> "Lanjutkan rencana Anggota 2 secara bertahap. Saya mengizinkan pembuatan environment proyek dan implementasi modul awal dalam workspace. Tidak perlu meminta konfirmasi berulang untuk tindakan rutin tersebut.
> 
> KOREKSI LAPORAN
> 1. Pisahkan aturan eksplisit panduan dari batas implementasi kelompok:
>    - Tidak memakai BertModel, TransformerEncoder, atau MultiheadAttention adalah keputusan implementasi kelompok agar komponen attention dibangun sendiri.
> 2. Jangan mengulang klaim ketidakcocokan Python 3.14 tanpa verifikasi resmi.
> 3. Jangan memasang torchvision karena proyek ini tidak membutuhkannya.
> 4. Klarifikasi bahwa weight tying memungkinkan gradien output head memperbarui baris PAD melalui softmax pada posisi target, walaupun labels padding diabaikan.
> 5. File model yang baru direncanakan harus disebut belum tersedia; jangan membuat tautan seolah sudah dibuat.
> 
> TARGET TAHAP INI
> A. Environment GPU terisolasi.
> B. Konfigurasi model.
> C. Modul embedding.
> D. Multi-head self-attention buatan sendiri.
> E. Tes yang relevan dan log aktual.
> 
> Belum membuat seluruh model, MLM head, inferensi, atau menjalankan training utama."

### Alasan Khusus:
Menegakkan batasan implementasi from-scratch, mengoreksi verifikasi dependensi GPU tanpa pustaka vision yang tidak relevan, memastikan pemahaman mendalam tentang efek weight tying pada token padding, serta membatasi cakupan kode ke fondasi konfigurasi, embedding, dan self-attention.

### Tindakan dan Implementasi Solusi:
1. **Pemeriksaan dan Isolasi Lingkungan**:
   - Memeriksa ketersediaan direktori `.venv-gpu` sebelum pembuatan (hasil awal: tidak ada).
   - Menambahkan aturan `.venv-gpu/` ke `.gitignore` tanpa mengubah aturan sebelumnya.
   - Melakukan verifikasi ketersediaan wheel PyTorch secara empiris:
     * Pada Python 3.14: `pip index versions torch --index-url https://download.pytorch.org/whl/cu124` menghasilkan `ERROR: No matching distribution found for torch`.
     * Pada Python 3.13.2: Roda `torch-2.6.0+cu124-cp313-cp313-win_amd64.whl` tersedia resmi di index PyTorch.
   - Membuat virtual environment baru `.venv-gpu` menggunakan Python 3.13.2.
   - Memasang `torch==2.6.0+cu124` secara eksklusif (tanpa torchvision) dan dependensi data dari `requirements-data.txt`.
   - Menguji komputasi GPU: Tensor kalkulasi sederhana `(x + x).sum()` pada device `cuda` berhasil dengan hasil `8.0`.
   - Menjalankan seluruh 36 tes pipeline data Anggota 1 di dalam `.venv-gpu` (hasil: 36/36 Lulus dalam 3.075 detik).

2. **Implementasi Konfigurasi Model (`src/models/config.py`)**:
   - Menyusun kelas dataclass `MiniBertConfig` dengan parameter `vocab_size=8000`, `pad_token_id=0`, `d_model=128`, `num_layers=2`, `num_heads=4`, `d_ff=512`, `max_position_embeddings=64`, `dropout=0.1`, `attention_dropout=0.1`, `layer_norm_eps=1e-12`, `initializer_range=0.02`.
   - Menambahkan validasi tipe integer positif, keterbagian head (`d_model % num_heads == 0`), rentang token ID, serta probabilitas dropout dalam rentang [0.0, 1.0).
   - Menyediakan metode serialisasi JSON (`to_json_file`, `from_json_file`, `to_dict`, `from_dict`).
   - Menyediakan metode `from_tokenizer_directory` yang menghitung hash vocabulary kanonikal SHA-256 menggunakan algoritma yang identik dengan tokenizer (`d2be29d07e76fe0cd15c3fe1b765325a5397a5e5fe30b2c6a5a019c976c552f2`).

3. **Implementasi Modul Embedding (`src/models/embeddings.py`)**:
   - Menyusun kelas `BertEmbeddings` menggabungkan `word_embeddings` (dengan `padding_idx=0`) dan `position_embeddings` yang dipelajari.
   - Menjumlahkan kedua embedding, menerapkan `nn.LayerNorm(128)` dan `nn.Dropout(0.1)`.
   - Membangun `position_ids` otomatis mengikuti device tensor input tanpa hardcoding device CUDA.
   - Memvalidasi bentuk tensor 2D [B, L], tipe data integer long, larangan tensor kosong, dan penolakan panjang urutan melebihi `max_position_embeddings`.

4. **Implementasi Multi-Head Self-Attention dari Nol (`src/models/attention.py`)**:
   - Menggunakan `nn.Linear` untuk proyeksi Query, Key, Value, dan Output Proyeksi, tanpa menggunakan `nn.MultiheadAttention`.
   - Menghitung scaled dot-product attention score: $Q K^T / \sqrt{d_k}$.
   - Menerapkan padding mask aditif pada posisi key dengan nilai $-10000.0$ untuk token padding, menjamin probabilitas atensi pada token padding bernilai 0.0 secara stabil pada float32 maupun float16.
   - Memvalidasi bahwa mask bernilai biner 0 atau 1, serta menolak batch yang memiliki sampel dengan seluruh mask bernilai 0.
   - Sifat atensi dua arah dipertahankan penuh tanpa causal mask.
   - Memberikan penjelasan bahwa representasi keluaran pada query padding belum tentu bernilai nol karena query tetap mengatensi token valid, namun posisi ini akan diabaikan oleh fungsi loss pada tahap training.

5. **Pengujian Unit Menyeluruh (`tests/test_model_primitives.py`)**:
   - Mengembangkan 19 pengujian unit yang mencakup validasi konfigurasi, batas dimensi, save/load, verifikasi matematis atensi terhadap perhitungan manual, uji isolasi padding mask (perubahan token padding tidak memengaruhi token valid), uji atensi dua arah (perubahan token kanan memengaruhi token kiri), serta finite gradient dan smoke test CPU/GPU.
   - Menjalankan pengujian: 19/19 pengujian baru lulus dalam 0.356 detik.
   - Menjalankan uji regresi keseluruhan: 55/55 pengujian lulus dalam 3.220 detik.
