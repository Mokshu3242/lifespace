"""The model router. Every AI call in LifeSpace goes through here.

    ask(prompt)            -> text
    ask_json(prompt)       -> dict
    see(prompt, image)     -> dict (vision, JSON out)
    render(prompt)         -> PNG bytes

MODE picks the provider chain. If one provider fails, the next one answers,
so the demo never breaks. Every answer is cached on disk.
"""
import base64
import io
import json
import logging
import re
import time

from PIL import Image

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


def _shrink(image_bytes: bytes, max_side: int = 1280) -> tuple[bytes, str]:
    """Resize big images and re-encode as PNG. Vision models fail or slow down on huge files."""
    try:
        img = Image.open(io.BytesIO(image_bytes))
        img.load()
    except Exception:
        return image_bytes, "image/png"  # not a real image (e.g. tests); send as is
    if img.mode not in ("RGB", "L"):
        img = img.convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue(), "image/png"


class ModelRouter:
    def __init__(self, settings: Settings | None = None):
        self.s = settings or get_settings()
        if self.s.mode not in CHAINS:
            raise ValueError(f"MODE must be one of {list(CHAINS)}, got {self.s.mode!r}")
        self.chat_providers = build_chat_providers(self.s)
        self.image_providers = build_image_providers(self.s)
        self.cache = DiskCache(self.s.cache_dir / self.s.mode)
        self.fresh = False   # when True, saved answers are ignored (new answers are still saved)
        self.last_provider: str | None = None

    def _cached(self, key: str):
        if self.fresh or not self.s.ai_cache:
            return None
        return self.cache.get(key)

    # ---------- core ----------
    def _chat(self, messages: list[dict], json_mode: bool, vision: bool,
              temperature: float) -> str:
        chain = CHAINS[self.s.mode]["chat"]
        if vision:
            chain = self.vision_chain()   # e.g. LOCAL_VISION_CHAIN=cloudflare,ollama
        key = self.cache.key("chat", chain, messages, json_mode, vision, temperature)
        hit = self._cached(key)
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
        image_bytes, mime = _shrink(image_bytes)
        data_url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"
        sys_msg = (system or "") + "\nReply with one JSON object only. No prose."
        msgs = [{"role": "system", "content": sys_msg.strip()},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ]}]
        return _extract_json(self._chat(msgs, json_mode=True, vision=True,
                                         temperature=0.1))

    def vision_chain(self) -> list[str]:
        chain = CHAINS[self.s.mode]["chat"]
        if self.s.mode == "local" and self.s.local_vision_chain.strip():
            chain = [p.strip() for p in self.s.local_vision_chain.split(",")
                     if p.strip() in self.chat_providers]
        # skip providers with no key set, so a missing Groq key costs nothing
        return [p for p in chain if getattr(self.chat_providers[p], "ready", True)]

    def see_each(self, prompt: str, image_bytes: bytes, mime: str = "image/png",
                 system: str | None = None) -> dict[str, dict]:
        """Ask EVERY vision model the same question (no stopping at the first answer),
        so their answers can be compared. Models that fail are left out. Cached per model."""
        image_bytes, mime = _shrink(image_bytes, max_side=1600)
        data_url = f"data:{mime};base64,{base64.b64encode(image_bytes).decode()}"
        sys_msg = ((system or "") + "\nReply with one JSON object only. No prose.").strip()
        msgs = [{"role": "system", "content": sys_msg},
                {"role": "user", "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ]}]
        out: dict[str, dict] = {}
        for name in self.vision_chain():
            key = self.cache.key("see_each", name, msgs)
            hit = self._cached(key)
            if hit is not None:
                out[name] = hit
                continue
            try:
                t0 = time.time()
                text = self.chat_providers[name].chat(msgs, json_mode=True, vision=True, temperature=0.1)
                ans = _extract_json(text)
            except (ProviderError, ValueError) as e:
                log.warning("vision model %s failed: %s", name, e)
                continue
            log.info("vision model %s answered in %.1fs", name, time.time() - t0)
            self.cache.set(key, ans)
            out[name] = ans
        return out

    def render(self, prompt: str) -> bytes:
        chain = CHAINS[self.s.mode]["image"]
        key = self.cache.key("image", chain, prompt)
        hit = self._cached(key)
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
