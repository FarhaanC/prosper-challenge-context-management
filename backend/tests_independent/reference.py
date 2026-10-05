"""My own small reference implementation of the booking rules, written straight
from catalog.json and the spec (rules 1-5, decisions 27 and 28). It does NOT
import anything from the module under test.
"""

import json
from pathlib import Path

DATA = Path(__file__).resolve().parent.parent / "data"
RAW = json.loads((DATA / "catalog.json").read_text(encoding="utf-8"))

LOC = {l["id"]: l for l in RAW["locations"]}
PROV = {p["id"]: p for p in RAW["providers"]}
VT = {a["id"]: a for a in RAW["appointment_types"]}
SPECIALTIES = sorted({a["specialty"] for a in RAW["appointment_types"]})


def _norm(s):
    return " ".join("".join(ch if ch.isalnum() else " " for ch in s.lower()).split())


def ref_pairs(is_new, vt_id):
    """(provider_id, location_id) pairs passing rules 1, 2, 3 and the doctor half of 5."""
    vt = VT[vt_id]
    out = set()
    for p in PROV.values():
        if vt_id not in p["appointment_type_ids"]:          # rule 2
            continue
        if is_new and not p["accepting_new_patients"]:      # rule 5 (doctor)
            continue
        for lid in p["location_ids"]:                       # rule 1
            cap = vt.get("required_capability")
            if cap and cap not in LOC[lid]["capabilities"]:  # rule 3
                continue
            out.add((p["id"], lid))
    return out


def ref_bookable(is_new, refs, vt_id):
    vt = VT[vt_id]
    if is_new and not vt["new_patients_allowed"]:            # rule 5 (visit type)
        return False
    if vt["requires_referral"] and _norm(vt["specialty"]) not in {_norm(r) for r in refs}:  # rule 4
        return False
    return bool(ref_pairs(is_new, vt_id))


def ref_combo_ok(is_new, refs, vt_id, pid, lid):
    """Do rules 1-5 allow this exact visit type + doctor + location?"""
    return ref_bookable(is_new, refs, vt_id) and (pid, lid) in ref_pairs(is_new, vt_id)


def first_name(full):
    return full.replace("Dr. ", "").split()[0]


def last_name(full):
    return full.split()[-1]
