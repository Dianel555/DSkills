"""Upload original files and invalidate caches produced by client-side chunking."""

import gzip
import json

import pytest
from indexer import Indexer
from templates import INDEX_DIR, INDEX_FILE


@pytest.mark.parametrize("line_count", [799, 800, 801, 1601])
def test_indexer_sends_one_whole_file_with_original_path(tmp_path, line_count):
    content = "\n".join(f"value_{i} = {i}" for i in range(line_count))
    (tmp_path / "source.py").write_text(content, encoding="utf-8")

    with Indexer(str(tmp_path), "", "") as indexer:
        indexer._load_index()
        assert indexer._scan_and_update()
        assert indexer._pending == [
            {
                "path": "source.py",
                "content": content,
                "blob_name": indexer._hash_blob("source.py", content),
            }
        ]


def test_unchanged_legacy_chunk_cache_is_rebuilt_and_replaced(tmp_path, monkeypatch):
    content = "\n".join(f"value_{i} = {i}" for i in range(801))
    source = tmp_path / "source.py"
    source.write_text(content, encoding="utf-8")
    stat = source.stat()
    lines = content.split("\n")
    with Indexer(str(tmp_path), "", "") as indexer:
        entries = {}
        for index, chunk in enumerate((lines[:800], lines[800:]), start=1):
            path = f"source.py#chunk{index}of2"
            blob_name = indexer._hash_blob(path, "\n".join(chunk))
            entries[blob_name] = {
                "path": path,
                "blob_name": blob_name,
                "mtime": stat.st_mtime,
                "size": stat.st_size,
            }
        cache = tmp_path / INDEX_DIR / INDEX_FILE
        cache.parent.mkdir()
        cache.write_bytes(gzip.compress(json.dumps({"entries": entries, "last_indexed": 1}).encode()))
        uploaded = []
        monkeypatch.setattr(indexer, "_upload_pending", lambda: uploaded.extend(indexer._pending) or True)

        names = indexer.get_blob_names()

        expected = indexer._hash_blob("source.py", content)
        assert names == [expected]
        assert uploaded == [{"path": "source.py", "content": content, "blob_name": expected}]
        assert [entry.path for entry in indexer._index.entries.values()] == ["source.py"]
        saved = json.loads(gzip.decompress(cache.read_bytes()))
        assert isinstance(saved.get("format_version"), int)
        assert set(saved["entries"]) == {expected}


def test_new_cache_reuses_whole_file_with_chunk_in_real_filename(tmp_path, monkeypatch):
    source = tmp_path / "odd#chunk-name.py"
    source.write_text("keyword = 1\n", encoding="utf-8")
    with Indexer(str(tmp_path), "", "") as first:
        names = first.get_blob_names()
    with Indexer(str(tmp_path), "", "") as second:

        def unexpected_read(*args):
            pytest.fail("unchanged file should be reused from the new-format cache")

        monkeypatch.setattr(second, "_process_file", unexpected_read)
        assert second.get_blob_names() == names
