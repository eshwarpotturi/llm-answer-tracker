import json

import httpx
import pytest

from tracker import client
from tracker.client import LLMError, make_ask

OK_BODY = {"choices": [{"message": {"content": "ok"}}]}


def mock(status, body, headers=None):
    return httpx.MockTransport(lambda request: httpx.Response(status, json=body, headers=headers))


def capture(seen):
    def handler(request):
        seen["url"] = str(request.url)
        seen["json"] = json.loads(request.content)
        seen["headers"] = dict(request.headers)
        return httpx.Response(200, json=OK_BODY)
    return httpx.MockTransport(handler)


class sequence(httpx.BaseTransport):
    """Answers with each status in turn; a 200 carries the answer 'ok'."""
    def __init__(self, statuses):
        self.statuses = list(statuses)
        self.calls = 0

    def handle_request(self, request):
        status = self.statuses[self.calls]
        self.calls += 1
        return httpx.Response(status, json=OK_BODY if status == 200 else {"error": "x"})


@pytest.fixture
def no_sleep(monkeypatch):
    waits = []
    monkeypatch.setattr(client, "_sleep", waits.append)
    return waits


def test_returns_message_content():
    ask = make_ask("k", "proj", 5, transport=mock(200, {"choices": [{"message": {"content": "hi"}}]}))
    assert ask("openai/x", "hello") == "hi"


def test_sends_model_prompt_token_project_and_no_cache():
    seen = {}
    ask = make_ask("secret", "llm-answer-tracker", 5, transport=capture(seen))
    ask("openai/x", "hello")
    assert seen["url"] == "https://llmfoundry.straive.com/openrouter/v1/chat/completions"
    assert seen["json"]["model"] == "openai/x"
    assert seen["json"]["messages"] == [{"role": "user", "content": "hello"}]
    assert seen["headers"]["authorization"] == "Bearer secret:llm-answer-tracker"
    assert seen["headers"]["cache-control"] == "no-cache"


def test_cached_response_rejected():
    t = mock(200, {"choices": [{"message": {"content": "old"}}]}, headers={"X-Cache": "HIT"})
    with pytest.raises(LLMError, match="served from cache"):
        make_ask("k", "proj", 5, transport=t)("m", "p")


def test_retries_then_succeeds(no_sleep):
    ask = make_ask("k", "proj", 5, transport=sequence([503, 429, 200]))
    assert ask("m", "p") == "ok"
    assert no_sleep == [2, 4]


def test_gives_up_after_three_attempts(no_sleep):
    with pytest.raises(LLMError, match="503"):
        make_ask("k", "proj", 5, transport=sequence([503, 503, 503]))("m", "p")


def test_client_error_not_retried(no_sleep):
    t = sequence([400, 200])
    with pytest.raises(LLMError, match="400"):
        make_ask("k", "proj", 5, transport=t)("m", "p")
    assert t.calls == 1


def test_missing_token_raises_clear_error():
    with pytest.raises(LLMError, match="LLMFOUNDRY_TOKEN is not set"):
        make_ask(None, "proj", 5)


def test_empty_or_missing_content_raises():
    with pytest.raises(LLMError, match="empty answer"):
        make_ask("k", "proj", 5, transport=mock(200, {"choices": [{"message": {"content": ""}}]}))("m", "p")


def test_timeout_is_retried_and_reported(no_sleep):
    def handler(request):
        raise httpx.ReadTimeout("slow", request=request)
    with pytest.raises(LLMError, match="timed out"):
        make_ask("k", "proj", 5, transport=httpx.MockTransport(handler))("m", "p")
    assert no_sleep == [2, 4]


def test_error_text_never_contains_the_token(no_sleep):
    with pytest.raises(LLMError) as e:
        make_ask("TOPSECRET", "proj", 5, transport=mock(401, {"error": "bad token TOPSECRET"}))("m", "p")
    assert "TOPSECRET" not in str(e.value)
