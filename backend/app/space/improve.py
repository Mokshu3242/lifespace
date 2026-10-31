"""Self-improving redesign: design → live the day → score → tell the model what's still wrong → design again.

Each round builds on the last: the items from the previous round become the starting point,
and only the money left can be spent. The model sees the real scores, what's missing, who
couldn't get where, and which of its ideas the checks rejected and why. It stops when the
target is met, when a round adds nothing, or after the last round."""
from app.space.redesign import redesign
from app.space.scorecard import scorecard
from app.space.simulate import simulate

STRUCTURAL = "can reach a"      # "a walker can reach a bathroom": needs a wider door, not furniture

FEEDBACK = """
Round {n} results, measured by code on the plan:
{scores}
Still missing: {missing}
Trips people couldn't make: {blocked}
Your ideas the checks rejected last round: {rejected}
Things furniture can't fix (don't try; a door or wall would need work): {flags}
Already in the space now (don't add these again): {have}
Target: {target}. Spend only the money left (${left:.0f}). Suggest only changes that move the scores."""


def _summary(sc: dict) -> str:
    return "; ".join(f"{k.capitalize()} {v['score']}" for k, v in sc.items()
                     if isinstance(v, dict) and "score" in v)


def improve(space: dict, budget: float, goals: str, router, target: dict, rounds: int = 3,
            context: str = "", people: list[dict] | None = None):
    """Yields (round number, design, scorecard side, sim) for each round."""
    target = {k: int(v) for k, v in (target or {"safety": 80}).items()}
    base = dict(space, items=[dict(it, status="kept") for it in space.get("items", [])])
    left = float(budget)
    extra = ""
    first_items = space.get("items", [])
    last_score = -1
    for n in range(1, max(1, min(rounds, 4)) + 1):
        design = redesign(base, left, (goals + extra).strip(), router, context)
        kept = [c for c in design.changes if not c.dropped]
        sim = simulate(space, design.items, None, context, people=people)
        # score against the ORIGINAL space, so Before always means the plan as it started
        before_space = dict(space, items=first_items)
        sc = scorecard(before_space, design.items, sim)["after"]
        yield n, design, sc, sim
        met = all(sc.get(k, {}).get("score", 0) >= v for k, v in target.items())
        left -= design.spent_usd
        score = sum(sc.get(k, {}).get("score", 0) for k in target)
        why = sc.get("safety", {}).get("why", "")
        missing_now = [m.strip() for m in why.split("Missing: ")[1].split(",")] if "Missing: " in why else []
        only_structural = bool(missing_now) and all(STRUCTURAL in m for m in missing_now)
        if met or not kept or left < 15 or only_structural or (n > 1 and score <= last_score):
            return              # target met, nothing added, money gone, only door work left, or no progress
        last_score = score
        blocked = sorted({f"{p}: {lg['note']} ({lg['why']})" for p, d in sim["after"].items()
                          for lg in d["legs"] if lg["blocked"]})
        missing = [sc[k]["why"].split("Missing: ")[1] for k in ("safety",) if "Missing: " in sc.get(k, {}).get("why", "")]
        have = sorted({it.get("name", "") for it in design.items if it.get("status") in ("kept", "new")})
        extra = FEEDBACK.format(
            n=n, scores=_summary(sc), missing="; ".join(missing) or "nothing",
            blocked="; ".join(blocked) or "none",
            rejected="; ".join(f"{c.name}: {c.dropped}" for c in design.changes if c.dropped) or "none",
            flags="; ".join(sc.get("flags", [])) or "none", have=", ".join(have) or "nothing",
            target=", ".join(f"{k.capitalize()} {v}+" for k, v in target.items()), left=left)
        # the next round starts from this round's result
        base = dict(space, items=[dict(it, status="kept") for it in design.items
                                  if it.get("status") in ("kept", "new")])
