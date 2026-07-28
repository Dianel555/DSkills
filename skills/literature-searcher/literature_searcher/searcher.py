"""Command-line facade for literature search and PDF download workflows."""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from typing import Dict, Iterable, List, Optional

from . import Paper
from .crossref_searcher import CrossRefSearcher
from .downloader import Downloader
from .openalex_searcher import OpenAlexSearcher
from .pubmed_searcher import PubMedSearcher
from .scopus_searcher import ScopusSearcher
from .semantic_scholar_searcher import SemanticScholarSearcher


SEARCHERS = {
    "crossref": CrossRefSearcher.search,
    "openalex": OpenAlexSearcher.search,
    "pubmed": PubMedSearcher.search,
    "semantic_scholar": SemanticScholarSearcher.search,
    "scopus": ScopusSearcher.search,
}


def search_papers(
    query: str,
    platforms: Optional[Iterable[str]] = None,
    limit: int = 20,
    year_from: Optional[int] = None,
    year_to: Optional[int] = None,
) -> Dict[str, List[Paper]]:
    selected = list(platforms) if platforms else ["crossref", "openalex", "pubmed", "semantic_scholar"]
    results: Dict[str, List[Paper]] = {}
    for platform in selected:
        try:
            search = SEARCHERS[platform]
        except KeyError as exc:
            raise ValueError(f"Unsupported platform: {platform}") from exc
        results[platform] = search(query, limit, year_from, year_to)
    return results


def merge_and_deduplicate(results: Dict[str, List[Paper]]) -> List[Paper]:
    merged: List[Paper] = []
    seen = set()
    for papers in results.values():
        for paper in papers:
            key = paper.doi.strip().lower() if paper.doi else paper.title.strip().lower()
            if key and key not in seen:
                seen.add(key)
                merged.append(paper)
    return merged


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Search academic literature and download open-access PDFs.")
    commands = parser.add_subparsers(dest="command", required=True)

    search = commands.add_parser("search", help="Search one or more literature indexes.")
    search.add_argument("query")
    search.add_argument("--platform", action="append", choices=sorted(SEARCHERS))
    search.add_argument("--limit", type=int, default=20)
    search.add_argument("--year-from", type=int)
    search.add_argument("--year-to", type=int)

    download = commands.add_parser("download", help="Download an open-access PDF by DOI.")
    download.add_argument("--doi", required=True)
    download.add_argument("--outdir", default="./downloads")
    download.add_argument("--email")
    download.add_argument("--scihub-fallback", choices=["auto", "off"], default="off")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    if args.command == "search":
        results = search_papers(args.query, args.platform, args.limit, args.year_from, args.year_to)
        output = {name: [asdict(paper) for paper in papers] for name, papers in results.items()}
        print(json.dumps(output, ensure_ascii=False))
        return 0

    result = Downloader.download_by_doi(
        args.doi,
        outdir=args.outdir,
        email=args.email,
        scihub_fallback=args.scihub_fallback,
    )
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result["status"] == "downloaded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
