"""Prepare the demo: bring back the saved plans, run each sample's day on its latest designs, and save
the results to Supabase, so judges always open finished, fresh results with no waiting.

Runs in GitHub Actions (7 GB memory, no hurry) or on your laptop:
    python -m scripts.prepare_demo                 # the samples
    python -m scripts.prepare_demo --all           # every saved plan
Needs SUPABASE_URL and SUPABASE_SERVICE_KEY; MODE=prod and META_API_KEY for the people's voices
(saved answers are reused, so a second run costs almost nothing)."""
from __future__ import annotations

import argparse
import json
import logging
import time

from fastapi.testclient import TestClient

from app import storage_sync
from app.config import ROOT

log = logging.getLogger("prepare")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--all", action="store_true", help="every saved home and office plan, not just the samples")
    ap.add_argument("--designs", type=int, default=2, help="latest designs per plan to run (default 2)")
    ap.add_argument("--add", metavar="FOLDER", help="read every image in FOLDER as a new sample (street-*.jpg as streets), save and print the SAMPLES value")
    ap.add_argument("--fresh", action="store_true", help="with --add: read again, ignore saved reads of the same image")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)

    m = storage_sync.mirror()
    if m:
        log.info("restoring saved data from Supabase…")
        log.info("restored %d files", m.restore())
    else:
        log.warning("Supabase not set: using local data only")

    from app.main import app            # after the restore, so it sees every plan
    c = TestClient(app)
    if a.add:
        return add_samples(c, a.add, m, a.fresh)
    if a.all:
        ids = [p.parent.name for p in (ROOT / ".data" / "spaces").glob("*/map.json")]
    else:
        ids = [s["id"] for s in c.get("/api/samples").json() if s["kind"] != "street"]
    t0, done, failed = time.time(), 0, []
    for sid in ids:
        designs = sorted(int(p.stem) for p in (ROOT / ".data" / "spaces" / sid / "designs").glob("*.json") if p.stem.isdigit())
        for d in [None] + designs[-a.designs:]:
            r = c.post(f"/api/spaces/{sid}/simulate", json={"design_id": d})
            if r.status_code == 200:
                done += 1
                sc = r.json().get("scores", {}).get("after", {})
                log.info("%s design %s: safety %s, access %s", sid, d, sc.get("safety", {}).get("score"), sc.get("access", {}).get("score"))
            else:
                failed.append(f"{sid}:{d} {r.status_code} {r.text[:120]}")
                log.warning("%s design %s failed: %s", sid, d, r.text[:200])
    if m:
        log.info("saved %d files to Supabase", m.push_changes())
    summary = {"plans": len(ids), "days_run": done, "failed": failed, "minutes": round((time.time() - t0) / 60, 1)}
    print(json.dumps(summary, indent=2))
    return 1 if failed and not done else 0


def add_samples(c, folder, m, fresh=False) -> int:
    """Read each image like an upload on the site, but here with 7 GB of memory. Prints the SAMPLES value."""
    from pathlib import Path
    files = sorted(p for p in Path(folder).iterdir() if p.suffix.lower() in (".jpg", ".jpeg", ".png"))
    ids, failed = [], []
    for p in files:
        street = p.stem.startswith("street")
        url = "/api/streets" if street else "/api/spaces?pack=home" + ("&fresh=true" if fresh else "")
        mime = "image/png" if p.suffix.lower() == ".png" else "image/jpeg"
        t = time.time()
        r = c.post(url, files={"file": (p.name, p.read_bytes(), mime)})
        if r.status_code == 200:
            j = r.json()
            ids.append(f"{'street' if street else 'home'}:{j['id']}")
            log.info("%s -> %s (%d rooms, %.0fs, %s)", p.name, j["id"], len(j.get("rooms", [])), time.time() - t, j.get("provider"))
        else:
            failed.append(f"{p.name} {r.status_code} {r.text[:150]}")
            log.warning("%s failed: %s", p.name, r.text[:300])
    if m:
        log.info("saved %d files to Supabase", m.push_changes())
    print("\nSAMPLES=" + ",".join(ids))
    if failed:
        print("failed:\n  " + "\n  ".join(failed))
    return 1 if failed and not ids else 0


if __name__ == "__main__":
    raise SystemExit(main())
