"""Floor plan reader tests on a plan we draw ourselves (no outside images, no network)."""
import cv2
import numpy as np

from app.space.reader import (FIXTURE, OUTSIDE, WALL, Label, build_space_map,
                              labels_from_ai, parse_dims)

PX_PER_FT = 20


def draw_plan() -> np.ndarray:
    """Two rooms side by side: Bedroom 12x10 ft and Office 8x10 ft, a 3 ft door between them,
    a 3 ft front door on the left wall, and a closed 2x2 ft cabinet in the office."""
    f = PX_PER_FT
    img = np.full((14 * f, 26 * f), 255, np.uint8)
    t = 8  # wall thickness px
    x0, y0 = 2 * f, 2 * f
    x1, x2, y1 = x0 + 12 * f, x0 + 20 * f, y0 + 10 * f
    cv2.rectangle(img, (x0 - t, y0 - t), (x2 + t, y1 + t), 0, -1)
    cv2.rectangle(img, (x0, y0), (x2, y1), 255, -1)
    cv2.rectangle(img, (x1, y0), (x1 + t, y1), 0, -1)                 # dividing wall
    cv2.rectangle(img, (x1, y0 + 4 * f), (x1 + t, y0 + 7 * f), 255, -1)  # door gap
    cv2.rectangle(img, (x0 - t, y0 + 3 * f), (x0, y0 + 6 * f), 255, -1)  # front door
    cv2.rectangle(img, (x2 - 3 * f, y0 + f), (x2 - f, y0 + 3 * f), 0, 3)  # cabinet outline
    cv2.putText(img, "BEDROOM", (x0 + 40, y0 + 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, 0, 2)
    return img


LABELS = [Label("Bedroom", "12'0\" x 10'0\"", 2 * PX_PER_FT + 120, 2 * PX_PER_FT + 160),
          Label("Office", "8'0\" x 10'0\"", 2 * PX_PER_FT + 300, 2 * PX_PER_FT + 160)]


def test_parse_dims():
    assert parse_dims("14'6\" x 20'5\"") == (14.5, 20 + 5 / 12)
    assert parse_dims("21’6” x 8’0”") == (21.5, 8.0)
    assert parse_dims("6'0\" x 6'34\"") == (6.0, 6.25)   # typo on real plans
    assert parse_dims("") is None
    assert parse_dims("big room") is None


def test_scale_and_rooms():
    m = build_space_map(draw_plan(), LABELS, None)
    assert abs(m.px_per_ft - PX_PER_FT) / PX_PER_FT < 0.12
    areas = {r.name: r.area_sqft for r in m.rooms}
    assert abs(areas["Bedroom"] - 120) / 120 < 0.2
    assert abs(areas["Office"] - 80) / 80 < 0.25


def test_walls_outside_and_fixtures():
    m = build_space_map(draw_plan(), LABELS, None)
    g = np.array(m.grid)
    assert g[0, 0] == OUTSIDE
    assert (g == WALL).sum() > 0
    assert (g == FIXTURE).sum() > 0          # the closed cabinet
    assert m.warnings == []


def test_rooms_connected_through_door():
    """Bedroom and Office cells must touch somewhere (the door), or nobody can walk between them."""
    m = build_space_map(draw_plan(), LABELS, None)
    g = np.array(m.grid)
    b, o = [r.id for r in m.rooms]
    touch = ((g[:, :-1] == b) & (g[:, 1:] == o)).any()
    assert touch


def test_labels_from_ai_handles_normalized_coords():
    ai = {"rooms": [{"name": "Kitchen", "dims": "", "x": 900, "y": 500},
                    {"name": "Kitchen", "dims": "", "x": 900, "y": 500}],   # duplicate
          "entrance": {"x": 100, "y": 900}}
    labels, ent = labels_from_ai(ai, w=500, h=300)
    assert len(labels) == 1
    assert labels[0].x == 450 and labels[0].y == 150
    assert ent == (50, 270)
