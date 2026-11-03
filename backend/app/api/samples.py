"""Sample spaces for the start page: plans already read and worked on, opened by id.
No file upload, no model calls, and the sample pictures never have to sit in the public repo.

Pick them with the SAMPLES setting, a list shown in order, for example
  SAMPLES=home:073c1ff1e713:Family home,street:1674e2e9c9b2:Busy street
Without it, the most worked-on saved home and office and the newest street are used."""
import json
import os

from fastapi import APIRouter

from app.config import ROOT

router = APIRouter(prefix="/api/samples", tags=["samples"])
LABEL = {"home": ("🏠", "A home"), "office": ("🏢", "An office"), "street": ("🚏", "A street")}


def _work(folder):
    """How much was done on a saved space: designs, people runs, pictures."""
    return sum(1 for _ in folder.glob("designs/*")) + sum(1 for _ in folder.glob("sims/*")) + (folder / "family.json").exists()


def _card(kind: str, sid: str, label: str = "") -> dict:
    icon, default = LABEL.get(kind, ("🏠", "A space"))
    thumb = f"/api/streets/{sid}/photo" if kind == "street" else f"/api/spaces/{sid}/image"
    return {"kind": kind, "id": sid, "icon": icon, "label": label or default, "thumb": thumb}


@router.get("")
def samples():
    """SAMPLES is a list, shown in order: kind:id or kind:id:Card name, e.g.
    home:073c1ff1e713:Family home,street:1674e2e9c9b2:Busy street. When it's set, only those are shown."""
    spaces, streets = ROOT / ".data" / "spaces", ROOT / ".data" / "streets"
    out = []
    for part in (os.environ.get("SAMPLES") or "").split(","):
        bits = [b.strip() for b in part.split(":", 2)]
        if len(bits) < 2 or bits[0] not in LABEL:
            continue
        kind, sid = bits[0], bits[1]
        there = (streets / sid / "photo.png").exists() if kind == "street" else (spaces / sid / "map.json").exists()
        if there:
            out.append(_card(kind, sid, bits[2] if len(bits) > 2 else ""))
    if out or os.environ.get("SAMPLES"):
        return out
    # no list set: the most worked-on saved home and office, and the newest street
    for pack in ("home", "office"):
        best = None
        for mp in spaces.glob("*/map.json"):
            try:
                if (json.loads(mp.read_text(encoding="utf-8")).get("pack") or "home") != pack:
                    continue
            except (OSError, ValueError):
                continue
            score = (_work(mp.parent), mp.stat().st_mtime)
            if best is None or score > best[0]:
                best = (score, mp.parent.name)
        if best:
            out.append(_card(pack, best[1]))
    found = sorted((p for p in streets.glob("*") if p.is_dir() and (p / "photo.png").exists()),
                   key=lambda p: p.stat().st_mtime, reverse=True) if streets.exists() else []
    if found:
        out.append(_card("street", found[0].name))
    return out
