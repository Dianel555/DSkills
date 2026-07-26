"""Tests for file CLI commands parameter mapping."""


def test_search_pattern_parameter_mapping():
    """Test that search_pattern function calls tool with correct parameters."""
    from unittest.mock import Mock, patch

    # Mock output_json to avoid side effects
    with patch('tools.output.output_json'):
        from tools.cli import State
        from tools.cli.file import search_pattern

        # Setup mock
        mock_core = Mock()
        State.core = mock_core
        mock_core.call_tool.return_value = {"results": []}

        # Execute
        search_pattern("test_pattern", path=None)

        # Verify - should use substring_pattern, not pattern
        mock_core.call_tool.assert_called_once_with(
            "search_for_pattern",
            substring_pattern="test_pattern",
            relative_path=None,
        )


def test_search_pattern_with_path():
    """Test search with path restriction."""
    from unittest.mock import Mock, patch

    with patch('tools.output.output_json'):
        from tools.cli import State
        from tools.cli.file import search_pattern

        # Setup mock
        mock_core = Mock()
        State.core = mock_core
        mock_core.call_tool.return_value = {"results": []}

        # Execute
        search_pattern("test_pattern", path="src")

        # Verify
        mock_core.call_tool.assert_called_once_with(
            "search_for_pattern",
            substring_pattern="test_pattern",
            relative_path="src",
        )


def test_find_file_parameter_mapping():
    """Test that find_file function calls tool with correct parameters."""
    from unittest.mock import Mock, patch

    with patch('tools.output.output_json'):
        from tools.cli import State
        from tools.cli.file import find_file

        # Setup mock
        mock_core = Mock()
        State.core = mock_core
        mock_core.call_tool.return_value = {"files": []}

        # Execute
        find_file("*.py")

        # Verify - should use file_mask and relative_path="."
        mock_core.call_tool.assert_called_once_with(
            "find_file",
            file_mask="*.py",
            relative_path=".",
        )


def test_list_dir_default_path():
    """Test that list_dir defaults to relative_path='.' when path is None."""
    from unittest.mock import Mock, patch

    with patch('tools.output.output_json'):
        from tools.cli import State
        from tools.cli.file import list_dir

        # Setup mock
        mock_core = Mock()
        State.core = mock_core
        mock_core.call_tool.return_value = {"entries": []}

        # Execute without path
        list_dir(path=None, recursive=False)

        # Verify - should default to relative_path="."
        mock_core.call_tool.assert_called_once_with(
            "list_dir",
            relative_path=".",
            recursive=False,
        )


def test_list_dir_with_path():
    """Test list_dir with explicit path."""
    from unittest.mock import Mock, patch

    with patch('tools.output.output_json'):
        from tools.cli import State
        from tools.cli.file import list_dir

        # Setup mock
        mock_core = Mock()
        State.core = mock_core
        mock_core.call_tool.return_value = {"entries": []}

        # Execute with path
        list_dir(path="src", recursive=True)

        # Verify
        mock_core.call_tool.assert_called_once_with(
            "list_dir",
            relative_path="src",
            recursive=True,
        )
