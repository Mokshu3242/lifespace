"""Talk to the people: ask Asha about her day. She answers in her own voice, only from her measured day
(the trips she made, where she squeezed, what she couldn't reach) and the changes in the rooms she uses."""
from __future__ import annotations

from app.space.firedrill import fire_drill
from app.space.simulate import load_personas, simulate

TALK_PROMPT = """You are {name}, {about}. You live in this {place} and you just lived one ordinary day in it.
{context}
Speak as {name} in the first person, warm and plain, 1 to 3 short sentences, like talking to family.
Use ONLY these facts about your day. They were measured on the floor plan. If asked about something not in
the facts, say you didn't notice or don't know. Never invent rooms, items, prices or numbers.

Your day:
{facts}

The conversation so far:
{history}
They ask: {message}

Return JSON: {{"reply": "what you say"}}"""


def person_facts(space: dict, items: list[dict] | None, people: list[dict], pid: str, changes: list[dict]) -> list[str]:
    sim = simulate(space, items, None, "", [], people)
    me = next(p for p in people if p["id"] == pid)
    day = sim["after"][pid]
    facts = [f"You need about {me['width_in']} in of space to get through a doorway or past furniture.",
             f"You walked {day['walked_ft']:.0f} ft today, {day['tight_ft']:.0f} ft of it squeezing past things."]
    rooms_used = set()
    for lg in day["legs"]:
        where = lg.get("room") or "somewhere"
        rooms_used.add(where)
        if lg["blocked"]:
            facts.append(f"{lg['t']} {lg['note']}: you couldn't do it ({lg['why']}).")
        else:
            tight = f", squeezing for {lg['tight_ft']:.0f} ft" if lg["tight_ft"] else ""
            facts.append(f"{lg['t']} {lg['note']} in the {where.lower()}: {lg['ft']:.0f} ft{tight}.")
    for c in changes or []:
        room = c.get("room_name") or next((r["name"] for r in space["rooms"] if r["id"] == c.get("room")), "")
        if room and room in rooms_used:
            facts.append(f"New in the {room.lower()}: {c.get('action', 'add')} {c.get('name') or c.get('item')}"
                         + (f" ({c['reason']})" if c.get("reason") else ""))
    drill = next(r for r in fire_drill(space, people, items)["people"] if r["id"] == pid)["after"]
    facts.append(f"In a night fire drill you would get out in {drill['seconds']} seconds." if drill["out"]
                 else f"In a night fire drill you couldn't get out alone ({drill['why']}).")
    return facts


def talk(space: dict, pid: str, message: str, history: list[dict], items: list[dict] | None,
         people: list[dict] | None, changes: list[dict], router, context: str = "") -> dict:
    people = people or list(load_personas(space.get("pack") or "home"))
    me = next((p for p in people if p["id"] == pid), None)
    if me is None:
        raise KeyError(pid)
    facts = person_facts(space, items, people, pid, changes)
    hist = "\n".join(f"{'They' if h.get('who') == 'you' else me['name']}: {h.get('text', '')[:300]}"
                      for h in (history or [])[-6:]) or "(nothing yet)"
    place = "workplace" if space.get("pack") == "office" else "home"
    ans = router.ask_json(TALK_PROMPT.format(name=me["name"], about=me["about"], place=place, context=context,
                                             facts="\n".join(f"- {f}" for f in facts), history=hist,
                                             message=message[:400]))
    return {"reply": str(ans.get("reply") or "").strip()[:500] or "I'm not sure.",
            "name": me["name"], "color": me.get("color"), "provider": getattr(router, "last_provider", None)}
