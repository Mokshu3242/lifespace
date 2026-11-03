"""Streets API: upload a street photo, get what's there and a scorecard, redesign it, see it drawn."""
import json

from starlette.concurrency import run_in_threadpool
import re
import uuid
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse, Response
from pydantic import BaseModel

from app.config import ROOT
from app.router.model_router import AllProvidersFailed, get_router
from app.space import street

router = APIRouter(prefix="/api/streets", tags=["streets"])
STORE = ROOT / ".data" / "streets"
STORE.mkdir(parents=True, exist_ok=True)
MAX_BYTES = 15 * 1024 * 1024


def _folder(street_id: str) -> Path:
    if not re.fullmatch(r"[0-9a-f]{12}", street_id):
        raise HTTPException(404, "Street not found")
    p = STORE / street_id
    if not (p / "street.json").exists():
        raise HTTPException(404, "Street not found")
    return p


@router.post("")
async def create_street(file: UploadFile = File(...)):
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Image is over 15 MB")
    if not (file.content_type or "").startswith("image/"):
        raise HTTPException(415, "Upload a PNG or JPG photo")
    try:
        read = await run_in_threadpool(street.read_street, data, get_router())   # off the loop: keeps /api/health answering
    except ValueError as e:
        raise HTTPException(400, str(e))
    except AllProvidersFailed as e:
        raise HTTPException(503, f"Models are unavailable: {e}")
    sid = uuid.uuid4().hex[:12]
    folder = STORE / sid
    folder.mkdir(parents=True)
    (folder / "photo.png").write_bytes(read.pop("png"))
    out = {"id": sid, "provider": get_router().last_provider, **read, "scores": street.scorecard(read)}
    (folder / "street.json").write_text(json.dumps(out), encoding="utf-8")
    (folder / "designs").mkdir()
    return out


@router.get("/{street_id}")
def get_street(street_id: str):
    p = _folder(street_id)
    out = json.loads((p / "street.json").read_text(encoding="utf-8"))
    out["designs"] = [json.loads(f.read_text(encoding="utf-8"))
                      for f in sorted((f for f in (p / "designs").glob("*.json") if f.stem.isdigit()), key=lambda f: int(f.stem))]
    return out


@router.get("/{street_id}/photo")
def get_photo(street_id: str):
    return FileResponse(_folder(street_id) / "photo.png", media_type="image/png")


class StreetAsk(BaseModel):
    budget: float = 20000
    goals: str = ""


@router.post("/{street_id}/designs")
def create_design(street_id: str, ask: StreetAsk):
    p = _folder(street_id)
    if not 500 <= ask.budget <= 2_000_000:
        raise HTTPException(400, "Budget must be between $500 and $2,000,000")
    read = json.loads((p / "street.json").read_text(encoding="utf-8"))
    try:
        design = street.redesign(read, ask.budget, " ".join(ask.goals.split()), get_router())
    except AllProvidersFailed as e:
        raise HTTPException(503, f"Models are unavailable: {e}")
    folder = p / "designs"
    n = len([f for f in folder.glob("*.json") if f.stem.isdigit()]) + 1
    while True:
        try:
            with open(folder / f"{n}.json", "x", encoding="utf-8") as f:
                design = {"n": n, "goals": ask.goals[:300], "provider": get_router().last_provider, **design}
                json.dump(design, f)
            return design
        except FileExistsError:
            n += 1


@router.post("/{street_id}/designs/{n}/render")
def render_design(street_id: str, n: int):
    p = _folder(street_id)
    dp = p / "designs" / f"{n}.json"
    if not dp.exists():
        raise HTTPException(404, "Design not found")
    design = json.loads(dp.read_text(encoding="utf-8"))
    read = json.loads((p / "street.json").read_text(encoding="utf-8"))
    if not design["changes"]:
        raise HTTPException(400, "This design has no changes to draw")
    try:
        png = get_router().render(street.render_prompt(read, design), (p / "photo.png").read_bytes())
    except AllProvidersFailed as e:
        raise HTTPException(503, f"Image models are unavailable: {e}")
    (p / "designs" / f"{n}.png").write_bytes(png)
    return {"ok": True, "provider": get_router().last_provider}


@router.get("/{street_id}/designs/{n}/render")
def get_render(street_id: str, n: int):
    f = _folder(street_id) / "designs" / f"{n}.png"
    if not f.exists():
        raise HTTPException(404, "Not drawn yet")
    return Response(f.read_bytes(), media_type="image/png")
