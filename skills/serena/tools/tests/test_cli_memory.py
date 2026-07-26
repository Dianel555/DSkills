"""Tests for memory CLI commands parameter mapping."""


def test_read_memory_parameter_mapping():
    """Test that read_memory maps name to memory_file_name."""
    from unittest.mock import Mock, patch

    with patch('tools.output.output_json'):
        from tools.cli import State
        from tools.cli.memory import read_memory

        # Setup mock
        mock_core = Mock()
        State.core = mock_core
        mock_core.call_tool.return_value = {"content": "test"}

        # Execute
        read_memory("project_notes")

        # Verify
        mock_core.call_tool.assert_called_once_with(
            "read_memory",
            memory_file_name="project_notes",
        )


def test_write_memory_parameter_mapping():
    """Test that write_memory maps name to memory_name."""
    from unittest.mock import Mock, patch

    with patch('tools.output.output_json'):
        from tools.cli import State
        from tools.cli.memory import write_memory

        # Setup mock
        mock_core = Mock()
        State.core = mock_core
        mock_core.call_tool.return_value = {"success": True}

        # Execute
        write_memory("api_notes", content="test content")

        # Verify
        mock_core.call_tool.assert_called_once_with(
            "write_memory",
            memory_name="api_notes",
            content="test content",
        )


def test_edit_memory_parameter_mapping():
    """Test that edit_memory maps to write_memory with memory_name."""
    from unittest.mock import Mock, patch

    with patch('tools.output.output_json'):
        from tools.cli import State
        from tools.cli.memory import edit_memory

        # Setup mock
        mock_core = Mock()
        State.core = mock_core
        mock_core.call_tool.return_value = {"success": True}

        # Execute
        edit_memory("notes", content="new content")

        # Verify - edit should use write_memory tool
        mock_core.call_tool.assert_called_once_with(
            "write_memory",
            memory_name="notes",
            content="new content",
        )


def test_delete_memory_parameter_mapping():
    """Test that delete_memory maps name to memory_file_name."""
    from unittest.mock import Mock, patch

    with patch('tools.output.output_json'):
        from tools.cli import State
        from tools.cli.memory import delete_memory

        # Setup mock
        mock_core = Mock()
        State.core = mock_core
        mock_core.call_tool.return_value = {"success": True}

        # Execute
        delete_memory("old_notes")

        # Verify
        mock_core.call_tool.assert_called_once_with(
            "delete_memory",
            memory_file_name="old_notes",
        )
