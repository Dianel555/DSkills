"""Search context injection: env toggle, normalization, prompt wrapping, guards."""
import os

import pytest
from unittest.mock import patch

from client import AceToolClient


class TestShouldIncludeSearchContext:
    def _check(self, env_val, expected):
        with patch.dict(os.environ, {
            "PROMPT_ENHANCER_ENDPOINT": "",
            "ACE_ENHANCER_ENDPOINT": "",
            "PROMPT_ENHANCER_INCLUDE_SEARCH_CONTEXT": env_val,
        }, clear=False):
            assert AceToolClient()._should_include_search_context() is expected

    def test_true_values(self):
        for val in ("1", "true", "yes", "on", " True ", " YES ", " ON "):
            self._check(val, True)

    def test_false_values(self):
        for val in ("0", "false", "no", "off", "", " "):
            self._check(val, False)


class TestNormalizeSearchContext:
    def _normalize(self, text):
        return AceToolClient._normalize_search_context(text)

    def test_empty_returns_placeholder(self):
        from templates import NO_RELEVANT_CODE_CONTEXT
        assert self._normalize("") == NO_RELEVANT_CODE_CONTEXT

    def test_whitespace_returns_placeholder(self):
        from templates import NO_RELEVANT_CODE_CONTEXT
        assert self._normalize("   ") == NO_RELEVANT_CODE_CONTEXT

    def test_normal_text_passthrough(self):
        assert self._normalize("some code context") == "some code context"

    def test_exact_limit_no_truncation(self):
        from templates import SEARCH_CONTEXT_CHAR_LIMIT
        result = self._normalize("a" * SEARCH_CONTEXT_CHAR_LIMIT)
        assert len(result) == SEARCH_CONTEXT_CHAR_LIMIT
        assert "[codebase_context truncated" not in result

    def test_over_limit_truncated(self):
        from templates import SEARCH_CONTEXT_CHAR_LIMIT
        result = self._normalize("a" * (SEARCH_CONTEXT_CHAR_LIMIT + 1))
        assert "[codebase_context truncated for length]" in result


class TestBuildPromptWithSearchContext:
    def _build(self, original, ctx):
        return AceToolClient._build_prompt_with_search_context(original, ctx)

    def test_contains_codebase_context_tag(self):
        result = self._build("my prompt", "some context")
        assert "<codebase_context>" in result
        assert "</codebase_context>" in result

    def test_contains_original_request_tag(self):
        result = self._build("my prompt", "some context")
        assert "<original_request>" in result
        assert "</original_request>" in result

    def test_original_and_context_preserved(self):
        result = self._build("my prompt", "some context")
        assert "my prompt" in result
        assert "some context" in result


class TestMaybeInjectSearchContext:
    def test_missing_project_root_raises(self):
        with patch.dict(os.environ, {
            "PROMPT_ENHANCER_ENDPOINT": "claude",
            "ACE_ENHANCER_ENDPOINT": "",
            "PROMPT_ENHANCER_INCLUDE_SEARCH_CONTEXT": "1",
            "PROMPT_ENHANCER_BASE_URL": "https://api.example.com",
            "PROMPT_ENHANCER_TOKEN": "tok",
            "ACE_API_URL": "https://ace.example.com",
            "ACE_API_TOKEN": "ace-tok",
        }, clear=False):
            c = AceToolClient(endpoint="claude")
            with pytest.raises(ValueError, match="project"):
                c._maybe_inject_search_context("claude", "test prompt", None)

    def test_non_third_party_returns_original(self):
        with patch.dict(os.environ, {
            "PROMPT_ENHANCER_ENDPOINT": "",
            "ACE_ENHANCER_ENDPOINT": "",
            "PROMPT_ENHANCER_INCLUDE_SEARCH_CONTEXT": "1",
        }, clear=False):
            c = AceToolClient(endpoint="new")
            assert c._maybe_inject_search_context("new", "test prompt", "/some/path") == "test prompt"

    def test_disabled_returns_original(self):
        with patch.dict(os.environ, {
            "PROMPT_ENHANCER_ENDPOINT": "claude",
            "ACE_ENHANCER_ENDPOINT": "",
            "PROMPT_ENHANCER_INCLUDE_SEARCH_CONTEXT": "0",
        }, clear=False):
            c = AceToolClient(endpoint="claude")
            assert c._maybe_inject_search_context("claude", "test prompt", "/some/path") == "test prompt"
