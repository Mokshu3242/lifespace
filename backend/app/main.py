"""LifeSpace API."""
import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config import get_settings
from app.router.model_router import AllProvidersFailed, CHAINS, get_router

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

settings = get_settings()
app = FastAPI(title="LifeSpace API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"ok": True, "mode": settings.mode, "chain": CHAINS[settings.mode]}


class AskIn(BaseModel):
    prompt: str


@app.post("/api/ask")
def ask(body: AskIn):
    """Dev-only smoke test for the router."""
    router = get_router()
    try:
        text = router.ask(body.prompt)
    except AllProvidersFailed as e:
        raise HTTPException(503, f"All providers failed: {e}")
    return {"text": text, "provider": router.last_provider}
