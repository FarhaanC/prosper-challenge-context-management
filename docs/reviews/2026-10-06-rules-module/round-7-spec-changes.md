# Spec changes after the sixth check (Wed 7 Oct 2026, evening)

The round-6 check found that place values were still read as phrases ("near…", "the X one", "on Geary"). So the claim "no part of the code reads the caller's sentences" wasn't true. **Farhaan decided "near" becomes a plain yes/no the AI passes.** The rule is now exact:

- **Names** (doctors, places, languages) are matched forgivingly against our own records, because the AI doesn't know them.
- **Everything else** is a plain instruction.

This note **adds to and overrides** the earlier notes (`build-decisions.md`, `spec-changes-round-2.md` … `spec-changes-round-6.md`) where they disagree. It describes behaviour, not code.

## 1. Places: a name plus near yes/no (replaces decision 24's near-phrases and the place-phrase rules from rounds 1–4)

`BookingCard.change_choice("location", name, near=False)`, and `Preferences.location_hint` plus the new `Preferences.near`:

- **`name`** is a place name: one of our locations ("Midtown", "Mission Bay"), a neighbourhood ("Hayes Valley"), a landmark ("Union Square", "the Castro") or a street with its street word ("Geary Street", "Mission St", "4455 Geary Blvd").
  - "" or a "no preference" word means no place wish.
  - Names are still matched forgivingly, as before:
    - spelling ("Richmund");
    - spaces ("mid town");
    - "District" ("Marina District");
    - city words ("Downtown SF");
    - generic name words ("Mission Bay Health Center").
  - Short words must match exactly ("Marin" isn't "Marina").
  - A name several places share is ambiguous ("Mission", "North", "Geary Street").
- **`near`**: True means "somewhere close to it": rank by distance, and don't restrict to that place. False means that place only.
  - A landmark is always "near", since it isn't a clinic.
  - An ambiguous name with near=True gives the note but doesn't narrow.
  - A house number we don't have ("9999 Geary Street") means somewhere on that street: ambiguous, near, no narrowing.
- **`near=True` with any other kind of change** is refused (`ValueError`, nothing changes).
- When a chosen place is carried over after another change, near goes back to False.
- The card summary shows "place: near Downtown" when near is set.

**No longer read from the words** (each is now simply not a place name, so it's "not recognised", kind `place_unknown`):

- "near…", "closer to…", "close to…", "next to…", "around…", "by…", "on the way to…", "not far from…";
- "the X one", "the one on X", "on X", "somewhere…";
- "…area", "…side", "…neighbourhood", "…location", "…clinic", "…office";
- linking words: "in", "at", "to", "from", "a", "one", "place".

A bare street name without a street word ("Geary", "main") is **not** a street. The AI passes "Geary Street" for "the one on Geary".

The `place_unknown` note now reads: "I don't recognise the place 'X'. Pass just a place name: a neighbourhood, a street or one of our location names."

## 2. Languages: one name, nothing guessed (replaces round 6, section 6)

Accepted:

- a language in our records, any case ("spanish" → Spanish);
- one listed other name: "Mandarin Chinese" (or "Chinese Mandarin") → Mandarin;
- a name we have no record of that contains no language we have ("Klingon", "Haitian Creole", "ASL", "Chinese"). It's kept as said, with its capitals, and gets the true "None of our doctors is listed as speaking X…" note.

Refused with `bad_input` (no options):

- anything mixing a language we have with other words ("Spanish French", "Spanish only", "only Spanish", "Cantonese Mandarin", "Spanish Klingon");
- more than two words;
- a sentence (round 6).

"No preference" words still mean no language wish.

## 3. "No preference" words are stored as empty

`change_choice` stores "" (not the word) for a no-preference doctor, place or language value. The card summary never shows them. For time, "any day" as `new_value` or a day entry still clears the day.

## 4. Exact names for what can be changed and asked about

- `change_choice(what, …)`: `what` must be one of visit_type, doctor, location, time or language. Case and spaces are ignored ("Visit Type"). Synonyms ("provider", "place", "clinic", "slot", "reason", "service", "day", "date", "visit") are refused with `ValueError`, changing nothing.
- `answer_question(about, …)`: `about` must be location, doctor or visit_type (case and spaces ignored). Anything else gets `found: False`, "Pass about as location, doctor or visit_type."
- `answer_question` refuses a sentence as a doctor or location name ("not Dr. Chen", "another doctor", "anywhere but Downtown") with `found: False` and "'…' isn't a doctor name. Pass just the name." This is the same guard as the search.

## 5. Notes: every list of doctors reads at most three

Every list of doctors in a note reads three, then "and N more". That covers:

- "Doctors who can";
- "no other doctor";
- the same-name note;
- both "whom you turned down" notes;
- the "can't do this" reasons.

The same-name note lists its doctors with "; " between them and ends "; and N more." when cut short.

Same-name doctors get their places added. Every one of them does, not just the first, even when they share a specialty too. Places inside a label are joined with " / ":

- "Dr. Daniel Chen (Dermatology, Downtown Health Center / Richmond Care Center)".

## 6. Smaller changes

- **Weekday words:** only full names, their plurals ("Thursdays") and these short forms: mon, tue, tues, wed, thu, thur, thurs, fri, sat, sun. "thus", "frid" and "wednes" are refused.
- **Repeated ids:** a repeated id is reported once however many copies there are, in both the catalog and patient checks. Ids are compared without surrounding spaces ("p1" and "p1 " are the same id).
