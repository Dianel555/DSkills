"""Tests for dashboard CLI commands."""


def test_dashboard_info_outputs_result_wrapper():
    """Test that dashboard info wraps output under result key."""
    from unittest.mock import Mock, patch

    with patch('tools.cli.dashboard.output_json') as mock_output:
        from tools.cli import State
        from tools.cli.dashboard import info

        mock_core = Mock()
        State.core = mock_core
        mock_core.get_dashboard_info.return_value = {"context": "agent"}

        info()

        mock_core.get_dashboard_info.assert_called_once_with()
        mock_output.assert_called_once_with({"result": {"context": "agent"}})


def test_dashboard_tools_outputs_active_and_available():
    """Test dashboard tools command output structure."""
    from unittest.mock import Mock, patch, call

    with patch('tools.cli.dashboard.output_json') as mock_output:
        from tools.cli import State
        from tools.cli.dashboard import tools

        mock_core = Mock()
        State.core = mock_core
        mock_core.list_tools.side_effect = [["read_memory"], ["read_memory", "find_symbol"]]

        tools()

        mock_core.list_tools.assert_has_calls([call(scope="active"), call(scope="all")])
        mock_output.assert_called_once_with(
            {
                "result": {
                    "active_count": 1,
                    "active": ["read_memory"],
                    "available_count": 2,
                    "available": ["read_memory", "find_symbol"],
                }
            }
        )


def test_dashboard_modes_outputs_active_and_available():
    """Test dashboard modes command output structure."""
    from unittest.mock import Mock, patch, call

    with patch('tools.cli.dashboard.output_json') as mock_output:
        from tools.cli import State
        from tools.cli.dashboard import modes

        mock_core = Mock()
        State.core = mock_core
        mock_core.list_modes.side_effect = [["interactive"], ["interactive", "editing"]]

        modes()

        mock_core.list_modes.assert_has_calls([call(scope="active"), call(scope="all")])
        mock_output.assert_called_once_with(
            {"result": {"active": ["interactive"], "available": ["interactive", "editing"]}}
        )


def test_dashboard_contexts_outputs_active_and_available():
    """Test dashboard contexts command output structure."""
    from unittest.mock import Mock, patch, call

    with patch('tools.cli.dashboard.output_json') as mock_output:
        from tools.cli import State
        from tools.cli.dashboard import contexts

        mock_core = Mock()
        State.core = mock_core
        mock_core.list_contexts.side_effect = [["codex"], ["agent", "claude-code", "codex", "ide"]]

        contexts()

        mock_core.list_contexts.assert_has_calls([call(scope="active"), call(scope="all")])
        mock_output.assert_called_once_with(
            {
                "result": {
                    "active": ["codex"],
                    "available": ["agent", "claude-code", "codex", "ide"],
                }
            }
        )
