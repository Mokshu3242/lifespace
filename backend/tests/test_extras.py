from app.space.extras import add_visitor, comic_prompt, time_saved
from app.space.simulate import simulate
from tests.test_firedrill import PEOPLE, _space


def test_add_dog_and_caregiver():
    rooms = _space(6)["rooms"]
    fam = add_visitor(None, PEOPLE, "dog", rooms)
    fam = add_visitor(fam, PEOPLE, "caregiver", rooms)
    ids = [p["id"] for p in fam["people"]]
    assert "dog" in ids and "caregiver" in ids and len(fam["people"]) == 4
    assert "helps Asha" in fam["people"][-1]["about"]


def test_time_saved_counts_unlocked_trips():
    sim = {"before": {"a": {"walked_ft": 100, "tight_ft": 20, "blocked": 2}},
           "after": {"a": {"walked_ft": 80, "tight_ft": 0, "blocked": 0}}}
    t = time_saved(sim, [{"id": "a", "name": "Asha", "about": "72, uses a walker"}])[0]
    assert t["trips_unlocked"] == 2 and t["minutes"] > 6


def test_comic_prompt_uses_the_measured_day():
    PEOPLE[0]["day"] = [{"t": "02:00", "use": "wash", "note": "night bathroom trip"}]
    s = _space(3)
    sim = simulate(s, None, None, "", [], PEOPLE)
    p = comic_prompt(PEOPLE[0], sim["before"]["a"], sim["after"]["a"], [{"name": "Grab bar"}], "apartment")
    assert "BEFORE" in p and "AFTER" in p and "Asha" in p


def test_comic_stays_honest_when_still_blocked():
    PEOPLE[0]["day"] = [{"t": "02:00", "use": "wash", "note": "night bathroom trip"}]
    s = _space(3)
    sim = simulate(s, None, None, "", [], PEOPLE)
    p = comic_prompt(PEOPLE[0], sim["before"]["a"], sim["after"]["a"], [{"name": "Grab bar"}], "apartment")
    assert "still stopped" in p
