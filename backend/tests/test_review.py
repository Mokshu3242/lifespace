import numpy as np

from app.space import lessons
from app.space.plandoctor import apply
from app.space.redesign import PROMPT, learned_block


def _space():
    g = np.full((12, 22), -1)
    g[1:11, 1:21] = 0
    return {"cell_in": 6, "grid": g.tolist(), "doors": [], "items": [], "pack": "home",
            "rooms": [{"id": 0, "name": "Living room", "kind": "room", "center_cells": [5, 5]}]}


def test_malformed_fixes_are_refused_not_crashed():
    s = _space()
    s["rooms"].append({"id": 5, "name": "Ghost"})          # a room with no cells
    _, log = apply(s, [{"action": "add_item", "room": 0, "item": "armchair", "at": [50]},
                       {"action": "add_item", "room": 0, "item": "armchair", "at": "5"},
                       {"action": "set_entrance", "room": 5},
                       {"action": "split", "room": 0, "from": [50], "to": [50, 100], "name": "H"}])
    assert [x["ok"] for x in log] == [False] * 4


def test_replaying_the_same_fixes_gives_the_same_map():
    fixes = [{"action": "split", "room": 0, "from": [70, 0], "to": [70, 100], "name": "A"},
             {"action": "split", "room": 1, "from": [0, 50], "to": [100, 50], "name": "C"},
             {"action": "add_item", "room": 0, "item": "armchair", "at": [10, 50]}]
    a, la = apply(_space(), fixes)
    b, _ = apply(_space(), fixes)
    assert [x["ok"] for x in la] == [True, False, True] and a == b   # 2nd: halves under 8 sq ft
    assert sorted(r["id"] for r in a["rooms"]) == [0, 1]


def test_damaged_outcomes_file_does_not_break_redesign(tmp_path, monkeypatch):
    monkeypatch.setattr(lessons, "OUTCOMES", tmp_path / "o.jsonl")
    assert learned_block("home") == ""
    (tmp_path / "o.jsonl").write_text('garbage\nnull\n5\n{"key": "x"}\n[1]\n')
    assert learned_block("home") == "" and lessons.outcome_stats("home")["designs"] == 0
    assert lessons.record_outcome({"rooms": []}, "s", 1, {"changes": [{"item": "gone-id", "action": "add"},
                                                                      {"item": "x", "dropped": "no"}]},
                                  {"before": {"safety": {"score": 1}}, "after": {"safety": {}}})
    full = learned_block("home")
    assert "gone-id" in full
    for L in ("", full + "{braces}"):
        PROMPT.format(context="", budget=1, goals="", basics="", style_rule="", rooms="", items="",
                      catalog="", learned=L)
