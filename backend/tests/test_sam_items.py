"""SAM 3.1 boxes become real catalog items; drawn blocks under them become floor."""
import numpy as np

from app.space import sam_items


def test_words_map_to_catalog_items_by_size_and_room():
    f = sam_items._catalog_id
    assert f("chair", "office", 25, 25, "Meeting Room") == "meet-chair"
    assert f("chair", "office", 25, 25, "Open Work Area") == "task-chair"
    assert f("table", "office", 96, 42, "Meeting Room") == "meet-8"
    assert f("sofa", "office", 80, 34, "Reception") == "lounge-sofa"
    assert f("desk", "office", 60, 36, "Meeting Room") == "meet-4"
    assert f("desk", "office", 60, 30, "Private Office") == "desk-office"
    assert f("bed", "home", 64, 84, "Bedroom") == "bed-queen"
    assert f("dining table", "home", 42, 22, "Living Room") == "coffee-table"


def test_merge_adds_missed_items_and_frees_blocks():
    grid = np.zeros((20, 20), int)
    grid[5:10, 5:10] = -4                      # a table drawn as a filled block
    shape = [{"item": "task-chair", "x": 15, "y": 15, "w": 4, "d": 4, "room": 0}]
    sam = [{"item": "meet-4", "x": 7.5, "y": 7.5, "w": 5, "d": 5, "room": 0},
           {"item": "task-chair", "x": 15.5, "y": 15, "w": 4, "d": 4, "room": 0}]   # already found
    out = sam_items.merge(shape, sam, grid)
    assert [i["item"] for i in out] == ["task-chair", "meet-4"]
    assert (grid[5:10, 5:10] == 0).all()      # the block is floor now; the table item blocks people


def test_no_sam_outside_prod(monkeypatch):
    class S:
        mode, meta_api_key = "local", ""
    monkeypatch.setattr(sam_items, "get_settings", lambda: S())
    assert sam_items.sam_items(np.zeros((10, 10), np.uint8), np.zeros((10, 10), int), [], 10, 6, "office", None) == []


def test_doors_from_boxes_measure_width_and_rooms():
    grid = np.full((40, 40), -1, int)
    grid[:, :18] = 1
    grid[:, 22:] = 2
    px_per_ft = 12.0                     # 1 px = 1 in, cell 6 in = 6 px
    boxes = [(100, 60, 132, 92, 0.9),    # 32 in door between rooms 1 and 2
             (101, 61, 133, 93, 0.6),    # same door again
             (10, 10, 70, 70, 0.9),      # 60 in: not a door
             (200, 30, 212, 42, 0.9)]    # 12 in: not a door
    doors = sam_items.doors_from_boxes(boxes, grid, px_per_ft, 6)
    assert len(doors) == 1
    assert doors[0]["width_in"] == 32 and doors[0]["rooms"] == [1, 2]


def test_doorway_with_a_leaf_block_is_found_measured_and_opened():
    # two rooms split by a wall on row 10, a 6-cell gap holding a door leaf read as a block (-4)
    grid = np.zeros((20, 30), int)
    grid[10:] = 1
    grid[9:12, :] = -1
    grid[9:12, 10:16] = -4
    gray = np.full((20 * 6, 30 * 6), 255, np.uint8)
    gray[9 * 6:12 * 6, :] = 0                 # wall
    gray[9 * 6:12 * 6, 10 * 6:16 * 6] = 255   # the opening (the leaf is thin, not wall)
    swing = [(10 * 6, 12 * 6, 15 * 6, 17 * 6, 0.8)]     # the door's swing drawn just below the gap
    doors = sam_items.doorways(gray, grid, 12.0, 6, swing)
    assert len(doors) == 1 and doors[0]["rooms"] == [0, 1]
    assert 30 <= doors[0]["width_in"] <= 40
    assert (grid[9:12, 10:16] != -4).all()     # people can walk through now



def test_gap_between_rooms_without_a_swing_is_an_open_doorway():
    grid = np.zeros((20, 30), int)
    grid[10:] = 1
    grid[9:12, :] = -1
    grid[9:12, 10:16] = 0
    gray = np.full((120, 180), 255, np.uint8)
    gray[54:72, :] = 0
    gray[54:72, 60:96] = 255
    d = sam_items.doorways(gray, grid, 12.0, 6, [])
    assert len(d) == 1 and d[0]["has_door"] is None and d[0]["rooms"] == [0, 1]


def test_wide_gap_without_a_swing_is_not_a_door():
    grid = np.zeros((20, 40), int)
    grid[10:] = 1
    grid[9:12, :] = -1
    grid[9:12, 10:20] = 0                     # 60 in: an open plan gap, not a door
    gray = np.full((120, 240), 255, np.uint8)
    gray[54:72, :] = 0
    gray[54:72, 60:120] = 255
    assert sam_items.doorways(gray, grid, 12.0, 6, []) == []



def test_door_with_a_big_swing_arc_beyond_the_wall_is_opened():
    # hallway (5) above, work area (9) below; the doorway and the swing below it are drawn as a block
    grid = np.full((30, 30), 5, int)
    grid[15:] = 9
    grid[12:14, :] = -1
    grid[12:20, 12:17] = -4          # door leaf in the wall and its arc spilling 6 rows into the room
    gray = np.full((180, 180), 255, np.uint8)
    gray[72:84, :] = 0
    gray[72:84, 72:102] = 255
    swing = [(72, 84, 102, 120, 0.8)]
    doors = sam_items.doorways(gray, grid, 12.0, 6, swing)
    assert len(doors) == 1 and doors[0]["rooms"] == [5, 9]
    assert (grid[12:20, 12:17] >= 0).all()      # leaf and arc are floor now
