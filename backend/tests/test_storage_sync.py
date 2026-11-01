import json

import httpx

from app import storage_sync


def test_restore_and_push(tmp_path, monkeypatch):
    monkeypatch.setattr(storage_sync, "ROOT", tmp_path)
    store = {".data/spaces/abc/map.json": b'{"id":"abc"}'}
    uploads = {}

    def handler(req: httpx.Request):
        path = req.url.path
        if path.endswith("/object/list/lifespace"):
            prefix = json.loads(req.content)["prefix"]
            names = {k[len(prefix) + 1:].split("/")[0] for k in store if k.startswith(prefix + "/")}
            rows = [{"name": n, "id": "x" if f"{prefix}/{n}" in store else None} for n in sorted(names)]
            return httpx.Response(200, json=rows)
        if req.method == "GET" and "/object/lifespace/" in path:
            return httpx.Response(200, content=store[path.split("/object/lifespace/")[1]])
        if req.method == "POST" and "/object/lifespace/" in path:
            uploads[path.split("/object/lifespace/")[1]] = req.content
            return httpx.Response(200, json={})
        return httpx.Response(404)

    m = storage_sync.Mirror("https://x.supabase.co", "key", "lifespace")
    m.client = httpx.Client(transport=httpx.MockTransport(handler))
    assert m.restore() == 1
    assert (tmp_path / ".data/spaces/abc/map.json").read_bytes() == b'{"id":"abc"}'
    (tmp_path / ".cache/ai").mkdir(parents=True)
    (tmp_path / ".cache/ai/k.json").write_text("{}")
    assert m.push_changes() == 1 and ".cache/ai/k.json" in uploads
    assert m.push_changes() == 0          # nothing changed
