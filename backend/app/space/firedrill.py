"""Fire drill: at night, how long does each person take to get out? Measured on the plan, no model.
Everyone starts in their bed and goes to the nearest way out their body fits through."""
from __future__ import annotations

import numpy as np

from app.space.future import _age_and_aid
from app.space.simulate import (SQUEEZE_IN, TIGHT_SPARE_IN, Floor, _astar, _nearest, _target,
                                load_personas)

# walking speed in ft/s (rule of thumb, slower at night and in a hurry it evens out)
SPEED = {"none": 3.5, "cane": 2.0, "walker": 1.3, "wheelchair": 2.0, "crutches": 1.5}
GOAL_S = 120          # fire services say you may have about 2 minutes to get out


def _wake_s(age: int, mob: str) -> tuple[int, str]:
    if age < 12:
        return 45, "a child may sleep through the alarm and needs an adult"
    if age >= 75 or mob != "none":
        return 40, "slower to get up and get going"
    return 20, ""


def _exits(space: dict, floor: Floor, passable: np.ndarray) -> list[tuple[tuple[int, int], str]]:
    out = []
    pts = []
    if floor.entrance:
        pts.append((floor.entrance, "front door"))
    for d in space.get("doors") or []:
        if d.get("outside"):
            pts.append(((int(d["x"]), int(d["y"])), "outside door"))
    for (c, r), name in pts:
        cell = _nearest(passable, r, c)
        if cell is not None and abs(cell[0] - r) + abs(cell[1] - c) <= 8:
            out.append((cell, name))
    return out


def drill_one(space: dict, floor: Floor, person: dict) -> dict:
    width = float(person["width_in"])
    passable = floor.fits(width - SQUEEZE_IN)
    tight = passable & ~floor.fits(width + 2 * TIGHT_SPARE_IN)
    age, mob = _age_and_aid(person)
    # at home they start in bed at night; at the office, at their desk in the afternoon
    use = "work" if floor.pack == "office" else "sleep"
    start, room = _target(floor, use, person.get("home", "bedroom"), passable, (0, 0))
    if start is None:                     # no bed or desk found: start in the middle of the floor
        start = _nearest(passable, floor.grid.shape[0] // 2, floor.grid.shape[1] // 2)
        room = "the middle of the space"
    wake, why_wake = _wake_s(age, mob)
    base = {"id": person["id"], "name": person["name"], "color": person.get("color"), "from": room,
            "wake_s": wake, "note": why_wake}
    if start is None:
        return {**base, "out": False, "why": "no room to get out of bed" if use == "sleep" else "no room to get up from the desk", "seconds": None, "path": []}
    best = None
    for cell, name in _exits(space, floor, passable):
        path = _astar(passable, tight, start, cell)
        if path and (best is None or len(path) < len(best[0])):
            best = (path, name)
    if best is None:
        return {**base, "out": False, "seconds": None, "path": [],
                "why": f"no way out {width:.0f} in wide: someone has to help"}
    path, exit_name = best
    ft_per_cell = floor.cell_in / 12
    speed = SPEED.get(mob, 3.0) * (0.85 if age < 12 else 1.0)
    walk_s = tight_ft = ft = 0.0
    for a, b in zip(path, path[1:]):
        step = (1.414 if a[0] != b[0] and a[1] != b[1] else 1.0) * ft_per_cell
        ft += step
        slow = 2.0 if tight[b] else 1.0          # squeezing past furniture in the dark
        tight_ft += step if tight[b] else 0
        walk_s += step / speed * slow
    secs = round(wake + walk_s)
    return {**base, "out": True, "seconds": secs, "ft": round(ft), "tight_ft": round(tight_ft),
            "exit": exit_name, "in_time": secs <= GOAL_S, "why": "",
            "path": [[c, r] for r, c in path]}


def fire_drill(space: dict, people: list[dict] | None, after_items: list[dict] | None) -> dict:
    pack = space.get("pack") or "home"
    people = people or list(load_personas(pack))
    before = Floor(space, space.get("items", []), pack)
    after = Floor(space, after_items if after_items is not None else space.get("items", []), pack)
    rows = []
    for p in people:
        b, a = drill_one(space, before, p), drill_one(space, after, p)
        rows.append({"id": p["id"], "name": p["name"], "color": p.get("color"), "before": b, "after": a})
    times = [r["after"]["seconds"] for r in rows if r["after"]["out"]]
    stuck = [r["name"] for r in rows if not r["after"]["out"]]
    last = max(times) if times else None
    return {"people": rows, "pack": pack, "goal_s": GOAL_S, "everyone_out_s": None if stuck else last, "stuck": stuck,
            "note": "Times are a rule of thumb: wake-up time plus walking at a typical speed for each body, "
                    "twice as slow through tight spots. Not fire safety advice. Practice a real plan with two ways out."}
