# Log Interaksi AI - Tahap 4: Pembagian Data Dokumen, Tokenizer Kata Kustom, Evaluasi Vocabulary, dan Sequence Chunking

**Tanggal**: 23 Oktober 2026  
**Peran Anggota**: Anggota 1 (Data Pipeline & Preprocessing Engineer)  
**Lingkungan**: Virtual Environment Python 3.12.3 di `.venv` (Windows PowerShell)  
**Tautan Transkrip Lokal**: `C:\Users\Fransisca Anggraeni\.gemini\antigravity-ide\brain\5d72c3ec-29e9-4f58-9024-ae3051230183\.system_generated\logs\transcript.jsonl`

---

## 1. Ringkasan Aktivitas dan Tujuan

Pada tahap ini, Anggota 1 melanjutkan persiapan dataset dan pembangunan fondasi representasi teks untuk Mini-BERT Bahasa Indonesia dari dataset bersih pilot (3.000 artikel):
1. **Penyaringan Kelayakan**: Menetapkan batas minimum 10 kata per artikel untuk pilot, mengidentifikasi dan mencatat 9 artikel sangat pendek ke dalam manifest eksklusi tanpa merusak berkas sumber.
2. **Pembagian Data Tingkat Dokumen (*Document-Level Split*)**: Membagi 2.991 artikel layak menjadi 80% Train (2.393 dokumen), 10% Validation (299 dokumen), dan 10% Test (299 dokumen) secara deterministik (seed 42) dengan bukti 0 irisan ID dan 0 irisan hash teks normalisasi.
3. **Tokenizer Tingkat Kata Kustom (*Word-Level Tokenizer*)**: Mengembangkan kelas `WordLevelTokenizer` mandiri tanpa pretrained model eksternal, mengunci ID token khusus `[PAD]=0, [UNK]=1, [CLS]=2, [SEP]=3, [MASK]=4`, normalisasi Unicode NFC, lowercase, pemisahan tanda baca, serta preservasi `[MASK]`.
4. **Pembangunan Vocabulary Eksklusif Train (*Train-Only*)**: Menghitung frekuensi token murni dari split Train, membandingkan batas ukuran 5.000, 8.000, dan 12.000 kata berdasarkan evaluasi coverage token-level dan type-level pada split Train dan Validation, mengunci rekomendasi 8.000 kata, serta mengevaluasi Test split hanya setelah konfigurasi dikunci.
5. **Pemotongan Urutan (*Sequence Chunking*)**: Merancang pemotongan artikel panjang tanpa tumpang tindih (*non-overlapping*) dengan panjang tetap 64 token (maksimal 62 token isi + `[CLS]` + `[SEP]`), menyertakan `attention_mask` (1 token aktif, 0 padding), mempertahankan `doc_id` dan `chunk_index`, serta membuang sisa potongan pendek di akhir artikel ($< 5$ token) secara transparan.
6. **Verifikasi dan Pengujian**: Menulis 7 unit test komprehensif pada `tests/test_tokenizer_and_pipeline.py` yang seluruhnya lulus 100%, serta menyusun dokumen kontrak serah terima data sementara di `docs/data_contract_pilot.md`.

---

## 2. Rincian Prompt dan Instruksi yang Diberikan

### Prompt Utama:
> "Lanjutkan ke pembagian data tingkat dokumen dan implementasi tokenizer/vocabulary versi pilot. Jangan memperbesar dataset atau membuat training model pada tahap ini.
> KONDISI: Dataset cleaned pilot 3.000 artikel, cleaner v1.1.0 lulus pengujian, vocabulary belum dibuat, pilot untuk validasi pipeline.
> A. TETAPKAN DATA YANG LAYAK: Periksa artikel sangat pendek (< 10 kata), simpan artikel yang dikeluarkan dalam manifest beserta alasan, jangan hapus data sumber, periksa duplikasi teks normalisasi, dokumentasikan keterbatasan deduplikasi persis.
> B. SPLIT TINGKAT DOKUMEN: Rasio 80/10/10, seed 42, urutkan deterministik sebelum acak, split sebelum chunking, seluruh potongan satu dokumen di split yang sama, simpan train.jsonl, val.jsonl, test.jsonl, simpan manifest, pastikan 0 irisan ID & hash.
> C. TOKENIZER TINGKAT KATA: Buat tokenizer sendiri, NFC, lowercase, [PAD]=0, [UNK]=1, [CLS]=2, [SEP]=3, [MASK]=4, pisahkan tanda baca konsisten, jelaskan angka, kata berimbuhan, tanda hubung, apostrof, preservasi [MASK], jangan stemming/hapus stopword, sediakan tokenize, encode, decode, save, load, tolak ID tidak valid.
> D. VOCABULARY TRAIN SAJA: Bangun frekuensi hanya dari train, bandingkan 5k, 8k, 12k, urutan deterministik frekuensi lalu leksikografis, evaluasi coverage token & type di train & val, kecualikan special token dari penyebut, kunci rekomendasi berdasarkan val, jangan pakai test untuk memilih, simpan artefak.
> E. PANJANG INPUT DAN CHUNKING: max_length 64 (62 isi + CLS + SEP), non-overlapping chunking, simpan doc_id & chunk_index, tangani tail chunk pendek (< 5), hindari sampel hanya special token, attention_mask 1 valid 0 pad, belum masking MLM.
> F. VERIFIKASI: Uji seluruh aspek integrasi.
> G. SERAH TERIMA: Buat docs/data_contract_pilot.md, jalankan kode, laporkan hasil aktual, catat log interaksi nyata."

---

## 3. Respon dan Implementasi Solusi Asisten AI

1. **Pembuatan Modul Pembagian Dokumen (`src/data/split_dataset.py`)**:
   - Membaca `data/pilot/wiki_pilot_3000_cleaned.jsonl`, menghitung hash SHA-256 berkas input (`e85fc85adba334f59e0adfd7514300300d0752ce54ee7581fbff289c56eb2816`).
   - Menyaring 9 artikel dengan $< 10$ kata berbasis spasi dan menyimpannya ke `data/pilot/excluded_articles_manifest.json`.
   - Mengelompokkan dokumen berdasarkan hash SHA-256 teks normalisasi (memastikan dokumen identik berada pada split yang sama).
   - Membagi ke Train (2.393 dok, 1.308.557 kata), Val (299 dok, 129.167 kata), dan Test (299 dok, 164.948 kata) dengan seed 42.
   - Menghasilkan `data/processed/pilot/split_manifest.json` yang memverifikasi 0 irisan ID dan 0 irisan hash teks normalisasi.
2. **Implementasi Kelas Tokenizer Mandiri (`src/data/tokenizer.py`)**:
   - Menggunakan pola regex `(\[(?:PAD|UNK|CLS|SEP|MASK)\])|([\w]+)|([^\w\s])` dengan `re.IGNORECASE`. Token khusus dikenali pertama kali dan dinormalisasi ke representasi kanonikal uppercase (`[MASK]`), sehingga tidak terpecah dan tidak diubah menjadi `[mask]`.
   - Huruf biasa dinormalisasi ke lowercase dan Unicode NFC.
   - Tanda hubung (`-`) dipisahkan sebagai tanda baca tersendiri, memecah kata ulang seperti `anak-anak` menjadi `["anak", "-", "anak"]`.
   - Apostrof dinormalisasi ke ASCII `'` dan dipisah sebagai tanda baca (misal: `Jum'at` -> `["jum", "'", "at"]`).
   - Metode `encode` menghasilkan `input_ids` dan `attention_mask` dengan truncation dan padding ke `max_length = 64`.
   - Metode `decode` memvalidasi ID dan menolak ID di luar rentang `0 <= id < vocab_size` dengan melemparkan `ValueError`.
   - Mendukung penyimpanan dan pemuatan artefak melalui `save_pretrained` dan `from_pretrained`.
3. **Pembangunan dan Evaluasi Vocabulary Eksklusif Train (`src/data/build_vocab.py`)**:
   - Membaca 1.597.330 token isi pada split Train dengan 73.369 jenis kata unik (*types*).
   - Mengevaluasi kandidat ukuran 5.000, 8.000, dan 12.000 kata pada Train dan Validation split.
   - Mengunci ukuran 8.000 kata (Train Token Cov: 89,971%, Val Token Cov: 87,341%, Val Type Cov: 35,997%) dengan SHA-256 hash `8a4ca39b69b596e1a47dfdcb373bf9bcf51e7f603d32ef3c8d45138127027d78`.
   - Menyimpan `vocab.json` dan `tokenizer_config.json` ke `data/processed/pilot/` serta laporan evaluasi komparatif ke `docs/vocabulary_comparison_report.json` dan `.md`.
4. **Implementasi Pemotongan Urutan Non-Overlapping (`src/data/chunker.py`)**:
   - Memotong artikel panjang menjadi segmen 62 token isi + `[CLS]` + `[SEP]` = 64 token.
   - Membuang sisa potongan di akhir artikel (*tail chunks*) yang $< 5$ token isi:
     - Train: 2.393 dokumen -> 27.002 chunks (227 tail dibuang).
     - Val: 299 dokumen -> 2.685 chunks (30 tail dibuang).
     - Test: 299 dokumen -> 3.427 chunks (39 tail dibuang).
   - Menghasilkan `train_chunks.jsonl`, `val_chunks.jsonl`, `test_chunks.jsonl`, dan `chunking_manifest.json`.
5. **Penyusunan Pengujian dan Kontrak Data**:
   - Mengembangkan 7 unit test di `tests/test_tokenizer_and_pipeline.py`. Seluruh pengujian lulus (total 24/24 unit test di seluruh repositori lolos).
   - Menyusun kontrak data resmi bagi Anggota 2 & 3 di `docs/data_contract_pilot.md`.

---

## 4. Masalah Nyata, Kasus Batas, dan Solusi Teknis

| No | Masalah / Temuan Kasus Batas | Dampak Jika Dibiarkan | Solusi Teknis yang Diterapkan |
| :---: | :--- | :--- | :--- |
| 1 | Token khusus `[MASK]` dapat terpecah atau di-lowercase oleh regex standar (`\[` `mask` `\]` atau `[mask]`). | MLM head pada Mini-BERT gagal mengenali token masking saat pretraining dan inferensi. | Regex engine dirancang memeriksa pola token khusus secara eksplisit di awal sebelum kata biasa, dan memetakan langsung ke uppercase kanonikal `[MASK]` dengan ID 4. |
| 2 | Duplikasi kata ulang bahasa Indonesia (misal: `anak-anak`, `berbondong-bondong`, `ke-2`). | Vocabulary membengkak dengan ribuan variasi kata ulang bertanda hubung. | Tanda hubung `-` dipisahkan secara konsisten sebagai tanda baca individual: `["anak", "-", "anak"]`, mereduksi ukuran vocabulary dan menaikkan efisiensi coverage. |
| 3 | Terdapat artikel Wikipedia sangat pendek (misal: ID 3986 `Karo` yang hanya berisi 1 kata `"Nama"`). | Sampel pelatihan tidak memiliki konteks kalimat yang memadai. | Diterapkan kebijakan penyaringan batas minimum 10 kata berbasis spasi. Tepat 9 artikel disaring ke manifest eksklusi tanpa menghapus rekaman dari data sumber. |
| 4 | Potongan sisa di akhir artikel panjang hanya berisi 1–3 kata (misal: titik penutup artikel). | Menghasilkan sampel pelatihan dengan 95%+ padding yang menurunkan kualitas representasi model. | Diterapkan ambang batas `min_chunk_tokens = 5` untuk sisa tail chunk (chunk_index > 0). Chunk primer (indeks 0) tetap dipertahankan selama $\ge 1$ kata isi agar tidak ada sampel kosong. |
| 5 | Evaluasi coverage rawan terdistorsi jika menyertakan token khusus (`[CLS]`, `[SEP]`, `[PAD]`). | Angka coverage tampak tinggi secara semu (*false sense of high coverage*). | Token khusus dan padding secara eksplisit dikeluarkan dari penyebut metrik, sehingga metrik coverage murni mengukur ketercakupan kata isi korpus. |
| 6 | Pengujian ulang pemisahan dataset berpotensi menghasilkan partisi berbeda jika tidak deterministik. | Reproduksibilitas eksperimen antarsesama anggota tim rusak. | Pengurutan deterministik berbasis ID artikel dilakukan sebelum pengacakan dengan `random.Random(seed=42)`. Teruji menghasilkan partisi yang 100% identik pada re-run. |

---

## 5. Ringkasan Verifikasi dan Pengujian

- **Eksekusi Unit Test**:
  - `.\.venv\Scripts\python.exe -m unittest tests/test_tokenizer_and_pipeline.py`: **7/7 Lulus (OK)** dalam 2,47 detik.
  - `.\.venv\Scripts\python.exe -m unittest discover tests`: **24/24 Lulus (OK)** dalam 3,57 detik.
- **Integritas Data dan Zero-Leakage**:
  - Irisan ID Train-Val: 0
  - Irisan ID Train-Test: 0
  - Irisan ID Val-Test: 0
  - Irisan Hash SHA-256 Teks Normalisasi Antarsplit: 0
- **Status Akhir**: Artefak tokenizer, vocabulary, dataset partisi, chunks, laporan komparasi, dan kontrak data selesai lengkap. Pipeline siap diserahterimakan untuk pembuatan PyTorch Dataset/DataLoader dengan masking MLM pada tahap berikutnya.
