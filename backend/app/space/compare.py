"""Apartment chooser: the same people live the same day in two or three plans. Code measures each one;
Muse Spark only explains the pick, from the measured facts."""
from __future__ import annotations

import logging

from app.space.scorecard import score_side
from app.space.simulate import load_personas, simulate

log = logging.getLogger("compare")

# a trip that can't be made to one of these is a deal-breaker, not an inconvenience
MUST = {"wash": "the bathroom", "sleep": "their bed", "enter": "the front door", "exit": "the front door",
        "cook": "the kitchen", "eat": "a place to eat"}
WEIGHTS = {"access": 0.35, "movement": 0.35, "safety": 0.2, "energy": 0.1}
DEAL_BREAKER = 15     # points off per person who can't reach a must-have

VERDICT_PROMPT = """{context}A family is choosing between {n} homes. The same people lived the same day in each one;
everything below was measured on the floor plans by code.
{people}
{plans}
Code ranked plan {pick} first. In plain words, explain why plan {pick} fits these people best, and what each
plan gets wrong for them. Only use the facts above. Name people and rooms. No numbers you weren't given.
Reply as JSON: {{"why": "2 or 3 sentences", "plans": [{{"plan": 1, "good": "a few words", "bad": "a few words"}}]}}"""


def measure(space: dict, people: list[dict], items: list[dict] | None = None, label: str = "") -> dict:
    """items: a redesign's items (None = the plan as it is)."""
    pack = space.get("pack") or "home"
    items = items if items is not None else space.get("items", [])
    sim = simulate(space, items, None, "", [], people)
    side = "after"
    scores = score_side(space, items, sim[side], pack)
    sim["before"] = sim[side]
    persons = []
    breakers = []
    for p in people:
        d = sim["before"][p["id"]]
        blocked = [lg for lg in d["legs"] if lg["blocked"]]
        must = sorted({MUST[lg["use"]] for lg in blocked if lg["use"] in MUST})
        if must:
            breakers.append(f"{p['name']} can't reach {', '.join(must)}")
        persons.append({"id": p["id"], "name": p["name"], "walked_ft": round(d["walked_ft"]),
                        "tight_ft": round(d["tight_ft"]), "blocked": len(blocked),
                        "blocked_notes": [f"{lg['t']} {lg['note']}" for lg in blocked][:4], "must": must})
    points = sum(scores[k]["score"] * w for k, w in WEIGHTS.items()) - DEAL_BREAKER * len(breakers)
    return {"id": space["id"], "label": label, "describe": space.get("describe") or "", "pack": pack,
            "size_ft": [space.get("width_ft"), space.get("height_ft")],
            "rooms": len([r for r in space["rooms"] if r.get("kind") != "closet"]),
            "scores": {k: scores[k] for k in ("safety", "access", "movement", "energy")},
            "flags": scores.get("flags", [])[:5], "people": persons, "deal_breakers": breakers,
            "points": round(points, 1)}


def compare(spaces: list[dict], people: list[dict] | None, router=None, context: str = "",
            options: list[tuple[list[dict] | None, str]] | None = None) -> dict:
    """spaces[i] is lived in as it is, or with options[i] = (a redesign's items, its label)."""
    people = people or load_personas(spaces[0].get("pack") or "home")
    options = options or [(None, "") for _ in spaces]
    plans = [measure(s, people, it, lb) for s, (it, lb) in zip(spaces, options)]
    order = sorted(range(len(plans)), key=lambda i: -plans[i]["points"])
    for rank, i in enumerate(order, 1):
        plans[i]["rank"] = rank
    pick = order[0] + 1
    out = {"people": [{k: p[k] for k in ("id", "name", "about", "width_in", "color")} for p in people],
           "plans": plans, "pick": pick, "why": "", "notes": []}
    if router is not None:
        ppl = "People: " + "; ".join(f"{p['name']} ({p['about']}, needs {p['width_in']} in to pass)" for p in people)
        lines = []
        for k, pl in enumerate(plans, 1):
            who = "; ".join(f"{x['name']} walks {x['walked_ft']} ft, {x['blocked']} trips blocked"
                            + (f" ({', '.join(x['blocked_notes'][:2])})" if x["blocked_notes"] else "") for x in pl["people"])
            lines.append(f"Plan {k}{' (' + pl['label'] + ')' if pl['label'] else ''}: {pl['rooms']} rooms; safety {pl['scores']['safety']['score']}, access "
                         f"{pl['scores']['access']['score']}, movement {pl['scores']['movement']['score']}. "
                         f"Deal-breakers: {'; '.join(pl['deal_breakers']) or 'none'}. {who}. "
                         f"Can't fix with furniture: {'; '.join(pl['flags'][:3]) or 'nothing'}.")
        try:
            ans = router.ask_json(VERDICT_PROMPT.format(context=context, n=len(plans), people=ppl,
                                                        plans="\n".join(lines), pick=pick))
            out["why"] = str(ans.get("why") or "")[:500]
            for row in ans.get("plans") or []:
                try:
                    k = int(row.get("plan")) - 1
                except (TypeError, ValueError):
                    continue
                if 0 <= k < len(plans):
                    plans[k]["good"] = str(row.get("good") or "")[:120]
                    plans[k]["bad"] = str(row.get("bad") or "")[:120]
            out["provider"] = getattr(router, "last_provider", None)
        except Exception as e:     # the ranking stands without the words
            log.warning("verdict failed: %s", e)
    return out
