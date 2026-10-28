"""Router tests. Run offline: no keys, no network."""
from pathlib import Path

import pytest

from app.config import Settings
from app.router.model_router import AllProvidersFailed, ModelRouter, _extract_json
from app.router.providers import ProviderError


def make_router(tmp_path: Path, mode: str = "mock") -> ModelRouter:
    return ModelRouter(Settings(mode=mode, cache_dir=tmp_path, _env_file=None))


def test_mock_ask_and_json(tmp_path):
    r = make_router(tmp_path)
    assert r.ask("hi") == "mock answer"
    assert r.ask_json("give json") == {"ok": True, "source": "mock"}
    assert r.see("what is this", b"fakepng") == {"ok": True, "source": "mock"}
    assert r.render("a street")[:4] == b"\x89PNG"


def test_cache_hit(tmp_path):
    r = make_router(tmp_path)
    r.ask("same prompt")
    r.ask("same prompt")
    assert r.last_provider == "mock (cache)"


def test_fallback_to_next_provider(tmp_path):
    r = make_router(tmp_path, mode="local")

    class Broken:
        def chat(self, *a, **k):
            raise ProviderError("down")

    class Works:
        def chat(self, *a, **k):
            return '{"answer": 42}'

    r.chat_providers["ollama"] = Broken()
    r.chat_providers["cloudflare"] = Works()
    assert r.ask_json("q") == {"answer": 42}
    assert r.last_provider == "cloudflare"


def test_junk_json_triggers_fallback(tmp_path):
    r = make_router(tmp_path, mode="local")

    class Junk:
        def chat(self, *a, **k):
            return "sorry, I can't"

    class Works:
        def chat(self, *a, **k):
            return '{"ok": 1}'

    r.chat_providers["ollama"] = Junk()
    r.chat_providers["cloudflare"] = Works()
    assert r.ask_json("q") == {"ok": 1}


def test_all_fail(tmp_path):
    r = make_router(tmp_path, mode="local")

    class Broken:
        def chat(self, *a, **k):
            raise ProviderError("down")

    r.chat_providers["ollama"] = Broken()
    r.chat_providers["cloudflare"] = Broken()
    with pytest.raises(AllProvidersFailed):
        r.ask("q")


def test_extract_json_from_fences():
    assert _extract_json('Here:\n```json\n{"a": 1}\n```') == {"a": 1}
    assert _extract_json('blah {"b": [1,2]} blah') == {"b": [1, 2]}


def test_bad_mode(tmp_path):
    with pytest.raises(ValueError):
        make_router(tmp_path, mode="nope")
