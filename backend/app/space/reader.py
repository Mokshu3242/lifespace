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
DOOR_LINE_PX = 4           # wall lines thinner than this are door leaves and swing arcs, not walls
FIXTURE = -4              # enclosed pockets nobody can walk into: counters, tubs, window strips

PACK_ROOMS = {
    "home": "bedroom, bathroom, kitchen, living room, dining area, hallway, closet, foyer, laundry",
    "office": "open work area, private office, meeting room, reception, pantry, lounge, phone booth, "
              "restroom, storage, server room, hallway",
}


def context_line(pack: str = "home", describe: str = "") -> str:
    """One line that tells the models what kind of space this is."""
    pack = pack if pack in PACK_ROOMS else "home"
    what = f"{pack} ({describe})" if describe else pack
    return (f"This plan is {'an' if pack == 'office' else 'a'} {what}. Use names that fit this kind of space. "
            f"Typical spaces here: {PACK_ROOMS[pack]}.\n")


OVERVIEW_PROMPT = """{context}This is a floor plan. Red rings with numbers 1 to {n} mark its spaces.
Answer two things:
- "entrance": the number of the space the main entrance door opens into, or null if you can't tell.
- "estimated_width_ft": the real width of the whole drawing in feet. Judge it from things with standard sizes:
  an interior door is about 3 ft wide, an office chair about 2 ft, a desk about 5 ft, a sofa about 7 ft,
  a bed about 5 to 6.5 ft, a toilet about 2.5 ft long.
Reply as JSON: {{"entrance": 1, "estimated_width_ft": 40}}"""

NAME_PROMPT = """{context}Each tile is a zoomed-in piece of one floor plan. The number above a tile is that tile's id.
The red ring marks ONE space; that space is shown clearly and everything around it is faded (a room, hallway, closet, open area or outdoor space).
For each tile, look only at the space the ring sits in, and give:
- "text": any room name printed inside that space, copied exactly, or "" if none
- "dims": a size printed inside that space, copied exactly as written (like 14'6" x 20'5"), or "" if none.
  Only copy what is actually printed. Never make up a size.
- "reason": a few words on what you see that decides the name (for example "bed and nightstand")
- "name": the space's name. Use the printed name if there is one. If not, name it by what is drawn in it:
  bed = Bedroom, toilet or tub = Bathroom, stove or sink with counters = Kitchen, table with chairs = Dining Area
  in a home or Meeting Room in an office, sofa = Living Room or Lounge, several desks = Work Area,
  a single desk = Office, an empty strip that connects rooms = Hallway, a small enclosed space = Closet.
Tile ids: {ids}.
Reply as JSON: {{"tiles": [{{"id": 1, "text": "", "dims": "", "reason": "...", "name": "..."}}]}}"""


# ---------------------------------------------------------------- data shapes
@dataclass
class Label:
    name: str
    dims: str
    x: float
    y: float
    source: str = ""        # "printed", "models agree", "referee", "one model", "none"
    note: str = ""          # the reasons behind the name
    unsure: bool = False    # true when the models disagreed or only one answered


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
    source: str = ""
    note: str = ""
    unsure: bool = False


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
    items: list[dict] = field(default_factory=list)    # furniture already on the plan, matched to the catalog

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
            "items": self.items,
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
    arr = np.array(img)
    # a frame drawn around the whole image is not the building's wall
    m = 3
    arr[:m, :] = 255
    arr[-m:, :] = 255
    arr[:, :m] = 255
    arr[:, -m:] = 255
    return arr


def find_walls(gray: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Returns (walls, furniture) masks.

    Walls: the big connected network of wall pixels. Plans draw walls in black, dark gray or
    light gray, so try cutoffs from dark to light and use the first one where one connected
    piece spans most of the plan.
    Furniture: the smaller pieces that are closed outlines (tables, sofas, tubs, counters),
    filled in so people walk around them. Text, door swings and dimension marks are open
    strokes or tiny, so they drop out."""
    h, w = gray.shape
    side = max(h, w)
    # Walls drawn as two lines with a light fill between them only come out solid at a light
    # cutoff, so use the LIGHTEST cutoff where one piece spans the plan but the floor stays clear.
    chosen = None
    for cutoff in (110, 150, 190, 215, 235):
        dark = (gray < cutoff).astype(np.uint8)
        n_c, lab_c, st_c, _ = cv2.connectedComponentsWithStats(dark, 8)
        if n_c < 2:
            continue
        top = 1 + int(np.argmax(st_c[1:, 4]))
        _, _, bw, bh, area = st_c[top]
        spans = bw >= 0.5 * w and bh >= 0.5 * h
        if spans and area <= 0.35 * w * h:
            chosen = (n_c, lab_c, st_c)
        elif chosen is not None:
            break
    if chosen is None:  # fall back to the darkest cutoff
        dark = (gray < 110).astype(np.uint8)
        chosen = cv2.connectedComponentsWithStats(dark, 8)[:3]
    n, lab, stats = chosen
    walls = np.zeros((h, w), bool)
    furniture = np.zeros((h, w), bool)
    top = 1 + int(np.argmax(stats[1:, 4]))
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        big = max(bw, bh)
        # walls are long and thin; a big but compact shape (table with chairs) is furniture
        if i == top or (big >= 0.15 * side and area < 0.25 * bw * bh and min(bw, bh) < 0.05 * side):
            walls |= lab == i
        elif big >= 0.03 * side:
            # a closed outline encloses empty space; fill it and see how much it grew
            piece = (lab[y:y + bh, x:x + bw] == i).astype(np.uint8)
            contours, _ = cv2.findContours(piece, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            filled = np.zeros_like(piece)
            cv2.drawContours(filled, contours, -1, 1, -1)
            if filled.sum() >= 1.5 * piece.sum() or piece.sum() >= 0.5 * bw * bh:
                furniture[y:y + bh, x:x + bw] |= filled.astype(bool)
    # close hairline gaps in the wall drawing
    walls = cv2.morphologyEx(walls.astype(np.uint8), cv2.MORPH_CLOSE, np.ones((3, 3), np.uint8)).astype(bool)
    return walls, furniture & ~walls


def seal(walls: np.ndarray, k: int) -> np.ndarray:
    """Close gaps up to k px wide (doors, windows) so spaces become closed areas."""
    # pad first: near the image edge, closing would grow walls out to the border and
    # seal the margin around the building shut, making it look like indoors
    p = k + 2
    padded = cv2.copyMakeBorder(walls.astype(np.uint8), p, p, p, p, cv2.BORDER_CONSTANT, value=0)
    closed = cv2.morphologyEx(padded, cv2.MORPH_CLOSE,
                              cv2.getStructuringElement(cv2.MORPH_RECT, (k, k)))
    return closed[p:-p, p:-p].astype(bool)


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
        # No labels yet: outside leaking through a door makes the inside area collapse.
        # Take the smallest size whose inside area is close to the best one.
        areas = [(k, int((~walls & ~outside_mask(walls, k)).sum())) for k in sizes]
        top = max(a for _, a in areas)
        return next(k for k, a in areas if a >= 0.95 * top)
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
CHAIR_IN = 22   # most chairs and stools on plans are 18 to 26 in across


def chair_scale(blocked: np.ndarray) -> tuple[float, int] | None:
    """px per ft from chairs. Plans repeat one chair size many times, so the biggest group of
    near-square shapes that agree on size (4+ of them) is almost always the chairs."""
    n, lab, st, _ = cv2.connectedComponentsWithStats(blocked.astype(np.uint8), 8)
    min_px = max(6, 0.015 * max(blocked.shape))      # smaller is a symbol or a speck, not a chair
    sizes = []
    for i in range(1, n):
        _, _, bw, bh, area = (int(v) for v in st[i])
        if min(bw, bh) >= min_px and 0.7 <= bw / bh <= 1.4 and area >= 0.6 * bw * bh:
            sizes.append((bw + bh) / 2)
    best: list[float] = []
    for c in sizes:
        group = [s for s in sizes if abs(s - c) <= 0.2 * c]
        if len(group) > len(best):
            best = group
    if len(best) < 4:
        return None
    return float(np.median(best)) / (CHAIR_IN / 12), len(best)


def build_space_map(gray: np.ndarray, labels: list[Label],
                    entrance_px: tuple[float, float] | None,
                    width_ft_hint: float | None = None,
                    entrance_label: int | None = None) -> SpaceMap:
    h, w = gray.shape
    warnings: list[str] = []
    walls, furniture = find_walls(gray)
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
    else:
        blocked = np.zeros_like(walls)
    blocked = (blocked | furniture) & inside_free
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
    room_px[blocked] = FIXTURE
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
        estimates.append((bw / pair[0] + bh / pair[1]) / 2)   # one estimate per room
    # A misread or made-up size gives a scale that disagrees with the rest. Keep only rooms
    # within 25% of the middle value, and trust the result only if 2+ rooms agree.
    agreeing = []
    if estimates:
        mid = float(np.median(estimates))
        agreeing = [e for e in estimates if abs(e - mid) <= 0.25 * mid]
    if len(agreeing) >= 2:
        px_per_ft = float(np.median(agreeing))
        scale_source = f"printed sizes: {len(agreeing)} of {len(estimates)} rooms agree"
    elif width_ft_hint and 8 <= width_ft_hint <= 400:
        px_per_ft = w / width_ft_hint
        scale_source = f"estimated by the vision model from doors and furniture ({width_ft_hint:.0f} ft wide)"
        warnings.append("No printed sizes on the plan. Scale was estimated from doors and furniture; check it.")
        # Chairs are a better ruler than a model's guess (models gave 40, 50 and 60 ft for the
        # same 40 ft office). When 4+ chairs agree, they set the scale.
        chairs = chair_scale(blocked)
        if chairs and abs(chairs[0] - px_per_ft) > 0.05 * chairs[0]:
            px_per_ft = chairs[0]
            warnings[-1] = f"No printed sizes on the plan. Scale was measured from {chairs[1]} chairs; check it."
            scale_source = (f"measured from {chairs[1]} chairs (about {CHAIR_IN} in each); the model "
                            f"guessed {width_ft_hint:.0f} ft wide")
            warnings[-1] = f"No printed sizes on the plan. Scale was measured from {chairs[1]} chairs; check it."
        # Sanity check: only catch an estimate that is clearly broken. Offices split into many
        # small spaces (booths, desk pods), so a 50 sq ft middle room is normal there.
        by_name: dict[str, int] = {}
        for i, (lb, _, _) in enumerate(usable):
            if kind_of(lb.name) in ("room", "open"):
                key = lb.name.strip().lower()
                by_name[key] = by_name.get(key, 0) + int((room_px == i).sum())
        core_px = [a for a in by_name.values() if a > 0]
        if core_px:
            mid_sqft = float(np.median(core_px)) / px_per_ft ** 2
            if not 25 <= mid_sqft <= 600:
                px_per_ft = (float(np.median(core_px)) / 150) ** 0.5
                scale_source = (f"room-size check: the estimate ({width_ft_hint:.0f} ft wide) gave rooms of "
                                f"{mid_sqft:.0f} sq ft, so scale was set to make a typical room 150 sq ft")
    else:
        px_per_ft = w / 60.0
        scale_source = "guess: no printed sizes found, assumed plan is 60 ft wide"
        warnings.append("No room sizes found on the plan. Scale is a guess; set it by hand.")

    # ---- doors: plans draw a door as thin lines (the leaf, a dotted swing arc) across the opening.
    # Those lines are part of the wall drawing but nobody walks into them as walls, so strip lines
    # thinner than real walls before making the grid. The opening becomes floor people can pass.
    thick = cv2.morphologyEx(walls.astype(np.uint8), cv2.MORPH_OPEN,
                             np.ones((DOOR_LINE_PX, DOOR_LINE_PX), np.uint8)).astype(bool)
    room_px[walls & ~thick] = UNASSIGNED

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

    # ---- one space can carry several marks; if the model named them the same and they're near, join them
    names = [lb.name.strip().lower() for lb, _, _ in usable]
    for i in range(len(usable)):
        for j in range(i + 1, len(usable)):
            if names[i] != names[j] or not (grid == i).any() or not (grid == j).any():
                continue
            # "near" = within about a foot, so a table that cuts a room in two doesn't split it
            a = cv2.dilate((grid == i).astype(np.uint8), np.ones((5, 5), np.uint8)).astype(bool)
            b = grid == j
            if (a & b).any():
                grid[b] = i

    # ---- room summaries
    rooms: list[Room] = []
    sqft_per_cell = (CELL_IN / 12) ** 2
    for idx, (lb, _, _) in enumerate(usable):
        rr, cc = np.nonzero(grid == idx)
        if len(rr) == 0:
            if not any(names[j] == names[idx] for j in range(idx)):
                warnings.append(f"'{lb.name}' ended up with no floor cells.")
            continue
        rooms.append(Room(
            id=idx, name=lb.name, dims_text=lb.dims, dims_ft=parse_dims(lb.dims),
            area_sqft=round(len(rr) * sqft_per_cell, 1), cells=int(len(rr)),
            bbox_cells=(int(cc.min()), int(rr.min()), int(cc.max()), int(rr.max())),
            center_cells=(round(float(cc.mean()), 1), round(float(rr.mean()), 1)),
            kind=kind_of(lb.name), source=lb.source, note=lb.note, unsure=lb.unsure,
        ))
    # whatever no room could reach is closed off: counters, tubs, window strips
    grid[grid == UNASSIGNED] = FIXTURE

    entrance = None
    if entrance_px:
        entrance = (int(entrance_px[0] / cell_px), int(entrance_px[1] / cell_px))
    elif entrance_label is not None and (grid == entrance_label).any():
        # the room's cell closest to outside is where the front door is
        rr, cc = np.nonzero(grid == entrance_label)
        orr, occ = np.nonzero(grid == OUTSIDE)
        if len(orr):
            d = np.min((rr[:, None] - orr[None]) ** 2 + (cc[:, None] - occ[None]) ** 2, axis=1) \
                if len(rr) * len(orr) < 4_000_000 else (rr - rr.mean()) ** 2
            j = int(np.argmin(d))
            entrance = (int(cc[j]), int(rr[j]))

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


def find_marks(gray: np.ndarray, with_floor: bool = False):
    """Places one point inside every space, using code only.
    Rooms: the sealed cores. Small spaces (closets) vanish when sealed, so wide-enough leftover
    pockets get a point too. Each point is the spot farthest from any wall, so it sits well inside."""
    walls, furniture = find_walls(gray)
    k = choose_seal_size(walls, [])
    # furniture only matters for walking; for finding spaces, look at the bare floor
    inside = ~walls & ~outside_mask(walls, k)
    # closed pockets (tables, tubs) are furniture
    n, lab, st, _ = cv2.connectedComponentsWithStats(inside.astype(np.uint8), 4)
    if n > 2:
        main = int(st[1:, 4].max())
        inside &= ~np.isin(lab, [i for i in range(1, n) if st[i, 4] < 0.03 * main])
    total = max(1, int(inside.sum()))
    sealed = seal(walls, k)
    cores = inside & ~sealed
    marks: list[tuple[int, int]] = []

    def add_points(mask: np.ndarray, min_area: float, min_depth: float, many: bool) -> None:
        n, lab, st, _ = cv2.connectedComponentsWithStats(mask.astype(np.uint8), 4)
        for i in range(1, n):
            if st[i, 4] < min_area:
                continue
            comp = (lab == i).astype(np.uint8)
            first = None
            for _ in range(5 if many else 1):
                dist = cv2.distanceTransform(comp, cv2.DIST_L2, 5)
                depth = float(dist.max())
                if depth < max(min_depth, 1) or (first and depth < 0.45 * first):
                    break
                first = first or depth
                y, x = np.unravel_index(int(np.argmax(dist)), dist.shape)
                marks.append((int(x), int(y)))
                # open-plan areas (living + dining + kitchen) hold several spaces:
                # blank out this one and look for the next deep spot
                cv2.circle(comp, (int(x), int(y)), int(1.3 * depth), 0, -1)

    add_points(cores, 0.004 * total, 0.3 * k, many=True)
    leftover = inside & ~cv2.dilate(cores.astype(np.uint8), np.ones((3, 3), np.uint8)).astype(bool)
    add_points(leftover, 0.003 * total, 0.25 * k, many=False)

    # gaps between chairs and desks can look like tiny spaces; keep one mark per neighbourhood
    kept: list[tuple[int, int]] = []
    for x, y in marks:
        if all((x - a) ** 2 + (y - b) ** 2 >= (0.8 * k) ** 2 for a, b in kept):
            kept.append((x, y))
    marks[:] = kept
    marks.sort(key=lambda p: (p[1] // max(1, gray.shape[0] // 6), p[0]))  # read order: rows, then left to right
    return (marks, inside) if with_floor else marks


def mark_regions(floor: np.ndarray, marks: list[tuple[int, int]], step: int = 3) -> np.ndarray:
    """Which mark owns each floor pixel, by walking distance (never through walls).
    Done on a 1/step grid for speed, then scaled back up. -1 = no owner."""
    h, w = floor.shape
    small = cv2.resize(floor.astype(np.uint8), (w // step, h // step), interpolation=cv2.INTER_NEAREST)
    sh, sw = small.shape
    owner = np.full((sh, sw), -1, np.int32)
    frontier = []
    for i, (x, y) in enumerate(marks):
        r, c = min(sh - 1, y // step), min(sw - 1, x // step)
        owner[r, c] = i
        frontier.append((r, c))
    while frontier:
        nxt = []
        for r, c in frontier:
            v = owner[r, c]
            for dr, dc in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                rr, cc = r + dr, c + dc
                if 0 <= rr < sh and 0 <= cc < sw and owner[rr, cc] == -1 and small[rr, cc]:
                    owner[rr, cc] = v
                    nxt.append((rr, cc))
        frontier = nxt
    return cv2.resize(owner, (w, h), interpolation=cv2.INTER_NEAREST)


def _ring(img: np.ndarray, x: int, y: int, r: int, label: str | None) -> None:
    """A hollow red ring, so printed room names under it stay readable."""
    cv2.circle(img, (x, y), r, (255, 255, 255), 5)
    cv2.circle(img, (x, y), r, (40, 40, 220), 3)
    if label:
        scale = max(0.45, r / 26)
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, scale, 2)
        tx, ty = x + r - 2, y - r + 2
        cv2.rectangle(img, (tx - 3, ty - th - 4), (tx + tw + 3, ty + 4), (40, 40, 220), -1)
        cv2.putText(img, label, (tx, ty), cv2.FONT_HERSHEY_SIMPLEX, scale, (255, 255, 255), 2)


def draw_marks(gray: np.ndarray, marks: list[tuple[int, int]]) -> bytes:
    img = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    r = max(10, int(0.014 * max(gray.shape)))
    for i, (x, y) in enumerate(marks, start=1):
        _ring(img, x, y, r, str(i))
    ok, buf = cv2.imencode(".png", img)
    return buf.tobytes()


TILE = 400          # px per tile on a naming sheet
TILES_PER_SHEET = 6  # 3 x 2; small models stay accurate with a handful at a time


def draw_sheets(gray: np.ndarray, marks: list[tuple[int, int]],
                regions: np.ndarray | None = None,
                only: list[int] | None = None) -> list[tuple[bytes, list[int]]]:
    """Cut a zoomed view of each space and lay them out on sheets, numbered.
    Each tile is cropped to its own space and everything outside it is faded, so the model reads
    THIS room's printed name and furniture, not the bold label of the room next door."""
    h, w = gray.shape
    color = cv2.cvtColor(gray, cv2.COLOR_GRAY2BGR)
    sheets = []
    numbers = only if only is not None else list(range(1, len(marks) + 1))
    for start in range(0, len(numbers), TILES_PER_SHEET):
        ids = numbers[start:start + TILES_PER_SHEET]
        cols = 3
        rows = (len(ids) + cols - 1) // cols
        cap = 34
        sheet = np.full((rows * (TILE + cap), cols * TILE, 3), 255, np.uint8)
        for k, n in enumerate(ids):
            x, y = marks[n - 1]
            img = color
            if regions is not None and (regions == n - 1).any():
                own = cv2.dilate((regions == n - 1).astype(np.uint8),
                                 np.ones((7, 7), np.uint8)).astype(bool)
                ys, xs = np.nonzero(own)
                x0, x1, y0, y1 = int(xs.min()), int(xs.max()), int(ys.min()), int(ys.max())
                faded = (color * 0.18 + 255 * 0.82).astype(np.uint8)
                img = np.where(own[:, :, None], color, faded)
            else:
                x0, x1, y0, y1 = x - 60, x + 60, y - 60, y + 60
            # square window around the space, with a margin, never smaller than a closet needs
            half = max(x1 - x0, y1 - y0) // 2 + max(12, int(0.12 * max(x1 - x0, y1 - y0)))
            half = max(half, int(0.08 * max(h, w)))
            cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
            X0, Y0, X1, Y1 = cx - half, cy - half, cx + half, cy + half
            crop = img[max(0, Y0):min(h, Y1), max(0, X0):min(w, X1)]
            pad = cv2.copyMakeBorder(crop, max(0, -Y0), max(0, Y1 - h), max(0, -X0), max(0, X1 - w),
                                     cv2.BORDER_CONSTANT, value=(255, 255, 255))
            f = TILE / (2 * half)
            tile = cv2.resize(pad, (TILE, TILE), interpolation=cv2.INTER_AREA if f < 1 else cv2.INTER_CUBIC)
            _ring(tile, int((x - X0) * f), int((y - Y0) * f), 18, None)
            r, c = divmod(k, cols)
            oy, ox = r * (TILE + cap), c * TILE
            sheet[oy + cap:oy + cap + TILE, ox:ox + TILE] = tile
            cv2.rectangle(sheet, (ox, oy + cap), (ox + TILE - 1, oy + cap + TILE - 1), (160, 160, 160), 1)
            cv2.putText(sheet, str(n), (ox + 8, oy + 26), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (40, 40, 220), 2)
        ok, buf = cv2.imencode(".png", sheet)
        sheets.append((buf.tobytes(), ids))
    return sheets


def read_floor_plan(image_bytes: bytes, router, pack: str = "home", describe: str = "") -> SpaceMap:
    context = context_line(pack, describe)
    gray = load_work_image(image_bytes)
    marks, floor = find_marks(gray, with_floor=True)
    if not marks:
        smap = build_space_map(gray, [], None)
        smap.warnings.insert(0, "Couldn't find any closed spaces. Is this a top-down floor plan?")
        return smap

    # 1) names and printed sizes: OCR first, then two models, then a referee if they disagree
    from app.space.naming import name_spaces
    regions = mark_regions(floor, marks)
    from app.space import ocr
    all_texts = ocr.read_all(gray)          # read the plan's text once, for names and the entrance
    labels = name_spaces(gray, marks, regions, router, context,
                         texts=[t for t in all_texts if t.is_dims or ocr._is_name(t.text)])

    # 2) entrance and overall width: one look at the whole plan
    overview = router.see(OVERVIEW_PROMPT.format(context=context, n=len(marks)), draw_marks(gray, marks))
    try:
        ent = int(overview.get("entrance")) - 1
        entrance_idx = ent if 0 <= ent < len(marks) else None
    except (TypeError, ValueError):
        entrance_idx = None
    try:
        width_hint = float(overview.get("estimated_width_ft") or 0) or None
    except (TypeError, ValueError):
        width_hint = None

    smap = build_space_map(gray, labels, None, width_hint, entrance_label=entrance_idx)

    # 2b) a printed "Entrance" beats the model's guess: the door is the floor right next to that label
    door = ocr.entrance_marks(all_texts)
    if door:
        g = np.array(smap.grid)
        cell_px = smap.px_per_ft * smap.cell_in / 12
        t = max(door, key=lambda t: t.conf)
        tc, tr = t.x / cell_px, t.y / cell_px
        # front doors open into a foyer, entry, hall or living area, not a bath or closet
        def pick(room_ids):
            ys, xs = np.nonzero(np.isin(g, list(room_ids)))
            if not len(ys):
                return None
            d = (xs - tc) ** 2 + (ys - tr) ** 2
            j = int(np.argmin(d))
            return (int(xs[j]), int(ys[j])) if d[j] <= (12 * 12 / smap.cell_in) ** 2 else None
        entry_like = {r.id for r in smap.rooms if any(w in r.name.lower() for w in ("foyer", "entry", "hall", "vestibule", "mud", "living", "lobby", "reception"))}
        not_private = {r.id for r in smap.rooms if r.kind not in ("bath", "closet")}
        spot = pick(entry_like) or pick(not_private) or pick({r.id for r in smap.rooms})
        if spot:
            smap.entrance = spot
    # 3) furniture already drawn on the plan, matched to real catalog items
    from app.space.items import detect_items, to_dicts
    smap.items = to_dicts(detect_items(gray, smap.grid, smap.rooms, smap.px_per_ft, smap.cell_in,
                                       pack, router, context))

    unnamed = sum(1 for lb in labels if lb.name.startswith("Space "))
    if unnamed:
        smap.warnings.insert(0, f"{unnamed} spaces have no name yet. Select them and type one.")
    return smap
