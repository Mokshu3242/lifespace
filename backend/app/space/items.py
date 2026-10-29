"""Find the furniture already drawn on a plan and match each piece to a real catalog item.

1. Code finds closed furniture shapes (the reader already uses them to block walking).
2. Each shape's real size and room give a shortlist of catalog items that could fit.
3. Every vision model picks from that shortlist (or "none"); the majority wins.
Nothing is trained: the catalog plus the vote does the work."""
import logging
from collections import Counter
from dataclasses import asdict, dataclass

import cv2
import numpy as np

from app import catalog
from app.space.reader import (TILE, TILES_PER_SHEET, choose_seal_size, find_walls, outside_mask)

log = logging.getLogger("items")

CHAIR_ROW_IN = 36        # a table drawn with its chairs is about this much bigger on each axis
MIN_SIDE_IN = 12         # smaller than this is a symbol, a hinge or a window strip
MAX_SIDE_IN = 140
MIN_FILL = 0.3           # share of the bounding box the shape covers; frames and outlines are lower
DOOR_MAX_IN = 48         # door swings are at most a 4 ft quarter circle

# What common top-down plan symbols look like, so the models know what to pick
SYMBOL_HINTS = """How furniture looks from above on a plan:
- bed: a long rectangle with one or two rounded pillows at one end, often a folded sheet line
- sofa: a long shape with a thick back and arms; armchair: the same, one seat wide
- dining or meeting set: a table with small chair shapes around it
- desk: a plain rectangle against a wall, often with a chair in front
- tub: a long rectangle with an oval or rounded shape inside; shower: a square with an X or a dot in the middle
- toilet: a small oval with a rectangle tank behind it; sink: a small oval or circle, often in a counter
- stove: a rectangle with 4 circles; fridge, washer, dryer: plain squares, often labelled
- plant: a star or spiky circle; lamp: a small circle
Never furniture, always pick "none": a quarter-circle arc (door swing), a V shape (bi-fold door),
thin double lines in a wall (window), arrows and dimension lines, stairs (many parallel lines), text."""

ITEM_PROMPT = """{context}{hints}
Each tile is a zoomed-in piece of one floor plan, seen from above.
A red box marks ONE drawn shape. The number above a tile is that tile's id.
For each tile, say what is inside the red box by picking ONE option id from that tile's list.
Pick "none" if it is a wall, counter, window, cabinet run, text, or nothing on the list fits.
{options}
Reply as JSON: {{"tiles": [{{"id": 1, "pick": "option id or none", "reason": "a few words on what you see"}}]}}"""


@dataclass
class Placed:
    id: int
    item: str            # catalog id
    name: str
    x: float             # center, in grid cells
    y: float
    w: float             # size along x and y, in grid cells
    d: float
    room: int | None
    chairs: int = 0      # a table drawn with chairs around it
    price_usd: float = 0
    source: str = ""     # "models agree", "most models", "best size match", "you"
    note: str = ""
    unsure: bool = False


@dataclass
class Shape:
    x: int               # bounding box in image pixels
    y: int
    w: int
    h: int
    w_in: float
    d_in: float
    room: int | None


def find_shapes(gray: np.ndarray, px_per_ft: float, grid: np.ndarray, cell_px: float) -> list[Shape]:
    walls, furniture = find_walls(gray)
    k = choose_seal_size(walls, [])
    inside = ~walls & ~outside_mask(walls, k)
    # small closed pockets (tubs, table tops) count as furniture too
    n, lab, st, _ = cv2.connectedComponentsWithStats(inside.astype(np.uint8), 4)
    if n > 2:
        main = int(st[1:, 4].max())
        inside_pockets = np.isin(lab, [i for i in range(1, n) if st[i, 4] < 0.03 * main])
    else:
        inside_pockets = np.zeros_like(walls)
    blocked = (furniture | inside_pockets) & inside
    near_wall = cv2.dilate(walls.astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)

    n, lab, st, _ = cv2.connectedComponentsWithStats(blocked.astype(np.uint8), 8)
    shapes = []
    for i in range(1, n):
        x, y, w, h, area = (int(v) for v in st[i])
        w_in, d_in = w / px_per_ft * 12, h / px_per_ft * 12
        if min(w_in, d_in) < MIN_SIDE_IN or max(w_in, d_in) > MAX_SIDE_IN or area < MIN_FILL * w * h:
            continue
        mask = lab[y:y + h, x:x + w] == i
        if is_door_swing(mask, gray[y:y + h, x:x + w], near_wall[y:y + h, x:x + w],
                         max(w_in, d_in), from_pocket=not furniture[y:y + h, x:x + w][mask].any()):
            continue
        shapes.append(Shape(x, y, w, h, round(w_in), round(d_in), _room_around(grid, x, y, w, h, cell_px)))
    return shapes


def is_door_swing(mask: np.ndarray, gray: np.ndarray, near_wall: np.ndarray, size_in: float,
                 from_pocket: bool) -> bool:
    """A door swing closes off a pocket: wall + door leaf + arc. It touches a wall, is blank
    inside (nothing drawn in it) and has a curved edge, so it doesn't fill its box.
    Tubs, counters and tables have lines or fill inside, or are bigger."""
    if not from_pocket or size_in > DOOR_MAX_IN:
        return False
    if not (near_wall & mask).any():
        return False
    inner = cv2.erode(mask.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    if not inner.any():
        return False
    ink = float((gray[inner] < 200).mean())
    fill = float(mask.mean())
    return ink < 0.03 and fill < 0.85


def _room_around(grid: np.ndarray, x: int, y: int, w: int, h: int, cell_px: float) -> int | None:
    """The room whose floor surrounds a shape (the shape itself is blocked on the grid)."""
    c0, r0 = int(x / cell_px) - 2, int(y / cell_px) - 2
    c1, r1 = int((x + w) / cell_px) + 3, int((y + h) / cell_px) + 3
    win = grid[max(0, r0):r1, max(0, c0):c1]
    ids = win[win >= 0]
    if not len(ids):
        return None
    return int(Counter(ids.tolist()).most_common(1)[0][0])


def candidates(pack: str, shape: Shape, room_name: str) -> list[tuple[catalog.Item, int]]:
    """(item, chairs) pairs that fit the shape. Tables also match as a set with chairs around them."""
    out: list[tuple[float, catalog.Item, int]] = []
    for it in catalog.shortlist(pack, shape.w_in, shape.d_in, room_name, tolerance=0.4, limit=5):
        out.append((catalog.size_error(it, shape.w_in, shape.d_in), it, 0))
    for it in catalog.load(pack):
        if it.category != "table" or not ({"eat", "meet"} & set(it.uses)):
            continue
        if room_name and not it.fits_room(room_name):
            continue
        set_item = catalog.Item(it.id, it.name, it.category, it.w_in + CHAIR_ROW_IN, it.d_in + CHAIR_ROW_IN,
                                it.h_in, it.price_usd, it.watts, it.rooms, it.uses)
        err = catalog.size_error(set_item, shape.w_in, shape.d_in)
        if err <= 0.3:
            out.append((err, it, _chairs_for(it)))
    out.sort(key=lambda p: p[0])
    seen, picked = set(), []
    for _, it, chairs in out:
        key = f"{it.id}+chairs" if chairs else it.id
        if key not in seen:
            seen.add(key)
            picked.append((it, chairs))
    return picked[:6]


def _chairs_for(table: catalog.Item) -> int:
    for n in (8, 6, 4, 2):
        if f"for {n}" in table.name:
            return n
    return 4 if table.w_in * table.d_in > 900 else 2


def _option_id(it: catalog.Item, chairs: int) -> str:
    return f"{it.id}+chairs" if chairs else it.id


def _option_name(it: catalog.Item, chairs: int) -> str:
    return f"{it.name} with {chairs} chairs" if chairs else it.name


def draw_item_sheets(gray: np.ndarray, shapes: list[Shape]) -> list[tuple[bytes, list[int]]]:
    """Tiles of each shape with a little of its surroundings, 6 per sheet. Ids start at 1."""
    h, w = gray.shape
    sheets = []
    for start in range(0, len(shapes), TILES_PER_SHEET):
        group = list(range(start, min(start + TILES_PER_SHEET, len(shapes))))
        cols = min(3, len(group))
        rows_n = (len(group) + cols - 1) // cols
        cap = 36
        sheet = np.full((rows_n * (TILE + cap), cols * TILE, 3), 255, np.uint8)
        for slot, i in enumerate(group):
            s = shapes[i]
            pad = int(max(s.w, s.h) * 0.8) + 12
            side = max(s.w, s.h) + 2 * pad
            cx, cy = s.x + s.w // 2, s.y + s.h // 2
            x0, y0 = max(0, cx - side // 2), max(0, cy - side // 2)
            x1, y1 = min(w, x0 + side), min(h, y0 + side)
            crop = cv2.cvtColor(gray[y0:y1, x0:x1], cv2.COLOR_GRAY2BGR)
            scale = TILE / max(crop.shape[:2])
            crop = cv2.resize(crop, None, fx=scale, fy=scale,
                              interpolation=cv2.INTER_CUBIC if scale > 1 else cv2.INTER_AREA)
            bx, by = int((s.x - x0) * scale), int((s.y - y0) * scale)
            cv2.rectangle(crop, (bx - 4, by - 4), (bx + int(s.w * scale) + 4, by + int(s.h * scale) + 4),
                          (40, 40, 220), 2)
            ox, oy = (slot % cols) * TILE, (slot // cols) * (TILE + cap)
            sheet[oy + cap:oy + cap + crop.shape[0], ox:ox + crop.shape[1]] = crop
            cv2.rectangle(sheet, (ox, oy + cap), (ox + TILE - 1, oy + cap + TILE - 1), (160, 160, 160), 1)
            cv2.putText(sheet, str(i + 1), (ox + 8, oy + 26), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (40, 40, 220), 2)
        ok, buf = cv2.imencode(".png", sheet)
        sheets.append((buf.tobytes(), [i + 1 for i in group]))
    return sheets


def detect_items(gray: np.ndarray, grid: list[list[int]], rooms: list, px_per_ft: float, cell_in: int,
                 pack: str, router, context: str = "") -> list[Placed]:
    g = np.array(grid)
    cell_px = px_per_ft * cell_in / 12
    names = {r.id: r.name for r in rooms}
    shapes = find_shapes(gray, px_per_ft, g, cell_px)
    opts = [candidates(pack, s, names.get(s.room, "")) for s in shapes]
    keep = [i for i, o in enumerate(opts) if o]
    shapes, opts = [shapes[i] for i in keep], [opts[i] for i in keep]
    if not shapes:
        return []

    votes: dict[int, list[tuple[str, str, str]]] = {i: [] for i in range(len(shapes))}
    for png, ids in draw_item_sheets(gray, shapes):
        lines = []
        for k in ids:
            s, o = shapes[k - 1], opts[k - 1]
            where = f"in {names[s.room]}, " if s.room in names else ""
            choice = ", ".join(f"{_option_id(it, c)} = {_option_name(it, c)}" for it, c in o)
            lines.append(f"Tile {k} ({where}about {s.w_in / 12:.1f} x {s.d_in / 12:.1f} ft): {choice}, none")
        prompt = ITEM_PROMPT.format(context=context, hints=SYMBOL_HINTS, options="\n".join(lines))
        try:
            answers = router.see_each(prompt, png)
        except Exception as e:  # items are a bonus; never fail the whole read over them
            log.warning("item vote failed: %s", e)
            answers = {}
        for model, ans in answers.items():
            for t in (ans or {}).get("tiles") or []:
                try:
                    k = int(t.get("id")) - 1
                except (TypeError, ValueError, AttributeError):
                    continue
                if 0 <= k < len(shapes):
                    votes[k].append((model, str(t.get("pick") or "").strip(), str(t.get("reason") or "")))

    placed: list[Placed] = []
    for k, s in enumerate(shapes):
        valid = {_option_id(it, c): (it, c) for it, c in opts[k]}
        picks = [(m, p, r) for m, p, r in votes[k] if p in valid or p == "none"]
        note = "; ".join(f"{m}: {p} ({r})" for m, p, r in picks)
        if picks:
            count = Counter(p for _, p, _ in picks)
            top, n = count.most_common(1)[0]
            if top == "none" and n * 2 > len(picks):
                continue
            if top == "none":
                top = next(p for p, _ in count.most_common() if p != "none")
            source = "models agree" if n == len(picks) else "most models"
            unsure = n * 2 <= len(picks) or len(picks) == 1
        else:
            top = _option_id(*opts[k][0])
            source, note, unsure = "best size match", "no model answered; closest size in the catalog", True
        it, chairs = valid[top]
        chair_price = next((c.price_usd for c in catalog.load(pack) if c.category == "seat"
                            and ({"eat", "meet"} & set(it.uses)) and c.fits_room(names.get(s.room, ""))
                            and "chair" in c.name.lower()), 60)
        placed.append(Placed(
            id=len(placed), item=it.id, name=_option_name(it, chairs),
            x=round((s.x + s.w / 2) / cell_px, 1), y=round((s.y + s.h / 2) / cell_px, 1),
            w=round(s.w / cell_px, 1), d=round(s.h / cell_px, 1), room=s.room, chairs=chairs,
            price_usd=it.price_usd + chairs * chair_price, source=source, note=note, unsure=unsure))
    return placed


def to_dicts(items: list[Placed]) -> list[dict]:
    return [asdict(i) for i in items]
