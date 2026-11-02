import pytest
from agent_wiki import boundary, cache, config


@pytest.mark.parametrize("payload", ["new text", b"new bytes"])
def test_atomic_write_does_not_touch_existing_predictable_temp(tmp_path, payload):
    boundary.bind(tmp_path)
    target = tmp_path / "output.txt"
    planted = tmp_path / "output.txt.tmp"
    planted.write_text("untouched", encoding="utf-8")

    config.atomic_write_text(target, payload)

    assert planted.read_text(encoding="utf-8") == "untouched"
    assert target.read_bytes() == (payload.encode() if isinstance(payload, str) else payload)


def test_cache_save_does_not_touch_existing_predictable_temp(tmp_path):
    wiki = tmp_path / "wiki"
    wiki.mkdir()
    planted = wiki / ".wiki-cache.json.tmp"
    planted.write_text("untouched", encoding="utf-8")

    cache.save(tmp_path, {"version": 1, "sources": {}})

    assert planted.read_text(encoding="utf-8") == "untouched"
    assert cache.load(tmp_path) == {"version": 1, "sources": {}}
