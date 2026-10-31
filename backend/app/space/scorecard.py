"""Livability scorecard: four scores, each computed by code from the map, the items and the people's day.

Movement   people make every trip in their day, without long tight squeezes
Access     a walker (home) or wheelchair (office) can reach every room, and rooms have a 5 ft turning circle
Safety     the cheap things that prevent the common problems: alarms, grab bars, night lights, a way to the bathroom
Energy     yearly electricity of the items (kWh and dollars)

Plus flags for what furniture can't fix (a door too narrow, a room with no outside wall).
For comparison only; not medical, safety or accessibility advice."""
import cv2
import numpy as np

from app import catalog
from app.space.simulate import Floor

KWH_PRICE = 0.17              # US average home electricity, $ per kWh
TURN_IN = 60                  # wheelchair turning circle (ADA)
ACCESS_BODY = {"home": ("walker", 25), "office": ("wheelchair", 32)}
HOURS = {"light": 5, "air": 4, "media": 4, "appliance": 1, "safety": 24, "noise": 0, "decor": 0, "outdoor": 4}
APPLIANCE_HOURS = {"fridge": 8, "fridge-office": 8, "server-rack": 24, "coffee-machine": 0.5,
                   "water-cooler": 12, "printer": 0.5, "dishwasher": 1, "dishwasher-office": 1}


def _active(items: list[dict]) -> list[dict]:
    return [it for it in items if it.get("status", "kept") in ("kept", "new")]


def _named(rooms: list[dict], *words: str) -> list[dict]:
    return [r for r in rooms if any(w in r["name"].lower() for w in words)]


def _in(items: list[dict], ids: set[str], rooms: list[dict]) -> int:
    """How many of these rooms hold one of these items."""
    room_ids = {it.get("room") for it in items if it.get("item") in ids}
    return sum(1 for r in rooms if r["id"] in room_ids)


def reachable(floor: Floor, width_in: float) -> set[int]:
    """Rooms a body this wide can get into from the entrance."""
    body = floor.fits(width_in - 4)
    if floor.entrance is None or not body.any():
        return set()
    n, lab = cv2.connectedComponents(body.astype(np.uint8), connectivity=4)
    c, r = floor.entrance
    ys, xs = np.nonzero(body)
    j = int(np.argmin((ys - r) ** 2 + (xs - c) ** 2))
    if (ys[j] - r) ** 2 + (xs[j] - c) ** 2 > 36:      # nearest spot is more than 3 ft from the door
        return set()
    part = lab == lab[ys[j], xs[j]]
    return {int(v) for v in np.unique(floor.grid[part]) if v >= 0}


def score_side(space: dict, items: list[dict], days: dict, pack: str) -> dict:
    floor = Floor(space, items, pack)
    items = _active(items)
    rooms = [r for r in space["rooms"] if r.get("kind") != "closet"]
    flags: list[str] = []
    out = {}

    # ---- movement: from the people's day
    if days:
        parts = []
        for d in days.values():
            steps = max(1, len(d["legs"]) - d["missing"])
            parts.append(100 * (1 - d["blocked"] / steps) - 40 * d["tight_ft"] / max(1.0, d["walked_ft"]))
        blocked = sum(d["blocked"] for d in days.values())
        tight = sum(d["tight_ft"] for d in days.values())
        out["movement"] = {"score": _clamp(np.mean(parts)),
                           "why": (f"{blocked} trip{'s' if blocked != 1 else ''} can't be made; " if blocked else "Every trip can be made; ")
                           + f"{tight:.0f} ft of tight squeezes across the day"}

    # ---- access: walker or wheelchair reach + turning space
    name, width = ACCESS_BODY.get(pack, ("walker", 25))
    reach = reachable(floor, width)
    turn = floor.fits(TURN_IN)
    turn_rooms = {r["id"] for r in rooms if (turn & (floor.grid == r["id"])).any()}
    n = max(1, len(rooms))
    reach_share = sum(1 for r in rooms if r["id"] in reach) / n
    turn_share = len(turn_rooms) / n
    out["access"] = {"score": _clamp(70 * reach_share + 30 * turn_share),
                     "why": f"A {name} ({width} in) reaches {sum(1 for r in rooms if r['id'] in reach)} of "
                            f"{len(rooms)} rooms; {len(turn_rooms)} have room for a 5 ft turn"}
    for r in rooms:
        if r["id"] not in reach and floor.entrance is not None and r.get("kind") != "outdoor":
            flags.append(f"{r['name']}: a {name} can't get in. The way in is narrower than about "
                         f"{width} in; a 32 in door fixes it. Furniture can't.")

    # ---- safety: the cheap things that matter most
    sleep = _named(rooms, "bedroom")
    baths = _named(rooms, "bath", "restroom", "wc")
    night_path = sleep + baths + _named(rooms, "hall", "foyer", "corridor")
    checks = []
    if pack == "home":
        alarms = {"smoke-alarm"}
        near_sleep = _in(items, alarms, sleep) + (1 if _in(items, alarms, _named(rooms, "hall", "foyer", "living")) else 0)
        checks.append((30, min(1.0, near_sleep / max(1, len(sleep))), "smoke alarm near the bedrooms"))
        checks.append((25, _in(items, {"grab-bar"}, baths) / max(1, len(baths)), "grab bars in the bathrooms"))
        checks.append((20, 1.0 if _in(items, {"night-light"}, night_path) else 0.0, "night light on the way to the bathroom"))
        checks.append((25, 1.0 if any(b["id"] in reach for b in baths) else 0.0, f"a {name} can reach a bathroom"))
    else:
        checks.append((35, 1.0 if any(it.get("item") == "extinguisher" for it in items) else 0.0, "fire extinguisher"))
        checks.append((25, 1.0 if any(it.get("item") == "first-aid" for it in items) else 0.0, "first aid cabinet"))
        checks.append((40, 1.0 if any(b["id"] in reach for b in baths) else 0.0, f"a {name} can reach a restroom"))
    missing = [label + (" (partly)" if share > 0 else "") for w, share, label in checks if share < 1]
    out["safety"] = {"score": _clamp(sum(w * share for w, share, _ in checks)),
                     "why": ("Has " + ", ".join(l for w, s, l in checks if s >= 1) if any(s >= 1 for _, s, _ in checks)
                             else "None of the basics yet") + (". Missing: " + ", ".join(missing) if missing else "")}

    # ---- energy
    kwh = 0.0
    for it in items:
        c = catalog.get(pack, it.get("item", ""))
        if c is None or not c.watts:
            continue
        hours = APPLIANCE_HOURS.get(c.id, HOURS.get(c.category, 2))
        kwh += c.watts * hours * 365 / 1000
    out["energy"] = {"score": _clamp(100 - kwh / 40), "kwh": round(kwh),
                     "why": f"About {kwh:,.0f} kWh a year from these items, roughly ${kwh * KWH_PRICE:,.0f}"}

    # ---- daylight flag: living spaces with no outside wall
    # outer walls can be thick (18 in or more): look through up to 2.5 ft of wall for the outside
    k = 2 * int(np.ceil(30 / floor.cell_in)) + 1
    outside = cv2.dilate((floor.grid == -2).astype(np.uint8), np.ones((k, k), np.uint8)).astype(bool)
    for r in rooms:
        if r.get("kind") in ("room", "open") and not _named([r], "hall", "foyer", "corridor") \
                and not (outside & (floor.grid == r["id"])).any():
            flags.append(f"{r['name']}: no outside wall, so likely little daylight")
    out["flags"] = flags
    return out


def scorecard(space: dict, after_items: list[dict] | None, sim: dict | None) -> dict:
    pack = space.get("pack") or "home"
    before = score_side(space, space.get("items", []), (sim or {}).get("before", {}), pack)
    after = score_side(space, after_items if after_items is not None else space.get("items", []),
                       (sim or {}).get("after", {}), pack)
    return {"before": before, "after": after,
            "note": "Measured from the floor plan for comparison only. Not medical, safety or accessibility advice."}


def _clamp(x: float) -> int:
    return int(round(max(0.0, min(100.0, float(x)))))
