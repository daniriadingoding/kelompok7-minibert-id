# LOG INTERAKSI LLM, KELOMPOK 7 (GENERATIVE AI - CAK4KBB3)

* **Tanggal Sesi**: 23/10/2026
* **Target Modul**: Pengambilan Sampel & Audit Awal Dataset Wikipedia Bahasa Indonesia (`wikimedia/wikipedia: 20231101.id`)
* **Tautan Sesi Chat**: [Tautan Riwayat Sesi Chat Antigravity IDE / Ekspor Transkrip]
* **Kontributor**: Anggota 1 (Data Pipeline & Preprocessing Engineer)

---

## KRONOLOGI PROMPT & RESPONS

### 1. TAHAP INISIASI (Persiapan Lingkungan, Sampling, & Skrip Audit)
- **Prompt Kelompok**:
  > "Lanjutkan instalasi dependensi, pembuatan skrip sampling, dan audit awal sesuai rencana. Verifikasi dataset wikimedia/wikipedia konfigurasi 20231101.id beserta revision terverifikasi. Ambil sekitar 300 artikel unik via streaming & shuffle buffer (seed 42), simpan metadata, dan buat skrip audit reporting kelengkapan kolom, keunikan teks (SHA-256), distribusi karakter/kata, anomali markup/URL, dan cuplikan inspeksi manual."
- **Alasan Khusus**:
  1. Menghindari pengunduhan seluruh korpus (~583,8 MB terkompresi / ~1,1 GB mentah) ke laptop lokal.
  2. Memastikan reproduksibilitas ilmiah dengan mengunci commit hash HEAD terverifikasi (`b04c8d1ceb2f5cd4588862100d08de323dccfbaa`) pada Hugging Face Hub.
  3. Menggunakan buffer shuffle lokal terukur (1.000 entri) untuk menghindari bias 300 baris pertama dokumen Wikipedia.
  4. Menerapkan isolasi dependensi ketat melalui `.venv` Python 3.12 lokal tanpa mengotori instalasi global.
- **Output Model**:
  - Berkas `.gitignore` dan `requirements-data.txt`.
  - Skrip `src/data/download_sample.py` dengan streaming range request HTTP 206 dan error handling retry.
  - Skrip `src/data/audit_sample.py` untuk menghasilkan audit analitis format JSON dan Markdown.
  - Pembuatan direktori `src/data/`, `data/sample/`, dan `docs/`.

---

### 2. TAHAP PENANGANAN EROR / DEBUGGING & VERIFIKASI LINGKUNGAN
- **Pesan Eror / Kendala dari Lingkungan**:
  1. *Deteksi Python*: Python default sistem adalah `Python 3.14.4` yang belum stabil mendukung pustaka PyTorch prebuilt di Windows.
  2. *Status Workspace Awal*: `fatal: not a git repository`, direktori awal kosong dari lingkungan virtual.
  3. *Verifikasi Commit*: Menghindari penggunaan commit hash yang tidak diverifikasi langsung dari server.
- **Prompt Perbaikan & Penyesuaian ke LLM**:
  > "Gunakan Python 3.12 yang terpasang untuk membuat .venv. Verifikasi keberadaan konfigurasi 20231101.id dan catat full commit hash aktual. Jangan mengaktifkan eksekusi kode dataset jarak jauh (trust_remote_code=False) dan jangan mengasumsikan shuffle buffer sebagai acak seragam sempurna."
- **Analisis & Solusi Kelompok**:
  1. **Solusi Python**: Memilih `py -3.12 -m venv .venv` secara eksplisit (`Python 3.12.3 64-bit`).
  2. **Verifikasi API Hugging Face**: Memanggil endpoint REST `https://huggingface.co/api/datasets/wikimedia/wikipedia` dan rute berkas `.../tree/main/20231101.id`. Ditemukan commit SHA HEAD aktual `b04c8d1ceb2f5cd4588862100d08de323dccfbaa` serta 3 berkas Parquet (`train-00000-of-00003.parquet` s.d. `00002`) dengan total ukuran 583.801.799 bytes.
  3. **Solusi Keamanan & Efisiensi**: Mengatur `trust_remote_code=False` pada `load_dataset` dan memanfaatkan streaming HTTP Range (Status `206 Partial Content`) sehingga waktu penarikan 300 sampel hanya memerlukan 29,36 detik tanpa mengunduh file 583 MB.

---

## RINGKASAN CAPAIAN TAHAP
1. **Berkas Terbuat**:
   - `requirements-data.txt` & `docs/installed_dependencies.txt`
   - `.gitignore`
   - `src/data/__init__.py`
   - `src/data/download_sample.py`
   - `src/data/audit_sample.py`
   - `data/sample/wiki_sample_300.jsonl` (1.838.747 bytes)
   - `data/sample/sample_metadata.json`
   - `docs/sample_audit_report.json`
   - `docs/sample_audit_report.md`
   - `docs/log_interaksi_tahap1.md`
2. **Kualitas Sampel**:
   - 300 artikel unik sempurna (0 duplikat ID, 0 duplikat hash teks).
   - 100% kolom terisi lengkap (`id`, `url`, `title`, `text` bertipe `str`).
   - Tidak ada artikel kosong atau sangat pendek (< 100 karakter).
   - Terdapat 1,7% sisa markup, 3% HTML tags, dan 4% URL mentah yang menjadi acuan aturan pembersihan (*regex cleaning*) pada tahap berikutnya.
