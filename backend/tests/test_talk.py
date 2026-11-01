from app.space.render import restyle_prompt
from app.space.talk import person_facts, talk
from tests.test_firedrill import PEOPLE, _space


class Fake:
    last_provider = "fake"
    def __init__(self): self.prompt = ""
    def ask_json(self, prompt):
        self.prompt = prompt
        return {"reply": "I couldn't get through the door."}


def test_asha_knows_her_blocked_door():
    s = _space(3)
    PEOPLE[0]["day"] = [{"t": "02:00", "use": "wash", "note": "night bathroom trip"}]
    f = person_facts(s, None, PEOPLE, "a", [])
    assert any("25 in" in x for x in f) and any("fire drill" in x for x in f)


def test_talk_returns_reply_in_her_voice():
    r = Fake()
    out = talk(_space(6), "a", "How was your day?", [{"who": "you", "text": "hi"}], None, PEOPLE, [], r)
    assert out["reply"] and out["name"] == "Asha" and "You are Asha" in r.prompt


def test_restyle_only_adds_design_items():
    s = _space(6)
    d = {"goals": "safe for mom", "items": [
        {"room": 0, "item": "grab-bar", "name": "Grab bar", "status": "new"},
        {"room": 0, "item": "rug", "name": "Rug", "status": "removed"},
        {"room": 1, "item": "sofa-3", "name": "Sofa", "status": "new"}]}
    p = restyle_prompt(s, d, 0)
    assert "grab bar" in p.lower() and "take out: area rug" in p.lower() and "sofa" not in p.lower()
