"""Endpoint routing, third-party detection, hard errors, and config output."""
import os

import pytest
from unittest.mock import patch

from client import AceToolClient


class TestEndpointResolution:
    """Resolution order: PROMPT_ENHANCER_ENDPOINT > ACE_ENHANCER_ENDPOINT > constructor > default."""

    def test_env_overrides_constructor(self):
        with patch.dict(os.environ, {
            "PROMPT_ENHANCER_ENDPOINT": "claude",
            "ACE_ENHANCER_ENDPOINT": "",
        }, clear=False):
            c = AceToolClient(endpoint="openai")
            assert c.endpoint == "claude"

    def test_new_env_wins_over_legacy_and_constructor(self):
        with patch.dict(os.environ, {
            "PROMPT_ENHANCER_ENDPOINT": "claude",
            "ACE_ENHANCER_ENDPOINT": "openai",
        }, clear=False):
            c = AceToolClient(endpoint="gemini")
            assert c.endpoint == "claude"

    def test_legacy_env_used_when_new_absent(self):
        with patch.dict(os.environ, {
            "PROMPT_ENHANCER_ENDPOINT": "",
            "ACE_ENHANCER_ENDPOINT": "gemini",
        }, clear=False):
            c = AceToolClient()
            assert c.endpoint == "gemini"

    def test_constructor_arg_used_when_no_env(self):
        with patch.dict(os.environ, {
            "PROMPT_ENHANCER_ENDPOINT": "",
            "ACE_ENHANCER_ENDPOINT": "",
        }, clear=False):
            c = AceToolClient(endpoint="openai")
            assert c.endpoint == "openai"

    def test_default_when_nothing_set(self):
        with patch.dict(os.environ, {
            "PROMPT_ENHANCER_ENDPOINT": "",
            "ACE_ENHANCER_ENDPOINT": "",
        }, clear=False):
            c = AceToolClient()
            assert c.endpoint == "new"


class TestIsThirdParty:
    def _client(self, endpoint):
        with patch.dict(os.environ, {
            "PROMPT_ENHANCER_ENDPOINT": "",
            "ACE_ENHANCER_ENDPOINT": "",
        }, clear=False):
            return AceToolClient(endpoint=endpoint)

    def test_codex_is_third_party(self):
        assert self._client("codex")._is_third_party() is True

    def test_claude_is_third_party(self):
        assert self._client("claude")._is_third_party() is True

    def test_new_is_not_third_party(self):
        assert self._client("new")._is_third_party() is False


class TestHardError:
    """Unconfigured third-party endpoints raise immediately, no silent fallback."""

    def _assert_raises(self, endpoint):
        with patch.dict(os.environ, {
            "PROMPT_ENHANCER_ENDPOINT": "",
            "ACE_ENHANCER_ENDPOINT": "",
            "PROMPT_ENHANCER_BASE_URL": "",
            "PROMPT_ENHANCER_TOKEN": "",
        }, clear=False):
            c = AceToolClient(endpoint=endpoint)
            with pytest.raises(ValueError, match="PROMPT_ENHANCER_BASE_URL"):
                c.enhance_prompt("test", "")

    def test_unconfigured_claude_raises(self):
        self._assert_raises("claude")

    def test_unconfigured_codex_raises(self):
        self._assert_raises("codex")


class TestGetConfigExtended:
    def test_get_config_has_extended_fields(self):
        with patch.dict(os.environ, {
            "ACE_API_URL": "http://test",
            "ACE_API_TOKEN": "tok",
            "PROMPT_ENHANCER_ENDPOINT": "claude",
            "ACE_ENHANCER_ENDPOINT": "",
            "PROMPT_ENHANCER_INCLUDE_SEARCH_CONTEXT": "1",
            "PROMPT_ENHANCER_BASE_URL": "http://third",
            "PROMPT_ENHANCER_TOKEN": "tp",
        }, clear=False):
            config = AceToolClient().get_config()
            assert "endpoint_effective" in config
            assert "endpoint_env_ready" in config
            assert "search_context_injection" in config
