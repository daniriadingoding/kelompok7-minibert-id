"""
Pengujian unit untuk validasi struktur, konten, dan portabilitas Jupyter Notebook:
notebooks/demo_minibert_indonesia.ipynb
"""

import json
import unittest
from pathlib import Path


class TestDemoNotebook(unittest.TestCase):
    """
    Rangkaian tes untuk memverifikasi integritas berkas demonstrasi Jupyter Notebook.
    """

    @classmethod
    def setUpClass(cls):
        cls.project_root = Path(__file__).resolve().parent.parent
        cls.notebook_path = cls.project_root / "notebooks" / "demo_minibert_indonesia.ipynb"

    def test_notebook_file_exists(self):
        """Memverifikasi bahwa berkas notebook benar-benar ada di direktori notebooks/."""
        self.assertTrue(
            self.notebook_path.exists(),
            f"Berkas notebook tidak ditemukan di {self.notebook_path}",
        )

    def test_notebook_json_structure_and_schema(self):
        """Memverifikasi bahwa berkas merupakan JSON valid dan mengikuti spesifikasi format notebook v4."""
        with open(self.notebook_path, "r", encoding="utf-8") as f:
            nb = json.load(f)

        self.assertIn("nbformat", nb)
        self.assertEqual(nb["nbformat"], 4)
        self.assertIn("nbformat_minor", nb)
        self.assertIn("cells", nb)
        self.assertIsInstance(nb["cells"], list)
        self.assertGreater(len(nb["cells"]), 10)

        # Validasi struktur setiap cell
        code_count = 0
        md_count = 0
        for i, cell in enumerate(nb["cells"]):
            self.assertIn("cell_type", cell, f"Cell #{i} tidak memiliki 'cell_type'")
            self.assertIn("metadata", cell, f"Cell #{i} tidak memiliki 'metadata'")
            self.assertIn("source", cell, f"Cell #{i} tidak memiliki 'source'")
            self.assertIn(cell["cell_type"], ["markdown", "code"])

            if cell["cell_type"] == "code":
                code_count += 1
                self.assertIn("outputs", cell, f"Code cell #{i} tidak memiliki 'outputs'")
                self.assertIsInstance(cell["outputs"], list)
            elif cell["cell_type"] == "markdown":
                md_count += 1

        self.assertGreater(code_count, 5, "Jumlah code cell kurang dari ekspektasi")
        self.assertGreater(md_count, 5, "Jumlah markdown cell kurang dari ekspektasi")

        # Jika nbformat tersedia di environment, jalankan validator resmi nbformat
        try:
            import nbformat
            nb_obj = nbformat.from_dict(nb)
            nbformat.validate(nb_obj)
        except ImportError:
            pass

    def test_notebook_sections_and_required_keywords(self):
        """Memverifikasi kehadiran seluruh bagian utama dan rujukan artefak resmi."""
        with open(self.notebook_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        kata_kunci_wajib = [
            "Mini-BERT Bahasa Indonesia dari Nol",
            "Pembagian Peran Anggota Kelompok",
            "Petunjuk Penggunaan",
            "Pemeriksaan Workspace dan Perangkat Komputasi",
            "Ringkasan Data dan Tokenizer",
            "Memuat Model Final",
            "Demonstrasi Prediksi Token [MASK]",
            "Hasil Eksperimen yang Tersimpan",
            "Keterbatasan Model dan Analisis Metodologis",
            "Petunjuk Lanjutan dan Reproduktibilitas",
            "runs/lr_1e3_gpu/best_model",
            "data/processed/pilot",
            "WordLevelTokenizer",
            "MiniBertForMaskedLM",
            "predict_mask",
            "5.4948",
            "17.4430",
            "31.7535",
            "27.002",
            "2.685",
            "3.426",
            "8.000",
        ]

        for kw in kata_kunci_wajib:
            self.assertIn(
                kw,
                raw_text,
                f"Kata kunci atau metrik wajib '{kw}' tidak ditemukan dalam isi notebook.",
            )

    def test_no_hardcoded_personal_paths(self):
        """Memastikan tidak ada path pribadi seperti AppData atau username laptop dalam notebook."""
        with open(self.notebook_path, "r", encoding="utf-8") as f:
            raw_text = f.read()

        path_terlarang = [
            "AppData",
            "C:\\Users\\DANI",
            "C:/Users/DANI",
        ]

        for p in path_terlarang:
            self.assertNotIn(
                p,
                raw_text,
                f"Path pribadi '{p}' ditemukan dalam notebook, melanggar prinsip portabilitas.",
            )

    def test_installation_cell_is_disabled(self):
        """Memastikan sel petunjuk instalasi dinonaktifkan secara default agar tidak auto-install saat Run All."""
        with open(self.notebook_path, "r", encoding="utf-8") as f:
            nb = json.load(f)

        code_cells = [c for c in nb["cells"] if c["cell_type"] == "code"]
        first_code = "".join(code_cells[0]["source"])

        # Sel pertama harus berupa komentar (tidak ada baris pip install aktif)
        for line in first_code.splitlines():
            clean = line.strip()
            if clean and not clean.startswith("#"):
                self.assertFalse(
                    clean.startswith("pip install") or clean.startswith("!pip install"),
                    "Perintah instalasi aktif ditemukan pada sel pertama, seharusnya berupa komentar/petunjuk.",
                )


if __name__ == "__main__":
    unittest.main()
