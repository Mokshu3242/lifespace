"""Furniture found by Meta SAM 3.1, for plans that draw furniture as filled shapes.

The shape finder (items.py) looks for closed outlines. Many plans, office plans most of all, draw
tables, sofas and desks as solid grey blocks, which read as built-ins instead. SAM 3.1 is asked for a
few words ("chair", "desk", "sofa"...) and returns a box for each one it sees. Code then turns each box
into a real catalog item at the box's measured size, in the room it sits in.

Cost: about $0.0025 per word per plan (10 words = 2.5 cents). Answers are cached, so a plan is only
paid for once. Runs only in prod with a Meta key; elsewhere it returns nothing.
"""
from __future__ import annotations

import base64
import logging
import re
import time

import cv2
import httpx
import numpy as np

from app import catalog
from app.config import get_settings

log = logging.getLogger("sam")

BOX_RE = re.compile(r"<\|box;x1=(\d+);y1=(\d+);x2=(\d+);y2=(\d+);w=(\d+);h=(\d+)(?:;c=([\d.]+))?\|>")
MIN_CONF = 0.5

# what to ask SAM for, per pack, and which catalog item each answer becomes (by size where it matters)
WORDS = {
    "office": ["chair", "table", "desk", "sofa", "armchair", "cabinet", "plant", "toilet", "sink"],
    "home": ["bed", "sofa", "armchair", "chair", "dining table", "desk", "toilet", "bathtub", "sink", "stove", "plant"],
}


def _catalog_id(word: str, pack: str, w_in: float, d_in: float, room_name: str) -> str | None:
    long, short = max(w_in, d_in), min(w_in, d_in)
    office = pack == "office"
    room = room_name.lower()
    if word == "chair":
        if office:
            return "meet-chair" if "meeting" in room or "conference" in room else "task-chair"
        return "dining-chair"
    if word == "armchair":
        return "lounge-chair" if office else "armchair"
    if word == "sofa":
        return "lounge-sofa" if office else ("sofa-3" if long >= 72 else "sofa-2")
    if word in ("table", "dining table"):
        if office:
            if "meeting" in room or "conference" in room or long >= 60:
                return "meet-8" if long >= 84 else "meet-4"
            return "cafe-table" if long < 40 else "side-table" if long < 26 else "meet-4"
        return "coffee-table" if short < 26 else ("dining-6" if long >= 66 else "dining-4")
    if word == "desk":
        # a "desk" in a meeting room with chairs round it is the meeting table
        if office and ("meeting" in room or "conference" in room) and long >= 40:
            return "meet-8" if long >= 84 else "meet-4"
        return "desk-office" if office else "desk-home"
    if word == "cabinet":
        return "cabinet"
    if word == "plant":
        return "plant-office" if office else "plant"
    if word == "toilet":
        return "toilet-office" if office else "toilet"
    if word == "sink":
        return "sink-office" if office else "vanity"
    if word == "bed":
        return "bed-king" if short >= 74 else "bed-queen" if short >= 58 else "bed-full" if short >= 50 else "bed-twin"
    if word == "bathtub":
        return "tub"
    if word == "stove":
        return "range"
    return None


def _ask(png: bytes, word: str, key: str, base: str) -> list[tuple[int, int, int, int, float]]:
    body = {
        "model": "sam-3.1",
        "input": [{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": word},
            {"type": "input_image", "image_url": "data:image/png;base64," + base64.b64encode(png).decode()},
        ]}],
        "metadata": {"include_confidence": "true", "mask_encoding": "one_bit"},
    }
    for attempt in range(3):      # parallel asks can hit Meta's rate limit: wait as told, then try again
        r = httpx.post(f"{base.rstrip('/')}/responses", json=body,
                       headers={"Authorization": f"Bearer {key}"}, timeout=45)
        if r.status_code not in (429, 503) or attempt == 2:
            break
        time.sleep(min(10.0, float(r.headers.get("retry-after") or 2 * (attempt + 1))))
    r.raise_for_status()
    texts: list[str] = []

    def walk(x):
        if isinstance(x, dict):
            if isinstance(x.get("text"), str):
                texts.append(x["text"])
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    data = r.json()
    walk(data.get("output", data))
    return [(int(a), int(b), int(c), int(d), float(conf) if conf else 1.0)
            for a, b, c, d, _, _, conf in BOX_RE.findall("".join(texts))]


def ask_many(png: bytes, words: list[str], router, s) -> dict[str, list]:
    """Ask SAM for several words in parallel (cached answers are used as they are). A word that fails
    is left out; SAM is a helper, so the shape finder's items stand."""
    from concurrent.futures import ThreadPoolExecutor
    out: dict[str, list] = {}
    todo = []
    for w in words:
        key = router.cache.key("sam", w, base64.b64encode(png[:4096]).decode(), len(png))
        hit = router.cache.get(key)
        if hit is not None:
            out[w] = hit
        else:
            todo.append((w, key))

    def one(job):
        w, key = job
        try:
            boxes = _ask(png, w, s.meta_api_key, s.meta_base_url)
            router.cache.set(key, boxes)
            return w, boxes
        except Exception as e:
            log.warning("SAM failed for %r: %s", w, e)
            return w, None
    if todo:
        with ThreadPoolExecutor(max_workers=min(6, len(todo))) as pool:
            for w, boxes in pool.map(one, todo):
                if boxes is not None:
                    out[w] = boxes
    return out


def sam_items(gray: np.ndarray, grid: np.ndarray, rooms: list, px_per_ft: float, cell_in: float,
              pack: str, router) -> list[dict]:
    """Ask SAM for furniture; return item dicts like items.to_dicts gives (x, y, w, d in grid cells)."""
    s = get_settings()
    if s.mode != "prod" or not s.meta_api_key:
        return []
    ok, buf = cv2.imencode(".png", gray)
    png = buf.tobytes()
    cell_px = px_per_ft * cell_in / 12
    names = {r.id if hasattr(r, "id") else r["id"]: (r.name if hasattr(r, "name") else r["name"]) for r in rooms}
    rows, cols = grid.shape
    out: list[dict] = []
    words = WORDS.get(pack, WORDS["home"])
    answers = ask_many(png, words, router, s)        # all words at once, not one after another
    for word in words:
        boxes = answers.get(word)
        if boxes is None:
            continue
        for x1, y1, x2, y2, conf in boxes:
            if conf < MIN_CONF:
                continue
            cx, cy = (x1 + x2) / 2 / cell_px, (y1 + y2) / 2 / cell_px
            w, d = max(1.0, (x2 - x1) / cell_px), max(1.0, (y2 - y1) / cell_px)
            r, c = int(cy), int(cx)
            if not (0 <= r < rows and 0 <= c < cols):
                continue
            room = int(grid[r, c])
            if room < 0:      # drawn as a filled block: take the nearest room
                near = [(abs(rr - r) + abs(cc - c), int(grid[rr, cc]))
                        for rr in range(max(0, r - 6), min(rows, r + 7))
                        for cc in range(max(0, c - 6), min(cols, c + 7)) if grid[rr, cc] >= 0]
                if not near:
                    continue
                room = min(near)[1]
            item = _catalog_id(word, pack, w * cell_in, d * cell_in, names.get(room, ""))
            if not item:
                continue
            c_item = catalog.get(pack, item)
            out.append({"item": item, "name": c_item.name if c_item else item, "chairs": 0,
                        "price_usd": c_item.price_usd if c_item else 0, "x": round(cx, 2), "y": round(cy, 2), "w": round(w, 2), "d": round(d, 2),
                        "room": room, "source": "SAM 3.1", "note": f"Meta SAM 3.1 found a {word} ({conf:.2f})",
                        "unsure": conf < 0.7})
    return out


def merge(shape_items: list[dict], sam: list[dict], grid: np.ndarray) -> list[dict]:
    """Add SAM's finds that the shape finder missed. Where SAM found furniture on cells read as
    built-in blocks, those cells become floor again: the item itself now blocks people, at its real size."""
    def overlaps(a, b):
        return abs(a["x"] - b["x"]) < (a["w"] + b["w"]) / 2 * 0.7 and abs(a["y"] - b["y"]) < (a["d"] + b["d"]) / 2 * 0.7
    out = list(shape_items)
    for it in sam:
        if any(overlaps(it, o) for o in out):
            continue
        out.append(it)
        r0, r1 = int(it["y"] - it["d"] / 2), int(np.ceil(it["y"] + it["d"] / 2))
        c0, c1 = int(it["x"] - it["w"] / 2), int(np.ceil(it["x"] + it["w"] / 2))
        block = grid[max(0, r0):r1, max(0, c0):c1]
        block[block == -4] = it["room"]
    for i, it in enumerate(out):
        it["id"] = i
    return out


DOOR_MIN_IN, DOOR_MAX_IN = 18, 48     # a door leaf is 18 to 42 in; wider boxes are double doors or noise


def find_doors(gray: np.ndarray, grid: np.ndarray, rooms: list, px_per_ft: float, cell_in: float,
               router) -> list[dict]:
    """Doors from SAM 3.1: a door is drawn as its leaf plus a quarter-circle swing, so the box around it is
    about as wide as the door. Returns [{x, y (cells), width_in, box: [x0, y0, x1, y1] (cells), rooms: [ids]}]."""
    # doorways found by code (free, every mode): gaps in the walls, measured in image pixels;
    # a door swing drawn next to the gap means there's a real door in it
    from app.space.items import find_door_swings
    code = doorways(gray, grid, px_per_ft, cell_in, find_door_swings(gray, px_per_ft), rooms)
    s = get_settings()
    if s.mode != "prod" or not s.meta_api_key:
        return code
    ok, buf = cv2.imencode(".png", gray)
    png = buf.tobytes()
    boxes = ask_many(png, ["door"], router, s).get("door") or []
    # SAM's doors confirm a doorway has a door; its width is only used where code found no gap
    sam = doors_from_boxes(boxes, grid, px_per_ft, cell_in)
    for d in sam:
        near = [c for c in code if abs(d["x"] - c["x"]) + abs(d["y"] - c["y"]) <= 6]
        if near:
            near[0]["has_door"] = True
            near[0]["source"] += " + SAM 3.1"
        else:
            code.append({**d, "source": "SAM 3.1", "has_door": True})
    return code


def doors_from_boxes(boxes: list, grid: np.ndarray, px_per_ft: float, cell_in: float) -> list[dict]:
    cell_px = px_per_ft * cell_in / 12
    rows, cols = grid.shape
    out: list[dict] = []
    for x1, y1, x2, y2, conf in boxes:
        if conf < MIN_CONF:
            continue
        w_in = (x2 - x1) / px_per_ft * 12
        h_in = (y2 - y1) / px_per_ft * 12
        # the swing makes the box square-ish; the door is its shorter side (the long side can include the frame)
        width_in = round(min(w_in, h_in))
        if not DOOR_MIN_IN <= width_in <= DOOR_MAX_IN:
            continue
        c0, r0 = int(x1 / cell_px), int(y1 / cell_px)
        c1, r1 = int(np.ceil(x2 / cell_px)), int(np.ceil(y2 / cell_px))
        near = grid[max(0, r0 - 2):min(rows, r1 + 2), max(0, c0 - 2):min(cols, c1 + 2)]
        ids = sorted({int(v) for v in np.unique(near) if v >= 0})
        out.append({"x": round((x1 + x2) / 2 / cell_px, 2), "y": round((y1 + y2) / 2 / cell_px, 2),
                    "width_in": width_in, "box": [c0, r0, c1, r1], "rooms": ids, "conf": round(conf, 2)})
    # one door per spot
    kept: list[dict] = []
    for d in sorted(out, key=lambda d: -d["conf"]):
        if all(abs(d["x"] - k["x"]) + abs(d["y"] - k["y"]) > 4 for k in kept):
            kept.append(d)
    return kept


def doorways(gray: np.ndarray, grid: np.ndarray, px_per_ft: float, cell_in: float,
             swings: list, rooms: list | None = None) -> list[dict]:
    """Every opening between two spaces: a short gap in the walls with floor on both sides. Found on the
    grid, then measured in image pixels along the wall (about an inch, not the grid's 6 in)."""
    from app.space.reader import find_walls
    walls, _ = find_walls(gray)
    cell_px = px_per_ft * cell_in / 12
    rows, cols = grid.shape
    is_wall = lambda r, c: 0 <= r < rows and 0 <= c < cols and grid[r, c] == -1     # real walls, not furniture
    open_ = lambda r, c: 0 <= r < rows and 0 <= c < cols and grid[r, c] >= 0
    # a door leaf drawn in the opening often reads as a built-in block (-4): it counts as part of the gap
    gap = lambda r, c: 0 <= r < rows and 0 <= c < cols and (grid[r, c] >= 0 or grid[r, c] == -4)
    found: list[dict] = []
    for axis in ("x", "y"):
        n_lines, n_along = (rows, cols) if axis == "x" else (cols, rows)
        cell = (lambda a, b: (a, b)) if axis == "x" else (lambda a, b: (b, a))   # (line, along) -> (r, c)
        for line in range(4, n_lines - 4):
            k = 0
            while k < n_along:
                if not gap(*cell(line, k)):
                    k += 1
                    continue
                k0 = k
                while k < n_along and gap(*cell(line, k)):
                    k += 1
                n = k - k0
                if not (2 <= n <= 10 and is_wall(*cell(line, k0 - 1)) and is_wall(*cell(line, k))):
                    continue
                # floor on both sides, and the sides belong to the room beyond (not a corridor's length)
                # a doorway joins two different spaces (look a little further in, past thick walls)
                sides = []
                for sgn in (-1, 1):
                    # look past the wall and past a drawn swing (-4 cells) for the space beyond
                    v = None
                    for d in range(2, 13):
                        rr, cc = cell(line + sgn * d, k0 + n // 2)
                        if not (0 <= rr < rows and 0 <= cc < cols):
                            break
                        g = grid[rr, cc]
                        if g >= 0 or g == -2:          # -2: outside (front door)
                            v = int(g)
                            break
                        if g == -1 and d > 4:          # a wall beyond the swing: nothing there
                            break
                    sides.append(v)
                if None in sides or sides[0] == sides[1] or max(sides) < 0:
                    continue
                a, b = sides
                if a < 0:
                    a, b = b, a           # the room side first (a door leaf becomes that room's floor)
                r, c = cell(line, k0 + n // 2)
                found.append({"axis": axis, "r": r, "c": c, "n": n, "rooms": sorted(v for v in {a, b} if v >= 0),
                              "outside": b < 0,
                              "line": line, "k0": k0, "cell": cell, "side_room": a})
    # one per doorway (a thick wall gives a gap on several lines)
    kept: list[dict] = []
    for f in found:
        if all(abs(f["r"] - k["r"]) + abs(f["c"] - k["c"]) > 7 for k in kept):
            kept.append(f)
    out = []
    for f in kept:
        # measure in pixels along the wall, through the middle of the gap
        y, x = int((f["r"] + 0.5) * cell_px), int((f["c"] + 0.5) * cell_px)
        h, w = walls.shape
        if not (0 <= y < h and 0 <= x < w):
            continue
        step = (0, 1) if f["axis"] == "x" else (1, 0)
        lo = hi = 0
        while 0 <= y - step[0] * (lo + 1) < h and 0 <= x - step[1] * (lo + 1) < w \
                and not walls[y - step[0] * (lo + 1), x - step[1] * (lo + 1)] and lo < 80:
            lo += 1
        while 0 <= y + step[0] * (hi + 1) < h and 0 <= x + step[1] * (hi + 1) < w \
                and not walls[y + step[0] * (hi + 1), x + step[1] * (hi + 1)] and hi < 80:
            hi += 1
        width_in = round((lo + hi + 1) / px_per_ft * 12)
        if not 14 <= width_in <= 72:
            width_in = round(f["n"] * cell_in)
        cx, cy = f["c"] + 0.5, f["r"] + 0.5
        door = any(abs((b[0] + b[2]) / 2 / cell_px - cx) + abs((b[1] + b[3]) / 2 / cell_px - cy) <= 12 for b in swings)
        # only real doors: a swing drawn next to the gap, and wide enough for a person. Gaps between
        # counters, windows and the ends of furniture runs have no swing.
        # a thin door arc is often missed by the swing finder. A clean gap of door size between two
        # different rooms (not outside) is still a doorway, just without a door leaf we can see.
        # only between two real indoor rooms: a window onto a terrace, or a built-in niche, is not a door
        kinds = {r["id"]: r.get("kind") for r in (rooms or [])}
        big = lambda i: (grid == i).sum() * (cell_in / 12) ** 2 >= 15
        room_to_room = len(f["rooms"]) == 2 and not f["outside"] \
            and all(kinds.get(i) != "outdoor" and big(i) for i in f["rooms"])
        if width_in < 20 or not (door or (room_to_room and 24 <= width_in <= 42 and 4 <= f["n"] <= 8)):
            continue
        # the door leaf and its swing arc are an open door, not furniture: make them floor so people
        # walk through. Clear the -4 cells joined to the opening, within a door's reach of it
        reach = f["n"] + 3
        seeds = [f["cell"](f["line"], kk) for kk in range(f["k0"], f["k0"] + f["n"])]
        todo = [rc for rc in seeds if grid[rc] == -4] + [rc for rc in seeds if grid[rc] >= 0]
        seen = set(todo)
        cleared = []
        while todo:
            rr, cc = todo.pop()
            if grid[rr, cc] == -4:
                cleared.append((rr, cc))
            for a, b in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                r2, c2 = rr + a, cc + b
                if (r2, c2) in seen or not (0 <= r2 < rows and 0 <= c2 < cols) or grid[r2, c2] != -4:
                    continue
                if abs(r2 - f["r"]) > reach or abs(c2 - f["c"]) > reach:
                    continue
                seen.add((r2, c2))
                todo.append((r2, c2))
        # each cleared cell joins the room it's open to (nearest floor cell)
        ys, xs = np.nonzero(grid >= 0)
        for rr, cc in cleared:
            if len(ys):
                j = int(np.argmin((ys - rr) ** 2 + (xs - cc) ** 2))
                grid[rr, cc] = grid[ys[j], xs[j]]
        out.append({"x": round(cx, 2), "y": round(cy, 2), "width_in": width_in, "axis": f["axis"],
                    "outside": f["outside"],
                    "rooms": f["rooms"], "has_door": door, "source": "code", "conf": 1.0,
                    "box": [f["c"] - 2, f["r"] - 2, f["c"] + 3, f["r"] + 3]})
    return out
