"""AI plan check: code finds what looks wrong on a read plan, Muse Spark looks at the plan picture and
proposes fixes (or follows the user's instruction), and code checks and applies each fix to a copy.
Nothing is saved until the user accepts it in the editor.

Fixes are a small, safe vocabulary:
  rename      {room, name}                 a room's name
  merge       {room, into}                 a piece of a room joins the room it belongs to
  widen_door  {door, width_in}             a renovation what-if: open the wall at a doorway to this width
  set_entrance{room}                       the front door opens into this room
"""
from __future__ import annotations

import copy
import json
import re

import cv2
import numpy as np

from app.space.simulate import Floor, _astar, _nearest

ACTIONS = ("rename", "merge", "widen_door", "set_entrance")

PROMPT = """You check a floor plan that a program has read. {context}
The picture is the original plan. The program found these rooms (id, name, size) and doorways:
{rooms}
{doors}
Problems the program noticed:
{issues}
{instruction}
Propose fixes using ONLY these actions:
- {{"action": "rename", "room": id, "name": "Bedroom 2", "why": "..."}}  use the name printed on the plan if there is one
- {{"action": "merge", "room": id, "into": id, "why": "..."}}  a small piece that is really part of another room
- {{"action": "widen_door", "door": index, "width_in": 32, "why": "..."}}  only when asked, or a walker or wheelchair needs it
- {{"action": "set_entrance", "room": id, "why": "..."}}
Use ids and door indexes from the lists. At most 12 fixes. Plain short reasons.
Return JSON: {{"summary": "one sentence", "fixes": [...]}}"""


def _sqft(g, rid, cell_in):
    return float((g == rid).sum()) * (cell_in / 12) ** 2


def _neighbors(g, rid, reach=3):
    m = g == rid
    k = 2 * reach + 1
    ring = cv2.dilate(m.astype(np.uint8), np.ones((k, k), np.uint8)).astype(bool) & ~m
    vals = [int(v) for v in g[ring] if v >= 0 and v != rid]
    return sorted(set(vals), key=lambda v: -vals.count(v))


def check(space: dict) -> list[dict]:
    """What looks wrong, found by code. Each issue may carry a ready fix."""
    g = np.array(space["grid"])
    cell = space["cell_in"]
    rooms = space["rooms"]
    issues = []
    names = {}
    for r in rooms:
        names.setdefault(r["name"].strip().lower(), []).append(r)
    for r in rooms:
        a = _sqft(g, r["id"], cell)
        if a < 10 and r.get("kind") not in ("closet",) and not re.search(r"closet|cl\b|wic|linen|pantry|storage", r["name"].lower()):
            nb = _neighbors(g, r["id"])
            issues.append({"kind": "sliver", "room": r["id"],
                           "text": f"{r['name']} is only {a:.0f} sq ft: probably a piece of another room",
                           "fix": {"action": "merge", "room": r["id"], "into": nb[0], "why": "tiny piece next to it"} if nb else None})
        if re.fullmatch(r"(space|room)\s*\d+", r["name"].strip().lower()):
            issues.append({"kind": "unnamed", "room": r["id"], "text": f"{r['name']} has no real name", "fix": None})
    for n, rs in names.items():
        if len(rs) > 1:
            issues.append({"kind": "duplicate", "room": rs[1]["id"],
                           "text": f"{len(rs)} rooms are called {rs[0]['name']}", "fix": None})
    if not space.get("entrance"):
        issues.append({"kind": "entrance", "text": "No front door marked", "fix": None})
    else:
        # rooms an everyday 22 in body can't reach from the front door
        floor = Floor(space, space.get("items", []), space.get("pack") or "home")
        passable = floor.fits(18)
        c, r0 = space["entrance"]
        start = _nearest(passable, r0, c)
        if start is not None:
            _, lab = cv2.connectedComponents(passable.astype(np.uint8), connectivity=8)
            reach = lab == lab[start]
            for r in rooms:
                m = (g == r["id"]) & passable
                if m.any() and not (m & reach).any() and r.get("kind") != "closet":
                    issues.append({"kind": "unreachable", "room": r["id"],
                                   "text": f"Nobody can walk into {r['name']} from the front door: a wall or a drawn item may be closing its door",
                                   "fix": None})
    for i, d in enumerate(space.get("doors") or []):
        if d.get("width_in", 99) < 28 and not d.get("outside"):
            rn = [next((r["name"] for r in rooms if r["id"] == x), "?") for x in d.get("rooms", [])]
            issues.append({"kind": "narrow_door", "door": i,
                           "text": f"Door {' to '.join(rn)} is {d['width_in']} in: a walker needs about 32 in",
                           "fix": {"action": "widen_door", "door": i, "width_in": 32, "why": "renovation what-if: 32 in fits a walker"}})
    return issues


def apply(space: dict, fixes: list[dict]) -> tuple[dict, list[dict]]:
    """Apply checked fixes to a copy. Returns (new space, [{fix, ok, note}])."""
    s = copy.deepcopy(space)
    g = np.array(s["grid"])
    ids = {r["id"] for r in s["rooms"]}
    log = []
    for f in fixes or []:
        a = f.get("action")
        try:
            if a == "rename":
                rid, name = int(f["room"]), str(f.get("name") or "").strip()[:40]
                if rid not in ids or not name:
                    raise ValueError("unknown room or empty name")
                for r in s["rooms"]:
                    if r["id"] == rid:
                        r.update(name=name, source="ai fix", unsure=False, note=f.get("why", ""))
            elif a == "merge":
                rid, into = int(f["room"]), int(f["into"])
                if rid not in ids or into not in ids or rid == into:
                    raise ValueError("unknown rooms")
                if into not in _neighbors(g, rid, reach=4):
                    raise ValueError("the two rooms don't touch")
                g[g == rid] = into
                src = next(r for r in s["rooms"] if r["id"] == rid)
                dst = next(r for r in s["rooms"] if r["id"] == into)
                if re.fullmatch(r"(space|room)\s*\d+", dst["name"].strip().lower()) and \
                        not re.fullmatch(r"(space|room)\s*\d+", src["name"].strip().lower()):
                    dst["name"] = src["name"]          # "Kitchen" sliver into "Space 3": it's the kitchen
                s["rooms"] = [r for r in s["rooms"] if r["id"] != rid]
                ids.discard(rid)
                for it in s.get("items") or []:
                    if it.get("room") == rid:
                        it["room"] = into
                for d in s.get("doors") or []:
                    d["rooms"] = sorted({into if x == rid else x for x in d.get("rooms", [])})
            elif a == "widen_door":
                i, w = int(f["door"]), float(f.get("width_in") or 32)
                doors = s.get("doors") or []
                if not 0 <= i < len(doors) or not 20 <= w <= 48:
                    raise ValueError("unknown door or width out of 20 to 48 in")
                _widen(g, doors[i], w, s["cell_in"])
            elif a == "set_entrance":
                rid = int(f["room"])
                if rid not in ids:
                    raise ValueError("unknown room")
                ys, xs = np.nonzero(g == rid)
                outside = np.nonzero(g == -2)
                if len(outside[0]):
                    j = int(np.argmin(np.min([(ys - oy) ** 2 + (xs - ox) ** 2 for oy, ox in
                                              zip(outside[0][::25], outside[1][::25])], axis=0)))
                else:
                    j = 0
                s["entrance"] = [int(xs[j]), int(ys[j])]
            else:
                raise ValueError(f"unknown action {a}")
            log.append({"fix": f, "ok": True, "note": f.get("why", "")})
        except (KeyError, TypeError, ValueError) as e:
            log.append({"fix": f, "ok": False, "note": str(e)})
    s["grid"] = g.tolist()
    return s, log


def _widen(g: np.ndarray, d: dict, width_in: float, cell_in: float) -> None:
    """Open the wall at a doorway to width_in, centered on the door: wall cells become the floor of the
    room next to them. Only walls between two rooms, never the outside wall."""
    n = int(np.ceil(width_in / cell_in))
    r, c = int(round(d["y"] - 0.5)), int(round(d["x"] - 0.5))
    rows, cols = g.shape
    along = (0, 1) if d.get("axis") == "x" else (1, 0)      # the wall runs along this direction
    across = (1, 0) if d.get("axis") == "x" else (0, 1)
    if d.get("outside"):
        raise ValueError("won't open an outside wall")
    for k in range(-(n // 2), n - n // 2):
        rr, cc = r + along[0] * k, c + along[1] * k
        line = []
        for t in range(-4, 5):
            y, x = rr + across[0] * t, cc + across[1] * t
            if 0 <= y < rows and 0 <= x < cols:
                line.append((t, y, x))
        # fill the wall cells between the nearest floor on each side
        before = [(t, y, x) for t, y, x in line if t < 0 and g[y, x] >= 0]
        after = [(t, y, x) for t, y, x in line if t > 0 and g[y, x] >= 0]
        if not before or not after:
            continue
        lo, hi = max(before)[0], min(after)[0]
        a_room, b_room = g[max(before)[1], max(before)[2]], g[min(after)[1], min(after)[2]]
        for t, y, x in line:
            if lo < t < hi and g[y, x] in (-1, -4):
                g[y, x] = a_room if t <= 0 else b_room
    d["width_in"] = round(width_in)
    d["widened"] = True


def ai_fixes(space: dict, image: bytes | None, issues: list[dict], instruction: str, router, context: str = "") -> dict:
    g = np.array(space["grid"])
    rooms = "\n".join(f"- {r['id']}: {r['name']} ({_sqft(g, r['id'], space['cell_in']):.0f} sq ft)" for r in space["rooms"])
    names = {r["id"]: r["name"] for r in space["rooms"]}
    doors = "Doorways:\n" + "\n".join(
        f"- door {i}: {' to '.join(names.get(x, '?') for x in d.get('rooms', []))}{' (front door)' if d.get('outside') else ''}, {d.get('width_in')} in"
        for i, d in enumerate(space.get("doors") or [])) if space.get("doors") else "Doorways: none found"
    iss = "\n".join(f"- {x['text']}" for x in issues) or "- none"
    ins = f"The user asks: {instruction.strip()[:300]}\nDo what they ask if the actions allow it." if instruction.strip() else ""
    prompt = PROMPT.format(context=context, rooms=rooms, doors=doors, issues=iss, instruction=ins)
    ans = router.see(prompt, image) if image else router.ask_json(prompt)
    fixes = [f for f in (ans.get("fixes") or []) if isinstance(f, dict) and f.get("action") in ACTIONS][:12]
    return {"summary": str(ans.get("summary") or "")[:200], "fixes": fixes,
            "provider": getattr(router, "last_provider", None)}
