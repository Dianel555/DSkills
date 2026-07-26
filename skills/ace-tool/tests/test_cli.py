"""CLI command behavior: index auth resolution, enhance error exit codes."""
import json
import os
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

try:
    from scripts import ace_cli
except ImportError:
    import ace_cli


def _index_args(project_root):
    return SimpleNamespace(api_url=None, token=None, endpoint=None, project_root=str(project_root))


class TestIndexAuth:
    """Test cmd_index resolves auth via the full session chain, not legacy vars only."""

    def test_index_accepts_augment_session_auth(self, tmp_path):
        """Regression: index must work with AUGMENT_SESSION_AUTH (new session format)."""
        env_data = {"accessToken": "session_token", "tenantURL": "https://session.example.com/"}
        env_vars = {"AUGMENT_SESSION_AUTH": json.dumps(env_data), "ACE_API_URL": "", "ACE_API_TOKEN": ""}

        captured = {}

        class FakeIndexer:
            def __init__(self, project_root, base_url, token):
                captured["base_url"] = base_url
                captured["token"] = token
                self.root = project_root
                self._index = SimpleNamespace(last_indexed=0.0)

            def get_blob_names(self):
                return ["blob1", "blob2"]

        with patch("pathlib.Path.home", return_value=tmp_path):
            with patch.dict(os.environ, env_vars, clear=False):
                with patch.object(ace_cli, "Indexer", FakeIndexer):
                    ace_cli.cmd_index(_index_args(tmp_path))

        assert captured["base_url"] == "https://session.example.com"
        assert captured["token"] == "session_token"

    def test_index_errors_when_no_auth(self, tmp_path, capsys):
        """Index exits with a clear error when no auth source is configured."""
        env_vars = {"AUGMENT_SESSION_AUTH": "", "ACE_API_URL": "", "ACE_API_TOKEN": ""}

        with patch("pathlib.Path.home", return_value=tmp_path):
            with patch.dict(os.environ, env_vars, clear=False):
                with pytest.raises(SystemExit) as exc:
                    ace_cli.cmd_index(_index_args(tmp_path))

        assert exc.value.code == 1
        err = json.loads(capsys.readouterr().err)
        assert "authentication" in err["error"].lower()


class TestCmdEnhancePromptError:
    """cmd_enhance_prompt exits 1 when enhancement returns an error dict."""

    def test_error_exits_with_code_1(self):
        args = MagicMock()
        args.no_interactive = True
        args.prompt = "test"
        args.history = ""
        args.history_file = None
        args.project_root = None
        args.api_url = None
        args.token = None
        args.endpoint = "new"

        with patch.dict(os.environ, {"ACE_API_URL": "", "ACE_API_TOKEN": ""}, clear=False):
            with patch.object(ace_cli, "AceToolClient") as MockClient:
                MockClient.return_value.enhance_prompt.return_value = {"error": "test error"}
                with pytest.raises(SystemExit) as exc_info:
                    ace_cli.cmd_enhance_prompt(args)
                assert exc_info.value.code == 1
