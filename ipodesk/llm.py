"""One small wrapper around the LLM so the rest of the app never talks to a vendor SDK.

Why a wrapper?
- Switching between Anthropic and OpenAI is a one-line change in config/settings.yaml.
- Every call that needs structured data goes through `complete_json`, which checks the
  reply against a pydantic schema and retries if the model returns broken JSON.
- A "fake" provider lets tests (and offline demos) run with no API key and no cost.

API keys are read from environment variables (ANTHROPIC_API_KEY / OPENAI_API_KEY).
Locally they come from a git-ignored .env file; on Streamlit Community Cloud, root-level
secrets are exposed as environment variables automatically.
"""
from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from typing import Callable, TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

from ipodesk.config import PROJECT_ROOT, get_settings

T = TypeVar("T", bound=BaseModel)

KEY_ENV_VARS: dict[str, str] = {"anthropic": "ANTHROPIC_API_KEY", "openai": "OPENAI_API_KEY"}

FakeReply = Callable[[str, str], str]


class LLMError(RuntimeError):
    """Raised when the LLM cannot be called or keeps returning invalid output."""


@dataclass
class LLMConfig:
    """Which provider/model to use and how."""

    provider: str
    model: str
    temperature: float = 0.0
    max_tokens: int = 4000
    max_retries: int = 2


@dataclass
class Usage:
    """Running token count, so the app can show roughly what a note cost."""

    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0

    def add(self, input_tokens: int, output_tokens: int) -> None:
        """Add one call's token counts to the running total."""
        self.input_tokens += input_tokens
        self.output_tokens += output_tokens
        self.calls += 1


def load_llm_config(provider: str | None = None) -> LLMConfig:
    """Build an LLMConfig from settings.yaml (optionally overriding the provider)."""
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    cfg = get_settings()["llm"]
    provider = (provider or os.getenv("IPODESK_LLM_PROVIDER") or cfg["provider"]).lower()
    if provider not in ("anthropic", "openai", "fake"):
        raise LLMError(f"Unknown LLM provider '{provider}'. Use anthropic, openai or fake.")
    return LLMConfig(
        provider=provider,
        model=cfg["models"].get(provider, "fake-model"),
        temperature=float(cfg.get("temperature", 0.0)),
        max_tokens=int(cfg.get("max_tokens", 4000)),
        max_retries=int(cfg.get("max_retries", 2)),
    )


def has_api_key(provider: str) -> bool:
    """True if the key for this provider is set (never returns or logs the key itself)."""
    if provider == "fake":
        return True
    load_dotenv(PROJECT_ROOT / ".env", override=False)
    return bool(os.getenv(KEY_ENV_VARS.get(provider, ""), "").strip())


def extract_json(text: str) -> str:
    """Pull the JSON object out of a model reply.

    Models sometimes wrap JSON in ```json fences or add a sentence before it.
    We strip fences, then take everything from the first '{' to the last '}'.
    """
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.DOTALL)
    if fenced:
        text = fenced.group(1)
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise LLMError("The model reply did not contain a JSON object.")
    return text[start : end + 1]


@dataclass
class LLMClient:
    """Provider-neutral client. Use `complete` for text, `complete_json` for schema-checked data."""

    config: LLMConfig = field(default_factory=load_llm_config)
    fake_reply: FakeReply | None = None  # used only when provider == "fake"
    usage: Usage = field(default_factory=Usage)

    def complete(self, system: str, user: str) -> str:
        """Send one system + user message and return the reply text."""
        provider = self.config.provider
        if provider == "fake":
            return self._fake(system, user)
        if not has_api_key(provider):
            raise LLMError(
                f"No API key found. Set {KEY_ENV_VARS[provider]} in .env (local) "
                "or in the app's Secrets (Streamlit Cloud)."
            )
        if provider == "anthropic":
            return self._anthropic(system, user)
        return self._openai(system, user)

    def complete_json(self, system: str, user: str, schema: type[T]) -> T:
        """Ask for JSON that matches `schema`; validate it and retry with the error if it fails."""
        schema_text = json.dumps(schema.model_json_schema(), indent=1)
        system_full = (
            f"{system}\n\nReply with ONLY one JSON object (no prose, no markdown) "
            f"that matches this JSON schema:\n{schema_text}"
        )
        prompt = user
        last_error = ""
        for _attempt in range(self.config.max_retries + 1):
            reply = self.complete(system_full, prompt)
            try:
                return schema.model_validate_json(extract_json(reply))
            except (LLMError, ValidationError, ValueError) as exc:
                last_error = str(exc)[:1500]
                prompt = (
                    f"{user}\n\nYour previous reply was invalid:\n{last_error}\n"
                    "Return ONLY the corrected JSON object."
                )
        raise LLMError(f"Model did not return valid JSON after retries: {last_error}")

    # ---- provider implementations (SDKs imported lazily so tests need neither) ----

    def _anthropic(self, system: str, user: str) -> str:
        """Call Anthropic's Messages API."""
        import anthropic

        client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from the environment
        try:
            resp = client.messages.create(
                model=self.config.model,
                max_tokens=self.config.max_tokens,
                temperature=self.config.temperature,
                system=system,
                messages=[{"role": "user", "content": user}],
            )
        except anthropic.APIError as exc:
            raise LLMError(f"Anthropic API error: {exc}") from exc
        self.usage.add(resp.usage.input_tokens, resp.usage.output_tokens)
        return "".join(block.text for block in resp.content if block.type == "text")

    def _openai(self, system: str, user: str) -> str:
        """Call OpenAI's Chat Completions API in JSON mode."""
        import openai

        client = openai.OpenAI()  # reads OPENAI_API_KEY from the environment
        kwargs: dict = {
            "model": self.config.model,
            "temperature": self.config.temperature,
            "max_completion_tokens": self.config.max_tokens,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        }
        if "JSON" in system:  # JSON mode needs the word "JSON" in the prompt
            kwargs["response_format"] = {"type": "json_object"}
        try:
            resp = client.chat.completions.create(**kwargs)
        except openai.OpenAIError as exc:
            raise LLMError(f"OpenAI API error: {exc}") from exc
        if resp.usage:
            self.usage.add(resp.usage.prompt_tokens, resp.usage.completion_tokens)
        return resp.choices[0].message.content or ""

    def _fake(self, system: str, user: str) -> str:
        """Return a canned reply (for tests and offline demos)."""
        self.usage.add(len(system + user) // 4, 50)
        if self.fake_reply is None:
            return "{}"
        return self.fake_reply(system, user)


if __name__ == "__main__":
    # Smoke test: `python -m ipodesk.llm` checks your key works with one tiny call.
    cfg = load_llm_config()
    print(f"Provider: {cfg.provider}  Model: {cfg.model}  Key set: {has_api_key(cfg.provider)}")

    class Ping(BaseModel):
        """Tiny schema for the smoke test."""

        status: str

    client = LLMClient(cfg, fake_reply=lambda _s, _u: '{"status": "ok (fake provider)"}')
    try:
        result = client.complete_json("You are a test endpoint.", 'Return {"status": "ok"}.', Ping)
        print("Reply:", result, "| tokens in/out:", client.usage.input_tokens, client.usage.output_tokens)
    except LLMError as err:
        print("Failed:", err)
