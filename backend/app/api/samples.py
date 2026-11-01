"""Sample spaces for the start page: plans already read and worked on, opened by id.
No file upload, no model calls, and the sample pictures never have to sit in the public repo.

Pick them with the SAMPLES setting, for example
  SAMPLES=home:32ec7da602fa,office:071d055fdc95,street:ab12cd34ef56
Without it, the most worked-on saved home and office and the newest street are used."""
import json
import os

from fastapi import APIRouter

from app.config import ROOT

router = APIRouter(prefix="/api/samples", tags=["samples"])
LABEL = {"home": ("🌿", "Home with terrace (best demo)"), "office": ("🏢", "Small office"), "street": ("🚏", "A city street")}


def _work(folder):
    """How much was done on a saved space: designs, people runs, pictures."""
    return sum(1 for _ in folder.glob("designs/*")) + sum(1 for _ in folder.glob("sims/*")) + (folder / "family.json").exists()


@router.get("")
def samples():
    chosen = {}
    for part in (os.environ.get("SAMPLES") or "").split(","):
        if ":" in part:
            k, v = part.split(":", 1)
            chosen[k.strip()] = v.strip()
    spaces = ROOT / ".data" / "spaces"
    for pack in ("home", "office"):
        if pack in chosen and (spaces / chosen[pack] / "map.json").exists():
            continue
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
            chosen[pack] = best[1]
    streets = ROOT / ".data" / "streets"
    if "street" not in chosen or not (streets / chosen["street"]).exists():
        found = sorted((p for p in streets.glob("*") if p.is_dir() and (p / "photo.png").exists()),
                       key=lambda p: p.stat().st_mtime, reverse=True) if streets.exists() else []
        if found:
            chosen["street"] = found[0].name
    out = []
    for kind in ("home", "office", "street"):
        if kind not in chosen:
            continue
        icon, label = LABEL[kind]
        sid = chosen[kind]
        thumb = f"/api/streets/{sid}/photo" if kind == "street" else f"/api/spaces/{sid}/image"
        out.append({"kind": kind, "id": sid, "icon": icon, "label": label, "thumb": thumb})
    return out
