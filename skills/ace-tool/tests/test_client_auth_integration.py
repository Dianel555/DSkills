"""Tests for AceToolClient authentication integration."""
import json
import os
from pathlib import Path
from unittest.mock import patch

import pytest

try:
    from scripts.client import AceToolClient
except ImportError:
    from client import AceToolClient


class TestClientAuthIntegration:
    """Test AceToolClient uses load_session_auth() correctly."""

    def test_constructor_params_override_all(self, tmp_path):
        """Test constructor parameters take highest priority."""
        session_file = tmp_path / ".augment" / "session.json"
        session_file.parent.mkdir(parents=True)
        session_data = {"accessToken": "file_token", "tenantURL": "https://file.example.com/"}
        session_file.write_text(json.dumps(session_data), encoding="utf-8")

        env_vars = {
            "ACE_API_URL": "https://env.example.com/",
            "ACE_API_TOKEN": "env_token"
        }

        with patch("pathlib.Path.home", return_value=tmp_path):
            with patch.dict(os.environ, env_vars, clear=False):
                client = AceToolClient(base_url="https://constructor.example.com", token="constructor_token")

        assert client.base_url == "https://constructor.example.com"
        assert client.token == "constructor_token"
        assert client.auth_source == "constructor"

    def test_session_json_used_when_no_constructor_params(self, tmp_path):
        """Test session.json used when constructor params not provided."""
        session_file = tmp_path / ".augment" / "session.json"
        session_file.parent.mkdir(parents=True)
        session_data = {"accessToken": "session_token", "tenantURL": "https://session.example.com/"}
        session_file.write_text(json.dumps(session_data), encoding="utf-8")

        with patch("pathlib.Path.home", return_value=tmp_path):
            client = AceToolClient()

        assert client.base_url == "https://session.example.com"
        assert client.token == "session_token"
        assert client.auth_source == "session.json"

    def test_augment_session_auth_fallback(self, tmp_path):
        """Test AUGMENT_SESSION_AUTH used when session.json missing."""
        env_data = {"accessToken": "env_token", "tenantURL": "https://env.example.com/"}
        env_vars = {"AUGMENT_SESSION_AUTH": json.dumps(env_data)}

        with patch("pathlib.Path.home", return_value=tmp_path):
            with patch.dict(os.environ, env_vars, clear=False):
                client = AceToolClient()

        assert client.base_url == "https://env.example.com"
        assert client.token == "env_token"
        assert client.auth_source == "AUGMENT_SESSION_AUTH"

    def test_legacy_env_vars_lowest_priority(self, tmp_path):
        """Test legacy ACE_API_* vars used as last resort."""
        env_vars = {
            "ACE_API_URL": "https://legacy.example.com/",
            "ACE_API_TOKEN": "legacy_token",
            "AUGMENT_SESSION_AUTH": ""
        }

        with patch("pathlib.Path.home", return_value=tmp_path):
            with patch.dict(os.environ, env_vars, clear=False):
                client = AceToolClient()

        assert client.base_url == "https://legacy.example.com"
        assert client.token == "legacy_token"
        assert client.auth_source == "ACE_API_TOKEN"

    def test_partial_constructor_params(self, tmp_path):
        """Test partial constructor params override only those fields."""
        session_file = tmp_path / ".augment" / "session.json"
        session_file.parent.mkdir(parents=True)
        session_data = {"accessToken": "session_token", "tenantURL": "https://session.example.com/"}
        session_file.write_text(json.dumps(session_data), encoding="utf-8")

        with patch("pathlib.Path.home", return_value=tmp_path):
            client = AceToolClient(token="override_token")

        # Only token overridden, base_url from session.json
        assert client.base_url == "https://session.example.com"
        assert client.token == "override_token"
        assert client.auth_source == "constructor"

    def test_no_auth_configured(self, tmp_path):
        """Test client handles missing authentication gracefully."""
        env_vars = {
            "ACE_API_URL": "",
            "ACE_API_TOKEN": "",
            "AUGMENT_SESSION_AUTH": ""
        }

        with patch("pathlib.Path.home", return_value=tmp_path):
            with patch.dict(os.environ, env_vars, clear=False):
                client = AceToolClient()

        assert client.base_url == ""
        assert client.token == ""
        assert client.auth_source == "none"

    def test_auth_source_in_get_config(self, tmp_path):
        """Test get_config() includes auth_source field."""
        session_file = tmp_path / ".augment" / "session.json"
        session_file.parent.mkdir(parents=True)
        session_data = {"accessToken": "token", "tenantURL": "https://example.com/"}
        session_file.write_text(json.dumps(session_data), encoding="utf-8")

        with patch("pathlib.Path.home", return_value=tmp_path):
            client = AceToolClient()
            config = client.get_config()

        assert "auth_source" in config
        assert config["auth_source"] == "session.json"
