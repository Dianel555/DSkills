"""Analyze coverage and gaps in literature-searcher result files."""

from __future__ import annotations

import argparse
import json
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional

from . import SKILL_DATA_DIR
from .classifier import CATEGORIES


def load_papers(path: Path) -> List[Dict[str, Any]]:
    """Load papers from monitor output, search CLI output, or a paper list."""

    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return _extract_papers(data)


def analyze_coverage(
    papers: Iterable[Mapping[str, Any]],
    categories: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> Dict[str, Any]:
    """Return source, year, and category coverage for the supplied papers."""

    category_config = categories or CATEGORIES
    category_counts = {name: 0 for name in category_config}
    years: Counter[str] = Counter()
    sources: Counter[str] = Counter()
    total = 0

    for paper in papers:
        total += 1
        text = " ".join(
            str(paper.get(field, "") or "") for field in ("title", "abstract", "journal")
        ).casefold()
        year = paper.get("year")
        years[str(year) if year else "unknown"] += 1
        sources[str(paper.get("source_platform") or "unknown")] += 1
        for name, config in category_config.items():
            if any(str(keyword).casefold() in text for keyword in config.get("keywords", [])):
                category_counts[name] += 1

    return {
        "total": total,
        "categories": category_counts,
        "years": dict(sorted(years.items(), reverse=True)),
        "sources": dict(sorted(sources.items())),
    }


def find_gaps(coverage: Mapping[str, Any], maximum_papers: int = 0) -> List[str]:
    """Return categories with no or low representation."""

    categories = coverage.get("categories", {})
    return sorted(
        name for name, count in categories.items() if int(count) <= maximum_papers
    )


def generate_insight_report(
    papers: Iterable[Mapping[str, Any]],
    baseline: Optional[Iterable[Mapping[str, Any]]] = None,
    categories: Optional[Mapping[str, Mapping[str, Any]]] = None,
) -> str:
    """Generate a Markdown summary of recent coverage and category gaps."""

    paper_list = list(papers)
    category_config = categories or CATEGORIES
    coverage = analyze_coverage(paper_list, category_config)
    gaps = find_gaps(coverage)
    baseline_coverage = (
        analyze_coverage(list(baseline), category_config) if baseline is not None else None
    )

    lines = [
        "# Literature Insight",
        "",
        f"Generated: {datetime.now().astimezone().isoformat(timespec='seconds')}",
        f"Papers analyzed: {coverage['total']}",
        "",
        "## Category Coverage",
        "",
        "| Category | Papers |",
        "| --- | ---: |",
    ]
    for name, count in sorted(
        coverage["categories"].items(), key=lambda item: (-item[1], item[0])
    ):
        lines.append(f"| {name} | {count} |")

    lines.extend(["", "## Gaps", ""])
    lines.extend(f"- {name}" for name in gaps) if gaps else lines.append("- None")

    if baseline_coverage:
        lines.extend(["", "## Baseline Comparison", ""])
        for name, count in coverage["categories"].items():
            delta = count - baseline_coverage["categories"].get(name, 0)
            lines.append(f"- {name}: {delta:+d}")

    lines.extend(["", "## Sources", ""])
    lines.extend(
        f"- {source}: {count}" for source, count in coverage["sources"].items()
    )
    return "\n".join(lines) + "\n"


def _extract_papers(data: Any) -> List[Dict[str, Any]]:
    if isinstance(data, list):
        return [_paper_mapping(item) for item in data]
    if not isinstance(data, Mapping):
        raise ValueError("Paper input must be a JSON list or object")

    if isinstance(data.get("new_papers"), list):
        return [_paper_mapping(item.get("paper", item)) for item in data["new_papers"]]
    if isinstance(data.get("papers"), list):
        return [_paper_mapping(item) for item in data["papers"]]

    papers: List[Dict[str, Any]] = []
    for source, values in data.items():
        if not isinstance(values, list):
            continue
        for value in values:
            paper = _paper_mapping(value)
            paper.setdefault("source_platform", source)
            papers.append(paper)
    if papers:
        return papers
    raise ValueError("Could not find a paper list in input JSON")


def _paper_mapping(value: Any) -> Dict[str, Any]:
    if not isinstance(value, Mapping):
        raise ValueError("Every paper must be a JSON object")
    return dict(value)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Analyze literature result coverage and category gaps."
    )
    parser.add_argument(
        "--input",
        default=str(SKILL_DATA_DIR / "monitor_results.json"),
        help="Monitor output, search CLI output, or a JSON paper list",
    )
    parser.add_argument("--baseline", help="Optional JSON paper source for comparison")
    parser.add_argument(
        "--output",
        default=str(SKILL_DATA_DIR / "insight_report.md"),
        help="Markdown report destination",
    )
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        papers = load_papers(Path(args.input))
        baseline = load_papers(Path(args.baseline)) if args.baseline else None
        report = generate_insight_report(papers, baseline)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Could not generate insight report: {exc}") from exc

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(report, encoding="utf-8")
    print(json.dumps({"output_file": str(output), "papers": len(papers)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
