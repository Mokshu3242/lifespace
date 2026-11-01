"""Street check: boxes and scene words become scores; fixes raise them; poles that are lights don't count twice."""
from app.space import street


def _read(**scene):
    sc = street._clean_scene({"surface": "cobblestone", "rail_tracks": True, "trees": 3, "shade": "some",
                              "sidewalk_width": "ok", **scene})
    box = lambda x: [x, 100, x + 10, 300]
    things = ([{"kind": "light", "box": box(x)} for x in (10, 60, 110)]
              + [{"kind": "pole", "box": box(12)},                       # the same as the first light
                 {"kind": "pole", "box": [400, 250, 405, 380]}]          # a sign pole on the sidewalk
              + [{"kind": "bin", "box": box(500)}, {"kind": "sidewalk", "box": [300, 200, 700, 400]}])
    return {"things": street._merge_lights_and_poles(things), "scene": sc}


def test_light_poles_count_once_and_poles_in_path_are_found():
    read = _read()
    c = street.counts_of(read)
    assert c["light"] == 3 and c.get("pole", 0) == 1 and c["pole_in_path"] == 1
    assert c["tree"] == 3                   # trees come from the scene reading when SAM sees none


def test_scorecard_flags_cobblestone_tracks_and_no_curb_ramp():
    s = street.scorecard(_read())
    text = " ".join(s["flags"])
    assert "Cobblestone" in text and "Rail tracks" in text and "No curb ramp" in text and "Nowhere to sit" in text
    assert s["walk"]["score"] < 60


def test_redesign_fixes_raise_scores_and_respect_budget():
    class R:
        def ask_json(self, prompt):
            assert "Cobblestone" in prompt
            return {"summary": "smoother and restful",
                    "changes": [{"item": "smooth-strip", "where": "middle"}, {"item": "track-filler", "where": "tracks"},
                                {"item": "bench", "where": "left"}, {"item": "bench", "where": "right"},
                                {"item": "curb-ramp", "where": "corner"}, {"item": "street-light", "where": "x"},
                                {"item": "spaceship", "where": "x"}]}
    d = street.redesign(_read(), 15000, "safer for my dad", R())
    names = [c["item"] for c in d["changes"]]
    assert names[:4] == ["smooth-strip", "track-filler", "bench", "bench"]
    assert d["spent_usd"] <= 15000
    assert any(x["why"] == "not in the street catalog" for x in d["dropped"])
    assert any("over budget" in x["why"] for x in d["dropped"])          # the street light didn't fit
    assert d["after"]["walk"]["score"] > d["before"]["walk"]["score"]
    assert d["after"]["rest"]["score"] > d["before"]["rest"]["score"]
    assert d["after"]["overall"] > d["before"]["overall"]
