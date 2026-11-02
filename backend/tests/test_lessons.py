import numpy as np

from app.space import lessons
from app.space.plandoctor import check
from tests.test_firedrill import _space


def test_learned_rename_is_suggested(tmp_path, monkeypatch):
    monkeypatch.setattr(lessons, "FILE", tmp_path / "lessons.jsonl")
    assert lessons.record("home", "rename", "Wic", "WC", "printed WC on the plan")
    assert lessons.record("home", "rename", "wic", "WC")
    assert not lessons.record("home", "rename", "WC", "wc")          # no-op
    assert lessons.renames("home") == {"wic": ("WC", 2)}
    s = _space(6)
    s["rooms"][1]["name"] = "Wic"
    learned = [i for i in check(s) if i["kind"] == "learned"]
    assert learned and learned[0]["fix"] == {"action": "rename", "room": 1, "name": "WC", "why": "learned from 2 past fixes"}
    assert "renamed" in lessons.examples("home")[0]
    assert lessons.stats("home")["count"] == 2 and lessons.stats("office")["count"] == 0
