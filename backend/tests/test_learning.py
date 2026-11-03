from app.space import lessons
from app.space.redesign import learned_block
from app.space.scorecard import _sleep_rooms


def _space():
    return {"pack": "home", "rooms": [{"id": 0, "name": "Bedroom 2", "kind": "room"},
                                      {"id": 1, "name": "Bathroom", "kind": "bath"}]}


def _design(dropped=""):
    return {"goals": "safe for a walker", "changes": [
        {"action": "add", "room": 1, "item": "grab-bar", "dropped": ""},
        {"action": "add", "room": 0, "item": "night-light", "dropped": ""},
        {"action": "add", "room": 0, "item": "bed-queen", "dropped": dropped or "won't fit through the 27 in door"}]}


def _scores(before, after):
    return {"before": {"safety": {"score": before}, "access": {"score": 90}},
            "after": {"safety": {"score": after}, "access": {"score": 90}}}


def test_a_measured_redesign_teaches_the_next_one(tmp_path, monkeypatch):
    monkeypatch.setattr(lessons, "OUTCOMES", tmp_path / "outcomes.jsonl")
    assert lessons.record_outcome(_space(), "abc", 1, _design(), _scores(25, 100))
    block = learned_block("home")
    assert "grab-bar" in block and "safety +75" in block
    assert "bed-queen in a bedroom: won't fit through the 27 in door" in block


def test_running_the_same_day_again_does_not_count_twice(tmp_path, monkeypatch):
    monkeypatch.setattr(lessons, "OUTCOMES", tmp_path / "outcomes.jsonl")
    for _ in range(3):
        lessons.record_outcome(_space(), "abc", 1, _design(), _scores(25, 100))
    assert lessons.outcome_stats("home")["designs"] == 1
    assert "in 1 measured redesign;" in "\n".join(lessons.what_worked("home"))


def test_nothing_learned_without_measured_days(tmp_path, monkeypatch):
    monkeypatch.setattr(lessons, "OUTCOMES", tmp_path / "outcomes.jsonl")
    assert learned_block("home") == ""
    assert not lessons.record_outcome(_space(), "abc", 2, {"changes": []}, _scores(25, 25))


def test_studio_main_room_counts_as_where_people_sleep():
    rooms = [{"id": 0, "name": "Main Room", "kind": "open", "cells": 900}, {"id": 1, "name": "Bathroom", "kind": "bath"},
             {"id": 2, "name": "Kitchenette", "kind": "open", "cells": 200}]
    assert [r["name"] for r in _sleep_rooms(rooms)] == ["Main Room"]
    assert [r["name"] for r in _sleep_rooms(rooms + [{"id": 3, "name": "Bed 1", "kind": "room"}])] == ["Bed 1"]
