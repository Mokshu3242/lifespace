"""Test SAM 3.1 on a floor plan: can it find furniture in line drawings?

    cd backend
    python -m scripts.sam_test path/to/plan.png

Needs META_API_KEY in .env. Costs about $0.0025 per word asked (10 words = 2.5 cents).
Writes <plan>_sam.png next to the plan with a box around everything SAM found.
"""
import base64
import re
import sys
import time
from pathlib import Path

import cv2
import httpx

from app.config import get_settings

WORDS = ["bed", "sofa", "chair", "dining table", "desk", "toilet", "bathtub", "sink", "stove", "door"]
BOX_RE = re.compile(r"<\|box;x1=(\d+);y1=(\d+);x2=(\d+);y2=(\d+);w=(\d+);h=(\d+)(?:;c=([\d.]+))?\|>")
COLORS = [(220, 40, 40), (40, 160, 40), (40, 40, 220), (200, 120, 0), (160, 0, 160),
          (0, 150, 150), (120, 80, 20), (90, 90, 90), (230, 0, 120), (0, 100, 230)]


def ask_sam(png: bytes, word: str, key: str, base: str) -> tuple[list[tuple], str]:
    body = {
        "model": "sam-3.1",
        "input": [{"type": "message", "role": "user", "content": [
            {"type": "input_text", "text": word},
            {"type": "input_image", "image_url": "data:image/png;base64," + base64.b64encode(png).decode()},
        ]}],
        "metadata": {"include_confidence": "true", "mask_encoding": "one_bit"},
    }
    r = httpx.post(f"{base.rstrip('/')}/responses", json=body,
                   headers={"Authorization": f"Bearer {key}"}, timeout=120)
    if r.status_code >= 400:
        return [], f"HTTP {r.status_code}: {r.text[:300]}"
    data = r.json()
    # collect every text piece in the response, whatever the exact shape
    texts = []

    def walk(x):
        if isinstance(x, dict):
            if isinstance(x.get("text"), str):
                texts.append(x["text"])
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)
    walk(data.get("output", data))
    text = "".join(texts)
    boxes = [(int(a), int(b), int(c), int(d), float(conf) if conf else None)
             for a, b, c, d, _, _, conf in BOX_RE.findall(text)]
    return boxes, text[:200]


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    s = get_settings()
    if not s.meta_api_key:
        print("No META_API_KEY in .env")
        return
    path = Path(sys.argv[1])
    img = cv2.imread(str(path))
    if img is None:
        print("Can't read", path)
        return
    ok, buf = cv2.imencode(".png", img)
    png = buf.tobytes()
    out = img.copy()
    total = 0
    for i, word in enumerate(WORDS):
        t0 = time.time()
        boxes, raw = ask_sam(png, word, s.meta_api_key, s.meta_base_url)
        total += len(boxes)
        confs = [round(b[4], 2) for b in boxes if b[4] is not None]
        print(f"{word:13s} {len(boxes):2d} found  {time.time() - t0:4.1f}s  confidence {confs}")
        if not boxes and raw:
            print("              raw:", raw.replace("\n", " ")[:160])
        for x1, y1, x2, y2, conf in boxes:
            color = COLORS[i % len(COLORS)]
            cv2.rectangle(out, (x1, y1), (x2, y2), color, 2)
            cv2.putText(out, word, (x1, max(12, y1 - 4)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)
    dest = path.with_name(path.stem + "_sam.png")
    cv2.imwrite(str(dest), out)
    print(f"\n{total} things found. Picture with boxes: {dest}")


if __name__ == "__main__":
    main()
