"""Item detection: shapes -> catalog shortlist -> model vote."""
import cv2
import numpy as np

from app.space import items
from app.space.reader import Room

PPF = 10.0   # px per ft


def plan_with_bed():
    """A 30 x 20 ft room with a queen bed (5.3 x 7 ft) drawn as a closed outline."""
    img = np.full((260, 360), 255, np.uint8)
    cv2.rectangle(img, (20, 20), (320, 220), 0, 6)
    cv2.rectangle(img, (60, 60), (60 + 53, 60 + 70), 0, 2)
    return img


def room_grid():
    g = np.full((52, 72), -2, int)
    g[5:43, 5:63] = 0
    return g.tolist(), [Room(id=0, name="Bedroom", dims_text="", dims_ft=None, area_sqft=600, cells=1,
                             bbox_cells=(0, 0, 1, 1), center_cells=(1, 1), kind="room")]


class Voters:
    def __init__(self, picks):
        self.picks = picks
        self.prompts = []

    def see_each(self, prompt, png, *a, **k):
        self.prompts.append(prompt)
        return {m: {"tiles": [{"id": 1, "pick": p, "reason": "r"}]} for m, p in self.picks.items()}


def test_finds_bed_and_majority_wins():
    grid, rooms = room_grid()
    r = Voters({"a": "bed-queen", "b": "bed-queen", "c": "bed-full"})
    out = items.detect_items(plan_with_bed(), grid, rooms, PPF, 6, "home", r)
    assert len(out) == 1
    bed = out[0]
    assert bed.item == "bed-queen" and bed.source == "most models" and not bed.unsure
    assert bed.room == 0 and abs(bed.w - 10.6) < 1.5           # 5.3 ft = about 10.6 cells
    assert "in Bedroom" in r.prompts[0] and "bed-queen = Queen bed" in r.prompts[0]


def test_none_majority_drops_shape_and_no_answers_fall_back():
    grid, rooms = room_grid()
    assert items.detect_items(plan_with_bed(), grid, rooms, PPF, 6, "home",
                              Voters({"a": "none", "b": "none", "c": "bed-queen"})) == []
    out = items.detect_items(plan_with_bed(), grid, rooms, PPF, 6, "home", Voters({}))
    assert out[0].source == "best size match" and out[0].unsure


def test_table_with_chairs_is_a_set():
    shape = items.Shape(0, 0, 10, 10, w_in=80, d_in=66, room=0)
    opts = items.candidates("home", shape, "Dining Area")
    first, chairs = opts[0]
    assert first.id == "dining-4" and chairs == 4


def test_door_swing_is_dropped_but_bed_stays():
    img = plan_with_bed()
    # a 3 ft door at the room's left wall: leaf along the wall, arc out to the side
    cv2.line(img, (24, 150), (54, 150), 0, 2)                      # door leaf, sticking into the room
    cv2.ellipse(img, (24, 150), (30, 30), 0, 0, 90, 0, 2)          # quarter-circle swing
    grid, rooms = room_grid()
    shapes = items.find_shapes(img, PPF, np.array(grid), PPF / 2)
    assert len(shapes) == 1 and shapes[0].w_in > 50                 # only the bed


def test_prompt_carries_symbol_hints():
    grid, rooms = room_grid()
    r = Voters({"a": "bed-queen"})
    items.detect_items(plan_with_bed(), grid, rooms, PPF, 6, "home", r)
    assert "quarter-circle arc (door swing)" in r.prompts[0]
