"""Tiny disk cache so the same AI request never gets paid for twice."""
import hashlib
import json
from pathlib import Path
from typing import Any


class DiskCache:
    def __init__(self, folder: Path):
        self.folder = folder
        self.folder.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def key(*parts: Any) -> str:
        raw = json.dumps(parts, sort_keys=True, default=str)
        return hashlib.sha256(raw.encode()).hexdigest()

    def get(self, key: str) -> Any | None:
        path = self.folder / f"{key}.json"
        if path.exists():
            return json.loads(path.read_text())
        return None

    def set(self, key: str, value: Any) -> None:
        (self.folder / f"{key}.json").write_text(json.dumps(value))
