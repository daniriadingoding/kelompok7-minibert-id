"""
Unit test komprehensif untuk memverifikasi tokenizer, vocabulary, split, dan sequence chunking.
Mencakup seluruh butir verifikasi Bagian F:
1. ID token khusus benar dan mapping save/load identik.
2. [MASK] tetap dikenali setelah normalisasi.
3. Vocabulary tidak dibangun dari validation/test (Train-only verification).
4. Split deterministik dan bebas kebocoran (0 irisan ID & hash).
5. Panjang hasil encoding, truncation, padding, serta attention_mask benar.
6. Artikel panjang menghasilkan beberapa chunk tanpa kehilangan token selain sisa yang dikeluarkan.
7. Penanganan teks kosong, Unicode, angka, tanda baca, dan kata tak dikenal.
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.data.tokenizer import (
    WordLevelTokenizer,
    SPECIAL_TOKENS,
    SPECIAL_TOKEN_IDS,
    PAD_TOKEN,
    UNK_TOKEN,
    CLS_TOKEN,
    SEP_TOKEN,
    MASK_TOKEN,
)
from src.data.chunker import chunk_document, DEFAULT_MAX_LENGTH
from src.data.split_dataset import split_document_dataset, normalize_for_leakage_check


class TestTokenizerAndPipeline(unittest.TestCase):

    @classmethod
    def setUpClass(cls):
        cls.pilot_processed_dir = "data/processed/pilot"
        cls.tokenizer = WordLevelTokenizer.from_pretrained(cls.pilot_processed_dir)

    def test_01_special_tokens_ids_and_save_load(self):
        """Verifikasi ID token khusus dan persistensi save/load yang identik."""
        self.assertEqual(self.tokenizer.pad_token_id, 0)
        self.assertEqual(self.tokenizer.unk_token_id, 1)
        self.assertEqual(self.tokenizer.cls_token_id, 2)
        self.assertEqual(self.tokenizer.sep_token_id, 3)
        self.assertEqual(self.tokenizer.mask_token_id, 4)

        # Simpan ke direktori temporer dan muat kembali
        temp_dir = tempfile.mkdtemp()
        try:
            self.tokenizer.save_pretrained(temp_dir)
            loaded_tokenizer = WordLevelTokenizer.from_pretrained(temp_dir)

            self.assertEqual(self.tokenizer.vocab_size, loaded_tokenizer.vocab_size)
            self.assertEqual(self.tokenizer.vocab, loaded_tokenizer.vocab)
            self.assertEqual(self.tokenizer.id_to_token, loaded_tokenizer.id_to_token)
            self.assertEqual(self.tokenizer.config["vocab_size"], loaded_tokenizer.config["vocab_size"])
        finally:
            shutil.rmtree(temp_dir)

    def test_02_mask_token_recognition(self):
        """Verifikasi bahwa [MASK] tetap dikenali utuh sebagai satu token, baik uppercase maupun lowercase."""
        text_upper = "Ibu kota Indonesia adalah [MASK] ."
        tokens_upper = self.tokenizer.tokenize(text_upper)
        self.assertIn("[MASK]", tokens_upper)
        self.assertEqual(tokens_upper[4], "[MASK]")

        # Inferensi dengan lowercase [mask]
        text_lower = "Ibu kota Indonesia adalah [mask] ."
        tokens_lower = self.tokenizer.tokenize(text_lower)
        self.assertIn("[MASK]", tokens_lower)
        self.assertEqual(tokens_lower[4], "[MASK]")

        # Encode memetakan [MASK] ke ID 4
        enc = self.tokenizer.encode(text_upper, add_special_tokens=False, padding=False, truncation=False)
        self.assertEqual(enc["input_ids"][4], 4)

    def test_03_vocabulary_train_only(self):
        """Verifikasi bahwa vocabulary hanya dibangun dari Train dan tidak bocor dari Val/Test."""
        train_file = os.path.join(self.pilot_processed_dir, "train.jsonl")
        val_file = os.path.join(self.pilot_processed_dir, "val.jsonl")

        # Ambil set kata dari train dan val
        train_words = set()
        with open(train_file, "r", encoding="utf-8") as f:
            for line in f:
                doc = json.loads(line)
                for t in self.tokenizer.tokenize(doc["text"]):
                    if t not in SPECIAL_TOKENS:
                        train_words.add(t)

        # Seluruh kata non-spesial di vocab HARUS berasal dari train_words
        for token, tid in self.tokenizer.vocab.items():
            if token not in SPECIAL_TOKENS:
                self.assertIn(
                    token,
                    train_words,
                    f"Token '{token}' di vocab tidak ditemukan dalam split Train!"
                )

        # Cari kata yang HANYA muncul di Val (tidak pernah ada di Train)
        # Kata tersebut harus dipetakan ke [UNK]=1
        val_only_words = []
        with open(val_file, "r", encoding="utf-8") as f:
            for line in f:
                doc = json.loads(line)
                for t in self.tokenizer.tokenize(doc["text"]):
                    if t not in train_words and t not in SPECIAL_TOKENS:
                        val_only_words.append(t)
                        if len(val_only_words) >= 5:
                            break
                if len(val_only_words) >= 5:
                    break

        if val_only_words:
            for word in val_only_words:
                self.assertNotIn(word, self.tokenizer.vocab)
                self.assertEqual(self.tokenizer.convert_tokens_to_ids([word]), [1])

    def test_04_split_determinism_and_zero_leakage(self):
        """Verifikasi determinisme split dan zero leakage antarpartisi."""
        manifest_path = os.path.join(self.pilot_processed_dir, "split_manifest.json")
        self.assertTrue(os.path.exists(manifest_path))

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        verif = manifest["verification"]
        self.assertEqual(verif["train_val_id_overlap"], 0)
        self.assertEqual(verif["train_test_id_overlap"], 0)
        self.assertEqual(verif["val_test_id_overlap"], 0)
        self.assertEqual(verif["train_val_hash_overlap"], 0)
        self.assertEqual(verif["train_test_hash_overlap"], 0)
        self.assertEqual(verif["val_test_hash_overlap"], 0)
        self.assertEqual(verif["leakage_status"], "ZERO_LEAKAGE_CONFIRMED")

        # Cek determinisme pembagian ulang dengan seed yang sama
        temp_dir = tempfile.mkdtemp()
        try:
            remade_manifest = split_document_dataset(
                input_file="data/pilot/wiki_pilot_3000_cleaned.jsonl",
                output_dir=temp_dir,
                excluded_manifest_path=os.path.join(temp_dir, "excluded.json"),
                min_words=10,
                seed=42
            )
            self.assertEqual(manifest["split_ids"]["train"], remade_manifest["split_ids"]["train"])
            self.assertEqual(manifest["split_ids"]["val"], remade_manifest["split_ids"]["val"])
            self.assertEqual(manifest["split_ids"]["test"], remade_manifest["split_ids"]["test"])
        finally:
            shutil.rmtree(temp_dir)

    def test_05_encoding_padding_truncation_attention_mask(self):
        """Verifikasi panjang sequence, padding, truncation, dan attention_mask."""
        # 1. Teks pendek (perlu padding hingga 64)
        short_text = "Hari ini cuaca cerah di Jakarta."
        enc_short = self.tokenizer.encode(short_text, max_length=64, padding=True, truncation=True)
        self.assertEqual(len(enc_short["input_ids"]), 64)
        self.assertEqual(len(enc_short["attention_mask"]), 64)
        self.assertEqual(enc_short["input_ids"][0], 2)  # [CLS]

        # Cari posisi [SEP]
        sep_idx = enc_short["input_ids"].index(3)
        self.assertGreater(sep_idx, 0)
        # Semua token sebelum dan pada [SEP] memiliki mask 1
        self.assertEqual(enc_short["attention_mask"][:sep_idx + 1], [1] * (sep_idx + 1))
        # Setelah [SEP] harus berupa padding 0
        self.assertEqual(enc_short["input_ids"][sep_idx + 1:], [0] * (64 - (sep_idx + 1)))
        self.assertEqual(enc_short["attention_mask"][sep_idx + 1:], [0] * (64 - (sep_idx + 1)))

        # 2. Teks panjang (perlu truncation tepat 64 token)
        long_text = " ".join(["kata"] * 100)
        enc_long = self.tokenizer.encode(long_text, max_length=64, padding=True, truncation=True)
        self.assertEqual(len(enc_long["input_ids"]), 64)
        self.assertEqual(len(enc_long["attention_mask"]), 64)
        self.assertEqual(enc_long["input_ids"][0], 2)  # [CLS]
        self.assertEqual(enc_long["input_ids"][63], 3)  # [SEP] di akhir batas 64
        self.assertEqual(enc_long["attention_mask"], [1] * 64)  # Tanpa padding

    def test_06_chunking_retention_and_no_token_loss(self):
        """Verifikasi chunking multi-segmen pada dokumen panjang tanpa kehilangan token."""
        # Buat teks buatan dengan tepat 150 token kata
        content_words = [f"kata{i}" for i in range(150)]
        text = " ".join(content_words)

        chunks, discarded = chunk_document(
            doc_id="test_doc_long",
            text=text,
            tokenizer=self.tokenizer,
            max_length=64,
            min_chunk_tokens=5
        )

        # max_length 64 -> content_max = 62
        # 150 kata:
        # Chunk 0: 62 kata
        # Chunk 1: 62 kata
        # Chunk 2: 26 kata (>= 5, jadi dipertahankan)
        self.assertEqual(len(chunks), 3)
        self.assertEqual(discarded, 0)

        # Verifikasi total token isi yang terkumpul sama dengan 150
        total_tokens_recovered = sum(c["num_content_tokens"] for c in chunks)
        self.assertEqual(total_tokens_recovered, 150)

        for idx, c in enumerate(chunks):
            self.assertEqual(c["doc_id"], "test_doc_long")
            self.assertEqual(c["chunk_index"], idx)
            self.assertEqual(c["total_chunks_in_doc"], 3)
            self.assertEqual(len(c["input_ids"]), 64)
            self.assertEqual(len(c["attention_mask"]), 64)
            self.assertEqual(c["input_ids"][0], 2)  # [CLS]

        # Uji kasus sisa potongan pendek < min_chunk_tokens (misal sisa 3 token)
        text_with_tiny_tail = " ".join([f"token{i}" for i in range(65)])  # 62 + 3
        chunks_tail, discarded_tail = chunk_document(
            doc_id="test_doc_tail",
            text=text_with_tiny_tail,
            tokenizer=self.tokenizer,
            max_length=64,
            min_chunk_tokens=5
        )
        self.assertEqual(len(chunks_tail), 1)  # Hanya chunk 0 yang dipertahankan
        self.assertEqual(discarded_tail, 1)  # 1 tail chunk (3 token) dikeluarkan

    def test_07_edge_cases_and_invalid_ids(self):
        """Verifikasi penanganan teks kosong, spasi murni, tanda hubung, angka, Unicode, dan invalid ID."""
        # 1. Teks kosong & spasi
        self.assertEqual(self.tokenizer.tokenize(""), [])
        self.assertEqual(self.tokenizer.tokenize("   \n\t  "), [])
        empty_chunks, _ = chunk_document("empty_doc", "", self.tokenizer)
        self.assertEqual(empty_chunks, [])

        # 2. Tanda hubung dan kata ulang
        tokens_hyphen = self.tokenizer.tokenize("anak-anak bergotong-royong")
        self.assertEqual(tokens_hyphen, ["anak", "-", "anak", "bergotong", "-", "royong"])

        # 3. Angka dan desimal
        tokens_num = self.tokenizer.tokenize("pada tahun 2024 mencapai 99.5%")
        self.assertEqual(tokens_num, ["pada", "tahun", "2024", "mencapai", "99", ".", "5", "%"])

        # 4. Unicode dan aksen
        tokens_unicode = self.tokenizer.tokenize("Café São Paulo René")
        self.assertEqual(tokens_unicode, ["café", "são", "paulo", "rené"])

        # 5. Kata tak dikenal (UNK)
        unk_word = "xyzabcdefqwertynonexistent123"
        self.assertEqual(self.tokenizer.convert_tokens_to_ids([unk_word]), [1])

        # 6. Decode validasi invalid ID
        # Valid decode
        decoded_text = self.tokenizer.decode([2, 5, 6, 3], skip_special_tokens=True)
        self.assertIsInstance(decoded_text, str)

        # Invalid ID di luar range vocab (misal ID 999999 atau negatif)
        with self.assertRaises(ValueError):
            self.tokenizer.decode([-1])
        with self.assertRaises(ValueError):
            self.tokenizer.decode([self.tokenizer.vocab_size + 100])
        with self.assertRaises(ValueError):
            self.tokenizer.decode(["bukan_int"])  # type: ignore

    def test_08_strict_vocab_validation_and_max_length(self):
        """Verifikasi penolakan eksplisit pada artefak vocab tidak valid dan validasi max_length."""
        # 1. Tolak vocab tanpa token khusus
        with self.assertRaises(ValueError) as ctx:
            WordLevelTokenizer(vocab={"kata": 0, "lain": 1})
        self.assertIn("Token khusus", str(ctx.exception))

        # 2. Tolak vocab dengan ID salah pada token khusus
        bad_special_vocab = dict(SPECIAL_TOKEN_IDS)
        bad_special_vocab["[PAD]"] = 99
        with self.assertRaises(ValueError) as ctx:
            WordLevelTokenizer(vocab=bad_special_vocab)
        self.assertIn("[PAD]", str(ctx.exception))

        # 3. Tolak vocab dengan ID duplikat
        duplicate_id_vocab = dict(SPECIAL_TOKEN_IDS)
        duplicate_id_vocab["kata1"] = 5
        duplicate_id_vocab["kata2"] = 5  # Duplikat ID
        with self.assertRaises(ValueError) as ctx:
            WordLevelTokenizer(vocab=duplicate_id_vocab)
        self.assertIn("duplikat", str(ctx.exception).lower())

        # 4. Tolak vocab dengan ID tidak kontigu
        non_contiguous_vocab = dict(SPECIAL_TOKEN_IDS)
        non_contiguous_vocab["kata1"] = 5
        non_contiguous_vocab["kata2"] = 7  # ID 6 hilang
        with self.assertRaises(ValueError) as ctx:
            WordLevelTokenizer(vocab=non_contiguous_vocab)
        self.assertIn("kontigu", str(ctx.exception).lower())

        # 5. Validasi max_length < 2 pada encode
        with self.assertRaises(ValueError) as ctx:
            self.tokenizer.encode("Halo", add_special_tokens=True, max_length=1)
        self.assertIn("max_length", str(ctx.exception).lower())

        # 6. Validasi max_length <= 2 pada chunker
        with self.assertRaises(ValueError) as ctx:
            chunk_document("doc_test", "Halo dunia", self.tokenizer, max_length=2)
        self.assertIn("max_length", str(ctx.exception).lower())


if __name__ == "__main__":
    unittest.main()

