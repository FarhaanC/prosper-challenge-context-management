# Scale test

Made by `python -m evals.scale` (see the top of `backend/evals/scale.py`).

Catalogs: the real one (50 doctors, 8 locations) and a made-up big one (2000 doctors, 500 locations), both with 82 visit types and the same rules.

## What the AI is given

| | Real catalog | Big catalog |
| --- | --- | --- |
| Ours, identify stage (characters) | 2,077 | 2,077 |
| Ours, visit_type stage (characters) | 2,215 | 2,215 |
| Ours, booking stage (characters) | 1,813 | 1,799 |
| Naive, its one set of instructions (characters) | 34,922 | 764,937 |
| Naive, in tokens (big: measured by OpenAI's refusal) | | 235,181 |

gpt-4o reads at most 128,000 tokens per request.

## The code's search (choose_visit_type, which finds the options)

| Search | Real catalog | Big catalog |
| --- | --- | --- |
| James Wilson's knee MRI near Downtown | 1.1 ms | 30.6 ms |
| A new patient's skin check with Dr. Garcia | 2.4 ms | 80.0 ms |
| A new patient's check-up with Dr. Maria Garcia | 7.7 ms | 308.8 ms |

## Ours on the big catalog (real AI, one run each)

| Scenario | Result | AI passes | Input tokens per call | Input tokens per AI pass |
| --- | --- | --- | --- | --- |
| garcia_skin_check | pass | 11 | 23,196 | 2,109 |
| james_knee_mri_downtown | pass | 9 | 17,725 | 1,969 |
