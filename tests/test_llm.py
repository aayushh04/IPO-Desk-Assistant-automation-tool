"""Tests for the LLM wrapper, using the offline 'fake' provider (no API key, no cost)."""
import pytest
from pydantic import BaseModel

from ipodesk.llm import LLMClient, LLMConfig, LLMError, extract_json


class Figure(BaseModel):
    """Tiny schema used by these tests."""

    value: float
    page: int


def _fake_client(replies: list[str]) -> LLMClient:
    """Client whose fake provider returns `replies` in order."""
    it = iter(replies)
    cfg = LLMConfig(provider="fake", model="fake-model", max_retries=2)
    return LLMClient(config=cfg, fake_reply=lambda system, user: next(it))


def test_extract_json_strips_code_fences() -> None:
    assert extract_json('Sure!\n```json\n{"a": 1}\n```') == '{"a": 1}'


def test_extract_json_raises_when_no_object() -> None:
    with pytest.raises(LLMError):
        extract_json("no json here")


def test_complete_json_validates_schema() -> None:
    result = _fake_client(['{"value": 105.0, "page": 6}']).complete_json("sys", "user", Figure)
    assert result == Figure(value=105.0, page=6)


def test_complete_json_retries_after_bad_reply() -> None:
    client = _fake_client(["not json", '{"value": "abc"}', '{"value": 1.5, "page": 2}'])
    assert client.complete_json("sys", "user", Figure).page == 2
    assert client.usage.calls == 3


def test_complete_json_gives_up_after_retries() -> None:
    with pytest.raises(LLMError):
        _fake_client(["bad"] * 3).complete_json("sys", "user", Figure)
