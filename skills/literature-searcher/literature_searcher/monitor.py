"""Incrementally search, classify, and report newly discovered papers."""

from __future__ import annotations

import argparse
import json
import os
import urllib.parse
import urllib.request
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence

from . import Paper, SKILL_DATA_DIR, SKILL_DIR, USER_AGENT
from .classifier import PaperClassifier
from .searcher import merge_and_deduplicate, search_papers


DEFAULT_CONFIG = {
    "queries": [],
    "platforms": [],
    "limit": 20,
    "year_from": None,
    "year_to": None,
    "state_file": "data/monitor_state.json",
    "output_file": "data/monitor_results.json",
    "report_file": "data/monitor_report.md",
    "translation": {
        "enabled": True,
        "provider": "deeplx",
        "target_lang": "ZH",
        "endpoint": "",
        "model": "",
        "translate_abstract": False,
    },
}


class TranslationError(RuntimeError):
    """Raised when an online translation provider cannot translate text."""


class OnlineTranslator:
    """Translate through an online DeepLX API or a local OpenAI-compatible LLM."""

    def __init__(
        self,
        provider: str = "deeplx",
        target_lang: str = "ZH",
        endpoint: Optional[str] = None,
        model: Optional[str] = None,
    ) -> None:
        if provider not in {"deeplx", "local_llm", "none"}:
            raise ValueError(f"Unsupported translation provider: {provider}")
        self.provider = provider
        self.target_lang = target_lang
        self.endpoint = endpoint or os.getenv(
            "DEEPLX_ENDPOINT" if provider == "deeplx" else "LOCAL_LLM_BASE_URL",
            "",
        )
        self.model = model or os.getenv("LOCAL_LLM_MODEL", "")

    def translate(self, text: str) -> str:
        if not text.strip() or self.provider == "none":
            return text
        if self.provider == "deeplx":
            return self._translate_deeplx(text)
        return self._translate_local_llm(text)

    def _translate_deeplx(self, text: str) -> str:
        if not self.endpoint:
            raise TranslationError("DEEPLX_ENDPOINT is required when provider is deeplx")

        response = self._post_json(
            self.endpoint,
            {"text": text, "source_lang": "EN", "target_lang": self.target_lang},
        )
        translated = response.get("data") or response.get("text")
        if isinstance(translated, Mapping):
            translated = translated.get("text") or translated.get("data")
        if not translated:
            raise TranslationError("DeepLX response did not contain translated text")
        return str(translated)

    def _translate_local_llm(self, text: str) -> str:
        if not self.endpoint:
            raise TranslationError(
                "LOCAL_LLM_BASE_URL is required when provider is local_llm"
            )
        if not self.model:
            raise TranslationError(
                "LOCAL_LLM_MODEL is required when provider is local_llm"
            )

        endpoint = self.endpoint.rstrip("/")
        if not endpoint.endswith("/chat/completions"):
            endpoint = f"{endpoint}/chat/completions"
        response = self._post_json(
            endpoint,
            {
                "model": self.model,
                "messages": [
                    {
                        "role": "system",
                        "content": (
                            f"Translate the user's English text into {self.target_lang}. "
                            "Return only the translation. Preserve scientific terminology, "
                            "DOIs, symbols, units, and citations."
                        ),
                    },
                    {"role": "user", "content": text},
                ],
                "temperature": 0,
                "stream": False,
            },
            require_https=False,
        )
        choices = response.get("choices", [])
        if not choices:
            raise TranslationError("Local LLM response did not contain choices")
        message = choices[0].get("message", {})
        translated = message.get("content") if isinstance(message, Mapping) else None
        if not translated:
            raise TranslationError("Local LLM response did not contain translated text")
        return str(translated).strip()

    @staticmethod
    def _post_json(
        endpoint: str,
        payload: Mapping[str, Any],
        require_https: bool = True,
    ) -> Dict[str, Any]:
        scheme = urllib.parse.urlparse(endpoint).scheme
        if scheme not in {"http", "https"}:
            raise TranslationError("Translation endpoints must use HTTP or HTTPS")
        if require_https and scheme != "https":
            raise TranslationError("Translation endpoints must use HTTPS")

        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        request = urllib.request.Request(
            endpoint,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.loads(response.read().decode("utf-8"))
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            raise TranslationError(f"Translation request failed: {exc}") from exc


def load_config(config_path: Optional[str] = None) -> Dict[str, Any]:
    """Load a monitor configuration, optionally from the skill data directory."""

    config = json.loads(json.dumps(DEFAULT_CONFIG))
    path = Path(config_path) if config_path else SKILL_DATA_DIR / "monitor_config.json"
    if path.exists():
        with path.open("r", encoding="utf-8") as handle:
            supplied = json.load(handle)
        if not isinstance(supplied, Mapping):
            raise ValueError("Monitor configuration must be a JSON object")
        config.update({key: value for key, value in supplied.items() if key != "translation"})
        translation = supplied.get("translation", {})
        if translation:
            if not isinstance(translation, Mapping):
                raise ValueError("translation configuration must be a JSON object")
            config["translation"].update(translation)
    return _normalize_config(config)


def run_monitor(config: Mapping[str, Any]) -> Dict[str, Any]:
    """Search configured queries and persist only papers not present in monitor state."""

    config = _normalize_config(config)
    queries = _string_list(config["queries"])
    if not queries:
        raise ValueError("Monitor needs at least one query")

    all_papers: List[Paper] = []
    for query in queries:
        results = search_papers(
            query,
            platforms=config["platforms"] or None,
            limit=config["limit"],
            year_from=config["year_from"],
            year_to=config["year_to"],
        )
        all_papers.extend(merge_and_deduplicate(results))
    papers = merge_and_deduplicate({"monitor": all_papers})

    state_file = Path(config["state_file"])
    state = _load_state(state_file)
    known = set(state["seen"])
    new_papers = [paper for paper in papers if _paper_key(paper) not in known]

    classifier = PaperClassifier()
    translator = _build_translator(config["translation"])
    records = [
        _monitor_record(paper, classifier, translator, config["translation"])
        for paper in new_papers
    ]
    records.sort(
        key=lambda record: (
            record["paper"].get("citations", 0),
            record["classification"].get("confidence", 0),
        ),
        reverse=True,
    )

    state["seen"] = sorted(known | {_paper_key(paper) for paper in papers})
    state["updated_at"] = _timestamp()
    _write_json(state_file, state)

    output = {
        "generated_at": _timestamp(),
        "queries": queries,
        "searched_papers": len(papers),
        "new_papers": records,
        "state_file": str(state_file),
    }
    output_file = Path(config["output_file"])
    _write_json(output_file, output)
    _write_report(Path(config["report_file"]), output)
    return output


def _monitor_record(
    paper: Paper,
    classifier: PaperClassifier,
    translator: Optional[OnlineTranslator],
    translation_config: Mapping[str, Any],
) -> Dict[str, Any]:
    translations: Dict[str, str] = {}
    errors: Dict[str, str] = {}
    if translator:
        fields = ["title"]
        if translation_config.get("translate_abstract"):
            fields.append("abstract")
        for field in fields:
            value = getattr(paper, field)
            if not value:
                continue
            try:
                translations[field] = translator.translate(value)
            except TranslationError as exc:
                errors[field] = str(exc)

    record = {
        "paper": asdict(paper),
        "classification": classifier.classify(paper),
        "translations": translations,
    }
    if errors:
        record["translation_errors"] = errors
    return record


def _build_translator(config: Mapping[str, Any]) -> Optional[OnlineTranslator]:
    if not config.get("enabled", True):
        return None
    provider = str(config.get("provider", "deeplx"))
    if provider == "none":
        return None
    return OnlineTranslator(
        provider=provider,
        target_lang=str(config.get("target_lang", "ZH")),
        endpoint=config.get("endpoint"),
        model=config.get("model"),
    )


def _normalize_config(config: Mapping[str, Any]) -> Dict[str, Any]:
    merged = json.loads(json.dumps(DEFAULT_CONFIG))
    merged.update({key: value for key, value in config.items() if key != "translation"})
    translation = config.get("translation", {})
    if translation:
        merged["translation"].update(translation)

    for key in ("state_file", "output_file", "report_file"):
        path = Path(merged[key]).expanduser()
        merged[key] = str(path if path.is_absolute() else SKILL_DIR / path)
    merged["platforms"] = _string_list(merged.get("platforms", []))
    merged["queries"] = _string_list(merged.get("queries", merged.get("keywords", [])))
    merged["limit"] = max(1, int(merged["limit"]))
    for key in ("year_from", "year_to"):
        if merged[key] is not None:
            merged[key] = int(merged[key])
    return merged


def _load_state(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {"seen": []}
    try:
        with path.open("r", encoding="utf-8") as handle:
            state = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"Could not read monitor state {path}: {exc}") from exc
    if not isinstance(state, Mapping) or not isinstance(state.get("seen", []), list):
        raise ValueError(f"Invalid monitor state: {path}")
    return {"seen": [str(value) for value in state["seen"]]}


def _write_json(path: Path, value: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)


def _write_report(path: Path, output: Mapping[str, Any]) -> None:
    lines = [
        "# Literature Monitor",
        "",
        f"Generated: {output['generated_at']}",
        f"Queries: {', '.join(output['queries'])}",
        f"Searched papers: {output['searched_papers']}",
        f"New papers: {len(output['new_papers'])}",
        "",
    ]
    for record in output["new_papers"]:
        paper = record["paper"]
        translated_title = record["translations"].get("title")
        lines.append(f"## {paper['title']}")
        if translated_title:
            lines.append(translated_title)
        lines.append(f"Category: {record['classification']['primary']}")
        if paper.get("doi"):
            lines.append(f"DOI: {paper['doi']}")
        if paper.get("url"):
            lines.append(f"URL: {paper['url']}")
        lines.append("")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines), encoding="utf-8")


def _paper_key(paper: Paper) -> str:
    return paper.doi.strip().lower() or "title:" + " ".join(paper.title.lower().split())


def _string_list(value: Any) -> List[str]:
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, Sequence):
        raise ValueError("queries and platforms must be strings or lists of strings")
    return [str(item).strip() for item in value if str(item).strip()]


def _timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Find papers not seen by earlier literature monitor runs."
    )
    parser.add_argument("--config", help="JSON configuration file")
    parser.add_argument("--query", action="append", help="Override configured query; repeatable")
    parser.add_argument("--platform", action="append", help="Override configured platform; repeatable")
    parser.add_argument("--limit", type=int, help="Override configured per-query result limit")
    parser.add_argument("--year-from", type=int)
    parser.add_argument("--year-to", type=int)
    parser.add_argument("--translator", choices=["deeplx", "local_llm", "none"])
    parser.add_argument("--translate-abstract", action="store_true")
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)
    config = load_config(args.config)
    for name in ("query", "platform", "limit", "year_from", "year_to"):
        value = getattr(args, name)
        if value is not None:
            config[{"query": "queries", "platform": "platforms"}.get(name, name)] = value
    if args.translator:
        config["translation"]["provider"] = args.translator
        config["translation"]["enabled"] = args.translator != "none"
    if args.translate_abstract:
        config["translation"]["translate_abstract"] = True

    try:
        output = run_monitor(config)
    except ValueError as exc:
        parser.error(str(exc))
    print(
        json.dumps(
            {
                "new_papers": len(output["new_papers"]),
                "output_file": config["output_file"],
                "report_file": config["report_file"],
            },
            ensure_ascii=False,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
