"""Tests for SerenaCore context detection."""
import os
from pathlib import Path
from unittest.mock import patch
import tempfile
import shutil


def test_context_detection_claude_code_directory():
    """Test Claude Code detection via .claude directory."""
    from tools.core import SerenaCore

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / ".claude").mkdir()

        core = SerenaCore(project=str(tmppath))
        assert core.context == "claude-code"


def test_context_detection_claude_code_env():
    """Test Claude Code detection via CLAUDECODE environment variable."""
    from tools.core import SerenaCore

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"CLAUDECODE": "1"}):
            core = SerenaCore(project=tmpdir)
            assert core.context == "claude-code"


def test_context_detection_vscode_directory():
    """Test VSCode detection via .vscode directory."""
    from tools.core import SerenaCore

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / ".vscode").mkdir()

        core = SerenaCore(project=str(tmppath))
        assert core.context == "ide"


def test_context_detection_vscode_env():
    """Test VSCode detection via VSCODE_PID environment variable."""
    from tools.core import SerenaCore

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"VSCODE_PID": "12345"}):
            core = SerenaCore(project=tmpdir)
            assert core.context == "ide"


def test_context_detection_jetbrains_directory():
    """Test JetBrains detection via .idea directory."""
    from tools.core import SerenaCore

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / ".idea").mkdir()

        core = SerenaCore(project=str(tmppath))
        assert core.context == "ide"


def test_context_detection_jetbrains_env():
    """Test JetBrains detection via IDEA_INITIAL_DIRECTORY environment variable."""
    from tools.core import SerenaCore

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"IDEA_INITIAL_DIRECTORY": tmpdir}):
            core = SerenaCore(project=tmpdir)
            assert core.context == "ide"


def test_context_detection_codex_directory():
    """Test Codex detection via .codex directory."""
    from tools.core import SerenaCore

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / ".codex").mkdir()

        core = SerenaCore(project=str(tmppath))
        assert core.context == "codex"


def test_context_detection_codex_env():
    """Test Codex detection via CODEX_CLI_SESSION environment variable."""
    from tools.core import SerenaCore

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"CODEX_CLI_SESSION": "test-session"}):
            core = SerenaCore(project=tmpdir)
            assert core.context == "codex"


def test_context_detection_default():
    """Test default context when no markers exist."""
    from tools.core import SerenaCore

    with tempfile.TemporaryDirectory() as tmpdir:
        # Clean environment - remove keys if they exist
        env_backup = {}
        keys_to_remove = ["CLAUDE_CODE_SESSION", "VSCODE_PID", "IDEA_INITIAL_DIRECTORY", "CODEX_CLI_SESSION"]
        for key in keys_to_remove:
            if key in os.environ:
                env_backup[key] = os.environ.pop(key)

        try:
            core = SerenaCore(project=tmpdir)
            assert core.context == "agent"
        finally:
            # Restore environment
            os.environ.update(env_backup)


def test_context_detection_priority_directory_over_env():
    """Test that directory markers take precedence over environment variables."""
    from tools.core import SerenaCore

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        (tmppath / ".claude").mkdir()

        # Set conflicting environment variable
        with patch.dict(os.environ, {"CODEX_CLI_SESSION": "test-session"}):
            core = SerenaCore(project=str(tmppath))
            # Should detect claude-code from directory, not codex from env
            assert core.context == "claude-code"


def test_serena_core_initializes_config_path():
    """Test that SerenaCore initializes config path on creation."""
    from tools.core import SerenaCore

    with tempfile.TemporaryDirectory() as tmpdir:
        with patch.dict(os.environ, {"SERENA_HOME": tmpdir}):
            core = SerenaCore(project=tmpdir)

            # Config file should be created
            config_file = Path(tmpdir) / "serena_config.yml"
            assert config_file.exists()


def test_get_dashboard_info_without_agent_uses_wrapper_state():
    """Test dashboard info fallback when agent is unavailable."""
    from tools.core import SerenaCore

    with tempfile.TemporaryDirectory() as tmpdir:
        core = SerenaCore(project=tmpdir, context="codex", modes=["interactive", "editing"])

        with patch.object(core, "_ensure_agent", side_effect=RuntimeError("agent unavailable")):
            info = core.get_dashboard_info()

        assert info["active_project_path"] == str(Path(tmpdir).resolve())
        assert info["context"] == "codex"
        assert info["active_modes"] == ["editing", "interactive"]
        assert info["active_tools_count"] == 0
        assert "codex" in info["available_contexts"]
        assert "interactive" in info["available_modes"]
