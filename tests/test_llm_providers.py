"""Provider selection, the Gemini (OpenAI-compatible) path and rate-limit retries, with no network calls."""
from types import SimpleNamespace

import pytest

from ipodesk import llm
from ipodesk.llm import LLMClient, LLMConfig, LLMError, Overloaded, RateLimited, load_llm_config, pick_provider


@pytest.fixture(autouse=True)
def no_keys(monkeypatch):
    """Start every test with no API keys and no .env file influence."""
    for var in llm.KEY_ENV_VARS.values():
        monkeypatch.delenv(var, raising=False)
    monkeypatch.delenv("IPODESK_LLM_PROVIDER", raising=False)
    monkeypatch.setattr(llm, "load_dotenv", lambda *a, **k: None)


def test_auto_picks_first_provider_with_a_key(monkeypatch) -> None:
    assert pick_provider(["anthropic", "openai", "gemini"]) == "anthropic"  # none set: first in order
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    assert pick_provider(["anthropic", "openai", "gemini"]) == "gemini"
    cfg = load_llm_config("auto")
    assert cfg.provider == "gemini" and cfg.model.startswith("gemini")


def test_unknown_provider_is_rejected() -> None:
    with pytest.raises(LLMError):
        load_llm_config("not-a-provider")


class _FakeCompletions:
    """Stands in for openai's chat.completions; records calls and can fail first."""

    def __init__(self, fail_with=None):
        self.calls, self.fail_with = [], fail_with

    def create(self, **kwargs):
        self.calls.append(kwargs)
        if self.fail_with and len(self.calls) == 1:
            raise self.fail_with
        msg = SimpleNamespace(content='{"ok": true}')
        return SimpleNamespace(choices=[SimpleNamespace(message=msg)],
                               usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5))


def _patch_openai(monkeypatch, completions):
    """Replace openai.OpenAI with a fake that captures the base URL and key it was given."""
    import openai

    seen = {}

    def fake_client(api_key=None, base_url=None, **_options):
        seen.update(api_key=api_key, base_url=base_url)
        return SimpleNamespace(chat=SimpleNamespace(completions=completions))

    monkeypatch.setattr(openai, "OpenAI", fake_client)
    return seen


def test_gemini_uses_google_endpoint_and_max_tokens(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    completions = _FakeCompletions()
    seen = _patch_openai(monkeypatch, completions)
    reply = LLMClient(LLMConfig("gemini", "gemini-test")).complete("Reply in JSON.", "hi")
    assert reply == '{"ok": true}'
    assert seen == {"api_key": "test-key", "base_url": llm.OPENAI_COMPATIBLE_BASE_URLS["gemini"]}
    call = completions.calls[0]
    assert call["max_tokens"] == 4000 and "max_completion_tokens" not in call
    assert call["response_format"] == {"type": "json_object"}


def test_json_mode_rejected_falls_back_to_plain(monkeypatch) -> None:
    import openai

    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    bad = openai.BadRequestError.__new__(openai.BadRequestError)  # skip the SDK's HTTP-response constructor
    Exception.__init__(bad, "no json mode")
    completions = _FakeCompletions(fail_with=bad)
    _patch_openai(monkeypatch, completions)
    LLMClient(LLMConfig("gemini", "gemini-test")).complete("Reply in JSON.", "hi")
    assert len(completions.calls) == 2 and "response_format" not in completions.calls[1]


def test_rate_limit_waits_then_succeeds(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    waits: list[int] = []
    monkeypatch.setattr(llm.time, "sleep", waits.append)
    attempts = iter([RateLimited("429"), RateLimited("429"), "done"])

    def flaky(self, system, user, model):
        result = next(attempts)
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(LLMClient, "_openai", flaky)
    assert LLMClient(LLMConfig("gemini", "gemini-test")).complete("s", "u") == "done"
    assert waits == list(llm.RATE_LIMIT_WAITS[:2])


def test_rate_limit_gives_up_with_clear_error(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)

    def always_limited(self, system, user, model):
        raise RateLimited("429")

    monkeypatch.setattr(LLMClient, "_openai", always_limited)
    with pytest.raises(LLMError, match="daily cap"):
        LLMClient(LLMConfig("gemini", "gemini-test")).complete("s", "u")


def test_overloaded_model_falls_back_to_next(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setattr(llm.time, "sleep", lambda s: pytest.fail("should not wait on a busy model"))
    tried: list[str] = []

    def busy_main(self, system, user, model):
        tried.append(model)
        if model == "main":
            raise Overloaded("main: HTTP 503")
        return "from lite"

    monkeypatch.setattr(LLMClient, "_openai", busy_main)
    client = LLMClient(LLMConfig("gemini", "main", fallback_models=("lite",)))
    assert client.complete("s", "u") == "from lite"
    assert tried == ["main", "lite"] and client.last_model == "lite"


def test_all_models_overloaded_gives_clear_error(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")

    def busy(self, system, user, model):
        raise Overloaded(f"{model}: HTTP 503")

    monkeypatch.setattr(LLMClient, "_openai", busy)
    with pytest.raises(LLMError, match="overloaded"):
        LLMClient(LLMConfig("gemini", "main", fallback_models=("lite",))).complete("s", "u")


def test_settings_give_gemini_fallbacks(monkeypatch) -> None:
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    assert load_llm_config("gemini").fallback_models  # config/settings.yaml lists at least one
