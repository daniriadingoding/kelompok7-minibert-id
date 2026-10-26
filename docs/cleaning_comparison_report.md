# Laporan Komparatif Pembersihan Data (Before-After Cleaning Report)

- **Versi Cleaner**: `1.1.0`
- **Berkas Mentah**: `data/sample/wiki_sample_300.jsonl`
- **Berkas Hasil Bersih**: `data/sample/wiki_sample_300_cleaned.jsonl`

## 1. Ringkasan Perubahan Agregat

| Metrik Evaluasi | Sebelum Pembersihan | Sesudah Pembersihan | Selisih / Perubahan |
| :--- | :---: | :---: | :---: |
| **Jumlah Artikel** | 300 | 300 | 0 (100% dipertahankan) |
| **Artikel Berubah** | - | 294 | 98.0% artikel disesuaikan |
| **Artikel Kosong (0 char)** | 0 | 0 | Tidak ada artikel yang musnah |
| **Total Karakter** | 1,780,294 | 1,708,068 | -4.06% |
| **Perkiraan Total Kata (Spasi)** | 238,713 | 229,965 | -3.66% |

## 2. Distribusi Proporsi Pengurangan Karakter per Artikel

| Metrik Rasio Pengurangan | Nilai Rasio | Persentase |
| :--- | :---: | :---: |
| **Minimum (Min)** | 0.0 | 0.0% |
| **Median (p50)** | 0.117 | 11.7% |
| **Persentil 90 (p90)** | 0.2859 | 28.59% |
| **Maksimum (Max)** | 0.7556 | 75.56% |
| **Rata-rata (Mean)** | 0.1423 | 14.23% |

## 3. Frekuensi Aturan Pembersihan yang Terpicu

| Nama Aturan Pembersihan | Jumlah Artikel Terpicu | Persentase |
| :--- | :---: | :---: |
| `unicode_normalized` | 0 | 0.0% |
| `control_chars_stripped` | 0 | 0.0% |
| `boilerplate_truncated` | 276 | 92.0% |
| `wiki_templates_cleaned` | 3 | 1.0% |
| `wiki_links_expanded` | 0 | 0.0% |
| `html_and_ref_cleaned` | 7 | 2.3% |
| `urls_removed` | 1 | 0.3% |
| `whitespace_normalized` | 293 | 97.7% |

## 4. Top 5 Artikel dengan Pengurangan Terbesar (Inspeksi Manual)

### 1. Margarita Teresa dari Spanyol (ID: `2699565`)
- **Panjang**: 2214 -> 541 karakter (Pengurangan: **75.6%**)
- **Aturan**: `boilerplate_truncated, whitespace_normalized`
- **Konteks Pemotongan Seksi**:
  - Heading dicocokkan: `Daftar pustaka`
  - Teks sebelum pemotongan: "...Velázquez, dan ia juga menjadi subjek lukisan-lukisan Velázquez yang lainnya."
  - Teks awal yang terbuang: "Andics, Hellmut, Die Frauen der Habsburger (Vienna: Jugend und Volk, 1985). In..."
- **Teks Tersisa**:
> "Margarita Teresa dari Spanyol (12 Juli 1651 – 12 Maret 1673) adalah sesosok perempuan yang mendapatkan gelar Maharani Romawi Suci, Adipatni Utama Austria, serta Ratu Hungaria dan Bohemia, berkat pernikahannya dengan Leopold I, Kaisar Romawi Suci, wal..."

### 2. Jean-Étienne Liotard (ID: `2699631`)
- **Panjang**: 565 -> 203 karakter (Pengurangan: **64.1%**)
- **Aturan**: `boilerplate_truncated, whitespace_normalized`
- **Konteks Pemotongan Seksi**:
  - Heading dicocokkan: `Referensi`
  - Teks sebelum pemotongan: "...t-potret berbahan pastel, dan membuat karya-karya dari perjalanannya ke Turki."
  - Teks awal yang terbuang: "Pranala luar 
 Short biography
 74 works by Liotard at the Musées d'Art et d'H..."
- **Teks Tersisa**:
> "Jean-Étienne Liotard (; ) adalah seorang pelukis, connoisseur seni rupa dan diler asal Swiss. Ia dikenal karena membuat potret-potret berbahan pastel, dan membuat karya-karya dari perjalanannya ke Turki."

### 3. Arnhem (ID: `1098`)
- **Panjang**: 259 -> 108 karakter (Pengurangan: **58.3%**)
- **Aturan**: `boilerplate_truncated, whitespace_normalized`
- **Konteks Pemotongan Seksi**:
  - Heading dicocokkan: `Lihat pula`
  - Teks sebelum pemotongan: "...i Gelderland, Belanda. Kota ini memiliki penduduk sekitar 146.095 jiwa.

Iklim"
  - Teks awal yang terbuang: "Gereja Santo Eusebius, Arnhem

Referensi

Pranala luar 
 Situs web resmi

Liha..."
- **Teks Tersisa**:
> "Arnhem adalah ibu kota provinsi Gelderland, Belanda. Kota ini memiliki penduduk sekitar 146.095 jiwa.

Iklim"

### 4. Eparki Joubbé, Sarba, dan Jounieh (ID: `2700871`)
- **Panjang**: 862 -> 402 karakter (Pengurangan: **53.4%**)
- **Aturan**: `boilerplate_truncated, whitespace_normalized`
- **Konteks Pemotongan Seksi**:
  - Heading dicocokkan: `Referensi`
  - Teks sebelum pemotongan: "...Pontificio Annuario, Libreria Editrice Vaticana, Città del Vaticano, 2003, ."
  - Teks awal yang terbuang: "Pranala luar 
 http://www.catholic-hierarchy.org/diocese/djsjm.html
 http://ww..."
- **Teks Tersisa**:
> "Eparki Joubbé, Sarba dan Jounieh (Latin: Eparchia Ioubbensis, Sarbensis et Iuniensis Maronitarum) adalah sebuah eparki Gereja Maronit yang menjadi Patriark Maronit Antiokhia di Lebanon. Pada 2013, terdapat 396,250 baptisan. Eparki tersebut sekarang d..."

### 5. Daftar sekolah dasar negeri di Aceh (ID: `2699228`)
- **Panjang**: 405 -> 199 karakter (Pengurangan: **50.9%**)
- **Aturan**: `boilerplate_truncated, whitespace_normalized`
- **Konteks Pemotongan Seksi**:
  - Heading dicocokkan: `Referensi`
  - Teks sebelum pemotongan: "...:

Update Terakhir : 27 Feb 2020

Sumber : Badan Pusat Statistik Provinsi Aceh"
  - Teks awal yang terbuang: "Jumlah Sekolah, Guru dan Murid Sekolah Dasar (SD) Negeri menurut Kabupaten/Kot..."
- **Teks Tersisa**:
> "Berikut adalah Daftar Sekolah Dasar Negeri di Aceh diurutkan berdasarkan masing-masing kabupaten dan kota sebagai berikut:

Update Terakhir : 27 Feb 2020

Sumber : Badan Pusat Statistik Provinsi Aceh"

## 5. Pemeriksaan Anomali Sisa & Duplikasi Baru

- Sisa pola mirip tag (`<...>`): **1**
  - `Elixir (bahasa pemrograman)`: `['<filename>', '<- [1,2,3,4,5], rem(n, 2) == 1, do: n*n\n[1, 9, 25]\n\nPencocokan pola (destructuring)\niex>', '<- 1..1000, do: spawn fn ->']` (Catatan: ini adalah kode program atau tanda kurung sudut matematika, bukan tag HTML)
- Sisa Wiki Markup (`{}`, `[[]]`): **0**
- Sisa URL di badan teks: **0**
- Duplikasi teks baru yang muncul setelah cleaning: **0** artikel identik

