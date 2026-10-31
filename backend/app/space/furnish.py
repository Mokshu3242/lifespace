"""How an item really gets into a room: carried from the front door, then set down somewhere sensible.

Delivery: the item is carried at its real size. Assembled pieces (sofas, armchairs, appliances, tubs)
can be tilted, so they need a clear width of their smallest side. Flat-packed pieces (beds, tables,
shelves, wardrobes) arrive in boxes no wider than about 2 ft. Code finds a path from the entrance
where that width fits through every door, or says which width was missing.

Trying places: before the best spot, code checks the spots a person would try first (the open middle
of the room, right by the door) and records the real reason each one fails."""
import numpy as np

from app import catalog

FLAT_PACK = {"bed", "table", "storage", "decor", "light", "noise"}
FLAT_BOX_IN = 24             # flat-packed boxes are about 2 ft across
TILT_SPARE_IN = 2            # carriers can angle a piece through with a little to spare
WALL_CATS = {"bed", "storage", "media", "appliance", "fixture"}


def carry_width(item: catalog.Item) -> tuple[float, str]:
    """Clear width needed to carry this item in, and how it's carried."""
    if item.category in FLAT_PACK:
        w = min(item.w_in, item.d_in, FLAT_BOX_IN)
        return w, "arrives flat-packed"
    w = item.w_in / 2 if "(pair)" in item.name.lower() else item.w_in   # a pair comes in one at a time
    dims = [d for d in (w, item.d_in, item.h_in) if d > 0]
    return min(dims), "carried tilted on its side"


def delivery_path(floor, start: tuple[int, int] | None, spot: dict, item: catalog.Item):
    """(path [[c, r], ...], how) from the entrance to the spot, or (None, why)."""
    from app.space.simulate import _astar, _nearest

    width, how = carry_width(item)
    if start is None:
        return [], how                      # no entrance marked: skip the delivery walk
    ok = floor.fits(max(6, width - TILT_SPARE_IN))
    c, r = start
    a = _nearest(ok, r, c)
    # arrive at the open floor right next to where the item will stand
    x0, y0 = int(spot["x"] - spot["w"] / 2) - 2, int(spot["y"] - spot["d"] / 2) - 2
    x1, y1 = int(spot["x"] + spot["w"] / 2) + 2, int(spot["y"] + spot["d"] / 2) + 2
    near = np.zeros_like(ok)
    near[max(0, y0):y1 + 1, max(0, x0):x1 + 1] = True
    b = _nearest(ok & near, int(spot["y"]), int(spot["x"]))
    if a is None or b is None or (abs(a[0] - r) + abs(a[1] - c)) > 8:
        return None, f"needs about {width:.0f} in of clear width to carry in ({how}); the way in is narrower"
    path = _astar(ok, np.zeros_like(ok), a, b)
    if path is None:
        return None, f"needs about {width:.0f} in of clear width to carry in ({how}); a door on the way is narrower"
    pts = [[cc, rr] for rr, cc in path]
    return pts[::2] + ([pts[-1]] if len(pts) % 2 == 0 else []), how


def spot_problem(grid, free, door_zone, room, item: catalog.Item, c0, r0, w, d) -> str:
    """Why an item can't stand here, or "" if it can (before the path check)."""
    rows, cols = grid.shape
    if c0 < 0 or r0 < 0 or c0 + w > cols or r0 + d > rows:
        return "it doesn't fit there"
    block = (slice(r0, r0 + d), slice(c0, c0 + w))
    if not (grid[block] == room).all():
        return "it runs into a wall"
    if not free[block].all():
        return "something is already there"
    if door_zone[block].any():
        return "it blocks the doorway"
    if item.category in WALL_CATS:
        sides = [grid[r0 - 1, c0:c0 + w] if r0 > 0 else None, grid[r0 + d, c0:c0 + w] if r0 + d < rows else None,
                 grid[r0:r0 + d, c0 - 1] if c0 > 0 else None, grid[r0:r0 + d, c0 + w] if c0 + w < cols else None]
        if not any(s is not None and np.isin(s, (-1, -2, -4)).mean() > 0.6 for s in sides):
            return "there's no wall behind it"
    return ""


def first_tries(grid, free, door_zone, room, item: catalog.Item, cell_in: int, blocks_way) -> list[dict]:
    """The spots a person would try first, with the real reason each one fails. At most two."""
    w = max(1, int(np.ceil(item.w_in / cell_in)))
    d = max(1, int(np.ceil(item.d_in / cell_in)))
    in_room = grid == room
    ys, xs = np.nonzero(in_room)
    if not len(ys):
        return []
    tries = []
    # 1) the open middle of the room
    cy, cx = int(round(ys.mean())), int(round(xs.mean()))
    # 2) right inside the door, where things get put down first
    dz = np.nonzero(door_zone & in_room)
    cands = [("the middle of the room", cx - w // 2, cy - d // 2)]
    if len(dz[0]):
        j = int(np.argmin((dz[0] - cy) ** 2 + (dz[1] - cx) ** 2))
        cands.append(("right by the door", int(dz[1][j]) - w // 2, int(dz[0][j]) - d // 2))
    for label, c0, r0 in cands:
        why = spot_problem(grid, free, door_zone, room, item, c0, r0, w, d)
        if not why and blocks_way(c0, r0, w, d):
            why = "it cuts off the way through the room"
        if why and why not in ("it doesn't fit there", "it runs into a wall"):   # only reasons a person would give
            tries.append({"x": c0 + w / 2, "y": r0 + d / 2, "w": float(w), "d": float(d),
                          "where": label, "why": why})
    return tries[:2]


def smaller_options(pack: str, item: catalog.Item, room_name: str, max_price: float) -> list[catalog.Item]:
    """Real catalog items that do the same job but carry in narrower, biggest first."""
    need, _ = carry_width(item)
    out = []
    for c in catalog.load(pack):
        if c.id == item.id or c.category != item.category or not (set(c.uses) & set(item.uses)):
            continue
        if c.price_usd > max_price or not c.fits_room(room_name):
            continue
        if carry_width(c)[0] < need:
            out.append(c)
    return sorted(out, key=lambda c: -carry_width(c)[0])[:2]
