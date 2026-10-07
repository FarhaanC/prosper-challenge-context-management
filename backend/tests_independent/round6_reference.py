"""Round 6: my own check of the "Doctors who can" list that the "no other doctor" note
now reuses (spec-changes-round-6.md s5), written from the spec and catalog.json. It
does NOT import anything from the module under test.
"""

import re

from reference import LOC, PROV as PROV_FILE

LABEL = re.compile(r"(?P<name>Dr\. [^(]+?) \((?P<specialty>[^,()]+)(?:, (?P<places>[^()]+))?\)")


def split_doctor_list(text, last_and=True):
    """Cut a written list of doctor labels into its labels. Round 8 s2: a label can hold a
    comma inside its brackets ("Dr. Daniel Chen (Dermatology, Downtown Health Center /
    Richmond Care Center)"), so the list is cut only at ", " OUTSIDE brackets, and only where
    the next label starts with "Dr.". With `last_and`, the final " and " before a "Dr." label
    (outside brackets) is a cut too ("A, B and C" -> A, B, C); without it only commas cut (use
    that for the part before "and N more", so a wrong join there is not hidden)."""
    seps = [", "] + ([" and "] if last_and else [])
    items, depth, start, i = [], 0, 0, 0
    while i < len(text):
        ch = text[i]
        if ch == "(":
            depth += 1
        elif ch == ")":
            depth = max(depth - 1, 0)
        elif depth == 0:
            sep = next((x for x in seps if text.startswith(x, i) and text.startswith("Dr.", i + len(x))), None)
            if sep:
                items.append(text[start:i])
                i += len(sep)
                start = i
                continue
        i += 1
    items.append(text[start:])
    return items


def who_can_problems(names_text, able_ids, prov=None):
    """Round 6 s5: the "no other doctor" list reuses the "Doctors who can" list: up to three
    "Name (Specialty)" labels, then "and N more"; same-name doctors get their locations; the
    labels are joined "A", "A and B", "A, B and C". Checked against catalog.json (or `prov`,
    a list of doctor records by id, for a test catalog)."""
    PROV = prov or PROV_FILE
    out = []
    labels = list(LABEL.finditer(names_text))
    shape = LABEL.sub("X", names_text)
    more = re.fullmatch(r"(?:X, )*X and (\d+) more", shape)
    shown = len(labels)
    if more:
        total = shown + int(more.group(1))
        if shown != 3:
            out.append(f"'and N more' after {shown} names, not 3")
    else:
        total = shown
        if not re.fullmatch(r"X|(?:X, )*X and X", shape):
            out.append(f"list not written as 'A, B and C': {names_text!r}")
    if total != len(able_ids):
        out.append(f"count {total} != {len(able_ids)} doctors who can")
    if shown > 3:
        out.append(f"{shown} names read out")
    texts = [m.group(0) for m in labels]
    if len(set(texts)) != len(texts):
        out.append(f"two labels read the same: {texts}")
    for m in labels:
        fits = [p for p in able_ids if PROV[p]["name"] == m.group("name") and PROV[p]["specialty"] == m.group("specialty")]
        if not fits:
            out.append(f"{m.group(0)} is not a doctor who can")
            continue
        same_name = [p for p in able_ids if PROV[p]["name"] == m.group("name")
                     and PROV[p]["specialty"] == m.group("specialty")]
        if len(same_name) > 1 and not m.group("places"):
            out.append(f"same-name doctor without locations: {m.group(0)}")
        if m.group("places"):
            places = set(m.group("places").split(" / "))   # round 7 s5: places joined with " / "
            if not any(places <= {LOC[l]["name"] for l in PROV[p]["location_ids"]} for p in fits):
                out.append(f"wrong locations in {m.group(0)}")
    return out


# Round 7 s5: every list of doctors in a note reads at most three names, then "and N more".
NAMES = sorted({x["name"] for x in PROV_FILE.values()}, key=len, reverse=True)


def names_in(text):
    """Doctor names written in a piece of text (longest first, so no name hides inside another)."""
    found = set()
    for n in NAMES:
        if n in text:
            found.add(n)
            text = text.replace(n, "#")
    return found


def capped_names_problems(names_text, want):
    """A list of plain doctor names ("A", "A and B", "A, B and C", or "A, B, C and N more"):
    the people shown must be among `want` (a set of names), at most three are read, and the
    count must add up to len(want)."""
    out = []
    more = re.fullmatch(r"(?P<shown>.+) and (?P<n>\d+) more", names_text)
    if more:
        shown = split_doctor_list(more.group("shown"), last_and=False)
        total = len(shown) + int(more.group("n"))
        if len(shown) != 3:
            out.append(f"'and N more' after {len(shown)} names, not 3: {names_text!r}")
    else:
        shown = split_doctor_list(names_text)
        total = len(shown)
        if len(shown) > 1 and names_text != ", ".join(shown[:-1]) + " and " + shown[-1]:
            out.append(f"list not written as 'A, B and C': {names_text!r}")
    if len(shown) > 3:
        out.append(f"{len(shown)} names read out: {names_text!r}")
    if len(set(shown)) != len(shown):
        out.append(f"a name read twice: {names_text!r}")
    if not set(shown) <= set(want) or names_in(", ".join(shown)) != set(shown):
        out.append(f"names {shown} not all among {sorted(want)}")
    if total != len(want):
        out.append(f"count {total} != {len(want)}")
    return out
