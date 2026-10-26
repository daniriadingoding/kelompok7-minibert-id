"""
Rangkaian pengujian unit untuk fungsi inferensi dan pemuatan checkpoint Mini-BERT:
1. Inferensi dengan satu token [MASK].
2. Inferensi dengan beberapa token [MASK] (multi-mask).
3. Inferensi dengan token [mask] huruf kecil.
4. Penolakan input teks kosong atau spasi.
5. Penolakan input tanpa token [MASK].
6. Penolakan input yang melebihi panjang maksimum model (tanpa pemotongan diam-diam).
7. Penolakan nilai top-k tidak valid (0 atau negatif).
8. Penolakan pemuatan jika tokenizer hash tidak cocok.
9. Penolakan pemuatan jika config.json dan model.pt tidak sinkron.
10. Penolakan pemuatan jika metadata hash kosong pada checkpoint.
11. Konsistensi hasil prediksi sebelum dan sesudah save-load.
"""

import json
import os
import tempfile
import unittest

import torch

from src.models.bert import MiniBertForMaskedLM
from src.models.config import MiniBertConfig
from src.models.predict import predict_mask


class TestInferenceAndCheckpointHardening(unittest.TestCase):
    """Pengujian inferensi predict_mask dan penguatan loader from_pretrained."""

    @classmethod
    def setUpClass(cls):
        cls.tokenizer_dir = "data/processed/pilot"
        cls.smoke_dir = "scratch/random_init_smoke_test"
        os.makedirs(cls.smoke_dir, exist_ok=True)

        torch.manual_seed(42)
        cls.config = MiniBertConfig.from_tokenizer_directory(cls.tokenizer_dir)
        cls.model = MiniBertForMaskedLM(cls.config)
        cls.model.save_pretrained(cls.smoke_dir, filename="model.pt", checkpoint_status="random_init")

    def test_single_mask_prediction(self):
        """Memastikan inferensi dengan satu [MASK] menghasilkan prediksi terstruktur yang valid."""
        text = "Indonesia adalah negara [MASK] di Asia Tenggara."
        res = predict_mask(
            text=text,
            checkpoint_dir=self.smoke_dir,
            tokenizer_dir=self.tokenizer_dir,
            top_k=5,
            device="cpu",
        )
        self.assertEqual(res["num_masks"], 1)
        self.assertEqual(res["checkpoint_status"], "random_init")
        self.assertEqual(len(res["predictions"]), 1)
        cands = res["predictions"][0]["candidates"]
        self.assertEqual(len(cands), 5)
        for c in cands:
            self.assertGreater(c["token_id"], 4)  # Memastikan bukan token khusus
            self.assertGreater(c["probability"], 0.0)

    def test_multiple_masks_prediction(self):
        """Memastikan inferensi dengan beberapa [MASK] memprediksi setiap posisi secara mandiri."""
        text = "Ibu kota [MASK] berada di pulau [MASK]."
        res = predict_mask(
            text=text,
            checkpoint_dir=self.smoke_dir,
            tokenizer_dir=self.tokenizer_dir,
            top_k=3,
            device="cpu",
        )
        self.assertEqual(res["num_masks"], 2)
        self.assertEqual(len(res["predictions"]), 2)
        self.assertEqual(res["predictions"][0]["sequence_position"], 3)
        self.assertEqual(res["predictions"][1]["sequence_position"], 7)

    def test_lowercase_mask_token(self):
        """Memastikan [mask] huruf kecil dinormalisasi otomatis ke [MASK] dan berhasil diprediksi."""
        text = "Presiden membaca teks [mask] proklamasi."
        res = predict_mask(
            text=text,
            checkpoint_dir=self.smoke_dir,
            tokenizer_dir=self.tokenizer_dir,
            top_k=3,
            device="cpu",
        )
        self.assertEqual(res["num_masks"], 1)
        self.assertEqual(len(res["predictions"][0]["candidates"]), 3)

    def test_empty_text_rejected(self):
        """Memastikan teks kosong atau spasi murni ditolak dengan eksepsi jelas."""
        with self.assertRaises(ValueError):
            predict_mask(
                text="   ",
                checkpoint_dir=self.smoke_dir,
                tokenizer_dir=self.tokenizer_dir,
            )

    def test_text_without_mask_rejected(self):
        """Memastikan teks tanpa token [MASK] ditolak."""
        with self.assertRaises(ValueError):
            predict_mask(
                text="Kalimat ini tidak memiliki target penutup.",
                checkpoint_dir=self.smoke_dir,
                tokenizer_dir=self.tokenizer_dir,
            )

    def test_excessive_length_rejected(self):
        """Memastikan teks melebihi max_position_embeddings (64) ditolak tanpa pemotongan diam-diam."""
        # 70 kata + [MASK]
        long_text = "kata " * 70 + "[MASK]."
        with self.assertRaises(ValueError):
            predict_mask(
                text=long_text,
                checkpoint_dir=self.smoke_dir,
                tokenizer_dir=self.tokenizer_dir,
            )

    def test_invalid_top_k_rejected(self):
        """Memastikan nilai top_k non-positif ditolak."""
        with self.assertRaises(ValueError):
            predict_mask(
                text="Tes [MASK]",
                checkpoint_dir=self.smoke_dir,
                tokenizer_dir=self.tokenizer_dir,
                top_k=0,
            )
        with self.assertRaises(ValueError):
            predict_mask(
                text="Tes [MASK]",
                checkpoint_dir=self.smoke_dir,
                tokenizer_dir=self.tokenizer_dir,
                top_k=-5,
            )

    def test_save_and_load_inference_consistency(self):
        """Memastikan hasil inferensi sebelum dan sesudah save-load identik secara numerik."""
        text = "Matahari terbit di sebelah [MASK]."
        res_before = predict_mask(
            text=text,
            checkpoint_dir=self.smoke_dir,
            tokenizer_dir=self.tokenizer_dir,
            top_k=5,
            device="cpu",
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            self.model.save_pretrained(tmpdir, filename="model.pt")
            res_after = predict_mask(
                text=text,
                checkpoint_dir=tmpdir,
                tokenizer_dir=self.tokenizer_dir,
                top_k=5,
                device="cpu",
            )

        cands_before = res_before["predictions"][0]["candidates"]
        cands_after = res_after["predictions"][0]["candidates"]

        for b, a in zip(cands_before, cands_after):
            self.assertEqual(b["token_id"], a["token_id"])
            self.assertAlmostEqual(b["probability"], a["probability"], places=5)

    def test_swapped_config_checkpoint_rejected(self):
        """Memastikan ketidakcocokan antara config.json dan metadata model.pt ditolak saat pemuatan."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self.model.save_pretrained(tmpdir, filename="model.pt")

            # Ubah config.json secara manual (misal d_model diubah ke 64)
            cfg_path = os.path.join(tmpdir, "config.json")
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg_data = json.load(f)
            cfg_data["d_model"] = 64
            with open(cfg_path, "w", encoding="utf-8") as f:
                json.dump(cfg_data, f)

            with self.assertRaises(ValueError):
                MiniBertForMaskedLM.from_pretrained(tmpdir, filename="model.pt")

    def test_empty_or_corrupt_vocab_hash_rejected(self):
        """Memastikan checkpoint dengan vocab_sha256 kosong atau None ditolak."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self.model.save_pretrained(tmpdir, filename="model.pt")

            # Hapus vocab_sha256 pada checkpoint model.pt
            model_path = os.path.join(tmpdir, "model.pt")
            ckpt = torch.load(model_path, map_location="cpu", weights_only=True)
            ckpt["vocab_sha256"] = ""
            torch.save(ckpt, model_path)

            with self.assertRaises(ValueError):
                MiniBertForMaskedLM.from_pretrained(tmpdir, filename="model.pt")

    def test_swapped_vocab_hash_rejected(self):
        """Memastikan ketidakcocokan hash antara config.json dan model.pt ditolak."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self.model.save_pretrained(tmpdir, filename="model.pt")

            model_path = os.path.join(tmpdir, "model.pt")
            ckpt = torch.load(model_path, map_location="cpu", weights_only=True)
            ckpt["vocab_sha256"] = "11112222333344445555666677778888"
            torch.save(ckpt, model_path)

            with self.assertRaises(ValueError):
                MiniBertForMaskedLM.from_pretrained(tmpdir, filename="model.pt")

    def test_missing_config_rejected(self):
        """Memastikan checkpoint tanpa dictionary config atau bernilai None ditolak."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self.model.save_pretrained(tmpdir, filename="model.pt")

            model_path = os.path.join(tmpdir, "model.pt")
            ckpt = torch.load(model_path, map_location="cpu", weights_only=True)
            del ckpt["config"]
            torch.save(ckpt, model_path)

            with self.assertRaises(ValueError):
                MiniBertForMaskedLM.from_pretrained(tmpdir, filename="model.pt")

    def test_deleted_config_field_rejected(self):
        """Memastikan penghapusan field konfigurasi pada checkpoint ditolak."""
        with tempfile.TemporaryDirectory() as tmpdir:
            self.model.save_pretrained(tmpdir, filename="model.pt")

            model_path = os.path.join(tmpdir, "model.pt")
            ckpt = torch.load(model_path, map_location="cpu", weights_only=True)
            del ckpt["config"]["d_model"]
            torch.save(ckpt, model_path)

            with self.assertRaises(ValueError):
                MiniBertForMaskedLM.from_pretrained(tmpdir, filename="model.pt")

    def test_checkpoint_status_trained_and_unknown(self):
        """Memastikan status trained dan unknown diteruskan secara akurat ke hasil inferensi."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # 1. Simpan dengan status trained
            self.model.save_pretrained(tmpdir, filename="model.pt", checkpoint_status="trained")
            loaded_trained = MiniBertForMaskedLM.from_pretrained(tmpdir, filename="model.pt")
            self.assertEqual(loaded_trained.checkpoint_status, "trained")

            res_trained = predict_mask(
                text="Uji status [MASK] pelatihan.",
                checkpoint_dir=tmpdir,
                tokenizer_dir=self.tokenizer_dir,
                top_k=2,
            )
            self.assertEqual(res_trained["checkpoint_status"], "trained")
            self.assertIn("trained", res_trained["status_message"])

            # 2. Modifikasi agar status hilang (menghasilkan unknown)
            model_path = os.path.join(tmpdir, "model.pt")
            ckpt = torch.load(model_path, map_location="cpu", weights_only=True)
            del ckpt["checkpoint_status"]
            torch.save(ckpt, model_path)

            loaded_unknown = MiniBertForMaskedLM.from_pretrained(tmpdir, filename="model.pt")
            self.assertEqual(loaded_unknown.checkpoint_status, "unknown")

            res_unknown = predict_mask(
                text="Uji status [MASK] pelatihan.",
                checkpoint_dir=tmpdir,
                tokenizer_dir=self.tokenizer_dir,
                top_k=2,
            )
            self.assertEqual(res_unknown["checkpoint_status"], "unknown")
            self.assertIn("unknown", res_unknown["status_message"])


if __name__ == "__main__":
    unittest.main()
