# Test results: AI-played callers against three versions of the agent (and ours on a smaller model)

Built by `python -m evals.run results` from the saved runs in `runs/`. How the runs work, and why: `docs/decisions.md` 16, 20, 22, 68, 84-88. Each run is a typed call: an AI (gpt-4o-mini) plays the caller from a short persona; the agent is one of the versions below; the result is checked by code against what was saved.

**Reading the columns.** *Scenarios passed*: the expected outcome, checked in code. *Bad bookings*: saved bookings that break a booking rule for the real caller. *Input tokens*: what the AI read, from OpenAI's usage figures (a token is roughly 3/4 of a word); *cached* is the part OpenAI had already seen and charges half for. *AI passes*: each time the AI read everything and replied. *Slowest reply*: the longest time from the caller's line to the agent's whole answer, AI and tool time only (a voice call adds about 1 s of speech); worst run, and the middle run in brackets. *Agent cost*: the agent's AI only, not the AI playing the caller.

## All versions, on the same scenarios, each once (round 1)

| Version | Scenarios passed | Bad bookings | Input tokens per call | Input tokens per AI pass | Of which cached | AI passes per call | Slowest reply: worst (typical) | Agent cost per call |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1. Naive: whole catalog, no checks (gpt-4o) | 3 of 6 | 1 | 82,527 | 10,316 | 93% | 8.0 | 2.5 s (2.3 s) | $0.112 |
| 2. Naive + rule checks (gpt-4o) | 4 of 6 | 0 | 78,923 | 10,294 | 96% | 7.7 | 3.2 s (2.1 s) | $0.105 |
| 3. Ours: stages and small slices (gpt-4o) | 5 of 6 | 0 | 22,671 | 2,159 | 72% | 10.5 | 3.9 s (3.1 s) | $0.039 |
| 3b. Ours on the smaller model (gpt-4o-mini) | 5 of 6 | 0 | 27,627 | 2,181 | 87% | 12.7 | 3.9 s (3.1 s) | $0.003 |

## Passes by scenario (all runs)

| Scenario | 1. Naive | 2. Naive + rule checks | 3. Ours | 3b. Ours on the smaller model |
| --- | --- | --- | --- | --- |
| New patient: a skin check with Dr. Garcia (no Garcia does skin checks) | 0 of 1 | 0 of 1 | 1 of 1 | 1 of 1 |
| New patient: a knee MRI (needs a referral; existing patients only) | 0 of 1 | 1 of 1 | 1 of 1 | 1 of 1 |
| James Wilson: a knee MRI near Downtown (only 2 valid doctor-place pairs) | 1 of 1 | 1 of 1 | 1 of 1 | 1 of 1 |
| James Wilson: a Garcia skin check, then 'actually, a knee MRI' | 1 of 1 | 1 of 1 | 1 of 1 | 1 of 1 |
| New patient: a check-up with Dr. Maria Garcia (there are two) | 0 of 1 | 0 of 1 | 0 of 1 | 0 of 1 |
| New patient: an OB/GYN visit (no OB/GYN takes new patients), then 'a person' | 1 of 1 | 1 of 1 | 1 of 1 | 1 of 1 |

## The check-in after the read-back (decision 71)

James Wilson's knee MRI, with 'Are you still there?' after the read-back: **pass**

## Every failed run, and why

- 1. Naive: whole catalog, no checks (gpt-4o), garcia_skin_check, run 1: A booking breaks the rules: Dermatology Consultation needs a referral to Dermatology, and there isn't one on file. Dr. Maria Garcia doesn't offer Dermatology Consultation. Booked visit type appt_026, expected one of appt_027, appt_028. Booked doctor prov_003, expected one of prov_001, prov_027, prov_035.
- 1. Naive: whole catalog, no checks (gpt-4o), knee_mri_new_patient, run 1: Promised staff would follow up, but the call wasn't handed to staff: "A member of staff will call you back to discuss your options further."
- 1. Naive: whole catalog, no checks (gpt-4o), maria_garcia_checkup, run 1: Booked under the name "New Patient", not "Priya Nair". Booked doctor prov_002, expected one of prov_003.
- 2. Naive + rule checks (gpt-4o), garcia_skin_check, run 1: Booked under the name "Unknown", not "Lena Park".
- 2. Naive + rule checks (gpt-4o), maria_garcia_checkup, run 1: Booked under the name "New Patient", not "Priya Nair". Booked doctor prov_002, expected one of prov_003.
- 3. Ours: stages and small slices (gpt-4o), maria_garcia_checkup, run 1: Booked visit type appt_001, expected one of appt_002, appt_003.
- 3b. Ours on the smaller model (gpt-4o-mini), maria_garcia_checkup, run 1: Booked doctor prov_002, expected one of prov_003.

## What else differs, besides what each version is given

Said here so nobody has to find it in the code (independent review, 12 Oct, R7 and R15):

- **Ours spells new patients' names back** letter by letter (decisions 59, 77). That's extra turns and tokens the naive versions don't spend.
- **Ours ends the call itself** after its goodbye; the naive versions can't, so a caller who says goodbye without hanging up can cost them one more AI pass.
- **Searching**: ours finds valid options in one code call; the naive versions' find_open_times returns times for one doctor, or for every doctor the catalog lists for a visit type, with no rule checks.

## How these typed calls differ from a voice call

- No speech: no mishearing, no talking over each other, no silence (the check-in is said by the loop in one run only).
- Timing is to the whole written reply; in a call the voice starts after the first sentence, and speech adds about 1 s.
- When the AI says something and calls a tool in one reply, the loop keeps them as two messages; Pipecat may keep one. A few tokens.
- If the AI asks for two tools at once (it's told one at a time), the loop runs the first and notes it.

## Spending

$1.60 of the $7.00 stop (decision 84): gpt-4o $1.57, gpt-4o-mini $0.03.
