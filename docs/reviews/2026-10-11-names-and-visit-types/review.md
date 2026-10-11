# Review: decision 77 (new patient's name saved from the confirmed letters), commit 39845de

## Summary

The idea is right and the main path works: if the AI sends the letters it read back as "F, A, R, H, A, A, N" / "C, H, I, D, A", the saved name is "Farhaan Chida", whatever `full_name` says, and that name reaches the thank-you line and the bookings file. But the code that turns letters into a name (`_spelled`) only handles the tidy forms in the tests. The Sun 11 call itself shows the forms that come up in a real call. Speech-to-text wrote the caller's spelling as "C-H-I-D-A" and "F-A..." / "R-H-", and the caller said "Double A". `_spelled` saves "C-H-I-D-A" exactly as written, and turns "F, A, R, H, double A, N" into the name "F A R H Double A N". Nothing is refused and no warning is given. That is the same kind of silent wrong name the change is meant to stop. The path where a returning caller isn't found and chooses to register as new has the same gap: the last name the caller spelled on the third try is reused as the saved name, in whatever form it came in. The new visit_type instruction asks the AI to explain how the visits differ, but the clinic data says nothing about that (Skin Cancer Screening and Full Body Skin Exam have identical data), so the AI would have to make it up. Finally, the change makes 313 independent tests fail, plus 8 errors, and none of it is recorded. Decision 77 is also missing from `docs/decisions.md`. I ran the throwaway-adapter check from P3 (results in N6): every new failure comes from the agreed change.

## Findings

### N1 (high): letters joined by hyphens are saved as written: "Farhaan C-H-I-D-A"

`backend/call/tools.py:121-123` (`_spelled`)

**What's wrong:** commas, full stops and spaces count as gaps between letters, but hyphens don't. So "F-A-R-H-A-A-N" stays as one word. Since hyphens are allowed in names, it passes the check, and the capital-letter rule puts a capital after every hyphen.

**Failure scenario (verified on a copy):** in the Sun 11 call, speech-to-text wrote the caller's spelling as `C-H-I-D-A.`, `F-A...` and `R-H-` (the console log at 18:21:15, 18:21:19 and 18:21:43). gpt-4o also often writes a spelled name this way. If the AI copies that form into the field:
- `spelled_first_name="F-A-R-H-A-A-N"`, `spelled_last_name="C-H-I-D-A"` → `{"ok": true}` and the saved name is **"F-A-R-H-A-A-N C-H-I-D-A"**.
- The caller is thanked as "F-A-R-H-A-A-N" (the voice would probably read the letters out), and the bookings file stores that name.
- The read-back doesn't include the name, so the caller can't catch it.

**Suggested fix:** treat a hyphen between single letters as a gap. If every part between gaps is one letter ("F-A-R" or "F, A, R"), join them. Keep a hyphen only when it stands alone ("M, A, R, Y, -, J, A, N, E") or sits between real words ("SMITH-JONES"). Add "F-A-R-H-A-A-N" and "C-H-I-D-A." to the tests.

### N2 (medium): a mix of single letters and words is saved as a name: "F A R H Double A N"

`backend/call/tools.py:122-124`

**What's wrong:** if even one part isn't a single letter, `_spelled` treats every part as a separate word. Anything made only of letters passes. Nothing refuses a mix of single letters and words.

**Failure scenarios (verified):**

| Sent | Saved |
| --- | --- |
| "F, A, R, H, double A, N" (the caller said "Double A" in the Sun 11 call) | "F A R H Double A N" |
| "F, A, R, H, A as in apple, A, N" (the new instruction itself adds "A as in apple" to the conversation) | "F A R H A As In Apple A N" |
| "O, apostrophe, B, R, I, E, N" | "O Apostrophe B R I E N" |
| "M, A, R, Y, space, A, N, N" | "M A R Y Space A N N" |
| "F A R H AA N" | "F A R H Aa N" |

Neither the instructions nor the field descriptions say what to send for "double A", a space, a hyphen or an apostrophe.

**Suggested fix:**
1. Refuse any value that mixes single letters with longer words, with a message saying how to send it: "letters only: 'double A' is A, A; send a name with a space or hyphen as words, e.g. MARY ANN, SMITH-JONES".
2. Put the same sentence in the `spelled_first_name` / `spelled_last_name` descriptions.

### N3 (medium): returning caller not found who registers as new: the third-try spelling becomes the saved name, and nothing tells the AI to spell back first

- `backend/call/tools.py:545-550` (start_booking description) and `:558-560`
- `backend/clinic/patients.py:45` (SAY_OFFER)

**What's wrong:** `spelled_last_name` now has two jobs.
- **Returning caller:** it's a search key. It's read loosely: punctuation and accents are dropped and one wrong letter is allowed (`letters_apart`, which works on the tidied-up text), so "B-R-A-U-N" or "B, R, O, W, N" both work.
- **New patient:** the same field becomes the saved name, read strictly.

The tool description says "If they choose to register as new, call again with returning false". It doesn't say to spell both names back first. The identify-stage text only says to spell back "for a new patient", and until the offer the AI was treating this caller as returning.

**Failure scenario (verified):** Emily fails twice, spells "B-R-A-U-N" on the third try, and is offered registration.
- The AI calls `returning=false, spelled_last_name="B-R-A-U-N"`. That is refused, which is good: the refusal does tell it to spell both names. But it costs an extra AI pass, and the caller first hears "Thank you, one moment" for nothing.
- If the AI then fills `spelled_first_name` from the name it heard ("EMILY") and reuses the old last name, the saved name is **"Emily B-R-A-U-N"**.
- If the heard first name was wrong ("Farhan"), the AI can send "FARHAN" without ever reading it back. The code can't tell confirmed letters from letters the AI made up, so we are back to the Sun 11 bug.

**Suggested fix:**
1. In the description: "If they choose to register as new, spell both names back as for a new patient, then call again with returning false and the letters they confirmed."
2. Fix N1, so a hyphenated last name from the third try can't be saved as written.
3. Optionally: once the caller has been offered registration, refuse a new-patient call whose `spelled_last_name` is the same text as the third-try value until the AI has sent a fresh one. This is optional, and the owner can decide.

### N4 (medium): the visit_type stage must explain "how the visits differ", but there's nothing to explain from, and no way out if the caller still won't choose

`backend/clinic_agent.json:44`

**What's wrong:**
- The AI only sees each visit's name, length, and the referral and new-patient flags (`call/session.py:195-205`). `answer_question` gives the same facts.
- In `backend/data/catalog.json`, Skin Cancer Screening (appt_027) and Full Body Skin Exam (appt_028) have identical data: 30 min, no referral, open to new patients. Cosmetic Consultation is the same too.
- So "tell them how the visits differ" can only be filled with medical-sounding claims the AI makes up. The persona forbids exactly that ("Never make up a fact").
- "Never choose for them" has no exit. The caller in the Sun 11 call said "Um, any... All of them is good". A caller who keeps answering "you pick" or "whichever" can go round in circles.

**Failure scenario:** the caller says "any of them". The agent invents a clinical difference, for example "the screening looks at specific spots, the full exam covers your whole body", which no record supports, in a healthcare setting. If the caller says "you decide" twice, the agent explains again; nothing ends the loop.

**Suggested fix:**
1. Say the differences only from what's listed (names, length, referral). If they don't differ, say the names and ask.
2. After one more "any", either offer a member of staff (hand_off with speak_to_staff) or let the owner agree a stated default. This is the owner's call.
3. If differences are wanted, add a one-line description per visit type to the catalog data, so the facts come from the data.

No conflict found with "Always say one short sentence before calling a tool" (no tool is called here). Asking which visit they want is not the doctor/place/time preference question that decision 60 bans.

### N5 (medium): the spelling exchange has no limit and no way out

`backend/clinic_agent.json:31` (identify instructions)

**What's wrong:** "If they correct you or a letter is unclear, check it with a word ... and spell the name back again" can repeat forever. Each unclear letter is now one more question, and the persona says to ask one question at a time. Decision 36 ("nobody should be asked forever") only covers returning callers.

**Evidence from the Sun 11 call:** spelling took about 2 minutes (18:19:53 to 18:21:54):
- the letters were misheard ("F, E, R, X, E, E, N" for F, A, R, H, A, A, N);
- the agent lost track of which name was being spelled ("Please spell your last name again" while the caller was on the first name);
- the reply to a check word was itself misheard ("More apple" at 18:21:04).

**Failure scenario:** a caller with a long or unusual name gets stuck in rounds of "Was that M as in Mary?" with no end. They hang up, or the 10-minute cap ends the call.

**Suggested fix:** add a limit to the instructions. For example: after two read-backs of a name that are still wrong, ask the caller to spell it slowly with a word for each letter. If that fails too, offer a member of staff. The AI-played callers can show how often this happens.

### N6 (medium, process): 313 independent tests now fail, decision 77 isn't in the decision log, and there's no spec-change note

`docs/decisions.md` (it ends at 76), `docs/reviews/` (nothing for this change)

**What's wrong:** the independent tests register new patients without the spelled fields, so they are refused.
- On this commit: **313 failed, 8 errors, 3221 passed** (`pytest tests_independent`).
- process.md step 7 / P3 asks for proof that these come only from the agreed change, and a written spec-change note for the next tester. Neither is in the repo.
- `INTERFACE.md:121` cites "Decision 77", which doesn't exist in `docs/decisions.md`.
- `docs/build-log.md:154` and `docs/defence-notes.md:191` still describe "the first name not spelled back" as known and not fixed, which this change overtakes.

**What I checked (on a copy, never committed):** a throwaway adapter played an AI that fills `spelled_first_name` / `spelled_last_name` from the first and last words of `full_name`. With it, **7 failures remain**, none caused by decision 77:
- `test_choose_option_handler_stays`: already known as decision 66.
- `test_log_lines_record_every_stage_move_and_tool_call_in_order`: caused by my adapter adding fields to the logged values.
- 5 `test_inspector_*` editor tests: they look for a real call-log file (`20261010-184339-8e2ba6.jsonl`) that isn't in this copy. *Unverified* whether they pass on the owner's machine.

**Suggested fix:**
1. Add decision 77 to `docs/decisions.md`.
2. Record the adapter result in a triage file.
3. Write the spec-change note for the next tester: "new patients need both spelled fields; the saved name is built from them".
4. Update the build-log and defence-notes lines.

### N7 (low–medium): a space inside a spelled name is lost, and the capitals can't be right for some names

`backend/call/tools.py:122-134`; the instruction says "saved from these letters exactly" (`clinic_agent.json:31`)

**What's wrong:**
- Spelled letter by letter, "Mary Ann" becomes **"Maryann"** ("M, A, R, Y, A, N, N" and "M A R Y  A N N" both do). The instructions give no way to show the gap.
- The capital-letter rule changes some names: "McDONALD" or "M, C, D, O, N, A, L, D" → **"Mcdonald"**; "van der Berg" → **"Van Der Berg"**; "J.R." → "Jr".
- "Exactly" isn't true, since the capitals and the gaps are decided by the code.

**Failure scenario:** a caller called Mary Ann Smith is saved as "Maryann Smith"; a McDonald is saved as "Mcdonald". This only affects how the name looks: returning-patient matching ignores capitals and gaps.

**Suggested fix:**
1. Tell the AI to send a name with a space or hyphen as words (it then keeps them).
2. Keep the capitals as sent when the AI sends mixed capitals ("McDonald", "van der Berg"); only change them when it sends all capitals or all lower case.
3. Drop "exactly" from the instruction.

### N8 (low): a curly apostrophe or a separately-coded accent is refused with a message that doesn't say why

`backend/call/tools.py:124-125`

**What's wrong:** "O’BRIEN" (curly apostrophe), "O`BRIEN", and an "Á" stored as A plus a separate accent mark are refused. The refusal only says "must be the letters the caller confirmed". The returning path accepts all of these, so the same field is read differently in the two paths.

**Failure scenario:** the AI retries with "OBRIEN", and the patient is saved as "Obrien". *Unverified* how often gpt-4o sends curly apostrophes in tool values.

**Suggested fix:** turn ’ and ` into ', and put accents back together with their letters (`unicodedata.normalize("NFC", ...)`) before checking.

### N9 (low): stray words and sentences are accepted as names, and the test that seems to cover this doesn't

`backend/call/tools.py:124`; `backend/tests/test_builder_call_tools.py:216`

**What's wrong:**
- Any run of letters passes (verified). "yes" / "unknown" are saved as "Yes Unknown", and the caller is thanked as "Yes".
- "not sure how its spelled" is saved as "Not Sure How Its Spelled Chida".
- "Farhaan, is that right" is saved as "Farhaan Is That Right".
- "--A" and "A-" are accepted as written.
- There's no length limit (300 letters are accepted).
- The test case "not sure how it's spelled!" is refused only because of the "!". Without it, the same sentence is saved as a name, so the test gives false confidence.

**Suggested fix:**
1. Refuse values of more than about 3 words, values with a hyphen or apostrophe at the start or end, and words from a small list ("yes", "no", "unknown", "double", "as", "in", "space", "apostrophe", "hyphen", "dash").
2. Add a sensible length limit, with the reason written next to it.
3. Change the test to the sentence without punctuation.

### N10 (low): `full_name` is no longer used for new patients but is still required, and the log shows two names

`backend/call/tools.py:257, 552, 564`

**What's wrong:** for a new patient, `full_name` is only written to the call log. In the editor's inspector, the start_booking line shows `full_name: "Farhan Chida"` while the booking card shows "Farhaan Chida". Someone reading the log could think the wrong name was saved.

Nothing else reads it: I checked the thank-you line (`just_happened`) and the bookings file `caller` field; both use the spelled name.

It's an unused field (an item on the slop checklist), and it can't be used to catch junk like "Yes Unknown".

**Suggested fix (owner's choice):**
- Say in its description "returning patients: used to find them; new patients: not saved", and log the saved name in the tool result (e.g. `{"ok": true, "saved_name": "Farhaan Chida"}`); or
- use it as a loose check: refuse when the spelled first name looks nothing like the heard first name (e.g. less than half alike). This would catch "Yes"/"Double" but still allow Chera→Chida.

### N11 (low): the tests miss the cases that matter most

`backend/tests/test_builder_call_tools.py:180-228`

**What's wrong:**
- The expected names are written by hand, not copied from the code's output. Good.
- But every "accepted" case is a tidy form. None of these is tested: hyphen-joined letters (N1); "double A", "A as in apple" or "apostrophe" (N2); a space lost in letter-by-letter spelling (N7); a curly apostrophe (N8); a stray word (N9).
- The `""` case in the refused list is refused by the "both names needed" check, not by `_spelled`.
- The Sun 11 regression test uses the comma form the AI spoke. The forms speech-to-text actually produced ("C-H-I-D-A.", "Double A") are the ones that fail.
- The register-as-new path is tested only with clean new letters ("EMILY", "BROWN"). It doesn't cover the AI re-sending only the third-try last name, or a hyphenated one.
- The instruction tests only check that sentences are present in the agent file. They can fail when the wording changes, but they prove nothing about what the AI does. That needs the AI-played callers or another real call, and should be said in the build log.

**Suggested fix:** add the cases above, each with the result it should have (refused, or the right name).

### N12 (low): small slop items

- `_spelled` docstring (`tools.py:117`) says "Only letters, spaces, hyphens and apostrophes are accepted"; commas and full stops are accepted too, as gaps.
- `first` is used for two different things in `start_booking` (`tools.py:284` and `:295`). For "Mary Ann Smith" the thank-you line uses "Mary", though the code was told the first name is "Mary Ann".
- A refused new-patient call (letters missing) drops the wishes sent with it, while a failed returning try keeps them (decision 53). This matches "a refused value changes nothing", and the AI still has the wishes in its history within the stage, so probably no fix is needed. Worth one line in the decision.

## Checked and found correct

- The main path: letters sent as "F, A, R, H, A, A, N" / "C, H, I, D, A" save "Farhaan Chida" even when `full_name` is "Farhan Chida". That name reaches the thank-you line and the bookings file (test at line 189, and my own run).
- Lower case, letters separated by spaces or full stops, "O'BRIEN", "SMITH-JONES", "M, A, R, Y, -, J, A, N, E", accented letters (José, Núñez), Turkish İ/ı, and ß all come out sensibly. Digits, "?", "/" and a lone "-" or "'" are refused.
- Missing either spelled name is refused, and nothing changes (no caller, no wishes recorded, no stage move).
- The returning-patient path is unchanged in code. A spelled last name sent on a first returning try doesn't skip any identity step, and in my checks it didn't find anyone the normal path wouldn't. "B, R, O, W, N" still finds Emily Brown.
- The identify text and the start_booking description don't contradict each other on the main new-patient path. "Say only a short line such as 'Thank you, one moment'" fits decision 60, and replaces the "Let me proceed with booking your skin check" line from the call.
- The visit_type text doesn't conflict with "Always say one short sentence before calling a tool" or with decision 60's ban on preference questions (but see N4).
- Builder tests: 431 pass on a copy of the commit.
