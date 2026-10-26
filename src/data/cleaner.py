"""
Modul Cleaner Konservatif untuk Korpus Teks Wikipedia Bahasa Indonesia.
Versi 1.1.0:
- Penanganan pra-normalisasi line ending (\\r\\n, \\r) dan whitespace sebelum deteksi heading.
- Parsing template bersarang berbasis stack (single pass, independen dari kedalaman, aman terhadap template tak tertutup).
- Preservasi tanda baca saat pembersihan URL.
- Idempotensi teruji pada seluruh variasi line ending, tab, dan kedalaman template.
"""

import re
import sys
import unicodedata
from typing import Dict, Any, Tuple, Optional, List

CLEANER_VERSION = "1.1.0"

DEFAULT_CLEANING_CONFIG = {
    "normalize_unicode_nfc": True,
    "strip_control_chars": True,
    "clean_html_and_ref_tags": True,
    "clean_wiki_templates": True,
    "expand_wiki_links": True,
    "remove_urls_in_body": True,
    "truncate_boilerplate_sections": True,
    "normalize_whitespace": True
}

# Regex untuk karakter kontrol (kecuali newline \n dan tab \t)
RE_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")

# Regex untuk URL (mendukung http/https dan www)
RE_URL = re.compile(r"(?i)\b(?:https?://|www\.)[^\s<>\"']+")

# Regex untuk heading terminal (harus berada pada baris tersendiri, mendukung spasi & tab)
RE_BOILERPLATE_HEADING = re.compile(
    r"(?im)^[\t ]*(?:={2,}[\t ]*)?(?:Referensi|Pranala luar|Lihat pula|Catatan kaki|Daftar pustaka|Bacaan lanjutan)(?:[\t ]*={2,})?[\t ]*$"
)

# Regex untuk tag referensi spesifik (<ref>...</ref> atau <ref ... />)
RE_REF_PAIRS = re.compile(r"(?is)<ref\b[^>]*>.*?</ref>")
RE_REF_SELF_CLOSING = re.compile(r"(?is)<ref\b[^>]*/>")
RE_REF_ORPHAN_CLOSE = re.compile(r"(?i)</ref>")

# Regex untuk komentar HTML <!-- ... -->
RE_HTML_COMMENTS = re.compile(r"(?s)<!--.*?-->")

# Regex untuk tag HTML format/tata letak aman yang di-strip (teks di dalamnya dipertahankan)
RE_SAFE_TAGS = re.compile(
    r"(?i)</?(?:p|div|span|br|sup|sub|small|b|i|u|strong|em|table|tr|td|th|tbody|thead|tfoot|caption|ul|ol|li|dl|dt|dd|center|font|h[1-6])\b[^>]*>"
)

# Regex untuk tautan berkas / media / kategori Wikipedia
RE_WIKI_MEDIA_LINKS = re.compile(r"(?i)\[\[(?:Berkas|File|Kategori|Category):[^\]]+\]\]")

# Regex untuk tautan wiki standar [[Target|Display]] atau [[Target]]
RE_WIKI_LINK_PIPED = re.compile(r"\[\[([^|\]\n]+)\|([^\]\n]+)\]\]")
RE_WIKI_LINK_SIMPLE = re.compile(r"\[\[([^|\]\n]+)\]\]")


def normalize_unicode(text: str) -> str:
    """Normalisasi Unicode ke bentuk komposit baku (NFC)."""
    return unicodedata.normalize("NFC", text)


def strip_control_characters(text: str) -> str:
    """Menghapus karakter kontrol sistem/biner yang tidak bermakna."""
    return RE_CONTROL_CHARS.sub("", text)


def pre_normalize_line_endings_and_spaces(text: str) -> str:
    """
    Pra-normalisasi line ending (\r\n -> \n) dan karakter spasi khusus (NBSP dsb.)
    sebelum deteksi heading agar pola multiline regex (^ dan $) bekerja deterministik.
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\u00a0\u2000-\u200b\u202f\u205f\u3000]", " ", text)
    return text


def clean_html_markup(text: str) -> str:
    """
    Membersihkan tag referensi dan tag tata letak HTML secara selektif.
    Tidak menggunakan regex rakus <[^>]+> agar tidak merusak contoh kode pembanding (misal: '<-').
    """
    text = RE_HTML_COMMENTS.sub("", text)
    text = RE_REF_PAIRS.sub("", text)
    text = RE_REF_SELF_CLOSING.sub("", text)
    text = RE_REF_ORPHAN_CLOSE.sub("", text)
    text = RE_SAFE_TAGS.sub(" ", text)
    return text


def clean_wiki_templates_stack(text: str) -> str:
    """
    Menghapus template Wikipedia {{...}} menggunakan algoritma tumpukan (stack) satu lintasan (single pass).
    - Mendukung kedalaman bersarang sembarang tanpa batasan iterasi (O(N)).
    - Tidak merusak teks di sekitar template yang tidak lengkap/tidak tertutup.
    """
    stack = []
    remove_spans = []
    i = 0
    n = len(text)

    while i < n - 1:
        if text[i:i + 2] == "{{":
            stack.append(i)
            i += 2
        elif text[i:i + 2] == "}}":
            if stack:
                start = stack.pop()
                # Jika tumpukan kembali kosong, kita menemukan batas terluar template tertutup
                if len(stack) == 0:
                    remove_spans.append((start, i + 2))
            i += 2
        else:
            i += 1

    if not remove_spans:
        return text

    # Rekonstruksi teks tanpa rentang template tertutup terluar
    result = []
    last_idx = 0
    for start, end in remove_spans:
        result.append(text[last_idx:start])
        last_idx = end
    result.append(text[last_idx:])
    return "".join(result)


def expand_wiki_links(text: str) -> str:
    """
    Menguraikan tautan internal Wikipedia [[Target|Anchor]] -> Anchor
    dan [[Target]] -> Target, serta menghapus tag Berkas/Kategori.
    """
    text = RE_WIKI_MEDIA_LINKS.sub("", text)
    text = RE_WIKI_LINK_PIPED.sub(r"\2", text)
    text = RE_WIKI_LINK_SIMPLE.sub(r"\1", text)
    return text


def remove_urls_conservatively(text: str) -> str:
    """
    Menghapus URL di badan teks dengan tetap mempertahankan tanda baca kalimat
    yang menempel di ujung URL (seperti titik atau koma).
    """
    def _url_replacer(match: re.Match) -> str:
        url_str = match.group(0)
        trailing_punct = ""
        while url_str and url_str[-1] in ".,;:!?)'\"":
            trailing_punct = url_str[-1] + trailing_punct
            url_str = url_str[:-1]
        return trailing_punct

    return RE_URL.sub(_url_replacer, text)


def truncate_boilerplate_sections(text: str) -> Tuple[str, Optional[Dict[str, str]]]:
    """
    Memotong seksi penutup standar Wikipedia (Referensi, Pranala luar, Lihat pula)
    hanya jika heading muncul sebagai baris mandiri.
    Mengembalikan (truncated_text, context_info).
    """
    match = RE_BOILERPLATE_HEADING.search(text)
    if match:
        start_pos = match.start()
        # Ambil konteks di sekitar pemotongan
        ctx_before = text[max(0, start_pos - 80):start_pos].strip()
        matched_heading = match.group(0).strip()
        ctx_after = text[match.end():min(len(text), match.end() + 80)].strip()
        context_info = {
            "matched_heading": matched_heading,
            "text_before_cut": ctx_before,
            "text_after_cut": ctx_after
        }
        return text[:start_pos], context_info
    return text, None


def normalize_whitespace(text: str) -> str:
    """
    Merapikan spasi berlebih pada tiap baris dan membatasi jeda paragraf maksimal 2 newline (\n\n).
    """
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[\u00a0\u2000-\u200b\u202f\u205f\u3000]", " ", text)
    text = text.replace("\t", " ")

    lines = []
    for line in text.split("\n"):
        cleaned_line = re.sub(r" +", " ", line).strip()
        lines.append(cleaned_line)

    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_text(text: str, config: Optional[Dict[str, Any]] = None) -> Tuple[str, Dict[str, Any]]:
    """
    Fungsi utama pipeline pembersihan teks Wikipedia secara konservatif.
    Mengembalikan (cleaned_text, rule_actions_log).
    """
    cfg = DEFAULT_CLEANING_CONFIG.copy()
    if config:
        cfg.update(config)

    actions = {}
    current = text

    # 1. Normalisasi Unicode NFC
    if cfg.get("normalize_unicode_nfc"):
        before = current
        current = normalize_unicode(current)
        actions["unicode_normalized"] = (before != current)

    # 2. Hapus Karakter Kontrol
    if cfg.get("strip_control_chars"):
        before = current
        current = strip_control_characters(current)
        actions["control_chars_stripped"] = (before != current)

    # 3. Pra-normalisasi line ending & whitespace horizontal untuk kestabilan heading regex
    current = pre_normalize_line_endings_and_spaces(current)

    # 4. Potong Seksi Boilerplate (Heading Mandiri)
    if cfg.get("truncate_boilerplate_sections"):
        before = current
        current, cut_context = truncate_boilerplate_sections(current)
        actions["boilerplate_truncated"] = (before != current)
        if cut_context:
            actions["cut_context"] = cut_context

    # 5. Bersihkan Template Wiki {{...}} via Stack tunggal
    if cfg.get("clean_wiki_templates"):
        before = current
        current = clean_wiki_templates_stack(current)
        actions["wiki_templates_cleaned"] = (before != current)

    # 6. Uraikan Tautan Wiki [[...]]
    if cfg.get("expand_wiki_links"):
        before = current
        current = expand_wiki_links(current)
        actions["wiki_links_expanded"] = (before != current)

    # 7. Bersihkan Tag HTML/Ref Spesifik
    if cfg.get("clean_html_and_ref_tags"):
        before = current
        current = clean_html_markup(current)
        actions["html_and_ref_cleaned"] = (before != current)

    # 8. Hapus URL di Badan Teks
    if cfg.get("remove_urls_in_body"):
        before = current
        current = remove_urls_conservatively(current)
        actions["urls_removed"] = (before != current)

    # 9. Normalisasi Whitespace & Paragraf Akhir
    if cfg.get("normalize_whitespace"):
        before = current
        current = normalize_whitespace(current)
        actions["whitespace_normalized"] = (before != current)

    return current, actions
