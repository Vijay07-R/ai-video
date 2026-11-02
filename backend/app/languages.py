"""Supported narration / subtitle languages and everything language-specific:
native script ranges (used to validate generated text), natural speaking rate,
subtitle fonts and writing guidance for the story model."""
from __future__ import annotations

import platform
import re
import unicodedata
from dataclasses import dataclass
from pathlib import Path

from .config import BASE_DIR

FONT_DIR = BASE_DIR / "fonts"


@dataclass(frozen=True)
class Language:
    code: str
    name: str
    native: str
    script: str               # Unicode block name, for validation
    script_range: tuple[int, int] | None
    words_per_s: float        # comfortable narration pace
    font: str                 # bundled Noto font family (backend/fonts)
    windows_font: str
    guidance: str


LANGUAGES: dict[str, Language] = {
    "en": Language("en", "English", "English", "Latin", None, 2.4, "Noto Sans", "Arial",
                   "Write in simple, warm, natural English suitable for a family audience."),
    "ta": Language("ta", "Tamil", "தமிழ்", "Tamil", (0x0B80, 0x0BFF), 1.5, "Noto Sans Tamil", "Nirmala UI",
                   "Write ORIGINALLY in Tamil (do not translate from English in your head). Use clear, natural Tamil as heard "
                   "in Tamil children's stories and TV narration: short sentences, everyday words, correct sandhi and spelling. "
                   "Avoid stiff literal translations, avoid heavy classical vocabulary, and do not mix English words in Latin "
                   "letters. Dialogue should sound like real spoken Tamil while staying easy to understand."),
    "te": Language("te", "Telugu", "తెలుగు", "Telugu", (0x0C00, 0x0C7F), 1.6, "Noto Sans Telugu", "Nirmala UI",
                   "Write ORIGINALLY in Telugu. Use clear, natural, conversational Telugu as used in Telugu children's "
                   "stories and narration: short sentences, common words, correct spelling. No literal translation, no "
                   "English words in Latin letters."),
    "hi": Language("hi", "Hindi", "हिन्दी", "Devanagari", (0x0900, 0x097F), 2.1, "Noto Sans Devanagari", "Nirmala UI",
                   "Write ORIGINALLY in Hindi in Devanagari script. Use simple, natural everyday Hindi (Hindustani) as used "
                   "in children's stories and TV narration; avoid overly Sanskritised words and literal translation; no "
                   "English words in Latin letters."),
}
SUPPORTED = list(LANGUAGES)


def get(code: str) -> Language:
    return LANGUAGES.get((code or "en").lower(), LANGUAGES["en"])




def script_share(text: str, lang: str) -> float:
    """Fraction of letters that are in the language's native script (1.0 for English)."""
    L = get(lang)
    # letters AND combining marks (Indic vowel signs / virama are marks, not letters)
    letters = [c for c in text if unicodedata.category(c)[0] in "LM"]
    if not letters:
        return 1.0
    if L.script_range is None:
        return sum(1 for c in letters if ord(c) < 0x250) / len(letters)
    lo, hi = L.script_range
    return sum(1 for c in letters if lo <= ord(c) <= hi) / len(letters)


def subtitle_font(lang: str) -> tuple[str, Path]:
    """Font family name + directory for FFmpeg/libass. Bundled Noto fonts work on every OS."""
    L = get(lang)
    if (FONT_DIR / f"{L.font.replace(' ', '')}-Regular.ttf").exists():
        return L.font, FONT_DIR
    return (L.windows_font if platform.system() == "Windows" else L.font), FONT_DIR


def split_cues(text: str, max_chars: int = 42) -> list[str]:
    """Split narration into short subtitle cues at sentence / clause boundaries."""
    text = " ".join(text.split())
    if not text:
        return []
    parts = re.split(r"(?<=[.!?।॥,;:])\s+", text)
    cues, cur = [], ""
    for p in parts:
        if not cur:
            cur = p
        elif len(cur) + 1 + len(p) <= max_chars:
            cur += " " + p
        else:
            cues.append(cur)
            cur = p
    if cur:
        cues.append(cur)
    out = []  # hard-wrap anything still too long at word boundaries
    for c in cues:
        while len(c) > max_chars * 1.6:
            cut = c.rfind(" ", 0, max_chars)
            cut = cut if cut > 0 else max_chars
            out.append(c[:cut].strip())
            c = c[cut:].strip()
        out.append(c)
    return out
