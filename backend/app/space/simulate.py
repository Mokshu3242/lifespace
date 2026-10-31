"""AI people live one day in a space: code walks them through it, so every number is real.

Each person has a body width (a walker or wheelchair needs more floor) and a routine
("06:30 wash", "07:15 cook"...). For each step, code finds where that happens (an item with
that use, or a room for it), then finds the shortest path a body that wide can fit through.
The same routine runs Before and After a redesign, so the two can be compared fairly.
The model only writes a short line in each person's voice, from these numbers."""
import heapq
import json
import logging
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

import cv2
import numpy as np

from app import catalog
from app.space.redesign import occupancy

log = logging.getLogger("simulate")

PACKS_DIR = Path(__file__).resolve().parents[2] / "data" / "packs"
TIGHT_SPARE_IN = 6         # less than this much room on each side counts as a tight squeeze
SQUEEZE_IN = 4             # a body may brush past by this much (clothes, a turned shoulder)
TIGHT_COST = 3.0           # people avoid tight spots if there's a reasonable way around

# where each use happens: item uses first, then room names
USE_ROOMS = {
    "wash": ["bath", "restroom", "wc", "toilet"],
    "cook": ["kitchen", "pantry"],
    "eat": ["dining", "kitchen", "pantry"],
    "sit": ["living", "lounge", "family"],
    "outdoor": ["terrace", "balcony", "patio", "garden"],
    "work": ["office", "study", "work", "dining"],
    "meet": ["meeting", "conference"],
    "drink": ["pantry", "kitchen", "cafe"],
    "greet": ["reception", "lobby"],
    "call": ["phone", "booth", "meeting"],
}
ITEM_USES = {"drink": ["drink", "cook"], "outdoor": ["sit", "rest"], "greet": ["greet"]}

VOICE_PROMPT = """{context}These people tried a day in a space Before and After a redesign. Code measured
their day; the facts are below. Write one short first-person line (under 20 words) for each person,
for Before and for After, in their own voice, about how the space felt to live in.
Speak like a real person: name places and moments ("the bathroom door", "my night trip"), not
statistics. Don't recite the numbers; the app shows them. Every After line MUST name one of the new
things listed for that person, and say what it means for their day (a night light on the way to the
bathroom at night, a smoke alarm near where they sleep), even when their walk is the same. If a new
thing is in a room they can't get into, say that honestly ("a grab bar in the bath, but I still can't
get through the door"). Only when "New in the rooms they use" is "nothing" may they say it feels the same. If After is worse, say so honestly.
Stay true to the facts below. No medical advice.
Redesign changes: {changes}
{people}
Reply as JSON: {{"voices": {{"person-id": {{"before": "...", "after": "..."}}}}}}"""


@lru_cache
def load_personas(pack: str) -> tuple[dict, ...]:
    p = PACKS_DIR / pack / "personas.json"
    return tuple(json.loads(p.read_text(encoding="utf-8"))["personas"])


@dataclass
class Leg:
    t: str
    use: str
    note: str
    room: str = ""
    path: list = field(default_factory=list)   # [[col, row], ...]
    ft: float = 0
    tight_ft: float = 0
    blocked: bool = False
    why: str = ""


@dataclass
class Day:
    legs: list[Leg]
    walked_ft: float = 0
    tight_ft: float = 0
    blocked: int = 0
    missing: int = 0           # steps with nowhere in the space to do them

    def to_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------- the walkable floor
class Floor:
    def __init__(self, space: dict, items: list[dict], pack: str):
        self.grid = np.array(space["grid"])
        self.cell_in = space["cell_in"]
        self.free = occupancy(self.grid, items, pack)
        self.items = [it for it in items if it.get("status", "kept") in ("kept", "new")]
        self.pack = pack
        self.rooms = space["rooms"]
        ent = space.get("entrance")
        if ent:
            c, r = ent
            if 0 <= r < self.grid.shape[0] and 0 <= c < self.grid.shape[1]:
                self.free[r, c] = True
        self.entrance = tuple(ent) if ent else None
        # distance (in cells) from each free cell to the nearest blocked cell
        self.dt = cv2.distanceTransform(self.free.astype(np.uint8), cv2.DIST_L2, 5)

    def clear_in(self) -> np.ndarray:
        """Open floor width around each cell, in inches."""
        # dt is measured from cell centers, so an opening n cells wide peaks at about n/2.
        # 2*dt - 0.5 cells is within a quarter cell (1.5 in) of the true width for odd and even n.
        return np.maximum(0, 2 * self.dt - 0.5) * self.cell_in

    def fits(self, width_in: float) -> np.ndarray:
        """Cells a body this wide can stand on: some square of that width, on open floor, covers it.
        (A morphological opening; exact on the 6 in grid for any door width.)"""
        k = max(1, int(np.ceil(width_in / self.cell_in - 1e-6)))
        kernel = np.ones((k, k), np.uint8)
        return cv2.morphologyEx(self.free.astype(np.uint8), cv2.MORPH_OPEN, kernel,
                                borderType=cv2.BORDER_CONSTANT, borderValue=0).astype(bool) & self.free

    def room_cells(self, room_id: int) -> np.ndarray:
        return self.grid == room_id


def _astar(passable: np.ndarray, tight: np.ndarray, start: tuple[int, int], goal: tuple[int, int]):
    """Shortest path over passable cells, 8 directions, tight cells cost more. Cells are (r, c)."""
    rows, cols = passable.shape
    if not (passable[start] and passable[goal]):
        return None
    gr, gc = goal
    best = {start: 0.0}
    came = {}
    heap = [(0.0, 0.0, start)]
    steps = [(-1, 0, 1), (1, 0, 1), (0, -1, 1), (0, 1, 1),
             (-1, -1, 1.414), (-1, 1, 1.414), (1, -1, 1.414), (1, 1, 1.414)]
    while heap:
        _, g, cur = heapq.heappop(heap)
        if cur == goal:
            path = [cur]
            while cur in came:
                cur = came[cur]
                path.append(cur)
            return path[::-1]
        if g > best.get(cur, 1e18):
            continue
        r, c = cur
        for dr, dc, cost in steps:
            nr, nc = r + dr, c + dc
            if not (0 <= nr < rows and 0 <= nc < cols) or not passable[nr, nc]:
                continue
            if dr and dc and not (passable[r, nc] and passable[nr, c]):
                continue                       # no cutting corners through walls
            ng = g + cost * (TIGHT_COST if tight[nr, nc] else 1.0)
            if ng < best.get((nr, nc), 1e18):
                best[(nr, nc)] = ng
                came[(nr, nc)] = cur
                h = max(abs(nr - gr), abs(nc - gc))
                heapq.heappush(heap, (ng + h, ng, (nr, nc)))
    return None


def _nearest(mask: np.ndarray, r: int, c: int) -> tuple[int, int] | None:
    ys, xs = np.nonzero(mask)
    if not len(ys):
        return None
    j = int(np.argmin((ys - r) ** 2 + (xs - c) ** 2))
    return int(ys[j]), int(xs[j])


def _rooms_for(floor: Floor, use: str, home: str) -> list[dict]:
    if use == "sleep":
        keys = [home, "bedroom"]
    elif use in USE_ROOMS:
        keys = USE_ROOMS[use]
    else:
        keys = [use]
    found = []
    for k in keys:                              # every room that fits; the walk decides which one
        found += [r for r in floor.rooms if k and k in r["name"].lower() and r not in found]
        if use == "sleep" and found:
            break                               # their own bed first
    return found


def _target(floor: Floor, use: str, home: str, passable: np.ndarray, at: tuple[int, int]):
    """Best place for a step: (cell, room name) or (None, reason)."""
    opts = _targets(floor, use, home, passable, at)
    return opts[0] if opts and opts[0][0] is not None else (opts[0] if opts else (None, "nowhere"))


def _targets(floor: Floor, use: str, home: str, passable: np.ndarray, at: tuple[int, int]) -> list:
    """Every place a step could happen, nearest first: [(cell, room name)], or [(None, reason)]."""
    if use in ("exit", "enter"):
        if floor.entrance is None:
            return None, "no entrance marked"
        c, r = floor.entrance
        cell = _nearest(passable, r, c)
        return [(cell, "entrance")] if cell else [(None, "can't reach the door")]
    rooms = _rooms_for(floor, use, home)
    want = set(ITEM_USES.get(use, [use]))
    # an item made for this use, in one of those rooms (or anywhere if no room fits)
    room_ids = {r["id"] for r in rooms}
    cands = []
    for it in floor.items:
        c = catalog.get(floor.pack, it.get("item", ""))
        if c is None or not (want & set(c.uses)):
            continue
        if room_ids and it.get("room") not in room_ids:
            continue
        cands.append(it)
    found = []
    for it in cands:
        r0 = int(it["y"] - it["d"] / 2) - 2
        c0 = int(it["x"] - it["w"] / 2) - 2
        r1 = int(it["y"] + it["d"] / 2) + 2
        c1 = int(it["x"] + it["w"] / 2) + 2
        ring = np.zeros_like(passable)
        ring[max(0, r0):r1 + 1, max(0, c0):c1 + 1] = True
        cell = _nearest(ring & passable, *at)
        if cell is not None:
            d = (cell[0] - at[0]) ** 2 + (cell[1] - at[1]) ** 2
            name = next((r["name"] for r in floor.rooms if r["id"] == it.get("room")), "")
            found.append((d, cell, name or it["name"]))
    if not rooms and not found:
        return [(None, f"no place to {use} here")]
    # no item: the most open spot of the nearest matching room
    opts = []
    for room in rooms:
        m = floor.room_cells(room["id"]) & passable
        if not m.any():
            continue
        score = np.where(m, floor.dt, -1)
        r, c = np.unravel_index(int(np.argmax(score)), score.shape)
        opts.append(((r - at[0]) ** 2 + (c - at[1]) ** 2, (int(r), int(c)), room["name"]))
    opts += found
    if not opts:
        return [(None, f"the {rooms[0]['name'].lower()} has no room to stand")]
    opts.sort(key=lambda o: o[0])
    return [(o[1], o[2]) for o in opts]


def live_a_day(floor: Floor, person: dict) -> Day:
    width = float(person["width_in"])
    passable = floor.fits(width - SQUEEZE_IN)
    tight = passable & ~floor.fits(width + 2 * TIGHT_SPARE_IN)
    home = person.get("home", "bedroom")
    ft_per_cell = floor.cell_in / 12

    # start in their home room
    start, _ = _target(floor, "sleep", home, passable, (0, 0))
    if start is None:
        start = _nearest(passable, floor.grid.shape[0] // 2, floor.grid.shape[1] // 2)
    at = start
    legs = []
    for step in person["day"]:
        leg = Leg(t=step["t"], use=step["use"], note=step.get("note", ""))
        legs.append(leg)
        if at is None:
            leg.blocked, leg.why = True, "stuck: no floor wide enough to stand on"
            continue
        options = _targets(floor, step["use"], home, passable, at)
        if options[0][0] is None:
            leg.blocked, leg.why = True, options[0][1]
            continue
        path, goal, where = None, None, options[0][1]
        for cell, name in options[:6]:          # nearest first; take the first one they can reach
            path = _astar(passable, tight, at, cell)
            if path is not None:
                goal, where = cell, name
                break
        leg.room = where
        if path is None:
            tried = sorted({n.lower() for _, n in options[:6]})
            leg.blocked = True
            leg.why = f"can't get to the {' or the '.join(tried)}: no path {width:.0f} in wide"
            continue
        leg.path = [[c, r] for r, c in path]
        steps = sum(1.414 if (a[0] != b[0] and a[1] != b[1]) else 1.0 for a, b in zip(path, path[1:]))
        leg.ft = round(steps * ft_per_cell, 1)
        leg.tight_ft = round(sum(1 for p in path if tight[p]) * ft_per_cell, 1)
        at = goal
    day = Day(legs=legs)
    day.walked_ft = round(sum(lg.ft for lg in legs), 1)
    day.tight_ft = round(sum(lg.tight_ft for lg in legs), 1)
    day.blocked = sum(1 for lg in legs if lg.blocked and "no place" not in lg.why)
    day.missing = sum(1 for lg in legs if lg.blocked and "no place" in lg.why)
    return day


def simulate(space: dict, after_items: list[dict] | None, router=None, context: str = "",
             changes: list[dict] | None = None, people: list[dict] | None = None) -> dict:
    pack = space.get("pack") or "home"
    people = people or load_personas(pack)
    before_floor = Floor(space, space.get("items", []), pack)
    after_floor = Floor(space, after_items if after_items is not None else space.get("items", []), pack)
    out = {"personas": [{k: p[k] for k in ("id", "name", "about", "width_in", "color")} for p in people],
           "before": {}, "after": {}, "voices": {}}
    for p in people:
        out["before"][p["id"]] = live_a_day(before_floor, p).to_dict()
        out["after"][p["id"]] = live_a_day(after_floor, p).to_dict()

    if router is not None:
        room_names = {r["id"]: r["name"] for r in space["rooms"]}
        lines = []
        for p in people:
            b, a = out["before"][p["id"]], out["after"][p["id"]]
            def blocked(d):
                return "; ".join(f"{lg['t']} {lg['note']}: {lg['why']}" for lg in d["legs"] if lg["blocked"]) or "none"
            # new things in the rooms this person spends their day in, so the voice can mention them
            visited = {lg["room"] for lg in a["legs"] if lg["room"]}
            mine = [f"{c.get('name')} in the {room_names.get(c.get('room'), '')}".lower()
                    for c in (changes or []) if not c.get("dropped")
                    and room_names.get(c.get("room")) in visited]
            lines.append(f"- {p['id']} ({p['name']}, {p['about']}): Before walked {b['walked_ft']:.0f} ft, "
                         f"{b['tight_ft']:.0f} ft of tight squeezes, blocked: {blocked(b)}. After walked "
                         f"{a['walked_ft']:.0f} ft, {a['tight_ft']:.0f} ft tight, blocked: {blocked(a)}. "
                         f"New in the rooms they use: {', '.join(mine) or 'nothing'}.")
        ch = ", ".join(f"{c.get('action')} {c.get('name')}" for c in (changes or []) if not c.get("dropped")) or "none"
        try:
            ans = router.ask_json(VOICE_PROMPT.format(context=context, changes=ch, people="\n".join(lines)))
            v = ans.get("voices") or {}
            out["voices"] = {pid: {"before": str((v.get(pid) or {}).get("before") or "")[:160],
                                   "after": str((v.get(pid) or {}).get("after") or "")[:160]}
                             for pid in out["before"]}
        except Exception as e:  # voices are a bonus; the numbers stand on their own
            log.warning("voices failed: %s", e)
        out["voice_provider"] = getattr(router, "last_provider", None)
    return out
