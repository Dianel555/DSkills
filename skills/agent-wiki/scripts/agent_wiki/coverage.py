"""Coverage and gap reporting for wiki sources.

Identifies which sources from the scan set are covered by topics and which
are gaps. Read-only, no file writes, no LLM, no network.
"""

from __future__ import annotations

import unicodedata
from pathlib import Path

from . import config, scanner, wiki_index


def _nfc(text: str) -> str:
    """Normalize to NFC Unicode form."""
    return unicodedata.normalize("NFC", text)


def compute_coverage(vault: str | Path) -> dict:
    """Compute coverage and gaps for the vault.

    Returns dict with:
    - ok: bool
    - covered: int (count of covered sources)
    - gaps: list[dict] (uncovered sources, NFC-sorted by path)
    - coverage_ratio: float ∈ [0, 1] (1.0 when scan set empty)
    """
    vault = Path(vault)

    # Require initialized wiki
    if not config.wiki_root(vault).exists():
        raise ValueError("wiki_not_initialized")

    # Scan for .md sources
    scan_set = set()
    for path in scanner.walk_sources(vault):
        if path.suffix == ".md":
            rel = config.normalize_relpath(path.relative_to(vault).as_posix())
            scan_set.add(_nfc(rel))

    # Collect covered sources from topics
    try:
        data, _ = wiki_index.rebuild(vault)
    except wiki_index.NormalizedPathCollisionError:
        raise ValueError("normalized_path_collision") from None

    covered_set = set()
    for topic_entry in data.get("topics", {}).values():
        for source in topic_entry.get("sources", []):
            covered_set.add(_nfc(source))

    # Compute gaps (scan - covered)
    gaps_set = scan_set - covered_set

    # Build gaps list (sorted)
    gaps = [{"path": path} for path in sorted(gaps_set)]

    # Compute coverage ratio
    coverage_ratio = 1.0 if len(scan_set) == 0 else len(covered_set & scan_set) / len(scan_set)

    return {
        "ok": True,
        "covered": len(covered_set & scan_set),  # Only count scanned sources
        "gaps": gaps,
        "coverage_ratio": coverage_ratio,
    }
