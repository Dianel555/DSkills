import json
import unicodedata

import pytest
from agent_wiki import config


def test_resolve_vault_prefers_argument_over_env(tmp_path, monkeypatch):
    arg_vault = tmp_path / "arg"
    env_vault = tmp_path / "env"
    arg_vault.mkdir()
    env_vault.mkdir()
    monkeypatch.setenv("AGENT_WIKI_VAULT", str(env_vault))

    assert config.resolve_vault(str(arg_vault)) == arg_vault.resolve()


def test_resolve_vault_uses_env_when_argument_missing(tmp_path, monkeypatch):
    vault = tmp_path / "vault"
    vault.mkdir()
    monkeypatch.setenv("AGENT_WIKI_VAULT", str(vault))

    assert config.resolve_vault(None) == vault.resolve()


def test_resolve_vault_requires_path(monkeypatch, capsys):
    monkeypatch.delenv("AGENT_WIKI_VAULT", raising=False)

    with pytest.raises(SystemExit) as exc:
        config.resolve_vault(None)

    assert exc.value.code == 2
    assert json.loads(capsys.readouterr().err) == {
        "error": "vault path required",
        "hint": "pass --vault PATH or set AGENT_WIKI_VAULT",
    }


def test_resolve_vault_rejects_missing_path(tmp_path, capsys):
    missing = tmp_path / "missing"

    with pytest.raises(SystemExit) as exc:
        config.resolve_vault(str(missing))

    assert exc.value.code == 2
    err = json.loads(capsys.readouterr().err)
    assert err["error"] == "vault not found"
    assert err["path"] == str(missing.resolve())


def test_wiki_paths_are_absolute(tmp_path):
    vault = tmp_path.resolve()

    assert config.wiki_root(vault) == vault / "wiki"
    assert config.cache_path(vault) == vault / "wiki" / ".wiki-cache.json"
    assert config.topics_dir(vault) == vault / "wiki" / "topics"
    assert config.archive_dir(vault) == vault / "wiki" / "_archived"


def test_to_rel_posix_normalizes_unicode_and_separators(tmp_path):
    name_nfd = "café.md"
    abs_path = tmp_path / "笔记" / name_nfd
    expected = "笔记/café.md"

    result = config.to_rel_posix(abs_path, tmp_path)

    assert unicodedata.normalize("NFC", result) == result
    assert result == expected
