"""Forgiving text matching for spoken names.

Callers speak, and speech-to-text mishears names ("Dr. Garsha" for Garcia,
"Farhan Jida"). Two cheap, dependency-free checks decide whether two words are
"the same name":

1. Spelling similarity (difflib ratio) of at least 0.8, or
2. Same Soundex code: a classic "sounds alike" key (Garcia and Garsha are both G620).

Standard library only, so it runs anywhere the bot runs.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

TITLE_WORDS = {"dr", "doctor", "doc", "mr", "mrs", "ms", "miss", "md", "do", "np", "pa"}


def normalize(text: str) -> str:
    """Lowercase, strip accents and punctuation, collapse spaces."""
    text = unicodedata.normalize("NFKD", text or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^a-z0-9 ]+", " ", text.lower())
    return re.sub(r"\s+", " ", text).strip()


def name_tokens(text: str) -> list[str]:
    """Words of a person's name, without titles like 'Dr.'."""
    return [t for t in normalize(text).split() if t not in TITLE_WORDS]


def soundex(word: str) -> str:
    word = normalize(word).replace(" ", "")
    if not word:
        return ""
    codes = {
        **dict.fromkeys("bfpv", "1"),
        **dict.fromkeys("cgjkqsxz", "2"),
        **dict.fromkeys("dt", "3"),
        "l": "4",
        **dict.fromkeys("mn", "5"),
        "r": "6",
    }
    first = word[0]
    out = [first.upper()]
    prev = codes.get(first, "")
    for ch in word[1:]:
        code = codes.get(ch, "")
        if code and code != prev:
            out.append(code)
        if ch not in "hw":  # h and w don't break a run of the same code
            prev = code
    return ("".join(out) + "000")[:4]


def similarity(a: str, b: str) -> float:
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def word_match(heard: str, actual: str) -> float:
    """How well one heard word matches one real word: 1.0 exact, 0.85 close, 0 no."""
    h, a = normalize(heard), normalize(actual)
    if not h or not a:
        return 0.0
    if h == a:
        return 1.0
    if similarity(h, a) >= 0.8 or (len(h) >= 3 and soundex(h) == soundex(a)):
        return 0.85
    return 0.0


def person_name_score(heard: str, full_name: str) -> float:
    """Score how well a heard person name matches a real full name (0 to 1).

    The surname carries the match. A first name, if heard, must also match;
    a single heard word may be either the surname or the first name.
    """
    heard_t = name_tokens(heard)
    real_t = name_tokens(full_name)
    if not heard_t or not real_t:
        return 0.0
    real_first, real_last = real_t[0], real_t[-1]

    if len(heard_t) == 1:
        last = word_match(heard_t[0], real_last)
        if last:
            return last
        # Only a first name heard ("Dr. Maria"): weaker match.
        return 0.6 * word_match(heard_t[0], real_first)

    heard_first, heard_last = heard_t[0], heard_t[-1]
    last = word_match(heard_last, real_last)
    first = word_match(heard_first, real_first)
    if last and first:
        return (last + first) / 2
    return 0.0
