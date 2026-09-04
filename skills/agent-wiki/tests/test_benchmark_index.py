"""Index performance benchmark (stdlib only, no benchmark framework).

Builds a synthetic vault (100 topics + 5 queries), measures full vs
incremental rebuild. The assertions are loose regression bounds so CI noise
doesn't flake; the printed timings are the record (visible with `pytest -s`).
"""

from __future__ import annotations

import time
from pathlib import Path

from agent_wiki import config, frontmatter, wiki_index

N_TOPICS = 100
N_QUERIES = 5


def _synthetic_vault(tmp_path: Path) -> Path:
    topics = config.topics_dir(tmp_path)
    topics.mkdir(parents=True, exist_ok=True)
    for i in range(N_TOPICS):
        (topics / f"t{i:03d}.md").write_text(
            frontmatter.dump(
                {"title": f"Topic {i}", "sources": [f"src{i}.md"], "summary": "x" * 200},
                "Body text " * 50 + " [[t000]] [[t001]]",
            ),
            encoding="utf-8",
        )
    queries = config.queries_dir(tmp_path)
    queries.mkdir(parents=True, exist_ok=True)
    for i in range(N_QUERIES):
        (queries / f"q{i:03d}.md").write_text(
            frontmatter.dump({"title": f"Query {i}"}, "body " * 20),
            encoding="utf-8",
        )
    return tmp_path


def test_full_vs_incremental_benchmark(tmp_path):
    vault = _synthetic_vault(tmp_path)

    start = time.perf_counter()
    data, errors = wiki_index.rebuild(vault)
    full_elapsed = time.perf_counter() - start
    assert len(data["topics"]) == N_TOPICS
    assert len(data["queries"]) == N_QUERIES
    assert errors == []
    wiki_index.save_index(vault, data)

    start = time.perf_counter()
    data2, errors2 = wiki_index.rebuild(vault, incremental=True)
    incr_elapsed = time.perf_counter() - start
    assert data2["topics"] == data["topics"]
    assert data2["queries"] == data["queries"]
    assert errors2 == []

    print(f"\nfull rebuild ({N_TOPICS} topics): {full_elapsed:.3f}s | "
          f"incremental unchanged: {incr_elapsed:.3f}s | "
          f"speedup: {full_elapsed / incr_elapsed:.1f}x")
    # Loose bounds: reuse must not be slower than re-parsing everything
    assert incr_elapsed <= full_elapsed
    assert full_elapsed / incr_elapsed >= 1.0
