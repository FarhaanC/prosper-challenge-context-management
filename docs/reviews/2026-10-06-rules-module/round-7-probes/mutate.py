"""Checks that the new round-7 tests can fail: makes one small change at a time to a COPY
of the code, runs the round-7 test files against it, and reports how many tests fail.
Run from this folder: python3 mutate.py"""
import shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC = HERE.parent / "work" / "backend"
MUTANTS = [
    ("near not reset on carry-over", "card.py",
     'prefs.preferred_location_id, prefs.location_hint, prefs.near = c.location_id, "", False',
     'prefs.preferred_location_id, prefs.location_hint = c.location_id, ""'),
    ("near ignored: always restrict", "options.py",
     'if place.kind == "location" and not place.near:', 'if place.kind == "location":'),
    ("near refused check removed", "card.py",
     'if near and kind != LOCATION:', 'if False:'),
    ("summary drops near", "card.py", "{'near ' if p.near else ''}", ""),
    ("four names read", "options.py", "NAMES_TO_READ = 3", "NAMES_TO_READ = 4"),
    ("'one' read as filler again", "catalog.py", '"care", "community", "the",', '"care", "community", "the", "one",'),
    ("'frid' accepted", "options.py", '"fri": 4,', '"fri": 4, "frid": 4,'),
    ("answer_question guard removed", "facts.py", 'if about in ("location", "doctor") and looks_like_a_sentence(name):',
     'if False:'),
    ("repeat reported per copy", "catalog.py", "if rid and rid in seen and rid not in repeated:", "if rid and rid in seen:"),
    ("language guessed from two words", "options.py", "or any(w in spoken for w in parts)):", "):"),
    ("no-preference stored as said", "card.py", "        if means_no_preference(said):\n            said = \"\"\n", ""),
    ("same-name note uncapped", "options.py", '+ _a_few(desc, "; ") +', '+ "; ".join(desc) +'),
    ("landmark honours near=False", "catalog.py", 'return PlaceMatch(kind="landmark", label=name, point=point, near=True)',
     'return PlaceMatch(kind="landmark", label=name, point=point, near=False)'),
]
for label, file, old, new in MUTANTS:
    dst = HERE / "mut"
    shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(SRC, dst / "backend", ignore=shutil.ignore_patterns("__pycache__", "tests"))
    f = dst / "backend" / "clinic" / file
    text = f.read_text()
    assert text.count(old) == 1, (label, text.count(old))
    f.write_text(text.replace(old, new))
    lines = subprocess.run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider",
                            "tests_independent/test_round7_places.py", "tests_independent/test_round7_values.py",
                            "tests_independent/test_round7_notes.py"],
                           cwd=dst / "backend", capture_output=True, text=True).stdout.splitlines()
    print(f"{label:40} {next(l for l in reversed(lines) if ' passed' in l)}   (unchanged code: 22 failed)")
shutil.rmtree(HERE / "mut", ignore_errors=True)
