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


def _bedroom():
    g = np.full((30, 40), -1)
    g[1:29, 1:39] = 0
    return {"cell_in": 6, "pack": "home", "grid": g.tolist(), "doors": [], "items": [], "entrance": [2, 15],
            "rooms": [{"id": 0, "name": "Bedroom 2", "kind": "room", "center_cells": [20, 15]}]}


def test_add_item_places_a_catalog_bed_near_where_it_is_drawn():
    new, log = apply(_bedroom(), [{"action": "add_item", "room": 0, "item": "bed-queen", "at": [80, 50]}])
    assert log[0]["ok"], log
    bed = new["items"][0]
    assert bed["item"] == "bed-queen" and bed["source"] == "ai fix"
    assert bed["x"] > 20                                   # on the right half, where it was drawn


def test_add_item_refuses_unknown_items_and_wrong_rooms():
    _, log = apply(_bedroom(), [{"action": "add_item", "room": 0, "item": "spaceship", "at": [50, 50]},
                                {"action": "add_item", "room": 0, "item": "range", "at": [50, 50]}])
    assert not log[0]["ok"] and not log[1]["ok"]


def test_split_moves_furniture_in_the_new_piece_to_the_new_room():
    sp = _space()
    sp["items"] = [{"id": 0, "item": "smoke-alarm", "x": 17, "y": 5, "w": 1, "d": 1, "room": 0},
                   {"id": 1, "item": "smoke-alarm", "x": 3, "y": 5, "w": 1, "d": 1, "room": 0}]
    new, log = apply(sp, [{"action": "split", "room": 0, "from": [50, 10], "to": [50, 90], "name": "Hallway"}])
    hall = next(r["id"] for r in new["rooms"] if r["name"] == "Hallway")
    assert [it["room"] for it in new["items"]] == [hall, 0]
