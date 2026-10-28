"""Floor plan reader: image in, grid map out.

Split of work:
  - AI (vision) reads WHAT is there: room names, printed sizes, where each label sits, the entrance.
  - Code (OpenCV) finds WHERE things are: the wall network, each room's floor area, the scale.

Code is exact and free; AI only does the part code can't (reading the drawing's meaning).
"""
from __future__ import annotations

import io
import re
from dataclasses import dataclass, field

import cv2
import numpy as np
from PIL import Image

WORK_SIDE = 1280          # same size the router sends to the vision model
CELL_IN = 6               # one grid cell = 6 inches
WALL, OUTSIDE = -1, -2    # grid codes; rooms are 0..n-1
UNASSIGNED = -3           # floor not yet given to a room (only during building)
FIXTURE = -4              # enclosed pockets nobody can walk into: counters, tubs, window strips

READ_PROMPT = """You are reading an architectural floor plan image that is {w} pixels wide and {h} pixels tall.
List every labeled room or space you can see, including small ones like closets (CL), linen closets (LC), WC and foyer.
For each one give:
- "name": the label as written, in title case
- "dims": the printed size exactly as written (like 14'6" x 20'5"), or "" if none
- "x", "y": the pixel position of the CENTER of that room's name label on this image
If a room has no written name, name it by what is in it (Meeting Room, Open Office, Lounge, Reception, Hallway)
and give the pixel position of the middle of its open floor instead.
Also give "entrance": {{"x":..., "y":...}} where the main entrance door is, or null.
Also give "estimated_width_ft": your best estimate of the real width of the whole drawing in feet,
using things with standard sizes: doors are about 3 ft wide, desks about 5 ft, beds about 5 to 6.5 ft, sofas about 7 ft.
Reply as JSON: {{"rooms": [{{"name": "...", "dims": "...", "x": 0, "y": 0}}], "entrance": {{"x": 0, "y": 0}}, "estimated_width_ft": 0}}"""


# ---------------------------------------------------------------- data shapes
@dataclass
class Label:
    name: str
    dims: str
    x: float
    y: float


@dataclass
class Room:
    id: int
    name: str
    dims_text: str
    dims_ft: tuple[float, float] | None
    area_sqft: float
    cells: int
    bbox_cells: tuple[int, int, int, int]  # col0, row0, col1, row1
    center_cells: tuple[float, float]
    kind: str  # "room", "closet", "bath", "outdoor", "open"


@dataclass
class SpaceMap:
    cols: int
    rows: int
    cell_in: int
    px_per_ft: float
    scale_source: str
    grid: list[list[int]]
    rooms: list[Room]
    entrance: tuple[int, int] | None
    image_size: tuple[int, int]          # (w, h) of the working image
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "cols": self.cols, "rows": self.rows, "cell_in": self.cell_in,
            "px_per_ft": round(self.px_per_ft, 3), "scale_source": self.scale_source,
            "width_ft": round(self.cols * self.cell_in / 12, 1),
            "height_ft": round(self.rows * self.cell_in / 12, 1),
            "grid": self.grid,
            "rooms": [r.__dict__ for r in self.rooms],
            "entrance": self.entrance,
            "image_size": self.image_size,
            "codes": {"wall": WALL, "outside": OUTSIDE, "fixture": FIXTURE},
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------- helpers
DIM_RE = re.compile(r"(\d+)\s*['’′]\s*(\d+)?\s*(?:[\"”″]|'')?")


def parse_dims(text: str) -> tuple[float, float] | None:
    """'14'6" x 20'5"' -> (14.5, 20.42). Handles curly quotes and missing inches."""
    if not text:
        return None
    parts = re.split(r"\s*[x×X]\s*", text.strip())
    if len(parts) != 2:
        return None
    out = []
    for p in parts:
        m = DIM_RE.search(p)
        if not m:
            return None
        feet = int(m.group(1))
        inches = int(m.group(2) or 0)
        if inches >= 12:          # typos like 6'34" -> treat as 6'3"
            inches = int(str(inches)[0])
        out.append(feet + inches / 12)
    return out[0], out[1]


def kind_of(name: str) -> str:
    n = name.lower()
    if n in {"cl", "lc"} or "closet" in n or "built-in" in n or "pantry" in n:
        return "closet"
    if "bath" in n or n == "wc" or "toilet" in n or "powder" in n:
        return "bath"
    if "terrace" in n or "balcony" in n or "patio" in n or "deck" in n:
        return "outdoor"
    if "living" in n or "dining" in n or "foyer" in n or "hall" in n or "kitchen" in n:
        return "open"
    return "room"


def load_work_image(image_bytes: bytes) -> np.ndarray:
    """Decode, flatten transparency onto white, shrink to WORK_SIDE, return grayscale."""
    img = Image.open(io.BytesIO(image_bytes))
    if img.mode in ("RGBA", "LA", "P"):
        img = img.convert("RGBA")
        bg = Image.new("RGBA", img.size, (255, 255, 255, 255))
        img = Image.alpha_composite(bg, img)
    img = img.convert("L")
    img.thumbnail((WORK_SIDE, WORK_SIDE))
    return np.array(img)


def find_walls(gray: np.ndarray) -> np.ndarray:
    """Wall mask: the big connected network of wall pixels.
    Plans draw walls in black, dark gray or light gray, so try cutoffs from dark to light and use
    the first one where one connected piece spans most of the plan. Text, door swings and
    fixtures are small separate pieces, so they drop out."""
    h, w = gray.shape
    big_side = 0.15 * max(h, w)
    for cutoff in (110, 150, 190, 215, 235):
        dark = (gray < cutoff).astype(np.uint8)
        n, lab, stats, _ = cv2.connectedComponentsWithStats(dark, 8)
        if n < 2:
            continue
        top = 1 + int(np.argmax(stats[1:, 4]))
        _, _, bw, bh, _ = stats[top]
        if bw >= 0.5 * w and bh >= 0.5 * h:
            break
    keep = np.zeros(n, bool)
    for i in range(1, n):
        if max(stats[i, 2], stats[i, 3]) >= big_side:
            keep[i] = True
    walls = keep[lab].astype(np.uint8)
    # close hairline gaps in the wall drawing
    walls = cv2.morphologyEx(walls, cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8))
    return walls.astype(bool)


def seal(walls: np.ndarray, k: int) -> np.ndarray:
    """Close gaps up to k px wide (doors, windows) so spaces become closed areas."""
    return cv2.morphologyEx(walls.astype(np.uint8), cv2.MORPH_CLOSE,
                            cv2.getStructuringElement(cv2.MORPH_RECT, (k, k))).astype(bool)


def outside_mask(walls: np.ndarray, k: int) -> np.ndarray:
    """Free space reachable from the image border = outside the apartment.
    Doors and windows are gaps in the outer wall, so they're sealed first,
    or the outside would leak into every room."""
    free = (~seal(walls, k)).astype(np.uint8)
    n, lab = cv2.connectedComponents(free, connectivity=4)
    border_labels = set(np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]])))
    border_labels.discard(0)
    return np.isin(lab, list(border_labels)) & (free == 1)


def choose_seal_size(walls: np.ndarray, labels: list[Label]) -> int:
    """Door width in pixels depends on the plan's scale, which we don't know yet.
    Try growing seal sizes; keep the smallest that puts the most room labels inside the walls."""
    side = max(walls.shape)
    sizes = sorted({max(9, int(f * side) | 1) for f in (0.03, 0.04, 0.05, 0.065, 0.08, 0.1, 0.12)})
    indoor = [lb for lb in labels if kind_of(lb.name) != "outdoor"]
    if not indoor:
        return max(9, int(0.05 * side) | 1)
    best_k, best = sizes[0], -1
    for k in sizes:
        out = outside_mask(walls, k)
        inside = sum(1 for lb in indoor
                     if 0 <= int(lb.y) < walls.shape[0] and 0 <= int(lb.x) < walls.shape[1]
                     and not out[int(lb.y), int(lb.x)])
        if inside > best:
            best_k, best = k, inside
        if best == len(indoor):
            break
    return best_k


def _grow(grid: np.ndarray, only: set[int] | None, steps: int | None) -> None:
    """Breadth-first growth of room labels into UNASSIGNED cells, 4-connected, never through walls.
    `only` limits which rooms grow; `steps` limits how far (None = until nothing changes)."""
    rows, cols = grid.shape
    frontier = [(r, c) for r, c in zip(*np.nonzero(grid >= 0))
                if only is None or grid[r, c] in only]
    step = 0
    while frontier and (steps is None or step < steps):
        nxt = []
        for r, c in frontier:
            v = grid[r, c]
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                rr, cc = r + dr, c + dc
                if 0 <= rr < rows and 0 <= cc < cols and grid[rr, cc] == UNASSIGNED:
                    grid[rr, cc] = v
                    nxt.append((rr, cc))
        frontier = nxt
        step += 1


# ---------------------------------------------------------------- main
def build_space_map(gray: np.ndarray, labels: list[Label],
                    entrance_px: tuple[float, float] | None,
                    width_ft_hint: float | None = None) -> SpaceMap:
    h, w = gray.shape
    warnings: list[str] = []
    walls = find_walls(gray)
    k = choose_seal_size(walls, labels)
    outside = outside_mask(walls, k)
    inside_free = ~walls & ~outside

    # Pockets fully closed off by lines (table tops, tubs, desks, wall fill) are furniture, not floor.
    # Real rooms always connect to the rest through a door gap.
    n_pk, pk, pk_stats, _ = cv2.connectedComponentsWithStats(inside_free.astype(np.uint8), 4)
    if n_pk > 2:
        main_area = int(pk_stats[1:, 4].max())
        small = [i for i in range(1, n_pk) if pk_stats[i, 4] < 0.03 * main_area]
        blocked = np.isin(pk, small)
        walls = walls | blocked
        inside_free = inside_free & ~blocked

    # Room cores: with door gaps sealed, each room's core is closed off from its neighbours.
    sealed = seal(walls, k)
    core_free = inside_free & ~sealed
    _, core = cv2.connectedComponents(core_free.astype(np.uint8), connectivity=4)

    # Snap each label to inside space (a label center can sit on a fixture or wall line)
    usable: list[tuple[Label, int, int]] = []
    for lb in labels:
        x, y = int(round(lb.x)), int(round(lb.y))
        if not (0 <= x < w and 0 <= y < h):
            warnings.append(f"Label '{lb.name}' is outside the image; skipped.")
            continue
        if not inside_free[y, x]:
            r = max(25, int(0.08 * max(h, w)))
            ys, xs = np.nonzero(inside_free[max(0, y - r):y + r + 1, max(0, x - r):x + r + 1])
            if len(xs) == 0:
                warnings.append(f"Label '{lb.name}' isn't inside the walls; skipped.")
                continue
            j = np.argmin((xs + max(0, x - r) - x) ** 2 + (ys + max(0, y - r) - y) ** 2)
            x, y = max(0, x - r) + int(xs[j]), max(0, y - r) + int(ys[j])
        usable.append((lb, x, y))

    # Give each core to the label(s) inside it. A core with several labels is an open-plan
    # area (living + dining + foyer): split it by nearest label.
    room_px = np.full((h, w), UNASSIGNED, np.int32)
    room_px[walls] = WALL
    room_px[outside] = OUTSIDE
    point_seeds: list[tuple[int, int, int]] = []
    by_core: dict[int, list[tuple[int, int, int]]] = {}
    for idx, (lb, x, y) in enumerate(usable):
        c = int(core[y, x])
        if c == 0:
            point_seeds.append((idx, x, y))      # small spaces (closets) disappear when sealed
        else:
            by_core.setdefault(c, []).append((idx, x, y))
    for c, members in by_core.items():
        ys, xs = np.nonzero(core == c)
        if len(members) == 1:
            room_px[ys, xs] = members[0][0]
        else:
            d = np.stack([(xs - mx) ** 2 + (ys - my) ** 2 for _, mx, my in members])
            room_px[ys, xs] = np.array([m[0] for m in members])[np.argmin(d, axis=0)]

    # ---- scale: pixels per foot, from printed sizes vs measured cores
    estimates = []
    for idx, (lb, x, y) in enumerate(usable):
        dims = parse_dims(lb.dims)
        c = int(core[y, x])
        if not dims or c == 0 or len(by_core.get(c, [])) != 1:
            continue                                  # only rooms that own their core alone
        ys, xs = np.nonzero(room_px == idx)
        if len(xs) < 50:
            continue
        bw, bh = xs.max() - xs.min() + 1, ys.max() - ys.min() + 1
        a, b = dims
        # the plan doesn't say which printed number is width; pick the pairing that fits the box shape
        pair = (a, b) if abs(bw / bh - a / b) <= abs(bw / bh - b / a) else (b, a)
        estimates += [bw / pair[0], bh / pair[1]]
    if len(estimates) >= 2:
        px_per_ft = float(np.median(estimates))
        scale_source = f"median of {len(estimates)} measurements from printed room sizes"
    elif width_ft_hint and 8 <= width_ft_hint <= 400:
        px_per_ft = w / width_ft_hint
        scale_source = f"estimated by the vision model from doors and furniture ({width_ft_hint:.0f} ft wide)"
        warnings.append("No printed sizes on the plan. Scale was estimated from doors and furniture; check it.")
    else:
        px_per_ft = w / 60.0
        scale_source = "guess: no printed sizes found, assumed plan is 60 ft wide"
        warnings.append("No room sizes found on the plan. Scale is a guess; set it by hand.")

    # ---- downsample pixels to grid cells
    cell_px = px_per_ft * CELL_IN / 12
    cols, rows = int(np.ceil(w / cell_px)), int(np.ceil(h / cell_px))
    grid = np.full((rows, cols), OUTSIDE, np.int32)
    for r in range(rows):
        y0, y1 = int(r * cell_px), min(h, int((r + 1) * cell_px) + 1)
        for c in range(cols):
            x0, x1 = int(c * cell_px), min(w, int((c + 1) * cell_px) + 1)
            block = room_px[y0:y1, x0:x1]
            if block.size == 0:
                continue
            if (block == WALL).mean() >= 0.2:
                grid[r, c] = WALL
                continue
            rest = block[block != WALL]
            if (rest == OUTSIDE).mean() > 0.5:
                continue
            rest = rest[rest != OUTSIDE]
            vals, counts = np.unique(rest, return_counts=True)
            grid[r, c] = vals[np.argmax(counts)] if len(vals) else WALL

    # ---- grow rooms into leftover floor (door gaps, closets) through open cells only.
    # Small spaces seeded by a single point get a head start so the big room next door
    # doesn't swallow them through their doorway.
    seeds: dict[tuple[int, int], int] = {}
    open_cells = np.argwhere((grid == UNASSIGNED) | (grid >= 0))
    for idx, x, y in point_seeds:
        r, c = int(y / cell_px), int(x / cell_px)
        if len(open_cells) == 0:
            break
        if not (0 <= r < rows and 0 <= c < cols) or grid[r, c] < 0 and grid[r, c] != UNASSIGNED:
            # rounding put the seed on a wall: move it to the nearest open cell
            j = int(np.argmin(((open_cells - (r, c)) ** 2).sum(1)))
            r, c = map(int, open_cells[j])
        grid[r, c] = idx
        seeds[(r, c)] = idx
    head_start = int(3 * 12 / CELL_IN)  # 3 ft
    _grow(grid, only=set(seeds.values()), steps=head_start)
    _grow(grid, only=None, steps=None)

    # ---- room summaries
    rooms: list[Room] = []
    sqft_per_cell = (CELL_IN / 12) ** 2
    for idx, (lb, _, _) in enumerate(usable):
        rr, cc = np.nonzero(grid == idx)
        if len(rr) == 0:
            warnings.append(f"'{lb.name}' ended up with no floor cells.")
            continue
        rooms.append(Room(
            id=idx, name=lb.name, dims_text=lb.dims, dims_ft=parse_dims(lb.dims),
            area_sqft=round(len(rr) * sqft_per_cell, 1), cells=int(len(rr)),
            bbox_cells=(int(cc.min()), int(rr.min()), int(cc.max()), int(rr.max())),
            center_cells=(round(float(cc.mean()), 1), round(float(rr.mean()), 1)),
            kind=kind_of(lb.name),
        ))
    # whatever no room could reach is closed off: counters, tubs, window strips
    grid[grid == UNASSIGNED] = FIXTURE

    entrance = None
    if entrance_px:
        entrance = (int(entrance_px[0] / cell_px), int(entrance_px[1] / cell_px))

    return SpaceMap(cols=cols, rows=rows, cell_in=CELL_IN, px_per_ft=px_per_ft,
                    scale_source=scale_source, grid=grid.tolist(), rooms=rooms,
                    entrance=entrance, image_size=(w, h), warnings=warnings)


def labels_from_ai(ai: dict, w: int, h: int) -> tuple[list[Label], tuple[float, float] | None]:
    """Clean up the vision model's answer. Models sometimes return 0-1000 normalized coords."""
    rooms = ai.get("rooms") or []
    pts = [(float(r.get("x", 0)), float(r.get("y", 0))) for r in rooms if isinstance(r, dict)]
    # 0-1000 coords give themselves away when some point lands past the image edge
    normalized = bool(pts) and max(max(p) for p in pts) <= 1000 \
        and any(p[0] > w or p[1] > h for p in pts)
    sx, sy = (w / 1000, h / 1000) if normalized else (1.0, 1.0)

    labels, seen = [], set()
    for r in rooms:
        if not isinstance(r, dict) or not r.get("name"):
            continue
        key = (r["name"].strip().lower(), round(float(r.get("x", 0))), round(float(r.get("y", 0))))
        if key in seen:
            continue
        seen.add(key)
        labels.append(Label(name=str(r["name"]).strip(), dims=str(r.get("dims") or ""),
                            x=float(r.get("x", 0)) * sx, y=float(r.get("y", 0)) * sy))
    ent = ai.get("entrance")
    entrance = (float(ent["x"]) * sx, float(ent["y"]) * sy) if isinstance(ent, dict) and "x" in ent else None
    return labels, entrance


def read_floor_plan(image_bytes: bytes, router) -> SpaceMap:
    gray = load_work_image(image_bytes)
    h, w = gray.shape
    png = io.BytesIO()
    Image.fromarray(gray).save(png, format="PNG")
    ai = router.see(READ_PROMPT.format(w=w, h=h), png.getvalue())
    labels, entrance = labels_from_ai(ai, w, h)
    try:
        width_hint = float(ai.get("estimated_width_ft") or 0) or None
    except (TypeError, ValueError):
        width_hint = None
    smap = build_space_map(gray, labels, entrance, width_hint)
    if not labels:
        smap.warnings.insert(0, "The vision model found no room labels. Name the rooms by hand.")
    return smap