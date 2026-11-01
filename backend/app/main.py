"""LifeSpace API."""
import logging

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.api.spaces import router as spaces_router
from app.api.catalog import router as catalog_router
from app.api.streets import router as streets_router
from app.api.samples import router as samples_router
from app.config import get_settings
from app.router.model_router import AllProvidersFailed, CHAINS, get_router

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
logging.getLogger("httpx").setLevel(logging.WARNING)      # not one line per file or model call

settings = get_settings()
app = FastAPI(title="LifeSpace API", version="0.1.0")
from app.ratelimit import limit as _limit   # noqa: E402
app.middleware("http")(_limit)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.frontend_origin.split(",") if o.strip()],
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(spaces_router)
app.include_router(catalog_router)
app.include_router(streets_router)
app.include_router(samples_router)


@app.on_event("startup")
def _restore_data():
    """Bring back saved plans and answers from Supabase before the first request (no-op without it)."""
    from app import storage_sync
    storage_sync.start()


@app.get("/api/health")
def health():
    return {"ok": True, "mode": settings.mode, "chain": CHAINS[settings.mode]}


class AskIn(BaseModel):
    prompt: str


@app.post("/api/ask")
def ask(body: AskIn):
    """Dev-only smoke test for the router. Off in prod so nobody can spend the credits."""
    router = get_router()
    if router.s.mode == "prod":
        raise HTTPException(404, "Not available in prod mode")
    try:
        text = router.ask(body.prompt)
    except AllProvidersFailed as e:
        raise HTTPException(503, f"All providers failed: {e}")
    return {"text": text, "provider": router.last_provider}
