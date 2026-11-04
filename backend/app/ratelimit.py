"""A small per-visitor daily limit on the calls that spend Meta credits. In memory: a restart resets it,
which is fine for a demo. Off in mock and local modes."""
from __future__ import annotations

import os
import time
from collections import defaultdict

from fastapi import Request
from fastapi.responses import JSONResponse

from app.budget import closed, spent
from app.config import get_settings

READS = ("/api/spaces", "/api/streets")                      # POST here = a new plan or photo read
ACTIONS = ("/designs", "/simulate", "/future", "/ask", "/talk", "/comic", "/doctor", "/restyle",
           "/render", "/family", "/compare")
_hits: dict[tuple[str, str, int], int] = defaultdict(int)
# one budget for the whole site: at most this many AI actions a day that really reach Meta's models
GLOBAL_CAP = int(os.getenv("GLOBAL_AI_PER_DAY", "30"))
_site: dict[int, int] = defaultdict(int)


def _who(req: Request) -> str:
    fwd = req.headers.get("x-forwarded-for", "")
    return (fwd.split(",")[0].strip() or (req.client.host if req.client else "?"))


async def limit(req: Request, call_next):
    s = get_settings()
    if req.method != "POST" or s.mode != "prod":
        return await call_next(req)
    path = req.url.path.rstrip("/")
    kind = "read" if path in READS else "action" if any(a in path for a in ACTIONS) else None
    if kind is None:
        return await call_next(req)
    if path.endswith("/doctor") and req.query_params.get("apply") == "1":
        return await call_next(req)          # putting chosen fixes on the map: code only, no model call
    day = int(time.time() // 86400)
    key = (_who(req), kind, day)
    cap = s.rate_reads_per_day if kind == "read" else s.rate_actions_per_day
    if _hits[key] >= cap:
        return JSONResponse({"detail": f"Daily limit reached for this demo ({cap} {'plan reads' if kind == 'read' else 'AI actions'}). "
                                       "The sample plans still work. Try again tomorrow."}, status_code=429)
    _hits[key] += 1
    box = [0]
    t1, t2 = closed.set(_site[day] >= GLOBAL_CAP), spent.set(box)
    try:
        resp = await call_next(req)
    finally:
        closed.reset(t1); spent.reset(t2)
    if box[0]:
        _site[day] += 1        # only actions that really used a model count
    return resp
