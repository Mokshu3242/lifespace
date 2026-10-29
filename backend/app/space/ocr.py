"""Reads the text printed on a floor plan: room names and sizes, with where they sit.

OCR is exact about printed text, so it outranks the vision models whenever a room has a name on it.
Uses RapidOCR (pretrained, models ship inside the package, runs offline on CPU in about a second).
If the library is missing, everything here returns nothing and the models do all the naming.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass

import cv2
import numpy as np

log = logging.getLogger("ocr")

DIMS_RE = re.compile(
    r"\d+\s*['’′]\s*\d*\s*(?:[\"”″]|'')?\s*[x×X]\s*\d+\s*['’′]\s*\d*\s*(?:[\"”″]|'')?")

# Words that show up in room names. Used to put spaces back ("SECONDBEDROOM" -> "SECOND BEDROOM").
VOCAB = sorted({
    "master", "primary", "second", "third", "guest", "kids", "main", "family", "great", "breakfast",
    "living", "dining", "sitting", "bed", "bedroom", "room", "area", "kitchen", "kitchenette", "bath",
    "bathroom", "powder", "half", "full", "closet", "walk", "in", "linen", "coat", "pantry", "laundry",
    "utility", "mud", "foyer", "entry", "hall", "hallway", "corridor", "terrace", "balcony", "patio",
    "deck", "porch", "garage", "office", "study", "den", "library", "media", "storage", "lobby",
    "reception", "waiting", "meeting", "conference", "lounge", "break", "work", "open", "copy",
    "print", "server", "nook", "built", "suite", "dressing", "gym", "play", "nursery",
}, key=len, reverse=True)

ABBREV = {
    "cl": "Closet", "clo": "Closet", "lc": "Linen Closet", "wic": "Walk-In Closet", "wc": "WC",
    "w/d": "Laundry", "br": "Bedroom", "bdrm": "Bedroom", "ba": "Bath", "lr": "Living Room",
    "dr": "Dining Room", "kit": "Kitchen", "pwd": "Powder Room", "pdr": "Powder Room",
}

# Labels that are not room names: appliances, plan notes, compass
NOISE = {"oven", "dw", "ref", "fridge", "w", "d", "n", "s", "e", "up", "dn", "down", "entrance",
         "entry door", "range", "sink", "wd", "w d", "00", "o0", "0o"}

MODIFIERS = {"master", "primary", "second", "third", "guest", "kids", "main", "family", "great",
             "breakfast", "living", "dining", "sitting", "powder", "half", "full", "walk", "linen",
             "coat", "meeting", "conference", "break", "work", "open", "waiting"}


@dataclass
class Text:
    text: str
    x: float
    y: float
    conf: float
    is_dims: bool


_engine = None
_failed = False


def _get_engine():
    global _engine, _failed
    if _engine is None and not _failed:
        try:
            from rapidocr_onnxruntime import RapidOCR
            _engine = RapidOCR()
        except Exception as e:  # missing package or model files
            log.warning("OCR not available, models will name every room: %s", e)
            _failed = True
    return _engine


def split_words(token: str) -> str:
    """Put spaces back into run-together words using room vocabulary. Unknown parts stay as they are."""
    t = token.lower()
    out, i = [], 0
    while i < len(t):
        for w in VOCAB:
            if t.startswith(w, i):
                out.append(w)
                i += len(w)
                break
        else:
            # no known word starts here: keep the rest as one piece
            out.append(t[i:])
            break
    return " ".join(out)


def _ocr(img: np.ndarray) -> list[tuple[str, float, float, float]]:
    eng = _get_engine()
    if eng is None:
        return []
    try:
        result, _ = eng(img)
    except Exception as e:
        log.warning("OCR failed: %s", e)
        return []
    out = []
    for box, txt, conf in result or []:
        pts = np.array(box, float)
        out.append((str(txt), float(pts[:, 0].mean()), float(pts[:, 1].mean()), float(conf)))
    return out


def read_texts(gray: np.ndarray, min_conf: float = 0.6) -> list[Text]:
    """All text on the plan, upright and sideways, in the image's own pixel coordinates."""
    h0, w0 = gray.shape
    # small labels (WC, LC, CL) need more pixels than the working image has: read a 2x copy
    up = max(1.0, 2400 / max(h0, w0))
    big = cv2.resize(gray, (int(w0 * up), int(h0 * up)), interpolation=cv2.INTER_CUBIC) if up > 1 else gray
    h, w = big.shape
    img = cv2.cvtColor(big, cv2.COLOR_GRAY2BGR)
    found = _ocr(img)
    # sideways labels (KITCHEN, CL written vertically): read the image turned both ways
    for rot, back in ((cv2.ROTATE_90_CLOCKWISE, lambda x, y: (y, h - 1 - x)),
                      (cv2.ROTATE_90_COUNTERCLOCKWISE, lambda x, y: (w - 1 - y, x))):
        for txt, x, y, c in _ocr(cv2.rotate(img, rot)):
            bx, by = back(x, y)
            found.append((txt, bx, by, c))

    found = [(t, x / up, y / up, c) for t, x, y, c in found]   # back to working-image pixels
    h, w = h0, w0
    texts: list[Text] = []
    for txt, x, y, c in sorted(found, key=lambda t: -t[3]):
        if c < min_conf:
            continue
        # the same label read in two orientations: keep the more confident one
        if any(abs(x - t.x) < 0.02 * w and abs(y - t.y) < 0.02 * h for t in texts):
            continue
        dims = DIMS_RE.search(txt)
        if dims:
            texts.append(Text(dims.group(0), x, y, c, True))
            rest = (txt[:dims.start()] + " " + txt[dims.end():]).strip(" :.-")
            if rest:
                texts.append(Text(rest, x, y, c, False))   # e.g. "CL2'11" x 6'11""
        else:
            texts.append(Text(txt.strip(" :.-"), x, y, c, False))
    return [t for t in texts if t.is_dims or _is_name(t.text)]


def _is_name(txt: str) -> bool:
    t = txt.lower().strip()
    if t in NOISE or len(re.sub(r"[^a-z]", "", t)) < 2:
        return False
    if "illustration" in t or "purposes" in t or "scale" in t or "approx" in t:
        return False
    return True


def name_from_pieces(pieces: list[Text]) -> str:
    """Join the name pieces found in one room: expand abbreviations, put spaces back,
    and put modifiers first ("BATHROOM" + "MASTER" -> "Master Bathroom")."""
    words: list[str] = []
    for p in sorted(pieces, key=lambda t: (t.y, t.x)):
        raw = p.text.strip()
        key = raw.lower().replace(".", "")
        if key in ABBREV:
            words.extend(ABBREV[key].split())
            continue
        for chunk in re.split(r"\s+", raw):
            words.extend(split_words(re.sub(r"[^A-Za-z/]", "", chunk)).split())
    words = [w for w in words if w]
    seen, uniq = set(), []
    for w in words:
        if w.lower() not in seen:
            seen.add(w.lower())
            uniq.append(w)
    uniq.sort(key=lambda w: 0 if w.lower() in MODIFIERS else 1)
    name = " ".join(uniq).title().replace("Wc", "WC").replace("Built In", "Built-In")
    return name.replace("Walk In", "Walk-In")
