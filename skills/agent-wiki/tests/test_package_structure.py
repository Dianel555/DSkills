"""Test that the agent_wiki Python package structure exists."""
import importlib.util
import pathlib
import subprocess
import sys
import tomllib
import zipfile

import pytest


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


def test_pyproject_packages_top_level_cli_module():
    """The wheel must include the legacy CLI module used by agent_wiki.cli."""
    pyproject = pathlib.Path(__file__).parent.parent / "pyproject.toml"
    text = pyproject.read_text(encoding="utf-8")
    assert 'py-modules = ["agent_wiki_cli"]' in text


def test_pyproject_uses_non_deprecated_license_metadata():
    """Wheel metadata must not rely on setuptools' deprecated license table/classifier."""
    pyproject = pathlib.Path(__file__).parent.parent / "pyproject.toml"
    data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
    project = data["project"]
    assert project["license"] == "MIT"
    assert not any(value.startswith("License ::") for value in project.get("classifiers", []))


def test_built_wheel_exposes_importable_cli(tmp_path):
    """A clean wheel must carry the legacy module used by the console entry point."""
    if importlib.util.find_spec("build") is None:
        pytest.skip("build is not installed")

    package_dir = pathlib.Path(__file__).parent.parent
    result = subprocess.run(
        [sys.executable, "-m", "build", "--wheel", "--no-isolation", "--outdir", str(tmp_path)],
        cwd=package_dir,
        text=True,
        capture_output=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr

    wheels = list(tmp_path.glob("*.whl"))
    assert len(wheels) == 1
    with zipfile.ZipFile(wheels[0]) as archive:
        names = set(archive.namelist())
        assert "agent_wiki_cli.py" in names
        assert "agent_wiki/cli.py" in names
        unpacked = tmp_path / "unpacked"
        archive.extractall(unpacked)

    smoke = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import sys; sys.path.insert(0, sys.argv[1]); from agent_wiki.cli import main; main([\"--help\"])",
            str(unpacked),
        ],
        text=True,
        capture_output=True,
    )
    assert smoke.returncode == 0, smoke.stdout + smoke.stderr
    assert "usage:" in smoke.stdout
