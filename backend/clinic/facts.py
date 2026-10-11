"""answer_question: small, factual answers about a location, doctor or visit type.

Available in every stage, so the agent looks facts up instead of making them
up (the baseline agent invented "our MRI clinic is near downtown"). Results
are kept short: a few fields each. Every doctor sharing a name is listed, with
the count, so the agent can ask "which one?" rather than guess.
"""

from __future__ import annotations

from .catalog import Catalog, distance_miles
from .fuzzy import looks_like_a_sentence

VISIT_TYPE_RESULTS = 3  # visit-type lookups are by meaning, so only the best few are useful


def _location_result(l) -> dict:
    return {
        "name": l.name, "address": f"{l.address}, {l.city}", "neighbourhood": l.neighbourhood,
        "phone": l.phone, "hours": l.hours, "equipment": list(l.capabilities) or ["none"],
    }


def answer_question(catalog: Catalog, about, name) -> dict:
    about = str(about or "").lower().strip().replace(" ", "_")  # "Visit Type" -> visit_type
    name = str(name or "").strip()
    if not name:
        return {"found": False, "message": "Say which location, doctor or visit type you mean."}
    if about in ("location", "doctor") and looks_like_a_sentence(name):
        # The same guard as the search: "not Dr. Chen" or "another doctor" isn't a name,
        # and matching it by spelling would answer about the wrong doctor.
        return {"found": False, "message": f"'{name}' isn't a {about} name. Pass just the name."}

    if about == "location":
        place = catalog.resolve_place(name)
        if place.kind in ("none", "any"):
            return {"found": False, "message": f"No location matches '{name}'."}
        if place.kind == "landmark":
            closest = min(catalog.locations.values(), key=lambda l: distance_miles(place.point, l.point))
            miles = round(distance_miles(place.point, closest.point), 1)
            return {"found": True, "message": f"Closest location to {place.label}, about {miles} miles away.",
                    "results": [_location_result(closest)]}
        message = "Several locations match; ask which one." if place.kind == "ambiguous" else ""
        return {"found": True, "message": message,
                "results": [_location_result(catalog.locations[i]) for i in place.location_ids]}

    if about == "doctor":
        matches = catalog.match_providers(name)
        if not matches:
            return {"found": False, "message": f"No doctor matches '{name}'."}
        messages = []
        if len(matches) > 1:
            messages.append(f"{len(matches)} doctors match '{name}'; ask which one.")
        if not all(m.is_exact for m in matches):
            messages.append(f"No doctor is called exactly '{name}'; these are the closest ({matches[0].describe()}).")
        return {
            "found": True,
            "message": " ".join(messages),
            "results": [
                {
                    "name": f"{m.provider.name}, {m.provider.title}", "specialty": m.provider.specialty,
                    "languages": list(m.provider.languages),
                    "locations": [catalog.locations[l].name for l in m.provider.location_ids],
                    "taking_new_patients": m.provider.accepting_new_patients,
                }
                for m in matches
            ],
        }

    if about == "visit_type":
        matches = catalog.find_visit_types_by_name(name, limit=VISIT_TYPE_RESULTS)
        if not matches:
            return {"found": False, "message": f"No visit type matches '{name}'."}
        return {
            "found": True,
            "message": "",
            "results": [
                {
                    "name": vt.name, "specialty": vt.specialty, "minutes": vt.duration_min,
                    "needs_referral": vt.requires_referral, "open_to_new_patients": vt.new_patients_allowed,
                    "needs_equipment": vt.required_capability or "none",
                    "offered_by_any_doctor": bool(catalog.providers_offering(vt.id)),
                    **({"description": vt.description} if vt.description else {}),
                }
                for vt in matches
            ],
        }

    return {"found": False, "message": "Pass about as location, doctor or visit_type."}
