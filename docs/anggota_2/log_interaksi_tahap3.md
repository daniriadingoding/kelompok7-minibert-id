# LOG INTERAKSI LLM, KELOMPOK 7 (ANGGOTA 2)

* Tanggal Sesi: 23/10/2026
* Peran: Anggota 2 (Arsitektur Model & Hardware Lead)
* Target Modul: Penguatan Pemuatan Checkpoint (Hardened from_pretrained), Skrip Inferensi Masked LM (src/models/predict.py), Pengujian Unit Inferensi, Smoke Test GPU Lanjutan, Penyesuaian Metadata Status Checkpoint, Validasi Dictionary Konfigurasi Lengkap, dan Dokumentasi Serah Terima
* Lingkungan Sistem:
  - Perangkat: Laptop Lenovo Legion Slim 5 (NVIDIA GeForce RTX 4060 Laptop GPU, 8GB VRAM)
  - Driver NVIDIA: 617.42 (Mendukung CUDA runtime hingga 13.4)
  - Interpreter: Python 3.13.2 pada `.venv-gpu`
  - PyTorch: 2.6.0+cu124 (CUDA runtime build 12.4)

---

## 1. TAHAP KRONOLOGI PROMPT & RESPONS

### Prompt Sesi 4 (Dikutip Aktual):
> "Lanjutkan tahap akhir pekerjaan Anggota 2: penguatan pemuatan checkpoint, skrip inferensi [MASK], dan dokumentasi serah terima.
> 
> Model utuh dan verifikasi vocabulary, chunk sudah selesai. Jangan membangun ulang data, vocabulary, arsitektur, atau environment. Jangan menjalankan training utama/tuning milik Anggota 3.
> 
> A. PERKUAT PEMUATAN CHECKPOINT
> B. BUAT SKRIP INFERENSI
> C. SMOKE TEST TANPA TRAINING
> D. PERBAIKI SMOKE TEST GPU
> E. DOKUMENTASI SERAH TERIMA"

### Prompt Sesi 5 (Penyempurnaan Akhir Pra-Serah Terima):
> "Selesaikan dua perbaikan kecil sebelum serah terima Anggota 2. Jangan mengubah data, vocabulary, split, atau arsitektur, dan jangan menjalankan training utama.
> 
> 1. STATUS CHECKPOINT PADA INFERENSI
> - Hapus peringatan permanen bahwa semua checkpoint pasti berbobot acak.
> - Tambahkan metadata status checkpoint yang eksplisit, misalnya random_init, trained, atau unknown.
> - Checkpoint smoke test harus berstatus random_init.
> - Jika status tidak tersedia, tampilkan unknown, bukan mengklaim sudah atau belum dilatih.
> - Dokumentasikan bagaimana Anggota 3 memberi status trained saat menyimpan hasil training.
> - Jangan menyimpulkan status dari nama folder saja.
> 
> 2. VALIDASI KONFIGURASI CHECKPOINT
> - Wajibkan metadata config berupa dictionary yang lengkap.
> - Cocokkan seluruh field konfigurasi yang diharapkan dengan config.json.
> - Tolak config yang hilang, tidak lengkap, atau berbeda.
> - Pertahankan pemeriksaan hash vocabulary dan strict state_dict loading.
> - Tambahkan tes untuk config hilang dan field config yang dihapus.
> 
> 3. DOKUMENTASI METRIK
> - Gunakan masked-token loss, top-1 accuracy, dan top-5 accuracy pada labels != -100.
> - Agregasikan berdasarkan jumlah target.
> - Jangan menyebut exp(loss dari masking sebagian token) sebagai pseudo-perplexity standar atau perplexity teks penuh.
> 
> Jalankan tes yang relevan dan regresi setelah perubahan.
> Perbarui model_contract.md, panduan serah terima, serta log Anggota 2.
> Laporkan hasil aktual. Jangan melakukan commit/push.
> Setelah selesai, nyatakan implementasi Anggota 2 siap untuk integrasi training oleh Anggota 3."

### Alasan Khusus:
Memastikan integritas serialisasi checkpoint bebas dari celah konfigurasi yang tidak lengkap, menghapus bias asumsi status model pada fungsi inferensi dengan menggantikannya pada metadata biner eksplisit, mencegah kesalahpahaman teoritis pada pelaporan metrik eksponensial loss MLM, serta menjamin kehandalan seluruh unit test sebelum serah terima resmi ke Anggota 3.

---

## 2. REALISASI DAN HASIL PENGUJIAN AKTUAL

### A. Penguatan Pemuatan Checkpoint (`from_pretrained`)
1. **Validasi Dictionary Konfigurasi Lengkap**:
   - Checkpoint `model.pt` wajib menyertakan dictionary `"config"`. Jika kunci hilang atau bukan bertipe dictionary, pemuatan ditolak dengan pesan kesalahan jelas.
   - Seluruh field konfigurasi yang diharapkan dari `config.json` dicocokkan satu per satu dengan dictionary `"config"` pada checkpoint. Jika ada field yang dihapus, field asing yang disisipkan, atau perbedaan nilai parameter, pemuatan langsung ditolak (`ValueError`).
2. **Validasi Tiga Titik Hash Vocabulary**:
   - Memeriksa keselarasan `vocab_sha256` pada tiga sumber: konfigurasi disk, metadata checkpoint, dan tokenizer fisik pada `tokenizer_dir`.
   - Menolak hash kosong (string kosong atau None) secara eksplisit.
3. **Pemuatan Bobot Strict dan Weight Tying**:
   - Memuat bobot menggunakan `load_state_dict(..., strict=True)`.
   - Menegakkan kembali ikatan memori: `model.cls.decoder.weight = model.embeddings.word_embeddings.weight`.
4. **Ekstraksi Status Checkpoint**:
   - Mengekstrak metadata `checkpoint_status` dari checkpoint model.pt. Nilai yang sah meliputi `'random_init'`, `'trained'`, atau fallback `'unknown'` jika metadata tidak tersedia.

### B. Implementasi Skrip Inferensi (`src/models/predict.py`)
1. **Penanganan Status Pelatihan Dinamis**:
   - Menghapus teks peringatan permanen yang sebelumnya menganggap seluruh checkpoint pasti berbobot acak.
   - Menampilkan status checkpoint eksplisit (`random_init`, `trained`, atau `unknown`) yang dibaca murni dari metadata internal, bukan dari nama folder.
2. **Validasi Masukan & Komputasi Probabilitas**:
   - Mendeteksi token `[MASK]` dan normalisasi `[mask]` huruf kecil sebelum tokenisasi.
   - Menolak teks tanpa mask atau melebihi kapasitas 64 token tanpa pemotongan diam-diam.
   - Probabilitas dihitung melalui softmax atas seluruh 8.000 vocabulary. Token khusus (ID 0..4) dikecualikan dari pemeringkatan tanpa normalisasi ulang probabilitas.
   - Multi-mask dievaluasi secara independen dari konteks kalimat yang sama (non-autoregressive).
   - Melaporkan kata di luar vocabulary (`[UNK]`).

### C. Pengujian Unit dan Regresi Menyeluruh
Menambahkan skenario pengujian baru pada [`tests/test_inference.py`](file:///C:/Users/DANI/Documents/Kuliah/Semester%207/Generative%20AI/Mid%20Project/KELOMPOK%207/tests/test_inference.py):
1. `test_swapped_config_rejection`: Penolakan nilai konfigurasi yang sengaja ditukar.
2. `test_swapped_hash_rejection`: Penolakan hash vocabulary yang sengaja diubah pada checkpoint.
3. `test_empty_hash_rejection`: Penolakan checkpoint dengan hash kosong.
4. `test_missing_tokenizer_when_required`: Penolakan saat tokenizer wajib namun path tidak valid.
5. `test_predict_single_mask`: Validasi struktur inferensi satu mask dan status `random_init`.
6. `test_predict_multi_mask`: Validasi inferensi multi-mask independen.
7. `test_predict_lowercase_mask`: Validasi normalisasi token `[mask]`.
8. `test_predict_reject_no_mask`: Penolakan input tanpa mask.
9. `test_predict_reject_exceeding_length`: Penolakan panjang token > 64.
10. `test_predict_reject_invalid_top_k`: Penolakan nilai top-k tidak valid.
11. `test_save_load_inference_numerical_equivalence`: Konsistensi numerik logits sebelum dan sesudah save-load.
12. `test_missing_config_rejected`: Penolakan checkpoint tanpa dictionary `config`.
13. `test_deleted_config_field_rejected`: Penolakan checkpoint jika salah satu field konfigurasi dihapus.
14. `test_checkpoint_status_trained_and_unknown`: Validasi propagasi status `trained` dan fallback `unknown`.

Hasil eksekusi seluruh suite pengujian proyek:
```text
Ran 82 tests in 4.991s
OK
```
Rincian: 36 tes pipeline data Anggota 1, 23 tes primitif model, 9 tes arsitektur model utuh, 14 tes inferensi dan checkpoint hardening Anggota 2. Seluruh 82 pengujian lulus 100%.

### D. Smoke Test GPU Lanjutan (RTX 4060 Laptop 8GB VRAM)
- 1 batch nyata split Train (B=4, L=64, 28 target MLM).
- Logits, loss (9.0151), dan seluruh gradien dari 41 parameter terbukti bernilai finite (True).
- Versi runtime CUDA PyTorch: `CUDA 12.4` (Driver NVIDIA 617.42).
- Peak allocated VRAM: 51.25 MB, peak reserved: 70.00 MB, latensi: 148.16 ms.

---

## 3. PENANGANAN ERROR DAN DEBUGGING

| No | Pesan Error Konsol / Kasus Uji | Analisis Penyebab | Solusi Teknis |
| :---: | :--- | :--- | :--- |
| 1 | Input tokenisasi dengan `[mask]` huruf kecil menghasilkan `[UNK]` | Tokenizer BPE mengonversi `[mask]` menjadi subword atau UNK karena token khusus didefinisikan dalam huruf besar `[MASK]`. | Pada `predict.py`, lakukan deteksi regex case-insensitive dan ganti variasi `[mask]` menjadi token kanonikal `[MASK]` sebelum masuk ke tokenizer pipeline. |
| 2 | `ValueError: Checkpoint config does not match config.json` pada pengujian swapped config | Pengujian sengaja mengubah `d_model` pada `config.json` dari 128 menjadi 256. | Pesan error tertangkap tepat oleh mekanisme validasi `from_pretrained`, membuktikan proteksi bekerja dengan sempurna. |
| 3 | Metadata `config` tidak divalidasi kelengkapannya jika kunci parsial | Kode sebelumnya hanya mengiterasi kunci yang ada di dalam checkpoint tanpa memeriksa apakah ada field yang terhapus. | Mewajibkan perbandingan set lengkap antara `set(expected_config.keys())` dan `set(checkpoint_config.keys())`, sehingga field yang hilang atau field asing langsung ditolak. |
| 4 | Asumsi status model acak secara permanen pada inferensi | Skrip awal mencetak peringatan model belum dilatih tanpa membaca metadata model.pt. | Menambahkan atribut `checkpoint_status` pada checkpoint dictionary dan menampilkannya secara dinamis (`random_init`, `trained`, atau `unknown`). |
