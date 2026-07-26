import json
from pathlib import Path

from agent_wiki import plugins


def _obsidian(tmp_path: Path, community=None, dv_data=None) -> Path:
    cfg = tmp_path / ".obsidian"
    cfg.mkdir()
    if community is not None:
        (cfg / "community-plugins.json").write_text(json.dumps(community), encoding="utf-8")
    if dv_data is not None:
        dv = cfg / "plugins" / "dataview"
        dv.mkdir(parents=True)
        (dv / "data.json").write_text(json.dumps(dv_data), encoding="utf-8")
    return cfg


# --- config dir discovery (walk up) ----------------------------------------

def test_config_dir_found_at_vault(tmp_path):
    cfg = _obsidian(tmp_path)
    assert plugins.obsidian_config_dir(tmp_path) == cfg


def test_config_dir_found_above_vault(tmp_path):
    cfg = _obsidian(tmp_path)
    nested = tmp_path / "记录" / "wiki"
    nested.mkdir(parents=True)
    assert plugins.obsidian_config_dir(nested) == cfg


def test_config_dir_none_when_absent(tmp_path):
    assert plugins.obsidian_config_dir(tmp_path) is None


# --- dataview installed -----------------------------------------------------

def test_dataview_installed_true(tmp_path):
    _obsidian(tmp_path, community=["dataview", "obsidian-banners"])
    assert plugins.dataview_installed(tmp_path) is True


def test_dataview_installed_false_when_absent_from_list(tmp_path):
    _obsidian(tmp_path, community=["obsidian-banners"])
    assert plugins.dataview_installed(tmp_path) is False


def test_dataview_installed_false_when_no_obsidian(tmp_path):
    assert plugins.dataview_installed(tmp_path) is False


def test_dataview_installed_false_on_bad_json(tmp_path):
    cfg = _obsidian(tmp_path)
    (cfg / "community-plugins.json").write_text("{not json", encoding="utf-8")
    assert plugins.dataview_installed(tmp_path) is False


# --- dataviewjs enabled -----------------------------------------------------

def test_dataviewjs_enabled_true(tmp_path):
    _obsidian(tmp_path, dv_data={"enableDataviewJs": True})
    assert plugins.dataviewjs_enabled(tmp_path) is True


def test_dataviewjs_enabled_false_when_flag_off(tmp_path):
    _obsidian(tmp_path, dv_data={"enableDataviewJs": False})
    assert plugins.dataviewjs_enabled(tmp_path) is False


def test_dataviewjs_enabled_false_when_missing(tmp_path):
    _obsidian(tmp_path)
    assert plugins.dataviewjs_enabled(tmp_path) is False


# --- combined gate ----------------------------------------------------------

def test_cards_available_requires_both(tmp_path):
    _obsidian(tmp_path, community=["dataview"], dv_data={"enableDataviewJs": True})
    assert plugins.cards_available(tmp_path) is True


def test_cards_available_false_without_js(tmp_path):
    _obsidian(tmp_path, community=["dataview"], dv_data={"enableDataviewJs": False})
    assert plugins.cards_available(tmp_path) is False


def test_cards_available_false_without_install(tmp_path):
    _obsidian(tmp_path, community=[], dv_data={"enableDataviewJs": True})
    assert plugins.cards_available(tmp_path) is False


def test_cards_available_false_without_obsidian(tmp_path):
    assert plugins.cards_available(tmp_path) is False
