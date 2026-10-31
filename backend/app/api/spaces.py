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
    (folder / "map.json").write_text(json.dumps(out), encoding="utf-8")
    return out


@router.get("/{space_id}")
def get_space(space_id: str):
    p = _path(space_id, "map.json")
    if not p.exists():
        raise HTTPException(404, "Space not found")
    return json.loads(p.read_text(encoding="utf-8"))


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
    items: list[dict] | None = None


@router.put("/{space_id}")
def save_space(space_id: str, edit: MapEdit):
    """Save hand fixes from the editor (painted cells, renamed rooms, moved entrance)."""
    p = _path(space_id, "map.json")
    if not p.exists():
        raise HTTPException(404, "Space not found")
    current = json.loads(p.read_text(encoding="utf-8"))
    if len(edit.grid) != current["rows"] or any(len(r) != current["cols"] for r in edit.grid):
        raise HTTPException(400, "Grid size changed; that isn't allowed")
    current.update(grid=edit.grid, rooms=edit.rooms, entrance=edit.entrance, edited=True)
    if edit.items is not None:
        current["items"] = edit.items
    p.write_text(json.dumps(current), encoding="utf-8")
    return current


class RedesignAsk(BaseModel):
    budget: float = 1000
    goals: str = ""


@router.post("/{space_id}/designs")
def create_design(space_id: str, ask: RedesignAsk):
    """Redesign the saved map with real catalog items inside a budget. Each run is a new version."""
    from app.space.reader import context_line
    from app.space.redesign import redesign

    p = _path(space_id, "map.json")
    if not p.exists():
        raise HTTPException(404, "Space not found")
    if not 50 <= ask.budget <= 100_000:
        raise HTTPException(400, "Budget must be between $50 and $100,000")
    space = json.loads(p.read_text(encoding="utf-8"))
    goals = " ".join(ask.goals.split())[:300]
    try:
        design = redesign(space, ask.budget, goals, get_router(),
                          context_line(space.get("pack") or "home", space.get("describe") or ""))
    except AllProvidersFailed as e:
        raise HTTPException(503, f"Models are unavailable: {e}")
    return _save_design(p.parent / "designs",
                        {"goals": goals, "provider": get_router().last_provider, **design.to_dict()})


def _save_design(folder: Path, out: dict) -> dict:
    """Save as the next design number. Two saves at once never overwrite each other."""
    folder.mkdir(exist_ok=True)
    n = len([f for f in folder.glob("*.json") if f.stem.isdigit()]) + 1
    while True:
        try:
            out["id"] = n
            with open(folder / f"{n}.json", "x", encoding="utf-8") as fh:
                fh.write(json.dumps(out))
            return out
        except FileExistsError:
            n += 1


@router.get("/{space_id}/designs")
def list_designs(space_id: str):
    folder = _path(space_id, "designs")
    if not folder.exists():
        return []
    files = sorted((f for f in folder.glob("*.json") if f.stem.isdigit()), key=lambda f: int(f.stem))
    return [json.loads(f.read_text(encoding="utf-8")) for f in files]


class SimulateAsk(BaseModel):
    design_id: int | None = None


@router.post("/{space_id}/simulate")
def run_simulation(space_id: str, ask: SimulateAsk):
    """AI people live a day Before and After a redesign. Paths and numbers come from code."""
    from app.space.reader import context_line
    from app.space.simulate import simulate

    p = _path(space_id, "map.json")
    if not p.exists():
        raise HTTPException(404, "Space not found")
    space = json.loads(p.read_text(encoding="utf-8"))
    after, changes = None, []
    if ask.design_id is not None:
        dp = _path(space_id, "designs") / f"{int(ask.design_id)}.json"
        if not dp.exists():
            raise HTTPException(404, "Design not found")
        design = json.loads(dp.read_text(encoding="utf-8"))
        after, changes = design["items"], design.get("changes", [])
    fam = p.parent / "family.json"
    people = json.loads(fam.read_text(encoding="utf-8"))["people"] if fam.exists() else None
    out = simulate(space, after, get_router(),
                   context_line(space.get("pack") or "home", space.get("describe") or ""), changes, people)
    out["design_id"] = ask.design_id
    from app.space.scorecard import scorecard
    out["scores"] = scorecard(space, after, out)
    folder = p.parent / "sims"
    folder.mkdir(exist_ok=True)
    (folder / f"{ask.design_id or 0}.json").write_text(json.dumps(out), encoding="utf-8")
    return out


class RenderAsk(BaseModel):
    room_id: int


@router.post("/{space_id}/designs/{design_id}/render")
def render_room(space_id: str, design_id: int, ask: RenderAsk):
    """Muse Image draws one room of a design. Saved, so each picture is paid for once."""
    from app.space.render import room_prompt

    p = _path(space_id, "map.json")
    dp = _path(space_id, "designs") / f"{int(design_id)}.json"
    if not (p.exists() and dp.exists()):
        raise HTTPException(404, "Design not found")
    space = json.loads(p.read_text(encoding="utf-8"))
    if not any(r["id"] == ask.room_id for r in space["rooms"]):
        raise HTTPException(404, "Room not found")
    out = dp.parent / f"{int(design_id)}_room{int(ask.room_id)}.png"
    url = f"/api/spaces/{space_id}/designs/{int(design_id)}/render/{int(ask.room_id)}"
    meta = out.with_suffix(".json")
    if out.exists() and meta.exists():
        return json.loads(meta.read_text(encoding="utf-8"))
    design = json.loads(dp.read_text(encoding="utf-8"))
    prompt = room_prompt(space, design, ask.room_id)
    router_ = get_router()
    try:
        png = router_.render(prompt)
    except AllProvidersFailed as e:
        raise HTTPException(503, f"Image models are unavailable: {e}")
    out.write_bytes(png)
    who = router_.last_provider or ""
    info = {"url": url, "prompt": prompt,
            "provider": who.replace("meta", "meta-image", 1) if who.startswith("meta") else who}
    meta.write_text(json.dumps(info), encoding="utf-8")
    return info


@router.get("/{space_id}/designs/{design_id}/render/{room_id}")
def get_render(space_id: str, design_id: int, room_id: int):
    out = _path(space_id, "designs") / f"{int(design_id)}_room{int(room_id)}.png"
    if not out.exists():
        raise HTTPException(404, "No picture yet")
    return FileResponse(out, media_type="image/png")


class FamilyAsk(BaseModel):
    text: str


@router.post("/{space_id}/family")
def describe_family(space_id: str, ask: FamilyAsk):
    """Describe the people in words; the model fills them in, code checks them. Used by the next run."""
    from app.space.family import check_people, family_prompt
    from app.space.reader import context_line

    p = _path(space_id, "map.json")
    if not p.exists():
        raise HTTPException(404, "Space not found")
    text = " ".join(ask.text.split())
    if not 3 <= len(text) <= 600:
        raise HTTPException(400, "Describe the people in 3 to 600 characters")
    space = json.loads(p.read_text(encoding="utf-8"))
    router_ = get_router()
    try:
        ans = router_.ask_json(family_prompt(text, space["rooms"],
                                             context_line(space.get("pack") or "home", space.get("describe") or "")))
    except AllProvidersFailed as e:
        raise HTTPException(503, f"Models are unavailable: {e}")
    people, notes = check_people(ans, space["rooms"])
    if not people:
        raise HTTPException(422, "Couldn't make anyone from that description. Try naming each person.")
    out = {"text": text, "people": people, "notes": notes, "provider": router_.last_provider}
    (p.parent / "family.json").write_text(json.dumps(out), encoding="utf-8")
    return out


@router.get("/{space_id}/family")
def get_family(space_id: str):
    fam = _path(space_id, "family.json")
    return json.loads(fam.read_text(encoding="utf-8")) if fam.exists() else None


@router.delete("/{space_id}/family")
def reset_family(space_id: str):
    fam = _path(space_id, "family.json")
    if fam.exists():
        fam.unlink()
    return {"ok": True}


class ImproveAsk(BaseModel):
    budget: float = 1000
    goals: str = ""
    target_safety: int = 80
    rounds: int = 3


# Running improve loops: job id -> {"events": [...], "done": bool}. In memory: one server process.
JOBS: dict[str, dict] = {}


@router.post("/{space_id}/improve")
def improve_design(space_id: str, ask: ImproveAsk):
    """Start the improve loop in the background. Poll GET /improve/{job} for its steps as they happen."""
    import threading

    p = _path(space_id, "map.json")
    if not p.exists():
        raise HTTPException(404, "Space not found")
    if not 50 <= ask.budget <= 100_000 or not 1 <= ask.rounds <= 4 or not 0 <= ask.target_safety <= 100:
        raise HTTPException(400, "Budget $50 to $100,000, 1 to 4 rounds, target 0 to 100")
    job = uuid.uuid4().hex[:12]
    JOBS[job] = {"events": [], "done": False}
    threading.Thread(target=_run_improve, args=(job, space_id, p, ask), daemon=True).start()
    return {"job": job}


@router.get("/{space_id}/improve/{job}")
def improve_progress(space_id: str, job: str, since: int = 0):
    j = JOBS.get(job)
    if j is None:
        raise HTTPException(404, "No such job")
    return {"events": j["events"][since:], "next": len(j["events"]), "done": j["done"]}


def _run_improve(job: str, space_id: str, p: Path, ask: ImproveAsk) -> None:
    from app.space.improve import improve
    from app.space.reader import context_line

    events = JOBS[job]["events"]

    def say(kind: str, **kw):
        events.append({"kind": kind, **kw})

    try:
        space = json.loads(p.read_text(encoding="utf-8"))
        fam = p.parent / "family.json"
        people = json.loads(fam.read_text(encoding="utf-8"))["people"] if fam.exists() else None
        goals = " ".join(ask.goals.split())[:300]
        original = {it["id"]: it for it in space.get("items", [])}
        names = {r["id"]: r["name"] for r in space["rooms"]}
        all_changes, timeline, spent = [], [], 0.0
        say("start", text=f"Aiming for Safety {ask.target_safety} with ${ask.budget:,.0f}"
                          + (f" for {', '.join(x['name'] for x in people)}" if people else ""))
        say("round", round=1, text="Round 1 · designing")
        rounds = improve(space, ask.budget, goals, get_router(), {"safety": ask.target_safety}, ask.rounds,
                         context_line(space.get("pack") or "home", space.get("describe") or ""), people)
        for n, design, sc, sim in rounds:
            spent += design.spent_usd
            for c in design.to_dict()["changes"]:
                all_changes.append(dict(c, round=n))
                where = names.get(c.get("room"), "")
                if c["dropped"]:
                    say("rejected", round=n, text=f"Rejected: {c['name']}{' in ' + where if where else ''}. {c['dropped']}",
                        item=None)
                else:
                    verb = {"add": "Adding", "replace": "Replacing with", "remove": "Removing"}.get(c["action"], c["action"])
                    say("change", round=n, action=c["action"], item=c.get("placed"), replaces=c.get("replaces"),
                        text=f"{verb} {c['name']}{' in ' + where if where else ''}"
                             + (f", ${c['cost_usd']:,.0f}" if c.get("cost_usd") else "")
                             + (f". {c['reason']}" if c.get("reason") else ""))
            items = []
            for it in design.items:
                if it["id"] in original:
                    items.append(dict(it, status=it.get("status") if it.get("status") in ("removed", "replaced") else "kept"))
                elif it.get("status") in ("kept", "new"):
                    items.append(dict(it, status="new"))
            seen = {it["id"] for it in items}
            items += [dict(it, status="removed") for i, it in original.items() if i not in seen]
            saved = _save_design(p.parent / "designs", {
                "goals": goals, "provider": get_router().last_provider, "summary": design.summary,
                "budget_usd": ask.budget, "spent_usd": round(spent, 2), "items": items,
                "changes": list(all_changes), "warnings": design.warnings,
                "kept": sum(1 for c in all_changes if not c["dropped"]), "round": n})
            scores = {k: v["score"] for k, v in sc.items() if isinstance(v, dict) and "score" in v}
            met = scores.get("safety", 0) >= ask.target_safety
            timeline.append({"round": n, "design_id": saved["id"], "spent_usd": round(spent, 2),
                             "added": [c["name"] for c in design.to_dict()["changes"] if not c["dropped"]],
                             "scores": scores, "met": met})
            missing = sc.get("safety", {}).get("why", "").split("Missing: ")
            say("scores", round=n, design_id=saved["id"], scores=scores, met=met, spent_usd=round(spent, 2),
                text=f"Round {n} measured: Safety {scores.get('safety')}, Access {scores.get('access')}, "
                     f"${spent:,.0f} spent" + (" · target met ✓" if met else
                                              (f" · still missing: {missing[1]}" if len(missing) > 1 else "")))
            if not met and n < ask.rounds:
                say("round", round=n + 1, text=f"Round {n + 1} · reading the results and designing again")
        if timeline and not timeline[-1]["met"]:
            say("note", text="Stopped: what's left needs work furniture can't do, like a wider door.")
        say("done", text="Done", rounds=timeline, final_design_id=timeline[-1]["design_id"] if timeline else None)
    except AllProvidersFailed as e:
        say("error", text=f"Models are unavailable: {e}")
    except Exception as e:  # noqa: BLE001  shown to the user instead of a silent hang
        say("error", text=f"Something went wrong: {e}")
    finally:
        JOBS[job]["done"] = True
