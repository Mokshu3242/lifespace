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


def _clean(space: dict) -> dict:
    """Spaces saved before duplicates were merged: merge them when loading."""
    from app.space.items import dedupe
    if space.get("items"):
        space["items"] = dedupe(space["items"])
    # saved before the door finder set the entrance: use the front door
    if not space.get("entrance") and space.get("doors"):
        front = [d for d in space["doors"] if d.get("outside")]
        if front:
            import numpy as np
            d = min(front, key=lambda d: abs(d["width_in"] - 34))
            g = np.array(space["grid"])
            ys, xs = np.nonzero(g >= 0)
            if len(ys):
                j = int(np.argmin((ys - d["y"]) ** 2 + (xs - d["x"]) ** 2))
                space["entrance"] = [int(xs[j]), int(ys[j])]
    # a tiny sliver with the same name as a bigger room (two "Kitchen"s) is part of that room
    rooms = space.get("rooms") or []
    if rooms and space.get("grid"):
        import cv2
        import numpy as np
        g = np.array(space["grid"])
        ft2 = (space.get("cell_in", 6) / 12) ** 2
        size = {r["id"]: int((g == r["id"]).sum()) for r in rooms}
        drop, moved = set(), {}
        for r in rooms:
            twins = [o for o in rooms if o is not r and o["name"].lower() == r["name"].lower() and o["id"] not in drop]
            if twins and size[r["id"]] * ft2 < 12:
                big = max(twins, key=lambda o: size[o["id"]])
                if size[big["id"]] > size[r["id"]]:
                    g[g == r["id"]] = big["id"]
                    drop.add(r["id"])
                    moved[r["id"]] = big["id"]
        # slivers under 4 sq ft (a gap between two fills, a hatched floor) join the room they touch most
        for r in rooms:
            if r["id"] in drop or size[r["id"]] * ft2 >= 4:
                continue
            m = g == r["id"]
            # look up to 3 cells out: slivers are often walled off by a thin line or a drawn item
            ring = cv2.dilate(m.astype(np.uint8), np.ones((7, 7), np.uint8)).astype(bool) & ~m
            near = [int(v) for v in g[ring] if v >= 0 and v not in drop and v != r["id"]]
            if near:
                to = max(set(near), key=near.count)
                g[m] = to
                size[to] += size[r["id"]]
                drop.add(r["id"])
                moved[r["id"]] = to
        if drop:
            space["rooms"] = [r for r in rooms if r["id"] not in drop]
            space["grid"] = g.tolist()
            for it in space.get("items") or []:
                if it.get("room") in moved:
                    it["room"] = moved[it["room"]]
    return space
MAX_BYTES = 15 * 1024 * 1024
ID_RE = re.compile(r"^[a-f0-9]{12}$")


def _path(space_id: str, name: str) -> Path:
    if not ID_RE.match(space_id):
        raise HTTPException(400, "Bad space id")
    return STORE / space_id / name


def _find_read(sha: str, pack: str, describe: str) -> dict | None:
    """The newest saved space made from exactly this picture, or None."""
    import hashlib
    best = None
    for mp in STORE.glob("*/map.json"):
        try:
            m = json.loads(mp.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if (m.get("pack") or "home") != pack or (m.get("describe") or "") != describe:
            continue
        h = m.get("image_sha")
        if h is None:
            img = mp.parent / "plan.img"
            h = hashlib.sha256(img.read_bytes()).hexdigest() if img.exists() else ""
        if h == sha and (best is None or mp.stat().st_mtime > best[0]):
            best = (mp.stat().st_mtime, m)
    return _clean(best[1]) if best else None


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
    import hashlib
    sha = hashlib.sha256(data).hexdigest()
    if not fresh:
        # the same picture was read before (same type and description): open that read, no model calls
        old = _find_read(sha, pack, describe)
        if old is not None:
            return {**old, "reused": True}
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
           "pack": pack, "describe": describe, "image_sha": sha, **smap.to_dict()}
    (folder / "map.json").write_text(json.dumps(out), encoding="utf-8")
    return out


@router.get("")
def list_spaces():
    """Saved plans grouped by layout (the same image uploaded again is one layout), newest first,
    each with every redesign made on any of its reads."""
    import hashlib
    groups: dict[str, dict] = {}
    for f in sorted(STORE.glob("*/map.json"), key=lambda f: f.stat().st_mtime, reverse=True)[:200]:
        try:
            s = json.loads(f.read_text(encoding="utf-8"))
            img = f.parent / "plan.img"
            key = hashlib.sha256(img.read_bytes()).hexdigest()[:16] if img.exists() else s["id"]
        except (OSError, ValueError, KeyError):
            continue
        g = groups.get(key)
        if g is None:
            g = groups[key] = {"id": s["id"], "pack": s.get("pack") or "home", "describe": s.get("describe") or "",
                               "size_ft": [s.get("width_ft"), s.get("height_ft")],
                               "rooms": [r["name"] for r in s.get("rooms", []) if r.get("kind") != "closet"][:8],
                               "reads": 0, "designs": []}
        g["reads"] += 1
        # only design files ("1.json"); room pictures sit next to them as "1_room10.json"
        for d in sorted((x for x in (f.parent / "designs").glob("*.json") if x.stem.isdigit()), key=lambda x: int(x.stem)):
            try:
                dj = json.loads(d.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            kept = [c for c in dj.get("changes", []) if not c.get("dropped")]
            g["designs"].append({"ref": f"{s['id']}:{d.stem}", "n": int(d.stem), "summary": (dj.get("summary") or "")[:90],
                                 "spent_usd": dj.get("spent_usd", 0), "budget_usd": dj.get("budget_usd", 0),
                                 "changes": len(kept), "goals": (dj.get("goals") or "")[:60]})
    out = list(groups.values())
    for g in out:
        # the same redesign saved on several reads shows once; number them 1, 2, 3 across the layout
        seen, uniq = set(), []
        for d in g["designs"]:
            key = (d["summary"], round(d["spent_usd"]), d["changes"])
            if key not in seen:
                seen.add(key)
                uniq.append(d)
        g["designs"] = uniq[-8:]                  # the latest few redesigns of this layout
        for k, d in enumerate(g["designs"], 1):
            d["label"] = k
    return out[:24]


class CompareAsk(BaseModel):
    ids: list[str]
    family: str = ""


@router.post("/compare")
def compare_plans(ask: CompareAsk):
    """The same people live the same day in 2 or 3 plans; code ranks them, Muse Spark explains why."""
    from app.space.compare import compare
    from app.space.family import check_people, family_prompt
    from app.space.reader import context_line

    refs = list(dict.fromkeys(ask.ids))          # "id" = the plan as it is, "id:n" = its redesign n
    if not 2 <= len(refs) <= 3:
        raise HTTPException(400, "Pick 2 or 3 options")
    spaces, options = [], []
    for ref in refs:
        sid, _, n = ref.partition(":")
        p = _path(sid, "map.json")
        if not p.exists():
            raise HTTPException(404, f"Plan {sid} not found")
        spaces.append(_clean(json.loads(p.read_text(encoding="utf-8"))))
        if n:
            dp = _path(sid, "designs") / f"{int(n)}.json"
            if not dp.exists():
                raise HTTPException(404, f"Design {n} of plan {sid} not found")
            d = json.loads(dp.read_text(encoding="utf-8"))
            options.append((d["items"], f"redesign {n}: ${d.get('spent_usd', 0):,.0f}"))
        else:
            options.append((None, "as it is"))
    ids = [r.partition(":")[0] for r in refs]
    if len({s.get("pack") or "home" for s in spaces}) > 1:
        raise HTTPException(400, "Compare homes with homes, offices with offices")
    ctx = context_line(spaces[0].get("pack") or "home", "")
    people = None
    text = " ".join(ask.family.split())
    router_ = get_router()
    try:
        if text:
            ans = router_.ask_json(family_prompt(text, spaces[0]["rooms"], ctx))
            people, _ = check_people(ans, spaces[0]["rooms"])
        else:
            fam = _path(ids[0], "family.json")
            people = json.loads(fam.read_text(encoding="utf-8"))["people"] if fam.exists() else None
        return compare(spaces, people, router_, ctx, options)
    except AllProvidersFailed as e:
        raise HTTPException(503, f"Models are unavailable: {e}")


@router.get("/{space_id}")
def get_space(space_id: str):
    p = _path(space_id, "map.json")
    if not p.exists():
        raise HTTPException(404, "Space not found")
    return _clean(json.loads(p.read_text(encoding="utf-8")))


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
    doors: list[dict] | None = None


class DoctorAsk(BaseModel):
    instruction: str = ""
    use_ai: bool = True
    fixes: list[dict] | None = None      # given: only apply these (preview), no model call


@router.get("/lessons/stats")
def lesson_stats(pack: str = "home"):
    """How many fixes LifeSpace has learned from so far."""
    from app.space import lessons
    return lessons.stats(pack)


@router.post("/{space_id}/doctor")
def plan_doctor(space_id: str, ask: DoctorAsk):
    """AI plan check: code lists problems, Muse Spark proposes fixes (or follows an instruction), code
    applies them to a copy. Returns the preview; nothing is saved until the editor saves the map."""
    from app.space.plandoctor import apply, ai_fixes, check
    from app.space.reader import context_line

    p = _path(space_id, "map.json")
    if not p.exists():
        raise HTTPException(404, "Space not found")
    space = _clean(json.loads(p.read_text(encoding="utf-8")))
    issues = check(space)
    from app.space import lessons as _lessons
    out = {"issues": issues, "summary": "", "provider": None,
           "learned_from": _lessons.stats(space.get("pack") or "home")["count"]}
    if ask.fixes is not None:
        fixes = ask.fixes
        # the person chose these fixes: save them as lessons for later plans
        from app.space import lessons
        names = {r["id"]: r["name"] for r in space["rooms"]}
        for f in fixes:
            if f.get("action") == "rename" and f.get("room") in names:
                lessons.record(space.get("pack") or "home", "rename", names[f["room"]], f.get("name", ""), f.get("why", ""), "plan check")
            elif f.get("action") == "merge" and f.get("room") in names and f.get("into") in names:
                lessons.record(space.get("pack") or "home", "merge", names[f["room"]], names[f["into"]], f.get("why", ""), "plan check")
    else:
        fixes = [i["fix"] for i in issues if i.get("fix") and i["kind"] != "narrow_door"]
        if ask.use_ai or ask.instruction.strip():
            img = p.parent / "plan.img"
            try:
                ai = ai_fixes(space, img.read_bytes() if img.exists() else None, issues, ask.instruction,
                              get_router(), context_line(space.get("pack") or "home", space.get("describe") or ""))
            except AllProvidersFailed as e:
                raise HTTPException(503, f"Models are unavailable: {e}")
            out.update(summary=ai["summary"], provider=ai["provider"])
            seen = {json.dumps(f, sort_keys=True) for f in fixes}
            fixes += [f for f in ai["fixes"] if json.dumps(f, sort_keys=True) not in seen]
    new, log = apply(space, fixes)
    out.update(fixes=log, preview={k: new[k] for k in ("grid", "rooms", "entrance", "doors", "items") if k in new})
    return out


@router.put("/{space_id}")
def save_space(space_id: str, edit: MapEdit):
    """Save hand fixes from the editor (painted cells, renamed rooms, moved entrance)."""
    p = _path(space_id, "map.json")
    if not p.exists():
        raise HTTPException(404, "Space not found")
    current = json.loads(p.read_text(encoding="utf-8"))
    if len(edit.grid) != current["rows"] or any(len(r) != current["cols"] for r in edit.grid):
        raise HTTPException(400, "Grid size changed; that isn't allowed")
    # renames and item swaps made by hand are lessons too
    from app.space import lessons
    pack = current.get("pack") or "home"
    old_names = {r["id"]: r["name"] for r in current.get("rooms", [])}
    for r in edit.rooms:
        was = old_names.get(r.get("id"))
        if was and r.get("source") == "you":
            lessons.record(pack, "rename", was, r.get("name", ""), "renamed by hand")
    if edit.items is not None:
        old_items = {it.get("id"): it for it in current.get("items", [])}
        for it in edit.items:
            o = old_items.get(it.get("id"))
            if o and it.get("source") == "you" and o.get("item") != it.get("item"):
                lessons.record(pack, "item", o.get("name") or o.get("item", ""), it.get("name") or it.get("item", ""), "changed by hand")
    current.update(grid=edit.grid, rooms=edit.rooms, entrance=edit.entrance, edited=True)
    if edit.doors is not None:
        current["doors"] = edit.doors
    if edit.items is not None:
        current["items"] = edit.items
    p.write_text(json.dumps(current), encoding="utf-8")
    return current


class RedesignAsk(BaseModel):
    budget: float = 1000
    goals: str = ""
    style: str = "small"     # "small": many small fixes, "big": fewer, bigger upgrades


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
    space = _clean(json.loads(p.read_text(encoding="utf-8")))
    goals = " ".join(ask.goals.split())[:300]
    try:
        design = redesign(space, ask.budget, goals, get_router(),
                          context_line(space.get("pack") or "home", space.get("describe") or ""),
                          style="big" if ask.style == "big" else "small")
    except AllProvidersFailed as e:
        raise HTTPException(503, f"Models are unavailable: {e}")
    return _save_design(p.parent / "designs",
                        {"goals": goals, "style": ask.style if ask.style in ("small", "big") else "small", "provider": get_router().last_provider, **design.to_dict()})


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
    space = _clean(json.loads(p.read_text(encoding="utf-8")))
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
    from app.space.extras import time_saved
    from app.space.simulate import load_personas as _lp
    out["time_saved"] = time_saved(out, people or list(_lp(space.get("pack") or "home")))
    from app.space.scorecard import scorecard
    out["scores"] = scorecard(space, after, out)
    folder = p.parent / "sims"
    folder.mkdir(exist_ok=True)
    (folder / f"{ask.design_id or 0}.json").write_text(json.dumps(out), encoding="utf-8")
    return out


class FutureAsk(BaseModel):
    years: int = 5
    design_id: int | None = None


class Question(BaseModel):
    question: str
    design_id: int | None = None


@router.post("/{space_id}/ask")
def ask_space(space_id: str, q: Question):
    """Ask LifeSpace: answered only from facts measured on the plan."""
    from app.space.ask import ask
    from app.space.reader import context_line

    if not q.question.strip():
        raise HTTPException(400, "Ask a question")
    p = _path(space_id, "map.json")
    if not p.exists():
        raise HTTPException(404, "Space not found")
    space = _clean(json.loads(p.read_text(encoding="utf-8")))
    items = None
    if q.design_id is not None:
        dp = _path(space_id, "designs") / f"{int(q.design_id)}.json"
        if not dp.exists():
            raise HTTPException(404, "Design not found")
        items = json.loads(dp.read_text(encoding="utf-8"))["items"]
    fam = p.parent / "family.json"
    people = json.loads(fam.read_text(encoding="utf-8"))["people"] if fam.exists() else None
    try:
        return ask(space, q.question, items, people, get_router(),
                   context_line(space.get("pack") or "home", space.get("describe") or ""))
    except AllProvidersFailed as e:
        raise HTTPException(503, f"Models are unavailable: {e}")


class DrillAsk(BaseModel):
    design_id: int | None = None


@router.post("/{space_id}/firedrill")
def drill(space_id: str, ask: DrillAsk):
    """Fire drill at night: how long each person takes to get out, Before and After. Code only."""
    from app.space.firedrill import fire_drill

    p = _path(space_id, "map.json")
    if not p.exists():
        raise HTTPException(404, "Space not found")
    space = _clean(json.loads(p.read_text(encoding="utf-8")))
    items = None
    if ask.design_id is not None:
        dp = _path(space_id, "designs") / f"{int(ask.design_id)}.json"
        if not dp.exists():
            raise HTTPException(404, "Design not found")
        items = json.loads(dp.read_text(encoding="utf-8"))["items"]
    fam = p.parent / "family.json"
    people = json.loads(fam.read_text(encoding="utf-8"))["people"] if fam.exists() else None
    return fire_drill(space, people, items)


@router.post("/{space_id}/future")
def in_years(space_id: str, ask: FutureAsk):
    """The same people, older, in the same home (or a redesign of it): what stops working."""
    from app.space.future import future
    from app.space.reader import context_line
    from app.space.simulate import load_personas

    if not 1 <= ask.years <= 30:
        raise HTTPException(400, "Pick 1 to 30 years")
    p = _path(space_id, "map.json")
    if not p.exists():
        raise HTTPException(404, "Space not found")
    space = _clean(json.loads(p.read_text(encoding="utf-8")))
    items = None
    if ask.design_id is not None:
        dp = _path(space_id, "designs") / f"{int(ask.design_id)}.json"
        if not dp.exists():
            raise HTTPException(404, "Design not found")
        items = json.loads(dp.read_text(encoding="utf-8"))["items"]
    fam = p.parent / "family.json"
    people = json.loads(fam.read_text(encoding="utf-8"))["people"] if fam.exists() else load_personas(space.get("pack") or "home")
    try:
        return future(space, people, items, ask.years, get_router(),
                      context_line(space.get("pack") or "home", space.get("describe") or ""))
    except AllProvidersFailed as e:
        raise HTTPException(503, f"Models are unavailable: {e}")


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
    space = _clean(json.loads(p.read_text(encoding="utf-8")))
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


@router.post("/{space_id}/designs/{design_id}/restyle")
async def restyle_photo(space_id: str, design_id: int, room_id: int = Query(...), file: UploadFile = File(...)):
    """Muse Image edit: put this design's changes for one room into the user's own photo of that room."""
    from app.space.render import restyle_prompt

    p = _path(space_id, "map.json")
    dp = _path(space_id, "designs") / f"{int(design_id)}.json"
    if not (p.exists() and dp.exists()):
        raise HTTPException(404, "Design not found")
    data = await file.read()
    if len(data) > MAX_BYTES:
        raise HTTPException(413, "Photo is too big (15 MB max)")
    if not (data[:3] == b"\xff\xd8\xff" or data[:8] == b"\x89PNG\r\n\x1a\n"):
        raise HTTPException(400, "Use a JPG or PNG photo")
    space = _clean(json.loads(p.read_text(encoding="utf-8")))
    if not any(r["id"] == room_id for r in space["rooms"]):
        raise HTTPException(404, "Room not found")
    design = json.loads(dp.read_text(encoding="utf-8"))
    prompt = restyle_prompt(space, design, room_id)
    router_ = get_router()
    try:
        png = router_.render(prompt, data)
    except AllProvidersFailed as e:
        raise HTTPException(503, f"Image models are unavailable: {e}")
    stem = f"{int(design_id)}_photo{int(room_id)}"
    (dp.parent / f"{stem}_before.img").write_bytes(data)
    (dp.parent / f"{stem}.png").write_bytes(png)
    base = f"/api/spaces/{space_id}/designs/{int(design_id)}/photo/{int(room_id)}"
    who = router_.last_provider or ""
    return {"before": base + "?which=before", "after": base, "prompt": prompt,
            "provider": who.replace("meta", "meta-image", 1) if who.startswith("meta") else who}


@router.get("/{space_id}/designs/{design_id}/photo/{room_id}")
def get_photo(space_id: str, design_id: int, room_id: int, which: str = "after"):
    stem = f"{int(design_id)}_photo{int(room_id)}"
    out = _path(space_id, "designs") / (f"{stem}_before.img" if which == "before" else f"{stem}.png")
    if not out.exists():
        raise HTTPException(404, "No photo yet")
    return FileResponse(out, media_type="image/jpeg" if which == "before" and out.read_bytes()[:2] == b"\xff\xd8" else "image/png")


class TalkAsk(BaseModel):
    person_id: str
    message: str
    history: list[dict] = []
    design_id: int | None = None


@router.post("/{space_id}/talk")
def talk_to(space_id: str, ask: TalkAsk):
    """Talk to one person about their day; they answer only from what was measured."""
    from app.space.reader import context_line
    from app.space.talk import talk

    if not ask.message.strip():
        raise HTTPException(400, "Say something")
    p = _path(space_id, "map.json")
    if not p.exists():
        raise HTTPException(404, "Space not found")
    space = _clean(json.loads(p.read_text(encoding="utf-8")))
    items, changes = None, []
    if ask.design_id is not None:
        dp = _path(space_id, "designs") / f"{int(ask.design_id)}.json"
        if not dp.exists():
            raise HTTPException(404, "Design not found")
        d = json.loads(dp.read_text(encoding="utf-8"))
        items, changes = d["items"], d.get("changes", [])
    fam = p.parent / "family.json"
    people = json.loads(fam.read_text(encoding="utf-8"))["people"] if fam.exists() else None
    try:
        return talk(space, ask.person_id, ask.message, ask.history, items, people, changes, get_router(),
                    context_line(space.get("pack") or "home", space.get("describe") or ""))
    except KeyError:
        raise HTTPException(404, "No such person")
    except AllProvidersFailed as e:
        raise HTTPException(503, f"Models are unavailable: {e}")


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
    space = _clean(json.loads(p.read_text(encoding="utf-8")))
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


class VisitorAsk(BaseModel):
    kind: str


@router.post("/{space_id}/family/add")
def add_person(space_id: str, ask: VisitorAsk):
    """Add a dog, a caregiver, a delivery or a toddler to the household (preset sizes and days)."""
    from app.space.extras import VISITORS, add_visitor
    from app.space.simulate import load_personas

    if ask.kind not in VISITORS:
        raise HTTPException(400, f"Pick one of: {', '.join(VISITORS)}")
    p = _path(space_id, "map.json")
    if not p.exists():
        raise HTTPException(404, "Space not found")
    space = _clean(json.loads(p.read_text(encoding="utf-8")))
    fam_p = p.parent / "family.json"
    fam = json.loads(fam_p.read_text(encoding="utf-8")) if fam_p.exists() else None
    if fam and len(fam["people"]) >= 8:
        raise HTTPException(400, "That's a full house (8 people max)")
    out = add_visitor(fam, list(load_personas(space.get("pack") or "home")), ask.kind, space["rooms"])
    fam_p.write_text(json.dumps(out), encoding="utf-8")
    return out


class ComicAsk(BaseModel):
    person_id: str
    design_id: int


@router.post("/{space_id}/comic")
def comic(space_id: str, ask: ComicAsk):
    """Muse Image draws a 4-panel comic of one person's day, Before and After, from the measured day."""
    from app.space.extras import comic_prompt
    from app.space.simulate import load_personas, simulate

    p = _path(space_id, "map.json")
    dp = _path(space_id, "designs") / f"{int(ask.design_id)}.json"
    if not (p.exists() and dp.exists()):
        raise HTTPException(404, "Design not found")
    out = dp.parent / f"{int(ask.design_id)}_comic_{re.sub(r'[^a-z0-9]', '', ask.person_id.lower())[:20]}.png"
    url = f"/api/spaces/{space_id}/comic/{out.name}"
    space = _clean(json.loads(p.read_text(encoding="utf-8")))
    d = json.loads(dp.read_text(encoding="utf-8"))
    fam = p.parent / "family.json"
    people = json.loads(fam.read_text(encoding="utf-8"))["people"] if fam.exists() else list(load_personas(space.get("pack") or "home"))
    me = next((x for x in people if x["id"] == ask.person_id), None)
    if me is None:
        raise HTTPException(404, "No such person")
    sim = simulate(space, d["items"], None, "", [], people)
    prompt = comic_prompt(me, sim["before"][me["id"]], sim["after"][me["id"]], d.get("changes", []),
                          "office" if space.get("pack") == "office" else "apartment")
    if not out.exists():
        router_ = get_router()
        try:
            out.write_bytes(router_.render(prompt))
        except AllProvidersFailed as e:
            raise HTTPException(503, f"Image models are unavailable: {e}")
        who = router_.last_provider or ""
    else:
        who = "meta (saved)"
    return {"url": url, "prompt": prompt, "provider": who.replace("meta", "meta-image", 1) if who.startswith("meta") else who}


@router.get("/{space_id}/comic/{name}")
def get_comic(space_id: str, name: str):
    if not re.fullmatch(r"\d+_comic_[a-z0-9]+\.png", name):
        raise HTTPException(400, "Bad name")
    out = _path(space_id, "designs") / name
    if not out.exists():
        raise HTTPException(404, "No comic yet")
    return FileResponse(out, media_type="image/png")


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
        space = _clean(json.loads(p.read_text(encoding="utf-8")))
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
            for t in design.thoughts:
                say("thought", round=n, text=f"Thinking: {t}")
            for c in design.to_dict()["changes"]:
                all_changes.append(dict(c, round=n))
                where = names.get(c.get("room"), "")
                if c["dropped"]:
                    say("rejected", round=n, text=f"Rejected: {c['name']}{' in ' + where if where else ''}. {c['dropped']}",
                        item=None, tries=c.get("tries", []))
                else:
                    verb = {"add": "Adding", "replace": "Replacing with", "remove": "Removing"}.get(c["action"], c["action"])
                    if c.get("swapped_from"):
                        say("swap", round=n, text=f"Won't fit: {c['swapped_from']} → trying {c['name']}")
                    say("change", round=n, action=c["action"], item=c.get("placed"), replaces=c.get("replaces"),
                        delivery=c.get("delivery", []), tries=c.get("tries", []), carry=c.get("carry", ""),
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
