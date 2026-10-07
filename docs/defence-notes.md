# Defence notes

For Farhaan, before the review call. Part 1 explains how the rules module works, in plain words, by following one phone call. Part 2 lists the questions an interviewer is likely to ask, with short answers. If any answer doesn't make sense to you, say so: per `process.md`, it gets simplified or explained before we move on.

This covers **version 0.1.0** (the rules module). Later steps will add their own sections.

---

## Part 1: how it works, following one call

**The caller:** "Hi, I'm Emily Brown, born 19 January 1988. I need a skin check with Dr. Garcia, near Downtown, Thursday morning if possible."

1. **Who is calling.** The AI passes the name and date of birth. The code looks for a returning patient with exactly that name *and* birthday.
   - If it doesn't find one, it says the same "Sorry, I couldn't find you" whatever was wrong, so it never gives away whether a name exists.
   - Second miss: it asks the caller to spell their last name.
   - Third miss: it offers to register them as a new patient or put them through to staff.
2. **What kind of visit.** The AI picks "Dermatology" from the 21 specialty names. The code lists the skin visit types. For each one it says whether *this* caller can book it, and if not, why (needs a referral, not open to new patients, nobody offers it).
3. **Who, where, when.** The AI fills in the caller's wishes as plain values:
   - doctor: "Dr. Garcia";
   - place: "Downtown", near = yes;
   - day: "Thursday";
   - time of day: "morning".

   The code then:
   - works out every doctor + location pair that passes all six rules for Emily;
   - drops pairs with no open time in the next 2 weeks;
   - applies her wishes one at a time, newest first, each only if something still survives it.

   No Dr. Garcia does skin checks. So instead of a wrong booking (the baseline agent's mistake), the AI gets a true note: "No doctor matching 'Dr. Garcia' can do this: Dr. Maria Garcia (Pediatrics), … don't offer Skin Cancer Screening. Doctors who can: Dr. Daniel Chen (Dermatology), …". It also gets up to 3 options that are already valid, ranked by distance from Downtown, all on Thursday mornings if possible.
4. **The caller changes their mind.**
   - **"Actually, a knee MRI."** `change_choice` clears what depended on the old visit (the doctor, place and time) and goes back to the visit stage. The old doctor and place stay only as weaker wishes, and if they no longer fit, a note says so. Nothing is kept or dropped silently.
   - **"Someone else, please."** The AI calls `turn_down_doctors`, saying exactly who (the doctors on offer, or the current one). Those doctors are left out of later searches, unless nobody else can do the visit, in which case a note says so.
5. **Confirm.** When the caller picks option 2, `choose_option` puts exactly that doctor, place and time on the card. The read-back sentence is built from the card, not from the AI's memory, so what the caller hears is what gets saved. A final check runs all six rules again and makes sure the time is still free.

**The one rule for what the AI sends:**
- Names (doctors, places, languages) are matched forgivingly against our records, because the AI doesn't know our clinics.
- Two fixed word lists are read: "no preference" words count as empty, and words no name has ("not", "another", "please") are refused.
- Everything else is a plain value (an id, yes/no, a weekday or date, morning or afternoon).
- Anything else is sent back to the AI with a note saying how to send it. The caller never hears that note; the AI just tries again.

---

## Part 2: likely questions

### The approach

**Why not just paste the catalog into the AI's instructions?**
Accuracy first, cost second. The baseline agent, with no catalog at all, sounded right and was wrong four times in one call. With the whole catalog pasted in, the AI still has to apply six rules across 50 doctors and 82 visit types in its head, on every reply. At the scale in the brief (about 2,000 doctors) the catalog is about 175,000 tokens, more than GPT-4o can take at all. Our AI only ever sees a small slice: the card, one specialty's visit types, three options. That stays the same size at any catalog size.

**Why does the code check the rules instead of the AI?**
Because the AI forgets and guesses, and code doesn't. The AI is never even shown an option that breaks a rule, and a final check runs before anything is saved. So it *can't* book something invalid.

**How do you know the notes the agent reads out are true?**
Every note is checked against all the valid options before it's written. The independent testers then checked them across the whole catalog: every visit type, several kinds of caller, every place, language and day. That's thousands of combinations, not a few examples. That's how they found notes that named the wrong doctors (rounds 4–5), which we fixed.

### The design choices that changed

**Why does the code refuse "someone else" or "not Dr. Chen"? Isn't that worse for the caller?**
The caller never hears the refusal; the AI does. We tried letting the code read phrases like "someone else, please", and four review rounds in a row found a new way it broke. For example, "No, not Dr. Chen" became a wish *for* Dr. Chen. Understanding speech is the AI's job; following a clear instruction is the code's job (decision 23). So the AI now says exactly what it means ("turn down the doctors on offer"), and the code follows it exactly. At worst a mistake costs one extra AI step, never a wrong booking.

**You said decision 23 from the start. Why did the code drift away from it?**
An honest answer: in round 3 a reviewer asked for everyday time phrases like "this afternoon" to work. We added them to the code instead of to the AI's instructions. Each new phrase brought new bugs. Rounds 4–7 took it back to the principle: days, times, "near" and turning doctors down are all plain values now. It's a good example of why independent review matters. The drift was gradual, and each step looked reasonable.

**Isn't matching names "reading the caller's words" too?**
No. Matching a *name* against our own list is something only the code can do, because the AI doesn't know our 50 doctors or 8 clinics. "Garsha" still finds Garcia; "Midtown" finds Midtown Medical Group. What the code doesn't do is work out *meaning* from a sentence ("near", "not", "someone else").

**How do you handle misheard names?**
Every match says how good it is: exact, close spelling, or "sounds alike". Anything less than exact comes with a "check with the caller" note. Names that fit several doctors (two Dr. Maria Garcias) list them all, with their specialty, and their places when that's needed to tell them apart, so the agent asks "which one?". Phrases passed by mistake as a name ("another doctor" once matched Dr. **Andre** Patel by sound) are refused before matching.

### Data and assumptions

**What did you fake, and why?**
- Patients, referrals and open times. The brief gives none, and the rules depend on them.
- Map coordinates and neighbourhoods. The catalog can't answer "near Downtown", and its addresses contradict its names.

Open times come from a fixed recipe, so every run gives the same answer and tests are repeatable.

**What assumptions did you make?**
- "New patient" means new to the clinic group, not to that doctor (decision 27).
- A referral covers a whole specialty (28).
- A doctor with several sites is at one site per working day.
- Lunch 12–13 is blocked.
- Bookings need 2 hours' notice and are offered 14 days ahead.

The catalog says nothing about any of these. Each is the simplest reading that fits the data, and each is written down.

**Why "name and date of birth" for returning patients?**
In round 1, "Mr. Wilson" found James Wilson, and "Robert Tyler" got Robert Taylor's record. That's a privacy problem in healthcare. Now nothing is looked up without both, and every miss gets the same reply, so the agent never reveals whether a name exists.

### Testing and process

**Who wrote the tests?**
There are two separate sets:
- **The builder's own tests (276).** These were written by the same AI that wrote the code.
- **Independent tests (2,848).** These were written by fresh AI agents that never saw the build conversation. They worked out the expected answers from the plan and the raw data, not from the code.

The builder never edits an independent test. When the builder thought 8 tests were wrong, a fresh verifier decided. It ruled 6 of them were real bugs, so the builder was wrong, and that's recorded.

**Seven review rounds sounds like a lot. Over-engineering?**
Each round found real problems, and we stopped when a round came back clean. Round 1 found false notes on the demo path that 30 builder tests had missed. Round 5 found a crash. For a healthcare booking agent, "sounded right but was wrong" is the failure we're trying to prevent, so the checking is the product, not decoration. It also used about a day of the week, which is why the voice wiring moved by a day.

**After a design change, lots of old tests failed. How do you know that was expected and not a bug?**
We proved it each time. A throwaway adapter played the AI's part: for example, it turned "near Downtown" into place = Downtown, near = yes. Then we reran the testers' unchanged tests. Whatever still failed was listed one by one. This caught the builder's own mistakes twice.

**What's "AI slop", and how did you avoid it?**
Code that looks finished but isn't:
- dead code;
- the same rule written in three places;
- comments that don't match the code;
- unexplained magic numbers;
- features half built.

The reviewers had a checklist for exactly this, and the triage files show each case found and fixed. Examples:
- the same rule written four times;
- three separate "no preference" lists;
- a leftover word list after a redesign;
- a space-tidying line copied 11 times.

### Scale and limits

**Does it scale?**
On a generated catalog with 500 locations and 2,000 doctors, a search takes about 0.2–0.6 s, and on the real catalog under 10 ms. What the AI sees doesn't grow. Half a second is noticeable in a voice call, so at that scale I'd precompute which doctor-location pairs are valid for each visit type and caller kind, which is most of the work. The full scale test is planned for Sat 10.

**What isn't done yet?**
These are the next step:
- the voice agent's tools and stages, which call this module;
- saving bookings to a file;
- the editor.

The module already has all the logic the tools need.

**What would you do differently?**
- Hold decision 23 strictly from day one, and put phrase handling in the AI's tool descriptions, not in code.
- Write whole-catalog "every note is true" tests from the start. They found more than the example-based tests did.
