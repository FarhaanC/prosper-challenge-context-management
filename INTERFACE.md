# Interface sheet for the independent tester (voice stages, build 25c3f91)

How to call the code. This sheet lists names, fields and shapes only; work out expected answers from the plan, the decisions and the raw data, not from the code.

## Setting up a call

```python
from call import Clinic, CallSession, run_tool, read_bookings, BookingsFileError, TOOLS
from clinic import Catalog, PatientDirectory, Schedule, IDENTIFY, VISIT_TYPE, BOOKING, END
clinic = Clinic(catalog, patients, schedule, bookings_file=path_or_None, log_dir=path_or_None)
# or Clinic.load(bookings_file=..., log_dir=...): loads the real catalog and patients, and reloads saved bookings
session = clinic.new_call(clock=lambda: NOW)   # NOW: a fixed datetime in clinic time
session.enter_stage(stage_name, instructions_list)   # what the builder does when a stage starts
outcome = run_tool(session, tool_name, args_dict)   # outcome.result (dict the AI sees), outcome.next_stage (None = stay)
session.fill(text)   # fills {placeholders}
session.card        # the clinic.BookingCard for this call (caller, preferences, choices, status, offered_options)
session.stage, session.log_path, clinic.schedule, clinic.bookings_file
```

After a tool moves the call (next_stage set), the voice agent enters that stage: in tests call `session.enter_stage(outcome.next_stage, [])` yourself, as the builder does.

Saved bookings: one JSON object per line in the bookings file. The call log: one JSON object per line (events `stage` and `tool`).

## The agent file and builder

```python
from agent_builder import AgentBuilder
b = AgentBuilder.from_json('clinic_agent.json')   # or from_dict(d); problems raise ValueError at load
node = b.build_initial_node(session)   # a Pipecat Flows NodeConfig dict; node['functions'] are FlowsFunctionSchema with .name and async .handler(args, flow_manager)
b.global_functions()
# flow_manager only needs a .state dict holding {'session': session}
```

Agent file fields beyond the starter format: per node `tools` (names), per agent `global_tools`, `history` ('keep'|'reset'), `parallel_tool_calls` (bool). Placeholders allowed in task messages (and only there):

- `{today}`: today's date and the time at the clinics
- `{booking_card}`: the booking card: who is calling, what they asked for, what's agreed
- `{specialties}`: the names of all our specialties
- `{visit_types}`: the visit types of the specialty already picked (if any), each marked bookable or not
- `{options}`: the notes and options on offer, from the latest search
- `{outcome}`: what the end stage should tell the caller (booked, or handed to staff)

## Tools (exactly what the AI is shown)

### start_booking

Call once you have the caller's full name, whether they've been a patient with us before, and (for returning patients) their date of birth. Also send anything they've already said they want. If it returns ok false with a 'say', say that sentence and follow it (ask again, ask them to spell their last name, or offer to register them as a new patient or have a member of staff call them back). If they choose to register as new, call again with returning false.

Required: ['full_name', 'returning']. Can move to: ['visit_type', 'end'].

```json
{
 "full_name": {
  "type": "string",
  "description": "The caller's full name, first and last."
 },
 "returning": {
  "type": "boolean",
  "description": "true if they've been a patient with us before."
 },
 "date_of_birth": {
  "type": "string",
  "description": "Returning patients only: YYYY-MM-DD."
 },
 "spelled_last_name": {
  "type": "string",
  "description": "Only when asked to spell: the letters they spelled, joined (\"WILSON\")."
 },
 "visit_description": {
  "type": "string",
  "description": "What they want, in their words (\"knee MRI\")."
 },
 "specialty": {
  "type": "string",
  "description": "If it's clear which of our specialties fits what they want, that specialty's name from your instructions (its visit types are then ready in the next stage). Leave it out if unsure."
 },
 "doctor_name": {
  "type": "string",
  "description": "A doctor the caller asked for, as they said it (\"Dr. Garcia\"). Only a name. For 'someone else' or 'not Dr. X', use turn_down_doctors."
 },
 "place": {
  "type": "string",
  "description": "A place the caller mentioned: one of our locations, a neighbourhood, a landmark or a street with its street word (\"Midtown\", \"Union Square\", \"Geary Street\"). Only the name; put closeness in near."
 },
 "near": {
  "type": "boolean",
  "description": "With place: true if the caller wants somewhere close to it (\"near Union Square\"), false if they mean that place itself (\"the Midtown one\")."
 },
 "days": {
  "type": "array",
  "items": {
   "type": "string"
  },
  "description": "Days that suit the caller, ONE day per entry: a weekday name (\"Thursday\"), \"today\", \"tomorrow\", or a date YYYY-MM-DD (use the year from 'Now' in your instructions). \"Thursday or Friday\" is [\"Thursday\", \"Friday\"]. Never put a time of day here."
 },
 "time_of_day": {
  "type": "string",
  "enum": [
   "morning",
   "afternoon",
   "any"
  ],
  "description": "\"morning\" (before noon) or \"afternoon\" (noon or later). Leave it out if they didn't say."
 },
 "soonest": {
  "type": "boolean",
  "description": "true if the caller wants the earliest time possible."
 },
 "language": {
  "type": "string",
  "description": "One language the doctor should speak (\"Spanish\")."
 }
}
```

### list_visit_types

List every visit type in one specialty, each marked can_book for THIS caller, with the reason if not. Pick the specialty that fits what the caller wants from the names in your instructions.

Required: ['specialty']. Can move to: stays.

```json
{
 "specialty": {
  "type": "string",
  "description": "One specialty name from your instructions."
 }
}
```

### choose_visit_type

Call when the caller has picked a visit type. If it's refused, explain the reason in plain words and offer the alternative it gives. Also send any new wishes they mentioned in this stage.

Required: ['visit_type_id']. Can move to: ['booking'].

```json
{
 "visit_type_id": {
  "type": "string",
  "description": "The visit type's id from the list."
 },
 "doctor_name": {
  "type": "string",
  "description": "A doctor the caller asked for, as they said it (\"Dr. Garcia\"). Only a name. For 'someone else' or 'not Dr. X', use turn_down_doctors."
 },
 "place": {
  "type": "string",
  "description": "A place the caller mentioned: one of our locations, a neighbourhood, a landmark or a street with its street word (\"Midtown\", \"Union Square\", \"Geary Street\"). Only the name; put closeness in near."
 },
 "near": {
  "type": "boolean",
  "description": "With place: true if the caller wants somewhere close to it (\"near Union Square\"), false if they mean that place itself (\"the Midtown one\")."
 },
 "days": {
  "type": "array",
  "items": {
   "type": "string"
  },
  "description": "Days that suit the caller, ONE day per entry: a weekday name (\"Thursday\"), \"today\", \"tomorrow\", or a date YYYY-MM-DD (use the year from 'Now' in your instructions). \"Thursday or Friday\" is [\"Thursday\", \"Friday\"]. Never put a time of day here."
 },
 "time_of_day": {
  "type": "string",
  "enum": [
   "morning",
   "afternoon",
   "any"
  ],
  "description": "\"morning\" (before noon) or \"afternoon\" (noon or later). Leave it out if they didn't say."
 },
 "soonest": {
  "type": "boolean",
  "description": "true if the caller wants the earliest time possible."
 },
 "language": {
  "type": "string",
  "description": "One language the doctor should speak (\"Spanish\")."
 }
}
```

### choose_option

Call when the caller picks one of the options on offer. Returns the read-back sentence to say.

Required: ['option_id']. Can move to: stays.

```json
{
 "option_id": {
  "type": "string",
  "description": "The option number from your instructions, e.g. \"2\"."
 }
}
```

### confirm_booking

Call only after the caller said yes to the read-back. Saves the booking. If the time was taken meanwhile, fresh options are found.

Required: none. Can move to: ['end', 'booking'].

```json
{}
```

### turn_down_doctors

The caller doesn't want certain doctors. "Not Dr. Chen": doctor_name "Dr. Chen" (works at any point in the call). "Someone else" or "a different doctor" while options are on offer: on_offer true. "Not him" or "not her" about the doctor just chosen: current true. If several doctors match a name, you get their ids: call again with doctor_id. Once options are on offer, fresh options follow.

Required: none. Can move to: ['visit_type', 'booking'].

```json
{
 "doctor_name": {
  "type": "string",
  "description": "A doctor's name only (\"Dr. Chen\")."
 },
 "doctor_id": {
  "type": "string",
  "description": "A doctor_id from an earlier which_one reply."
 },
 "on_offer": {
  "type": "boolean",
  "description": "Turn down every doctor in the options on offer."
 },
 "current": {
  "type": "boolean",
  "description": "Turn down the doctor just chosen."
 }
}
```

### change_choice

The caller wants something different, or adds a wish. Send only the fields that change, in the same form as for start_booking: doctor_name, place (with near), days, time_of_day, soonest, language; or visit_type for a different kind of visit (what they want now, in their words, plus specialty if clear). Several can go in one call: "Friday afternoon at Midtown" is days ["Friday"], time_of_day "afternoon", place "Midtown". To drop a wish, send "any" (doctor_name "any", days ["any"], time_of_day "any"). Once options are on offer, fresh options follow. For 'someone else' or 'not Dr. X', use turn_down_doctors.

Required: none. Can move to: ['visit_type', 'booking'].

```json
{
 "visit_type": {
  "type": "string",
  "description": "A different kind of visit, in the caller's words."
 },
 "specialty": {
  "type": "string",
  "description": "If it's clear which of our specialties fits what they want, that specialty's name from your instructions (its visit types are then ready in the next stage). Leave it out if unsure."
 },
 "doctor_name": {
  "type": "string",
  "description": "A doctor the caller asked for, as they said it (\"Dr. Garcia\"). Only a name. For 'someone else' or 'not Dr. X', use turn_down_doctors."
 },
 "place": {
  "type": "string",
  "description": "A place the caller mentioned: one of our locations, a neighbourhood, a landmark or a street with its street word (\"Midtown\", \"Union Square\", \"Geary Street\"). Only the name; put closeness in near."
 },
 "near": {
  "type": "boolean",
  "description": "With place: true if the caller wants somewhere close to it (\"near Union Square\"), false if they mean that place itself (\"the Midtown one\")."
 },
 "days": {
  "type": "array",
  "items": {
   "type": "string"
  },
  "description": "Days that suit the caller, ONE day per entry: a weekday name (\"Thursday\"), \"today\", \"tomorrow\", or a date YYYY-MM-DD (use the year from 'Now' in your instructions). \"Thursday or Friday\" is [\"Thursday\", \"Friday\"]. Never put a time of day here."
 },
 "time_of_day": {
  "type": "string",
  "enum": [
   "morning",
   "afternoon",
   "any"
  ],
  "description": "\"morning\" (before noon) or \"afternoon\" (noon or later). Leave it out if they didn't say."
 },
 "soonest": {
  "type": "boolean",
  "description": "true if the caller wants the earliest time possible."
 },
 "language": {
  "type": "string",
  "description": "One language the doctor should speak (\"Spanish\")."
 }
}
```

### answer_question

Look up a fact instead of guessing: a location (address, hours, phone, neighbourhood, equipment), a doctor (specialty, languages, locations, taking new patients?) or a visit type (referral needed? how long? new patients?).

Required: ['about', 'name']. Can move to: stays.

```json
{
 "about": {
  "type": "string",
  "enum": [
   "location",
   "doctor",
   "visit_type"
  ]
 },
 "name": {
  "type": "string",
  "description": "The location, doctor or visit type name."
 }
}
```

### hand_off

For things a member of staff handles: rescheduling or cancelling an appointment, or when the caller asks for a person. Staff will call them back; this ends the call with a goodbye.

Required: ['reason']. Can move to: ['end'].

```json
{
 "reason": {
  "type": "string",
  "enum": [
   "reschedule",
   "cancel",
   "speak_to_staff"
  ]
 }
}
```
