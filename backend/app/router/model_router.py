"""The model router. Every AI call in LifeSpace goes through here.

    ask(prompt)            -> text
    ask_json(prompt)       -> dict
    see(prompt, image)     -> dict (vision, JSON out)
    render(prompt)         -> PNG bytes

MODE picks the provider chain. If one provider fails, the next one answers,
so the demo never breaks. Every answer is cached on disk.
"""
import base64
import json
import logging
import re
import time

from app.config import Settings, get_settings
from app.router.cache import DiskCache
from app.router.providers import (ProviderError, build_chat_providers,
                                  build_image_providers)

log = logging.getLogger("router")

# Order = try first -> last
CHAINS = {
    "local": {"chat": ["ollama", "cloudflare"], "image": ["cloudflare"]},
    "prod":  {"chat": ["meta", "baseten", "cloudflare"], "image": ["meta", "cloudflare"]},
    "mock":  {"chat": ["mock"], "image": ["mock"]},
}


class AllProvidersFailed(Exception):
    pass


def _extract_json(text: str) -> dict:
    """Models sometimes wrap JSON in ```fences``` or add words. Pull out the object."""
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.S)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object found")
    return json.loads(text[start:end + 1])


class ModelRouter:
    def __init__(self, settings: Settings | None = None):
        self.s = settings or get_settings()
        if self.s.mode not in CHAINS:
            raise ValueError(f"MODE must be one of {list(CHAINS)}, got {self.s.mode!r}")
        self.chat_providers = build_chat_providers(self.s)
        self.image_providers = build_image_providers(self.s)
        self.cache = DiskCache(self.s.cache_dir / self.s.mode)
        self.last_provider: str | None = None

    # ---------- core ----------
    def _chat(self, messages: list[dict], json_mode: bool, vision: bool,
              temperature: float) -> str:
        chain = CHAINS[self.s.mode]["chat"]
        key = self.cache.key("chat", chain, messages, json_mode, vision, temperature)
        hit = self.cache.get(key)
        if hit is not None:
            self.last_provider = hit["provider"] + " (cache)"
            return hit["text"]

        errors = []
        for name in chain:
            provider = self.chat_providers[name]
            t0 = time.time()
            try:
                text = provider.chat(messages, json_mode=json_mode, vision=vision,
                                     temperature=temperature)
                if json_mode:
                    _extract_json(text)  # fail over if a provider returns junk
            except (ProviderError, ValueError) as e:
                log.warning("provider %s failed: %s", name, e)
                errors.append(f"{name}: {e}")
                continue
            log.info("provider %s answered in %.1fs", name, time.time() - t0)
            self.last_provider = name
            self.cache.set(key, {"provider": name, "text": text})
            return text
        raise AllProvidersFailed(" | ".join(errors))

    # ---------- public API ----------
    def ask(self, prompt: str, system: str | None = None,
            temperature: float = 0.3) -> str:
        msgs = ([{"role": "system", "content": system}] if system else []) + \
               [{"role": "user", "content": prompt}]
        return self._chat(msgs, json_mode=False, vision=False, temperature=temperature)

    def ask_json(self, prompt: str, system: str | None = None,
                 temperature: float = 0.2) -> dict:
        sys_msg = (system or "") + "\nReply with one JSON object only. No prose."
        msgs = [{"role": "system", "content": sys_msg.strip()},
                {"role": "user", "content": prompt}]
        return _extract_json(self._chat(msgs, json_mode=True, vision=False,
                                         temperature=temperature))

    def see(self, prompt: str, image_bytes: bytes, mime: str = "image/png",
            system: str | None = None) -> dict:
        data_url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"
        sys_msg = (system or "") + "\nReply with one JSON object only. No prose."
        msgs = [{"role": "system", "content": sys_msg.strip()},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ]}]
        return _extract_json(self._chat(msgs, json_mode=True, vision=True,
                                         temperature=0.1))

    def render(self, prompt: str) -> bytes:
        chain = CHAINS[self.s.mode]["image"]
        key = self.cache.key("image", chain, prompt)
        hit = self.cache.get(key)
        if hit is not None:
            self.last_provider = hit["provider"] + " (cache)"
            return base64.b64decode(hit["b64"])
        errors = []
        for name in chain:
            try:
                png = self.image_providers[name].render(prompt)
            except ProviderError as e:
                log.warning("image provider %s failed: %s", name, e)
                errors.append(f"{name}: {e}")
                continue
            self.last_provider = name
            self.cache.set(key, {"provider": name, "b64": base64.b64encode(png).decode()})
            return png
        raise AllProvidersFailed(" | ".join(errors))


_router: ModelRouter | None = None


def get_router() -> ModelRouter:
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router
