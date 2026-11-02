"""Clean up storage: remove saved AI answers (.cache) not touched for N days, so Supabase's free 1 GB
and Render's disk stay small. Plans, designs, pictures and lessons (.data) are never removed.

    python -m scripts.cleanup_storage --days 14            # report and delete
    python -m scripts.cleanup_storage --days 14 --dry-run  # report only"""
from __future__ import annotations

import argparse
import datetime as dt
import json

from app import storage_sync


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    m = storage_sync.mirror()
    if m is None:
        print("SUPABASE_URL and SUPABASE_SERVICE_KEY are needed")
        return 1
    totals = {}
    for top in (".data", ".cache"):
        rows: list = []
        m._list(top, rows)
        totals[top] = rows
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=a.days)

    def old(ts: str) -> bool:
        try:
            return dt.datetime.fromisoformat(ts.replace("Z", "+00:00")) < cutoff
        except ValueError:
            return False
    stale = [p for p, _, ts in totals[".cache"] if old(ts)]
    mb = lambda rows: round(sum(r[1] for r in rows) / 1e6, 1)
    report = {"plans_and_designs": {"files": len(totals[".data"]), "MB": mb(totals[".data"])},
              "saved_ai_answers": {"files": len(totals[".cache"]), "MB": mb(totals[".cache"])},
              f"answers_older_than_{a.days}_days": len(stale), "dry_run": a.dry_run}
    if stale and not a.dry_run:
        report["deleted"] = m.delete(stale)
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
