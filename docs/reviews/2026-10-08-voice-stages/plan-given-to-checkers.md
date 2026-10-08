# Phase 2 plan: context management (v2, locked 5 Oct)

(Copied from the project's planning documents for this review. Where a later decision in docs/decisions.md changes something here, the decision wins; the main ones are listed at the end.)

---

## The core idea

**The AI never holds the catalog. It holds a small "booking card," and the code holds the catalog.**

- The **catalog** lives in plain Python code. The AI only sees small, relevant slices of it, returned by tools or pasted into a stage's instructions when it starts.
- The **booking card** is a small record kept by the code. The AI can only change it through tools, and the code checks every rule before accepting a change.
- The AI is only ever **offered options that are already valid for this caller**. Impossible combinations never reach it, so it can't pick one.

Three guarantees that come from this, and that the demo shows:
1. **It can't book something that breaks a rule.** The code says no.
2. **What's saved always matches what was said.** The read-back is built from the booking card, not the AI's memory.
3. **What the AI sees stays about the same size whether there are 8 locations or 800.** Only the code's search does more work.

---

## The booking card

```
caller:
  name
  patient_id            (fake record, or none if new)
  is_new_patient
  referrals_on_file     (list of specialties)
preferences:            (what the caller asked for, kept across stage moves)
  visit_description     ("knee MRI", "skin check")
  doctor_name_heard     ("Dr. Garsha")
  location_hint         ("near Downtown")
  day_or_time           ("Tuesday morning")
  soonest               (yes/no)
  language
choices:                (filled only when the code accepts them)
  specialty
  visit_type_id
  provider_id
  location_id
  slot
status:                 in_progress | booked | handed_off
```

**Why the preferences section matters:** moving stage wipes the conversation history. Anything the caller said that matters later goes on the card, so it survives the move.

---

## The stages (3 plus an end)

### Stage 1: Identify
- Get the name, whether they're new or returning, and what they want to do.
- Returning → look up the fake patient record (gives referrals on file). Reschedule or cancel → polite hand-off to the end stage.
- **Tool `start_booking(name, is_returning, any details mentioned)`:** stores the caller and any preferences, then moves to stage 2.

### Stage 2: What do you need? (two-level lookup)
- The stage's instructions include the **21 specialty names** and the caller's own words.
- **Tool `list_visit_types(specialty)`** (stays in the stage): the code returns *every* visit type in that specialty (never more than about 7), each marked with:
  - needs a referral? open to new patients?
  - **can THIS caller actually book it?** (checks there's at least one valid doctor and location for them)
  - if not bookable, the plain reason ("no doctor currently offers this," "needs a referral, none on file," "no doctor is taking new patients for this").
- The AI helps the caller pick, including between look-alikes.
- **Tool `choose_visit_type(id)`:**
  - **Rejected** → stays in stage 2 with the reason and alternatives (for example, a new-patient visit with a family doctor). The agent never promises that visit produces a referral.
  - **Accepted** → the code **immediately fetches the first options** using the caller's preferences, and moves to stage 3 with those options already in its instructions (saves a full AI round trip).

### Stage 3: Who, where, when, and confirm
- The instructions arrive with **up to 3 valid options** (doctor + location + time slot), plus plain notes on any preference that couldn't be met:
  - "No Dr. Garcia offers skin checks. Dermatologists available: …"
  - "There are 2 Dr. Maria Garcias: Pediatrics at X, Family Medicine at Y."
- **Tool `find_options(preferences)`** (stays): when the caller wants something different ("anything Thursday?", "a Spanish speaker?"). *(Replaced by decision 43: changes go through change_choice.)*
- **Tool `choose_option(id)`** (stays): locks it onto the card and returns a **code-built read-back** for the agent to say and ask "shall I book that?"
- **Tool `confirm_booking()`:** a final full rule check, saves the fake booking, and moves to the end stage.
- Confirm is folded into this stage to save a move.

### End stage
- Says goodbye (with the booking summary, or the hand-off message) and ends the call.

### Always available, in every stage
- **`answer_question(about, name)`:** facts about a location (address, hours, phone, neighbourhood), a doctor (specialty, languages, locations, new patients?), or a visit type (referral? duration?). Small results only. Stops the agent making things up.
- **`change_choice(what, new_value)`** (Farhaan's MRI catch): clears that choice **and everything that depended on it**, records the new value as a preference, and jumps to the right stage:

| Caller changes… | Code clears | Goes to |
| --- | --- | --- |
| visit type | visit type, doctor, location, slot | stage 2 |
| doctor | doctor, slot (and location, if the new doctor doesn't work there) | stage 3, fresh options |
| location | location, slot (and doctor, if they don't work there) | stage 3, fresh options |
| time | slot | stage 3, fresh options |

### Safety setting
- **Parallel tool calls are turned off**, so two tool calls in one reply can't overwrite each other's stage move.

---

## What the AI sees at each stage

- persona (a few lines)
- this stage's instructions, **built at the moment of the move**, with the booking card and any pre-fetched options pasted in
- the conversation **within this stage only**

**History is reset on every stage move** using Pipecat Flows' plain "reset" setting. We don't use "reset with summary": it's deprecated, and it costs an extra AI call of up to 5 s per move.

---

## Search

- **Visit types:** two-level. The AI picks a specialty from the 21 names, then the code lists that specialty's types. No hand-written phrase list.
- **Doctor names:** forgiving spelling match, so "Garsha" still finds Garcia. Always return *all* matches for duplicate names, with specialty and location, so the AI can ask "which one?"
- **"Near X":** fake coordinates plus a neighbourhood name for each of the 8 locations. *(Decision 39: near is a yes/no the AI passes with a place name.)*

---

## What we fake (and why)

| Thing | How | Why |
| --- | --- | --- |
| Patient records | A small file of about 6 returning patients, some with referrals on file | Rules depend on new/returning and referrals; there's no patient system |
| Referrals | On the fake patient record; new callers have none | Rule 4 needs something to check |
| Open slots | Generated by code per doctor and location, within opening hours, over the next 2 weeks, the same every run | Availability isn't provided; tests must be repeatable |
| Coordinates and neighbourhoods | Added per location in our own file | The real data can't answer "near Downtown" |
| The booking | Saved to a local file | No real calendar |
| Reschedule / cancel | Recognised, then handed off | Out of scope |

---

## Speed budget

Every tool call costs about 2 AI passes (about 2.5 s for that reply). No reply should need more than 2 passes.

---

## Changes to the agent format

The editor must show what actually runs:
- **Per stage:** `tools` (names of tools that stay in the stage), and instructions that can contain placeholders filled at move time (`{booking_card}`, `{options}`, `{specialties}`).
- **Per agent:** `global_tools` (always available: answer_question, change_choice).
- **Moves decided by code** (change_choice jumps, a rejected choose staying put) are listed in the tool registry and drawn as **dashed arrows** in the editor.
- **The tool registry:** a Python list of available tools with their descriptions and possible destinations.

---

## Demo script (what the live call must show)

- "Skin check with Dr. Garcia" → "None of our Dr. Garcias do skin checks. I can offer Dr. X or Dr. Y in dermatology."
- "Actually, a knee MRI" → the doctor is cleared, and the agent asks about a referral. As a returning patient with a referral, it offers the 2 valid options.
- Book it. The read-back matches the booking card exactly.

---

## Later decisions that change this plan (details in docs/decisions.md)

- 32, 36: returning patients give full name + date of birth; identity steps: try again → spell the last name → offer to register as new or speak to staff; same name and birthday → staff.
- 37: turning doctors down is its own instruction (`turn_down_doctors`), never a phrase in a name field.
- 38: days and times are plain fields: each day entry is one weekday, "today", "tomorrow" or a date; time of day is "morning" or "afternoon".
- 39: "near" is a yes/no passed with a place name.
- 40: the rule for what comes in from the AI (see backend/clinic/__init__.py's docstring).
- 43: no find_options tool; every change goes through change_choice; in the booking stage every change rebuilds the stage with fresh options.
- 45: a call log file per call. 46: hand_off in every stage. 47: wishes travel with start_booking and choose_visit_type; change_choice in stages 1–2 records without moving. 48: bookings saved one per line and reloaded at start-up. 49: tools in plain Python (backend/call/), Pipecat only in agent_builder/, load-time checks of the agent file.
