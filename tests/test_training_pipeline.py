"""
Rangkaian Pengujian Unit Komprehensif untuk Pipeline Pelatihan Mini-BERT Bahasa Indonesia (Tahap 2):

1. test_weighted_metrics_different_targets:
   Verifikasi agregasi berbobot (weighted epoch metrics) pada batch dengan jumlah target berbeda,
   membuktikan hasil tidak bias unweighted batch averaging.
2. test_ignore_index_minus_100:
   Verifikasi bahwa posisi labels == -100 sepenuhnya diabaikan dan perubahan logit pada posisi tersebut
   tidak memengaruhi nilai loss atau akurasi.
3. test_optimizer_parameter_coverage_and_tied_weights:
   Verifikasi bahwa setiap parameter trainable tercakup tepat satu kali di optimizer,
   tied weights (cls.decoder.weight) tidak didaftarkan ganda, serta pemisahan decay/no-decay tepat.
4. test_single_optimizer_step_updates_weights_finite:
   Verifikasi satu optimizer step benar-benar memperbarui bobot model dengan gradien finite.
5. test_scheduler_and_global_step_progression:
   Verifikasi nilai learning rate pada langkah pertama (step 1), akhir warmup, dan akhir run,
   serta penolakan terhadap konfigurasi scheduler yang cacat.
6. test_epoch_boundary_checkpoint_and_resume:
   Membandingkan run CPU 2 epoch tanpa putus dengan run yang disimpan di epoch 1 lalu dilanjutkan (resume)
   untuk epoch 2 dengan konfigurasi sama persis.
7. test_exported_model_compatible_with_inference_loader:
   Verifikasi model hasil ekspor berstatus 'trained' dapat dimuat sempurna oleh MiniBertForMaskedLM.from_pretrained
   dan skrip inferensi predict_mask milik Anggota 2.
8. test_training_and_validation_never_touch_test_split:
   Verifikasi isolasi ketat bahwa dataset dan loader pelatihan tidak pernah membuka split test.
"""

import json
import math
import os
import shutil
import tempfile
import unittest

import torch
import torch.nn as nn
from torch.utils.data import DataLoader, Dataset

from src.data.dataset import PrechunkedMLMDataset, MLMDataCollator
from src.models.bert import MiniBertForMaskedLM
from src.models.config import MiniBertConfig
from src.models.predict import predict_mask
from src.training.checkpoint import CheckpointManager
from src.training.config import TrainingConfig
from src.training.metrics import MLMMetricAccumulator, compute_batch_mlm_metrics
from src.training.optimizer import create_optimizer, perform_optimizer_step
from src.training.scheduler import get_linear_schedule_with_warmup
from src.training.trainer import Trainer


class DummyMiniDataset(Dataset):
    """Dataset sintetis kecil deterministik untuk pengujian unit trainer yang cepat."""

    def __init__(self, num_samples: int = 8, seq_len: int = 16, vocab_size: int = 8000):
        self.samples = []
        for i in range(num_samples):
            # 1 [CLS], seq_len-2 token isi (> 4), 1 [SEP]
            tokens = [2] + [(i * 13 + j) % (vocab_size - 10) + 5 for j in range(seq_len - 2)] + [3]
            mask = [1] * seq_len
            self.samples.append({
                "doc_id": f"dummy_{i}",
                "chunk_index": 0,
                "input_ids": tokens,
                "attention_mask": mask,
                "num_content_tokens": seq_len - 2,
            })
        self.vocab_size = vocab_size

    def __len__(self):
        return len(self.samples)

    def __getitem__(self, idx):
        item = self.samples[idx]
        return {
            "doc_id": item["doc_id"],
            "chunk_index": item["chunk_index"],
            "input_ids": list(item["input_ids"]),
            "attention_mask": list(item["attention_mask"]),
            "num_content_tokens": item["num_content_tokens"],
        }


class TestTrainingPipeline(unittest.TestCase):
    """Pengujian unit lengkap untuk modul training, optimizer, scheduler, metrik, dan checkpoint."""

    def setUp(self):
        self.temp_dir = tempfile.mkdtemp(prefix="test_training_")
        self.vocab_size = 8000
        self.config = MiniBertConfig(
            vocab_size=self.vocab_size,
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

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_weighted_metrics_different_targets(self):
        """1. Verifikasi agregasi metrik berbobot jumlah target riil antarepoch."""
        vocab_size = 50
        accumulator = MLMMetricAccumulator(vocab_size=vocab_size)

        # Batch 1: 10 target, loss rata-rata = 2.0 -> loss_sum = 20.0, top1 = 8/10 (80%)
        # Batch 2: 20 target, loss rata-rata = 0.5 -> loss_sum = 10.0, top1 = 10/20 (50%)
        # Unweighted average loss = (2.0 + 0.5) / 2 = 1.25
        # Weighted average loss = (20.0 + 10.0) / (10 + 20) = 30.0 / 30 = 1.00
        # Weighted top1 acc = (8 + 10) / 30 = 18 / 30 = 60.0%

        # Simulasikan perhitungan dengan menyuntikkan data ke akumulator
        accumulator.total_loss_sum = 30.0
        accumulator.total_targets = 30
        accumulator.total_top1_correct = 18
        accumulator.total_top5_correct = 24
        accumulator.batch_count = 2

        results = accumulator.compute()
        self.assertAlmostEqual(results["loss"], 1.0, places=5)
        self.assertNotAlmostEqual(results["loss"], 1.25, places=2)
        self.assertAlmostEqual(results["top1_acc"], 0.60, places=5)
        self.assertAlmostEqual(results["top5_acc"], 0.80, places=5)
        self.assertAlmostEqual(results["exp_masked_loss"], math.exp(1.0), places=4)

        # Uji penolakan batch tanpa target
        empty_labels = torch.full((2, 16), -100, dtype=torch.long)
        dummy_logits = torch.randn(2, 16, vocab_size)
        with self.assertRaises(ValueError):
            compute_batch_mlm_metrics(dummy_logits, empty_labels, vocab_size=vocab_size)

    def test_ignore_index_minus_100(self):
        """2. Verifikasi posisi labels == -100 tidak memengaruhi nilai loss atau akurasi."""
        logits1 = torch.randn(2, 8, self.vocab_size)
        labels = torch.full((2, 8), -100, dtype=torch.long)
        labels[0, 2] = 150
        labels[1, 5] = 250

        # Hitung metrik awal
        res1 = compute_batch_mlm_metrics(logits1, labels, vocab_size=self.vocab_size)

        # Ubah nilai logit secara ekstrem pada seluruh posisi non-target (selain [0,2] dan [1,5])
        logits2 = logits1.clone()
        logits2[0, 0, :] += 999.0
        logits2[0, 1, :] -= 500.0
        logits2[1, 4, :] *= 100.0

        res2 = compute_batch_mlm_metrics(logits2, labels, vocab_size=self.vocab_size)

        self.assertAlmostEqual(res1["loss"], res2["loss"], places=5)
        self.assertEqual(res1["top1_correct"], res2["top1_correct"])
        self.assertEqual(res1["top5_correct"], res2["top5_correct"])

    def test_optimizer_parameter_coverage_and_tied_weights(self):
        """3. Verifikasi parameter optimizer unik tepat satu kali dan pemisahan decay/no-decay."""
        model = MiniBertForMaskedLM(self.config)
        optimizer, summary = create_optimizer(model, learning_rate=3e-4, weight_decay=0.01)

        # Pastikan tidak ada data_ptr duplikat di seluruh param groups
        all_params = [p for group in optimizer.param_groups for p in group["params"]]
        all_ptrs = [p.data_ptr() for p in all_params]
        self.assertEqual(len(all_ptrs), len(set(all_ptrs)))

        # cls.decoder.weight harus terdeteksi sebagai tied dan dilewati
        self.assertIn("cls.decoder.weight", summary["tied_skipped_names"])

        # Total parameter di optimizer harus sama persis dengan total parameter unik model (1.453.760)
        total_opt_params = sum(p.numel() for p in all_params)
        self.assertEqual(total_opt_params, model.num_parameters(only_trainable=True))
        self.assertEqual(total_opt_params, 1453760)

        # Periksa pemisahan weight decay
        for group in optimizer.param_groups:
            if group["group_name"] == "decay":
                self.assertEqual(group["weight_decay"], 0.01)
                for p in group["params"]:
                    self.assertGreater(p.ndim, 1)  # Bobot matriks
            elif group["group_name"] == "no_decay":
                self.assertEqual(group["weight_decay"], 0.0)

    def test_single_optimizer_step_updates_weights_finite(self):
        """4. Verifikasi satu optimizer step benar-benar memperbarui bobot dengan gradien finite."""
        torch.manual_seed(42)
        model = MiniBertForMaskedLM(self.config)
        optimizer, _ = create_optimizer(model, learning_rate=1e-2, weight_decay=0.0)

        # Salin bobot sebelum step
        weight_before = model.embeddings.word_embeddings.weight.clone()

        input_ids = torch.randint(0, 8000, (2, 8), dtype=torch.long)
        attention_mask = torch.ones(2, 8, dtype=torch.long)
        labels = torch.full((2, 8), -100, dtype=torch.long)
        labels[0, 3] = 45
        labels[1, 6] = 88

        logits = model(input_ids=input_ids, attention_mask=attention_mask)
        loss_fn = nn.CrossEntropyLoss(ignore_index=-100)
        loss = loss_fn(logits.view(-1, 8000), labels.view(-1))

        optimizer.zero_grad(set_to_none=True)
        grad_norm = perform_optimizer_step(model, optimizer, loss, max_grad_norm=1.0)

        # Pastikan grad_norm finite
        self.assertTrue(math.isfinite(grad_norm))
        self.assertGreater(grad_norm, 0.0)

        # Pastikan bobot terbarui
        weight_after = model.embeddings.word_embeddings.weight
        self.assertFalse(torch.equal(weight_before, weight_after))

        # Tied weight juga harus terbarui otomatis
        self.assertTrue(torch.equal(model.cls.decoder.weight, weight_after))

    def test_scheduler_and_global_step_progression(self):
        """5. Verifikasi nilai learning rate pada langkah 1, puncak warmup, dan akhir run."""
        model = MiniBertForMaskedLM(self.config)
        optimizer, _ = create_optimizer(model, learning_rate=1e-3)

        num_warmup = 10
        total_steps = 100
        scheduler = get_linear_schedule_with_warmup(
            optimizer=optimizer,
            num_warmup_steps=num_warmup,
            num_training_steps=total_steps,
            min_lr_ratio=0.0,
        )

        # Pada inisialisasi awal sebelum step 1 (0-indexed step 0)
        # Langkah 1 (optimizer step pertama): LR = 1e-3 * (1 / 10) = 1e-4
        lr_step1 = optimizer.param_groups[0]["lr"]
        self.assertAlmostEqual(lr_step1, 1e-3 * (1.0 / 10.0), places=7)

        # Simulasikan langkah warmup hingga langkah ke-10
        for step in range(1, 10):
            optimizer.step()
            scheduler.step()

        # Pada akhir warmup (optimizer step 10): LR harus tepat mencapai 1.0 * base_lr (1e-3)
        lr_peak = optimizer.param_groups[0]["lr"]
        self.assertAlmostEqual(lr_peak, 1e-3, places=7)

        # Simulasikan decay hingga langkah ke-100 (akhir run)
        for step in range(10, 100):
            optimizer.step()
            scheduler.step()

        # Pada akhir run (step 100): LR harus bernilai 0.0
        lr_final = optimizer.param_groups[0]["lr"]
        self.assertAlmostEqual(lr_final, 0.0, places=7)

        # Uji penolakan konfigurasi cacat
        with self.assertRaises(ValueError):
            get_linear_schedule_with_warmup(optimizer, num_warmup_steps=50, num_training_steps=20)
        with self.assertRaises(ValueError):
            get_linear_schedule_with_warmup(optimizer, num_warmup_steps=-1, num_training_steps=20)
        with self.assertRaises(ValueError):
            get_linear_schedule_with_warmup(optimizer, num_warmup_steps=5, num_training_steps=0)

    def test_epoch_boundary_checkpoint_and_resume(self):
        """6. Membandingkan run CPU tanpa putus dengan run yang di-resume pada batas epoch."""
        dummy_train = DummyMiniDataset(num_samples=16, seq_len=16)
        dummy_val = DummyMiniDataset(num_samples=8, seq_len=16)

        run_uninterrupted_dir = os.path.join(self.temp_dir, "run_uninterrupted")
        cfg_uninterrupted = TrainingConfig(
            output_dir=run_uninterrupted_dir,
            epochs=2,
            batch_size=4,
            learning_rate=1e-3,
            device="cpu",
            model_seed=123,
            shuffle_seed=456,
            masking_seed=789,
            overwrite_output_dir=True,
        )

        trainer1 = Trainer(cfg_uninterrupted, train_dataset=dummy_train, val_dataset=dummy_val)
        history_uninterrupted = trainer1.train()

        # Sekarang simulasikan run bertahap: Latih Epoch 1 -> Simpan -> Buat Trainer Baru -> Resume Epoch 2
        run_resumed_dir = os.path.join(self.temp_dir, "run_resumed")
        cfg_phase1 = TrainingConfig(
            output_dir=run_resumed_dir,
            epochs=2,
            batch_size=4,
            learning_rate=1e-3,
            device="cpu",
            model_seed=123,
            shuffle_seed=456,
            masking_seed=789,
            overwrite_output_dir=True,
        )
        trainer_p1 = Trainer(cfg_phase1, train_dataset=dummy_train, val_dataset=dummy_val)
        train_m1 = trainer_p1.train_one_epoch(1)
        val_m1 = trainer_p1.evaluate()
        trainer_p1.history.append({
            "epoch": 1,
            "global_step": trainer_p1.global_step,
            "learning_rate": train_m1["learning_rate"],
            "train_loss": train_m1["loss"],
            "train_top1_acc": train_m1["top1_acc"],
            "train_top5_acc": train_m1["top5_acc"],
            "train_exp_masked_loss": train_m1["exp_masked_loss"],
            "train_targets": train_m1["total_targets"],
            "train_duration_sec": train_m1["epoch_duration_sec"],
            "val_loss": val_m1["loss"],
            "val_top1_acc": val_m1["top1_acc"],
            "val_top5_acc": val_m1["top5_acc"],
            "val_exp_masked_loss": val_m1["exp_masked_loss"],
            "val_targets": val_m1["total_targets"],
            "val_duration_sec": val_m1["eval_duration_sec"],
            "is_best": True,
        })
        trainer_p1._save_history()
        trainer_p1.checkpoint_manager.save_training_checkpoint(
            model=trainer_p1.model,
            optimizer=trainer_p1.optimizer,
            scheduler=trainer_p1.scheduler,
            epoch_completed=1,
            global_step=trainer_p1.global_step,
            best_val_loss=val_m1["loss"],
            best_epoch=1,
            best_global_step=trainer_p1.global_step,
            train_config=cfg_phase1,
            history=trainer_p1.history,
            best_model_state_dict=trainer_p1.model.state_dict(),
            dataloader_generator=trainer_p1.dataloader_generator,
            is_best=True,
        )

        # Checkpoint epoch 1
        ckpt_epoch1 = os.path.join(run_resumed_dir, "checkpoints", "checkpoint_epoch_001.pt")
        self.assertTrue(os.path.exists(ckpt_epoch1))

        # Buat trainer baru untuk melanjutkan ke Epoch 2
        trainer_p2 = Trainer(cfg_phase1, train_dataset=dummy_train, val_dataset=dummy_val, is_resume=True)
        trainer_p2.resume_from_checkpoint(ckpt_epoch1)
        history_resumed = trainer_p2.train()

        # Verifikasi bahwa riwayat memuat 2 epoch lengkap tanpa duplikasi atau kehilangan
        self.assertEqual(len(history_resumed), 2)
        self.assertEqual(history_resumed[0]["epoch"], 1)
        self.assertEqual(history_resumed[1]["epoch"], 2)

        # Verifikasi bahwa Epoch 2 pada run resumed konsisten dengan run uninterrupted
        self.assertAlmostEqual(
            history_uninterrupted[1]["val_loss"],
            history_resumed[1]["val_loss"],
            places=3,
        )

    def test_exported_model_compatible_with_inference_loader(self):
        """7. Verifikasi model ekspor bertanda 'trained' kompatibel dengan loader Anggota 2."""
        model = MiniBertForMaskedLM(self.config)
        ckpt_mgr = CheckpointManager(output_dir=self.temp_dir, overwrite=True)

        export_dir = ckpt_mgr.export_inference_model(
            model=model,
            export_subdir="test_best_model",
            global_step=10,  # Ada pembaruan training
        )

        # Muat menggunakan MiniBertForMaskedLM.from_pretrained
        loaded_model = MiniBertForMaskedLM.from_pretrained(
            load_directory=export_dir,
            tokenizer_dir="data/processed/pilot",
            require_tokenizer=True,
        )
        self.assertEqual(loaded_model.checkpoint_status, "trained")

        # Jalankan predict_mask
        res = predict_mask(
            text="Indonesia adalah negara [MASK] di Asia Tenggara.",
            checkpoint_dir=export_dir,
            tokenizer_dir="data/processed/pilot",
            top_k=5,
            device="cpu",
        )
        self.assertEqual(res["checkpoint_status"], "trained")
        self.assertEqual(len(res["predictions"]), 1)
        self.assertEqual(len(res["predictions"][0]["candidates"]), 5)

    def test_training_and_validation_never_touch_test_split(self):
        """8. Verifikasi isolasi mutlak: split test tidak pernah diakses atau dimuat."""
        cfg = TrainingConfig(
            output_dir=os.path.join(self.temp_dir, "test_isolation_run"),
            device="cpu",
            overwrite_output_dir=True,
        )
        trainer = Trainer(cfg)

        # Pastikan path dataset trainer hanya train dan val
        train_path = os.path.normpath(trainer.train_dataset.jsonl_path)
        val_path = os.path.normpath(trainer.val_dataset.jsonl_path)

        self.assertNotIn("test_chunks.jsonl", train_path)
        self.assertNotIn("test.jsonl", train_path)
        self.assertNotIn("test_chunks.jsonl", val_path)
        self.assertNotIn("test.jsonl", val_path)
        self.assertTrue(train_path.endswith("train_chunks.jsonl"))
        self.assertTrue(val_path.endswith("val_chunks.jsonl"))

    def test_best_model_export_is_best_not_last(self):
        """9. Verifikasi ekspor best_model berasal murni dari epoch dengan val loss terbaik, bukan epoch terakhir."""
        dummy_train = DummyMiniDataset(num_samples=16, seq_len=16)
        dummy_val = DummyMiniDataset(num_samples=8, seq_len=16)

        run_dir = os.path.join(self.temp_dir, "run_best_not_last")
        cfg = TrainingConfig(
            output_dir=run_dir,
            epochs=2,
            batch_size=4,
            learning_rate=1e-3,
            device="cpu",
            model_seed=123,
            shuffle_seed=456,
            masking_seed=789,
            overwrite_output_dir=True,
            save_best_model=True,
            save_last_checkpoint=True,
        )

        trainer = Trainer(cfg, train_dataset=dummy_train, val_dataset=dummy_val)

        # Mock evaluate: Epoch 1 sengaja memiliki val_loss lebih rendah (terbaik) daripada Epoch 2
        eval_counter = 0
        def mocked_evaluate():
            nonlocal eval_counter
            eval_counter += 1
            if eval_counter == 1:
                return {
                    "loss": 2.50,
                    "top1_acc": 0.50,
                    "top5_acc": 0.80,
                    "exp_masked_loss": 12.18,
                    "total_targets": 10,
                    "eval_duration_sec": 0.05,
                }
            else:
                return {
                    "loss": 6.80,
                    "top1_acc": 0.10,
                    "top5_acc": 0.30,
                    "exp_masked_loss": 897.8,
                    "total_targets": 10,
                    "eval_duration_sec": 0.05,
                }

        trainer.evaluate = mocked_evaluate
        history = trainer.train()

        # Pastikan pelacakan best epoch menunjuk ke Epoch 1, bukan Epoch 2
        self.assertEqual(trainer.best_epoch, 1)
        self.assertAlmostEqual(trainer.best_val_loss, 2.50, places=4)
        self.assertEqual(history[0]["is_best"], True)
        self.assertEqual(history[1]["is_best"], False)

        # Muat bobot best_model yang diekspor
        best_model_path = os.path.join(run_dir, "best_model", "model.pt")
        self.assertTrue(os.path.exists(best_model_path))
        exported_payload = torch.load(best_model_path, map_location="cpu", weights_only=True)
        exported_weights = exported_payload["state_dict"]

        # 1. Bobot ekspor HARUS SAMA PERSIS dengan best_model_state_dict (Epoch 1)
        for param_name, param_tensor in trainer.best_model_state_dict.items():
            self.assertTrue(
                torch.equal(exported_weights[param_name], param_tensor),
                f"Parameter {param_name} tidak cocok dengan bobot Epoch 1!",
            )

        # 2. Bobot ekspor HARUS BERBEDA dari bobot model aktif pada akhir pelatihan (Epoch 2)
        differing_params = 0
        active_weights = trainer.model.state_dict()
        for param_name in exported_weights:
            if not torch.equal(exported_weights[param_name], active_weights[param_name]):
                differing_params += 1
        self.assertGreater(differing_params, 0, "Bobot ekspor tidak boleh identik dengan bobot epoch terakhir!")

        # 3. Checkpoint last_checkpoint.pt dan best_checkpoint.pt harus mencerminkan perbedaannya
        last_ckpt = torch.load(os.path.join(run_dir, "checkpoints", "last_checkpoint.pt"), map_location="cpu", weights_only=True)
        self.assertEqual(last_ckpt["epoch_completed"], 2)
        self.assertEqual(last_ckpt["best_epoch"], 1)
        self.assertAlmostEqual(last_ckpt["best_val_loss"], 2.50, places=4)

        best_ckpt = torch.load(os.path.join(run_dir, "checkpoints", "best_checkpoint.pt"), map_location="cpu", weights_only=True)
        self.assertEqual(best_ckpt["epoch_completed"], 1)

        # 4. Pastikan training_history.json mencatat best_epoch, best_val_loss, dan best_global_step
        with open(os.path.join(run_dir, "training_history.json"), "r", encoding="utf-8") as f:
            hist_json = json.load(f)
        self.assertEqual(hist_json["best_epoch"], 1)
        self.assertAlmostEqual(hist_json["best_val_loss"], 2.50, places=4)
        self.assertIsNotNone(hist_json["best_global_step"])

    def test_resume_in_same_directory_without_overwrite(self):
        """10. Verifikasi resume dapat menggunakan direktori yang sama tanpa --overwrite dan menolak run baru jika direktori berisi."""
        dummy_train = DummyMiniDataset(num_samples=16, seq_len=16)
        dummy_val = DummyMiniDataset(num_samples=8, seq_len=16)

        run_dir = os.path.join(self.temp_dir, "run_same_dir_resume")
        cfg = TrainingConfig(
            output_dir=run_dir,
            epochs=2,
            batch_size=4,
            learning_rate=1e-3,
            device="cpu",
            model_seed=123,
            shuffle_seed=456,
            masking_seed=789,
            overwrite_output_dir=False,  # Eksplisit False
        )

        # Fase 1: Inisialisasi awal pada direktori kosong
        trainer_p1 = Trainer(cfg, train_dataset=dummy_train, val_dataset=dummy_val, is_resume=False)
        m1 = trainer_p1.train_one_epoch(1)
        v1 = trainer_p1.evaluate()
        trainer_p1.history.append({
            "epoch": 1,
            "global_step": trainer_p1.global_step,
            "learning_rate": m1["learning_rate"],
            "train_loss": m1["loss"],
            "train_top1_acc": m1["top1_acc"],
            "train_top5_acc": m1["top5_acc"],
            "train_exp_masked_loss": m1["exp_masked_loss"],
            "train_targets": m1["total_targets"],
            "train_duration_sec": m1["epoch_duration_sec"],
            "val_loss": v1["loss"],
            "val_top1_acc": v1["top1_acc"],
            "val_top5_acc": v1["top5_acc"],
            "val_exp_masked_loss": v1["exp_masked_loss"],
            "val_targets": v1["total_targets"],
            "val_duration_sec": v1["eval_duration_sec"],
            "is_best": True,
        })
        trainer_p1._save_history()
        ckpt_path = trainer_p1.checkpoint_manager.save_training_checkpoint(
            model=trainer_p1.model,
            optimizer=trainer_p1.optimizer,
            scheduler=trainer_p1.scheduler,
            epoch_completed=1,
            global_step=trainer_p1.global_step,
            best_val_loss=v1["loss"],
            best_epoch=1,
            best_global_step=trainer_p1.global_step,
            train_config=cfg,
            history=trainer_p1.history,
            is_best=True,
        )

        # Uji 1: Run baru pada direktori yang tidak kosong dengan overwrite=False HARUS DITOLAK
        with self.assertRaises(FileExistsError):
            Trainer(cfg, train_dataset=dummy_train, val_dataset=dummy_val, is_resume=False)

        # Uji 2: Resume pada direktori yang sama dengan overwrite=False HARUS DIIZINKAN
        trainer_p2 = Trainer(cfg, train_dataset=dummy_train, val_dataset=dummy_val, is_resume=True)
        trainer_p2.resume_from_checkpoint(ckpt_path)
        history = trainer_p2.train()

        # Uji 3: Riwayat harus memuat tepat 2 baris (tidak ada baris hilang atau ganda)
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["epoch"], 1)
        self.assertEqual(history[1]["epoch"], 2)

        # Uji 4: Pastikan berkas CSV dan JSON di disk juga memiliki 2 epoch
        with open(os.path.join(run_dir, "training_history.json"), "r", encoding="utf-8") as f:
            disk_json = json.load(f)
        self.assertEqual(disk_json["total_epochs"], 2)
        self.assertEqual(len(disk_json["history"]), 2)

    def test_checkpoint_validation_rejections(self):
        """11. Verifikasi penolakan ketat saat memuat checkpoint yang korup, cacat, atau tidak kompatibel."""
        dummy_train = DummyMiniDataset(num_samples=16, seq_len=16)
        dummy_val = DummyMiniDataset(num_samples=8, seq_len=16)

        run_dir = os.path.join(self.temp_dir, "run_validation_rejections")
        cfg = TrainingConfig(
            output_dir=run_dir,
            epochs=2,
            batch_size=4,
            learning_rate=1e-3,
            device="cpu",
            overwrite_output_dir=True,
        )

        trainer = Trainer(cfg, train_dataset=dummy_train, val_dataset=dummy_val)
        m1 = trainer.train_one_epoch(1)
        v1 = trainer.evaluate()
        trainer.history.append({
            "epoch": 1, "global_step": trainer.global_step, "learning_rate": m1["learning_rate"],
            "train_loss": m1["loss"], "train_top1_acc": m1["top1_acc"], "train_top5_acc": m1["top5_acc"],
            "train_exp_masked_loss": m1["exp_masked_loss"], "train_targets": m1["total_targets"],
            "train_duration_sec": m1["epoch_duration_sec"], "val_loss": v1["loss"],
            "val_top1_acc": v1["top1_acc"], "val_top5_acc": v1["top5_acc"],
            "val_exp_masked_loss": v1["exp_masked_loss"], "val_targets": v1["total_targets"],
            "val_duration_sec": v1["eval_duration_sec"], "is_best": True,
        })
        trainer._save_history()
        valid_ckpt_path = trainer.checkpoint_manager.save_training_checkpoint(
            model=trainer.model,
            optimizer=trainer.optimizer,
            scheduler=trainer.scheduler,
            epoch_completed=1,
            global_step=trainer.global_step,
            best_val_loss=v1["loss"],
            best_epoch=1,
            best_global_step=trainer.global_step,
            train_config=cfg,
            history=trainer.history,
            is_best=True,
            filename="valid_checkpoint.pt",
        )

        # Baseline: Validasi pemuatan valid berhasil
        raw_valid = torch.load(valid_ckpt_path, map_location="cpu", weights_only=True)

        # Kasus A: Kunci metadata wajib hilang
        corrupt_ckpt = dict(raw_valid)
        del corrupt_ckpt["history"]
        corrupt_path = os.path.join(run_dir, "checkpoints", "corrupt_missing_key.pt")
        torch.save(corrupt_ckpt, corrupt_path)
        with self.assertRaises(ValueError) as ctx:
            CheckpointManager.load_training_checkpoint(corrupt_path, cfg, trainer.model, trainer.optimizer, trainer.scheduler)
        self.assertIn("Kunci metadata wajib hilang", str(ctx.exception))

        # Kasus B: Data train/val berubah (hash tidak cocok)
        corrupt_ckpt = dict(raw_valid)
        corrupt_ckpt["data_hashes"] = dict(raw_valid["data_hashes"])
        corrupt_ckpt["data_hashes"]["train_file"] = "tampered_train_hash_00000000000000"
        corrupt_path = os.path.join(run_dir, "checkpoints", "corrupt_train_hash.pt")
        torch.save(corrupt_ckpt, corrupt_path)
        with self.assertRaises(ValueError) as ctx:
            CheckpointManager.load_training_checkpoint(corrupt_path, cfg, trainer.model, trainer.optimizer, trainer.scheduler)
        self.assertIn("Hash berkas train telah berubah", str(ctx.exception))

        # Kasus C: Konfigurasi training kritis berubah (misal learning_rate atau batch_size)
        corrupt_ckpt = dict(raw_valid)
        corrupt_ckpt["training_config"] = dict(raw_valid["training_config"])
        corrupt_ckpt["training_config"]["learning_rate"] = 0.999
        corrupt_path = os.path.join(run_dir, "checkpoints", "corrupt_lr.pt")
        torch.save(corrupt_ckpt, corrupt_path)
        with self.assertRaises(ValueError) as ctx:
            CheckpointManager.load_training_checkpoint(corrupt_path, cfg, trainer.model, trainer.optimizer, trainer.scheduler)
        self.assertIn("learning_rate", str(ctx.exception))

        # Kasus D: Konfigurasi model berbeda (meskipun tensor weights cocok)
        corrupt_ckpt = dict(raw_valid)
        corrupt_ckpt["model_config"] = dict(raw_valid["model_config"])
        corrupt_ckpt["model_config"]["dropout"] = 0.5  # Beda dari 0.1
        corrupt_path = os.path.join(run_dir, "checkpoints", "corrupt_dropout.pt")
        torch.save(corrupt_ckpt, corrupt_path)
        with self.assertRaises(ValueError) as ctx:
            CheckpointManager.load_training_checkpoint(corrupt_path, cfg, trainer.model, trainer.optimizer, trainer.scheduler)
        self.assertIn("dropout", str(ctx.exception))

        # Kasus E: Subset parameter berbeda
        corrupt_ckpt = dict(raw_valid)
        corrupt_ckpt["data_hashes"] = dict(raw_valid["data_hashes"])
        corrupt_ckpt["data_hashes"]["max_train_samples"] = 9999
        corrupt_path = os.path.join(run_dir, "checkpoints", "corrupt_subset.pt")
        torch.save(corrupt_ckpt, corrupt_path)
        with self.assertRaises(ValueError) as ctx:
            CheckpointManager.load_training_checkpoint(corrupt_path, cfg, trainer.model, trainer.optimizer, trainer.scheduler)
        self.assertIn("max_train_samples berbeda", str(ctx.exception))

        # Kasus F: Konflik cabang riwayat (direktori memuat epoch lebih baru dari checkpoint)
        conflict_dir = os.path.join(self.temp_dir, "run_branch_conflict")
        os.makedirs(conflict_dir, exist_ok=True)
        with open(os.path.join(conflict_dir, "training_history.json"), "w", encoding="utf-8") as f:
            json.dump({"history": [{"epoch": 1}, {"epoch": 2}, {"epoch": 3}]}, f)
        conflict_cfg = TrainingConfig(output_dir=conflict_dir, device="cpu", overwrite_output_dir=False)
        conflict_trainer = Trainer(conflict_cfg, train_dataset=dummy_train, val_dataset=dummy_val, is_resume=True)
        with self.assertRaises(ValueError) as ctx:
            conflict_trainer.resume_from_checkpoint(valid_ckpt_path)
        self.assertIn("Konflik riwayat resume", str(ctx.exception))

    def test_history_saved_per_epoch_and_atomic(self):
        """12. Verifikasi riwayat tersimpan per-epoch secara atomik ke JSON dan CSV."""
        dummy_train = DummyMiniDataset(num_samples=16, seq_len=16)
        dummy_val = DummyMiniDataset(num_samples=8, seq_len=16)

        run_dir = os.path.join(self.temp_dir, "run_atomic_history")
        cfg = TrainingConfig(
            output_dir=run_dir,
            epochs=2,
            batch_size=4,
            learning_rate=1e-3,
            device="cpu",
            overwrite_output_dir=True,
        )

        trainer = Trainer(cfg, train_dataset=dummy_train, val_dataset=dummy_val)

        # Latih Epoch 1 secara individual
        m1 = trainer.train_one_epoch(1)
        v1 = trainer.evaluate()
        trainer.history.append({
            "epoch": 1,
            "global_step": trainer.global_step,
            "learning_rate": m1["learning_rate"],
            "train_loss": m1["loss"],
            "train_top1_acc": m1["top1_acc"],
            "train_top5_acc": m1["top5_acc"],
            "train_exp_masked_loss": m1["exp_masked_loss"],
            "train_targets": m1["total_targets"],
            "train_duration_sec": m1["epoch_duration_sec"],
            "val_loss": v1["loss"],
            "val_top1_acc": v1["top1_acc"],
            "val_top5_acc": v1["top5_acc"],
            "val_exp_masked_loss": v1["exp_masked_loss"],
            "val_targets": v1["total_targets"],
            "val_duration_sec": v1["eval_duration_sec"],
            "is_best": True,
        })
        trainer._save_history()

        json_path = os.path.join(run_dir, "training_history.json")
        csv_path = os.path.join(run_dir, "training_history.csv")

        # Pastikan berkas langsung ada sebelum Epoch 2 dimulai
        self.assertTrue(os.path.exists(json_path))
        self.assertTrue(os.path.exists(csv_path))

        # Pastikan tidak ada berkas .tmp tersisa
        self.assertFalse(os.path.exists(json_path + ".tmp"))
        self.assertFalse(os.path.exists(csv_path + ".tmp"))

        with open(json_path, "r", encoding="utf-8") as f:
            j_data = json.load(f)
        self.assertEqual(j_data["total_epochs"], 1)
        self.assertEqual(j_data["history"][0]["epoch"], 1)

        with open(csv_path, "r", encoding="utf-8") as f:
            lines = f.readlines()
        # 1 baris header + 1 baris epoch 1
        self.assertEqual(len(lines), 2)

    def test_subset_config_limits(self):
        """13. Verifikasi mekanisme batasan sampel subset deterministik pada DataLoader dan metadata checkpoint."""
        # Konfigurasi dengan batas sampel
        cfg = TrainingConfig(
            output_dir=os.path.join(self.temp_dir, "run_subset_test"),
            max_train_samples=32,
            max_val_samples=16,
            batch_size=4,
            epochs=2,
            device="cpu",
            overwrite_output_dir=True,
        )

        trainer = Trainer(cfg)
        self.assertEqual(len(trainer.train_dataset), 32)
        self.assertEqual(len(trainer.val_dataset), 16)
        self.assertEqual(len(trainer.train_loader), 8)  # 32 / 4 = 8 batch
        self.assertEqual(len(trainer.val_loader), 4)    # 16 / 4 = 4 batch

        # Simpan checkpoint dan periksa metadata subset
        ckpt_path = trainer.checkpoint_manager.save_training_checkpoint(
            model=trainer.model,
            optimizer=trainer.optimizer,
            scheduler=trainer.scheduler,
            epoch_completed=1,
            global_step=8,
            best_val_loss=8.5,
            train_config=cfg,
            history=[],
        )

        ckpt = torch.load(ckpt_path, map_location="cpu", weights_only=True)
        self.assertTrue(ckpt["data_hashes"]["is_subset"])
        self.assertEqual(ckpt["data_hashes"]["max_train_samples"], 32)
        self.assertEqual(ckpt["data_hashes"]["max_val_samples"], 16)

        # Uji validasi TrainingConfig: nilai negatif atau nol harus ditolak
        with self.assertRaises(ValueError):
            TrainingConfig(max_train_samples=0)
        with self.assertRaises(ValueError):
            TrainingConfig(max_val_samples=-5)


if __name__ == "__main__":
    unittest.main()

