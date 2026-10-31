"""Furnishing: carried from the front door at real size, obvious spots tried first, smaller swap if stuck."""
import numpy as np

from app.space.redesign import redesign


def flat(door_cells):
    """Hallway (1) with the front door, living room (0) through a door of door_cells x 6 in."""
    g = np.full((30, 50), -2)
    g[0, :] = g[29, :] = g[:, 0] = g[:, 49] = -1
    g[:, 15] = -1
    g[1:29, 1:15] = 1
    g[1:29, 16:49] = 0
    g[12:12 + door_cells, 15] = 0
    return {"grid": g.tolist(), "cell_in": 6, "pack": "home", "entrance": [2, 14], "items": [],
            "rooms": [{"id": 0, "name": "Living Room", "kind": "open", "area_sqft": 230, "bbox_cells": [16, 1, 48, 28]},
                      {"id": 1, "name": "Hallway", "kind": "open", "area_sqft": 100, "bbox_cells": [1, 1, 14, 28]}]}


class Model:
    def __init__(self, changes):
        self.changes = changes

    def ask_json(self, *a, **k):
        return {"summary": "s", "thoughts": ["Skipped the TV: not what the goal is about"], "changes": self.changes}


def test_item_is_carried_in_from_the_front_door():
    d = redesign(flat(8), 2000, "", Model([{"action": "add", "room": 0, "item": "sofa-3", "reason": "seating"}]))
    ch = d.changes[0]
    assert not ch.dropped and ch.delivery and ch.carry == "carried tilted on its side"
    assert abs(ch.delivery[0][0] - 2) + abs(ch.delivery[0][1] - 14) <= 8      # starts at the front door
    assert d.thoughts == ["Skipped the TV: not what the goal is about"]


def test_sofa_too_big_for_the_door_is_swapped_for_a_smaller_real_item():
    d = redesign(flat(5), 2000, "", Model([{"action": "add", "room": 0, "item": "sofa-3", "reason": "seating"}]))
    ch = d.changes[0]
    assert not ch.dropped and ch.item != "sofa-3"
    assert "3-seat sofa" in ch.swapped_from and "clear width" in ch.swapped_from


def test_obvious_spots_are_tried_first_with_real_reasons():
    d = redesign(flat(8), 2000, "", Model([{"action": "add", "room": 0, "item": "bookshelf", "reason": "books"}]))
    ch = d.changes[0]
    assert not ch.dropped
    reasons = {t["where"]: t["why"] for t in ch.tries}
    assert reasons.get("the middle of the room") == "there's no wall behind it"


def test_rug_lies_in_the_open_middle_at_real_size():
    d = redesign(flat(8), 2000, "", Model([{"action": "add", "room": 0, "item": "rug", "reason": "cozy"}]))
    rug = d.changes[0].placed
    assert 26 <= rug["x"] <= 38 and 8 <= rug["y"] <= 22             # middle of the living room
    assert max(rug["w"], rug["d"]) >= 15                            # 8 ft = 16 cells (capped to fit)
