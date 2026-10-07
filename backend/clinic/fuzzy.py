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
from dataclasses import dataclass
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

# Words that are part of how a name is said but not part of the name itself.
# (Degree letters like "MD" or "DO" are left out on purpose: "Do" is a common
# Vietnamese surname, and the catalog keeps degrees in a separate field.)
TITLE_WORDS = {"dr", "doctor", "doc", "mr", "mrs", "ms", "miss", "mx",
               "jr", "junior", "sr", "senior", "ii", "iii", "iv"}

# Ways of saying "no preference", written with spaces and apostrophes removed
# (compare with `squash(text)`). The one list, shared by every kind of wish: the
# value counts as empty, the same as "". That is the only reading the code does of
# these words; it never works out anything else from them.
NO_PREFERENCE = {
    "any", "anything", "anytime", "anywhere", "anyone", "anybody", "anyday", "anydate",
    "nopreference", "dontmind", "idontmind", "doesntmatter", "itdoesntmatter", "whatever",
    "whenever", "wherever", "whoever", "either", "eitherisfine", "notfussed", "none", "no",
    "anyisfine", "anyofthem", "anywhereisfine", "anywhereisok", "anytimeisfine", "anytimeworks",
    "anydayisfine", "anydayworks",
}

# Words that show a value is a sentence or an instruction, not a name: "not Dr. Chen",
# "another doctor", "anyone but Dr. Kim", "Dr. Chen please". The AI is asked to pass
# bare names; this list only catches its mistakes, so they're refused instead of being
# matched to a doctor or language by spelling. It is never used to work out what was meant.
NOT_NAME_WORDS = {"not", "but", "except", "without", "another", "other", "else", "someone", "somebody",
                  "anyone", "anybody", "different", "instead", "please"}


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


def squash(text) -> str:
    """Lowercase letters and digits only: "I don't mind!" -> "idontmind"."""
    return re.sub(r"[^a-z0-9]", "", str(text or "").lower())


def means_no_preference(text) -> bool:
    return squash(text) in NO_PREFERENCE


def looks_like_a_sentence(text) -> bool:
    """True if the value has a word no name has ("not Dr. Chen"). See NOT_NAME_WORDS."""
    return bool(set(normalize(text).split()) & NOT_NAME_WORDS)


def name_tokens(text) -> list:
    """Words of a person's name, without titles like 'Dr.' or 'Mr.' or endings like 'Jr'."""
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


@dataclass(frozen=True, order=True)
class NameRank:
    """How strongly a heard name matches a real one. Compared field by field, so a
    bigger value in an earlier field always wins:

    whole_name  1 if every word the caller said matched (0 = surname-only fallback)
    quality     the weakest word quality in the match (EXACT, CLOSE, SOUNDS_LIKE, NONE)
    by_surname  1 if the match is on the surname (preferred over a first name at equal quality)
    """

    whole_name: int
    quality: int
    by_surname: int


NO_MATCH = NameRank(0, NONE, 0)


def person_match(heard, full_name: str, allow_sounds_like: bool = True, close_at: float = CLOSE_SPELLING) -> NameRank:
    """Compare a heard person name with a real full name. NO_MATCH if they don't match.

    - Two or more words heard: first and last word must both match ("Maria Garcia").
      If only the surname matches, it's a weaker fallback ("Dr. John Garcia" finds the
      Garcias with whole_name=0, so the agent can say there's no Dr. John Garcia).
    - One word heard: it may be a surname or a first name ("Dr. Chen", "Dr. Grace").
      The better match counts, so an exact first name beats a sounds-alike surname. At
      equal quality the surname wins: "Garsha" sounds like both Garcia and Grace, and
      callers name doctors by surname.
    """
    heard_t = name_tokens(heard)
    real_t = name_tokens(full_name)
    if not heard_t or not real_t:
        return NO_MATCH
    real_first, real_last = real_t[0], real_t[-1]

    if len(heard_t) == 1:
        as_last = word_quality(heard_t[0], real_last, allow_sounds_like, close_at)
        as_first = word_quality(heard_t[0], real_first, allow_sounds_like, close_at)
        if as_last and as_last >= as_first:
            return NameRank(1, as_last, 1)
        return NameRank(1, as_first, 0) if as_first else NO_MATCH

    first = word_quality(heard_t[0], real_first, allow_sounds_like, close_at)
    last = word_quality(heard_t[-1], real_last, allow_sounds_like, close_at)
    if first and last:
        return NameRank(1, min(first, last), 1)
    if last:
        return NameRank(0, last, 1)
    return NO_MATCH


def letters_apart(a: str, b: str) -> int:
    """How many single-letter changes (add, remove or swap one letter) turn a into b.
    Used for names the caller spelled out: 'BRAWN' is 1 letter from 'BROWN'."""
    a, b = normalize(a).replace(" ", ""), normalize(b).replace(" ", "")
    row = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        prev, row[0] = row[0], i
        for j, cb in enumerate(b, 1):
            prev, row[j] = row[j], min(row[j] + 1, row[j - 1] + 1, prev + (ca != cb))
    return row[-1]
