"""In 5 years: the same people, older, in the same home. Who needs more room, and what stops working?

How people change is a rule of thumb, shown to the user as an assumption, never as a prediction about
a real person: a walker often becomes a wheelchair by the late 70s, a cane a walker, someone over 75 may
start using a cane, and a child grows to adult width. Everything after that is measured, the same way as
today: the same day, the same paths, the same scorecard."""
from __future__ import annotations

import logging
import re

from app.space.family import CHILD_WIDTH_IN, WIDTH_IN
from app.space.scorecard import score_side
from app.space.simulate import simulate

log = logging.getLogger("future")

VOICE_PROMPT = """{context}The same family, {years} years from now, in the same home. Everything below was measured.
{people}
For each person write ONE short sentence in their own voice about the home {years} years from now, from these facts
only. Name a room. No numbers you weren't given.
Reply as JSON: {{"voices": {{"<id>": "..."}}}}"""


def _age_and_aid(p: dict) -> tuple[int, str]:
    age = p.get("age")
    if not isinstance(age, (int, float)):
        m = re.match(r"\s*(\d{1,3})", p.get("about") or "")
        age = int(m.group(1)) if m else 40
    mob = p.get("mobility")
    if not mob:
        m = re.search(r"uses an? ([a-z ]+?)(,|$)", p.get("about") or "")
        mob = m.group(1).strip() if m and m.group(1).strip() in WIDTH_IN else "none"
    return int(age), mob


def age_person(p: dict, years: int) -> tuple[dict, str]:
    """The person `years` from now, and what changed (a plain-words assumption, or "")."""
    age, mob = _age_and_aid(p)
    new_age, new_mob, why = age + years, mob, ""
    if mob in ("walker", "rollator") and new_age >= 75:
        new_mob, why = "wheelchair", "walker → wheelchair (common by the late 70s)"
    elif mob == "cane":
        new_mob, why = "walker", "cane → walker"
    elif mob == "crutches":
        new_mob, why = "none", "off crutches"
    elif mob == "none" and new_age >= 75 and age < 75:
        new_mob, why = "cane", "starts using a cane"
    if mob == "none" and age < 13:
        width = WIDTH_IN["none"] if new_age >= 13 else CHILD_WIDTH_IN + 1
        if new_age >= 13:
            why = "grown to adult size"
    else:
        width = WIDTH_IN.get(new_mob, p["width_in"])
    about = re.sub(r"^\s*\d{1,3}", str(new_age), p.get("about") or "", count=1)
    if new_mob != mob:
        about = re.sub(rf"uses an? {re.escape(mob)}", f"uses a {new_mob}", about) if mob != "none" \
            else f"{about}, uses a {new_mob}"
    return ({**p, "age": new_age, "mobility": new_mob, "width_in": width, "about": about}, why)


def future(space: dict, people: list[dict], items: list[dict] | None, years: int = 5,
           router=None, context: str = "") -> dict:
    pack = space.get("pack") or "home"
    items = items if items is not None else space.get("items", [])
    later, changes = [], {}
    for p in people:
        q, why = age_person(p, years)
        later.append(q)
        if why:
            changes[p["id"]] = why
    now = simulate(space, items, None, "", [], people)["after"]
    then = simulate(space, items, None, "", [], later)["after"]
    def widest(group):
        w = max(group, key=lambda q: q["width_in"])
        mob = w.get("mobility") or _age_and_aid(w)[1]
        return (mob if mob != "none" else "person", w["width_in"])
    body_now, body = widest(people), widest(later)        # access is checked for the widest person each time
    scores_now = score_side(space, items, now, pack, body_now)
    scores_then = score_side(space, items, then, pack, body)
    breaks = []
    for p, q in zip(people, later):
        a, b = now[p["id"]], then[q["id"]]
        newly = [lg for la, lg in zip(a["legs"], b["legs"]) if lg["blocked"] and not la["blocked"]]
        for lg in newly:
            breaks.append({"person": q["name"], "t": lg["t"], "note": lg["note"], "why": lg["why"]})
    still = []
    for p, q in zip(people, later):
        for la, lg in zip(now[p["id"]]["legs"], then[q["id"]]["legs"]):
            if la["blocked"] and lg["blocked"]:
                s = f"{q['name']}: {lg['note']}"
                if s not in still:
                    still.append(s)
    out = {"years": years, "still": still,
           "people": [{"id": q["id"], "name": q["name"], "about": q["about"], "width_in": q["width_in"],
                       "was_width_in": p["width_in"], "color": q["color"], "change": changes.get(p["id"], ""),
                       "now": {"walked_ft": round(now[p["id"]]["walked_ft"]), "blocked": now[p["id"]]["blocked"]},
                       "then": {"walked_ft": round(then[q["id"]]["walked_ft"]), "blocked": then[q["id"]]["blocked"]}}
                      for p, q in zip(people, later)],
           "breaks": breaks, "days": then, "body": {"name": body[0], "width_in": body[1]},
           "body_now": {"name": body_now[0], "width_in": body_now[1]},
           "scores": {"now": scores_now, "then": scores_then}, "voices": {},
           "note": "How people change is a rule of thumb, not a prediction about anyone. Everything after is measured."}
    if router is not None:
        lines = [f"- {x['id']} ({x['name']}, {x['about']}{'; ' + x['change'] if x['change'] else ''}): now walks "
                 f"{x['now']['walked_ft']} ft with {x['now']['blocked']} trips blocked; then {x['then']['walked_ft']} ft "
                 f"with {x['then']['blocked']} blocked. Newly blocked: "
                 + ("; ".join(f"{b['t']} {b['note']} ({b['why']})" for b in breaks if b["person"] == x["name"]) or "nothing")
                 for x in out["people"]]
        try:
            ans = router.ask_json(VOICE_PROMPT.format(context=context, years=years, people="\n".join(lines)))
            v = ans.get("voices") or {}
            out["voices"] = {x["id"]: str(v.get(x["id"]) or "")[:160] for x in out["people"]}
            out["provider"] = getattr(router, "last_provider", None)
        except Exception as e:
            log.warning("future voices failed: %s", e)
    return out
