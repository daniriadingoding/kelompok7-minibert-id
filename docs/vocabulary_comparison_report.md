# Laporan Evaluasi dan Perbandingan Vocabulary Pilot (Train-Only)

Dokumen ini mencatat evaluasi empiris pembangunan vocabulary tokenizer tingkat kata (*word-level*) untuk pipeline Mini-BERT Bahasa Indonesia. Vocabulary dibangun **secara eksklusif hanya dari data split Train** menggunakan aturan deterministik: frekuensi menurun, lalu urutan leksikografis untuk frekuensi yang sama.

---

## 1. Statistik Korpus Berdasarkan Tokenizer Kata

- **Train Split**: 1,597,330 token isi (73,369 jenis kata unik / types)
- **Validation Split**: 156,741 token isi (17,246 types)
- **Test Split**: 202,360 token isi (19,416 types)
*Catatan: Token khusus ([PAD], [UNK], [CLS], [SEP], [MASK]) dikecualikan dari penyebut metrik coverage.*

---

## 2. Perbandingan Kandidat Vocabulary (5.000 vs 8.000 vs 12.000)

| Ukuran Target | Ukuran Aktual | Min Freq Train | Cutoff Token | Train Token Cov (%) | Train Type Cov (%) | Val Token Cov (%) | Val Token UNK (%) | Val Type Cov (%) | Val Type UNK (%) |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **5.000** | 5000 | 27 | `from` | 86.318% | 6.808% | 83.456% | 16.544% | 25.878% | 74.122% |
| **8.000** | 8000 | 14 | `may` | 89.971% | 10.897% | 87.341% | 12.659% | 35.997% | 64.003% |
| **12.000** | 12000 | 8 | `soerjo` | 92.535% | 16.349% | 89.749% | 10.251% | 44.961% | 55.039% |

---

## 3. Analisis Perbedaan Token-Level vs Type-Level Coverage

- **Token-Level Coverage**: Merefleksikan persentase kemunculan token dalam korpus yang dikenali oleh vocabulary. Karena distribusi kata mengikuti Hukum Zipf (*Zipf's Law*), sebagian besar kata berfrekuensi tinggi (seperti kata depan, kata hubung, dan istilah umum) terakomodasi bahkan pada ukuran 5.000 kata.
- **Type-Level Coverage**: Merefleksikan persentase *kamus kata unik* yang tertampung. Wikipedia Indonesia memiliki variasi kosakata luas (nama tokoh, lokasi geografis, istilah taksonomi biologi, dan serapan asing). Pada level tipe, ukuran 8.000 mencakup porsi jenis kata yang signifikan lebih baik daripada 5.000 tanpa harus menampung kata-kata *hapax legomena* (frekuensi 1 atau 2) yang rawan overfit pada ukuran 12.000.

---

## 4. Keputusan dan Rekomendasi Terkunci (Locked Configuration)

- **Ukuran Terpilih**: **8000 token** (aktual: 8000 termasuk 5 token khusus).
- **SHA-256 Hash Vocabulary**: `d2be29d07e76fe0cd15c3fe1b765325a5397a5e5fe30b2c6a5a019c976c552f2`
- **Rasional Pemilihan**:
  1. *Performa Validasi*: Memberikan token coverage yang sangat baik pada Validation split dengan penurunan tingkat UNK yang nyata dibanding 5.000.
  2. *Efisiensi GPU & Memori*: Bobot embedding layer untuk vocabulary 8.000 (`8.000 x d_model`) menjaga konsumsi VRAM pada GPU Anggota 2 (RTX 4060 Laptop 8GB) tetap sangat leluasa, menyisakan ruang maksimal untuk batch size dan kedalaman lapisan Transformer.
  3. *Penolakan Kebocoran*: Data **Test Split sama sekali tidak digunakan** dalam menentukan ukuran 8.000 ini.

---

## 5. Evaluasi Kunci pada Test Split (Pasca-Penguncian)

Evaluasi ini dilakukan hanya setelah konfigurasi 8.000 dikunci secara resmi:
- **Test Token-Level Coverage**: 88.764% (UNK rate: 11.236%)
- **Test Type-Level Coverage**: 33.452% (UNK rate: 66.548%)
