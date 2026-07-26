"""Tests for authentication upgrade: load_session_auth() function."""
import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

try:
    from scripts import utils
    from scripts.utils import load_env, load_session_auth
except ImportError:
    import utils
    from utils import load_env, load_session_auth


class TestLoadSessionAuth:
    """Test load_session_auth() authentication fallback chain."""

    def test_session_json_valid(self, tmp_path):
        """Test loading from valid session.json file."""
        session_file = tmp_path / ".augment" / "session.json"
        session_file.parent.mkdir(parents=True)
        session_data = {
            "accessToken": "token_from_file",
            "tenantURL": "https://file.example.com/",
            "scopes": ["email"]
        }
        session_file.write_text(json.dumps(session_data), encoding="utf-8")

        with patch("pathlib.Path.home", return_value=tmp_path):
            base_url, token, source = load_session_auth()

        assert base_url == "https://file.example.com"
        assert token == "token_from_file"
        assert source == "session.json"

    def test_augment_session_auth_env(self):
        """Test loading from AUGMENT_SESSION_AUTH environment variable."""
        env_data = {
            "accessToken": "token_from_env",
            "tenantURL": "https://env.example.com/"
        }
        with patch.dict(os.environ, {"AUGMENT_SESSION_AUTH": json.dumps(env_data)}, clear=False):
            with patch("pathlib.Path.exists", return_value=False):
                base_url, token, source = load_session_auth()

        assert base_url == "https://env.example.com"
        assert token == "token_from_env"
        assert source == "AUGMENT_SESSION_AUTH"

    def test_legacy_env_fallback(self, tmp_path):
        """Test fallback to legacy ACE_API_URL and ACE_API_TOKEN."""
        env_vars = {
            "ACE_API_URL": "https://legacy.example.com/",
            "ACE_API_TOKEN": "legacy_token",
            "AUGMENT_SESSION_AUTH": ""
        }
        with patch("pathlib.Path.home", return_value=tmp_path):
            with patch.dict(os.environ, env_vars, clear=False):
                base_url, token, source = load_session_auth()

        assert base_url == "https://legacy.example.com"
        assert token == "legacy_token"
        assert source == "ACE_API_TOKEN"

    def test_all_missing_returns_none(self, tmp_path):
        """Test returns (None, None, 'none') when all sources missing."""
        env_vars = {
            "ACE_API_URL": "",
            "ACE_API_TOKEN": "",
            "AUGMENT_SESSION_AUTH": ""
        }
        with patch("pathlib.Path.home", return_value=tmp_path):
            with patch.dict(os.environ, env_vars, clear=False):
                base_url, token, source = load_session_auth()

        assert base_url is None
        assert token is None
        assert source == "none"

    def test_session_json_file_not_found(self, tmp_path):
        """Test graceful handling when session.json doesn't exist."""
        env_data = {"accessToken": "env_token", "tenantURL": "https://env.example.com/"}
        with patch("pathlib.Path.home", return_value=tmp_path):
            with patch.dict(os.environ, {"AUGMENT_SESSION_AUTH": json.dumps(env_data)}, clear=False):
                base_url, token, source = load_session_auth()

        assert base_url == "https://env.example.com"
        assert token == "env_token"
        assert source == "AUGMENT_SESSION_AUTH"

    def test_session_json_invalid_json(self, tmp_path):
        """Test fallback when session.json contains invalid JSON."""
        session_file = tmp_path / ".augment" / "session.json"
        session_file.parent.mkdir(parents=True)
        session_file.write_text("not valid json{", encoding="utf-8")

        env_data = {"accessToken": "fallback_token", "tenantURL": "https://fallback.example.com/"}
        with patch("pathlib.Path.home", return_value=tmp_path):
            with patch.dict(os.environ, {"AUGMENT_SESSION_AUTH": json.dumps(env_data)}, clear=False):
                base_url, token, source = load_session_auth()

        assert base_url == "https://fallback.example.com"
        assert token == "fallback_token"
        assert source == "AUGMENT_SESSION_AUTH"

    def test_session_json_missing_fields(self, tmp_path):
        """Test fallback when session.json missing required fields."""
        session_file = tmp_path / ".augment" / "session.json"
        session_file.parent.mkdir(parents=True)
        session_data = {"scopes": ["email"]}  # Missing accessToken and tenantURL
        session_file.write_text(json.dumps(session_data), encoding="utf-8")

        env_vars = {"ACE_API_URL": "https://legacy.example.com/", "ACE_API_TOKEN": "legacy_token"}
        with patch("pathlib.Path.home", return_value=tmp_path):
            with patch.dict(os.environ, env_vars, clear=True):
                base_url, token, source = load_session_auth()

        assert base_url == "https://legacy.example.com"
        assert token == "legacy_token"
        assert source == "ACE_API_TOKEN"

    def test_session_json_empty_strings(self, tmp_path):
        """Test rejection of empty string values."""
        session_file = tmp_path / ".augment" / "session.json"
        session_file.parent.mkdir(parents=True)
        session_data = {"accessToken": "", "tenantURL": "   "}
        session_file.write_text(json.dumps(session_data), encoding="utf-8")

        env_vars = {"ACE_API_URL": "https://legacy.example.com/", "ACE_API_TOKEN": "legacy_token"}
        with patch("pathlib.Path.home", return_value=tmp_path):
            with patch.dict(os.environ, env_vars, clear=True):
                base_url, token, source = load_session_auth()

        assert base_url == "https://legacy.example.com"
        assert token == "legacy_token"
        assert source == "ACE_API_TOKEN"

    def test_session_json_with_bom(self, tmp_path):
        """Test UTF-8 BOM handling."""
        session_file = tmp_path / ".augment" / "session.json"
        session_file.parent.mkdir(parents=True)
        session_data = {"accessToken": "bom_token", "tenantURL": "https://bom.example.com/"}
        session_file.write_bytes(b'\xef\xbb\xbf' + json.dumps(session_data).encode("utf-8"))

        with patch("pathlib.Path.home", return_value=tmp_path):
            base_url, token, source = load_session_auth()

        assert base_url == "https://bom.example.com"
        assert token == "bom_token"
        assert source == "session.json"

    def test_url_trailing_slash_stripped(self, tmp_path):
        """Test that trailing slashes are removed from URLs."""
        session_file = tmp_path / ".augment" / "session.json"
        session_file.parent.mkdir(parents=True)
        session_data = {"accessToken": "token", "tenantURL": "https://example.com///"}
        session_file.write_text(json.dumps(session_data), encoding="utf-8")

        with patch("pathlib.Path.home", return_value=tmp_path):
            base_url, token, source = load_session_auth()

        assert base_url == "https://example.com"
        assert token == "token"
        assert source == "session.json"


class TestLoadEnv:
    """Test .env loading behavior."""

    def test_loads_only_skill_root_env(self, tmp_path, monkeypatch):
        """Test loading only the skill root .env file."""
        cwd_env = tmp_path / ".env"
        cwd_env.write_text("UNRELATED=value\nPROMPT_ENHANCER_ENDPOINT=wrong\n", encoding="utf-8")

        skill_root = tmp_path / "skill"
        scripts_dir = skill_root / "scripts"
        scripts_dir.mkdir(parents=True)
        skill_env = skill_root / ".env"
        skill_env.write_text("PROMPT_ENHANCER_ENDPOINT=openai\n", encoding="utf-8")

        monkeypatch.chdir(tmp_path)
        monkeypatch.setattr(utils, "__file__", str(scripts_dir / "utils.py"))
        monkeypatch.delenv("UNRELATED", raising=False)
        monkeypatch.delenv("PROMPT_ENHANCER_ENDPOINT", raising=False)

        load_env()

        assert "UNRELATED" not in os.environ
        assert os.environ["PROMPT_ENHANCER_ENDPOINT"] == "openai"
