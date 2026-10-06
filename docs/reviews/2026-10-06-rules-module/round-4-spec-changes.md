# Spec changes after the third review (6 Oct 2026, night)

Round 3 found problems at the edges. The builder fixed them. Some fixes deliberately change behaviour the round-3 spec described. This note **adds to and overrides** the earlier notes (`build-decisions.md`, `spec-changes-round-2.md`, `spec-changes-round-3.md`) where they disagree. It describes behaviour, not code.

## Four deliberate behaviour changes

1. **A wish only a turned-down doctor can meet** (e.g. the caller turned down Dr. Kenji Kim, then asks for "the Midtown one", where only Dr. Kim does that visit for them) now gets a note of kind `wish_conflict`: "Midtown Medical Group is only possible with Dr. Kenji Kim, whom you turned down." It is no longer `wish_impossible` ("…has nothing available…"), because that wasn't true. The turned-down doctor still isn't offered.
2. **Unusable identity answers no longer loop forever.** `need_both` (name or date of birth missing or unusable) still doesn't count as a miss, but after **3 unusable answers in a row**, `IdentityCheck.attempt` returns `offer_new_or_staff` (register as a new patient, or speak to staff). A usable answer resets that count.
3. **"Near" plus a street name without the word "street" is recognised:** "near Geary" or "near Market" match our streets (here both are shared by two clinics, so the result is ambiguous: a note, no narrowing). Without "near", a bare street name like "Geary" is still not treated as a street.
4. **Naming a turned-down doctor again brings them back.** If the caller turned a doctor down and later asks for that doctor by name ("actually, Dr. Kim is fine"), the name wins: they're offered again, with no false note. A doctor wish that is only carried over (not named again) doesn't override a turn-down.

## Other round-3 behaviour to test

- **"Someone else, please":** `BookingCard.change_choice("doctor", X)` where X is empty or a phrase like "someone else", "somebody else", "a different doctor", "another doctor", "anyone else", "other doctor" turns down, for the rest of the call:
  - the chosen doctor, if one is chosen;
  - otherwise the carried-over doctor;
  - otherwise every doctor in the options currently on offer (`BookingCard.remember_offer`).

  "not Dr. Chen" turns down doctors matching that name. If nobody else can do the visit, a `no_other_doctor` note says so and the turned-down doctor(s) are offered after all. `BookingCard.summary()` lists turned-down doctors ("not: Dr. …").
- **Language as a change:** `change_choice("language", "Spanish")` sets the language wish and makes it the latest change. "" or "any" clears it. "Mandarin Chinese" counts as Mandarin (a language some doctor speaks); unknown languages are kept as said.
- **Time phrases** (through `change_choice("time", …)` and in `Preferences.days` entries): "this afternoon" means today, in the afternoon; "Thursday or Friday" means two days; "Thursday, morning please" works; "I don't mind", "don't mind", "whenever" and "any time" clear day and time; "any day" clears the day only. Only what's mentioned changes. Unclear phrases ("next Thursday") still give `bad_input`.
- **"No preference"** is recognised the same way everywhere (day, time, place, doctor), apostrophes and spaces ignored: "I don't mind", "dont mind", "no preference", "anywhere", "anyone", "whatever"…
- **Identity steps** (amends round 3, section 1):
  - every attempt is looked up, so correct details are accepted at any step, even unspelled after two misses;
  - after two misses, an unspelled wrong attempt returns `spell_last_name` again without counting;
  - once `offer_new_or_staff` has been given, later misses give it again (never back to "spell");
  - a spelled surname of only spaces counts as no spelling;
  - a first name alone plus a spelled surname is enough to look up;
  - the `found` step's sentence is "Thank you, <first name>. I've found your details.";
  - degree letters are not titles, so "Anh Do" is a full name ("Dr.", "Mr.", "Jr" etc. still are).
- **Specialty words:** the usual doctor word built from each specialty name must match exactly (plural allowed). Spelling forgiveness applies only to the 21 real names. "podiatrist", "hematologist", "nephrologist", "audiologist", "generalist", "physician" and "gynecologist" match nothing.
- **Places:**
  - Words of 5 letters or fewer must match exactly ("Marin" isn't "Marina"); longer words may be misspelled ("Richmund", "Mision Bay").
  - Small linking words are ignored ("the Midtown one in SF").
  - City words alone ("SF") mean no place wish.
  - A full address works, and the house number picks between clinics on the same street ("4455 Geary Blvd" is Downtown Health Center).
  - Street abbreviations ("St", "Ave", "Blvd", "Rd") count only as the last word, so "St Mary's" isn't a street.
- **Notes:**
  - "Doctors with that surname: A, B, C and N more" when more match than are read out.
  - "Nothing is open today for X; here are other options." (no "in the next 14 days" for today/tomorrow).
  - "a Ukrainian-speaking doctor" / "an Urdu-speaking doctor".
- **Catalog checks** also refuse wrong kinds of value (e.g. a duration that isn't a whole number, languages that aren't a list of text, a record that isn't a record), listing every problem.
