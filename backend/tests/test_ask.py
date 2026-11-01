import json
from pathlib import Path

from app.space.ask import ask, gather_facts
from tests.test_firedrill import PEOPLE, _space


class Fake:
    last_provider = "fake"
    def ask_json(self, prompt):
        assert "Fire drill" in prompt and "Doorway" not in prompt.split("Question:")[1]
        return {"answer": "No, the bedroom door is too narrow.", "facts": [1, 99, "x"], "verdict": "no"}


def test_facts_include_rooms_people_and_drill():
    f = gather_facts(_space(3), None, PEOPLE)
    text = "\n".join(f)
    assert "Room: Bedroom" in text and "Asha" in text and "can't get out alone" in text


def test_answer_keeps_only_real_fact_numbers():
    out = ask(_space(3), "Can Asha live here?", None, PEOPLE, Fake())
    assert out["verdict"] == "no" and out["facts"] == ["Room: Bedroom (room), about 112 sq ft"]
