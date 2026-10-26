"""
Rangkaian pengujian unit untuk primitif model Mini-BERT Bahasa Indonesia:
1. Validasi MiniBertConfig (argumen valid, tidak valid, NaN/Inf, serialisasi JSON, deteksi hash vocabulary, penolakan override bertentangan).
2. Perilaku BertEmbeddings (bentuk tensor, learned positions, penolakan input tidak valid/panjang berlebih, validasi dtype dan device position_ids).
3. Perilaku MultiHeadSelfAttention:
   - Kesesuaian bentuk tensor keluaran.
   - Verifikasi komputasi matematis terhadap implementasi referensi independen.
   - Isolasi padding mask dengan masked_fill dan magnitudo tinggi (perubahan token yang dimasking tidak mengubah token valid).
   - Sifat atensi dua arah (perubahan token kanan memengaruhi token kiri).
   - Penolakan attention_mask seluruhnya nol atau tidak biner.
   - Keutuhan gradien (gradien dan keluaran finite).
   - Smoke test eksekusi CPU dan GPU.
"""

import json
import math
import os
import tempfile
import unittest

import torch

from src.models.attention import MultiHeadSelfAttention
from src.models.config import MiniBertConfig
from src.models.embeddings import BertEmbeddings


class TestMiniBertConfig(unittest.TestCase):
    """Pengujian untuk kelas konfigurasi MiniBertConfig."""

    def test_default_config_valid(self):
        """Memastikan konfigurasi bawaan valid dan parameter sesuai rancangan."""
        cfg = MiniBertConfig()
        self.assertEqual(cfg.vocab_size, 8000)
        self.assertEqual(cfg.pad_token_id, 0)
        self.assertEqual(cfg.d_model, 128)
        self.assertEqual(cfg.num_layers, 2)
        self.assertEqual(cfg.num_heads, 4)
        self.assertEqual(cfg.d_ff, 512)
        self.assertEqual(cfg.max_position_embeddings, 64)
        self.assertEqual(cfg.dropout, 0.1)
        self.assertEqual(cfg.attention_dropout, 0.1)
        self.assertEqual(cfg.layer_norm_eps, 1e-12)
        self.assertEqual(cfg.initializer_range, 0.02)

    def test_invalid_dimension_types_and_values(self):
        """Memastikan parameter dimensi non-positif atau salah tipe ditolak."""
        with self.assertRaises(ValueError):
            MiniBertConfig(vocab_size=0)
        with self.assertRaises(ValueError):
            MiniBertConfig(vocab_size=-10)
        with self.assertRaises(ValueError):
            MiniBertConfig(vocab_size=True)
        with self.assertRaises(ValueError):
            MiniBertConfig(d_model=0)
        with self.assertRaises(ValueError):
            MiniBertConfig(num_layers=0)
        with self.assertRaises(ValueError):
            MiniBertConfig(num_heads=0)
        with self.assertRaises(ValueError):
            MiniBertConfig(max_position_embeddings=0)

    def test_head_divisibility_validation(self):
        """Memastikan d_model yang tidak habis dibagi num_heads ditolak."""
        with self.assertRaises(ValueError):
            MiniBertConfig(d_model=130, num_heads=4)

    def test_pad_token_id_range_validation(self):
        """Memastikan pad_token_id di luar rentang vocabulary ditolak."""
        with self.assertRaises(ValueError):
            MiniBertConfig(vocab_size=100, pad_token_id=100)
        with self.assertRaises(ValueError):
            MiniBertConfig(vocab_size=100, pad_token_id=-1)

    def test_dropout_range_validation(self):
        """Memastikan nilai dropout di luar rentang [0.0, 1.0) ditolak."""
        with self.assertRaises(ValueError):
            MiniBertConfig(dropout=1.0)
        with self.assertRaises(ValueError):
            MiniBertConfig(dropout=-0.1)
        with self.assertRaises(ValueError):
            MiniBertConfig(attention_dropout=1.5)

    def test_nan_inf_numeric_rejected(self):
        """Memastikan nilai numerik NaN atau Inf ditolak."""
        with self.assertRaises(ValueError):
            MiniBertConfig(dropout=float("nan"))
        with self.assertRaises(ValueError):
            MiniBertConfig(dropout=float("inf"))
        with self.assertRaises(ValueError):
            MiniBertConfig(attention_dropout=float("nan"))
        with self.assertRaises(ValueError):
            MiniBertConfig(layer_norm_eps=float("nan"))
        with self.assertRaises(ValueError):
            MiniBertConfig(layer_norm_eps=float("inf"))
        with self.assertRaises(ValueError):
            MiniBertConfig(initializer_range=float("nan"))

    def test_json_save_and_load(self):
        """Memastikan konfigurasi dapat disimpan dan dimuat kembali via JSON secara identik."""
        cfg = MiniBertConfig(d_model=64, num_heads=2, d_ff=256, vocab_sha256="abcd1234")
        with tempfile.TemporaryDirectory() as tmpdir:
            file_path = os.path.join(tmpdir, "config.json")
            cfg.to_json_file(file_path)
            loaded_cfg = MiniBertConfig.from_json_file(file_path)
            self.assertEqual(cfg.to_dict(), loaded_cfg.to_dict())

    def test_from_tokenizer_directory(self):
        """Memastikan konfigurasi dapat membaca langsung artefak tokenizer di data/processed/pilot."""
        tok_dir = "data/processed/pilot"
        if os.path.exists(os.path.join(tok_dir, "vocab.json")):
            cfg = MiniBertConfig.from_tokenizer_directory(tok_dir)
            self.assertEqual(cfg.vocab_size, 8000)
            self.assertEqual(cfg.pad_token_id, 0)
            self.assertEqual(cfg.max_position_embeddings, 64)
            self.assertEqual(
                cfg.vocab_sha256,
                "d2be29d07e76fe0cd15c3fe1b765325a5397a5e5fe30b2c6a5a019c976c552f2",
            )

    def test_from_tokenizer_directory_conflicting_override_rejected(self):
        """Memastikan override yang bertentangan dengan artefak fisik ditolak."""
        tok_dir = "data/processed/pilot"
        if os.path.exists(os.path.join(tok_dir, "vocab.json")):
            with self.assertRaises(ValueError):
                MiniBertConfig.from_tokenizer_directory(tok_dir, vocab_size=5000)
            with self.assertRaises(ValueError):
                MiniBertConfig.from_tokenizer_directory(tok_dir, pad_token_id=9)
            with self.assertRaises(ValueError):
                MiniBertConfig.from_tokenizer_directory(tok_dir, vocab_sha256="salah_hash")

    def test_from_tokenizer_directory_corrupt_config_rejected(self):
        """Memastikan berkas tokenizer_config.json yang rusak tidak diabaikan diam-diam."""
        with tempfile.TemporaryDirectory() as tmpdir:
            vocab = {"[PAD]": 0, "[UNK]": 1, "[CLS]": 2, "[SEP]": 3, "[MASK]": 4, "kata": 5}
            with open(os.path.join(tmpdir, "vocab.json"), "w", encoding="utf-8") as f:
                json.dump(vocab, f)
            # Tulis berkas konfigurasi yang rusak (bukan JSON valid)
            with open(os.path.join(tmpdir, "tokenizer_config.json"), "w", encoding="utf-8") as f:
                f.write("{corrupt json...")
            with self.assertRaises(json.JSONDecodeError):
                MiniBertConfig.from_tokenizer_directory(tmpdir)


class TestBertEmbeddings(unittest.TestCase):
    """Pengujian untuk modul BertEmbeddings."""

    def setUp(self):
        self.config = MiniBertConfig(
            vocab_size=100,
            pad_token_id=0,
            d_model=32,
            max_position_embeddings=16,
            dropout=0.0,
        )
        self.embeddings = BertEmbeddings(self.config)
        self.embeddings.eval()

    def test_embeddings_shape(self):
        """Memastikan bentuk output embedding tepat [B, L, d_model]."""
        input_ids = torch.randint(0, 100, (2, 8), dtype=torch.long)
        out = self.embeddings(input_ids)
        self.assertEqual(out.shape, (2, 8, 32))

    def test_max_position_and_overflow(self):
        """Memastikan panjang urutan sama dengan batas diterima dan panjang berlebih ditolak."""
        # Tepat kapasitas batas (16)
        valid_ids = torch.randint(0, 100, (1, 16), dtype=torch.long)
        out = self.embeddings(valid_ids)
        self.assertEqual(out.shape, (1, 16, 32))

        # Melebihi kapasitas batas (17)
        overflow_ids = torch.randint(0, 100, (1, 17), dtype=torch.long)
        with self.assertRaises(ValueError):
            self.embeddings(overflow_ids)

    def test_invalid_input_types_and_dimensions(self):
        """Memastikan input kosong, salah dimensi, atau salah tipe data ditolak."""
        with self.assertRaises(TypeError):
            self.embeddings([1, 2, 3])
        with self.assertRaises(ValueError):
            self.embeddings(torch.tensor([1, 2, 3], dtype=torch.long))  # 1D
        with self.assertRaises(TypeError):
            self.embeddings(torch.ones((2, 4), dtype=torch.float32))    # Float dtype
        with self.assertRaises(ValueError):
            self.embeddings(torch.zeros((0, 4), dtype=torch.long))      # Batch size 0
        with self.assertRaises(ValueError):
            self.embeddings(torch.zeros((2, 0), dtype=torch.long))      # Seq len 0
        with self.assertRaises(ValueError):
            self.embeddings(torch.tensor([[100, 2]], dtype=torch.long)) # ID di luar rentang

    def test_custom_position_ids(self):
        """Memastikan custom position_ids bekerja dan memvalidasi batas nilai."""
        input_ids = torch.tensor([[5, 10]], dtype=torch.long)
        pos_ids = torch.tensor([[0, 1]], dtype=torch.long)
        out = self.embeddings(input_ids, position_ids=pos_ids)
        self.assertEqual(out.shape, (1, 2, 32))

        # Posisi di luar kapasitas
        pos_overflow = torch.tensor([[0, 20]], dtype=torch.long)
        with self.assertRaises(ValueError):
            self.embeddings(input_ids, position_ids=pos_overflow)

    def test_position_ids_device_and_dtype_validation(self):
        """Memastikan tipe data dan device position_ids divalidasi ketat."""
        input_ids = torch.tensor([[5, 10]], dtype=torch.long)
        # Tipe float ditolak
        pos_float = torch.tensor([[0.0, 1.0]])
        with self.assertRaises(TypeError):
            self.embeddings(input_ids, position_ids=pos_float)


class TestMultiHeadSelfAttention(unittest.TestCase):
    """Pengujian untuk modul MultiHeadSelfAttention."""

    def setUp(self):
        self.config = MiniBertConfig(
            d_model=32,
            num_heads=4,
            attention_dropout=0.0,
        )
        self.attention = MultiHeadSelfAttention(self.config)
        self.attention.eval()

    def test_output_shape(self):
        """Memastikan bentuk keluaran atensi tepat [B, L, d_model]."""
        x = torch.randn(2, 6, 32)
        mask = torch.ones(2, 6, dtype=torch.long)
        out = self.attention(x, attention_mask=mask)
        self.assertEqual(out.shape, (2, 6, 32))

    def test_against_reference_computation(self):
        """
        Membandingkan hasil atensi dengan komputasi matematika referensi independen
        pada konfigurasi single head yang terkontrol.
        """
        simple_config = MiniBertConfig(d_model=4, num_heads=1, attention_dropout=0.0)
        attn = MultiHeadSelfAttention(simple_config)
        attn.eval()

        with torch.no_grad():
            x = torch.tensor([[[1.0, 0.0, 0.0, 0.0], [0.0, 1.0, 0.0, 0.0]]])  # [1, 2, 4]
            # Set bobot proyeksi sebagai matriks identitas
            attn.query.weight.copy_(torch.eye(4))
            attn.query.bias.zero_()
            attn.key.weight.copy_(torch.eye(4))
            attn.key.bias.zero_()
            attn.value.weight.copy_(torch.eye(4))
            attn.value.bias.zero_()
            attn.out_proj.weight.copy_(torch.eye(4))
            attn.out_proj.bias.zero_()

            out = attn(x)

            scale = 1.0 / math.sqrt(4)
            q_ref = x[0]
            k_ref = x[0]
            v_ref = x[0]
            scores_ref = torch.matmul(q_ref, k_ref.T) * scale
            probs_ref = torch.softmax(scores_ref, dim=-1)
            expected = torch.matmul(probs_ref, v_ref).unsqueeze(0)

            self.assertTrue(torch.allclose(out, expected, atol=1e-5))

    def test_padding_mask_isolation_with_high_magnitude(self):
        """
        Uji kritis isolasi padding mask dengan masked_fill:
        Mengubah nilai hidden_states pada posisi padding dengan magnitudo sangat besar (1e5)
        TIDAK BOLEH mengubah representasi keluaran pada posisi token valid.
        """
        batch_size = 2
        seq_len = 6
        d_model = 32

        # 4 token valid pertama, 2 token terakhir adalah padding
        mask = torch.tensor([[1, 1, 1, 1, 0, 0], [1, 1, 1, 0, 0, 0]], dtype=torch.long)

        x1 = torch.randn(batch_size, seq_len, d_model)
        x2 = x1.clone()

        # Ubah nilai fitur dengan magnitudo sangat besar pada token padding
        x2[0, 4:, :] = 100000.0
        x2[1, 3:, :] = -100000.0

        with torch.no_grad():
            out1 = self.attention(x1, attention_mask=mask)
            out2 = self.attention(x2, attention_mask=mask)

        # Untuk contoh 0, posisi valid 0..3 harus identik
        diff_ex0_valid = (out1[0, :4, :] - out2[0, :4, :]).abs().max().item()
        self.assertAlmostEqual(diff_ex0_valid, 0.0, places=4)

        # Untuk contoh 1, posisi valid 0..2 harus identik
        diff_ex1_valid = (out1[1, :3, :] - out2[1, :3, :]).abs().max().item()
        self.assertAlmostEqual(diff_ex1_valid, 0.0, places=4)

    def test_bidirectional_attention_behavior(self):
        """
        Uji atensi dua arah:
        Memastikan bahwa perubahan token di sisi kanan memengaruhi token di sisi kiri
        (membuktikan tidak adanya causal / autoregressive mask).
        """
        x1 = torch.randn(1, 4, 32)
        x2 = x1.clone()
        # Ubah token di posisi paling kanan (indeks 3)
        x2[0, 3, :] += 5.0

        mask = torch.ones(1, 4, dtype=torch.long)

        with torch.no_grad():
            out1 = self.attention(x1, attention_mask=mask)
            out2 = self.attention(x2, attention_mask=mask)

        # Token pertama di sisi paling kiri (indeks 0) harus berubah nilainya
        diff_left = (out1[0, 0, :] - out2[0, 0, :]).abs().max().item()
        self.assertGreater(diff_left, 1e-4)

    def test_all_zero_mask_rejected(self):
        """Memastikan attention_mask yang seluruhnya nol ditolak."""
        x = torch.randn(1, 4, 32)
        zero_mask = torch.zeros(1, 4, dtype=torch.long)
        with self.assertRaises(ValueError):
            self.attention(x, attention_mask=zero_mask)

    def test_non_binary_mask_rejected(self):
        """Memastikan attention_mask dengan nilai selain 0 atau 1 ditolak."""
        x = torch.randn(1, 4, 32)
        invalid_mask = torch.tensor([[1, 2, 0, 1]], dtype=torch.long)
        with self.assertRaises(ValueError):
            self.attention(x, attention_mask=invalid_mask)

    def test_finite_output_and_gradients(self):
        """Memastikan forward dan backward pass menghasilkan angka finite (tanpa NaN atau Inf)."""
        attn = MultiHeadSelfAttention(self.config)
        attn.train()

        x = torch.randn(2, 5, 32, requires_grad=True)
        mask = torch.tensor([[1, 1, 1, 1, 0], [1, 1, 1, 0, 0]], dtype=torch.long)

        out = attn(x, attention_mask=mask)
        self.assertTrue(torch.isfinite(out).all())

        loss = out.sum()
        loss.backward()

        self.assertTrue(torch.isfinite(x.grad).all())
        for param in attn.parameters():
            if param.grad is not None:
                self.assertTrue(torch.isfinite(param.grad).all())

    def test_cpu_and_gpu_smoke(self):
        """Smoke test eksekusi forward dan backward pada CPU dan GPU (jika CUDA tersedia)."""
        devices = ["cpu"]
        if torch.cuda.is_available():
            devices.append("cuda")

        for dev in devices:
            attn = MultiHeadSelfAttention(self.config).to(dev)
            x = torch.randn(2, 4, 32, device=dev, requires_grad=True)
            mask = torch.ones(2, 4, dtype=torch.long, device=dev)

            out = attn(x, attention_mask=mask)
            self.assertEqual(out.device.type, dev)
            self.assertTrue(torch.isfinite(out).all())

            loss = out.sum()
            loss.backward()
            self.assertTrue(torch.isfinite(x.grad).all())


if __name__ == "__main__":
    unittest.main()
