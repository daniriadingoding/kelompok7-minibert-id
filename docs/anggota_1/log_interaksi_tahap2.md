# LOG INTERAKSI LLM, KELOMPOK 7 (GENERATIVE AI - CAK4KBB3)

* **Tanggal Sesi**: 23/10/2026
* **Target Modul**: Penguatan Ketahanan Sampling, Perbaikan Audit Analitis, dan Implementasi Cleaner Konservatif Idempotent
* **Lokasi Riwayat AI Aktual**: `C:\Users\Fransisca Anggraeni\.gemini\antigravity-ide\brain\5d72c3ec-29e9-4f58-9024-ae3051230183\.system_generated\logs\transcript.jsonl`
* **Kontributor**: Anggota 1 (Data Pipeline & Preprocessing Engineer)

---

## KRONOLOGI PROMPT & RESPONS

### 1. TAHAP INISIASI (Penyusunan Perbaikan Sampling, Audit, & Cleaner)
- **Ringkasan Prompt Pengguna**:
  > Memperbaiki ketahanan sampling (validasi argumen, batas pemeriksaan mutlak pada semua jalur, pembedaan status complete/partial, validasi berkas yang sudah ada tanpa unduh ulang tidak perlu, dan unit test mock data). Memperbaiki audit (diferensiasi null/kosong/salah tipe, pelaporan baris korup, pola mirip tag, contoh konteks, dan stratifikasi panjang). Merancang cleaner konservatif (Unicode NFC, whitespace, kontrol karakter, preservasi huruf kapital/angka/tanda baca/stopword, pembersihan tag referensi aman tanpa merusak kode program, ekspansi tautan wiki, pemotongan seksi penutup berbasis heading baris mandiri, dan jaminan idempotensi). Menyusun laporan komparatif sebelum-sesudah.
- **Rasional & Keputusan Desain**:
  1. *Keamanan Ekstraksi*: Mengganti regex rakus `<[^>]+>` dengan penanganan tag referensi spesifik (`<ref>...</ref>`) dan tag format aman, sehingga kode program (seperti `<-` pada artikel Elixir) tidak terhapus secara keliru.
  2. *Preservasi Konteks*: Tidak melakukan lowercase pada tahap cleaning awal agar fleksibel untuk kebutuhan eksperimen Anggota 2 & 3.
  3. *Idempotensi*: Memastikan `clean_text(clean_text(text)) == clean_text(text)` agar teks stabil bila diproses ulang.
  4. *Efisiensi & Integritas*: Menolak unduh ulang bila sampel 300 artikel mentah sudah terverifikasi lengkap dan utuh.

---

### 2. TAHAP PENANGANAN EROR / DEBUGGING & VERIFIKASI AKTUAL
- **Eror Nyata yang Ditemukan dan Solusinya**:
  1. *UnicodeEncodeError pada Konsol Windows*:
     - *Pesan Eror*: `UnicodeEncodeError: 'charmap' codec can't encode character '\u014d' in position 39`
     - *Akar Masalah*: Windows console default menggunakan cp1252 saat mencetak teks Wikipedia bahasa Indonesia yang memuat karakter macron/diakritik.
     - *Solusi*: Menambahkan `sys.stdout.reconfigure(encoding="utf-8")` pada setiap skrip eksekusi.
  2. *Batas Pemeriksaan Sampling Melebihi Limit pada Kasus Uji*:
     - *Pesan Eror*: `AssertionError: 4 != 3` pada `tests/test_sampling_logic.py`.
     - *Akar Masalah*: Pengecekan `examined_count > max_examined_limit` dilakukan setelah item berikutnya sempat diambil ke memori.
     - *Solusi*: Memperbaiki kondisi batas loop menjadi `if examined_count >= max_examined_limit: break` pada seluruh cabang (termasuk rekaman kosong dan duplikat).
  3. *Impor Modul Package*:
     - *Pesan Eror*: `ModuleNotFoundError: No module named 'src'` saat mengeksekusi `apply_cleaner.py`.
     - *Akar Masalah*: Eksekusi skrip langsung menetapkan `sys.path[0]` ke direktori subfolder `src/data/`.
     - *Solusi*: Menambahkan `sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "../..")))`.

---

## RINGKASAN CAPAIAN TAHAP
1. **Pengujian Unit Otomatis (100% Lolos)**:
   - `tests/test_sampling_logic.py`: 4 pengujian lolos (validasi argumen, aliran normal, penanganan duplikat/kosong, batas mutlak limit).
   - `tests/test_cleaner.py`: 8 pengujian lolos (idempotensi, normalisasi NFC, preservasi casing/angka/stopword, preservasi kode non-HTML, ekspansi tautan wiki, pembersihan template bersarang, pembersihan URL aman, dan pemotongan heading mandiri).
2. **Kualitas Data Bersih (`wiki_sample_300_cleaned.jsonl`)**:
   - 300 dari 300 artikel berhasil diproses (0 artikel musnah/menjadi kosong).
   - 294 artikel (98%) mengalami penyesuaian/pembersihan; 6 artikel tidak memerlukan perubahan.
   - Penurunan karakter bersih sebesar 4,06% (median pengurangan 11,7% yang didominasi oleh pemotongan daftar referensi dan pranala luar di bagian penutup).
   - Seluruh 12 URL mentah di badan teks bersih tanpa merusak tanda baca kalimat.
   - Seluruh sisa template wiki `{{...}}` bersih (0 tersisa).
   - Pola `<...>` tersisa hanya 1, yakni sintaks kode program bahasa Elixir (`<- 1..1000`) yang memang sengaja dipertahankan.
   - Tidak ada duplikasi teks baru yang muncul akibat proses pembersihan (300 teks tetap unik sempurna).
