"""Round 6: my own check of the "Doctors who can" list that the "no other doctor" note
now reuses (spec-changes-round-6.md s5), written from the spec and catalog.json. It
does NOT import anything from the module under test.
"""

import re

from reference import LOC, PROV as PROV_FILE

LABEL = re.compile(r"(?P<name>Dr\. [^(]+?) \((?P<specialty>[^,()]+)(?:, (?P<places>[^()]+))?\)")


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
            places = set(re.split(r", | and ", m.group("places")))
            if not any(places <= {LOC[l]["name"] for l in PROV[p]["location_ids"]} for p in fits):
                out.append(f"wrong locations in {m.group(0)}")
    return out
