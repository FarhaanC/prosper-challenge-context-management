# Spec changes after the seventh check (Wed 7 Oct 2026, night)

Small corrections after round 7. This note **adds to and overrides** the earlier notes (`build-decisions.md`, `spec-changes-round-2.md` … `spec-changes-round-7.md`) where they disagree. It describes behaviour, not code.

## The rule, stated exactly

Names (doctors, places, languages) are matched forgivingly against our own records, because the AI doesn't know them. Two fixed word lists are read:

- "no preference" words, which are treated as empty;
- words no name has ("not", "but", "another", "someone", "else", "please"…), which are refused with a note saying how to send the value.

Everything else is a plain instruction: ids, yes/no, a weekday or a date, "morning" or "afternoon". Anything that isn't one of those is refused, never guessed.

## 1. Places: a place's own name words only (confirms round 7, section 1; fresh verifier's ruling)

When a place name is matched, words that don't tell our places apart (health, center, clinic, medical, group, family, specialty, care, community) are allowed **only if they're part of that place's own name**. "the" is always ignored ("the Castro").

- **Recognised:**
  - "Sunset Clinic" and "Sunset Community Clinic" → Sunset Community Clinic;
  - "Mission Bay Health Center" → Mission Bay Health Center;
  - "Richmond Care Center" → Richmond Care Center.
- **Not recognised** (`place_unknown`), because the word belongs to *other* places' names or to none:
  - "Richmond clinic", "Downtown clinic", "Richmond Medical Group", "Midtown Health Center";
  - "Midtown office", "Downtown location", "Sunset hospital", "Richmond branch", "Mission Bay Health Centre".
- **"Chinatown clinic" is not recognised.** It is not quietly read as "near Chinatown", because we have no clinic there.
- A value containing a word no name has ("not far from Union Square", "the Midtown one please") is refused as `bad_input` before any matching. This is the round-6 sentence guard; round 7 wrongly listed "not far from…" as "not recognised".
- The "could mean A or B" note for a shared place name reads three names, then "or N more".

## 2. Doctor labels: one form everywhere (adds to round 7, section 5)

In every list of doctors, a label that would repeat is written "Name (Specialty, place / place)". That includes the "can't do this" reasons, which otherwise show names only. Example: "Dr. Daniel Chen (Dermatology, Downtown Health Center / Richmond Care Center) and Dr. Daniel Chen (Dermatology, Sunset Community Clinic) aren't taking new patients."

Note that a label can contain a comma inside its brackets. A list of labels is separated by ", " **outside** brackets.

"Doctors with that surname" uses the same labels and reads three, then "and N more".

## 3. Small items

- `answer_question(about, …)`: case and spaces are ignored in `about`, as in `change_choice` ("Visit Type" works).
- `change_choice(…, near=…)`: `near` must be a real true/false. Anything else (e.g. the text "false") is refused with `ValueError`, changing nothing.
