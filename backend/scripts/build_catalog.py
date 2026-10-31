"""Writes the home and office catalogs. Sizes are standard US sizes in inches.
Prices are typical US retail for a mid-range version of each item (USD, 2026).
Run: python -m scripts.build_catalog"""
import json
from pathlib import Path

# id, name, category, width, depth, height, price, watts, rooms, uses
HOME = [
    ("bed-queen", "Queen bed", "bed", 64, 84, 40, 650, 0, "bedroom", "sleep"),
    ("bed-full", "Full bed", "bed", 56, 78, 40, 480, 0, "bedroom", "sleep"),
    ("bed-twin", "Twin bed", "bed", 41, 79, 36, 320, 0, "bedroom", "sleep"),
    ("bed-king", "King bed", "bed", 80, 84, 40, 900, 0, "bedroom", "sleep"),
    ("nightstand", "Nightstand", "storage", 20, 16, 24, 90, 0, "bedroom", "store"),
    ("dresser", "6-drawer dresser", "storage", 60, 18, 32, 380, 0, "bedroom", "store"),
    ("wardrobe", "Wardrobe", "storage", 40, 24, 79, 300, 0, "bedroom", "store"),
    ("sofa-3", "3-seat sofa", "seat", 84, 36, 34, 800, 0, "living room", "sit,rest"),
    ("sofa-2", "Loveseat", "seat", 60, 34, 34, 550, 0, "living room", "sit,rest"),
    ("armchair", "Armchair", "seat", 32, 34, 34, 300, 0, "living room,bedroom", "sit"),
    ("coffee-table", "Coffee table", "table", 42, 22, 18, 150, 0, "living room", "place"),
    ("tv-stand", "TV stand with 55 in TV", "media", 60, 16, 24, 650, 90, "living room", "watch"),
    ("bookshelf", "Bookshelf", "storage", 31, 11, 79, 80, 0, "living room,bedroom,office", "store"),
    ("rug", "Area rug 5x8", "decor", 60, 96, 0, 120, 0, "living room,bedroom", "comfort"),
    ("dining-4", "Dining table for 4", "table", 48, 30, 30, 300, 0, "dining area,kitchen", "eat"),
    ("dining-6", "Dining table for 6", "table", 72, 36, 30, 550, 0, "dining area", "eat"),
    ("dining-chair", "Dining chair", "seat", 18, 21, 33, 60, 0, "dining area,kitchen", "sit"),
    ("bar-stool", "Bar stool", "seat", 16, 16, 30, 70, 0, "kitchen", "sit"),
    ("fridge", "Refrigerator", "appliance", 30, 32, 68, 1200, 150, "kitchen", "cook"),
    ("range", "Stove and oven", "appliance", 30, 26, 36, 800, 2000, "kitchen", "cook"),
    ("dishwasher", "Dishwasher", "appliance", 24, 24, 34, 600, 1200, "kitchen", "clean"),
    ("microwave", "Microwave", "appliance", 20, 15, 12, 120, 1000, "kitchen", "cook"),
    ("kitchen-island", "Kitchen island cart", "table", 48, 24, 36, 350, 0, "kitchen", "cook,place"),
    ("washer", "Washing machine", "appliance", 27, 30, 39, 800, 500, "laundry,closet,bathroom", "clean"),
    ("dryer", "Dryer", "appliance", 27, 30, 39, 750, 3000, "laundry,closet,bathroom", "clean"),
    ("toilet", "Toilet", "fixture", 15, 28, 30, 250, 0, "bathroom", "wash"),
    ("vanity", "Bathroom vanity with sink", "fixture", 30, 21, 34, 400, 0, "bathroom", "wash"),
    ("tub", "Bathtub", "fixture", 30, 60, 20, 600, 0, "bathroom", "wash"),
    ("shower", "Shower stall", "fixture", 36, 36, 80, 700, 0, "bathroom", "wash"),
    ("desk-home", "Home desk", "table", 47, 24, 30, 150, 0, "bedroom,living room,office", "work"),
    ("desk-chair", "Desk chair", "seat", 24, 24, 38, 150, 0, "bedroom,living room,office", "sit,work"),
    ("floor-lamp", "Floor lamp (LED)", "light", 12, 12, 64, 60, 10, "*", "light"),
    ("table-lamp", "Table lamp (LED)", "light", 10, 10, 20, 35, 8, "*", "light"),
    ("ceiling-fan", "Ceiling fan", "air", 52, 52, 0, 200, 60, "bedroom,living room", "cool"),
    ("air-purifier", "Air purifier", "air", 10, 10, 20, 150, 40, "*", "air"),
    ("window-ac", "Window air conditioner", "air", 19, 16, 13, 350, 550, "bedroom,living room", "cool"),
    ("space-heater", "Space heater", "air", 10, 8, 12, 60, 1500, "*", "heat"),
    ("plant", "Potted plant", "decor", 14, 14, 36, 50, 0, "*", "comfort"),
    ("shoe-rack", "Shoe rack", "storage", 30, 12, 20, 40, 0, "foyer,hallway,closet", "store"),
    ("grab-bar", "Bathroom grab bar", "safety", 24, 3, 3, 35, 0, "bathroom", "safety"),
    ("night-light", "Motion night light", "safety", 3, 2, 3, 15, 1, "hallway,bathroom,bedroom", "light,safety"),
    ("smoke-alarm", "Smoke alarm", "safety", 6, 6, 2, 25, 0, "*", "safety"),
    # style and comfort
    ("wall-art", "Framed wall art", "decor", 30, 2, 40, 90, 0, "living room,bedroom,dining area,foyer,hallway", "comfort,style"),
    ("mirror", "Full-length mirror", "decor", 24, 2, 65, 120, 0, "bedroom,foyer,hallway,bathroom", "style,light"),
    ("curtains", "Linen curtains (pair)", "decor", 100, 2, 84, 80, 0, "living room,bedroom,dining area", "comfort,style,quiet"),
    ("pendant", "Pendant light (LED)", "light", 16, 16, 0, 140, 12, "dining area,kitchen,living room,foyer", "light,style"),
    ("accent-chair", "Accent chair", "seat", 28, 30, 32, 280, 0, "living room,bedroom", "sit,style"),
    ("shelves", "Floating wall shelves", "storage", 36, 8, 2, 70, 0, "living room,bedroom,kitchen,dining area,hallway", "store,style"),
    ("side-table-home", "Side table", "table", 18, 18, 22, 80, 0, "living room,bedroom", "place"),
    ("bench-entry", "Entry bench with storage", "seat", 40, 16, 18, 160, 0, "foyer,hallway", "sit,store"),
    ("sideboard", "Sideboard", "storage", 60, 18, 32, 450, 0, "dining area,living room", "store,style"),
    ("smart-bulbs", "Smart LED bulbs (4 pack)", "light", 3, 3, 0, 50, 36, "*", "light,energy"),
    ("blackout", "Blackout shades", "decor", 60, 2, 72, 90, 0, "bedroom", "sleep,quiet"),
    # outdoor
    ("outdoor-chairs", "Outdoor chairs (pair)", "outdoor", 48, 28, 32, 220, 0, "terrace,balcony,patio,outdoor", "sit,rest"),
    ("outdoor-table", "Outdoor bistro table", "outdoor", 28, 28, 29, 120, 0, "terrace,balcony,patio,outdoor", "eat,place"),
    ("outdoor-sofa", "Outdoor loveseat", "outdoor", 54, 30, 30, 450, 0, "terrace,balcony,patio,outdoor", "sit,rest"),
    ("planter", "Large outdoor planter", "outdoor", 20, 20, 24, 80, 0, "terrace,balcony,patio,outdoor", "comfort,air"),
    ("string-lights", "Outdoor string lights", "outdoor", 3, 3, 0, 40, 10, "terrace,balcony,patio,outdoor", "light,style"),
]

OFFICE = [
    ("desk-office", "Office desk", "table", 60, 30, 30, 300, 0, "open work area,office", "work"),
    ("desk-standing", "Standing desk", "table", 60, 30, 48, 500, 50, "open work area,office", "work"),
    ("bench-desk-4", "Bench desk for 4", "table", 120, 60, 30, 1200, 0, "open work area", "work"),
    ("task-chair", "Task chair", "seat", 26, 26, 40, 250, 0, "open work area,office,meeting room", "sit,work"),
    ("monitor", "24 in monitor", "media", 21, 8, 16, 150, 20, "open work area,office", "work"),
    ("pedestal", "Mobile file pedestal", "storage", 16, 22, 24, 180, 0, "open work area,office", "store"),
    ("cabinet", "Storage cabinet", "storage", 36, 18, 72, 350, 0, "*", "store"),
    ("meet-4", "Meeting table for 4", "table", 48, 48, 30, 450, 0, "meeting room,phone booth", "meet"),
    ("meet-8", "Meeting table for 8", "table", 96, 42, 30, 1100, 0, "meeting room", "meet"),
    ("meet-chair", "Meeting chair", "seat", 22, 22, 34, 150, 0, "meeting room", "sit"),
    ("screen-65", "65 in display on stand", "media", 58, 24, 60, 1100, 150, "meeting room", "present"),
    ("whiteboard", "Mobile whiteboard", "media", 48, 24, 72, 250, 0, "meeting room,open work area", "present"),
    ("phone-booth", "One-person phone booth", "room", 40, 40, 88, 6000, 60, "open work area", "call"),
    ("reception-desk", "Reception desk", "table", 72, 30, 42, 900, 0, "reception", "work,greet"),
    ("waiting-chair", "Waiting chair", "seat", 24, 26, 32, 180, 0, "reception,lounge", "sit"),
    ("lounge-sofa", "Lounge sofa", "seat", 80, 34, 32, 1100, 0, "lounge,reception", "sit,rest"),
    ("lounge-chair", "Lounge chair", "seat", 30, 32, 32, 400, 0, "lounge,reception", "sit"),
    ("side-table", "Side table", "table", 20, 20, 20, 90, 0, "lounge,reception", "place"),
    ("cafe-table", "Cafe table", "table", 30, 30, 30, 200, 0, "pantry,lounge", "eat"),
    ("cafe-chair", "Cafe chair", "seat", 18, 20, 32, 90, 0, "pantry,lounge", "sit"),
    ("pantry-stool", "Counter stool", "seat", 16, 16, 30, 90, 0, "pantry", "sit"),
    ("fridge-office", "Refrigerator", "appliance", 30, 32, 68, 1200, 150, "pantry", "cook"),
    ("microwave-office", "Microwave", "appliance", 20, 15, 12, 120, 1000, "pantry", "cook"),
    ("coffee-machine", "Coffee machine", "appliance", 12, 16, 18, 400, 1400, "pantry", "cook"),
    ("water-cooler", "Water dispenser", "appliance", 13, 13, 40, 200, 100, "pantry,hallway", "drink"),
    ("dishwasher-office", "Dishwasher", "appliance", 24, 24, 34, 600, 1200, "pantry", "clean"),
    ("printer", "Office printer", "appliance", 24, 24, 40, 900, 600, "open work area,storage,hallway", "print"),
    ("locker", "Locker unit", "storage", 36, 18, 72, 450, 0, "hallway,storage", "store"),
    ("server-rack", "Server rack", "appliance", 24, 42, 80, 1500, 1200, "server room", "it"),
    ("coat-rack", "Coat rack", "storage", 20, 20, 70, 60, 0, "reception,hallway", "store"),
    ("acoustic-panel", "Acoustic wall panel", "noise", 24, 2, 48, 120, 0, "*", "quiet"),
    ("divider", "Desk privacy divider", "noise", 60, 2, 24, 150, 0, "open work area", "quiet"),
    ("desk-lamp", "LED desk lamp", "light", 8, 8, 18, 50, 8, "open work area,office", "light"),
    ("floor-lamp-office", "Floor lamp (LED)", "light", 12, 12, 64, 80, 10, "*", "light"),
    ("air-purifier-office", "Air purifier", "air", 14, 14, 26, 300, 60, "*", "air"),
    ("fan-office", "Pedestal fan", "air", 16, 16, 48, 70, 45, "*", "cool"),
    ("plant-office", "Large potted plant", "decor", 18, 18, 60, 120, 0, "*", "comfort"),
    ("first-aid", "First aid cabinet", "safety", 15, 6, 20, 80, 0, "pantry,hallway", "safety"),
    ("extinguisher", "Fire extinguisher", "safety", 8, 6, 20, 60, 0, "hallway,pantry", "safety"),
    ("wall-art-office", "Framed wall art", "decor", 36, 2, 48, 120, 0, "*", "comfort,style"),
    ("pendant-office", "Pendant light (LED)", "light", 20, 20, 0, 180, 15, "meeting room,pantry,reception,lounge", "light,style"),
    ("moss-wall", "Preserved moss wall panel", "noise", 24, 2, 24, 200, 0, "*", "quiet,style,comfort"),
    ("rug-office", "Area rug 6x9", "decor", 72, 108, 0, 250, 0, "lounge,reception,office", "comfort,quiet"),
    ("toilet-office", "Toilet", "fixture", 15, 28, 30, 250, 0, "restroom", "wash"),
    ("sink-office", "Wall sink", "fixture", 20, 18, 34, 250, 0, "restroom,pantry", "wash"),
]


def rows(items):
    out = []
    for id_, name, cat, w, d, h, price, watts, rooms, uses in items:
        out.append({"id": id_, "name": name, "category": cat,
                    "size_in": {"w": w, "d": d, "h": h}, "price_usd": price, "watts": watts,
                    "rooms": rooms.split(","), "uses": uses.split(",")})
    return out


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1] / "data" / "packs"
    for pack, items in (("home", HOME), ("office", OFFICE)):
        doc = {"pack": pack, "note": "Standard US sizes in inches. Typical mid-range US prices, 2026.",
               "items": rows(items)}
        (root / pack / "catalog.json").write_text(json.dumps(doc, indent=1))
        print(pack, len(items))
