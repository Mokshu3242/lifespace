import numpy as np

from app.space.plandoctor import apply, check
from tests.test_firedrill import _space


def _with_door(cells):
    s = _space(cells)
    s["doors"] = [{"x": 20.0, "y": 14 + cells / 2, "axis": "y", "width_in": cells * 6, "rooms": [0, 1], "outside": False}]
    return s


def test_narrow_door_found_and_widened():
    s = _with_door(3)
    issues = check(s)
    nd = [i for i in issues if i["kind"] == "narrow_door"]
    assert nd and nd[0]["fix"]["action"] == "widen_door"
    new, log = apply(s, [nd[0]["fix"]])
    assert log[0]["ok"]
    g = np.array(new["grid"])
    assert (g[12:20, 19:21] >= 0).sum() > 6           # the wall is open wider now
    assert new["doors"][0]["width_in"] == 32


def test_merge_and_rename_and_bad_fix():
    s = _with_door(6)
    s["rooms"].append({"id": 2, "name": "Space 3", "kind": "room"})
    g = np.array(s["grid"]); g[2:4, 2:4] = 2; s["grid"] = g.tolist()
    new, log = apply(s, [{"action": "merge", "room": 2, "into": 0}, {"action": "rename", "room": 1, "name": "Living Room"},
                         {"action": "rename", "room": 99, "name": "x"}, {"action": "explode"}])
    assert [x["ok"] for x in log] == [True, True, False, False]
    assert all(r["id"] != 2 for r in new["rooms"]) and any(r["name"] == "Living Room" for r in new["rooms"])
