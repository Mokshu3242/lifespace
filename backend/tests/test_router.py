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


def test_local_vision_chain_setting(tmp_path):
    r = ModelRouter(Settings(mode="local", cache_dir=tmp_path, local_vision_chain="cloudflare,ollama",
                             _env_file=None))
    seen = []

    class Rec:
        def __init__(self, name):
            self.name = name

        def chat(self, *a, **k):
            seen.append(self.name)
            return '{"ok": 1}'

    r.chat_providers["ollama"] = Rec("ollama")
    r.chat_providers["cloudflare"] = Rec("cloudflare")
    r.see("q", b"x")
    r.ask("q")
    assert seen == ["cloudflare", "ollama"]   # vision tries cloudflare first, chat keeps ollama first


def test_fresh_and_cache_off_skip_saved_answers(tmp_path):
    r = make_router(tmp_path)
    r.ask("same")
    r.ask("same")
    assert r.last_provider == "mock (cache)"
    r.fresh = True
    r.ask("same")
    assert r.last_provider == "mock"
    r.fresh = False
    r2 = ModelRouter(Settings(mode="mock", cache_dir=tmp_path, ai_cache=False, _env_file=None))
    r2.ask("same")
    assert r2.last_provider == "mock"


def test_keyless_voters_are_skipped_and_gemini_gets_no_response_format(tmp_path):
    r = ModelRouter(Settings(mode="local", cache_dir=tmp_path, _env_file=None,
                             local_vision_chain="cloudflare,ollama,gemini,groq",
                             gemini_api_key="k"))
    assert r.vision_chain() == ["ollama", "gemini"]       # cloudflare and groq have no keys
    assert r.chat_providers["gemini"].json_format is False
