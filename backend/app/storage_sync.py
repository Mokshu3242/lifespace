"""Mirror the local data folders to Supabase Storage, so a restart or redeploy loses nothing.

The app keeps reading and writing plain files (.data and .cache). This module:
  - on startup, downloads every saved file that isn't on disk yet;
  - every few seconds, uploads files that are new or changed.
No Supabase settings: it does nothing, and the app works on local disk as before."""
from __future__ import annotations

import logging
import threading
import time
from pathlib import Path

import httpx

from app.config import ROOT, get_settings

log = logging.getLogger("sync")
FOLDERS = [".data", ".cache"]
EVERY_S = 8


class Mirror:
    def __init__(self, url: str, key: str, bucket: str):
        self.base = url.rstrip("/") + "/storage/v1"
        self.bucket = bucket
        self.h = {"Authorization": f"Bearer {key}", "apikey": key}
        self.client = httpx.Client(timeout=60)
        self.seen: dict[str, float] = {}

    def _list(self, prefix: str) -> list[str]:
        """Every object path under prefix (Storage lists one folder at a time)."""
        out, todo = [], [prefix]
        while todo:
            folder = todo.pop()
            offset = 0
            while True:
                r = self.client.post(f"{self.base}/object/list/{self.bucket}", headers=self.h,
                                     json={"prefix": folder, "limit": 1000, "offset": offset})
                r.raise_for_status()
                rows = r.json()
                for row in rows:
                    path = f"{folder}/{row['name']}" if folder else row["name"]
                    (out if row.get("id") else todo).append(path)     # no id: it's a folder
                if len(rows) < 1000:
                    break
                offset += 1000
        return out

    def restore(self) -> int:
        n = 0
        for top in FOLDERS:
            try:
                names = self._list(top)
            except httpx.HTTPError as e:
                log.warning("restore list %s failed: %s", top, e)
                continue
            for name in names:
                dest = ROOT / name
                if dest.exists():
                    continue
                r = self.client.get(f"{self.base}/object/{self.bucket}/{name}", headers=self.h)
                if r.status_code == 200:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(r.content)
                    self.seen[name] = dest.stat().st_mtime
                    n += 1
        return n

    def push_changes(self) -> int:
        n = 0
        for top in FOLDERS:
            base = ROOT / top
            if not base.exists():
                continue
            for f in base.rglob("*"):
                if not f.is_file():
                    continue
                name = f.relative_to(ROOT).as_posix()
                m = f.stat().st_mtime
                if self.seen.get(name) == m:
                    continue
                try:
                    r = self.client.post(f"{self.base}/object/{self.bucket}/{name}",
                                         headers={**self.h, "x-upsert": "true",
                                                  "Content-Type": "application/octet-stream"},
                                         content=f.read_bytes())
                    if r.status_code < 300:
                        self.seen[name] = m
                        n += 1
                    else:
                        log.warning("upload %s: %s %s", name, r.status_code, r.text[:200])
                except httpx.HTTPError as e:
                    log.warning("upload %s failed: %s", name, e)
        return n

    def loop(self):
        while True:
            time.sleep(EVERY_S)
            try:
                self.push_changes()
            except Exception as e:          # never let the sync thread die
                log.warning("sync round failed: %s", e)


def start() -> bool:
    s = get_settings()
    if not (s.supabase_url and s.supabase_service_key):
        log.info("Supabase not set: data stays on local disk")
        return False
    m = Mirror(s.supabase_url, s.supabase_service_key, s.supabase_bucket)
    got = m.restore()
    m.push_changes()                       # files made before the first sync go up now
    log.info("Supabase: restored %d files, syncing every %ds", got, EVERY_S)
    threading.Thread(target=m.loop, daemon=True, name="supabase-sync").start()
    return True
