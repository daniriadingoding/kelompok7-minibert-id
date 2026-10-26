# Laporan Audit Kualitas Data Sampel Wikipedia Bahasa Indonesia

- **Berkas Data**: `data/sample/wiki_sample_300.jsonl`
- **Ukuran Berkas**: 1795.65 KB (1,838,747 bytes)
- **Total Rekaman Valid**: 300
- **Baris JSON Rusak/Gagal**: 0

## 1. Analisis Kelengkapan & Tipe Kolom

| Kolom | Hadir (Valid) | Hilang (Missing Key) | Null (`None`) | String Kosong | Salah Tipe | Tipe Data |
| :--- | :---: | :---: | :---: | :---: | :---: | :--- |
| `id` | 300 | 0 | 0 | 0 | 0 | str |
| `url` | 300 | 0 | 0 | 0 | 0 | str |
| `title` | 300 | 0 | 0 | 0 | 0 | str |
| `text` | 300 | 0 | 0 | 0 | 0 | str |

### Keunikan Rekaman (Berdasarkan SHA-256)
- ID unik: **300/300** (Duplikat: 0)
- Teks unik: **300/300** (Duplikat: 0)

## 2. Distribusi Panjang Karakter & Perkiraan Kata

> **Catatan**: Perkiraan kata dihitung berbasis *whitespace split*. Angka ini **bukan** jumlah token tokenizer final.

| Metrik | Panjang Karakter | Perkiraan Kata (Whitespace) |
| :--- | :---: | :---: |
| **Minimum** | 127 | 16 |
| **Median (p50)** | 709.5 | 95.0 |
| **Persentil 90 (p90)** | 20,103.40000000001 | 2,643.300000000001 |
| **Maksimum** | 87,157 | 11,417 |
| **Rata-rata (Mean)** | 5,934.31 | 795.71 |

## 3. Indikasi Anomali & Temuan Teks

| Indikator Anomali | Jumlah Artikel | Persentase | Catatan Analisis |
| :--- | :---: | :---: | :--- |
| Indikasi Pola Mirip Tag (`<...>`) | 9 | 3.0% | Termasuk tag HTML referensi (`<ref>`), serta kode program non-HTML |
| Sisa Wiki Markup (`{}`, `[[]]`) | 3 | 1.0% | Template kutipan atau tautan internal wiki yang belum terurai |
| URL di Badan Teks | 12 | 4.0% | Tautan web mentah (`http://`, `https://`) di dalam teks narasi |
| Karakter Kontrol Non-Printable | 0 | 0.0% | Karakter kontrol sistem biner (selain `\n` dan `\t`) |
| Artikel Sangat Pendek (< 100 char) | 0 | 0.0% | Potensi rintisan/stub dengan konteks kalimat sangat minim |
| Heading Seksi Penutup (Referensi, dsb.) | 272 | 90.7% | Heading baris mandiri (Referensi, Pranala luar, Lihat pula) |

### Contoh Konteks Anomali Aktual

#### Kategori Anomali: `tag_like`
- **Artikel `Bahasa Melayu Klasik` (ID: `1013`)**:
  - Pola ditemukan: `['<p>', '<p>', '<p>', '<p>', '<p>']`
  - Cuplikan teks: "Bahasa Melayu Klasik adalah dialek bahasa Melayu yang dipakai oleh Kesultanan Melaka (abad ke-14), Kesultanan Aceh, dan sejumlah entitas politik lain di sekitarnya hingga abad ke-1..."
- **Artikel `Sastra Jawa` (ID: `873`)**:
  - Pola ditemukan: `['<p xml:lang="jv">']`
  - Cuplikan teks: "Sastra Jawa secara global bisa dibagi menjadi dua kategori yaitu yang ditulis dalam bentuk prosa atau puisi. Dalam bentuk prosa biasanya disebut gancaran dan dalam bentuk puisi bia..."
- **Artikel `Modu Chanyu` (ID: `2698634`)**:
  - Pola ditemukan: `['</ref>']`
  - Cuplikan teks: "Modu, Modun, atau Maodun (, skt. 234 – skt. 174 SM) merupakan penguasa Xiongnu yang kedua yang diketahui dan pendiri kekaisaran Xiongnu. Ia menjadi penguasa Xiongnu setelah ia meme..."

#### Kategori Anomali: `wiki_markup`
- **Artikel `Yesus` (ID: `843`)**:
  - Pola ditemukan: `['{{cite book|first=Rabbi Joshua|last=Garroway|chapter=Ioudaios|editors=Amy-Jill Levine, Marc Z. Brettler|url=https://books.google.co.uk/books?id=DZRJ5zXUI2QC&lpg=PA524&pg=PA524|title=The Jewish Annotated New Testament|publisher=Oxford University Press|date=2011|isbn=9780195297706|pages=524–526}}']`
  - Cuplikan teks: "Yesus (, ;  4 SM  sampai 30–33 M; ; ), juga disebut sebagai Yesus dari Nazaret atau Yesus Kristus, adalah tokoh sentral Kekristenan. Menurut sebagian besar denominasi Kristen, Yesu..."
- **Artikel `Hamengkubuwana IX` (ID: `792`)**:
  - Pola ditemukan: `['{{efn|Bergelar Kanjeng Gusti Pangeran Adipati Anom Hamengku Negara Sudibya Raja Putra Narendra ing Mataram.}}']`
  - Cuplikan teks: "Jenderal TNI. (Tit.) (Purn.) H. Sri Sultan Hamengkubuwana IX (; , lahir dengan nama Gusti Raden Mas Dorodjatun) adalah Sultan Yogyakarta kesembilan dan Gubernur Daerah Istimewa Yog..."
- **Artikel `Dharma` (ID: `896`)**:
  - Pola ditemukan: `['{{multiple image\n| perrow            = 2\n| total_width       = 250\n| caption_align     = center\n| title             = Dharma\n| image1            = A havan ceremony on the banks of Ganges, Muni ki Reti, Rishikesh.jpg\n| caption1          = Ritual dan ritus peralihan\n| image2            = Yoga Meditation Pos-410px.png\n| caption2          = Yoga, perilaku pribadi\n| image3            = Ahimsa.svg\n| caption3          = Kebajikan seperti ahimsa (tanpa kekerasan)\n| image4            = Balanced scales.svg\n| caption4          = Hukum dan keadilan\n| image5            = Raja Ravi Varma - Sankaracharya.jpg\n| caption5          = Sannyasa dan tahapan kehidupan<ref>Harold Coward (2004), "bioetika Hindu untuk abad kedua puluh satu", JAMA: The Journal of American Medical Association\' \', 291(22), hlm. 2759–2760; Quote–"Pendekatan tahapan kehidupan Hindu (ashrama dharma)..."</ref>\n| image6            = Dharma Wheel.svg\n| caption6          = Tugas, seperti belajar dari guru\n}}']`
  - Cuplikan teks: "Dharma atau Sanatana Dharma adalah kebenaran absolut yang kekal dan abadi. "kebenaran" berbeda dengan "benar" sebab "benar" bersifat bersifat relatif, menyesuaikan dengan sudut pan..."

#### Kategori Anomali: `url_in_text`
- **Artikel `Sastra Jawa` (ID: `873`)**:
  - Pola ditemukan: `['http://www.sastra.org']`
  - Cuplikan teks: "Sastra Jawa secara global bisa dibagi menjadi dua kategori yaitu yang ditulis dalam bentuk prosa atau puisi. Dalam bentuk prosa biasanya disebut gancaran dan dalam bentuk puisi bia..."
- **Artikel `Eparki Sidon` (ID: `2699191`)**:
  - Pola ditemukan: `['http://www.catholic-hierarchy.org/diocese/dsadm.html', 'http://www.gcatholic.org/dioceses/diocese/said1.htm']`
  - Cuplikan teks: "Eparki Sidon (Latin: Eparchia Sidoniensis Maronitarum) adalah sebuah eparki Gereja Maronit yang menjadi subyek langsung dari Patriark Maronit Antiokhia di Lebanon. Pada 2014, terda..."
- **Artikel `Winston Churchill` (ID: `79`)**:
  - Pola ditemukan: `['http://www.bbc.co.uk/programmes/b00tpsvk']`
  - Cuplikan teks: "Sir Winston Leonard Spencer-Churchill (30 November 187424 Januari 1965) adalah seorang politikus, perwira militer, dan penulis Britania Raya. Ia merupakan Perdana Menteri Britania ..."

#### Kategori Anomali: `section_headings`
- **Artikel `Daftar sekolah dasar negeri di Bengkulu` (ID: `2700350`)**:
  - Heading baris: `['Referensi', 'Pranala luar ']`
- **Artikel `Arnhem` (ID: `1098`)**:
  - Heading baris: `['Lihat pula ', 'Referensi', 'Pranala luar ']`
- **Artikel `Keuskupan Agung Vitória` (ID: `2700245`)**:
  - Heading baris: `['Referensi']`

## 4. Sampel Inspeksi Berdasarkan Stratifikasi Panjang

### Artikel Terpendek (Rentang Bawah)
- **Judul**: Oxycanus sirpus (ID: `2699880`)
- **Panjang**: 127 karakter (~16 kata)
- **URL**: https://id.wikipedia.org/wiki/Oxycanus%20sirpus
- **Cuplikan**:
> "Oxycanus sirpus adalah sejenis ngengat dari keluarga Hepialidae. Jenis ngengat ini ditemukan di Victoria, Australia.

Referensi"

### Artikel Median (Rentang Tengah)
- **Judul**: Federasi Futsal Indonesia (ID: `2699104`)
- **Panjang**: 711 karakter (~96 kata)
- **URL**: https://id.wikipedia.org/wiki/Federasi%20Futsal%20Indonesia
- **Cuplikan**:
> "adalah sebuah organisasi olahraga yang menaungi aktivitas futsal di Indonesia. Organisasi ini berada dalam naungan Persatuan Sepak Bola Seluruh Indonesia. Organisasi ini merupakan pembaruan dari Badan Futsal Nasional yang dibubarkan PSSI pada tahun 2014, serta berganti nama dari Asosiasi Futsal Indo"

### Artikel Terpanjang (Rentang Atas)
- **Judul**: Yesus (ID: `843`)
- **Panjang**: 87157 karakter (~11417 kata)
- **URL**: https://id.wikipedia.org/wiki/Yesus
- **Cuplikan**:
> "Yesus (, ;  4 SM  sampai 30–33 M; ; ), juga disebut sebagai Yesus dari Nazaret atau Yesus Kristus, adalah tokoh sentral Kekristenan. Menurut sebagian besar denominasi Kristen, Yesus dipandang sebagai Allah Putra (Allah Anak). Namun, seluruh umat Kristen meyakini bahwa Yesus adalah Mesias (atau Krist"

