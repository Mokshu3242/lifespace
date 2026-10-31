"""Naming spaces: OCR first, then several vision models vote, then a referee for real disagreements.

  1. Printed text (OCR) wins: if a name is printed inside a space, that's its name.
  2. Spaces with no printed name go to every vision model at once, each giving a name and a reason.
  3. If the models agree (or most of them do), that's the name.
  4. If they split with no majority, a text model reads all the answers and reasons and picks one;
     the space is flagged "unsure" so the user knows to check it.
"""
from __future__ import annotations

import logging

import numpy as np

from app.space import ocr
from app.space.reader import (TILES_PER_SHEET, Label, NAME_PROMPT, draw_sheets, parse_dims)

log = logging.getLogger("naming")

REFEREE_PROMPT = """{context}Several vision models named spaces on a floor plan and disagreed about some of them.
For each space below, pick the best name. Weigh the reasons each model gave; a reason that cites
specific furniture or printed text beats a vague one. Size hints: "small" spaces are rarely bedrooms
or living rooms; "large" spaces are rarely closets or bathrooms.
Spaces:
{cases}
Reply as JSON: {{"decisions": [{{"id": 1, "name": "...", "reason": "..."}}]}}"""

SYNONYMS = {"restroom": "bathroom", "toilet": "bathroom", "washroom": "bathroom", "bath": "bathroom",
            "powder room": "bathroom", "hall": "hallway", "corridor": "hallway", "entry": "foyer",
            "conference room": "meeting room", "break room": "lounge", "sitting area": "lounge",
            "storage": "closet", "kitchenette": "kitchen", "bed room": "bedroom"}


def _canon(name: str) -> str:
    n = " ".join(name.lower().replace("-", " ").split())
    return SYNONYMS.get(n, n)


def _same(a: str, b: str) -> bool:
    """'Bedroom' and 'Master Bedroom' agree; 'Bedroom' and 'Office' don't."""
    a, b = _canon(a), _canon(b)
    return a == b or a in b.split() or b in a.split() or a.endswith(" " + b) or b.endswith(" " + a)


def _owner_at(regions: np.ndarray, x: float, y: float) -> int:
    """Which space a piece of text sits in. Text can sit on a line, so look nearby if needed."""
    h, w = regions.shape
    xi, yi = int(round(x)), int(round(y))
    if 0 <= yi < h and 0 <= xi < w and regions[yi, xi] >= 0:
        return int(regions[yi, xi])
    r = max(6, int(0.02 * max(h, w)))
    win = regions[max(0, yi - r):yi + r + 1, max(0, xi - r):xi + r + 1]
    ys, xs = np.nonzero(win >= 0)
    if len(xs) == 0:
        return -1
    j = int(np.argmin((xs - min(r, xi)) ** 2 + (ys - min(r, yi)) ** 2))
    return int(win[ys[j], xs[j]])


def _nearest_label(pieces: list, x: float, y: float, side: int) -> list:
    """One space can hold two separate labels (a tiny closet's "LC" inside the foyer's area).
    Group pieces that sit together (like "MASTER" over "BATHROOM") and keep the group nearest the mark."""
    gap = 0.045 * side
    groups: list[list] = []
    for p in sorted(pieces, key=lambda t: (t.y, t.x)):
        for g in groups:
            if any(abs(p.x - q.x) < gap and abs(p.y - q.y) < gap for q in g):
                g.append(p)
                break
        else:
            groups.append([p])
    return min(groups, key=lambda g: min((q.x - x) ** 2 + (q.y - y) ** 2 for q in g))


def _size_word(regions: np.ndarray, i: int) -> str:
    sizes = np.bincount(regions[regions >= 0].ravel())
    if i >= len(sizes) or sizes.max() == 0:
        return "medium"
    share = sizes[i] / np.median(sizes[sizes > 0])
    return "small" if share < 0.4 else "large" if share > 1.8 else "medium"


def name_spaces(gray: np.ndarray, marks: list[tuple[int, int]], regions: np.ndarray,
                router, context: str = "", texts: list | None = None) -> list[Label]:
    n = len(marks)

    # ---- 1. printed text
    names_by_mark: dict[int, list[ocr.Text]] = {}
    dims_by_mark: dict[int, list[ocr.Text]] = {}
    for t in (texts if texts is not None else ocr.read_texts(gray)):
        i = _owner_at(regions, t.x, t.y)
        if i < 0:
            continue
        (dims_by_mark if t.is_dims else names_by_mark).setdefault(i, []).append(t)

    labels: list[Label] = []
    for i, (x, y) in enumerate(marks):
        dims = ""
        if dims_by_mark.get(i):
            best = max(dims_by_mark[i], key=lambda t: t.conf)
            dims = best.text if parse_dims(best.text) else ""
        if names_by_mark.get(i):
            pieces = _nearest_label(names_by_mark[i], x, y, max(gray.shape))
            labels.append(Label(ocr.name_from_pieces(pieces), dims, x, y,
                                source="printed", note="read from the plan's text"))
        else:
            labels.append(Label("", dims, x, y))

    # ---- 2. models, only for spaces without a printed name
    todo = [i + 1 for i, lb in enumerate(labels) if not lb.name]
    votes: dict[int, list[tuple[str, str, str, str]]] = {k: [] for k in todo}  # model, name, reason, dims
    for png, ids in draw_sheets(gray, marks, regions, only=todo):
        answers = router.see_each(NAME_PROMPT.format(context=context, ids=", ".join(map(str, ids))), png)
        for model, ans in answers.items():
            for t in ans.get("tiles") or []:
                try:
                    k = int(t.get("id"))
                except (TypeError, ValueError, AttributeError):
                    continue
                name = str(t.get("name") or t.get("text") or "").strip()
                if k in votes and name:
                    votes[k].append((model, name.title(), str(t.get("reason") or "").strip(),
                                     str(t.get("dims") or "").strip()))

    # ---- 3. agree or majority
    disputed: dict[int, list[tuple[str, str, str, str]]] = {}
    for k, vs in votes.items():
        lb = labels[k - 1]
        if not vs:
            lb.name, lb.source, lb.unsure = f"Space {k}", "none", True
            continue
        # group answers that mean the same thing
        groups: list[list[tuple[str, str, str, str]]] = []
        for v in vs:
            for g in groups:
                if _same(g[0][1], v[1]):
                    g.append(v)
                    break
            else:
                groups.append([v])
        groups.sort(key=len, reverse=True)
        top = groups[0]
        reasons = "; ".join(f"{m}: {r}" for m, _, r, _ in vs if r)
        if len(vs) == 1:
            lb.name, lb.source, lb.note, lb.unsure = top[0][1], "one model", reasons, True
        elif len(groups) == 1:
            lb.name, lb.source, lb.note = max((v[1] for v in top), key=len), "models agree", reasons
        elif len(top) > len(vs) / 2:
            lb.name, lb.source, lb.note = max((v[1] for v in top), key=len), "majority", reasons
        else:
            disputed[k] = vs
        # a model-read size counts only if 2+ models read the same one
        if not lb.dims:
            parsed = [parse_dims(d) for _, _, _, d in vs if parse_dims(d)]
            if len(parsed) >= 2 and all(p == parsed[0] for p in parsed):
                lb.dims = next(d for _, _, _, d in vs if parse_dims(d))

    # ---- 4. referee for splits
    if disputed:
        cases = "\n".join(
            f"- id {k} ({_size_word(regions, k - 1)} space): " +
            "; ".join(f'{m} says "{nm}" because "{r or "no reason given"}"' for m, nm, r, _ in vs)
            for k, vs in disputed.items())
        try:
            ruling = router.ask_json(REFEREE_PROMPT.format(context=context, cases=cases))
            decided = {int(d["id"]): d for d in ruling.get("decisions") or []
                       if isinstance(d, dict) and str(d.get("id", "")).isdigit()}
        except Exception as e:  # no text model available: fall back to the first model's answer
            log.warning("referee failed: %s", e)
            decided = {}
        for k, vs in disputed.items():
            lb = labels[k - 1]
            d = decided.get(k)
            if d and str(d.get("name") or "").strip():
                lb.name = str(d["name"]).strip().title()
                lb.note = f'referee: {d.get("reason", "")}'.strip()
            else:
                lb.name = vs[0][1]
                lb.note = "models disagreed; kept the first model's answer"
            lb.source, lb.unsure = "referee", True
            lb.note += " | " + "; ".join(f"{m}: {nm} ({r})" for m, nm, r, _ in vs)

    return labels


__all__ = ["name_spaces", "TILES_PER_SHEET"]
