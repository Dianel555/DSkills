---
name: literature-searcher
description: |
  Search CrossRef, OpenAlex, PubMed, Semantic Scholar, and optional Scopus;
  deduplicate results, download open-access PDFs by DOI, classify papers, monitor
  new results, and analyze coverage.
  Use when asked to search literature, monitor a topic, download an open-access
  paper, classify papers, or analyze literature gaps.
---

# Literature Searcher

Run all commands from `skills/literature-searcher`. The package uses only the
Python standard library.

## Search

```bash
python -m literature_searcher.searcher search "ionogel flexible sensor" --limit 10
python -m literature_searcher.searcher search "solid electrolyte" \
  --platform openalex --platform semantic_scholar --year-from 2020 --year-to 2024
```

Without `--platform`, the command searches CrossRef, OpenAlex, PubMed, and
Semantic Scholar. Scopus requires `ELSEVIER_API_KEY`.

## Download Open-Access PDFs

```bash
python -m literature_searcher.searcher download --doi 10.1016/j.cej.2022.135593
```

Downloads query Unpaywall by default. Enable the optional `scihub-cli` fallback
explicitly with `--scihub-fallback auto`.

## Incremental Monitoring And Insight

```powershell
New-Item -ItemType Directory -Force data | Out-Null
Copy-Item monitor_config.json.template data/monitor_config.json
```

Set `queries` in `data/monitor_config.json`, then run:

```bash
python -m literature_searcher.monitor --config data/monitor_config.json
python -m literature_searcher.insight --input data/monitor_results.json
```

Monitoring uses the HTTPS DeepLX endpoint in `DEEPLX_ENDPOINT` by default and
does not require a DeepL API key. To use a local OpenAI-compatible model
service, set `LOCAL_LLM_BASE_URL` and `LOCAL_LLM_MODEL`, then pass
`--translator local_llm`. Translation failures are recorded in the result JSON
and do not stop monitoring.

## Python API

| Capability | Import | Entry point |
| --- | --- | --- |
| Multi-platform search | `literature_searcher.searcher` | `search_papers()` |
| Result deduplication | `literature_searcher.searcher` | `merge_and_deduplicate()` |
| PDF download | `literature_searcher.downloader` | `Downloader.download_by_doi()` |
| Paper classification | `literature_searcher.classifier` | `PaperClassifier.classify()` |
| Incremental monitoring | `literature_searcher.monitor` | `run_monitor()` |
| Coverage analysis | `literature_searcher.insight` | `analyze_coverage()` |

`PaperClassifier.classify()` and `batch_classify()` accept both mappings and
objects with paper attributes.

## Configuration

The package reads these optional variables from the process environment:
`LITERATURE_EMAIL`, `OPENALEX_EMAIL`, `OPENALEX_API_KEY`,
`SEMANTIC_SCHOLAR_API_KEY`, `ELSEVIER_API_KEY`, `DEEPLX_ENDPOINT`,
`LOCAL_LLM_BASE_URL`, and `LOCAL_LLM_MODEL`. Copy `.env.example` to `.env` in
the skill directory to load values automatically. Variables already exported by
the calling shell take precedence.
