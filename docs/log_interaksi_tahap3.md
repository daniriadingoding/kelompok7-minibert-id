# LOG INTERAKSI LLM, KELOMPOK 7 (GENERATIVE AI - CAK4KBB3)

* **Tanggal Sesi**: 23/10/2026
* **Target Modul**: Perbaikan Cleaner v1.1.0 (Idempotensi & Template Parser Stack-based), Pengambilan Dataset Pilot 3.000 Artikel, dan Audit Multi-Dimensi
* **Lokasi Riwayat AI Aktual**: `C:\Users\Fransisca Anggraeni\.gemini\antigravity-ide\brain\5d72c3ec-29e9-4f58-9024-ae3051230183\.system_generated\logs\transcript.jsonl`
* **Kontributor**: Anggota 1 (Data Pipeline & Preprocessing Engineer)

---

## KRONOLOGI PROMPT & RESPONS

### 1. TAHAP INISIASI (Penyempurnaan Cleaner & Pembangunan Pilot 3.000 Artikel)
- **Ringkasan Prompt Pengguna**:
  > Memperbaiki cleaner konservatif untuk mengatasi kegagalan idempotensi pada kasus spasi tab (`\t`), line ending Windows (`\r\n`), template bersarang > 10 tingkat, serta menjaga keamanan template yang tidak lengkap/tidak tertutup. Melakukan pengujian regresi dan memeriksa idempotensi seluruh 300 artikel sampel. Mengoreksi klaim dokumentasi dari “pembuktian matematis” menjadi “lulus pengujian empiris” serta mengakui keberadaan kutipan bahasa asing, kode, dan daftar. Mengambil dataset pilot terpisah sebanyak 3.000 artikel unik, menerapkan cleaner terbaru, melakukan deduplikasi teks SHA-256, dan menyusun audit pilot multi-dimensi.
- **Rasional & Keputusan Desain**:
  1. *Pra-normalisasi Whitespace & Line Ending*: Sebelum regex heading dievaluasi, karakter `\r\n` dan `\r` distandarisasi ke `\n`, dan spasi khusus (NBSP, dsb.) diubah ke spasi biasa agar pencocokan multiline regex (`^` dan `$`) konsisten pada lintas platform.
  2. *Algoritma Stack Template Satu Lintasan*: Menggantikan perulangan regex `max_iterations = 10` dengan parser tumpukan karakter yang mengidentifikasi pasangan kurung kurawal terluar `{{` dan `}}` dalam kompleksitas $O(N)$. Algoritma ini mendukung kedalaman sembarang tanpa batasan iterasi dan secara otomatis membiarkan template tak tertutup tanpa merusak teks di sekitarnya.
  3. *Isolasi Folder Pilot*: Dataset pilot 3.000 artikel disimpan terpisah di `data/pilot/` agar sampel dan metadata 300 artikel di `data/sample/` tetap utuh.

---

### 2. TAHAP PENANGANAN EROR / DEBUGGING & VERIFIKASI AKTUAL
- **Eror & Temuan Nyata yang Direproduksi**:
  1. *Kegagalan Idempotensi pada Cleaner v1.0.0*:
     - Kasus 1 (`Narasi\n\tReferensi\nSumber`): Pass 1 tidak memotong karena regex hanya mencocokkan spasi ASCII `' '`. Pada pass 2 baru terpotong karena `\t` sempat diubah ke spasi pada langkah normalisasi akhir.
     - Kasus 2 (`Narasi\r\nReferensi\r\nSumber`): Pass 1 gagal memotong karena karakter `\r` masih menempel pada akhir baris sebelum normalisasi newline.
     - Kasus 3 (Template 15 tingkat): Pass 1 hanya memangkas 10 tingkat karena batasan `max_iterations = 10`. Pass 2 baru memangkas 5 tingkat sisanya.
  2. *Solusi Empiris*:
     - Cleaner dinaikkan ke versi `1.1.0`.
     - Ditambahkan fungsi `pre_normalize_line_endings_and_spaces` dan regex `RE_BOILERPLATE_HEADING` diperluas menggunakan `[\t ]*`.
     - Diimplementasikan fungsi `clean_wiki_templates_stack`.
  3. *Verifikasi Regresi*:
     - Ditambahkan 5 unit test regresi baru di `tests/test_cleaner.py`.
     - Seluruh 13 unit test **lolos 100%**.
     - Diuji idempotensi langsung pada seluruh 300 artikel aktual di `data/sample/wiki_sample_300.jsonl`: **0 inkonsistensi** (`len(non_idempotent) == 0`).
  4. *Kendala Eksekusi Import Package*:
     - Penyesuaian `sys.path` di `process_and_audit_pilot.py` agar paket modular `src.data` dikenali dari direktori mana pun skrip dipanggil.

---

## RINGKASAN CAPAIAN TAHAP
1. **Pengujian Unit Cleaner v1.1.0**:
   - `tests/test_cleaner.py`: 13 pengujian lolos (termasuk kasus tab, CRLF, template 15 tingkat, template unclosed, dan idempotensi sampel 300 artikel).
2. **Dataset Pilot 3.000 Artikel**:
   - Berkas mentah: `data/pilot/wiki_pilot_3000.jsonl` (12,97 MB, 3.000 artikel unik).
   - Berkas bersih: `data/pilot/wiki_pilot_3000_cleaned.jsonl` (12,98 MB, 3.000 artikel unik).
   - Metadata sampling: `data/pilot/pilot_metadata.json` (status: `complete`, streaming selesai dalam 24,28 detik).
   - Log deduplikasi: `data/pilot/pilot_deduplication_log.json` (0 duplikat teks persis pasca-cleaning).
3. **Hasil Audit Dataset Pilot**:
   - Total karakter berkurang 5,28% (12.445.627 -> 11.788.620 karakter).
   - Perkiraan kata berkurang 4,74% (1.682.527 -> 1.602.732 kata).
   - Median panjang artikel bersih: 455 karakter (~63 kata).
   - Artikel dengan pemotongan terbesar (hingga 93%) terbukti memotong bibliografi panjang dalam bahasa Belanda/Inggris pada seksi `Daftar pustaka` dan `Referensi`.
   - Teridentifikasi keberadaan artikel rintisan pendek (ID 3986 `Karo` hanya 4 char mentah), artikel panjang komprehensif (ID 44 `Indonesia` dengan 152.362 char), artikel daftar/katalog, serta istilah asing/taksonomi.
