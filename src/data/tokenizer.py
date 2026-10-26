"""
Tokenizer tingkat kata (Word-Level Tokenizer) kustom untuk Mini-BERT Bahasa Indonesia.
Mendukung:
- Pemeliharaan token khusus: [PAD]=0, [UNK]=1, [CLS]=2, [SEP]=3, [MASK]=4.
- Normalisasi Unicode (NFC), kutipan, dan lowercase untuk token non-khusus.
- Pemisahan tanda baca konsisten (termasuk tanda hubung dan apostrof).
- Preservasi token khusus seperti [MASK] pada tahap tokenisasi dan inferensi.
- Encoding dengan truncation dan padding (menghasilkan input_ids dan attention_mask).
- Decoding dengan validasi ID token dan penanganan token khusus.
- Simpan dan muat artefak (vocab.json dan tokenizer_config.json).
"""

import hashlib
import json
import os
import re
import unicodedata
from typing import Dict, List, Optional, Union, Any

TOKENIZER_VERSION = "1.0.0"

PAD_TOKEN = "[PAD]"
UNK_TOKEN = "[UNK]"
CLS_TOKEN = "[CLS]"
SEP_TOKEN = "[SEP]"
MASK_TOKEN = "[MASK]"

SPECIAL_TOKENS = [PAD_TOKEN, UNK_TOKEN, CLS_TOKEN, SEP_TOKEN, MASK_TOKEN]
SPECIAL_TOKEN_IDS = {
    PAD_TOKEN: 0,
    UNK_TOKEN: 1,
    CLS_TOKEN: 2,
    SEP_TOKEN: 3,
    MASK_TOKEN: 4,
}

# Regex untuk mengenali token khusus terlebih dahulu, kemudian kata (alphanumeric Unicode), lalu tanda baca
SPECIAL_PATTERN = "|".join(re.escape(tok) for tok in SPECIAL_TOKENS)
TOKEN_REGEX = re.compile(rf"({SPECIAL_PATTERN})|([\w]+)|([^\w\s])", re.IGNORECASE)


class WordLevelTokenizer:
    """
    Tokenizer tingkat kata deterministik tanpa dependensi pretrained eksternal.
    """

    def __init__(
        self,
        vocab: Optional[Dict[str, int]] = None,
        config: Optional[Dict[str, Any]] = None,
    ):
        self.config = config or {}
        self.version = self.config.get("tokenizer_version", TOKENIZER_VERSION)
        self.lowercase = self.config.get("lowercase", True)
        self.max_length = self.config.get("max_length", 64)

        self.pad_token = PAD_TOKEN
        self.unk_token = UNK_TOKEN
        self.cls_token = CLS_TOKEN
        self.sep_token = SEP_TOKEN
        self.mask_token = MASK_TOKEN

        self.pad_token_id = SPECIAL_TOKEN_IDS[PAD_TOKEN]
        self.unk_token_id = SPECIAL_TOKEN_IDS[UNK_TOKEN]
        self.cls_token_id = SPECIAL_TOKEN_IDS[CLS_TOKEN]
        self.sep_token_id = SPECIAL_TOKEN_IDS[SEP_TOKEN]
        self.mask_token_id = SPECIAL_TOKEN_IDS[MASK_TOKEN]

        if vocab is not None:
            self._validate_vocab(vocab)
            self.vocab = dict(vocab)
        else:
            # Default vocab hanya berisi special tokens
            self.vocab = dict(SPECIAL_TOKEN_IDS)

        self.id_to_token = {v: k for k, v in self.vocab.items()}
        if "vocab_sha256" not in self.config and len(self.vocab) > len(SPECIAL_TOKENS):
            sorted_pairs = sorted(self.vocab.items(), key=lambda x: x[1])
            self.config["vocab_sha256"] = hashlib.sha256(
                json.dumps(sorted_pairs, ensure_ascii=False).encode("utf-8")
            ).hexdigest()

    @staticmethod
    def _validate_vocab(vocab: Dict[str, int]) -> None:
        """
        Validasi integritas vocabulary:
        1. ID harus integer non-negatif.
        2. Lima token khusus harus ada dengan ID yang disepakati (0..4).
        3. Seluruh ID harus unik dan kontigu 0..vocab_size-1.
        Tolak artefak tidak valid dengan pesan jelas tanpa diam-diam memperbaiki mapping.
        """
        if not isinstance(vocab, dict) or len(vocab) == 0:
            raise ValueError("Vocabulary harus berupa kamus (dict) non-kosong.")

        # 1. Cek tipe dan non-negativitas
        for token, tid in vocab.items():
            if not isinstance(tid, int) or isinstance(tid, bool) or tid < 0:
                raise ValueError(
                    f"Token '{token}' memiliki ID tidak valid: {tid}. ID harus berupa integer non-negatif."
                )

        # 2. Cek token khusus
        for tok, expected_id in SPECIAL_TOKEN_IDS.items():
            if tok not in vocab:
                raise ValueError(
                    f"Artefak vocabulary tidak valid: Token khusus '{tok}' tidak ditemukan."
                )
            if vocab[tok] != expected_id:
                raise ValueError(
                    f"Artefak vocabulary tidak valid: Token khusus '{tok}' memiliki ID {vocab[tok]}, "
                    f"seharusnya {expected_id}."
                )

        # 3. Cek keunikan dan kontiguitas
        ids = list(vocab.values())
        unique_ids = set(ids)
        if len(ids) != len(unique_ids):
            raise ValueError("Artefak vocabulary tidak valid: Terdapat ID duplikat pada token yang berbeda.")

        expected_ids = set(range(len(vocab)))
        if unique_ids != expected_ids:
            missing_ids = sorted(list(expected_ids - unique_ids))[:5]
            raise ValueError(
                f"Artefak vocabulary tidak valid: ID tidak kontigu 0..{len(vocab)-1}. "
                f"Contoh ID yang hilang: {missing_ids}."
            )

    @property
    def vocab_size(self) -> int:
        return len(self.vocab)

    def normalize(self, text: str) -> str:
        """
        Normalisasi teks:
        1. Unicode NFC (konsisten dengan cleaner).
        2. Normalisasi kutipan dan apostrof tipografis ke representasi standar ASCII.
        """
        if not text:
            return ""
        text = unicodedata.normalize("NFC", text)
        # Normalisasi kutipan tipografis
        text = text.replace("’", "'").replace("‘", "'").replace("“", '"').replace("”", '"')
        return text

    def tokenize(self, text: str) -> List[str]:
        """
        Memecah teks menjadi daftar token:
        - Mengenali token khusus [PAD], [UNK], [CLS], [SEP], [MASK] secara utuh (tidak dipecah / tidak di-lowercase).
        - Memecah tanda baca sebagai token individual.
        - Tanda hubung '-' dipisahkan (misal: 'anak-anak' -> ['anak', '-', 'anak']).
        - Angka dipertahankan sebagai token alfanumerik.
        - Huruf biasa dinormalisasi ke lowercase (jika self.lowercase=True).
        """
        text = self.normalize(text)
        if not text:
            return []

        tokens: List[str] = []
        for match in TOKEN_REGEX.finditer(text):
            special, word, punct = match.groups()
            if special:
                # Token khusus selalu dipetakan ke uppercase kanonikal
                tokens.append(special.upper())
            elif word:
                tokens.append(word.lower() if self.lowercase else word)
            elif punct:
                tokens.append(punct)
        return tokens

    def convert_tokens_to_ids(self, tokens: List[str]) -> List[int]:
        """Konversi daftar token menjadi token ID. Token yang tidak ada di vocab menjadi UNK (ID=1)."""
        return [self.vocab.get(tok, self.unk_token_id) for tok in tokens]

    def convert_ids_to_tokens(self, ids: List[int]) -> List[str]:
        """Konversi daftar token ID menjadi daftar token string. Menolak ID tidak valid."""
        tokens = []
        for tid in ids:
            if not isinstance(tid, int) or tid < 0 or tid not in self.id_to_token:
                raise ValueError(
                    f"Token ID tidak valid: {tid}. ID harus berupa integer antara 0 dan {self.vocab_size - 1}."
                )
            tokens.append(self.id_to_token[tid])
        return tokens

    def encode(
        self,
        text: str,
        add_special_tokens: bool = True,
        max_length: Optional[int] = None,
        padding: bool = True,
        truncation: bool = True,
    ) -> Dict[str, List[int]]:
        """
        Melakukan tokenisasi dan encoding teks menjadi input_ids dan attention_mask.
        - Jika add_special_tokens=True: menambahkan [CLS] di awal dan [SEP] di akhir.
        - Jika truncation=True: membatasi panjang total tepat max_length (termasuk [CLS] dan [SEP]).
        - Jika padding=True: menambahkan [PAD]=0 hingga panjang tepat max_length.
        - attention_mask bernilai 1 pada token nyata dan 0 pada padding.
        """
        limit = max_length if max_length is not None else self.max_length
        if add_special_tokens and limit < 2:
            raise ValueError(
                f"max_length={limit} tidak valid. Dibutuhkan minimal 2 ketika add_special_tokens=True untuk menampung [CLS] dan [SEP]."
            )
        raw_tokens = self.tokenize(text)

        if add_special_tokens:
            content_limit = max(0, limit - 2) if truncation else len(raw_tokens)
            content_tokens = raw_tokens[:content_limit] if truncation else raw_tokens
            tokens = [self.cls_token] + content_tokens + [self.sep_token]
        else:
            tokens = raw_tokens[:limit] if truncation else raw_tokens

        input_ids = self.convert_tokens_to_ids(tokens)
        attention_mask = [1] * len(input_ids)

        if padding and len(input_ids) < limit:
            pad_len = limit - len(input_ids)
            input_ids.extend([self.pad_token_id] * pad_len)
            attention_mask.extend([0] * pad_len)

        return {
            "input_ids": input_ids,
            "attention_mask": attention_mask,
        }

    def decode(
        self,
        token_ids: List[int],
        skip_special_tokens: bool = False,
    ) -> str:
        """
        Mengonversi daftar token ID kembali menjadi teks string.
        Keterbatasan dan normalisasi:
        - Decode menggabungkan token dengan spasi.
        - Teks hasil decode berhuruf kecil (lowercase) untuk kata biasa.
        - Tanda baca yang sebelumnya dipisah mungkin memiliki spasi sebelumnya (misal: 'halo , dunia !').
        - Token yang menjadi [UNK] tidak dapat dipulihkan ke kata aslinya.
        """
        tokens = self.convert_ids_to_tokens(token_ids)
        if skip_special_tokens:
            tokens = [t for t in tokens if t not in SPECIAL_TOKENS]

        # Penggabungan dasar dengan spasi
        return " ".join(tokens)

    def save_pretrained(self, save_directory: str) -> Dict[str, str]:
        """
        Menyimpan artefak vocabulary dan konfigurasi ke direktori tujuan:
        - vocab.json
        - tokenizer_config.json
        """
        os.makedirs(save_directory, exist_ok=True)

        vocab_path = os.path.join(save_directory, "vocab.json")
        with open(vocab_path, "w", encoding="utf-8") as f:
            json.dump(self.vocab, f, indent=2, ensure_ascii=False)

        # Pertahankan seluruh metadata config yang ada (termasuk vocab_sha256)
        config_data = dict(self.config)
        config_data.update({
            "tokenizer_class": "WordLevelTokenizer",
            "tokenizer_version": self.version,
            "vocab_size": self.vocab_size,
            "lowercase": self.lowercase,
            "max_length": self.max_length,
            "special_tokens": {
                "pad_token": {"token": self.pad_token, "id": self.pad_token_id},
                "unk_token": {"token": self.unk_token, "id": self.unk_token_id},
                "cls_token": {"token": self.cls_token, "id": self.cls_token_id},
                "sep_token": {"token": self.sep_token, "id": self.sep_token_id},
                "mask_token": {"token": self.mask_token, "id": self.mask_token_id},
            },
            "tokenization_rules": {
                "unicode_normalization": "NFC",
                "special_token_protection": True,
                "split_punctuation": True,
                "hyphen_handling": "split_as_punctuation",
                "apostrophe_handling": "normalized_and_split",
                "number_handling": "retained_as_alphanumeric_word",
                "stemming": False,
                "stopword_removal": False
            }
        })

        config_path = os.path.join(save_directory, "tokenizer_config.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)

        return {"vocab_path": vocab_path, "config_path": config_path}

    @classmethod
    def from_pretrained(cls, load_directory: str) -> "WordLevelTokenizer":
        """
        Memuat tokenizer dari direktori penyimpanan artefak.
        """
        vocab_path = os.path.join(load_directory, "vocab.json")
        config_path = os.path.join(load_directory, "tokenizer_config.json")

        if not os.path.exists(vocab_path):
            raise FileNotFoundError(f"Berkas vocabulary '{vocab_path}' tidak ditemukan.")

        with open(vocab_path, "r", encoding="utf-8") as f:
            vocab = json.load(f)

        config = {}
        if os.path.exists(config_path):
            with open(config_path, "r", encoding="utf-8") as f:
                config = json.load(f)

        return cls(vocab=vocab, config=config)
