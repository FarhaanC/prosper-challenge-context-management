"""Round 2: my own model of spec change 1 ("newest wish wins, every note true").

Written from spec-changes-round-2.md section 1 and the raw data. It uses the
module's fake calendar ONLY as the source of open times (as round 1 did); the
rules come from reference.py and the wish order from the spec text:

1. Preferences.latest; 2. said wishes: doctor, place, day/time, language;
3. carried-over: preferred_provider_id, then preferred_location_id.
A wish is applied only if some bookable option survives it together with every
stronger wish already applied; otherwise it is set aside with a note:
wish_impossible if no valid option anywhere meets it, wish_conflict otherwise.

Round 3 updates (spec-changes-round-3.md):
- s4 "The newest wish wins, whatever it is": latest promotes that kind of wish to
  strongest even when it is a carried-over choice.
- s3: a YYYY-MM-DD day outside today..today+14 gives NO options and one bad_input note.
- s4 "Someone else, please": doctors in not_provider_ids are left out unless nobody
  else can do the visit (then a no_other_doctor note, and they stay).
- s4: doctor wishes "any", "anyone", "no preference" mean no doctor wish.
- s2: notes are records; their text is note.say.

Round 4 updates (spec-changes-round-4.md, "Four deliberate behaviour changes"):
- change 1: a wish that only a turned-down doctor can meet is set aside with a
  wish_conflict note "... is only possible with Dr. X, whom you turned down."
  (not wish_impossible); the turned-down doctor is still not offered.
- change 4: a doctor the caller NAMES again (doctor_name_heard) is no longer
  turned down; a carried-over doctor id does not override a turn-down.

Round 5 updates (spec-changes-round-5.md):
- s3: a doctor name brings turned-down doctors back ONLY if it picks out one doctor
  (one full name; two doctors with exactly the same full name count as one name).
  A surname that fits several doctors brings nobody back.
- s3: when the only fitting doctor for a doctor wish was turned down, the wish_conflict
  note reads "The only doctor matching '...' who can do this is X, whom you turned
  down. Check whether ..." (it does not end with "turned down.").

Only the exact forms below are interpreted (exact doctor names / surnames,
exact location names or "the <neighbourhood> one"), so nothing here depends on
the module's fuzzy matching.
"""

from datetime import date, timedelta

from conftest import NOW
from reference import LOC, PROV, VT, ref_pairs

WEEKDAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]

# Place phrases that NAME one of our locations (restrict), from catalog.json names
# and the spec's examples. Near-phrases are not wishes (they only rank).
RESTRICT_PHRASES = {}
for _lid, _l in LOC.items():
    RESTRICT_PHRASES[_l["name"].lower()] = _lid
RESTRICT_PHRASES.update({
    "the midtown one": "loc_005", "the hayes valley one": "loc_005", "the downtown one": "loc_004",
    "the marina district": "loc_003", "richmond district": "loc_007", "the sunset one": "loc_006",
    "the north beach one": "loc_002", "mission bay": "loc_000", "the mission district one": "loc_001",
})


def _norm_name(n):
    return " ".join(n.replace("Dr.", "").replace("'s", "").split()).lower()


def doctors_named(heard):
    """Exact full name, or exact surname, from catalog.json."""
    h = _norm_name(heard)
    full = {pid for pid, p in PROV.items() if _norm_name(p["name"]) == h}
    if full:
        return full
    sur = {pid for pid, p in PROV.items() if _norm_name(p["name"]).split()[-1] == h}
    if sur:
        return sur
    raise ValueError(f"test only supports exact names, got {heard!r}")


def _day_test(d):
    d = d.strip().lower()
    if d == "today":
        return lambda s: s.date() == NOW.date()
    if d == "tomorrow":
        return lambda s: s.date() == NOW.date() + timedelta(days=1)
    if d[:1].isdigit():
        t = date.fromisoformat(d)
        return lambda s: s.date() == t
    i = next(i for i, w in enumerate(WEEKDAYS) if w.startswith(d[:3]))
    return lambda s: s.weekday() == i


ANY_DOCTOR = {"any", "anyone", "no preference"}


class Wishes(list):
    """A list of wishes plus what the model expects besides them."""
    bad_input = False
    excluded = frozenset()


def out_of_window(days):
    last = NOW.date() + timedelta(days=14)
    for d in days or []:
        d = str(d or "").strip()
        if d[:1].isdigit():
            t = date.fromisoformat(d)
            if not NOW.date() <= t <= last:
                return True
    return False


def interpret(prefs):
    """Wishes as (kind, carried, test(pid, lid, start), keyword-for-note)."""
    wishes = Wishes()
    wishes.bad_input = out_of_window(prefs.days)
    wishes.excluded = frozenset(getattr(prefs, "not_provider_ids", []) or [])
    if prefs.doctor_name_heard.strip() and prefs.doctor_name_heard.strip().lower() not in ANY_DOCTOR:
        ids = doctors_named(prefs.doctor_name_heard)
        if len({PROV[i]["name"] for i in ids}) == 1:  # round 5 s3: only a name picking out one doctor
            wishes.excluded = wishes.excluded - ids
        kw = PROV[next(iter(ids))]["name"].split()[-1]
        wishes.append(("doctor", False, lambda p, l, s, ids=ids: p in ids, kw))
    if prefs.location_hint.strip():
        lid = RESTRICT_PHRASES.get(prefs.location_hint.strip().lower())
        if lid:
            wishes.append(("place", False, lambda p, l, s, lid=lid: l == lid, LOC[lid]["name"]))
    days = [d for d in prefs.days if d.strip() and d.strip().lower() not in ("any", "any day")]
    tod = prefs.time_of_day.strip().lower()
    if days or tod in ("morning", "afternoon"):
        tests = [_day_test(d) for d in days]

        def t(p, l, s, tests=tests, tod=tod):
            if tests and not any(x(s) for x in tests):
                return False
            if tod == "morning":
                return s.hour < 12
            if tod == "afternoon":
                return s.hour >= 12
            return True
        wishes.append(("time", False, t, None))
    if prefs.language.strip():
        lang = prefs.language.strip().lower()
        wishes.append(("language", False,
                       lambda p, l, s, lang=lang: lang in [x.lower() for x in PROV[p]["languages"]],
                       prefs.language.strip().capitalize()))
    if prefs.preferred_provider_id:
        pid = prefs.preferred_provider_id
        wishes.append(("doctor", True, lambda p, l, s, pid=pid: p == pid, PROV[pid]["name"]))
    if prefs.preferred_location_id:
        lid = prefs.preferred_location_id
        wishes.append(("place", True, lambda p, l, s, lid=lid: l == lid, LOC[lid]["name"]))
    strength = {"doctor": 1, "place": 2, "time": 3, "language": 4}
    latest = {"location": "place"}.get(prefs.latest, prefs.latest)
    # Round 3 s4: latest promotes that kind of wish to strongest, even a carried-over one.
    wishes.sort(key=lambda w: (w[0] != latest, w[1], strength[w[0]]))
    return wishes


def universe(schedule, is_new, refs, vt_id):
    out = []
    for pid, lid in ref_pairs(is_new, vt_id):
        for s in schedule.open_slots(pid, lid, VT[vt_id]["duration_min"], NOW):
            out.append((pid, lid, s))
    return out


TURNED_DOWN = "turned_down"  # a wish_conflict whose only fit is a turned-down doctor (round 4, change 1)


def expected(slots, wishes, with_turned_down=None):
    """Greedy, strongest first. Returns (applied, set_aside[(wish, 'wish_impossible'|'wish_conflict'|TURNED_DOWN)]).
    `with_turned_down`: the valid slots before turned-down doctors were removed."""
    current = list(slots)
    applied, aside = [], []
    for w in wishes:
        narrowed = [x for x in current if w[2](*x)]
        if narrowed:
            current = narrowed
            applied.append(w)
        elif any(w[2](*x) for x in slots):
            aside.append((w, "wish_conflict"))
        elif with_turned_down and any(w[2](*x) for x in with_turned_down):
            aside.append((w, TURNED_DOWN))
        else:
            aside.append((w, "wish_impossible"))
    return applied, aside


def check(result, slots, wishes):
    """List of problems (empty = the module agrees with the spec model)."""
    problems = []
    if getattr(wishes, "bad_input", False):
        kinds = [n.kind for n in result.notes]
        if result.options or kinds != ["bad_input"]:
            problems.append(f"out-of-window date: expected no options and one bad_input note, got "
                            f"{len(result.options)} options, notes {[str(n) for n in result.notes]}")
        return problems
    excluded = getattr(wishes, "excluded", frozenset())
    full = list(slots)
    if excluded:
        others = [x for x in slots if x[0] not in excluded]
        if others:
            slots = others
            if any(n.kind == "no_other_doctor" for n in result.notes):
                problems.append("no_other_doctor note although other doctors exist")
        elif slots and not any(n.kind == "no_other_doctor" for n in result.notes):
            problems.append("missing no_other_doctor note")
    applied, aside = expected(slots, wishes, full)
    if slots and not result.options:
        problems.append("no options although valid times exist")
    for o in result.options:
        x = (o.provider_id, o.location_id, o.start)
        if x not in set(slots):
            problems.append(f"option {o.spoken} is not a valid open slot")
        for w in applied:
            if not w[2](*x):
                problems.append(f"option {o.spoken} ignores applied {w[0]} wish (carried={w[1]})")
    wish_notes = [n for n in result.notes if n.kind in ("wish_impossible", "wish_conflict")]
    exp_kinds = sorted("wish_conflict" if k == TURNED_DOWN else k for _, k in aside)
    got_kinds = sorted(n.kind for n in wish_notes)
    if exp_kinds != got_kinds:
        problems.append(f"wish notes {got_kinds} != expected {exp_kinds}: {[str(n) for n in result.notes]}")
    for w, kind in aside:
        if kind == TURNED_DOWN:
            down = [n.say for n in wish_notes if n.kind == "wish_conflict"
                    and (n.say.endswith("whom you turned down.") or ", whom you turned down. Check whether" in n.say)
                    and (not w[3] or w[3].lower() in n.say.lower())]
            if not down:
                problems.append(f"no 'whom you turned down' note for {w[0]} wish: {[str(n) for n in wish_notes]}")
            for say in down:  # every doctor named must be turned down and able to meet the wish alone
                for pid in {x[0] for x in full}:
                    if PROV[pid]["name"] in say and not (pid in excluded and any(w[2](*x) for x in full if x[0] == pid)):
                        problems.append(f"turned-down note names {PROV[pid]['name']}, who doesn't fit: {say}")
            continue
        if w[3] and not any(w[3].lower() in n.say.lower() for n in wish_notes if n.kind == kind):
            problems.append(f"no {kind} note mentioning {w[3]!r}: {[str(n) for n in wish_notes]}")
    return problems
