"""Lessons: every plan fix a person accepts is saved, and later plans learn from it.

A lesson is a small record: the kind of plan, what was wrong ("Wic" read as a room name), what it was
fixed to ("WC"), and why. Lessons live in .data/lessons.jsonl, which is mirrored to Supabase with the
rest of the saved data, so they survive restarts and grow over time. Only fixes are saved, never what
people type about their family.

They are used two ways:
  - code: a room whose name matches a past rename gets that fix suggested straight away (no model call);
  - Muse Spark: the most common past fixes are shown to it as examples in the AI plan check.
"""
from __future__ import annotations

import json
import time
from collections import Counter

from app.config import ROOT

FILE = ROOT / ".data" / "lessons.jsonl"
MAX_LINES = 5000


def _norm(name: str) -> str:
    return " ".join((name or "").lower().split())


def record(pack: str, kind: str, before: str, after: str, why: str = "", source: str = "you") -> bool:
    """Save one accepted fix. Ignores empty or no-op changes."""
    before, after = (before or "").strip()[:60], (after or "").strip()[:60]
    if not before or not after or _norm(before) == _norm(after):
        return False
    FILE.parent.mkdir(parents=True, exist_ok=True)
    row = {"t": int(time.time()), "pack": pack or "home", "kind": kind, "from": before, "to": after,
           "why": (why or "")[:160], "source": source}
    with FILE.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    return True


def load(pack: str | None = None) -> list[dict]:
    if not FILE.exists():
        return []
    rows = []
    for line in FILE.read_text(encoding="utf-8").splitlines()[-MAX_LINES:]:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if pack is None or r.get("pack") == pack:
            rows.append(r)
    return rows


def renames(pack: str) -> dict[str, tuple[str, int]]:
    """Learned room renames: read-as name → (most common fix, how many times people made it)."""
    votes: dict[str, Counter] = {}
    for r in load(pack):
        if r.get("kind") == "rename":
            votes.setdefault(_norm(r["from"]), Counter())[r["to"]] += 1
    return {k: c.most_common(1)[0] for k, c in votes.items()}


def examples(pack: str, n: int = 8) -> list[str]:
    """The most common past fixes, as short lines for the model's prompt."""
    c = Counter((r["kind"], r["from"], r["to"]) for r in load(pack))
    out = []
    for (kind, a, b), k in c.most_common(n):
        verb = {"rename": f'a room read as "{a}" was renamed "{b}"', "merge": f'a small piece "{a}" was merged into "{b}"',
                "item": f'an item read as "{a}" was changed to "{b}"',
                "split": f'"{a}" was really two rooms: a piece was split off as "{b}"',
                "add_item": f'a "{b}" drawn in a {a} was missing from the map and added'}.get(kind, f"{a} → {b}")
        out.append(f"- {verb} ({k} time{'s' if k > 1 else ''})")
    return out


def stats(pack: str | None = None) -> dict:
    rows = load(pack)
    return {"count": len(rows), "kinds": dict(Counter(r.get("kind") for r in rows))}


# ---------------------------------------------------------------------------------------------------
# Redesign outcomes: every time people live a day in a redesign, code measures what changed. The
# redesign, its kept and refused ideas and the measured score changes are saved, so the next redesign
# can see what actually helped before and which ideas code had to refuse. One row per design (the
# latest run wins), so running the same day again doesn't count twice. No family details are saved.

OUTCOMES = ROOT / ".data" / "outcomes.jsonl"
SCORES = ("safety", "access", "movement", "energy")


def _kind_of_room(space: dict, rid) -> str:
    r = next((r for r in space.get("rooms", []) if r["id"] == rid), None)
    if r is None:
        return "?"
    from app.space.reader import kind_of
    k = kind_of(r["name"])
    return {"room": "bedroom" if "bed" in r["name"].lower() else "room"}.get(k, k)


def record_outcome(space: dict, space_id: str, design_id: int, design: dict, scores: dict) -> bool:
    """Save what one measured redesign did. Returns False when there is nothing to learn from."""
    changes = design.get("changes") or []
    b, a = scores.get("before") or {}, scores.get("after") or {}
    gain = {k: int(a.get(k, {}).get("score", 0)) - int(b.get(k, {}).get("score", 0)) for k in SCORES
            if k in a and k in b}
    kept = [{"item": c["item"], "room": _kind_of_room(space, c.get("room"))}
            for c in changes if c.get("item") and not c.get("dropped") and c.get("action") in ("add", "replace")]
    dropped = [{"item": c["item"], "room": _kind_of_room(space, c.get("room")), "why": str(c["dropped"])[:90]}
               for c in changes if c.get("item") and c.get("dropped")]
    if not kept and not dropped:
        return False
    OUTCOMES.parent.mkdir(parents=True, exist_ok=True)
    row = {"t": int(time.time()), "pack": space.get("pack") or "home", "key": f"{space_id}:{design_id}",
           "goals": str(design.get("goals") or "")[:80], "kept": kept, "dropped": dropped, "gain": gain}
    with OUTCOMES.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row) + "\n")
    return True


def outcomes(pack: str | None = None) -> list[dict]:
    """The latest measured run of each design."""
    if not OUTCOMES.exists():
        return []
    latest: dict[str, dict] = {}
    for line in OUTCOMES.read_text(encoding="utf-8").splitlines()[-MAX_LINES:]:
        try:
            r = json.loads(line)
        except ValueError:
            continue
        if not (isinstance(r, dict) and isinstance(r.get("kept"), list) and isinstance(r.get("dropped"), list)
                and isinstance(r.get("gain"), dict)):
            continue                     # a damaged line must never break a redesign
        if pack is None or r.get("pack") == pack:
            latest[r.get("key", "")] = r
    return list(latest.values())


def what_worked(pack: str, n: int = 8) -> list[str]:
    """Items that were in measured redesigns, with the average score change of those redesigns."""
    from app import catalog
    seen: dict[str, list[dict]] = {}
    for o in outcomes(pack):
        for it in {k["item"] for k in o["kept"]}:
            seen.setdefault(it, []).append(o["gain"])
    rows = []
    for it, gains in seen.items():
        avg = {k: sum(g.get(k, 0) for g in gains) / len(gains) for k in SCORES}
        best = max(avg, key=lambda k: avg[k])
        c = catalog.get(pack, it)
        name = c.name if c else it
        moved = ", ".join(f"{k} {v:+.0f}" for k, v in avg.items() if abs(v) >= 1) or "no score change"
        rows.append((len(gains), avg[best],
                     f"- {it} ({name}): in {len(gains)} measured redesign{'s' if len(gains) > 1 else ''}; those redesigns: {moved}"))
    rows.sort(key=lambda r: (-r[0], -r[1]))
    return [r[2] for r in rows[:n]]


def refused(pack: str, n: int = 6) -> list[str]:
    """Ideas code had to refuse before, most common first (so the model stops suggesting them)."""
    c = Counter((d["item"], d["room"], d["why"]) for o in outcomes(pack) for d in o["dropped"])
    return [f"- {it} in a {room}: {why} ({k} time{'s' if k > 1 else ''})" for (it, room, why), k in c.most_common(n)]


def outcome_stats(pack: str | None = None) -> dict:
    rows = outcomes(pack)
    return {"designs": len(rows), "ideas_refused": sum(len(o["dropped"]) for o in rows)}
