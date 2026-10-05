"""Forgiving matching for spoken names, which also says how sure it is.

Callers speak, and speech-to-text mishears names ("Dr. Garsha" for Garcia).
Each heard word is compared with a real word and given a quality:

    EXACT        the same word once case, accents and punctuation are ignored
    CLOSE        spelled at least 80% alike ("Ramires" / "Ramirez")
    SOUNDS_LIKE  same Soundex code, a classic "sounds alike" key
                 (Garcia and Garsha are both G620); only for words of 3+ letters
    NONE         no match

Callers of this module decide how much doubt they accept. Doctor search accepts
SOUNDS_LIKE but reports it, so the agent can say "I don't have a Dr. Cohen; did
you mean Dr. Chen?". Patient lookup accepts at most CLOSE spelling, because a
wrong match there would hand out someone else's medical record.

Standard library only.
"""

from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher
from functools import lru_cache

# Match qualities, best first. Plain integers so they can be compared and ranked.
EXACT, CLOSE, SOUNDS_LIKE, NONE = 3, 2, 1, 0
QUALITY_NAMES = {EXACT: "exact", CLOSE: "close spelling", SOUNDS_LIKE: "sounds alike", NONE: "none"}

# Spelling similarity (0 to 1) at which two words count as CLOSE. 0.8 accepts
# one wrong letter in a 5-letter name ("Smyth"/"Smith") and rejects different
# names that share letters ("Kim"/"Khan" is 0.29).
CLOSE_SPELLING = 0.8
# Soundex codes are crude for very short words ("Li" and "Lee"), so only use them from 3 letters.
SOUNDEX_MIN_LETTERS = 3

TITLE_WORDS = {"dr", "doctor", "doc", "mr", "mrs", "ms", "miss", "mx", "md", "do", "np", "pa"}


@lru_cache(maxsize=50_000)  # the same catalog names are compared on every search
def _normalize(text: str) -> str:
    """Lowercase, strip accents, a possessive "'s", and punctuation; collapse spaces."""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"['’]s\b", "", text.lower())  # "Garcia's" -> "garcia"
    text = re.sub(r"[^a-z0-9 ]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def normalize(text) -> str:
    """Lowercase, strip accents, a possessive "'s", and punctuation; collapse spaces."""
    return _normalize(str(text or ""))


def name_tokens(text) -> list:
    """Words of a person's name, without titles like 'Dr.' or 'Mr.'."""
    return [t for t in normalize(text).split() if t not in TITLE_WORDS]


@lru_cache(maxsize=50_000)
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
    out = [word[0].upper()]
    prev = codes.get(word[0], "")
    for ch in word[1:]:
        code = codes.get(ch, "")
        if code and code != prev:
            out.append(code)
        if ch not in "hw":  # h and w don't break a run of the same code
            prev = code
    return ("".join(out) + "000")[:4]


@lru_cache(maxsize=200_000)
def similarity(a: str, b: str) -> float:
    """Spelling similarity from 0 (nothing alike) to 1 (identical)."""
    return SequenceMatcher(None, normalize(a), normalize(b)).ratio()


def word_quality(heard: str, actual: str, allow_sounds_like: bool = True, close_at: float = CLOSE_SPELLING) -> int:
    """How well one heard word matches one real word (EXACT, CLOSE, SOUNDS_LIKE or NONE).
    `close_at` is the spelling similarity that counts as CLOSE."""
    h, a = normalize(heard), normalize(actual)
    if not h or not a:
        return NONE
    if h == a:
        return EXACT
    if similarity(h, a) >= close_at:
        return CLOSE
    if allow_sounds_like and len(h) >= SOUNDEX_MIN_LETTERS and soundex(h) == soundex(a):
        return SOUNDS_LIKE
    return NONE


def person_match(heard, full_name: str, allow_sounds_like: bool = True, close_at: float = CLOSE_SPELLING) -> tuple:
    """Compare a heard person name with a real full name.

    Returns (rank, quality, first_name_matched):
    - rank: higher is better, 0 means no match. Matching the full heard name
      always outranks matching only part of it.
    - quality: the weakest word quality in the match (EXACT, CLOSE, SOUNDS_LIKE).
    - first_name_matched: False when the caller gave a first name that matched
      nobody, and we fell back to the surname alone ("Dr. John Garcia" -> the Garcias).

    One heard word may be a surname or a first name ("Dr. Chen", "Dr. Grace"); the
    better match counts, so an exact first name beats a sounds-alike surname. At equal
    quality the surname wins: "Garsha" sounds like both Garcia and Grace, and callers
    name doctors by surname.
    """
    heard_t = name_tokens(heard)
    real_t = name_tokens(full_name)
    if not heard_t or not real_t:
        return (0, NONE, False)
    real_first, real_last = real_t[0], real_t[-1]

    if len(heard_t) == 1:
        as_last = word_quality(heard_t[0], real_last, allow_sounds_like, close_at)
        as_first = word_quality(heard_t[0], real_first, allow_sounds_like, close_at)
        if as_last >= as_first and as_last:
            return (as_last * 10 + 1, as_last, True)
        return (as_first * 10, as_first, True) if as_first else (0, NONE, False)

    first = word_quality(heard_t[0], real_first, allow_sounds_like, close_at)
    last = word_quality(heard_t[-1], real_last, allow_sounds_like, close_at)
    if first and last:
        q = min(first, last)
        return (q * 10, q, True)
    if last:
        # Surname matches but the first name doesn't: a weak, clearly-labelled fallback.
        return (last, last, False)
    return (0, NONE, False)
