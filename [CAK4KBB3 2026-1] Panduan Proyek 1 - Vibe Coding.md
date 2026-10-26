# PANDUAN PROYEK KELOMPOK: VIBE CODING GENERATIVE AI FROM SCRATCH

Dalam proyek ini, setiap kelompok (terdiri dari 4 anggota) akan membangun model Computer Vision atau Generative Model tingkat menengah hingga lanjut dari nol (from scratch). Seluruh kode, arsitektur, dan proses debugging wajib dibangun menggunakan metode Vibe Coding, yaitu berkolaborasi aktif dengan Large Language Model (LLM) tanpa menyalin (copy-paste) dari tutorial internet.

Proyek ini mencakup penyiapan jalur data (data pipeline), perancangan model, pelatihan (training), penyelarasan (fine-tuning), hingga dokumentasi terstruktur dari setiap interaksi log bersama kecerdasan buatan.

---

## 1. Instruksi Pelaksanaan

* **Dilarang Keras Copy-Paste Tutorial**: Mahasiswa tidak diperbolehkan menyalin blok kode utuh dari GitHub orang lain atau blog tutorial. Dokumentasi resmi pustaka (seperti PyTorch/TensorFlow) hanya boleh digunakan sebagai referensi fungsi dasar.
* **Dokumentasi Chat LLM**: Setiap kelompok wajib merekam dan melampirkan riwayat obrolan dengan LLM dalam bentuk tautan aktif (share link) atau ekspor dokumen Markdown/PDF.
* **Proses Debugging Mandiri**: Jika terjadi kesalahan/eror pada kode, mahasiswa harus mengonsultasikan pesan eror tersebut kepada LLM, menganalisis solusinya, dan mendokumentasikannya di Log Interaksi.

---

## 2. Pembagian Tugas Kelompok (Job Desk)

Setiap kelompok terdiri dari 4 anggota dengan pembagian peran dan tanggung jawab yang jelas agar kontribusi merata. Contoh pembagian tugas:

### Anggota 1: Prompt Engineer & LLM Navigator (Ketua)
* **Tanggung Jawab**: Mengarahkan interaksi dengan LLM dan menyusun strategi arsitektur model.
* **Tugas Spesifik**: Merancang system prompt awal, mengomunikasikan kebutuhan arsitektur ke AI, dan menjaga konsistensi logika coding yang dihasilkan dari awal hingga akhir.

### Anggota 2: Data Pipeline & Preprocessing Engineer
* **Tanggung Jawab**: Mengisolasikan, menyiapkan, dan menyuplai dataset ke dalam model.
* **Tugas Spesifik**: Mencari/menyiapkan dataset ringan, menginstruksikan LLM membuat skrip data augmentation, normalisasi gambar/teks, data loader, serta memastikan ukuran input (shape) sesuai arsitektur.

### Anggota 3: Training Loop & Hyperparameter Tuning Engineer
* **Tanggung Jawab**: Mengelola jalannya pelatihan model dan optimasi performa.
* **Tugas Spesifik**: Memandu LLM menyusun fungsi loss kustom dan perulangan epoch (training loop), melakukan eksperimen fine-tuning (tuning learning rate, batch size), serta mencatat metrik performa.

### Anggota 4: Lead Documentarian & Error Handler
* **Tanggung Jawab**: Mencatat rekam jejak interaksi AI dan memimpin penyelesaian bug.
* **Tugas Spesifik**: Mengompilasi 'Log Interaksi LLM', menangkap pesan eror compiler untuk diformulasikan menjadi prompt perbaikan ke AI, dan menyusun laporan akhir kelompok.

---

## 3. Pilihan Metode dan Arsitektur Model

Berikut adalah beberapa contoh pilihan arsitektur model yang bisa digunakan. Setiap kelompok dibebaskan memilih salah satu dari metode terkini berdasarkan minat dan spesifikasi perangkat keras (hardware) yang dimiliki.

Untuk usulan model lain di luar contoh yang diberikan, silakan konsultasikan dengan dosen kelas. Pastikan bahwa model masih dapat dikategorikan sebagai model terkini (10 tahun terakhir).

### Generative Image & Computer Vision
* **Pix2Pix (Conditional GAN)**: Menerjemahkan gambar domain A ke B (misal: sketsa ke foto berwarna) menggunakan Generator U-Net dan Discriminator PatchGAN. Tantangan: Skip connections dan gabungan loss (BCE + L1).
* **CycleGAN**: Penerjemahan gaya visual dari domain A ke domain B tanpa memerlukan dataset berpasangan menggunakan konsep Cycle Consistency Loss (misal: mengubah foto pemandangan nyata menjadi lukisan seni klasik). Tantangan: Melibatkan koordinasi dua Generator dan dua Discriminator sekaligus.
* **Conditional GAN Klasik**: Model GAN standar yang dikondisikan lewat penambahan tensor label kelas pada sisi input, sehingga model dapat menghasilkan klasifikasi visual tertentu berdasarkan perintah indeks (misal: Fashion-MNIST). Tantangan: Penggabungan (concatenation) matriks gambar dan label.
* **Vision Transformer (ViT) Minimalis**: Mengganti total CNN tradisional dengan mekanisme Self-Attention dengan memotong gambar menjadi patches kecil untuk klasifikasi atau rekonstruksi.
* **Mini Diffusion Model (DDPM)**: Model difusi skala kecil yang belajar menghapus noise secara bertahap pada matriks gambar kecil (32x32 atau 28x28). Tantangan: Menyusun noise schedule dan timestep embedding.

### Generative Text & NLP
* **Mini-Transformer (GPT Minimalis)**: Decoder-only Transformer menggunakan mekanisme Self-Attention tanpa RNN untuk memprediksi kata berikutnya. Tantangan: Menyusun Multi-Head Attention dari nol.
* **BERT dari Nol (Masked Language Model)**: Encoder Transformer dua arah untuk menebak kata tersembunyi ([MASK]). Tantangan: Membuat pipeline otomatisasi data masking dan matriks atensi dua arah.

### Multimodal & Cross-Discipline
* **Image Captioning Minimalis (CNN + Text Decoder)**: Model lintas domain yang menerima input berupa data visual (gambar) lalu menerjemahkannya menjadi satu rangkaian kalimat deskripsi teks. Memanfaatkan ekstraksi fitur CNN dan digabungkan ke modul penulas kata (LSTM/Transformer Decoder).
* **Neural Style Transfer (NST)**: Model optimasi pemindahan estetika seni tanpa melatih bobot jaringan secara konvensional. Tantangan: Membuat pipeline untuk menghitung Content Loss dan Style Loss berbasis ekstraksi fitur Gram Matrix dari lapisan tengah VGG-19.

### Generative Audio & Sequence
* **Generative Audio (MIDI String Generator)**: Model mengenerate rangkaian nada musik tanpa pemrosesan berkas biner .wav yang berat.

---

## 4. Rubrik Penilaian (Total: 100 Poin)

| Kriteria Penilaian | Bobot | Deskripsi Penilaian |
| :--- | :---: | :--- |
| **Kualitas & Orisinalitas Vibe Coding** | 30% | Kemampuan mengarahkan LLM untuk menghasilkan kode yang bersih, modular, dan bebas dari plagiasi langsung tutorial internet. Dinilai dari variasi prompt. |
| **Log Interaksi & Dokumentasi LLM** | 25% | Kelengkapan rekam jejak percakapan dengan LLM, menunjukkan kronologi rasional dari tahap inisiasi, penanganan eror, hingga optimasi. |
| **Fungsionalitas Model & Pelatihan** | 25% | Model dapat berjalan tanpa eror, proses training/fine-tuning terdokumentasi dengan grafik metrik yang valid, serta luaran model logis. |
| **Kerjasama Tim & Manajemen Integrasi** | 20% | Keselarasan penggabungan tugas antar job desk anggota (terlihat pada Git commit atau log kerja) serta penguasaan materi individu saat presentasi. |

---

## 5. Template/Contoh Log Interaksi LLM

> **Catatan Khusus**: Setiap berinteraksi dengan AI untuk membuat bagian kode baru atau memecahkan bug, isilah log di bawah ini.

```markdown
LOG INTERAKSI LLM, KELOMPOK [Nama Kelompok]
* Tanggal Sesi: [DD/MM/YYYY]
* Target Modul: (Contoh: Struktur Pemotong Patches pada ViT / Debugging Loss)
* Tautan Sesi Chat: [Sertakan tautan share link AI]

KRONOLOGI PROMPT & RESPONS:
1. TAHAP INISIASI (Meminta Kode Awal)
   - Prompt Kelompok: "[Tulis prompt spesifik Anda di sini]"
   - Alasan Khusus: [Mengapa menggunakan pendekatan/instruksi ini?]
   - Output Model: [Jelaskan ringkasan skrip atau tempel cuplikan kode krusial]

2. TAHAP PENANGANAN EROR / DEBUGGING
   - Pesan Eror dari Notebook: [Salin pesan eror konsol secara utuh]
   - Prompt Perbaikan ke LLM: "[Tulis bagaimana Anda menanyakan solusi eror ke AI]"
   - Analisis & Solusi Kelompok: [Bagaimana AI membantu Anda memperbaiki eror dan apa pelajaran yang kelompok ambil?]
```
