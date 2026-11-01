"""Ask LifeSpace: a plain question ("Can my dad live here safely?") answered only from measured facts.
Code gathers the facts (rooms, doors, scores, each person's day, the fire drill); Muse Spark only reads
them and answers, naming the facts it used. If the facts don't cover it, it says so."""
from __future__ import annotations

import logging

from app.space.firedrill import fire_drill
from app.space.scorecard import scorecard
from app.space.simulate import load_personas, simulate

log = logging.getLogger(__name__)

ASK_PROMPT = """You answer questions about one home or workspace for the people who live or work there.
{context}
Use ONLY the numbered facts below. They were measured on the floor plan by code. Do not guess sizes,
prices or anything not in the facts. If the facts don't answer the question, say what is not measured
and what the person could check. Short, plain words, like talking to a friend. No medical, legal or
fire safety advice: you can say what the plan shows.

Facts:
{facts}

Question: {question}

Return JSON: {{"answer": "2 to 5 short sentences", "facts": [numbers of the facts you used],
"verdict": "yes" | "no" | "partly" | "not measured"}}"""


def gather_facts(space: dict, items: list[dict] | None, people: list[dict] | None) -> list[str]:
    pack = space.get("pack") or "home"
    people = people or list(load_personas(pack))
    ft2 = (space["cell_in"] / 12) ** 2
    facts = []
    for r in space.get("rooms", []):
        n = sum(row.count(r["id"]) for row in space["grid"])
        facts.append(f"Room: {r['name']} ({r.get('kind', 'room')}), about {n * ft2:.0f} sq ft")
    for d in space.get("doors") or []:
        names = [next((r["name"] for r in space["rooms"] if r["id"] == i), "?") for i in d.get("rooms", [])]
        where = " to ".join(names) + (" to outside" if d.get("outside") else "")
        facts.append(f"Doorway {where}: {d.get('width_in')} in wide{'' if d.get('has_door', True) else ', open (no door leaf)'}")
    active = [it for it in (items if items is not None else space.get("items", []))
              if it.get("status", "kept") in ("kept", "new")]
    by_room: dict[str, list[str]] = {}
    for it in active:
        rn = next((r["name"] for r in space["rooms"] if r["id"] == it.get("room")), "somewhere")
        by_room.setdefault(rn, []).append(it.get("name") or it.get("item", ""))
    for rn, names in by_room.items():
        facts.append(f"In the {rn}: {', '.join(names[:14])}")
    sim = simulate(space, items, None, "", [], people)
    card = scorecard(space, items, sim)["after"]
    for k in ("safety", "access", "movement", "energy"):
        if k in card:
            facts.append(f"{k.title()} score {card[k]['score']}/100: {card[k].get('why', '')}")
    for f in card.get("flags", []):
        facts.append(f"Flag: {f}")
    for p in people:
        day = sim["after"][p["id"]]
        blocked = [f"{lg['t']} {lg['note']} ({lg['why']})" for lg in day["legs"] if lg["blocked"]]
        facts.append(f"{p['name']} ({p['about']}, needs {p['width_in']} in to pass): walks {day['walked_ft']:.0f} ft a day, "
                     f"{day['tight_ft']:.0f} ft of tight squeezes, "
                     + (f"can't make: {'; '.join(blocked)}" if blocked else "every trip works"))
    drill = fire_drill(space, people, items)
    for r in drill["people"]:
        a = r["after"]
        facts.append(f"Fire drill at night: {r['name']} " + (f"gets out in {a['seconds']} s ({a['from']} to {a['exit']})"
                     if a["out"] else f"can't get out alone: {a['why']}"))
    return [f"{i + 1}. {f}" for i, f in enumerate(facts)]


def ask(space: dict, question: str, items: list[dict] | None, people: list[dict] | None,
        router, context: str = "") -> dict:
    facts = gather_facts(space, items, people)
    ans = router.ask_json(ASK_PROMPT.format(context=context, facts="\n".join(facts), question=question[:400]))
    used = [int(n) for n in (ans.get("facts") or []) if str(n).isdigit() and 1 <= int(n) <= len(facts)]
    return {"question": question, "answer": str(ans.get("answer") or "").strip(),
            "verdict": ans.get("verdict") if ans.get("verdict") in ("yes", "no", "partly", "not measured") else "partly",
            "facts": [facts[n - 1].split(". ", 1)[1] for n in used[:8]],
            "provider": getattr(router, "last_provider", None)}
