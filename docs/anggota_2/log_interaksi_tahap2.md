# LOG INTERAKSI LLM, KELOMPOK 7 (ANGGOTA 2)

* Tanggal Sesi: 23/10/2026
* Peran: Anggota 2 (Arsitektur Model & Hardware Lead)
* Target Modul: Rekonsiliasi Hash Vocabulary, TransformerEncoderLayer, BertEncoder, BertMLMHead, MiniBertForMaskedLM, Save/Load Strict, Kontrak Model, dan Smoke Test GPU
* Lingkungan Sistem:
  - Perangkat: Laptop Lenovo Legion Slim 5 (NVIDIA GeForce RTX 4060 Laptop GPU, 8GB VRAM)
  - Driver NVIDIA: 617.42 (Mendukung CUDA runtime hingga 13.4)
  - Interpreter: Python 3.13.2 pada `.venv-gpu`
  - Pustaka Utama: PyTorch 2.6.0+cu124

---

## 1. TAHAP KRONOLOGI PROMPT & RESPONS

### Prompt Sesi 3 (Dikutip Aktual):
> "Lanjutkan ke model Mini-BERT utuh dan uji integrasi satu batch. Jangan menjalankan training utama atau tuning milik Anggota 3.
> 
> A. BERESKAN INTEGRITAS ARTEFAK TERLEBIH DAHULU
> Hash vocabulary aktual yang dihitung ulang:
> d2be29d07e76fe0cd15c3fe1b765325a5397a5e5fe30b2c6a5a019c976c552f2
> Dokumentasi sebelumnya mencantumkan hash berbeda.
> 1. Telusuri perbedaan berdasarkan berkas dan log yang tersedia.
> 2. Bedakan perubahan serialisasi dari perubahan mapping token-ke-ID.
> 3. Verifikasi vocabulary aktual masih cocok dengan seluruh chunk:
>    - Tokenisasi dan encoding ulang dokumen menggunakan aturan chunking yang sama.
>    - Bandingkan input_ids, attention_mask, identitas chunk, dan jumlah chunk terhadap artefak yang tersedia.
>    - Lakukan pemeriksaan tanpa menimpa artefak sumber.
> 4. Jika ditemukan ketidakcocokan, berhenti sebelum training dan laporkan penyebab serta usulan perbaikan.
> 5. Jika cocok, dokumentasikan hasilnya dan selaraskan referensi hash pada dokumentasi aktif. Pertahankan catatan historis dengan koreksi, jangan mengubah sejarah seolah tidak pernah berbeda.
> 6. Model harus memeriksa kecocokan hash saat dimuat bersama tokenizer, bukan hanya menghitung hash baru lalu menerimanya tanpa pembandingan.
> 
> B. PERBAIKAN TERBATAS MODUL AWAL
> ...
> C. IMPLEMENTASIKAN ENCODER
> ...
> D. IMPLEMENTASIKAN MLM HEAD DAN MODEL UTUH
> ...
> E. SAVE/LOAD MODEL
> ...
> F. PENGUJIAN MODEL DAN INTEGRASI
> ...
> G. SMOKE TEST GPU
> ...
> H. KONTRAK DAN LOG"

### Alasan Khusus:
Menjamin bahwa fondasi artefak data dan vocabulary terbukti 100% konsisten sebelum membangun model utuh, memperbaiki mekanisme masking atensi dengan masked_fill dan penanganan numerik ketat, mengimplementasikan blok encoder Post-LayerNorm dan MLM head dengan weight tying, serta memvalidasi integrasi pada GPU nyata tanpa mengambil alih porsi pelatihan milik Anggota 3.

---

## 2. REALISASI DAN HASIL PENGUJIAN AKTUAL

### A. Rekonsiliasi Integritas Vocabulary dan Verifikasi Chunking
1. **Penelusuran Asal Perbedaan Hash**:
   - Berkas artefak fisik `vocab.json` dan laporan asli `docs/vocabulary_comparison_report.json` serta `.md` dari eksekusi `build_vocab.py` mencatat hash kanonikal SHA-256 `d2be29d07e76fe0cd15c3fe1b765325a5397a5e5fe30b2c6a5a019c976c552f2`.
   - String `8a4ca39b69b596e1...` hanya muncul pada teks dokumentasi `docs/data_contract_pilot.md` dan `README.md` akibat penulisan draf manual yang tidak sinkron, bukan karena perubahan mapping pada berkas `vocab.json`.
2. **Uji Verifikasi Determinisme Re-chunking**:
   - Seluruh 2.991 dokumen pada split Train (2.393 dok), Val (299 dok), dan Test (299 dok) di-tokenisasi dan dipotong ulang menggunakan tokenizer aktual melalui skrip `scratch/verify_chunks_integrity.py`.
   - Hasil perbandingan baris demi baris terhadap berkas artefak chunk sumber:
     * Split Train (27.002 chunk): Identik 100% (0 mismatch pada doc_id, chunk_index, input_ids, attention_mask, num_content_tokens).
     * Split Val (2.685 chunk): Identik 100% (0 mismatch).
     * Split Test (3.427 chunk): Identik 100% (0 mismatch).
   - Kesimpulan: Artefak vocabulary aktual sah, valid, dan cocok seutuhnya dengan seluruh dataset yang ada.

### B. Penyempurnaan Modul Awal
1. **Perbaikan MultiHeadSelfAttention**:
   - Menggantikan masking aditif dengan `scores.masked_fill(key_padding_mask, -10000.0)`.
   - Mempertahankan penolakan sampel dengan attention_mask seluruhnya bernilai 0.
   - Menguji isolasi padding dengan magnitudo hidden state sangat besar (1e5) pada posisi padding, membuktikan bahwa posisi valid tetap identik hingga presisi float32.
2. **Penyempurnaan MiniBertConfig**:
   - Menambahkan penolakan eksplisit untuk nilai numerik NaN atau Inf pada parameter float.
   - Menolak override argumen yang bertentangan dengan artefak fisik (vocab_size, pad_token_id, atau vocab_sha256).
   - Menolak pembacaan direktori jika berkas `tokenizer_config.json` mengalami korupsi format JSON.
3. **Penyempurnaan BertEmbeddings**:
   - Memvalidasi tipe data integer long dan device position_ids agar konsisten dengan input_ids jika diberikan secara manual.

### C. Implementasi Transformer Encoder dan MLM Head
1. **TransformerEncoderLayer & BertEncoder**:
   - Arsitektur Post-LayerNorm: Multi-Head Self-Attention -> Dropout -> Residual Add -> LayerNorm -> Feed-Forward Network (128 -> 512 -> 128 dengan GELU) -> Dropout -> Residual Add -> LayerNorm.
   - Menumpuk 2 layer encoder dan menerapkan attention_mask secara konsisten pada setiap layer.
2. **BertMLMHead & MiniBertForMaskedLM**:
   - Transformasi: Linear(128, 128) -> GELU -> LayerNorm -> Proyeksi Linear(128, 8000).
   - Weight tying: Matriks bobot proyeksi vocabulary diikat ke bobot word embeddings (`cls.decoder.weight = embeddings.word_embeddings.weight`), sementara bias output (8.000 dimensi) berdiri sendiri.
   - Inisialisasi bobot standar normal (mean=0, std=0.02) dengan pengikatan bobot yang aman dan penolakan double-counting pada penghitungan parameter unik.
   - Total parameter unik terhitung analitis dan empiris: Tepat **1.453.760 parameter**.

### D. Rangkaian Pengujian Unit dan Integrasi
- Menulis 9 pengujian integrasi baru pada `tests/test_model_architecture.py`.
- Menjalankan seluruh pengujian:
  * 36 pengujian data pipeline Anggota 1: Lulus (OK).
  * 23 pengujian primitif model Anggota 2: Lulus (OK).
  * 9 pengujian arsitektur model utuh Anggota 2: Lulus (OK).
  * **Total: 68/68 unit test lulus 100% (OK)** dalam 4,122 detik.

### E. Smoke Test GPU Aktual (RTX 4060 Laptop 8GB VRAM)
- Batch nyata: 4 sampel dari split Train (panjang urutan 64 token).
- Jumlah target MLM aktif: 28 token dari 256 posisi total (10,94%).
- Loss awal terukur: **9.0048** (Finite: True, konsisten dengan ekspektasi teoritis ln(8000) = 8.987).
- Peak Allocated VRAM: **51.25 MB**.
- Peak Reserved VRAM: **70.00 MB**.
- Waktu eksekusi 1 batch (Forward + Loss + Backward): **148.95 ms**.

---

## 3. PENANGANAN ERROR DAN PERBAIKAN

| No | Pesan Error Konsol | Analisis Penyebab | Solusi Teknis |
| :---: | :--- | :--- | :--- |
| 1 | `KeyError: 'doc_id'` pada `scratch/verify_chunks_integrity.py` | Berkas JSONL dokumen menggunakan kunci `"id"` sedangkan skrip verifikasi awal langsung membaca `"doc_id"`. | Menggunakan fallback `doc.get("id", f"doc_{total_docs}")` dan meng-unpack tuple keluaran `chunk_document`. |
| 2 | `AssertionError: 1453760 != 1453248` pada `test_unique_parameter_count` | Penghitungan manual awal mengabaikan LayerNorm kedua pada 2 blok encoder (2 * 256 = 512 parameter). | Menyesuaikan rumus manual dan assertion dengan nilai analitis aktual yang tepat (1.453.760 parameter). |
| 3 | `AssertionError: 7.769999980926514 != 7.77` pada `test_weight_tying_identity` | Presisi representasi biner 32-bit float menghasilkan pembulatan epsilon minor pada angka desimal. | Menggunakan `assertAlmostEqual(..., places=5)` untuk memvalidasi identitas bobot bertipe float32. |
