"""Send one prompt to one model through Straive's LLM Foundry (OpenRouter route)."""
from __future__ import annotations

import time
from typing import Callable

import httpx

URL = "https://llmfoundry.straive.com/openrouter/v1/chat/completions"
ATTEMPTS = 3

AskFn = Callable[[str, str], str]  # (model_id, prompt) -> answer text

_sleep = time.sleep  # replaced in tests


class LLMError(RuntimeError):
    pass


def make_ask(token: str | None, project: str, timeout_s: int,
             transport: httpx.BaseTransport | None = None) -> AskFn:
    if not token or not token.strip():
        raise LLMError("LLMFOUNDRY_TOKEN is not set")
    token = token.strip()
    http = httpx.Client(timeout=timeout_s, transport=transport)
    headers = {
        "Authorization": f"Bearer {token}:{project}",
        "Content-Type": "application/json",
        # Foundry caches every response by default. Without this header a
        # weekly run would be handed last week's answer.
        "Cache-Control": "no-cache",
    }

    def clean(text: str) -> str:
        return " ".join(text.replace(token, "***").split())[:200]

    def ask(model_id: str, prompt: str) -> str:
        body = {"model": model_id, "messages": [{"role": "user", "content": prompt}]}
        problem = "no attempt made"
        for attempt in range(ATTEMPTS):
            if attempt:
                _sleep(2 ** attempt)  # 2 s, then 4 s
            try:
                response = http.post(URL, headers=headers, json=body)
            except httpx.TimeoutException:
                problem = f"timed out after {timeout_s}s"
                continue
            except httpx.TransportError as e:
                problem = f"could not reach LLM Foundry ({type(e).__name__})"
                continue
            status = response.status_code
            if status == 429 or status >= 500:
                problem = f"HTTP {status}: {clean(response.text)}"
                continue
            if status != 200:
                raise LLMError(f"HTTP {status}: {clean(response.text)}")
            if response.headers.get("X-Cache", "").upper() == "HIT":
                raise LLMError("served from cache")
            return _content(response, clean)
        raise LLMError(problem)

    return ask


def _content(response: httpx.Response, clean: Callable[[str], str]) -> str:
    try:
        data = response.json()
    except ValueError:
        raise LLMError(f"reply was not JSON: {clean(response.text)}") from None
    if isinstance(data, dict) and data.get("error"):
        raise LLMError(f"provider error: {clean(str(data['error']))}")
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        content = None
    if isinstance(content, list):  # some providers return content in parts
        content = "".join(p.get("text", "") for p in content if isinstance(p, dict))
    if not isinstance(content, str) or not content.strip():
        raise LLMError("empty answer")
    return content
