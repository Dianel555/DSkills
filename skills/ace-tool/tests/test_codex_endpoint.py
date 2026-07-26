"""Codex endpoint: Responses API output parsing and model resolution."""
import os

import pytest
from unittest.mock import patch

from client import AceToolClient


class TestExtractCodexOutputText:
    def _extract(self, api_response):
        return AceToolClient._extract_codex_output_text(api_response)

    def test_final_answer_priority(self):
        resp = {
            "output": [
                {"type": "message", "phase": "thinking", "content": [
                    {"type": "output_text", "text": "thinking text"}
                ]},
                {"type": "message", "phase": "final_answer", "content": [
                    {"type": "output_text", "text": "final text"}
                ]},
            ]
        }
        assert self._extract(resp) == "final text"

    def test_multi_part_concat(self):
        resp = {
            "output": [
                {"type": "message", "phase": "final_answer", "content": [
                    {"type": "output_text", "text": "part1"},
                    {"type": "output_text", "text": "part2"},
                ]},
            ]
        }
        assert self._extract(resp) == "part1\npart2"

    def test_refusal_raises(self):
        resp = {
            "output": [
                {"type": "message", "content": [
                    {"type": "refusal", "refusal": "I cannot do that"}
                ]},
            ]
        }
        with pytest.raises(RuntimeError, match="Codex API refusal"):
            self._extract(resp)

    def test_refusal_plus_text_returns_text(self):
        resp = {
            "output": [
                {"type": "message", "content": [
                    {"type": "refusal", "refusal": "refused"},
                    {"type": "output_text", "text": "actual output"},
                ]},
            ]
        }
        assert self._extract(resp) == "actual output"

    def test_no_output_raises(self):
        with pytest.raises(RuntimeError, match="no output_text"):
            self._extract({"output": []})

    def test_empty_text_ignored(self):
        resp = {
            "output": [
                {"type": "message", "content": [
                    {"type": "output_text", "text": "  "},
                    {"type": "output_text", "text": "real"},
                ]},
            ]
        }
        assert self._extract(resp) == "real"

    def test_null_content_raises(self):
        resp = {"output": [{"type": "message", "content": None}]}
        with pytest.raises(RuntimeError, match="no output_text"):
            self._extract(resp)


class TestCodexModelResolution:
    def test_codex_default_model(self):
        with patch.dict(os.environ, {
            "PROMPT_ENHANCER_ENDPOINT": "",
            "ACE_ENHANCER_ENDPOINT": "",
            "PROMPT_ENHANCER_MODEL": "",
        }, clear=False):
            c = AceToolClient(endpoint="codex")
            from templates import DEFAULT_CODEX_MODEL
            assert c._get_third_party_model() == DEFAULT_CODEX_MODEL
