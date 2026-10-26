# Laporan Audit & Pembersihan Dataset Pilot (3.000 Artikel Wikipedia)

- **Versi Cleaner**: `1.1.0`
- **Waktu Pemrosesan Bersih**: 3.96 detik
- **Ukuran Berkas Mentah**: 12.38 MB (12,978,094 bytes)
- **Ukuran Berkas Bersih**: 12.98 MB (13,605,387 bytes)

## 1. Ringkasan Eksekutif Pilot Dataset

| Metrik Evaluasi | Nilai Mentah | Nilai Bersih (Cleaned) | Selisih / Persentase |
| :--- | :---: | :---: | :---: |
| **Jumlah Artikel** | 3,000 | 3,000 | 0 duplikat dikeluarkan |
| **Artikel Mengalami Modifikasi** | - | 2,955 | 98.5% artikel disesuaikan |
| **Artikel Menjadi Kosong (0 char)** | 0 | 0 | 0 artikel musnah |
| **Total Karakter** | 12,445,627 | 11,788,620 | -5.28% |
| **Perkiraan Total Kata (Spasi)** | 1,682,527 | 1,602,732 | -4.74% |

## 2. Distribusi Panjang Karakter dan Kata (Cleaned)

> **Catatan Metrik**: Perkiraan kata dihitung berbasis *whitespace split*. Angka ini **bukan** jumlah token tokenizer final.

| Metrik Distribusi | Panjang Karakter | Perkiraan Kata (Whitespace) |
| :--- | :---: | :---: |
| **Minimum** | 4 | 1 |
| **Median (p50)** | 455.0 | 63.0 |
| **Persentil 90 (p90)** | 10,233.199999999999 | 1,410.1 |
| **Maksimum** | 152,362 | 20,220 |
| **Rata-rata (Mean)** | 3,929.54 | 534.24 |

## 3. Frekuensi Aturan Pembersihan yang Terpicu

| Aturan Pembersihan | Jumlah Terpicu | Persentase |
| :--- | :---: | :---: |
| `unicode_normalized` | 0 | 0.0% |
| `control_chars_stripped` | 0 | 0.0% |
| `boilerplate_truncated` | 2,738 | 91.3% |
| `wiki_templates_cleaned` | 16 | 0.5% |
| `wiki_links_expanded` | 2 | 0.1% |
| `html_and_ref_cleaned` | 28 | 0.9% |
| `urls_removed` | 12 | 0.4% |
| `whitespace_normalized` | 2,953 | 98.4% |

## 4. Analisis Deduplikasi Teks Persis & Keterbatasannya

- Jumlah teks hash SHA-256 unik: **3,000**
- Jumlah pasangan duplikat persis ditemukan: **0**
> **Keterbatasan Ilmiah**: Deduplikasi berbasis hash SHA-256 hanya menjaring duplikasi verbatim persis. Artikel dengan parafrasa ringan, variasi ejaan, atau kemiripan topikal tidak terdeteksi oleh deduplikasi persis ini dan memerlukan pemeriksaan n-gram minhash/Jaccard pada tahap lanjut.

## 5. Top 10 Pengurangan Terbesar (Inspeksi Lokasi Pemotongan)

### 1. Melati van Java (ID: `2706517`)
- **Panjang**: 2,918 -> 199 karakter (Pengurangan: **93.18%**)
- **Aturan**: `boilerplate_truncated, whitespace_normalized`
- **Konteks Lokasi Pemotongan**:
  - Heading dicocokkan: `Daftar pustaka`
  - Teks sebelum pemotongan: "...anda. Selain itu, ia juga memakai pseudonim Mathilde atau Max van Ravensteijn."
  - Teks awal yang terbuang: "Mathilde, ‘Twee moeders’, dalam De Katholieke Illustratie, 1872; novelle.
 Ma..."
- **Cuplikan Narasi Bersih Tersisa**:
> "Melati van Java adalah sebuah pseudonim dari Nicolina Maria (Marie) Sloot (), seorang penulis Hindia Belanda berdarah Belanda. Selain itu, ia juga memakai pseudonim Mathilde atau Max van Ravensteijn."

### 2. Arbor Low (ID: `2706143`)
- **Panjang**: 1,627 -> 141 karakter (Pengurangan: **91.33%**)
- **Aturan**: `boilerplate_truncated, whitespace_normalized`
- **Konteks Lokasi Pemotongan**:
  - Heading dicocokkan: `Referensi`
  - Teks sebelum pemotongan: "...ct, Derbyshire, Inggris. Arbor Low berada di kawasan White Peak, Peak District"
  - Teks awal yang terbuang: "Bacaan tambahan 
 
 Addy, S.O. (1911). The ‘Harbour’ and Barrows at Arbour-Low..."
- **Cuplikan Narasi Bersih Tersisa**:
> "Arbor Low adalah sebuah monumen henge Neolitikum di Peak District, Derbyshire, Inggris. Arbor Low berada di kawasan White Peak, Peak District"

### 3. Daftar sekolah menengah kejuruan di Tangerang (ID: `2698516`)
- **Panjang**: 324 -> 33 karakter (Pengurangan: **89.81%**)
- **Aturan**: `boilerplate_truncated, whitespace_normalized`
- **Konteks Lokasi Pemotongan**:
  - Heading dicocokkan: `Referensi`
  - Teks sebelum pemotongan: "...Daftar SMK di Kabupaten Tangerang"
  - Teks awal yang terbuang: "Data Sekolah

Lihat pula 
 Sekolah Menengah Kejuruan
 Daftar sekolah menengah..."
- **Cuplikan Narasi Bersih Tersisa**:
> "Daftar SMK di Kabupaten Tangerang"

### 4. Daftar sungai di Jambi (ID: `2701057`)
- **Panjang**: 932 -> 148 karakter (Pengurangan: **84.12%**)
- **Aturan**: `boilerplate_truncated, whitespace_normalized`
- **Konteks Lokasi Pemotongan**:
  - Heading dicocokkan: `Lihat pula`
  - Teks sebelum pemotongan: "...Menurut abjad 
 Batang Hari
 Batang Merangin

 Batang Tembesi

 Sungai Tungkal"
  - Teks awal yang terbuang: "Daftar sungai di Indonesia
 Daftar sungai di Sumatra

Referensi

Pustaka 
 W...."
- **Cuplikan Narasi Bersih Tersisa**:
> "Berikut ini adalah daftar sungai yang mengalir di wilayah provinsi Jambi:

Menurut abjad
Batang Hari
Batang Merangin

Batang Tembesi

Sungai Tungkal"

### 5. Yatim piatu (ID: `2862`)
- **Panjang**: 398 -> 69 karakter (Pengurangan: **82.66%**)
- **Aturan**: `boilerplate_truncated, whitespace_normalized`
- **Konteks Lokasi Pemotongan**:
  - Heading dicocokkan: `Lihat pula`
  - Teks sebelum pemotongan: "...Taksum adalah seseorang yang tidak lagi memiliki ayah sebelum baligh."
  - Teks awal yang terbuang: "Anak angkat, orang yang diasuh oleh orang lain dan dianggap sebagai anak sendi..."
- **Cuplikan Narasi Bersih Tersisa**:
> "Taksum adalah seseorang yang tidak lagi memiliki ayah sebelum baligh."

### 6. Anna dari Austria (1549–1580) (ID: `2699583`)
- **Panjang**: 1,268 -> 270 karakter (Pengurangan: **78.71%**)
- **Aturan**: `boilerplate_truncated, whitespace_normalized`
- **Konteks Lokasi Pemotongan**:
  - Heading dicocokkan: `Referensi`
  - Teks sebelum pemotongan: "...adalah putri sulung Maximilian II, Kaisar Romawi Suci, dan Maria dari Spanyol."
  - Teks awal yang terbuang: "J. Brouwer, Montigny, Representative of the Netherlands by Philip II (Amsterda..."
- **Cuplikan Narasi Bersih Tersisa**:
> "Anna dari Austria (2 November 1549 – 26 Oktober 1580) adalah seorang permaisuri Spanyol. Ia menjadi permaisuri berkat pernikahannya dengan pamannya sendiri, Raja Felipe II dari Spanyol.

Anna adalah putri sulung Maximili..."

### 7. Sinode Mahakudus (ID: `2706255`)
- **Panjang**: 1,052 -> 240 karakter (Pengurangan: **77.19%**)
- **Aturan**: `boilerplate_truncated, whitespace_normalized`
- **Konteks Lokasi Pemotongan**:
  - Heading dicocokkan: `Referensi`
  - Teks sebelum pemotongan: "...hakudus meliputi segala jenis pertanyaan gerejawi dan sebagian materi sekuler."
  - Teks awal yang terbuang: "Sumber 
 
 Statesman's handbook for Russia. 1896.
 Cracraft, James. "Diplomati..."
- **Cuplikan Narasi Bersih Tersisa**:
> "Sinode Mahakudus () adalah badan pemerintahan tertinggi Gereja Ortodoks Rusia antara 1721 dan 1918 (saat Gereja menghimpun ulang Patriarkat). Yurisdiksi Sinode Mahakudus meliputi segala jenis pertanyaan gerejawi dan seba..."

### 8. Kuali Gundestrup (ID: `2706976`)
- **Panjang**: 1,033 -> 242 karakter (Pengurangan: **76.57%**)
- **Aturan**: `boilerplate_truncated, whitespace_normalized`
- **Konteks Lokasi Pemotongan**:
  - Heading dicocokkan: `Referensi`
  - Teks sebelum pemotongan: "...nempatkannya dalam akhir periode La Tène atau awal Zaman Besi Romawi.

Catatan"
  - Teks awal yang terbuang: "Green, Miranda, Celtic Art, Reading the Messages, 1996, The Everyman Art Libra..."
- **Cuplikan Narasi Bersih Tersisa**:
> "Kuali Gundestrup adalah sebuah bejana perak yang kaya akan dekorasi, yang berasal dari antara tahun 200 SM dan 300 M, atau setidaknya antara 150 SM dan 1 SM, Ini menempatkannya dalam akhir periode La Tène atau awal Zaman..."

### 9. Margarita Teresa dari Spanyol (ID: `2699565`)
- **Panjang**: 2,214 -> 541 karakter (Pengurangan: **75.56%**)
- **Aturan**: `boilerplate_truncated, whitespace_normalized`
- **Konteks Lokasi Pemotongan**:
  - Heading dicocokkan: `Daftar pustaka`
  - Teks sebelum pemotongan: "...Velázquez, dan ia juga menjadi subjek lukisan-lukisan Velázquez yang lainnya."
  - Teks awal yang terbuang: "Andics, Hellmut, Die Frauen der Habsburger (Vienna: Jugend und Volk, 1985). In..."
- **Cuplikan Narasi Bersih Tersisa**:
> "Margarita Teresa dari Spanyol (12 Juli 1651 – 12 Maret 1673) adalah sesosok perempuan yang mendapatkan gelar Maharani Romawi Suci, Adipatni Utama Austria, serta Ratu Hungaria dan Bohemia, berkat pernikahannya dengan Leop..."

### 10. Valsgärde (ID: `2705336`)
- **Panjang**: 843 -> 212 karakter (Pengurangan: **74.85%**)
- **Aturan**: `boilerplate_truncated, whitespace_normalized`
- **Konteks Lokasi Pemotongan**:
  - Heading dicocokkan: `Referensi`
  - Teks sebelum pemotongan: "...wedia dan kepercayaan pagan di Swedia. Kebun saat ini bermula dari abad ke-16."
  - Teks awal yang terbuang: "Arwidsson, Greta (1942) Valsgärde 6 (Almqvist & Wiksells Boktryckeri-A.B. Upps..."
- **Cuplikan Narasi Bersih Tersisa**:
> "Valsgärde atau Vallsgärde adalah sebuah kebun di sungai Fyris, sekitar tiga kilometer dari utara Gamla Uppsala, pusat kuno raja-raja Swedia dan kepercayaan pagan di Swedia. Kebun saat ini bermula dari abad ke-16."

## 6. Contoh Kualitatif Representatif (Beragam Tipe Dokumen)

### A. Teks Pendek (Rentang Bawah)
- **Judul**: Karo (ID: `3986` | 4 char / 1 kata)
> "Nama"

### B. Teks Sedang (Rentang Median)
- **Judul**: (264147) 2009 UF132 (ID: `1211161` | 455 char / 59 kata)
> "(264147) 2009 UF132 adalah sebuah asteroid. Asteroid ini merupakan bagian dari asteroid Troya Yupiter, yang terletak di orbit Yupiter. Eksentrisitas orbit asteroid ini tercatat sebesar 0.060, sementara magnitudo mutlaknya adalah 12.9.

Pembentukan

Seperti asteroid secara keselur"

### C. Teks Panjang (Rentang Atas)
- **Judul**: Indonesia (ID: `44` | 152362 char / 20220 kata)
> "Indonesia (), dikenal dengan nama resmi Republik Indonesia atau lebih lengkapnya Negara Kesatuan Republik Indonesia, adalah negara kepulauan di Asia Tenggara yang dilintasi garis khatulistiwa dan berada di antara daratan benua Asia dan Oseania sehingga dikenal sebagai negara lint"

### D. Teks Dominan Daftar / Katalog
- **Judul**: Skuad Piala Dunia Antarklub FIFA 2015 (ID: `2701216` | 635 char / 84 kata)
> "Setiap tim yang berpartisipasi dalam Piala Dunia Antarklub FIFA 2015 wajib mendaftarkan skuad berisi 23 pemain (tiga di antaranya merupakan penjaga gawang) sebelum batas akhir yang ditetapkan oleh FIFA, yakni pada 30 November 2015. Penggantian pemain akibat cedera diizinkan palin"

### E. Teks Memuat Sintaks Teknis / Kode Program
- **Judul**: Yesus (disambiguasi) (ID: `1123` | 1876 char / 271 kata)
> "Kitab Suci
Yesus Kristus: tokoh sentral dalam agama Kristen. Dalam agama Islam dikenal dengan nama Isa (Al-Masih). Orang Kristen yang berbahasa Arab mengenalnya dengan nama Yashu' atau Yashuk.
Yesus bin Sirakh, penulis Kitab Yesus bin Sirakh
Yesus Barabas, penjahat yang dibebaska"

### F. Teks Memuat Istilah Taksonomi / Kutipan Bahasa Lain
- **Judul**: Rencana pendudukan kembali Indonesia (ID: `2698915` | 2694 char / 350 kata)
> "Setelah Jepang menyerah pada tanggal 15 Agustus 1945, ia harus melepaskan kembali daerah pendudukannya. Ini berarti daerah-daerah koloni yang semula direbut dari bangsa Barat yang tergabung ke dalam blok Sekutu harus dikembalikan. Memang negara-negara barat itu masih menganggap d"

