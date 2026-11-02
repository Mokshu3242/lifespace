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
        # new-style secret keys (sb_secret_...) go only in the apikey header; Supabase turns them into a
        # service token. Legacy service_role keys (a JWT) also work as a Bearer token.
        self.h = {"apikey": key} if key.startswith("sb_") else {"Authorization": f"Bearer {key}", "apikey": key}
        self.client = httpx.Client(timeout=60, limits=httpx.Limits(max_connections=20))
        self.seen: dict[str, float] = {}

    def _list(self, prefix: str, rows_out: list | None = None) -> list[str]:
        """Every object path under prefix (Storage lists one folder at a time). With rows_out, also
        collects (path, size in bytes, last updated ISO time) for each object."""
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
                    if row.get("id") and rows_out is not None:
                        meta = row.get("metadata") or {}
                        rows_out.append((path, int(meta.get("size") or 0), row.get("updated_at") or row.get("created_at") or ""))
                if len(rows) < 1000:
                    break
                offset += 1000
        return out

    def restore(self) -> int:
        """Download every saved file that isn't on disk yet, 16 at a time (plans first, then answers)."""
        from concurrent.futures import ThreadPoolExecutor
        n = 0
        for top in FOLDERS:
            try:
                names = [x for x in self._list(top) if not (ROOT / x).exists()]
            except httpx.HTTPError as e:
                log.warning("restore list %s failed: %s", top, e)
                continue

            def one(name):
                try:
                    r = self.client.get(f"{self.base}/object/{self.bucket}/{name}", headers=self.h)
                except httpx.HTTPError:
                    return 0
                if r.status_code != 200:
                    return 0
                dest = ROOT / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                tmp = dest.with_name(dest.name + ".part")
                tmp.write_bytes(r.content)
                tmp.replace(dest)                         # never a half-written file
                self.seen[name] = dest.stat().st_mtime
                return 1
            with ThreadPoolExecutor(max_workers=16) as pool:
                n += sum(pool.map(one, names))
            log.info("Supabase: restored %s (%d files)", top, len(names))
        return n

    def delete(self, paths: list[str]) -> int:
        """Remove objects from the bucket, 100 at a time."""
        n = 0
        for i in range(0, len(paths), 100):
            r = self.client.request("DELETE", f"{self.base}/object/{self.bucket}", headers=self.h,
                                    json={"prefixes": paths[i:i + 100]})
            if r.status_code < 300:
                n += len(paths[i:i + 100])
            else:
                log.warning("delete failed: %s %s", r.status_code, r.text[:200])
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


def mirror() -> Mirror | None:
    """A Mirror for one-off jobs (scripts), or None without Supabase settings."""
    s = get_settings()
    if not (s.supabase_url and s.supabase_service_key):
        return None
    return Mirror(s.supabase_url, s.supabase_service_key, s.supabase_bucket)


def start() -> bool:
    """Start in the background so the web server opens its port at once (hosts like Render wait for it).
    Saved plans come back within seconds; until then a plan link may say "not found" once."""
    s = get_settings()
    if not (s.supabase_url and s.supabase_service_key):
        log.info("Supabase not set: data stays on local disk")
        return False
    m = Mirror(s.supabase_url, s.supabase_service_key, s.supabase_bucket)

    def run():
        try:
            got = m.restore()
            m.push_changes()                   # files made before the first sync go up now
            log.info("Supabase: restored %d files, syncing every %ds", got, EVERY_S)
        except Exception as e:
            log.warning("Supabase restore failed: %s", e)
        m.loop()
    threading.Thread(target=run, daemon=True, name="supabase-sync").start()
    return True
