"""
Unit test komprehensif untuk memverifikasi PyTorch PrechunkedMLMDataset, MLMDataCollator,
DataLoader, dan integrasi loss pipeline (Bagian G).

Mencakup seluruh 10 butir pengujian Bagian G:
1. Bentuk dan dtype batch: input_ids, attention_mask, labels torch.long [B, 64].
2. Labels hanya pada token layak dan sesuai token asli.
3. Semua contoh memiliki target minimal satu.
4. Padding dan token khusus (0..4) tidak menjadi target atau pengganti acak.
5. Masking tidak memodifikasi dataset sumber.
6. Train dapat berubah antarepoch dan dapat direproduksi jika seed sama.
7. Evaluasi tetap (deterministik) meski urutan/batch size berubah.
8. Rasio 80/10/10 diperiksa pada sampel besar dengan toleransi statistik.
9. Kasus seluruh isi [UNK] ditangani dan dikeluarkan dari dataset siap MLM.
10. Smoke test loss menggunakan logits dummy dan ignore_index=-100 menghasilkan loss finite.
"""

import os
import sys
import unittest
import torch
import torch.nn as nn

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.data.dataset import (
    PrechunkedMLMDataset,
    MLMDataCollator,
    get_mlm_dataloader,
    NUM_SPECIAL_TOKENS,
    MASK_TOKEN_ID,
    PAD_TOKEN_ID,
)


class TestDatasetAndCollator(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.data_dir = "data/processed/pilot"
        cls.val_file = os.path.join(cls.data_dir, "val_chunks.jsonl")
        cls.test_file = os.path.join(cls.data_dir, "test_chunks.jsonl")
        cls.dataset_val = PrechunkedMLMDataset(cls.val_file, vocab_size=8000, max_length=64)

    def test_01_batch_shapes_and_dtypes(self):
        """Verifikasi bentuk tensor [B, 64] dan dtype torch.long pada batch."""
        collator = MLMDataCollator(vocab_size=8000, mode="train", train_seed=42)
        batch_items = [self.dataset_val[i] for i in range(8)]
        batch = collator(batch_items)

        self.assertIn("input_ids", batch)
        self.assertIn("attention_mask", batch)
        self.assertIn("labels", batch)

        self.assertEqual(batch["input_ids"].shape, (8, 64))
        self.assertEqual(batch["attention_mask"].shape, (8, 64))
        self.assertEqual(batch["labels"].shape, (8, 64))

        self.assertEqual(batch["input_ids"].dtype, torch.long)
        self.assertEqual(batch["attention_mask"].dtype, torch.long)
        self.assertEqual(batch["labels"].dtype, torch.long)

    def test_02_labels_integrity_and_original_matching(self):
        """Verifikasi bahwa labels hanya berada pada token layak dan sesuai token asli."""
        collator = MLMDataCollator(vocab_size=8000, mode="train", train_seed=123)
        raw_items = [self.dataset_val[i] for i in range(16)]
        batch = collator(raw_items)

        for b_idx, raw in enumerate(raw_items):
            orig_ids = raw["input_ids"]
            for pos in range(64):
                lbl = batch["labels"][b_idx, pos].item()
                if lbl != -100:
                    # Posisi target harus sesuai dengan token asli
                    self.assertEqual(lbl, orig_ids[pos])
                    # Token asli harus merupakan kandidat reguler (ID >= 5)
                    self.assertGreaterEqual(lbl, NUM_SPECIAL_TOKENS)

    def test_03_all_examples_have_at_least_one_target(self):
        """Verifikasi bahwa semua contoh dalam batch memiliki minimal satu token target."""
        collator = MLMDataCollator(vocab_size=8000, mode="train", mlm_probability=0.15)
        raw_items = [self.dataset_val[i] for i in range(32)]
        batch = collator(raw_items)

        for b_idx in range(32):
            sample_labels = batch["labels"][b_idx]
            targets_count = (sample_labels != -100).sum().item()
            self.assertGreaterEqual(
                targets_count, 1,
                f"Contoh index {b_idx} tidak memiliki token target masking!"
            )

    def test_04_special_tokens_and_padding_never_targeted_or_randomly_injected(self):
        """Verifikasi bahwa token khusus (0..4) dan padding tidak pernah menjadi target atau pengganti acak."""
        collator = MLMDataCollator(vocab_size=8000, mode="train", train_seed=777)
        raw_items = [self.dataset_val[i] for i in range(50)]
        batch = collator(raw_items)

        for b_idx, raw in enumerate(raw_items):
            orig_ids = raw["input_ids"]
            for pos in range(64):
                orig_tid = orig_ids[pos]
                lbl = batch["labels"][b_idx, pos].item()
                inp_tid = batch["input_ids"][b_idx, pos].item()

                if orig_tid < NUM_SPECIAL_TOKENS:
                    # Token khusus / padding / UNK tidak boleh menjadi target
                    self.assertEqual(
                        lbl, -100,
                        f"Token khusus ID {orig_tid} di pos {pos} dijadikan target label!"
                    )
                    # Token khusus / padding / UNK tidak boleh termutasi
                    self.assertEqual(inp_tid, orig_tid)

                # Jika token diganti acak (bukan [MASK] dan bukan -100), ID pengganti harus >= 5
                if lbl != -100 and inp_tid != MASK_TOKEN_ID:
                    self.assertGreaterEqual(
                        inp_tid, NUM_SPECIAL_TOKENS,
                        f"Pengganti acak {inp_tid} merupakan token khusus!"
                    )

    def test_05_immutability_of_source_dataset(self):
        """Verifikasi bahwa pemanggilan collator berkali-kali tidak memodifikasi dataset sumber."""
        collator = MLMDataCollator(vocab_size=8000, mode="train")
        sample_before = list(self.dataset_val.samples[0]["input_ids"])

        # Panggil collator 5 kali
        for _ in range(5):
            batch_item = [self.dataset_val[0]]
            _ = collator(batch_item)

        sample_after = list(self.dataset_val.samples[0]["input_ids"])
        self.assertEqual(sample_before, sample_after)

    def test_06_train_reproducibility_and_variation_across_epochs(self):
        """Verifikasi bahwa train masking dapat berubah antarepoch dan identik jika seed sama."""
        collator1 = MLMDataCollator(vocab_size=8000, mode="train", train_seed=42)
        collator2 = MLMDataCollator(vocab_size=8000, mode="train", train_seed=42)
        collator3 = MLMDataCollator(vocab_size=8000, mode="train", train_seed=999)

        batch_items = [self.dataset_val[i] for i in range(10)]

        out1 = collator1(batch_items)
        out2 = collator2(batch_items)
        out3 = collator3(batch_items)

        # Seed sama harus menghasilkan input_ids dan labels yang identik
        self.assertTrue(torch.equal(out1["input_ids"], out2["input_ids"]))
        self.assertTrue(torch.equal(out1["labels"], out2["labels"]))

        # Seed berbeda harus menghasilkan masking yang berbeda
        self.assertFalse(torch.equal(out1["input_ids"], out3["input_ids"]))

    def test_07_eval_determinism_across_batch_sizes_and_orders(self):
        """Verifikasi bahwa masking mode evaluasi 100% deterministik terlepas dari batch size atau urutan."""
        collator_eval = MLMDataCollator(vocab_size=8000, mode="eval", eval_seed=42)

        items_forward = [self.dataset_val[i] for i in range(5)]
        items_reversed = list(reversed(items_forward))

        # Batch ukuran 5 forward
        batch_fwd = collator_eval(items_forward)

        # Batch ukuran 5 reversed
        batch_rev = collator_eval(items_reversed)

        # Batch individual (ukuran 1)
        batches_single = [collator_eval([item]) for item in items_forward]

        # Periksa bahwa item 0 di batch_fwd persis sama dengan item 4 di batch_rev dan batches_single[0]
        for i in range(5):
            # Cek dengan batch individual
            self.assertTrue(
                torch.equal(batch_fwd["input_ids"][i], batches_single[i]["input_ids"][0])
            )
            self.assertTrue(
                torch.equal(batch_fwd["labels"][i], batches_single[i]["labels"][0])
            )

            # Cek dengan batch reversed
            rev_idx = 4 - i
            self.assertTrue(
                torch.equal(batch_fwd["input_ids"][i], batch_rev["input_ids"][rev_idx])
            )
            self.assertTrue(
                torch.equal(batch_fwd["labels"][i], batch_rev["labels"][rev_idx])
            )

    def test_08_mlm_ratio_distribution_on_large_sample(self):
        """Verifikasi aturan distribusi masking 80/10/10 pada sampel besar dengan toleransi statistik."""
        collator = MLMDataCollator(vocab_size=8000, mode="train", train_seed=2026)
        large_batch_items = [self.dataset_val[i] for i in range(min(300, len(self.dataset_val)))]
        batch = collator(large_batch_items)

        labels = batch["labels"]
        input_ids = batch["input_ids"]

        mask_count = 0
        random_count = 0
        same_count = 0
        total_targets = 0

        for b_idx in range(len(large_batch_items)):
            orig_ids = large_batch_items[b_idx]["input_ids"]
            for pos in range(64):
                lbl = labels[b_idx, pos].item()
                if lbl != -100:
                    total_targets += 1
                    inp_tid = input_ids[b_idx, pos].item()
                    orig_tid = orig_ids[pos]

                    if inp_tid == MASK_TOKEN_ID:
                        mask_count += 1
                    elif inp_tid == orig_tid:
                        same_count += 1
                    else:
                        random_count += 1

        self.assertGreater(total_targets, 1000)

        mask_pct = (mask_count / total_targets) * 100.0
        random_pct = (random_count / total_targets) * 100.0
        same_pct = (same_count / total_targets) * 100.0

        # Toleransi statistik wajar (80% ± 4%, 10% ± 3%)
        self.assertAlmostEqual(mask_pct, 80.0, delta=4.0)
        self.assertAlmostEqual(random_pct, 10.0, delta=3.0)
        self.assertAlmostEqual(same_pct, 10.0, delta=3.0)

    def test_09_zero_candidate_chunk_properly_filtered(self):
        """Verifikasi penanganan chunk tanpa kandidat target (seluruh isi [UNK]) pada test split."""
        dataset_test = PrechunkedMLMDataset(self.test_file, filter_zero_candidates=True)

        # Chunk doc_id 3792 chunk_index 3 harus dikeluarkan
        self.assertEqual(len(dataset_test.excluded_chunks), 1)
        exc = dataset_test.excluded_chunks[0]
        self.assertEqual(str(exc["doc_id"]), "3792")
        self.assertEqual(exc["chunk_index"], 3)

        # Dataset test siap MLM harus berkurang tepat 1 (3.427 - 1 = 3.426)
        self.assertEqual(len(dataset_test), 3426)

    def test_10_smoke_test_loss_with_dummy_logits(self):
        """
        Smoke test perhitungan loss PyTorch dengan CrossEntropyLoss(ignore_index=-100).
        Menjamin tensor labels dari collator kompatibel dengan head MLM PyTorch.
        (Catatan: ini verifikasi kontrak pipeline, bukan training model).
        """
        batch_size = 4
        seq_len = 64
        vocab_size = 8000

        collator = MLMDataCollator(vocab_size=vocab_size, mode="train", train_seed=42)
        batch = collator([self.dataset_val[i] for i in range(batch_size)])

        # Buat logits tiruan berbobot float32 acak: [B, seq_len, vocab_size]
        dummy_logits = torch.randn(batch_size, seq_len, vocab_size, dtype=torch.float32)

        loss_fn = nn.CrossEntropyLoss(ignore_index=-100)

        # Hitung loss
        loss = loss_fn(
            dummy_logits.view(-1, vocab_size),
            batch["labels"].view(-1)
        )

        self.assertTrue(torch.isfinite(loss).item())
        self.assertGreater(loss.item(), 0.0)

    def test_11_collator_parameter_validation_and_dataloader_vocab_size(self):
        """Verifikasi validasi ketat mode, mlm_probability, vocab_size, token ID, dan helper DataLoader."""
        # 1. Validasi mode hanya menerima 'train' atau 'eval'
        with self.assertRaises(ValueError) as ctx:
            MLMDataCollator(mode="inferensi")
        self.assertIn("train", str(ctx.exception).lower())

        # 2. Validasi mlm_probability berada pada (0, 1]
        with self.assertRaises(ValueError):
            MLMDataCollator(mlm_probability=0.0)
        with self.assertRaises(ValueError):
            MLMDataCollator(mlm_probability=-0.1)
        with self.assertRaises(ValueError):
            MLMDataCollator(mlm_probability=1.5)

        # Valid boundary mlm_probability=1.0
        coll_full = MLMDataCollator(mlm_probability=1.0)
        self.assertEqual(coll_full.mlm_probability, 1.0)

        # 3. Validasi vocab_size > 5
        with self.assertRaises(ValueError):
            MLMDataCollator(vocab_size=3)
        with self.assertRaises(ValueError):
            MLMDataCollator(vocab_size="8000")  # type: ignore

        # 4. Validasi konsistensi token ID khusus
        with self.assertRaises(ValueError):
            MLMDataCollator(mask_token_id=99)
        with self.assertRaises(ValueError):
            MLMDataCollator(pad_token_id=99)

        # 5. Helper DataLoader menggunakan vocab_size aktual dari Dataset jika collator=None
        custom_dataset = PrechunkedMLMDataset(self.val_file, vocab_size=8000)
        custom_dataset.vocab_size = 7500  # simulasi custom vocab size
        loader = get_mlm_dataloader(custom_dataset, batch_size=4, collator=None)
        self.assertEqual(loader.collate_fn.vocab_size, 7500)


if __name__ == "__main__":
    unittest.main()
