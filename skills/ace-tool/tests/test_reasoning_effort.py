"""Reasoning effort control: resolution order and per-endpoint payload injection."""

import os

import pytest
from unittest.mock import patch

from client import AceToolClient

_BASE_ENV = {
    "PROMPT_ENHANCER_ENDPOINT": "",
    "ACE_ENHANCER_ENDPOINT": "",
    "PROMPT_ENHANCER_BASE_URL": "https://h",
    "PROMPT_ENHANCER_TOKEN": "t",
    "PROMPT_ENHANCER_INCLUDE_SEARCH_CONTEXT": "",
    "PROMPT_ENHANCER_REASONING_EFFORT": "",
}


def _make(endpoint, effort_env=None, effort_arg="__unset__"):
    env = dict(_BASE_ENV)
    if effort_env is None:
        env.pop("PROMPT_ENHANCER_REASONING_EFFORT")
    else:
        env["PROMPT_ENHANCER_REASONING_EFFORT"] = effort_env
    with patch.dict(os.environ, env, clear=False):
        kwargs = {} if effort_arg == "__unset__" else {"reasoning_effort": effort_arg}
        return AceToolClient(endpoint=endpoint, **kwargs)


def _captured(client, endpoint):
    """Call the endpoint-specific API with a stubbed _post_json; return its payload."""
    responses = {
        "openai": {"choices": [{"message": {"content": "<augment-enhanced-prompt>x</augment-enhanced-prompt>"}}]},
        "codex": {"output": [{"type": "message", "content": [{"type": "output_text", "text": "x"}]}]},
        "claude": {"content": [{"type": "text", "text": "x"}]},
        "gemini": {"candidates": [{"content": {"parts": [{"text": "x"}]}}]},
    }
    captured = {}

    def fake_post(url, payload, **kw):
        captured.update(payload)
        return responses[endpoint]

    client._post_json = fake_post
    getattr(client, f"_call_{endpoint}_api")("test prompt", [], client._get_third_party_model())
    return captured


class TestEffortResolution:
    def test_default_is_none(self):
        assert _make("openai").reasoning_effort == "none"

    def test_env_override_normalized(self):
        assert _make("openai", effort_env=" HIGH ").reasoning_effort == "high"

    def test_constructor_wins_over_env(self):
        assert _make("openai", effort_env="high", effort_arg="low").reasoning_effort == "low"

    def test_empty_env_sends_nothing(self):
        assert _make("openai", effort_env="").reasoning_effort == ""


class TestPayloadInjection:
    def test_openai_default(self):
        p = _captured(_make("openai"), "openai")
        assert p["reasoning_effort"] == "none"
        assert p["max_tokens"] == 4096

    def test_openai_explicit(self):
        p = _captured(_make("openai", effort_env="high"), "openai")
        assert p["reasoning_effort"] == "high"

    def test_openai_empty_omits_key(self):
        p = _captured(_make("openai", effort_env=""), "openai")
        assert "reasoning_effort" not in p

    def test_codex_default(self):
        p = _captured(_make("codex"), "codex")
        assert p["reasoning"] == {"effort": "none"}

    def test_codex_empty_omits_key(self):
        p = _captured(_make("codex", effort_env=""), "codex")
        assert "reasoning" not in p

    def test_claude_default_disabled(self):
        p = _captured(_make("claude"), "claude")
        assert p["thinking"] == {"type": "disabled"}
        assert "output_config" not in p

    def test_claude_explicit_adaptive_with_effort(self):
        p = _captured(_make("claude", effort_env="high"), "claude")
        assert p["thinking"] == {"type": "adaptive"}
        assert p["output_config"] == {"effort": "high"}

    def test_claude_empty_omits_key(self):
        p = _captured(_make("claude", effort_env=""), "claude")
        assert "thinking" not in p

    def test_gemini_none_maps_to_minimal(self):
        p = _captured(_make("gemini"), "gemini")
        assert p["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "minimal"}

    def test_gemini_explicit_level(self):
        p = _captured(_make("gemini", effort_env="low"), "gemini")
        assert p["generationConfig"]["thinkingConfig"] == {"thinkingLevel": "low"}

    def test_gemini_empty_omits_key(self):
        p = _captured(_make("gemini", effort_env=""), "gemini")
        assert "thinkingConfig" not in p["generationConfig"]
