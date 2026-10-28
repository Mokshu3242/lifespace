"""One class per model provider.

Meta, Baseten, Cloudflare and Ollama all speak the OpenAI chat format,
so most providers share one client. Only image generation differs.
"""
import base64

import httpx

from app.config import Settings


class ProviderError(Exception):
    """Raised when a provider can't answer. The router then tries the next one."""


class OpenAICompatProvider:
    def __init__(self, name: str, base_url: str, api_key: str, chat_model: str,
                 vision_model: str | None, timeout: float):
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.chat_model = chat_model
        self.vision_model = vision_model or chat_model
        self.timeout = timeout

    def chat(self, messages: list[dict], json_mode: bool = False,
             vision: bool = False, temperature: float = 0.3) -> str:
        body = {
            "model": self.vision_model if vision else self.chat_model,
            "messages": messages,
            "temperature": temperature,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        try:
            r = httpx.post(f"{self.base_url}/chat/completions", json=body,
                           headers=headers, timeout=self.timeout)
        except httpx.HTTPError as e:
            raise ProviderError(f"{self.name}: {e}") from e
        if r.status_code >= 400:
            raise ProviderError(f"{self.name}: HTTP {r.status_code} {r.text[:300]}")
        try:
            return r.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as e:
            raise ProviderError(f"{self.name}: bad response {r.text[:300]}") from e


class CloudflareImageProvider:
    """Free text-to-image on Cloudflare Workers AI (local backup for renders)."""

    name = "cloudflare-image"

    def __init__(self, s: Settings):
        self.s = s

    def render(self, prompt: str) -> bytes:
        if not (self.s.cloudflare_account_id and self.s.cloudflare_api_token):
            raise ProviderError("cloudflare-image: no credentials")
        url = (f"https://api.cloudflare.com/client/v4/accounts/"
               f"{self.s.cloudflare_account_id}/ai/run/{self.s.cloudflare_image_model}")
        try:
            r = httpx.post(url, json={"prompt": prompt},
                           headers={"Authorization": f"Bearer {self.s.cloudflare_api_token}"},
                           timeout=self.s.request_timeout)
        except httpx.HTTPError as e:
            raise ProviderError(f"cloudflare-image: {e}") from e
        if r.status_code >= 400:
            raise ProviderError(f"cloudflare-image: HTTP {r.status_code} {r.text[:300]}")
        return base64.b64decode(r.json()["result"]["image"])


class MetaImageProvider:
    """Muse Image / Muse Wonder on the Meta Model API.

    TODO(day 6): fill in once credits land and we read the image docs.
    Until then it raises, so the router falls back to the free renderer.
    """

    name = "meta-image"

    def __init__(self, s: Settings):
        self.s = s

    def render(self, prompt: str) -> bytes:
        raise ProviderError("meta-image: not wired yet")


class MockProvider:
    """Canned answers, no network. Lets tests and the UI run with zero setup."""

    name = "mock"

    def chat(self, messages: list[dict], json_mode: bool = False,
             vision: bool = False, temperature: float = 0.3) -> str:
        if json_mode:
            return '{"ok": true, "source": "mock"}'
        return "mock answer"

    def render(self, prompt: str) -> bytes:
        # 1x1 grey PNG
        return base64.b64decode(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mN8/5+hHgAHggJ/PchI7wAAAABJRU5ErkJggg=="
        )


def build_chat_providers(s: Settings) -> dict[str, object]:
    cf_base = (f"https://api.cloudflare.com/client/v4/accounts/"
               f"{s.cloudflare_account_id}/ai/v1")
    return {
        "meta": OpenAICompatProvider("meta", s.meta_base_url, s.meta_api_key,
                                     s.meta_chat_model, s.meta_chat_model, s.request_timeout),
        "baseten": OpenAICompatProvider("baseten", s.baseten_base_url, s.baseten_api_key,
                                        s.baseten_model, s.baseten_model, s.request_timeout),
        "cloudflare": OpenAICompatProvider("cloudflare", cf_base, s.cloudflare_api_token,
                                           s.cloudflare_chat_model, s.cloudflare_vision_model,
                                           s.request_timeout),
        "ollama": OpenAICompatProvider("ollama", f"{s.ollama_url}/v1", "",
                                       s.ollama_chat_model, s.ollama_vision_model,
                                       s.request_timeout),
        "mock": MockProvider(),
    }


def build_image_providers(s: Settings) -> dict[str, object]:
    return {
        "meta": MetaImageProvider(s),
        "cloudflare": CloudflareImageProvider(s),
        "mock": MockProvider(),
    }
