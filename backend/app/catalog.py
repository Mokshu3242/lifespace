"""The catalog: real, common items with standard sizes and typical prices.

Used to name detected furniture (shortlist by size and room) and, later, for redesigns."""
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

PACKS_DIR = Path(__file__).resolve().parents[1] / "data" / "packs"
PACKS = ("home", "office")


@dataclass(frozen=True)
class Item:
    id: str
    name: str
    category: str
    w_in: float
    d_in: float
    h_in: float
    price_usd: float
    watts: float
    rooms: tuple[str, ...]
    uses: tuple[str, ...]

    def fits_room(self, room: str) -> bool:
        room = room.lower()
        return "*" in self.rooms or any(r in room or room in r for r in self.rooms)

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "category": self.category,
                "size_in": {"w": self.w_in, "d": self.d_in, "h": self.h_in},
                "price_usd": self.price_usd, "watts": self.watts,
                "rooms": list(self.rooms), "uses": list(self.uses)}


@lru_cache
def load(pack: str) -> tuple[Item, ...]:
    if pack not in PACKS:
        raise ValueError(f"Unknown pack: {pack}")
    doc = json.loads((PACKS_DIR / pack / "catalog.json").read_text())
    return tuple(Item(i["id"], i["name"], i["category"], i["size_in"]["w"], i["size_in"]["d"],
                      i["size_in"]["h"], i["price_usd"], i["watts"], tuple(i["rooms"]), tuple(i["uses"]))
                 for i in doc["items"])


def get(pack: str, item_id: str) -> Item | None:
    return next((i for i in load(pack) if i.id == item_id), None)


def size_error(item: Item, w_in: float, d_in: float) -> float:
    """How far a shape's size is from the item's, as a fraction. Either rotation counts."""
    a, b = sorted((w_in, d_in))
    x, y = sorted((item.w_in, item.d_in))
    return max(abs(a - x) / x, abs(b - y) / y)


def shortlist(pack: str, w_in: float, d_in: float, room: str = "",
              tolerance: float = 0.4, limit: int = 6) -> list[Item]:
    """Catalog items that could be a shape of this size in this room, closest size first.
    Items with no floor footprint (ceiling fans, wall panels) are never matched to a shape."""
    out = []
    for it in load(pack):
        if it.d_in < 6 or it.h_in == 0:
            continue
        if room and not it.fits_room(room):
            continue
        err = size_error(it, w_in, d_in)
        if err <= tolerance:
            out.append((err, it))
    out.sort(key=lambda p: p[0])
    return [it for _, it in out[:limit]]
