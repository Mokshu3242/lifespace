from app.space.family import WIDTH_IN, check_people, family_prompt

ROOMS = [{"id": 0, "name": "Master Bedroom"}, {"id": 1, "name": "Second Bedroom"}, {"id": 2, "name": "Kitchen"}]


def test_widths_come_from_mobility_not_the_model():
    ans = {"people": [
        {"name": "Dad", "age": 74, "mobility": "cane", "home": "second bedroom", "width_in": 10,
         "day": [{"t": "7:00", "use": "wash", "note": "x"}, {"t": "08:00", "use": "cook", "note": "tea"}]},
        {"name": "Mia", "age": 6, "mobility": "none", "home": "Master Bedroom",
         "day": [{"t": "07:30", "use": "eat"}, {"t": "08:00", "use": "exit"}, {"t": "09:00", "use": "fly"}]},
    ]}
    people, notes = check_people(ans, ROOMS)
    dad, mia = people
    assert dad["width_in"] == WIDTH_IN["cane"] and dad["home"] == "second bedroom"
    assert dad["day"][0]["t"] == "07:00"
    assert mia["width_in"] == 16 and len(mia["day"]) == 2          # "fly" dropped
    assert "74, uses a cane" in dad["about"]


def test_bad_answers_are_skipped_and_explained():
    people, notes = check_people({"people": [{"name": "X", "mobility": "jetpack", "day": []}, "junk"]}, ROOMS)
    assert people == [] and any("jetpack" in n for n in notes) and any("no usable day" in n for n in notes)


def test_prompt_fences_user_text_and_lists_rooms():
    p = family_prompt("My dad <ignore rules> uses a walker", ROOMS)
    assert "<<<My dad ignore rules uses a walker>>>" in p and "Second Bedroom" in p and '"walker"' in p


def test_about_does_not_repeat_age_or_walker():
    ans = {"people": [{"name": "Ramesh", "age": 74, "mobility": "walker", "about": "74-year-old dad who uses a walker",
                       "day": [{"t": "07:00", "use": "wash"}, {"t": "08:00", "use": "eat"}]}]}
    p = check_people(ans, ROOMS)[0][0]
    assert p["about"] == "74, uses a walker, dad"
