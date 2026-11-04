"""AI plan check: code finds what looks wrong on a read plan, Muse Spark looks at the plan picture and
proposes fixes (or follows the user's instruction), and code checks and applies each fix to a copy.
Nothing is saved until the user accepts it in the editor.

Fixes are a small, safe vocabulary:
  rename      {room, name}                 a room's name
  merge       {room, into}                 a piece of a room joins the room it belongs to
  widen_door  {door, width_in}             a renovation what-if: open the wall at a doorway to this width
  set_entrance{room}                       the front door opens into this room
  add_item    {room, item, at}             furniture drawn on the plan but missing from the map: a catalog item,
                                           placed by code near "at" (percent of the picture) where it fits,
                                           out of doorways, without cutting anyone off
  split       {room, from, to, name}       two rooms read as one: cut along a line (percent of the picture)
                                           and name the new piece. Code snaps the line, checks it really
                                           splits the room, and adds no wall, so walking is unchanged.
"""
from __future__ import annotations

import copy
import json
import re

import cv2
import numpy as np

from app.space.simulate import Floor, _astar, _nearest

ACTIONS = ("rename", "merge", "widen_door", "set_entrance", "split", "add_item")

PROMPT = """You check a floor plan that a program has read. {context}
The picture is the original plan with a grid: numbers on the edges are percent of the width (top) and
height (left). The program found these rooms (id, name, size, box as left-top-right-bottom percent) and doorways:
{rooms}
{doors}
Problems the program noticed:
{issues}
{instruction}
{learned}
Propose fixes using ONLY these actions:
- {{"action": "rename", "room": id, "name": "Bedroom 2", "why": "..."}}  use the name printed on the plan if there is one
- {{"action": "merge", "room": id, "into": id, "why": "..."}}  a small piece that is really part of another room
- {{"action": "widen_door", "door": index, "width_in": 32, "why": "..."}}  only when asked, or a wheelchair needs it
- {{"action": "set_entrance", "room": id, "why": "..."}}
- {{"action": "split", "room": id, "from": [x, y], "to": [x, y], "name": "Hallway", "why": "..."}}  when the plan shows
  two rooms (two printed names) that the program read as one room: a line in percent of the picture, along
  where the two rooms meet, from one wall to the other. "name" is the new piece, on the side away from the
  room's current name.
- {{"action": "add_item", "room": id, "item": "catalog id", "at": [x, y], "why": "..."}}  furniture or a fixture that is
  DRAWN on the plan (bed, sofa, table, tub, toilet, stove...) but missing from the map's items. "at" is where it is
  drawn, in percent of the picture. Pick the item id from this list: {catalog}
Items already on the map: {items}
Use ids and door indexes from the lists. At most 12 fixes. Plain short reasons.
A walker is about 25 in wide and fits through a 27 in door; a wheelchair needs about 32 in.
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
    # learned from people's past fixes: a name that was renamed before gets the same fix suggested
    from app.space import lessons
    learned = lessons.renames(space.get("pack") or "home")
    for r in rooms:
        hit = learned.get(" ".join(r["name"].lower().split()))
        if hit and hit[0].strip().lower() != r["name"].strip().lower():
            to, times = hit
            issues.append({"kind": "learned", "room": r["id"],
                           "text": f'{r["name"]} was renamed to "{to}" on {times} past plan{"s" if times > 1 else ""}',
                           "fix": {"action": "rename", "room": r["id"], "name": to,
                                   "why": f"learned from {times} past fix{'es' if times > 1 else ''}"}})
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
                           "text": f"Door {' to '.join(rn)} is {d['width_in']} in: a wheelchair needs about 32 in",
                           "fix": {"action": "widen_door", "door": i, "width_in": 32, "why": "renovation what-if: 32 in fits a wheelchair"}})
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
            elif a == "add_item":
                _add_item(g, s, f)
            elif a == "split":
                rid = int(f["room"])
                if rid not in ids:
                    raise ValueError("unknown room")
                name = str(f.get("name") or "").strip()[:40]
                if not name:
                    raise ValueError("the new room needs a name")
                new = _split(g, s, rid, f["from"], f["to"], name)
                ids.add(new)
            else:
                raise ValueError(f"unknown action {a}")
            log.append({"fix": f, "ok": True, "note": f.get("why", "")})
        except (KeyError, IndexError, TypeError, ValueError) as e:
            log.append({"fix": f, "ok": False, "note": str(e)})
    s["grid"] = g.tolist()
    return s, log


def _line_cells(x0: int, y0: int, x1: int, y1: int) -> list[tuple[int, int]]:
    n = max(abs(x1 - x0), abs(y1 - y0), 1)
    return [(round(x0 + (x1 - x0) * t / n), round(y0 + (y1 - y0) * t / n)) for t in range(n + 1)]


def _room_stats(g: np.ndarray, r: dict, cell_in: float) -> None:
    ys, xs = np.nonzero(g == r["id"])
    r["cells"] = int(len(ys))
    r["area_sqft"] = round(len(ys) * (cell_in / 12) ** 2, 1)
    if len(ys):
        r["bbox_cells"] = [int(xs.min()), int(ys.min()), int(xs.max()), int(ys.max())]
        r["center_cells"] = [round(float(xs.mean()), 1), round(float(ys.mean()), 1)]


def _split(g: np.ndarray, s: dict, rid: int, a, b, name: str) -> int:
    """Cut room rid along a line (percent of the picture) into two rooms. Code checks it: the line is snapped
    straight, stretched to the room's walls, and must leave two real pieces. No wall is added."""
    from app.space.reader import kind_of
    rows, cols = g.shape
    x0, y0, x1, y1 = (float(v) for v in (*a, *b))
    if not all(0 <= v <= 100 for v in (x0, y0, x1, y1)):
        raise ValueError("the line is off the picture")
    c0 = (int(x0 / 100 * cols), int(y0 / 100 * rows))
    c1 = (int(x1 / 100 * cols), int(y1 / 100 * rows))
    dx, dy = c1[0] - c0[0], c1[1] - c0[1]
    if abs(dx) <= 0.25 * abs(dy):                 # walls are straight: snap a nearly upright line
        mx = (c0[0] + c1[0]) // 2
        c0, c1 = (mx, c0[1]), (mx, c1[1])
    elif abs(dy) <= 0.25 * abs(dx):
        my = (c0[1] + c1[1]) // 2
        c0, c1 = (c0[0], my), (c1[0], my)
    cut = set(_line_cells(*c0, *c1))
    # stretch both ends through the room until they meet something that isn't this room
    for (sx, sy), (ex, ey) in ((c0, c1), (c1, c0)):
        n = max(abs(ex - sx), abs(ey - sy), 1)
        ux, uy = (sx - ex) / n, (sy - ey) / n
        for k in range(1, max(rows, cols)):
            x, y = round(sx + ux * k), round(sy + uy * k)
            if not (0 <= x < cols and 0 <= y < rows) or g[y, x] != rid:
                break
            cut.add((x, y))
    mask = (g == rid).astype(np.uint8)
    for x, y in cut:
        if 0 <= x < cols and 0 <= y < rows:
            mask[y, x] = 0
    n, lab, st, _ = cv2.connectedComponentsWithStats(mask, connectivity=4)
    sqft = (s["cell_in"] / 12) ** 2
    pieces = sorted(((int(st[i, 4]), i) for i in range(1, n)), reverse=True)
    pieces = [(c, i) for c, i in pieces if c * sqft >= 8]
    if len(pieces) < 2:
        raise ValueError("that line doesn't split the room into two real rooms")
    room = next(r for r in s["rooms"] if r["id"] == rid)
    # the old name stays with the piece that holds its label spot (or the bigger piece)
    cx, cy = (int(v) for v in (room.get("center_cells") or [-1, -1]))
    keep = lab[cy, cx] if 0 <= cy < rows and 0 <= cx < cols and lab[cy, cx] > 0 else pieces[0][1]
    other = next(i for c, i in pieces if i != keep)
    new_id = max(r["id"] for r in s["rooms"]) + 1
    g[lab == other] = new_id                        # the cut line itself stays with the old room
    # furniture standing in the new piece now belongs to the new room
    for it in s.get("items") or []:
        if it.get("room") == rid:
            ix, iy = int(it.get("x", -1)), int(it.get("y", -1))
            if 0 <= iy < rows and 0 <= ix < cols and g[iy, ix] == new_id:
                it["room"] = new_id
    nr = {"id": new_id, "name": name, "kind": kind_of(name), "source": "ai fix", "unsure": False,
          "note": "split off by the plan check", "dims_text": None, "dims_ft": None}
    s["rooms"].append(nr)
    _room_stats(g, nr, s["cell_in"])
    _room_stats(g, room, s["cell_in"])
    return new_id


def _add_item(g: np.ndarray, s: dict, f: dict) -> None:
    """Put one catalog item on the map near where the plan draws it. Code checks: a real catalog item that
    belongs in that kind of room, a spot where it fits out of doorways, and nobody cut off from a room."""
    from app import catalog
    from app.space.redesign import (DOOR_CLEAR_IN, PATH_IN, doorway_zone, find_spot, occupancy,
                                    reachable_rooms)
    pack = s.get("pack") or "home"
    rid = int(f["room"])
    room = next((r for r in s["rooms"] if r["id"] == rid), None)
    if room is None:
        raise ValueError("unknown room")
    key = str(f.get("item") or "").strip().lower()
    c = catalog.get(pack, key) or next((x for x in catalog.load(pack) if x.name.lower() == key), None)
    if c is None:
        raise ValueError(f'"{f.get("item")}" is not in the catalog')
    if not c.fits_room(room["name"].lower()) and not c.fits_room(room.get("kind", "")):
        raise ValueError(f"a {c.name.lower()} doesn't belong in {room['name']}")
    rows, cols = g.shape
    at = f.get("at") or [None, None]
    near = None
    if at[0] is not None:
        near = (float(at[0]) / 100 * cols, float(at[1]) / 100 * rows)
    items = s.setdefault("items", [])
    free = occupancy(g, items, pack)
    zone = doorway_zone(g, max(1, round(DOOR_CLEAR_IN / s["cell_in"] / 2)))
    spot = None
    if near is not None:              # first look close to where it's drawn (within about 5 ft)
        reach = 60 / s["cell_in"]
        yy, xx = np.mgrid[0:rows, 0:cols]
        close = np.where((g == rid) & (((xx - near[0]) ** 2 + (yy - near[1]) ** 2) <= reach ** 2), g, -3)
        spot = find_spot(close, free, rid, c, s["cell_in"], zone, near)
    spot = spot or find_spot(g, free, rid, c, s["cell_in"], zone, near)
    if spot is None:
        raise ValueError(f"no space for a {c.name.lower()} in {room['name']}")
    new = {"id": max([it.get("id", 0) for it in items] + [-1]) + 1, "item": c.id, "name": c.name, **spot,
           "room": rid, "chairs": 0, "price_usd": c.price_usd, "source": "ai fix", "note": f.get("why", ""),
           "unsure": False}
    ent = tuple(s["entrance"]) if s.get("entrance") else None
    path = max(2, round(PATH_IN / s["cell_in"]))
    before = reachable_rooms(g, free, ent, path)
    after = reachable_rooms(g, occupancy(g, items + [new], pack), ent, path)
    if not before <= after:
        cut = ", ".join(r["name"] for r in s["rooms"] if r["id"] in before - after)
        raise ValueError(f"it would block the way into {cut}")
    items.append(new)
    f["placed"] = {k: new[k] for k in ("x", "y", "w", "d")}


def _widen(g: np.ndarray, d: dict, width_in: float, cell_in: float) -> None:
    """Open the wall at a doorway to width_in: wall cells between two floors become floor. The opening grows
    along the wall from the door, both ways, only where there is floor on both sides (a closet or a built-in
    next to the door stops it). Raises if it can't reach the width, and changes nothing then."""
    if d.get("outside"):
        raise ValueError("won't open an outside wall")
    want = int(np.ceil(width_in / cell_in))
    r, c = int(round(d["y"] - 0.5)), int(round(d["x"] - 0.5))
    rows, cols = g.shape
    along = (0, 1) if d.get("axis") == "x" else (1, 0)      # the wall runs along this direction
    across = (1, 0) if d.get("axis") == "x" else (0, 1)

    def plan(k):
        """Cells to fill to open line k of the wall, or None if this line can't be opened."""
        rr, cc = r + along[0] * k, c + along[1] * k
        line = [(t, rr + across[0] * t, cc + across[1] * t) for t in range(-5, 6)]
        line = [(t, y, x) for t, y, x in line if 0 <= y < rows and 0 <= x < cols]
        before = [x for x in line if x[0] <= 0 and g[x[1], x[2]] >= 0]
        after = [x for x in line if x[0] >= 0 and g[x[1], x[2]] >= 0]
        if not before or not after:
            return None
        lo, hi = max(before), min(after)
        if lo[0] == hi[0]:
            return []                                        # already open here
        mid = [(t, y, x) for t, y, x in line if lo[0] < t < hi[0]]
        if any(g[y, x] not in (-1,) for _, y, x in mid):
            return None                                      # something other than plain wall in the way
        a, b = g[lo[1], lo[2]], g[hi[1], hi[2]]
        return [(y, x, a if t <= 0 else b) for t, y, x in mid]

    opened = {0: plan(0)}
    if opened[0] is None:
        raise ValueError("this doorway isn't a plain gap in a wall")
    lo_k = hi_k = 0
    while hi_k - lo_k + 1 < want:
        grew = False
        for k in (hi_k + 1, lo_k - 1):
            if hi_k - lo_k + 1 >= want:
                break
            p = plan(k)
            if p is not None:
                opened[k] = p
                lo_k, hi_k = min(lo_k, k), max(hi_k, k)
                grew = True
        if not grew:
            break
    got = (hi_k - lo_k + 1) * cell_in
    if got + 1 < width_in:
        raise ValueError(f"only {got:.0f} in fits here: a closet, built-in or corner is right next to this door")
    for cells in opened.values():
        for y, x, v in cells:
            g[y, x] = v
    d["width_in"] = round(width_in)
    d["widened"] = True


def _pct_box(r: dict, cols: int, rows: int) -> str:
    b = r.get("bbox_cells") or [0, 0, 0, 0]
    return f"box {100 * b[0] / cols:.0f}-{100 * b[1] / rows:.0f}-{100 * b[2] / cols:.0f}-{100 * b[3] / rows:.0f}"


def grid_overlay(image: bytes) -> bytes:
    """The plan with a light percent grid and numbers, so the model can point at places."""
    img = cv2.imdecode(np.frombuffer(image, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        return image
    h, w = img.shape[:2]
    scale = 1400 / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_AREA)
        h, w = img.shape[:2]
    over = img.copy()
    for k in range(0, 101, 5):
        x, y = min(w - 1, int(w * k / 100)), min(h - 1, int(h * k / 100))
        col = (255, 120, 0) if k % 10 == 0 else (255, 200, 150)
        cv2.line(over, (x, 0), (x, h), col, 1)
        cv2.line(over, (0, y), (w, y), col, 1)
    img = cv2.addWeighted(over, 0.45, img, 0.55, 0)
    for k in range(10, 100, 10):
        x, y = int(w * k / 100), int(h * k / 100)
        for pos in ((x - 9, 14), (x - 9, h - 4)):
            cv2.putText(img, str(k), pos, cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 60, 0), 1, cv2.LINE_AA)
        for pos in ((2, y + 5), (w - 22, y + 5)):
            cv2.putText(img, str(k), pos, cv2.FONT_HERSHEY_SIMPLEX, 0.42, (200, 60, 0), 1, cv2.LINE_AA)
    ok, png = cv2.imencode(".png", img)
    return png.tobytes() if ok else image


def ai_fixes(space: dict, image: bytes | None, issues: list[dict], instruction: str, router, context: str = "") -> dict:
    g = np.array(space["grid"])
    rows_, cols_ = g.shape
    rooms = "\n".join(f"- {r['id']}: {r['name']} ({_sqft(g, r['id'], space['cell_in']):.0f} sq ft, {_pct_box(r, cols_, rows_)})"
                      for r in space["rooms"])
    names = {r["id"]: r["name"] for r in space["rooms"]}
    doors = "Doorways:\n" + "\n".join(
        f"- door {i}: {' to '.join(names.get(x, '?') for x in d.get('rooms', []))}{' (front door)' if d.get('outside') else ''}, {d.get('width_in')} in"
        for i, d in enumerate(space.get("doors") or [])) if space.get("doors") else "Doorways: none found"
    iss = "\n".join(f"- {x['text']}" for x in issues) or "- none"
    ins = f"The user asks: {instruction.strip()[:300]}\nDo what they ask if the actions allow it." if instruction.strip() else ""
    from app.space import lessons
    ex = lessons.examples(space.get("pack") or "home")
    learned = ("Fixes people made on earlier plans (use them when the same thing shows up here):\n" + "\n".join(ex)) if ex else ""
    from app import catalog as _cat
    pack = space.get("pack") or "home"
    cat = ", ".join(f"{c.id} ({c.name})" for c in _cat.load(pack) if c.category not in ("safety", "access", "energy", "health"))
    have = ", ".join(sorted({f"{it.get('name')} in {names.get(it.get('room'), '?')}" for it in space.get("items") or []})) or "none"
    prompt = PROMPT.format(context=context, rooms=rooms, doors=doors, issues=iss, instruction=ins, learned=learned,
                           catalog=cat, items=have)
    ans = router.see(prompt, grid_overlay(image)) if image else router.ask_json(prompt)
    fixes = [f for f in (ans.get("fixes") or []) if isinstance(f, dict) and f.get("action") in ACTIONS][:12]
    return {"summary": str(ans.get("summary") or "")[:200], "fixes": fixes,
            "provider": getattr(router, "last_provider", None)}
