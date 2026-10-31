from app.space.render import room_prompt


def test_prompt_uses_only_real_items_and_the_goal():
    space = {"pack": "home", "cell_in": 6,
             "rooms": [{"id": 0, "name": "Bedroom", "kind": "room", "bbox_cells": [0, 0, 23, 29]}]}
    design = {"goals": "calm and safe for my parents", "items": [
        {"room": 0, "item": "bed-queen", "status": "kept"},
        {"room": 0, "item": "night-light", "status": "new"},
        {"room": 0, "item": "armchair", "status": "removed"},
        {"room": 1, "item": "sofa-3", "status": "kept"}]}
    p = room_prompt(space, design, 0)
    assert "queen bed" in p and "motion night light" in p and "Newly added: motion night light" in p
    assert "armchair" not in p and "sofa" not in p
    assert "15 by 12 feet" in p and "calm and safe for my parents" in p and "No people" in p
