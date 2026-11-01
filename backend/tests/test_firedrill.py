import numpy as np

from app.space.firedrill import fire_drill


def _space(door_cells):
    grid = np.full((30, 40), -1, int)
    grid[2:28, 2:19] = 0          # bedroom
    grid[2:28, 21:38] = 1         # living room
    grid[14:14 + door_cells, 19:21] = 0   # doorway between them
    grid[28:30, 30:34] = -2
    return {"grid": grid.tolist(), "cell_in": 6, "pack": "home", "entrance": [32, 27], "items": [],
            "rooms": [{"id": 0, "name": "Bedroom", "kind": "room"}, {"id": 1, "name": "Living Room", "kind": "room"}]}


PEOPLE = [{"id": "a", "name": "Asha", "about": "72, uses a walker", "width_in": 25, "color": "#e55", "day": [], "home": "bedroom"},
          {"id": "k", "name": "Kabir", "about": "9", "width_in": 16, "color": "#55e", "day": [], "home": "bedroom"}]


def test_everyone_gets_out_through_a_wide_door():
    out = fire_drill(_space(6), PEOPLE, None)
    assert out["stuck"] == []
    a, k = (r["after"] for r in out["people"])
    assert a["out"] and k["out"] and a["seconds"] > k["seconds"]


def test_a_narrow_door_traps_the_walker():
    out = fire_drill(_space(3), PEOPLE, None)        # 18 in
    assert out["stuck"] == ["Asha"]
    assert out["people"][1]["after"]["out"]
