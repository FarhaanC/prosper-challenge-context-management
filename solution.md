# Solution: Farhaan Chida

## Where this started

Before writing any code I rang the sample agent and played an awkward caller. I asked for a skin check with Dr. Garcia, switched to a knee MRI halfway through, and asked for somewhere "closer to downtown". The agent was friendly and quick, and it got five things wrong:

- No Dr. Garcia in the catalog does skin checks.
- A knee MRI needs a referral and isn't open to new patients. It booked one anyway.
- When I switched to the MRI it quietly dropped Dr. Garcia, without saying why.
- It made up an answer about downtown.
- The record it saved still said "skin check", although it had just told me "MRI on your knee".

It sounded confident the whole way through and still booked the wrong thing. For a clinic that's worse than an agent that's slow or awkward but correct. So my first goal was that the agent can't book anything that breaks the clinic's rules, and that what's saved always matches what the caller was told. Cost came second.

## The approach

The main change from the sample agent is that the catalog isn't in the AI's prompt. The AI gets a short booking card (who's calling, which visit, what they've asked for so far), and my code does all the catalog lookups.

A call goes through three stages: who's calling, what kind of visit, then who/where/when and confirm. At each stage the AI only sees a small slice. In the visit stage that's one specialty's visit types, each marked as bookable for this caller or not, and why. In the booking stage it's up to three options, each a doctor, a place and a time. Every doctor, place and time it's offered already passes all six booking rules. On every stage move the conversation is wiped and the next stage's instructions are rebuilt from the card, so anything the caller said that matters later lives on the card rather than in the chat history.

I split the work like this: the AI works out what the caller means, and the code only accepts plain values from it. Doctor and place names are matched forgivingly against our records ("Dr. Garsha" still finds Garcia). Everything else is an id, a date or a word like "morning". The code checks every rule, owns what gets booked, and builds the read-back itself, so the caller hears exactly what's saved.

When the caller changes their mind ("actually, a knee MRI"), the code clears everything that depended on the old choice and searches again. If the old doctor can't do the new visit, the caller is told. That came straight from the MRI switch on my first call.

## The booking rules

The catalog comes with six rules. The code checks all of them; none is left to the AI to remember.

| # | Rule | Example from this catalog |
| --- | --- | --- |
| 1 | A doctor can only be booked at a location they work at. | Dr. Linda Ramirez works at Mission Bay and Downtown only. |
| 2 | A doctor can only be booked for visit types they offer. | No Dr. Garcia offers a skin check. |
| 3 | A visit that needs equipment can only be booked where that equipment is. | A knee MRI needs imaging, which only 3 of the 8 locations have. |
| 4 | A visit that needs a referral needs one on file first. | 36 of the 82 visit types need a referral. |
| 5 | New patients can only book visits open to new patients, and only with doctors taking new patients. | A knee MRI is for existing patients only, and the one OB/GYN doctor isn't taking new patients. |
| 6 | A doctor who works at several locations needs the location settled before booking. | 34 of the 50 doctors work at more than one place. |

The rules are checked in two places. First, when the code builds the options for the AI, it only includes doctor, place and time combinations that pass all six, so the AI is never offered a wrong one. Rule 6 is built in: every option is a doctor, a place and a time together. Second, a final check runs all six again just before anything is saved, and also checks the time is still free.

The data didn't answer two questions, so I made a call on each and wrote it down:
- "New patient" means new to the clinic group, not new to that doctor. The catalog has one yes/no per doctor and no history of who has seen whom.
- A referral is stored by specialty. A radiology referral covers every radiology visit that needs one, because the catalog has no more detail than that.

## Results

To check it works, I tested it against simpler versions.

I couldn't make 70 phone calls myself, so a second AI played the caller, over text. Each fake caller had a short script, like: "You're new here. You want a skin check with Dr. Garcia. If Garcia can't do it, any skin doctor is fine."

After each call, my code looked at what actually got booked. Was it the right visit, the right doctor, under the right name, and did it follow the rules? What the agent *said* didn't count, only what it saved.

I wrote six of these callers. Each one hits a tricky spot in the catalog, like a doctor who doesn't do that visit, or two doctors with the same name. Each caller rang each version three times.

The four versions:
1. Simple: the whole catalog pasted in, and it books whatever the AI asks for.
2. Simple plus my rule checks: the same, but a booking that breaks a rule is refused.
3. My design, as described above: the call goes in three steps, the AI only sees a small slice of the catalog at each step, and the code offers only valid choices, checks the rules and saves the booking. It runs on gpt-4o, the same AI model as versions 1 and 2.
4. My design again, but on gpt-4o-mini, a cheaper and faster AI model, to see whether it holds up.

Why have version 2 at all? My design changes two things at once. First, the AI only sees a small part of the catalog at each step instead of all of it. Second, the code checks the rules before anything is booked. A reviewer could fairly wonder whether the second change is doing all the work, and the first adds nothing. Version 2 answers that: it's the simple version with only the second change added. If version 2 did as well as my design, the step-by-step part would be pointless.

To keep the comparison fair, all four versions got the same tools for looking up patients and finding free appointment times.

| Version | Calls passed (of 18) | Bookings that broke a rule | AI input per call | Cost per call |
| --- | --- | --- | --- | --- |
| 1. Simple | 11 | 2 | ~82,600 tokens | $0.110 |
| 2. Simple + rule checks | 11 | 0 | ~82,200 tokens | $0.109 |
| 3. My design (gpt-4o) | 17 | 0 | ~23,000 tokens | $0.039 |
| 4. My design (gpt-4o-mini) | 16 | 0 | ~28,600 tokens | $0.003 |

"AI input" is how much text the AI had to read over the whole call, in tokens (a token is about three-quarters of a word). It's what OpenAI charges for. The full tables and every call, word for word, are in `docs/results/2026-10-12-testing/`.

Adding rule checks to the simple version stopped its two rule-breaking bookings, but it still passed only 11 of 18, because most of its mistakes broke no rule at all:
- James Wilson asked for a knee MRI and got booked for a spine MRI. He has a radiology referral, so it's a valid booking, just not the one he asked for. The agent told him "Your MRI appointment is confirmed."
- It told him "You're confirmed for a knee MRI… today at 11 AM" and never called the booking tool, so nothing was saved.
- The simple versions saved bookings under "Unknown", "New Patient" and "Caller".
- A new patient's yearly check-up went to the children's Dr. Maria Garcia.

My design can't save a booking that breaks a rule, can't say "confirmed" without saving, and builds a new patient's name from the letters they confirmed. It can still pick the wrong valid option. The children's-doctor mistake above is the one my agent made too (see "What's weak").

On cost, my design reads about 3.6 times less per call. OpenAI charges half price for text it has already seen, and the simple version's prompt is mostly the same catalog every time, so the price gap is smaller: about 2.8 times. At this catalog size the simple version still only costs about 11 cents a call. So with 50 doctors the case for my version is mostly accuracy. Size starts to matter once the catalog grows (next section).

It's a bit slower at its worst moments, though:
- In a typical call, the slowest reply took 2.7 s, against 2.2 s for the simple version.
- In the worst run, it was 4.0 s against 2.7 s.
- On gpt-4o-mini, it was 5.2 s at the worst.

The slow turns are the ones where the call moves on: the AI calls a tool, the code searches, and the next stage answers, which takes two AI passes. These timings are for the typed reply only. On my real voice calls, the wait from me stopping to the agent starting was 1.2 to 2.7 s.

The smaller model passed 16 of 18 for about a thirteenth of the price. I haven't switched to it yet, for the reason in "What's weak".

## Would it still work at 2,000 doctors?

I generated a catalog with 500 locations and 2,000 doctors: the real 8 locations and 50 doctors plus made-up ones, with the same visit types and rules.

| | Real catalog | 500 locations, 2,000 doctors |
| --- | --- | --- |
| My design: instructions per step | ~2,000 characters | the same |
| My design: AI input per pass, in the test calls | ~2,150 tokens | ~2,000 tokens (2 calls, both passed) |
| Simple version: what the AI reads each pass | ~10,300 tokens | 235,181 tokens, refused (gpt-4o's limit is 128,000) |
| The code's search for options | 1 to 8 ms | 31 to 309 ms |

The simple version's figure is measured. It's the count OpenAI gave back when it refused the request.

My agent doesn't get bigger as the catalog grows, because it only ever sees one specialty's visit types and three options. The extra work lands in the code's search, which gets slower. A third of a second is fine on a phone call, and it could be indexed. If the list of specialties ever got too long to show the AI, I'd group them or search over their names. I didn't build that; this catalog has 21.

## The editor (Phase 1)

The agent is a JSON file (`backend/clinic_agent.json`), and the editor (`frontend/`, React and React Flow) edits it. Stages are boxes. Solid arrows are moves the AI makes, and dashed arrows show where a tool's code can send the call; a change of visit goes back to the visit stage, for example. A side panel edits a stage's instructions and tools, or the agent's persona, model and voice.

Save runs the same checks the voice agent runs at start-up, so you can't save a file that would break a call. Test call opens the call page beside the editor. Underneath it, the inspector follows the call live: the stage, the booking card, every tool call, and the tokens of every AI reply. I checked the loop on a real call: I added a line in the editor, saved, rang the agent and heard the new line.

I kept the editor plain on purpose. The brief says judgement matters more than polish, and the editor is where time disappears.

## What I faked, and why

| Thing | How | Why |
| --- | --- | --- |
| Patients | 6 returning patients in `backend/data/patients.json`, some with referrals on file | The rules depend on new versus returning and on referrals, and there's no patient system |
| Open times | Generated by a fixed recipe: the same every run, two weeks ahead, about half already taken | No availability was provided, and tests have to repeat |
| Locations on a map | Made-up coordinates and neighbourhoods, in a separate file | The data can't answer "near Downtown": North Beach Specialty Center is on Mission St |
| Look-alike visits | One-line descriptions for 9 groups (Skin Cancer Screening vs Full Body Skin Exam, for example) | The catalog gives two of them identical data, and callers say "a skin check" |
| The booking | One line per booking in a local file | No real calendar |

## Choices I'd defend, and one I changed my mind on

- Three stages, not more. Every stage move costs an extra AI pass, about a second of silence. Who/where/when share a stage because callers say them together ("Dr. Chen, Thursday morning, near Downtown").
- Finding the right kind of visit in two steps. There are 82 kinds of visit, too many to show the AI at once. So first the AI picks which kind of doctor the caller needs, from a list of 21 (skin doctor, heart doctor, family doctor and so on). Then it only sees the visits that kind of doctor offers, usually five or six. I first tried matching the caller's words against the visit names, but people say things like "stomach pain" or "something for my heart", which don't match any name. The AI is good at turning those into the right kind of doctor.
- The code, not the AI, reads the booking back before confirming ("Knee MRI with Dr. Ramirez at Downtown, Tuesday at 11 AM. Shall I book it?"). The sentence is built from what's about to be saved, so the caller always hears exactly what gets booked. It's also faster, because the AI doesn't have to think up the sentence.
- Changing or cancelling an existing booking goes to staff. In this demo there's no safe way to find a new patient's booking: they're not in the patient records, and we don't take their date of birth. In a real system I'd tie each booking to the caller's phone number. When they ring back, the number finds their bookings, and a quick check (name or date of birth) confirms it's them before anything changes. I left that out because the demo has no phone numbers to work with (calls come from a browser), and building find, change and cancel properly would have cost about half a day.

The one I changed my mind on: early on, my code tried to read the caller's phrases ("someone else please", "Thursday or Friday, mornings"). Review round after review round found a new way it broke; "No, not Dr. Chen" once became a wish for Dr. Chen. In round 4 I changed the rule: the AI works out what the caller meant, and the code only takes plain instructions ("turn down the doctors on offer", days as dates). It took until round 7 to remove the last places the code was still reading phrases, but that kind of bug hasn't come back since.

## What's weak

My three failed calls were all about the two Dr. Maria Garcias, and they show the limit of the approach:
- gpt-4o once offered only first-visit types when the caller asked for a yearly check-up.
- gpt-4o-mini twice offered "Dr. Maria Garcia, MD or Dr. Maria Garcia, NP" without saying that one is a children's doctor, and the caller picked the wrong one.

So the code stopped every booking that broke a rule, but it didn't stop the agent booking a valid visit the caller didn't want. The first thing I'd try is having the code write the "which one?" question itself, the way it already writes the read-back.

Other things I know are weak:
- The tests are typed, not spoken, so there's no mishearing and no talking over each other. I covered that with real voice calls, which found things no test did:
  - a 6-second silence before the greeting;
  - the speech service writing my name in Russian;
  - a late draft from speech-to-text cancelling the agent's answer, which left 25 seconds of silence.
- The caller in the tests is also an AI, so a couple of fails are partly the caller's choice. Every call is saved, so you can judge for yourself.
- Names over the phone are slow. A new patient spells their name, then spells it again with a word per letter if needed. On one call that took two minutes. In production I'd text them a short form instead.
- Searches go by morning or afternoon, not by the hour. "Around 11" is searched as morning, and the caller is told so.
- One call at a time. The bookings file isn't safe for two calls booking at once. Fine for a demo, not for a clinic.

## What I'd do next

1. Have the code write the "which one?" question for look-alike doctors and visits, then run the tests again, especially on gpt-4o-mini. If it then passes as often as gpt-4o, I'd switch, since it costs about a thirteenth as much.
2. Run the test scenarios through the real voice pipeline, with synthetic speech, to catch what typed tests can't.
3. Replace the fake open times with a real scheduling system, and the fake patients with a real lookup.

## How I built it

I planned this myself. I made the first test call that showed what was wrong, worked through the catalog to find its traps, chose the approach, and wrote the plan and the rules for how the agent should behave. I used Claude to help write the code, which Prosper allows, and I reviewed the code and made every decision that changed how the agent behaves. I also made the real voice calls, and those found problems no test could, like the 25 seconds of silence.

With AI-written code, the risk is that it looks finished and isn't, and that the same AI then checks its own work. So after each piece was built, a separate AI that hadn't seen it being built wrote its own tests from my plan and the raw data, and reviewed the code. I went through what they found and decided what to fix. This caught real bugs, for example:
- "Chinatown clinic" being read as "near Chinatown";
- a greeting that jammed the call if you talked over it;
- a test runner that would have charged me twice for the same call.

Every decision is written down with its reason in `docs/decisions.md`, and the reviews are in `docs/reviews/`. The git history has a save at every step, so you can see how the work actually went.

There are about 4,100 automated tests. On my Windows laptop 4,093 pass and 1 fails; on Linux all of them pass. The one that fails saves the agent file from the editor over and over while calls keep starting, and Windows sometimes won't let a file be read while it's being replaced. In real use that only matters if someone saves in the editor at the exact moment a call starts. The fix is a short retry when the file is loaded, and it's next on my list.

## Running it

From the repo root (on Windows, the README has the commands without `make`):

```bash
make install
make run                      # then open http://localhost:7860/client to call the agent
```

- The editor: `cd frontend && npm install && npm run build`, start the agent as above, then open http://localhost:7860/editor.
- Tests: from `backend/`, `python -m pytest -q`.
- The comparison: from `backend/`, `python -m evals.run plan`, then `smoke`, `round1`, `round2` and `round3`. It needs an OpenAI key and stops itself at $7. My full set of runs, all four versions plus the scale test, cost $4.85.
- The scale test: `python -m evals.scale`.

More detail in `docs/`:
- `decisions.md`: every decision and why;
- `build-log.md`: what was built, step by step, and what each step taught me;
- `reviews/`: the independent checks;
- `results/2026-10-12-testing/`: the test results and every call.
