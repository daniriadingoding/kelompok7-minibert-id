"""
Unit test untuk memvalidasi logika sampling pada data tiruan (mock data).
Memeriksa: batas pemeriksaan mutlak, penanganan duplikat, teks kosong, dan status parsial/lengkap.
"""

import sys
import unittest
import os

sys.stdout.reconfigure(encoding="utf-8")

# Tambahkan root proyek ke sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.data.download_sample import (
    sample_records_from_iterable,
    validate_sampling_arguments
)


class TestSamplingLogic(unittest.TestCase):

    def test_argument_validation(self):
        """Memastikan parameter yang tidak valid ditolak dengan ValueError."""
        with self.assertRaises(ValueError):
            validate_sampling_arguments(target_samples=0, buffer_size=100, max_examined_limit=500, max_init_retries=3)
        with self.assertRaises(ValueError):
            validate_sampling_arguments(target_samples=100, buffer_size=-1, max_examined_limit=500, max_init_retries=3)
        with self.assertRaises(ValueError):
            validate_sampling_arguments(target_samples=100, buffer_size=100, max_examined_limit=50, max_init_retries=3)
        with self.assertRaises(ValueError):
            validate_sampling_arguments(target_samples=100, buffer_size=100, max_examined_limit=500, max_init_retries=0)

    def test_mock_sampling_complete(self):
        """Uji alur normal: mencapai target sampel unik."""
        mock_data = [
            {"id": f"id_{i}", "url": f"http://test/{i}", "title": f"Judul {i}", "text": f"Teks artikel {i}"}
            for i in range(10)
        ]
        collected, examined, dupes, empty, status = sample_records_from_iterable(
            stream=mock_data,
            target_samples=5,
            max_examined_limit=20
        )
        self.assertEqual(len(collected), 5)
        self.assertEqual(examined, 5)
        self.assertEqual(dupes, 0)
        self.assertEqual(empty, 0)
        self.assertEqual(status, "complete")

    def test_mock_sampling_with_duplicates_and_empty(self):
        """Uji penanganan duplikat ID/judul dan teks kosong."""
        mock_data = [
            {"id": "1", "url": "url1", "title": "A", "text": "Valid 1"},
            {"id": "2", "url": "url2", "title": "B", "text": "   "},      # Kosong
            {"id": "1", "url": "url1", "title": "A", "text": "Valid 1"},  # Duplikat ID
            {"id": "3", "url": "url3", "title": "A", "text": "Valid 3"},  # Duplikat Judul
            {"id": "4", "url": "url4", "title": "C", "text": ""},         # Kosong
            {"id": "5", "url": "url5", "title": "D", "text": "Valid 5"},
            {"id": "6", "url": "url6", "title": "E", "text": "Valid 6"}
        ]
        collected, examined, dupes, empty, status = sample_records_from_iterable(
            stream=mock_data,
            target_samples=3,
            max_examined_limit=10
        )
        self.assertEqual(len(collected), 3)
        self.assertEqual(empty, 2)
        self.assertEqual(dupes, 2)
        self.assertEqual(status, "complete")
        # ID yang terkumpul harus unik: 1, 5, 6
        collected_ids = [c["id"] for c in collected]
        self.assertEqual(collected_ids, ["1", "5", "6"])

    def test_mock_sampling_max_examined_limit(self):
        """Uji batas pemeriksaan mutlak: berhenti meskipun target belum tercapai (partial status)."""
        # Semua data duplikat setelah rekaman pertama
        mock_data = [
            {"id": "1", "url": "url1", "title": "A", "text": "Valid 1"},
            {"id": "1", "url": "url1", "title": "A", "text": "Valid 1"},
            {"id": "1", "url": "url1", "title": "A", "text": "Valid 1"},
            {"id": "1", "url": "url1", "title": "A", "text": "Valid 1"},
            {"id": "1", "url": "url1", "title": "A", "text": "Valid 1"},
            {"id": "2", "url": "url2", "title": "B", "text": "Valid 2"}
        ]
        collected, examined, dupes, empty, status = sample_records_from_iterable(
            stream=mock_data,
            target_samples=5,
            max_examined_limit=3  # Berhenti setelah memeriksa 3 rekaman
        )
        self.assertEqual(examined, 3)
        self.assertEqual(len(collected), 1)
        self.assertEqual(dupes, 2)
        self.assertEqual(status, "partial")


if __name__ == "__main__":
    unittest.main()
