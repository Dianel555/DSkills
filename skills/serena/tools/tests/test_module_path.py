"""Regression test for module path fix.

This test ensures that the serena tools can be executed from the serena root directory
using 'python -m tools' command, which is the correct usage after skill installation.

Issue: Previously, SKILL.md and README.md used 'python -m skills.serena.tools' which
assumed execution from the parent directory of skills/, causing ModuleNotFoundError
when executed from the serena root directory.

Fix: Changed all command examples to 'python -m tools' for execution from serena root.
"""
import subprocess
import sys
from pathlib import Path


def test_module_execution_from_serena_root():
    """Test that 'python -m tools' works from serena root directory."""
    serena_root = Path(__file__).parent.parent.parent

    # Test basic command execution
    result = subprocess.run(
        [sys.executable, "-m", "tools", "--help"],
        cwd=serena_root,
        capture_output=True,
        text=True,
        timeout=10
    )

    assert result.returncode == 0, f"Command failed with: {result.stderr}"
    assert "serena" in result.stdout.lower(), "Help text should mention serena"


def test_symbol_command_execution():
    """Test that symbol commands work correctly."""
    serena_root = Path(__file__).parent.parent.parent

    result = subprocess.run(
        [sys.executable, "-m", "tools", "symbol", "--help"],
        cwd=serena_root,
        capture_output=True,
        text=True,
        timeout=10
    )

    assert result.returncode == 0, f"Symbol command failed: {result.stderr}"
    assert "symbol" in result.stdout.lower()


def test_dashboard_command_execution():
    """Test that dashboard commands work correctly."""
    serena_root = Path(__file__).parent.parent.parent

    result = subprocess.run(
        [sys.executable, "-m", "tools", "dashboard", "info"],
        cwd=serena_root,
        capture_output=True,
        text=True,
        timeout=10
    )

    assert result.returncode == 0, f"Dashboard command failed: {result.stderr}"
    # Should return JSON output
    assert "{" in result.stdout


def test_documentation_uses_correct_module_path():
    """Test that documentation files use 'python -m tools' instead of 'python -m skills.serena.tools'."""
    serena_root = Path(__file__).parent.parent.parent

    # Check SKILL.md
    skill_md = (serena_root / "SKILL.md").read_text(encoding="utf-8")
    assert "skills.serena.tools" not in skill_md, "SKILL.md should not contain 'skills.serena.tools'"
    assert "python -m tools" in skill_md, "SKILL.md should contain 'python -m tools'"

    # Check README.md
    readme_md = (serena_root / "README.md").read_text(encoding="utf-8")
    assert "skills.serena.tools" not in readme_md, "README.md should not contain 'skills.serena.tools'"
    assert "python -m tools" in readme_md, "README.md should contain 'python -m tools'"


if __name__ == "__main__":
    test_module_execution_from_serena_root()
    test_symbol_command_execution()
    test_dashboard_command_execution()
    test_documentation_uses_correct_module_path()
    print("✅ All regression tests passed!")
