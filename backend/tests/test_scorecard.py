"""Scorecard: numbers come from the map and items, and move the right way."""
import numpy as np

from app.space.scorecard import reachable, scorecard
from app.space.simulate import Floor


def flat(door_cells=6):
    """Bedroom (0) left, bathroom (1) right, door in the wall at col 20; entrance in the bedroom."""
    g = np.full((24, 41), -2)
    g[0, :] = g[23, :] = -1
    g[:, 0] = g[:, 40] = g[:, 20] = -1
    g[1:23, 1:20] = 0
    g[1:23, 21:40] = 1
    g[9:9 + door_cells, 20] = 0
    return {"grid": g.tolist(), "cell_in": 6, "pack": "home", "entrance": [2, 12],
            "rooms": [{"id": 0, "name": "Bedroom", "kind": "room"}, {"id": 1, "name": "Bathroom", "kind": "bath"}],
            "items": []}


def test_walker_reach_depends_on_the_door():
    assert reachable(Floor(flat(6), [], "home"), 25) == {0, 1}
    assert reachable(Floor(flat(3), [], "home"), 25) == {0}


def test_safety_items_raise_safety_and_flags_name_the_door():
    s = flat(3)
    after = [{"id": 1, "item": "grab-bar", "x": 30, "y": 5, "w": 1, "d": 1, "room": 1, "status": "new"},
             {"id": 2, "item": "night-light", "x": 5, "y": 5, "w": 1, "d": 1, "room": 0, "status": "new"},
             {"id": 3, "item": "smoke-alarm", "x": 8, "y": 8, "w": 1, "d": 1, "room": 0, "status": "new"}]
    sc = scorecard(s, after, None)
    assert sc["before"]["safety"]["score"] == 0
    assert sc["after"]["safety"]["score"] == 75          # all but "a walker can reach a bathroom"
    assert any("Bathroom: a walker can't get in" in f and "32 in door" in f for f in sc["after"]["flags"])
    assert sc["after"]["energy"]["kwh"] > sc["before"]["energy"]["kwh"]
    assert "Not medical" in sc["note"]
