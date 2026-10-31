"""One class per model provider.

Meta, Baseten, Cloudflare and Ollama all speak the OpenAI chat format,
so most providers share one client. Only image generation differs.
"""
import base64
import random
import time

import httpx

from app.config import Settings


class ProviderError(Exception):
    """Raised when a provider can't answer. The router then tries the next one."""


class OpenAICompatProvider:
    def __init__(self, name: str, base_url: str, api_key: str, chat_model: str,
                 vision_model: str | None, timeout: float, json_format: bool = True,
                 max_tokens: int | None = None, send_temperature: bool = True):
        # Muse Spark is tuned for its default temperature; Meta's docs say to leave it unset
        self.send_temperature = send_temperature
        self.max_tokens = max_tokens     # Groq's free tier rejects requests that could exceed 1000 output tokens
        self.json_format = json_format   # some providers reject response_format; the prompt asks for JSON anyway
        self.name = name
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.chat_model = chat_model
        self.vision_model = vision_model or chat_model
        self.timeout = timeout

    @property
    def ready(self) -> bool:
        """Has the key it needs (Ollama runs locally and needs none)."""
        return bool(self.api_key) or self.name == "ollama"

    def chat(self, messages: list[dict], json_mode: bool = False,
             vision: bool = False, temperature: float = 0.3) -> str:
        body = {
            "model": self.vision_model if vision else self.chat_model,
            "messages": messages,
        }
        if self.send_temperature:
            body["temperature"] = temperature
        if self.max_tokens:
            body["max_tokens"] = self.max_tokens
        if json_mode and self.json_format:
            body["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        r = _post_with_retry(self.name, f"{self.base_url}/chat/completions", body, headers, self.timeout)
        if r.status_code >= 400:
            raise ProviderError(f"{self.name}: HTTP {r.status_code} {r.text[:300]}")
        try:
            return r.json()["choices"][0]["message"]["content"]
        except (KeyError, IndexError, ValueError) as e:
            raise ProviderError(f"{self.name}: bad response {r.text[:300]}") from e


RETRY_STATUS = {429, 500, 502, 503}


def _post_with_retry(name: str, url: str, body: dict, headers: dict, timeout: float,
                     attempts: int = 3) -> httpx.Response:
    """Retry rate limits and brief server errors with backoff, honoring Retry-After.
    Never retry 4xx request errors (they fail the same way again), per Meta's error docs."""
    delay = 1.0
    for attempt in range(attempts):
        try:
            r = httpx.post(url, json=body, headers=headers, timeout=timeout)
        except httpx.TimeoutException as e:
            raise ProviderError(f"{name}: timed out") from e      # a retry would time out too
        except httpx.HTTPError as e:
            if attempt == attempts - 1:
                raise ProviderError(f"{name}: {e}") from e
            time.sleep(delay + random.random())
            delay *= 2
            continue
        if r.status_code in RETRY_STATUS and attempt < attempts - 1:
            try:
                wait = min(10.0, float(r.headers.get("retry-after", delay)))
            except ValueError:
                wait = delay
            time.sleep(wait + random.random())
            delay *= 2
            continue
        return r
    return r


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
    """Muse Image on the Meta Model API ($0.01 per image).
    Generate: POST /images/generations. Edit (redraw a given picture): POST /images/edits."""

    name = "meta-image"

    def __init__(self, s: Settings):
        self.s = s

    def render(self, prompt: str, image_bytes: bytes | None = None) -> bytes:
        if not self.s.meta_api_key:
            raise ProviderError("meta-image: no key")
        body = {"model": self.s.meta_image_model, "prompt": prompt, "n": 1,
                "response_format": "b64_json", "output_format": "png",
                "tool_enablement": {"enable_image_search": False, "enable_web_search": False,
                                    "enable_shell": False}}
        path = "images/generations"
        if image_bytes is not None:
            path = "images/edits"
            body["images"] = [{"image_url": "data:image/png;base64," + base64.b64encode(image_bytes).decode()}]
        else:
            body["size"] = "1536x1024"
        r = _post_with_retry("meta-image", f"{self.s.meta_base_url.rstrip('/')}/{path}", body,
                             {"Authorization": f"Bearer {self.s.meta_api_key}"}, max(self.s.request_timeout, 180))
        if r.status_code >= 400:
            raise ProviderError(f"meta-image: HTTP {r.status_code} {r.text[:300]}")
        try:
            return base64.b64decode(r.json()["data"][0]["b64_json"])
        except (KeyError, IndexError, ValueError) as e:
            raise ProviderError(f"meta-image: bad response {r.text[:200]}") from e


class MockProvider:
    """Canned answers, no network. Lets tests and the UI run with zero setup."""

    name = "mock"
    ready = True

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
                                     s.meta_chat_model, s.meta_chat_model, s.request_timeout,
                                     send_temperature=False),
        # Baseten's Muse Spark Open has no JSON mode (per Baseten's docs); the prompt asks for JSON
        "baseten": OpenAICompatProvider("baseten", s.baseten_base_url, s.baseten_api_key,
                                        s.baseten_model, s.baseten_model, s.request_timeout,
                                        json_format=False),
        "cloudflare": OpenAICompatProvider("cloudflare", cf_base, s.cloudflare_api_token,
                                           s.cloudflare_chat_model, s.cloudflare_vision_model,
                                           s.request_timeout),
        "groq": OpenAICompatProvider("groq", s.groq_base_url, s.groq_api_key,
                                     s.groq_model, s.groq_model, s.request_timeout, max_tokens=900),
        "gemini": OpenAICompatProvider("gemini", s.gemini_base_url, s.gemini_api_key,
                                       s.gemini_model, s.gemini_model, s.request_timeout,
                                       json_format=False),
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
