"""Shared types and configuration for the literature searcher package."""

from __future__ import annotations

import os
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional


SKILL_DIR = Path(__file__).resolve().parent.parent
SKILL_DATA_DIR = SKILL_DIR / "data"


def _load_dotenv(path: Path) -> None:
    """Load simple KEY=VALUE entries without overriding the process environment."""

    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return

    for raw_line in lines:
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            continue
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


_load_dotenv(SKILL_DIR / ".env")

CROSSREF_API = "https://api.crossref.org"
OPENALEX_API = "https://api.openalex.org"
SCOPUS_API = "https://api.elsevier.com/content/search/scopus"
SEMANTIC_SCHOLAR_API = "https://api.semanticscholar.org/graph/v1"
UNPAYWALL_URL = "https://api.unpaywall.org/v2"
USER_AGENT = "LiteratureSearcher/1.0"
UVX_FALLBACK_CMD = ["uvx", "scihub-cli"]

LITERATURE_EMAIL = os.getenv("LITERATURE_EMAIL", "")
OPENALEX_EMAIL = os.getenv("OPENALEX_EMAIL", "")
OPENALEX_API_KEY = os.getenv("OPENALEX_API_KEY", "")
SEMANTIC_SCHOLAR_API_KEY = os.getenv("SEMANTIC_SCHOLAR_API_KEY", "")
ELSEVIER_API_KEY = os.getenv("ELSEVIER_API_KEY", "")
SCOPUS_API_KEY = os.getenv("SCOPUS_API_KEY", "")


@dataclass
class Paper:
    title: str
    abstract: str = ""
    authors: List[str] = field(default_factory=list)
    doi: str = ""
    year: Optional[int] = None
    citations: int = 0
    journal: str = ""
    source_platform: str = ""
    url: str = ""
    is_oa: bool = False
    pdf_url: str = ""
    issn: Optional[str] = None


def generate_random_email() -> str:
    return f"literature-searcher-{random.randint(100000, 999999)}@example.com"


def safe_int(value: str) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def reconstruct_abstract(inverted_index: Optional[Dict[str, List[int]]]) -> str:
    if not inverted_index:
        return ""
    positions = {
        position: word
        for word, word_positions in inverted_index.items()
        for position in word_positions
    }
    return " ".join(positions[position] for position in sorted(positions))


def safe_filename(value: str, fallback: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]+', "_", value).strip("._ ")
    return cleaned[:120] or fallback


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for index in range(1, 10_000):
        candidate = path.with_name(f"{path.stem}_{index}{path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not create a unique path for {path}")
