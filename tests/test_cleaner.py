"""
Unit test dan regression test untuk memvalidasi cleaner.py (v1.1.0).
Memeriksa: idempotensi kasus batas, unclosed template, deep nested templates,
dan idempotensi seluruh sampel 300 artikel aktual.
"""

import json
import os
import sys
import unittest
import unicodedata

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.data.cleaner import clean_text, CLEANER_VERSION


class TestCleaner(unittest.TestCase):

    def test_version(self):
        """Memastikan versi cleaner terdefinisi dengan benar."""
        self.assertEqual(CLEANER_VERSION, "1.1.0")

    def test_idempotence_general(self):
        """clean_text(clean_text(t)) harus sama dengan clean_text(t)."""
        raw_text = (
            "  Ini adalah artikel uji.\n\n"
            "Teks memiliki <ref>Catatan kaki</ref> dan [[Indonesia|Republik Indonesia]].\n"
            "Kunjungi https://wikipedia.org/wiki/Main_Page. Bagus!\n"
            "{{cite book|title=Buku}}\n\n"
            "Referensi\n"
            "1. Sumber A\n"
        )
        c1, _ = clean_text(raw_text)
        c2, _ = clean_text(c1)
        self.assertEqual(c1, c2)

    def test_regression_tab_before_boilerplate_heading(self):
        """Kasus 1: Narasi\\n\\tReferensi\\nSumber harus langsung terpotong pada pass 1."""
        raw = "Narasi utama\n\tReferensi\nSumber daftar pustaka"
        c1, _ = clean_text(raw)
        c2, _ = clean_text(c1)
        self.assertEqual(c1, "Narasi utama")
        self.assertEqual(c1, c2)

    def test_regression_crlf_before_boilerplate_heading(self):
        """Kasus 2: Narasi\\r\\nReferensi\\r\\nSumber harus langsung terpotong pada pass 1."""
        raw = "Narasi utama\r\nReferensi\r\nSumber daftar pustaka"
        c1, _ = clean_text(raw)
        c2, _ = clean_text(c1)
        self.assertEqual(c1, "Narasi utama")
        self.assertEqual(c1, c2)

    def test_regression_deeply_nested_templates(self):
        """Kasus 3: Template bersarang > 10 tingkat (15 tingkat) harus bersih dalam 1 pass."""
        raw = "Narasi awal " + "{{a|" * 15 + "konten" + "}}" * 15 + " penutup"
        c1, _ = clean_text(raw)
        c2, _ = clean_text(c1)
        self.assertEqual(c1, "Narasi awal penutup")
        self.assertEqual(c1, c2)

    def test_regression_unclosed_template_safety(self):
        """Kasus 4: Template tidak tertutup tidak boleh merusak teks sekelilingnya."""
        raw = "Awal kalimat {{unclosed template tanpa kurung tutup lanjut narasi."
        c1, _ = clean_text(raw)
        c2, _ = clean_text(c1)
        self.assertIn("Awal kalimat", c1)
        self.assertIn("lanjut narasi.", c1)
        self.assertEqual(c1, c2)

    def test_unicode_nfc_normalization(self):
        """Memastikan karakter kombinasi dinormalisasi ke NFC."""
        decomposed = "caf" + "e" + "\u0301"
        composed = "caf\u00e9"
        c1, actions = clean_text(decomposed)
        self.assertEqual(c1, composed)
        self.assertTrue(actions["unicode_normalized"])

    def test_preserve_stopwords_casing_punctuation_and_numbers(self):
        """Memastikan huruf kapital, angka, tanda baca, dan stopword tetap utuh."""
        raw = "Pada tahun 1945, Presiden Soekarno membacakan teks Proklamasi di Jakarta!"
        c1, _ = clean_text(raw)
        self.assertEqual(c1, raw)

    def test_safe_tag_handling_vs_code(self):
        """Memastikan tag ref dibuang, tag format di-strip, tapi operator '<-' di kode tetap aman."""
        raw = "Contoh tag <p>paragraf</p> dan kode <- [1, 2, 3] tidak boleh hilang!"
        c1, _ = clean_text(raw)
        self.assertIn("paragraf", c1)
        self.assertIn("<- [1, 2, 3]", c1)
        self.assertNotIn("<p>", c1)

    def test_wiki_links_expansion(self):
        """Memastikan [[Target|Display]] menjadi Display dan [[Target]] menjadi Target."""
        raw = "Kota [[Amsterdam]] adalah ibu kota [[Belanda|Negeri Kincir]]."
        c1, _ = clean_text(raw)
        self.assertEqual(c1, "Kota Amsterdam adalah ibu kota Negeri Kincir.")

    def test_conservative_url_removal(self):
        """Memastikan URL dibersihkan tanpa membuang tanda baca penutup kalimat."""
        raw = "Info lengkap di https://id.wikipedia.org/wiki/Indonesia. Hubungi kami!"
        c1, _ = clean_text(raw)
        self.assertEqual(c1, "Info lengkap di . Hubungi kami!")

    def test_section_truncation_standalone_vs_inline(self):
        """Memastikan pemotongan hanya terjadi pada heading mandiri."""
        inline_raw = "Buku ini menjadi referensi utama bagi para peneliti sejarah di Indonesia."
        c1, _ = clean_text(inline_raw)
        self.assertEqual(c1, inline_raw)

    def test_idempotence_on_actual_300_sample_dataset(self):
        """
        Pemeriksaan idempotensi pada SELURUH 300 artikel aktual di data/sample/wiki_sample_300.jsonl.
        clean_text(clean_text(t)) == clean_text(t) untuk 100% artikel.
        """
        sample_path = os.path.join(os.path.dirname(__file__), "..", "data", "sample", "wiki_sample_300.jsonl")
        if not os.path.exists(sample_path):
            self.skipTest("Berkas wiki_sample_300.jsonl belum ada")

        non_idempotent = []
        total = 0
        with open(sample_path, "r", encoding="utf-8") as f:
            for line_no, line in enumerate(f, 1):
                rec = json.loads(line)
                raw_text = rec.get("text", "")
                c1, _ = clean_text(raw_text)
                c2, _ = clean_text(c1)
                total += 1
                if c1 != c2:
                    non_idempotent.append({
                        "id": rec.get("id"),
                        "title": rec.get("title"),
                        "len_pass1": len(c1),
                        "len_pass2": len(c2)
                    })

        self.assertEqual(
            len(non_idempotent), 0,
            f"Ditemukan {len(non_idempotent)}/{total} artikel yang tidak idempotent: {non_idempotent[:3]}"
        )


if __name__ == "__main__":
    unittest.main()
