"""In-process tests for gen-home's REST-aware write and managed-block merge.

These monkeypatch ``commands.obsidian_api`` / ``commands.plugins`` / ``commands.emit``;
the subprocess ``run_cli`` path in test_home.py cannot reach in-process patches.
"""

import json
import types

import pytest
from agent_wiki import commands, config, home


def _args(vault, cards="auto", no_rest=False):
    return types.SimpleNamespace(vault=str(vault), cards=cards, no_rest=no_rest)


@pytest.fixture
def initialized(tmp_path):
    commands.cmd_init(_args(tmp_path))
    return tmp_path


@pytest.fixture
def capture_emit(monkeypatch):
    payloads = []
    monkeypatch.setattr(commands, "emit", lambda payload: payloads.append(payload))
    return payloads


def _idx(vault):
    return (config.wiki_root(vault) / "index.md").read_text(encoding="utf-8")


def test_atomic_by_default_when_api_unavailable(initialized, capture_emit, monkeypatch):
    monkeypatch.setattr(commands.obsidian_api, "available", lambda timeout=2.0: False)
    commands.cmd_gen_home(_args(initialized))
    payload = capture_emit[-1]
    assert payload["write_via"] == "atomic"
    assert payload["path"] == "wiki/index.md"
    assert payload["cards"] is False  # no .obsidian under tmp_path
    text = _idx(initialized)
    assert text == home.render_skeleton(initialized, False)
    assert home.AUTO_START in text


def test_rest_bootstraps_identity_before_probe(initialized, capture_emit, monkeypatch, capsys):
    monkeypatch.setenv("AGENT_WIKI_OBSIDIAN_API_KEY", "k")
    monkeypatch.delenv("AGENT_WIKI_OBSIDIAN_VAULT_ID_PATH", raising=False)
    monkeypatch.delenv("AGENT_WIKI_OBSIDIAN_VAULT_ID", raising=False)

    def forbidden(*a, **k):
        raise AssertionError("identity must be checked before the REST availability probe")

    monkeypatch.setattr(commands.obsidian_api, "available", forbidden)
    with pytest.raises(SystemExit):
        commands.cmd_gen_home(_args(initialized))

    payload = json.loads(capsys.readouterr().err)
    env = payload["env"]
    assert payload["error"] == "obsidian_vault_identity_setup_required"
    assert set(env) == {"AGENT_WIKI_OBSIDIAN_VAULT_ID_PATH", "AGENT_WIKI_OBSIDIAN_VAULT_ID"}
    assert env["AGENT_WIKI_OBSIDIAN_VAULT_ID"]
    marker = config.wiki_root(initialized) / env["AGENT_WIKI_OBSIDIAN_VAULT_ID_PATH"].split("/")[-1]
    assert marker.read_text(encoding="utf-8") == env["AGENT_WIKI_OBSIDIAN_VAULT_ID"]


def test_rest_identity_bootstrap_does_not_overwrite_marker(initialized, capture_emit, monkeypatch, capsys):
    existing = config.wiki_root(initialized) / ".agent-wiki-vault-id.md"
    existing.write_text("old-marker", encoding="utf-8")
    monkeypatch.setenv("AGENT_WIKI_OBSIDIAN_API_KEY", "k")
    monkeypatch.delenv("AGENT_WIKI_OBSIDIAN_VAULT_ID_PATH", raising=False)
    monkeypatch.delenv("AGENT_WIKI_OBSIDIAN_VAULT_ID", raising=False)
    monkeypatch.setattr(commands.obsidian_api, "available", lambda timeout=2.0: False)

    with pytest.raises(SystemExit):
        commands.cmd_gen_home(_args(initialized))

    payload = json.loads(capsys.readouterr().err)
    generated = config.wiki_root(initialized) / payload["env"]["AGENT_WIKI_OBSIDIAN_VAULT_ID_PATH"].split("/")[-1]
    assert existing.read_text(encoding="utf-8") == "old-marker"
    assert generated != existing
    assert generated.read_text(encoding="utf-8") == payload["env"]["AGENT_WIKI_OBSIDIAN_VAULT_ID"]


def test_rest_identity_bootstrap_uses_obsidian_root_prefix(tmp_path, capture_emit, monkeypatch, capsys):
    (tmp_path / ".obsidian").mkdir()
    vault = tmp_path / "nested"
    vault.mkdir()
    commands.cmd_init(_args(vault))
    monkeypatch.setenv("AGENT_WIKI_OBSIDIAN_API_KEY", "k")
    monkeypatch.delenv("AGENT_WIKI_OBSIDIAN_VAULT_ID_PATH", raising=False)
    monkeypatch.delenv("AGENT_WIKI_OBSIDIAN_VAULT_ID", raising=False)
    monkeypatch.setattr(commands.obsidian_api, "available", lambda timeout=2.0: False)

    with pytest.raises(SystemExit):
        commands.cmd_gen_home(_args(vault))

    payload = json.loads(capsys.readouterr().err)
    assert payload["env"]["AGENT_WIKI_OBSIDIAN_VAULT_ID_PATH"].startswith("nested/wiki/")
    assert (config.wiki_root(vault) / payload["env"]["AGENT_WIKI_OBSIDIAN_VAULT_ID_PATH"].split("/")[-1]).exists()


def test_uses_rest_when_available(initialized, capture_emit, monkeypatch):
    monkeypatch.setenv("AGENT_WIKI_OBSIDIAN_API_KEY", "k")
    monkeypatch.setenv("AGENT_WIKI_OBSIDIAN_VAULT_ID_PATH", "wiki/.agent-wiki-vault-id.md")
    monkeypatch.setenv("AGENT_WIKI_OBSIDIAN_VAULT_ID", "vault-one")
    monkeypatch.setattr(commands.obsidian_api, "available", lambda timeout=2.0: True)
    calls = {}
    monkeypatch.setattr(commands.obsidian_api, "put_file",
                        lambda vault_rel, text, timeout=10.0, **kwargs: calls.update(vault_rel=vault_rel, text=text) or True)
    commands.cmd_gen_home(_args(initialized))
    assert capture_emit[-1]["write_via"] == "rest"
    assert calls["vault_rel"] == "wiki/index.md"  # no .obsidian ancestor -> empty prefix
    assert calls["text"] == home.render_skeleton(initialized, False)
    # fake PUT never touched disk -> index.md keeps the init placeholder
    assert _idx(initialized) == "# Wiki Index\n\n"


def test_no_rest_skips_api_entirely(initialized, capture_emit, monkeypatch):
    def forbidden(*a, **k):
        raise AssertionError("REST API must not be touched with --no-rest")

    monkeypatch.setattr(commands.obsidian_api, "available", forbidden)
    monkeypatch.setattr(commands.obsidian_api, "put_file", forbidden)
    commands.cmd_gen_home(_args(initialized, no_rest=True))
    assert capture_emit[-1]["write_via"] == "atomic"
    assert _idx(initialized) == home.render_skeleton(initialized, False)


def test_rest_write_failure_does_not_fall_back_to_atomic(initialized, capture_emit, monkeypatch):
    monkeypatch.setenv("AGENT_WIKI_OBSIDIAN_API_KEY", "k")
    monkeypatch.setenv("AGENT_WIKI_OBSIDIAN_VAULT_ID_PATH", "wiki/.agent-wiki-vault-id.md")
    monkeypatch.setenv("AGENT_WIKI_OBSIDIAN_VAULT_ID", "vault-one")
    monkeypatch.setattr(commands.obsidian_api, "available", lambda timeout=2.0: True)
    monkeypatch.setattr(commands.obsidian_api, "put_file", lambda vault_rel, text, timeout=10.0, **kwargs: False)
    with pytest.raises(SystemExit):
        commands.cmd_gen_home(_args(initialized))
    assert _idx(initialized) == "# Wiki Index\n\n"


def test_obsidian_prefix_in_rest_path(tmp_path, capture_emit, monkeypatch):
    # vault nested under a folder containing .obsidian -> prefix must appear in PUT path
    (tmp_path / ".obsidian").mkdir()
    vault = tmp_path / "记录"
    vault.mkdir()
    commands.cmd_init(_args(vault))
    monkeypatch.setenv("AGENT_WIKI_OBSIDIAN_API_KEY", "k")
    monkeypatch.setenv("AGENT_WIKI_OBSIDIAN_VAULT_ID_PATH", "wiki/.agent-wiki-vault-id.md")
    monkeypatch.setenv("AGENT_WIKI_OBSIDIAN_VAULT_ID", "vault-one")
    monkeypatch.setattr(commands.obsidian_api, "available", lambda timeout=2.0: True)
    calls = {}
    monkeypatch.setattr(commands.obsidian_api, "put_file",
                        lambda vault_rel, text, timeout=10.0, **kwargs: calls.update(vault_rel=vault_rel) or True)
    commands.cmd_gen_home(_args(vault))
    assert calls["vault_rel"] == "记录/wiki/index.md"


# --- cards resolution -------------------------------------------------------

def test_cards_auto_follows_detection(initialized, capture_emit, monkeypatch):
    monkeypatch.setattr(commands.obsidian_api, "available", lambda timeout=2.0: False)
    monkeypatch.setattr(commands.plugins, "cards_available", lambda vault: True)
    commands.cmd_gen_home(_args(initialized, cards="auto"))
    assert capture_emit[-1]["cards"] is True
    assert "```dataviewjs" in _idx(initialized)


def test_cards_off_overrides_positive_detection(initialized, capture_emit, monkeypatch):
    monkeypatch.setattr(commands.obsidian_api, "available", lambda timeout=2.0: False)
    monkeypatch.setattr(commands.plugins, "cards_available", lambda vault: True)
    commands.cmd_gen_home(_args(initialized, cards="off"))
    assert capture_emit[-1]["cards"] is False
    assert "```dataviewjs" not in _idx(initialized)


def test_cards_on_overrides_negative_detection(initialized, capture_emit, monkeypatch):
    monkeypatch.setattr(commands.obsidian_api, "available", lambda timeout=2.0: False)
    monkeypatch.setattr(commands.plugins, "cards_available", lambda vault: False)
    commands.cmd_gen_home(_args(initialized, cards="on"))
    assert capture_emit[-1]["cards"] is True
    assert "```dataviewjs" in _idx(initialized)


def test_merge_preserves_prose_in_process(initialized, capture_emit, monkeypatch):
    monkeypatch.setattr(commands.obsidian_api, "available", lambda timeout=2.0: False)
    custom = f"# Wiki Index\n\n手写散文。\n\n{home.AUTO_START}\n\nSTALE\n\n{home.AUTO_END}\n"
    (config.wiki_root(initialized) / "index.md").write_text(custom, encoding="utf-8")
    commands.cmd_gen_home(_args(initialized, cards="on"))
    text = _idx(initialized)
    assert "手写散文。" in text
    assert "STALE" not in text
    assert "```dataviewjs" in text
