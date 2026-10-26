"""
Rangkaian pengujian unit untuk model Mini-BERT Bahasa Indonesia utuh (MiniBertForMaskedLM):
1. Kesesuaian bentuk logits pada input kecil dan batch nyata dari DataLoader.
2. Perhitungan CrossEntropyLoss finite dengan ignore_index=-100.
3. Propagasi gradien backward finite pada seluruh parameter yang relevan.
4. Identitas memori weight tying sebelum dan sesudah save-load.
5. Verifikasi penghitungan parameter unik (tanpa menghitung bobot bersama dua kali).
6. Konsistensi keluaran mode eval (output deterministik).
7. Penolakan hash vocabulary tokenizer yang tidak cocok saat pemuatan.
8. Isolasi padding pada model utuh (perubahan token padding tidak memengaruhi token valid).
9. Sifat atensi dua arah pada model utuh (token kanan memengaruhi representasi token kiri).
10. Integrasi batch DataLoader nyata dari split Train.
"""

import json
import os
import tempfile
import unittest

import torch
import torch.nn as nn

from src.data.dataset import PrechunkedMLMDataset, MLMDataCollator, get_mlm_dataloader
from src.data.tokenizer import WordLevelTokenizer
from src.models.bert import MiniBertForMaskedLM
from src.models.config import MiniBertConfig


class TestMiniBertForMaskedLM(unittest.TestCase):
    """Pengujian integrasi dan arsitektur model MiniBertForMaskedLM."""

    def setUp(self):
        self.config = MiniBertConfig(
            vocab_size=8000,
            pad_token_id=0,
            d_model=128,
            num_layers=2,
            num_heads=4,
            d_ff=512,
            max_position_embeddings=64,
            dropout=0.1,
            attention_dropout=0.1,
            vocab_sha256="d2be29d07e76fe0cd15c3fe1b765325a5397a5e5fe30b2c6a5a019c976c552f2",
        )
        self.model = MiniBertForMaskedLM(self.config)

    def test_unique_parameter_count(self):
        """
        Memastikan jumlah parameter unik dihitung tepat tanpa menduplikasi weight tying.
        Penghitungan analitis:
        - Word embeddings: 8000 * 128 = 1.024.000
        - Positional embeddings: 64 * 128 = 8.192
        - Embedding LayerNorm: 2 * 128 = 256
        - 2 Blok Encoder: 2 * (16.512 * 4 + 256 + 66.048 + 65.664 + 256) = 396.032
        - MLM Head Dense: 128 * 128 + 128 = 16.512
        - MLM Head LayerNorm: 256
        - MLM Decoder: Bobot diikat (0 unik baru) + Bias decoder (8.000) = 8.000
        Total unik: 1.453.248 parameter.
        """
        total_unique = self.model.num_parameters()
        self.assertEqual(total_unique, 1453760)

    def test_weight_tying_identity(self):
        """Memastikan matriks bobot decoder dan word embeddings merujuk ke objek memori yang persis sama."""
        self.assertIs(
            self.model.cls.decoder.weight,
            self.model.embeddings.word_embeddings.weight,
        )

        # Memastikan pembaruan bobot pada satu sisi langsung tecermin di sisi lain
        with torch.no_grad():
            self.model.embeddings.word_embeddings.weight[10, 0] = 7.77
            self.assertAlmostEqual(self.model.cls.decoder.weight[10, 0].item(), 7.77, places=5)

    def test_forward_logits_shape(self):
        """Memastikan logits berukuran [B, L, vocab_size] pada input buatan."""
        input_ids = torch.randint(0, 8000, (2, 16), dtype=torch.long)
        attention_mask = torch.ones(2, 16, dtype=torch.long)

        logits = self.model(input_ids=input_ids, attention_mask=attention_mask)
        self.assertEqual(logits.shape, (2, 16, 8000))
        self.assertTrue(torch.isfinite(logits).all())

    def test_loss_and_backward_pass(self):
        """Memastikan perhitungan CrossEntropyLoss dan backward menghasilkan gradien finite."""
        self.model.train()
        input_ids = torch.randint(0, 8000, (2, 8), dtype=torch.long)
        attention_mask = torch.ones(2, 8, dtype=torch.long)

        # Label dengan target pada sebagian posisi dan -100 pada posisi lain
        labels = torch.full((2, 8), -100, dtype=torch.long)
        labels[0, 2] = 120
        labels[1, 5] = 450

        logits = self.model(input_ids=input_ids, attention_mask=attention_mask)

        loss_fn = nn.CrossEntropyLoss(ignore_index=-100)
        loss = loss_fn(logits.view(-1, 8000), labels.view(-1))

        self.assertTrue(torch.isfinite(loss))
        loss.backward()

        # Pastikan gradien pada embedding dan encoder finite
        self.assertIsNotNone(self.model.embeddings.word_embeddings.weight.grad)
        self.assertTrue(torch.isfinite(self.model.embeddings.word_embeddings.weight.grad).all())

    def test_save_and_load_pretrained(self):
        """Memastikan save/load mempertahankan bobot, evaluasi deterministik, dan weight tying."""
        self.model.eval()
        input_ids = torch.randint(0, 8000, (1, 10), dtype=torch.long)
        attention_mask = torch.ones(1, 10, dtype=torch.long)

        with torch.no_grad():
            original_logits = self.model(input_ids, attention_mask=attention_mask)

        with tempfile.TemporaryDirectory() as tmpdir:
            self.model.save_pretrained(tmpdir, filename="model.pt")

            # Muat kembali
            loaded_model = MiniBertForMaskedLM.from_pretrained(tmpdir, filename="model.pt")
            loaded_model.eval()

            # Pastikan weight tying tetap berlaku utuh
            self.assertIs(
                loaded_model.cls.decoder.weight,
                loaded_model.embeddings.word_embeddings.weight,
            )

            with torch.no_grad():
                loaded_logits = loaded_model(input_ids, attention_mask=attention_mask)

            # Keluaran logits harus identik secara eksak
            diff = (original_logits - loaded_logits).abs().max().item()
            self.assertEqual(diff, 0.0)

    def test_tokenizer_hash_verification_on_load(self):
        """Memastikan pemuatan menolak direktori tokenizer dengan hash yang tidak sesuai."""
        with tempfile.TemporaryDirectory() as model_dir, tempfile.TemporaryDirectory() as tok_dir:
            self.model.save_pretrained(model_dir)

            # Buat vocabulary palsu di tok_dir
            fake_vocab = {"[PAD]": 0, "[UNK]": 1, "[CLS]": 2, "[SEP]": 3, "[MASK]": 4, "berbeda": 5}
            with open(os.path.join(tok_dir, "vocab.json"), "w", encoding="utf-8") as f:
                json.dump(fake_vocab, f)

            with self.assertRaises(ValueError):
                MiniBertForMaskedLM.from_pretrained(
                    model_dir,
                    filename="model.pt",
                    tokenizer_dir=tok_dir,
                )

    def test_padding_isolation_on_full_model(self):
        """
        Memastikan bahwa pada model utuh (mode eval), pengubahan nilai token padding
        TIDAK mengubah representasi logits pada token valid.
        """
        self.model.eval()
        batch_size = 2
        seq_len = 8

        # 5 token valid, 3 token padding
        mask = torch.tensor([[1, 1, 1, 1, 1, 0, 0, 0], [1, 1, 1, 1, 0, 0, 0, 0]], dtype=torch.long)

        input_ids_1 = torch.tensor([
            [2, 100, 200, 300, 3, 0, 0, 0],
            [2, 50, 60, 3, 0, 0, 0, 0],
        ], dtype=torch.long)

        # Ubah isi token padding ke ID kata lain (misal ID 555)
        input_ids_2 = torch.tensor([
            [2, 100, 200, 300, 3, 555, 666, 777],
            [2, 50, 60, 3, 888, 999, 111, 222],
        ], dtype=torch.long)

        with torch.no_grad():
            logits_1 = self.model(input_ids_1, attention_mask=mask)
            logits_2 = self.model(input_ids_2, attention_mask=mask)

        # Logits pada posisi valid 0..4 (contoh 0) harus identik
        diff_0 = (logits_1[0, :5, :] - logits_2[0, :5, :]).abs().max().item()
        self.assertAlmostEqual(diff_0, 0.0, places=4)

        # Logits pada posisi valid 0..3 (contoh 1) harus identik
        diff_1 = (logits_1[1, :4, :] - logits_2[1, :4, :]).abs().max().item()
        self.assertAlmostEqual(diff_1, 0.0, places=4)

    def test_bidirectional_attention_on_full_model(self):
        """
        Memastikan sifat atensi dua arah bekerja pada model utuh:
        Perubahan kata di sisi kanan memengaruhi keluaran logits kata di sisi kiri.
        """
        self.model.eval()
        mask = torch.ones(1, 6, dtype=torch.long)

        input_ids_1 = torch.tensor([[2, 15, 20, 25, 30, 3]], dtype=torch.long)
        input_ids_2 = torch.tensor([[2, 15, 20, 25, 999, 3]], dtype=torch.long)  # ubah indeks 4

        with torch.no_grad():
            logits_1 = self.model(input_ids_1, attention_mask=mask)
            logits_2 = self.model(input_ids_2, attention_mask=mask)

        # Logits pada posisi kata kiri (indeks 1) harus terpengaruh
        diff_left = (logits_1[0, 1, :] - logits_2[0, 1, :]).abs().max().item()
        self.assertGreater(diff_left, 1e-4)

    def test_real_dataloader_batch_integration(self):
        """
        Uji integrasi pada satu batch nyata dari pipeline data Train milik Anggota 1.
        Memverifikasi pemisahan metadata batch, komputasi forward, loss CrossEntropy, dan backward.
        """
        train_chunk_file = "data/processed/pilot/train_chunks.jsonl"
        if not os.path.exists(train_chunk_file):
            self.skipTest("Berkas train_chunks.jsonl tidak ditemukan.")

        dataset = PrechunkedMLMDataset(train_chunk_file, vocab_size=8000, max_length=64)
        collator = MLMDataCollator(vocab_size=8000, mode="train", train_seed=42)
        dataloader = get_mlm_dataloader(dataset, batch_size=4, shuffle=False, collator=collator)

        batch = next(iter(dataloader))

        # Verifikasi pemisahan: Metadata tidak boleh dikirimkan ke model
        self.assertIn("doc_ids", batch)
        self.assertIn("chunk_indices", batch)

        input_ids = batch["input_ids"]           # [4, 64]
        attention_mask = batch["attention_mask"] # [4, 64]
        labels = batch["labels"]                 # [4, 64]

        self.assertEqual(input_ids.shape, (4, 64))
        self.assertEqual(attention_mask.shape, (4, 64))
        self.assertEqual(labels.shape, (4, 64))

        # Forward pass murni dengan input_ids dan attention_mask
        self.model.train()
        logits = self.model(input_ids=input_ids, attention_mask=attention_mask)

        self.assertEqual(logits.shape, (4, 64, 8000))
        self.assertTrue(torch.isfinite(logits).all())

        # Perhitungan loss CrossEntropy pada posisi target MLM
        loss_fn = nn.CrossEntropyLoss(ignore_index=-100)
        loss = loss_fn(logits.view(-1, 8000), labels.view(-1))

        self.assertTrue(torch.isfinite(loss))
        self.assertGreater(loss.item(), 0.0)

        # Backward pass
        loss.backward()
        for p in self.model.parameters():
            if p.grad is not None:
                self.assertTrue(torch.isfinite(p.grad).all())


if __name__ == "__main__":
    unittest.main()
