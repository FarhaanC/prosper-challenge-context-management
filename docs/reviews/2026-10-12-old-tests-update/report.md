# Bringing the older independent tests up to date (12 Oct)

I'm a fresh tester. I didn't write the product code and I didn't change any of it. I only
edited files under `backend/tests_independent/`. The builder's own tests in `backend/tests/`
are untouched.

## 1. Test totals (whole suite, `python3 -m pytest -q -p no:cacheprovider`, Linux)

| | Failed | Passed | Errors | Total |
|---|---|---|---|---|
| Before | 313 | 3,764 | 8 | 4,085 |
| After | **2** | **4,093** | **0** | 4,095 |

There are 10 more tests than before. These are new versions of two old checks (see
`test_voice_identity.py` and `test_voice_values.py` below). I didn't delete, skip or
loosen any test.

The 2 tests still failing are both new versions I added. I left them failing on purpose
because they show a possible gap in the product (see section 4).

## 2. What I changed, and why

### `backend/tests_independent/voice_reference.py` (the shared helper)
- **Change:** the standard new patient (`NEW`, "Farhan Jida") now also sends the letters the
  caller confirmed: `spelled_first_name: "F, A, R, H, A, N"` and `spelled_last_name: "J, I, D, A"`.
- **Why:** decisions 77 and 78. A new patient's name is now saved from the confirmed letters,
  and a new patient without letters is turned away. The letters spell the same name as
  before, so every test that expects "Farhan Jida" still checks the same thing.
- **Effect:** this one change fixed almost all of the 313 failures and all 8 errors.

### `backend/tests_independent/test_voice_agent_builder.py`
- **Test:** `test_choose_option_handler_stays`.
- **Change:** the old test expected the choose_option handler to hand back "no new stage".
  Decision 66 changed this: the handler now hands back the same booking stage, with these
  four things:
  - the conversation kept;
  - the read-back as a `say` line spoken by the code;
  - `respond_immediately` set to false;
  - the booking tools still there.
- **The test now checks all of that**, including the exact sentence "To confirm: <read
  back> Would you like me to book it?". It also still checks that the call stays in the
  booking stage. The test is stricter than before, not looser.

### `backend/tests_independent/test_voice_identity.py`
- **New constant:** `WILSON_LETTERS` holds James Wilson's letters ("J, A, M, E, S" and
  "W, I, L, S, O, N").
- **Register as new after the offer:** `test_register_as_new_after_the_offer` now sends
  these letters when the caller chooses to register as a new patient (decisions 77 and 78;
  INTERFACE.md says "confirm the spelling of both names as for a new patient"). What it
  checks hasn't changed: no record and no referrals from the real James Wilson, and the
  caller's wishes are kept.
- **Same name as a patient:** `test_new_patient_who_shares_a_patients_name_gets_no_record`
  now sends the letters too, for the same reason. It also checks that the call was accepted
  first. Before, if the call was refused, the test crashed instead of saying why.
- **One-word name:** `test_new_patient_with_one_word_name_is_asked_for_full_name` keeps its
  old case. I added two new versions of "only one name was given", because the old case is
  now turned away just for having no letters (decisions 77 and 78):
  - only the first name spelled;
  - `name_not_confirmed: true` with a one-word name. INTERFACE.md says that case "then
    needs first and last".

  Both are refused, as they should be.

### `backend/tests_independent/test_voice_booking_stage.py` and `test_voice_round2_call_order.py`
- **Change:** in the lists of "tools tried after the call has ended", the new patient
  "Someone Else" now sends spelled letters.
- **Why:** decisions 77 and 78. Without letters, the call would be refused for the missing
  letters, and the tests would no longer show that a *finished call* refuses a new booking.
  With the letters, the only reason left for refusing is that the call has ended, which is
  what these tests are about.

### `backend/tests_independent/test_voice_values.py`
- **Test:** `test_start_booking_refuses_bad_identity_values`.
- **Change:** each bad value is now tried twice: once as before (no letters), and once with
  good letters.
- **Why:** decisions 77 and 78. With no letters, every new-patient case is refused just for
  missing letters. So the old version no longer showed that the bad value *itself* is
  refused. The "with letters" version does. Two of these fail (see section 4).

### `backend/tests_independent/editor/api/test_editor_api.py` (the call viewer tests)
- **The problem:** five tests copied the machine's real `backend/call_logs/` folder. They
  expected one particular file (`20261010-184339-8e2ba6.jsonl`, Zoya Chida's call) to be the
  newest. On the owner's machine, newer calls from 11 Oct took its place. On this machine
  there's no `call_logs` folder at all. So the tests depended on which calls had been made on
  the machine.
- **How the viewer finds its logs:** the editor's routes take the log folder as a setting
  (`editor_routes(agent_file, log_dir)`), and the tests already pass in a temporary folder.
  Only the "real logs" they copied in came from the machine.
- **The fix:** a new setup step, `real_logs`, makes two call logs with the real call code in
  a temporary folder that the test controls:
  - **an older call** that was handed to staff;
  - **the newest call**, which replays Zoya Chida's call: new patient (with spelled letters,
    decision 77), New Patient Consultation, afternoon, option 2 booked.

  Each log gets a fixed name, so the test decides which one is newest, not the machine. The
  newest keeps the old file name.
- **What the tests still check:**
  - the newest log wins;
  - a newer call replaces an older one;
  - the events keep their order and drop the card;
  - the card is read from the newest log, with the same values as before: Zoya Chida, new
    patient, New Patient Consultation, Dr. Michael Sato, Richmond Care Center, 12 Oct at
    1 PM, booked, 3 options, one with Dr. Michael Sato;
  - a half-written last line is skipped;
  - the latest card is used, not the first.
- **One number changed:** the old real log had 13 lines. Some of those lines came from
  bot.py during a live call, and there's no live call here. The made-up log has 9 lines
  (one per stage and one per tool call). The test still checks that the viewer shows exactly
  as many events as the file has lines.
- **Two checks I added:**
  - the made-up newest log really is the newest before a newer call arrives;
  - the event count matches the file. Before, a comparison stopped quietly at the shorter
    list, so missing events could go unnoticed.

### Decisions 69 and 79
No older test needed changing for these. No old test looked at the greeting's `tts_say`
line, and none rejected the extra `description` and `usual_choice` fields.

## 3. Still failing

| Test | What kind of problem |
|---|---|
| `test_voice_values.py::test_start_booking_refuses_bad_identity_values[with letters-args4]` | Possible product gap (section 4) |
| `test_voice_values.py::test_start_booking_refuses_bad_identity_values[with letters-args6]` | Same |

**About `test_a_call_starting_during_saves_never_reads_half_a_file` (the Windows one):** it
passes here on Linux. I think the test is fine and the problem is a real one in the product
on Windows. The test's constant reloading just makes it happen far more often than in normal
use.

- **Why Windows is different:** on Windows, a file can't be swapped for a new copy while
  another part of the program has it open. While the swap is happening, the file also can't
  be opened. Linux and Mac allow both.
- **What the test does:** one part keeps loading the agent file in a tight loop, the way
  bot.py does at the start of every call. Another part saves the file 150 times. A crash can
  come from either side:
  - **The save side.** `_write_whole` in `editor_api.py` tries the swap up to 5 times,
    0.1 seconds apart, then gives up. If all 5 tries land while the file is being read, the
    save fails.
  - **The loading side.** `AgentBuilder.from_json` (used by bot.py) has no retry. If it opens
    the file in the middle of a swap, Windows refuses it. In real life, that means **a call
    that starts at the moment the editor saves could fail to load the agent.**
- **How to tell which side it was:** the error message on the owner's machine wasn't saved.
  If the error mentions `os.replace` or `_write_whole`, it was the save side. If it shows up
  inside the test's `failures` list, it was the loading side. The loading side is the more
  serious one, and the more likely one, since it has no retry. It's rare in real use, because
  calls start far less often than in this test. I didn't change product code.

## 4. Possible product bugs

**A new patient with spelled letters is accepted with no `full_name`, or with an empty one.**
Low severity.

- **Evidence:** both of these go through with `{"ok": true}` and move the call on to choosing
  a visit:
  - `start_booking` with `{"returning": false, "spelled_first_name": "F, A, R, H, A, N", "spelled_last_name": "J, I, D, A"}`;
  - the same with `"full_name": ""`.
- **Why it counts:** INTERFACE.md lists `full_name` as required (`Required: ['full_name', 'returning']`),
  and that's what the AI is told. The old test (no letters) still passes, but only because
  the call is refused for having no letters, not because the name is missing.
- **How much it matters:** the saved name comes from the letters, so nothing wrong gets
  saved. Review finding N10 (11 Oct) already said `full_name` isn't used for new patients.
  Its triage kept the field and rewrote its description, but didn't decide whether a missing
  one should be refused.
- **The owner should decide:** refuse a missing or empty `full_name` as the interface sheet
  says, or record that it's optional for new patients who sent letters. If it's optional,
  these two test cases should be updated to match that decision.

Nothing else I saw looked like a product bug. Every other old failure came from an agreed
change (decisions 66, 77 and 78) or from the machine's call logs.

## Update after the owner's decision (decision 92, 12 Oct)

The owner decided the possible bug in section 4. For a new patient whose name comes from
the spelled letters, `full_name` is not checked. A missing or empty one is accepted,
because the saved name is built from the letters. `full_name` is still needed for
returning patients, and for new patients marked "name not confirmed".

**What I changed:** only my 2 new cases in `test_voice_values.py`. These are the cases
"no `full_name`, with letters" and "empty `full_name`, with letters". They now expect the
call to be accepted. The test checks that the call moves on to choosing a visit, and that
the saved name is "Farhan Jida", built from the letters, for a new patient. The comment in
the test cites decision 92.

Every other case in that test still expects a refusal, including `full_name` 123 with
letters and all the "no letters" cases. Nothing else changed.

A note: decision 92 isn't in this copy's `docs/decisions.md` yet. I took it from the
coordinator's message.

**New totals (whole suite, Linux):** 0 failed, 4,095 passed, 0 errors (4,095 tests).
