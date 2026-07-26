import pathlib


def test_skill_directory_exists():
    skill_dir = pathlib.Path(__file__).parent.parent
    assert skill_dir.exists()
    assert skill_dir.name == "agent-wiki"


def test_scripts_directory_exists():
    scripts_dir = pathlib.Path(__file__).parent.parent / "scripts"
    assert scripts_dir.exists()
    assert scripts_dir.is_dir()


def test_skill_md_exists():
    skill_md = pathlib.Path(__file__).parent.parent / "SKILL.md"
    assert skill_md.exists()
    assert skill_md.is_file()
