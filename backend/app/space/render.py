"""Picture a redesigned room with Muse Image: a realistic photo of the room with the items it really has.

The picture is built only from facts: the room's name and size, the items kept and the items the
redesign added (real catalog names), and the user's style goal. Nothing is invented on top."""
from app import catalog

PROMPT = ("A realistic interior photo of a {kind} about {w:.0f} by {d:.0f} feet, eye-level wide-angle view, "
          "soft natural daylight{window}. The room contains exactly these real, everyday items: {items}. "
          "{new}Style: {style}. Clean, lived-in and believable, true to scale, nothing extra added. "
          "No people, no text, no labels, no watermark.")


def room_prompt(space: dict, design: dict, room_id: int) -> str:
    pack = space.get("pack") or "home"
    room = next(r for r in space["rooms"] if r["id"] == room_id)
    c0, r0, c1, r1 = room.get("bbox_cells") or (0, 0, 10, 10)
    ft = space["cell_in"] / 12
    w, d = (c1 - c0 + 1) * ft, (r1 - r0 + 1) * ft
    kept, new = [], []
    for it in design.get("items", []):
        if it.get("room") != room_id or it.get("status") not in ("kept", "new"):
            continue
        c = catalog.get(pack, it.get("item", ""))
        name = (c.name if c else it.get("name", "")).lower()
        (new if it.get("status") == "new" else kept).append(name)
    items = ", ".join(sorted(set(kept + new))) or "simple everyday furniture for this room"
    new_txt = f"Newly added: {', '.join(sorted(set(new)))}, placed where people would use them. " if new else ""
    window = " from a window" if room.get("kind") != "bath" else ""
    style = design.get("goals") or "warm, simple and practical"
    return PROMPT.format(kind=room["name"].lower(), w=max(w, d), d=min(w, d), window=window,
                         items=items, new=new_txt, style=style)


RESTYLE = ("Edit this photo of a real {kind}. Keep the room exactly as it is: same walls, windows, doors, floor, "
           "ceiling, camera angle and light. {add}{remove}Style: {style}. Each item true to its real size, placed "
           "where a person would use it, believable and photo-real. Do not add anything else. No people, no text.")


def restyle_prompt(space: dict, design: dict, room_id: int) -> str:
    """Put this design's changes for one room into the user's own photo of it (Muse Image edit)."""
    pack = space.get("pack") or "home"
    room = next(r for r in space["rooms"] if r["id"] == room_id)
    new, gone = [], []
    for it in design.get("items", []):
        if it.get("room") != room_id:
            continue
        c = catalog.get(pack, it.get("item", ""))
        name = (c.name if c else it.get("name", "")).lower()
        if it.get("status") == "new":
            new.append(name)
        elif it.get("status") in ("removed", "replaced"):
            gone.append(name)
    add = f"Add only these real items: {', '.join(sorted(set(new)))}. " if new else ""
    remove = f"Take out: {', '.join(sorted(set(gone)))}. " if gone else ""
    return RESTYLE.format(kind=room["name"].lower(), add=add, remove=remove,
                          style=design.get("goals") or "warm, simple and practical")
