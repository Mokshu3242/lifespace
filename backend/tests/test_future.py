"""In 5 years: a walker becomes a wheelchair, and a door that worked today stops working."""
from app.space.future import age_person, future
from tests.test_simulate import CHILD, WALKER, two_rooms


def test_people_age_with_plain_rules():
    q, why = age_person(dict(WALKER, about="72, uses a walker", mobility="walker", age=72), 5)
    assert q["mobility"] == "wheelchair" and q["width_in"] == 30 and "wheelchair" in why and q["about"].startswith("77")
    kid, why = age_person(dict(CHILD, about="9, plays", mobility="none", age=9), 5)
    assert kid["width_in"] == 22 and why == "grown to adult size"
    same, why = age_person(dict(WALKER, about="40, works", mobility="none", age=40, width_in=22), 5)
    assert why == "" and same["width_in"] == 22


def test_a_door_that_works_today_fails_in_five_years():
    s = two_rooms(4)                                          # a 24 in doorway: a walker squeezes by, a wheelchair can't
    asha = dict(WALKER, about="72, uses a walker", mobility="walker", age=72)
    out = future(s, [asha], None, 5)
    p = out["people"][0]
    assert p["now"]["blocked"] == 0 and p["then"]["blocked"] > 0
    assert out["breaks"] and out["breaks"][0]["person"] == "A"
    assert out["scores"]["then"]["access"]["score"] <= out["scores"]["now"]["access"]["score"]
