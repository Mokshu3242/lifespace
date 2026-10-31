"""The loop gives the model real results and stops when the target is met."""
import numpy as np

from app.space.improve import improve


def home():
    g = np.full((24, 41), -2)
    g[0, :] = g[23, :] = g[:, 0] = g[:, 40] = g[:, 20] = -1
    g[1:23, 1:20] = 0
    g[1:23, 21:40] = 1
    g[9:15, 20] = 0
    return {"grid": g.tolist(), "cell_in": 6, "pack": "home", "entrance": [2, 12], "items": [],
            "rooms": [{"id": 0, "name": "Bedroom", "kind": "room", "area_sqft": 100, "bbox_cells": [1, 1, 19, 22]},
                      {"id": 1, "name": "Bathroom", "kind": "bath", "area_sqft": 100, "bbox_cells": [21, 1, 39, 22]}]}


class Model:
    """Round 1 adds a grab bar only; round 2 (after seeing what's missing) adds the rest."""
    def __init__(self):
        self.prompts = []

    def ask_json(self, prompt, *a, **k):
        self.prompts.append(prompt)
        if len(self.prompts) == 1:
            return {"summary": "r1", "changes": [{"action": "add", "room": 1, "item": "grab-bar", "reason": "steady"}]}
        return {"summary": "r2", "changes": [
            {"action": "add", "room": 0, "item": "smoke-alarm", "reason": "alarm by the bed"},
            {"action": "add", "room": 0, "item": "night-light", "reason": "night path"}]}


def test_second_round_sees_the_results_and_meets_the_target():
    m = Model()
    rounds = list(improve(home(), 500, "safe", m, {"safety": 80}, rounds=3))
    assert len(rounds) == 2                                  # stopped once the target was met
    assert rounds[0][2]["safety"]["score"] < 80 <= rounds[1][2]["safety"]["score"]
    second = m.prompts[1]
    assert "Round 1 results" in second and "Still missing" in second and "smoke alarm" in second
    assert "Bathroom grab bar" in second                      # told what's already there
    names = {it["item"] for it in rounds[1][1].items if it.get("status") in ("kept", "new")}
    assert {"grab-bar", "smoke-alarm", "night-light"} <= names


def test_stops_when_only_a_wider_door_would_help():
    s = home()
    g = np.array(s["grid"]); g[9:15, 20] = -1; g[11:13, 20] = 0; s["grid"] = g.tolist()   # 12 in door: walker can't pass
    m = Model()
    rounds = list(improve(s, 500, "safe", m, {"safety": 80}, rounds=3))
    assert len(rounds) == 2 and len(m.prompts) == 2          # no third, pointless round
    assert "can reach a bathroom" in rounds[-1][2]["safety"]["why"]


def test_smoke_alarms_never_go_in_bathrooms():
    from app import catalog
    alarm = catalog.get("home", "smoke-alarm")
    assert alarm.fits_room("Second Bedroom") and alarm.fits_room("Hallway")
    assert not alarm.fits_room("Bathroom") and not alarm.fits_room("Kitchen")
