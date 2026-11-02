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
                "item": f'an item read as "{a}" was changed to "{b}"'}.get(kind, f"{a} → {b}")
        out.append(f"- {verb} ({k} time{'s' if k > 1 else ''})")
    return out


def stats(pack: str | None = None) -> dict:
    rows = load(pack)
    return {"count": len(rows), "kinds": dict(Counter(r.get("kind") for r in rows))}
