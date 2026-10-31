"""Simulation: people walk real paths; a wider body (walker) needs more floor."""
import numpy as np

from app.space.simulate import Floor, live_a_day, simulate


def two_rooms(door_cells=6):
    """Bedroom (0) on the left, kitchen (1) on the right, joined by a door in the wall at col 20."""
    g = np.full((24, 41), -1)
    g[1:23, 1:20] = 0
    g[1:23, 21:40] = 1
    g[9:9 + door_cells, 20] = 0          # the doorway
    return {"grid": g.tolist(), "cell_in": 6, "pack": "home", "entrance": [39, 12],
            "rooms": [{"id": 0, "name": "Bedroom", "kind": "room"}, {"id": 1, "name": "Kitchen", "kind": "open"}],
            "items": []}


WALKER = {"id": "p", "name": "A", "about": "", "width_in": 25, "color": "#000", "home": "bedroom",
          "day": [{"t": "07:00", "use": "cook", "note": "tea"}, {"t": "08:00", "use": "sleep", "note": "rest"}]}
CHILD = dict(WALKER, id="c", width_in=16)


def test_walks_through_a_wide_door():
    day = live_a_day(Floor(two_rooms(6), [], "home"), WALKER)       # 36 in door
    assert day.blocked == 0 and day.walked_ft > 5
    assert day.legs[0].room == "Kitchen" and day.legs[0].path


def test_narrow_door_blocks_the_walker_but_not_the_child():
    s = two_rooms(3)                                                 # 18 in door
    day = live_a_day(Floor(s, [], "home"), WALKER)
    assert day.legs[0].blocked and "25 in wide" in day.legs[0].why
    assert live_a_day(Floor(s, [], "home"), CHILD).blocked == 0


def test_furniture_in_the_way_is_measured_before_and_after(monkeypatch):
    from app.space import simulate as sim
    monkeypatch.setattr(sim, "load_personas", lambda pack: (WALKER, CHILD))
    s = two_rooms(6)
    # a dresser parked in front of the door on the kitchen side leaves no room for a walker
    after = [{"id": 0, "item": "dresser", "name": "Dresser", "x": 22.5, "y": 12, "w": 3, "d": 12, "room": 1,
              "status": "new"}]
    out = simulate(s, after)
    assert out["before"]["p"]["blocked"] == 0 and out["after"]["p"]["blocked"] > 0
    assert "8 in wide" not in out["after"]["p"]["legs"][0]["why"]


def test_voices_use_the_numbers(monkeypatch):
    from app.space import simulate as sim
    monkeypatch.setattr(sim, "load_personas", lambda pack: (WALKER,))

    class M:
        last_provider = "meta"
        prompt = ""

        def ask_json(self, prompt, *a, **k):
            M.prompt = prompt
            return {"voices": {"p": {"before": "Easy morning.", "after": "Still easy."}}}

    out = simulate(two_rooms(6), None, M())
    assert out["voices"]["p"]["after"] == "Still easy." and out["voice_provider"] == "meta"
    assert "walked" in M.prompt and "No medical advice" in M.prompt
