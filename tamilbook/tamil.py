"""Tamil Unicode helpers: normalisation, tokenising, sanity checks."""
from __future__ import annotations

import re
import unicodedata

TAMIL_DIGITS = "௦௧௨௩௪௫௬௭௮௯"
_DIGIT_CLASS = "0-9" + TAMIL_DIGITS

# Dependent vowel signs + pulli (virama). These must follow a consonant.
_DEPENDENT = set(range(0x0BBE, 0x0BCE)) | {0x0BD7}
_CONSONANTS = range(0x0B95, 0x0BBA)

# Word characters: Unicode letters/digits plus the whole Tamil block
# (Python's \w does not match combining vowel signs) and ZWJ/ZWNJ.
WORD_RE = re.compile(r"[\w\u0B80-\u0BFF\u200c\u200d]+")
DIGITS_RE = re.compile(f"[{_DIGIT_CLASS}]+")
TERMINAL_PUNCT = tuple(".?!:;\"'”’)]»|।")

_INVISIBLE = dict.fromkeys(map(ord, "\u00ad\ufeff\u200b"), None)


def normalize(text: str) -> str:
    """NFC-normalise, drop soft hyphens / zero-width spaces, tidy whitespace."""
    text = unicodedata.normalize("NFC", text).translate(_INVISIBLE)
    text = text.replace("\u0bcd\u200c", "\u0bcd")  # Tesseract adds ZWNJ after pulli
    return re.sub(r"[ \t\u00a0]+", " ", text).strip()


def is_tamil(ch: str) -> bool:
    return "\u0B80" <= ch <= "\u0BFF"


def tamil_ratio(text: str) -> float:
    """Share of letters in the text that are Tamil."""
    letters = [c for c in text if c.isalpha() or is_tamil(c)]
    if not letters:
        return 0.0
    return sum(is_tamil(c) for c in letters) / len(letters)


def legacy_font_score(text: str) -> float:
    """Share of letters in Latin-1 Supplement (À–ÿ etc.).

    Old Tamil PDFs often use non-Unicode fonts (TAM, TAB, Bamini, Vanavil...)
    whose text layer comes out as accented Latin garbage. A high score means
    the text layer can't be trusted and the page should be OCR'd instead.
    """
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return 0.0
    return sum(0x80 <= ord(c) <= 0x24F for c in letters) / len(letters)


def tokens(text: str) -> list[str]:
    """Split text into comparable word tokens (punctuation dropped)."""
    return [t.lower() for t in WORD_RE.findall(normalize(text))]


def has_invalid_sequence(word: str) -> bool:
    """True if a vowel sign / pulli doesn't follow a consonant.

    This is a cheap, reliable signal of OCR errors or legacy-font mojibake.
    """
    prev = None
    for ch in word:
        cp = ord(ch)
        if cp in _DEPENDENT and (prev is None or prev not in _CONSONANTS):
            return True
        prev = cp
    return False


def ends_sentence(text: str) -> bool:
    return text.rstrip().endswith(TERMINAL_PUNCT)


_MIXED_RE = re.compile(r"[\u0B80-\u0BFF][A-Za-z\u00a1-\u024f]|[A-Za-z\u00a1-\u024f][\u0B80-\u0BFF]")


def broken_text_score(text: str) -> float:
    """Share of Tamil-containing words that look corrupted.

    Many Tamil PDFs (exported from Word, InDesign, old DTP software) have a
    text layer that *looks* Tamil but is broken: conjuncts mapped to Latin
    letters ("கிழக்Lப்"), pre-base vowel signs split off on their own ("ெ"),
    missing letters. Copy-paste from these PDFs gives garbage, so we OCR them.
    """
    words = [w for w in text.split() if any(is_tamil(c) for c in w)]
    if not words:
        return 0.0
    bad = sum(1 for w in words if has_invalid_sequence(w) or _MIXED_RE.search(w))
    return bad / len(words)
