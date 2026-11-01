"""Apartment chooser: same people, same day, two plans; the plan where the walker can't reach the
kitchen loses, and the words only explain the pick code made."""
from app.space.compare import compare
from tests.test_simulate import CHILD, WALKER, two_rooms


def test_the_plan_the_walker_can_use_wins():
    narrow, wide = dict(two_rooms(3), id="aaaaaaaaaaaa"), dict(two_rooms(6), id="bbbbbbbbbbbb")
    asked = []

    class R:
        last_provider = "meta"

        def ask_json(self, prompt):
            asked.append(prompt)
            return {"why": "Plan 2 lets A reach the kitchen.", "plans": [{"plan": 1, "good": "same size", "bad": "door too narrow"},
                                                                        {"plan": 2, "good": "36 in door", "bad": ""}]}
    out = compare([narrow, wide], [WALKER, CHILD], R())
    assert out["pick"] == 2
    a, b = out["plans"]
    assert a["rank"] == 2 and b["rank"] == 1
    assert any("A can't reach the kitchen" in d for d in a["deal_breakers"])
    assert not b["deal_breakers"]
    assert "Code ranked plan 2 first" in asked[0]
    assert a["bad"] == "door too narrow" and out["why"]


def test_compare_works_without_a_model():
    out = compare([dict(two_rooms(6), id="a" * 12), dict(two_rooms(6), id="b" * 12)], [WALKER])
    assert out["pick"] in (1, 2) and out["why"] == ""


def test_a_redesign_is_compared_against_the_plan_as_it_is():
    s = dict(two_rooms(6), id="c" * 12)
    # a dresser across the doorway on the kitchen side blocks the walker as it is; the redesign removes it
    dresser = {"item": "dresser", "x": 22.5, "y": 12, "w": 3, "d": 10, "status": "kept"}
    s["items"] = [dresser]
    removed = [dict(dresser, status="removed")]
    out = compare([s, s], [WALKER], None, "", [(None, "as it is"), (removed, "redesign 1")])
    a, b = out["plans"]
    assert a["label"] == "as it is" and b["label"] == "redesign 1"
    assert out["pick"] == 2 and a["deal_breakers"] and not b["deal_breakers"]


def test_plan_list_skips_room_picture_files(tmp_path, monkeypatch):
    import json
    from app.api import spaces
    monkeypatch.setattr(spaces, "STORE", tmp_path)
    d = tmp_path / "abcdefabcdef"
    (d / "designs").mkdir(parents=True)
    (d / "map.json").write_text(json.dumps({"id": "abcdefabcdef", "rooms": []}))
    (d / "plan.img").write_bytes(b"x")
    (d / "designs" / "1.json").write_text(json.dumps({"summary": "s", "spent_usd": 10, "changes": []}))
    (d / "designs" / "1_room10.json").write_text("{}")
    out = spaces.list_spaces()
    assert len(out) == 1 and len(out[0]["designs"]) == 1
