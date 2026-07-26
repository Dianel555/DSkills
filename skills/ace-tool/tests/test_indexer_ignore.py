"""Indexer ignore patterns: .gitignore + .aceignore merge behavior."""
from indexer import Indexer


class TestLoadIgnorePatterns:
    def test_reads_gitignore(self, tmp_path):
        (tmp_path / ".gitignore").write_text("*.pyc\n__pycache__\n", encoding="utf-8")
        idx = Indexer(str(tmp_path), "http://fake.url", "fake-token")
        assert "*.pyc" in idx._gitignore_patterns
        assert "__pycache__" in idx._gitignore_patterns

    def test_reads_aceignore(self, tmp_path):
        (tmp_path / ".aceignore").write_text("secret/\n*.log\n", encoding="utf-8")
        idx = Indexer(str(tmp_path), "http://fake.url", "fake-token")
        assert "secret/" in idx._gitignore_patterns
        assert "*.log" in idx._gitignore_patterns

    def test_merges_both_files(self, tmp_path):
        (tmp_path / ".gitignore").write_text("*.pyc\n", encoding="utf-8")
        (tmp_path / ".aceignore").write_text("*.log\n", encoding="utf-8")
        idx = Indexer(str(tmp_path), "http://fake.url", "fake-token")
        assert "*.pyc" in idx._gitignore_patterns
        assert "*.log" in idx._gitignore_patterns

    def test_skips_comments_and_empty_lines(self, tmp_path):
        (tmp_path / ".aceignore").write_text("# comment\n\n  \nvalid_pattern\n", encoding="utf-8")
        idx = Indexer(str(tmp_path), "http://fake.url", "fake-token")
        assert "valid_pattern" in idx._gitignore_patterns
        assert "# comment" not in idx._gitignore_patterns

    def test_no_files_empty_patterns(self, tmp_path):
        idx = Indexer(str(tmp_path), "http://fake.url", "fake-token")
        assert idx._gitignore_patterns == []

    def test_aceignore_only(self, tmp_path):
        (tmp_path / ".aceignore").write_text("build/\n", encoding="utf-8")
        idx = Indexer(str(tmp_path), "http://fake.url", "fake-token")
        assert "build/" in idx._gitignore_patterns
