"""Extra people (a dog, a caregiver, a delivery, a toddler), time saved per day, and a comic of one
person's day. People are presets with real body widths; the comic is drawn from the measured day."""
from __future__ import annotations

import copy

# speed in ft/s for time saved (same rule of thumb as the fire drill, at a calm pace)
CALM_FT_S = {"none": 3.0, "cane": 1.8, "walker": 1.2, "wheelchair": 1.8, "child": 2.6, "dog": 4.0, "toddler": 1.2}
TRIP_MIN = 3          # a trip that couldn't be made: someone has to help, about 3 minutes each

VISITORS = {
    "dog": {"name": "Biscuit", "about": "dog, 4, follows everyone around", "width_in": 14, "mobility": "dog",
            "home": "living room",
            "day": [{"t": "06:45", "use": "exit", "note": "morning walk"}, {"t": "07:20", "use": "enter", "note": "back home"},
                    {"t": "07:30", "use": "cook", "note": "food bowl"}, {"t": "10:00", "use": "sit", "note": "naps on the rug"},
                    {"t": "13:00", "use": "outdoor", "note": "sun on the terrace"}, {"t": "18:00", "use": "cook", "note": "dinner bowl"},
                    {"t": "22:00", "use": "sleep", "note": "dog bed"}]},
    "caregiver": {"name": "Grace", "about": "45, visiting caregiver, carries a bag", "width_in": 26, "mobility": "none",
                  "home": "",
                  "day": [{"t": "08:00", "use": "enter", "note": "arrives"}, {"t": "08:10", "use": "sleep", "note": "helps someone out of bed"},
                          {"t": "08:30", "use": "wash", "note": "helps in the bathroom"}, {"t": "09:00", "use": "cook", "note": "makes breakfast"},
                          {"t": "12:00", "use": "eat", "note": "sets lunch"}, {"t": "13:00", "use": "exit", "note": "leaves"}]},
    "delivery": {"name": "Sam", "about": "delivery, carrying a 24 in box", "width_in": 30, "mobility": "none", "home": "",
                 "day": [{"t": "11:00", "use": "enter", "note": "brings a big box in"}, {"t": "11:05", "use": "sit", "note": "sets it in the living room"},
                         {"t": "11:10", "use": "cook", "note": "groceries to the kitchen"}, {"t": "11:20", "use": "exit", "note": "leaves"}]},
    "toddler": {"name": "Mia", "about": "2, toddler, crawls and climbs", "width_in": 14, "mobility": "toddler", "home": "bedroom",
                "day": [{"t": "07:00", "use": "eat", "note": "breakfast"}, {"t": "09:00", "use": "sit", "note": "plays on the floor"},
                        {"t": "11:00", "use": "cook", "note": "follows into the kitchen"}, {"t": "13:00", "use": "sleep", "note": "nap"},
                        {"t": "16:00", "use": "wash", "note": "bath time"}, {"t": "19:30", "use": "sleep", "note": "bedtime"}]},
}
COLORS = ["#8a5a2b", "#7a4fd1", "#c98a12", "#d14f8f"]


def add_visitor(family: dict | None, defaults: list[dict], kind: str, rooms: list[dict]) -> dict:
    fam = copy.deepcopy(family) if family else {"text": "", "people": copy.deepcopy(defaults), "notes": [], "provider": "sample"}
    v = copy.deepcopy(VISITORS[kind])
    taken = {p["id"] for p in fam["people"]}
    v["id"] = kind if kind not in taken else f"{kind}{len(taken)}"
    v["color"] = COLORS[list(VISITORS).index(kind)]
    names = [r["name"] for r in rooms]
    if v["home"]:
        v["home"] = next((n.lower() for n in names if v["home"] in n.lower()), v["home"])
    if kind == "caregiver":           # helps the oldest person: goes to their room
        old = max(fam["people"], key=lambda p: int(p.get("about", "0").split(",")[0] or 0) if p.get("about", "")[:2].isdigit() else 0)
        v["home"] = old.get("home", "")
        v["about"] += f", helps {old['name']}"
    fam["people"].append(v)
    fam["notes"] = (fam.get("notes") or []) + [f"{v['name']} added: {v['about']} (needs {v['width_in']} in)"]
    return fam


def _speed(p: dict) -> float:
    mob = p.get("mobility") or ""
    if mob in CALM_FT_S:
        return CALM_FT_S[mob]
    about = (p.get("about") or "").lower()
    for k in ("wheelchair", "walker", "cane"):
        if k in about:
            return CALM_FT_S[k]
    return CALM_FT_S["child"] if about[:2].strip().isdigit() and int(about[:2]) < 13 else CALM_FT_S["none"]


def time_saved(sim: dict, people: list[dict]) -> list[dict]:
    """Minutes a day each person gains After vs Before: less walking and squeezing, and trips that now work."""
    out = []
    for p in people:
        b, a = sim["before"][p["id"]], sim["after"][p["id"]]
        v = _speed(p)
        walk = (b["walked_ft"] - a["walked_ft"]) / v + (b["tight_ft"] - a["tight_ft"]) / v   # squeezing = half speed
        trips = b["blocked"] - a["blocked"]
        out.append({"id": p["id"], "name": p["name"], "minutes": round(walk / 60 + trips * TRIP_MIN, 1),
                    "trips_unlocked": trips})
    return out


COMIC = ("A warm, simple 4-panel comic strip in a clean flat illustration style, two rows of two panels, "
         "about {name} ({about}) at home. Top row, labeled BEFORE: panel 1 {b1}; panel 2 {b2}. "
         "Bottom row, labeled AFTER: panel 3 {a1}; panel 4 {a2}. Friendly faces, soft colors, a real {place}, "
         "no speech bubbles, only the two labels BEFORE and AFTER, no other text.")


def comic_prompt(person: dict, before: dict, after: dict, changes: list[dict], place: str) -> str:
    def scene(day, good):
        blocked = [lg for lg in day["legs"] if lg["blocked"]]
        tight = sorted((lg for lg in day["legs"] if lg["tight_ft"] > 0), key=lambda lg: -lg["tight_ft"])
        if not good and blocked:
            lg = blocked[0]
            return f"stopped at a doorway that is too narrow, can't get to the {lg['note']}", \
                   (f"squeezing past furniture for the {tight[0]['note']}" if tight else "waiting for help")
        if not good:
            lg = tight[0] if tight else day["legs"][0]
            return f"squeezing past furniture for the {lg['note']}", "tired, holding the wall"
        new = [c.get("name") or c.get("item") for c in changes if not c.get("dropped")][:2]
        still = [lg for lg in day["legs"] if lg["blocked"]]
        if still:     # honest: a trip still blocked after the redesign stays blocked in the comic
            fixed = f", a new {new[0].lower()} visible inside" if new else ""
            return (f"still stopped at the same narrow doorway for the {still[0]['note']}{fixed}, looking worried",
                    f"a small win elsewhere" + (f": using the new {new[-1].lower()}" if new else ", resting in a chair"))
        lg = next((lg for lg in day["legs"] if not lg["blocked"]), day["legs"][0])
        return (f"moving easily for the {lg['note']}" + (f", next to a new {new[0].lower()}" if new else ""),
                f"smiling and relaxed" + (f" by the new {new[1].lower()}" if len(new) > 1 else ""))
    b1, b2 = scene(before, False)
    a1, a2 = scene(after, True)
    return COMIC.format(name=person["name"], about=person["about"], b1=b1, b2=b2, a1=a1, a2=a2, place=place)
