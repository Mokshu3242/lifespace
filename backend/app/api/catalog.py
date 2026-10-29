"""Catalog API: list the real items a pack can use."""
from fastapi import APIRouter, HTTPException

from app import catalog

router = APIRouter(prefix="/api/catalog", tags=["catalog"])


@router.get("/{pack}")
def list_items(pack: str):
    try:
        items = catalog.load(pack)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"pack": pack, "items": [i.to_dict() for i in items]}
