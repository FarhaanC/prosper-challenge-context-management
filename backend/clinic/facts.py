"""answer_question: small, factual answers about a location, doctor or visit type.

Available in every stage, so the agent looks facts up instead of making them
up (the baseline agent invented "our MRI clinic is near downtown"). Results
are kept short: at most 3 matches, a few fields each.
"""

from __future__ import annotations

from .catalog import Catalog


def answer_question(catalog: Catalog, about: str, name: str) -> dict:
    about = (about or "").lower().strip()

    if about in ("location", "clinic", "place", "office"):
        place = catalog.resolve_place(name)
        if place.kind == "none":
            return {"found": False, "message": f"No location matches '{name}'."}
        if place.kind == "landmark":
            ranked = sorted(
                catalog.locations.values(),
                key=lambda l: (l.lat - place.point[0]) ** 2 + (l.lon - place.point[1]) ** 2,
            )
            ids = [ranked[0].id]
            message = f"Closest location to {place.label}."
        else:
            ids = place.location_ids[:3]
            message = "Several locations match; ask which one." if place.kind == "ambiguous" else ""
        results = []
        for i in ids:
            l = catalog.locations[i]
            results.append({
                "name": l.name, "address": f"{l.address}, {l.city}", "neighbourhood": l.neighbourhood,
                "phone": l.phone, "hours": l.hours, "equipment": list(l.capabilities) or ["none"],
            })
        return {"found": True, "message": message, "results": results}

    if about in ("doctor", "provider"):
        matches = catalog.find_providers_by_name(name)[:3]
        if not matches:
            return {"found": False, "message": f"No doctor matches '{name}'."}
        return {
            "found": True,
            "message": "Several doctors share this name; ask which one." if len(matches) > 1 else "",
            "results": [
                {
                    "name": f"{p.name}, {p.title}", "specialty": p.specialty,
                    "languages": list(p.languages),
                    "locations": [catalog.locations[l].name for l in p.location_ids],
                    "taking_new_patients": p.accepting_new_patients,
                }
                for p in matches
            ],
        }

    if about in ("visit_type", "visit", "appointment", "service", "appointment_type"):
        matches = catalog.find_visit_types_by_name(name)
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
                }
                for vt in matches
            ],
        }

    return {"found": False, "message": "I can answer about a location, a doctor or a visit type."}
