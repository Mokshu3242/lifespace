"""Spaces API: upload a plan, get a grid map, save hand fixes."""
import json
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from app.config import ROOT
from app.router.model_router import AllProvidersFailed, get_router
from app.space.reader import read_floor_plan

router = APIRouter(prefix="/api/spaces", tags=["spaces"])
STORE = ROOT / ".data" / "spaces"
STORE.mkdir(parents=True, exist_ok=True)
MAX_BYTES = 15 * 1024 * 1024
ID_RE = re.compile(r"^[a-f0-9]{12}$")


def _path(space_id: str, name: str) -> Path:
    if not ID_RE.match(space_id):
        raise HTTPException(400, "Bad space id")
    return STORE / space_id / name


@router.post("")
async def create_space(file: UploadFile = File(...),
                       fresh: bool = Query(False, description="ignore saved AI answers"),
                       pack: str = Query("home", pattern="^(home|office)$"),
                       describe: str = Query("", max_length=40)):
    describe = " ".join(describe.split())
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Image is over 15 MB")
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(415, "Upload an image (PNG or JPG)")
    try:
        router_ = get_router()
        router_.fresh = fresh
        try:
            smap = read_floor_plan(data, router_, pack, describe)
        finally:
            router_.fresh = False
    except AllProvidersFailed as e:
        raise HTTPException(503, f"Vision models are unavailable: {e}")
    except Exception as e:  # bad image file
        raise HTTPException(422, f"Couldn't read that image: {e}")

    space_id = uuid.uuid4().hex[:12]
    folder = STORE / space_id
    folder.mkdir(parents=True)
    (folder / "plan.img").write_bytes(data)
    out = {"id": space_id, "provider": get_router().last_provider,
           "pack": pack, "describe": describe, **smap.to_dict()}
    (folder / "map.json").write_text(json.dumps(out))
    return out


@router.get("/{space_id}")
def get_space(space_id: str):
    p = _path(space_id, "map.json")
    if not p.exists():
        raise HTTPException(404, "Space not found")
    return json.loads(p.read_text())


@router.get("/{space_id}/image")
def get_image(space_id: str):
    p = _path(space_id, "plan.img")
    if not p.exists():
        raise HTTPException(404, "Space not found")
    return FileResponse(p)


class MapEdit(BaseModel):
    grid: list[list[int]]
    rooms: list[dict]
    entrance: list[int] | None = None


@router.put("/{space_id}")
def save_space(space_id: str, edit: MapEdit):
    """Save hand fixes from the editor (painted cells, renamed rooms, moved entrance)."""
    p = _path(space_id, "map.json")
    if not p.exists():
        raise HTTPException(404, "Space not found")
    current = json.loads(p.read_text())
    if len(edit.grid) != current["rows"] or any(len(r) != current["cols"] for r in edit.grid):
        raise HTTPException(400, "Grid size changed; that isn't allowed")
    current.update(grid=edit.grid, rooms=edit.rooms, entrance=edit.entrance, edited=True)
    p.write_text(json.dumps(current))
    return current
