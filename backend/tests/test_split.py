import numpy as np

from app.space.plandoctor import apply, grid_overlay


def _space():
    g = np.full((12, 22), -1)
    g[1:11, 1:21] = 0                      # one open area: really Dining (left) and Hallway (right)
    return {"cell_in": 6, "grid": g.tolist(), "doors": [], "items": [],
            "rooms": [{"id": 0, "name": "Dining", "kind": "open", "center_cells": [5, 5], "bbox_cells": [1, 1, 20, 10]}]}


def test_split_cuts_room_in_two_and_keeps_the_name_on_its_side():
    # a slightly crooked line near x = 50%: snapped upright, stretched to the walls
    new, log = apply(_space(), [{"action": "split", "room": 0, "from": [50, 20], "to": [52, 75], "name": "Hallway"}])
    assert log[0]["ok"], log
    names = {r["name"]: r for r in new["rooms"]}
    assert set(names) == {"Dining", "Hallway"}
    g = np.array(new["grid"])
    assert (g == -1).sum() == (np.array(_space()["grid"]) == -1).sum()     # no wall added: walking unchanged
    assert names["Dining"]["center_cells"][0] < names["Hallway"]["center_cells"][0]
    assert names["Hallway"]["area_sqft"] > 8


def test_split_refuses_a_line_that_cuts_nothing():
    new, log = apply(_space(), [{"action": "split", "room": 0, "from": [99, 2], "to": [99, 3], "name": "X"}])
    assert not log[0]["ok"]
    assert len(new["rooms"]) == 1


def test_grid_overlay_returns_a_picture():
    import cv2
    ok, png = cv2.imencode(".png", np.full((200, 300, 3), 255, np.uint8))
    out = grid_overlay(png.tobytes())
    assert out[:4] == b"\x89PNG"
