"""Test that the agent_wiki Python package structure exists."""
import pathlib
import importlib.util


def test_agent_wiki_package_exists():
    """Test that agent_wiki package directory exists."""
    package_dir = pathlib.Path(__file__).parent.parent / "scripts" / "agent_wiki"
    assert package_dir.exists()
    assert package_dir.is_dir()


def test_agent_wiki_init_exists():
    """Test that agent_wiki/__init__.py exists."""
    init_file = pathlib.Path(__file__).parent.parent / "scripts" / "agent_wiki" / "__init__.py"
    assert init_file.exists()
    assert init_file.is_file()


def test_agent_wiki_modules_exist():
    """Test that all required modules exist."""
    scripts_dir = pathlib.Path(__file__).parent.parent / "scripts" / "agent_wiki"
    required_modules = [
        "config.py",
        "cache.py",
        "scanner.py",
        "frontmatter.py",
        "cleanup.py",
        "commands.py",
    ]

    for module in required_modules:
        module_path = scripts_dir / module
        assert module_path.exists(), f"Module {module} not found"
        assert module_path.is_file(), f"{module} is not a file"


def test_cli_entry_exists():
    """Test that agent_wiki_cli.py entry point exists."""
    cli_entry = pathlib.Path(__file__).parent.parent / "scripts" / "agent_wiki_cli.py"
    assert cli_entry.exists()
    assert cli_entry.is_file()
