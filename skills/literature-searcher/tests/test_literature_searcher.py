from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from unittest import mock


SKILL_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SKILL_DIR))

from literature_searcher import Paper, _load_dotenv
from literature_searcher.classifier import PaperClassifier
from literature_searcher.insight import analyze_coverage, find_gaps, load_papers
from literature_searcher.monitor import OnlineTranslator, run_monitor
from literature_searcher.openalex_searcher import OpenAlexSearcher
from literature_searcher.searcher import main, merge_and_deduplicate
from literature_searcher.semantic_scholar_searcher import SemanticScholarSearcher


class JsonResponse:
    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def __enter__(self) -> "JsonResponse":
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        return False

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class LiteratureSearcherTests(unittest.TestCase):
    def test_load_dotenv_populates_missing_values_without_overriding_environment(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            dotenv_path = Path(temporary_directory) / ".env"
            dotenv_path.write_text(
                "# comment\n"
                "FROM_FILE=quoted value\n"
                "EXISTING=from-file\n"
                "INVALID-KEY=ignored\n",
                encoding="utf-8",
            )
            with mock.patch.dict(
                os.environ,
                {"EXISTING": "from-environment"},
                clear=True,
            ):
                _load_dotenv(dotenv_path)
                self.assertEqual(os.environ["FROM_FILE"], "quoted value")
                self.assertEqual(os.environ["EXISTING"], "from-environment")
                self.assertNotIn("INVALID-KEY", os.environ)

    def test_openalex_uses_valid_year_filters_and_api_key(self) -> None:
        scenarios = (
            (2020, None, "publication_year:>2019"),
            (None, 2020, "publication_year:<2021"),
            (2020, 2024, "publication_year:2020-2024"),
        )
        for year_from, year_to, expected_filter in scenarios:
            with self.subTest(year_from=year_from, year_to=year_to):
                captured_requests = []

                def fake_urlopen(request: urllib.request.Request, timeout: int) -> JsonResponse:
                    captured_requests.append(request)
                    return JsonResponse({"results": []})

                with (
                    mock.patch(
                        "literature_searcher.openalex_searcher.OPENALEX_API_KEY",
                        "test-key",
                    ),
                    mock.patch(
                        "literature_searcher.openalex_searcher.urllib.request.urlopen",
                        side_effect=fake_urlopen,
                    ),
                ):
                    OpenAlexSearcher.search("ionogel", year_from=year_from, year_to=year_to)

                query = urllib.parse.parse_qs(
                    urllib.parse.urlparse(captured_requests[0].full_url).query
                )
                self.assertEqual(query["filter"], [expected_filter])
                self.assertEqual(query["api_key"], ["test-key"])

    def test_semantic_scholar_retries_after_rate_limit(self) -> None:
        rate_limited = urllib.error.HTTPError(
            "https://api.semanticscholar.org/graph/v1/paper/search",
            429,
            "Too Many Requests",
            {"Retry-After": "0"},
            None,
        )
        request = urllib.request.Request("https://example.com")

        with (
            mock.patch(
                "literature_searcher.semantic_scholar_searcher.urllib.request.urlopen",
                side_effect=[rate_limited, JsonResponse({"data": []})],
            ) as urlopen,
            mock.patch("literature_searcher.semantic_scholar_searcher.time.sleep") as sleep,
        ):
            self.assertEqual(SemanticScholarSearcher._request_with_retry(request), {"data": []})

        self.assertEqual(urlopen.call_count, 2)
        sleep.assert_called_once_with(0.0)

    def test_classifier_accepts_mapping(self) -> None:
        result = PaperClassifier().classify(
            {"title": "Ionogel electrolyte for a lithium battery"}
        )
        self.assertIn(result["primary"], {"ionogel", "electrolyte", "battery"})

    def test_merge_and_deduplicate_uses_normalized_doi(self) -> None:
        first = Paper(title="First", doi="10.1000/ABC")
        duplicate = Paper(title="Second", doi="10.1000/abc")

        papers = merge_and_deduplicate({"crossref": [first], "openalex": [duplicate]})

        self.assertEqual(papers, [first])

    def test_cli_help_exits_successfully(self) -> None:
        with self.assertRaises(SystemExit) as raised:
            main(["--help"])

        self.assertEqual(raised.exception.code, 0)

    def test_default_translator_uses_deeplx_without_auth_key(self) -> None:
        captured = []

        def fake_urlopen(request: urllib.request.Request, timeout: int) -> JsonResponse:
            captured.append(request)
            return JsonResponse(
                {
                    "code": 200,
                    "data": "你好，世界",
                    "source_lang": "EN",
                    "target_lang": "ZH",
                }
            )

        with mock.patch(
            "literature_searcher.monitor.urllib.request.urlopen",
            side_effect=fake_urlopen,
        ):
            translated = OnlineTranslator(
                endpoint="https://translate.example.test/translate"
            ).translate(
                "Hello, world!"
            )

        self.assertEqual(translated, "你好，世界")
        self.assertIsNone(captured[0].get_header("Authorization"))
        self.assertEqual(
            json.loads(captured[0].data.decode("utf-8")),
            {
                "text": "Hello, world!",
                "source_lang": "EN",
                "target_lang": "ZH",
            },
        )

    def test_local_llm_translator_uses_openai_compatible_endpoint(self) -> None:
        captured = []

        def fake_urlopen(request: urllib.request.Request, timeout: int) -> JsonResponse:
            captured.append(request)
            return JsonResponse(
                {"choices": [{"message": {"content": "你好，世界"}}]}
            )

        with mock.patch(
            "literature_searcher.monitor.urllib.request.urlopen",
            side_effect=fake_urlopen,
        ):
            translated = OnlineTranslator(
                "local_llm",
                endpoint="http://127.0.0.1:11434/v1",
                model="qwen3",
            ).translate("Hello, world!")

        self.assertEqual(translated, "你好，世界")
        self.assertEqual(
            captured[0].full_url,
            "http://127.0.0.1:11434/v1/chat/completions",
        )
        payload = json.loads(captured[0].data.decode("utf-8"))
        self.assertEqual(payload["model"], "qwen3")
        self.assertFalse(payload["stream"])
        self.assertEqual(payload["messages"][-1]["content"], "Hello, world!")

    def test_monitor_records_only_unseen_papers(self) -> None:
        paper = Paper(
            title="Ionogel electrolyte for flexible sensors",
            doi="10.1000/monitor",
            source_platform="crossref",
        )
        with tempfile.TemporaryDirectory() as temporary_directory:
            temporary_path = Path(temporary_directory)
            config = {
                "queries": ["ionogel sensor"],
                "limit": 5,
                "state_file": str(temporary_path / "state.json"),
                "output_file": str(temporary_path / "results.json"),
                "report_file": str(temporary_path / "report.md"),
                "translation": {"enabled": False},
            }
            with mock.patch(
                "literature_searcher.monitor.search_papers",
                return_value={"crossref": [paper]},
            ):
                first = run_monitor(config)
                second = run_monitor(config)

            self.assertEqual(len(first["new_papers"]), 1)
            self.assertEqual(len(second["new_papers"]), 0)
            self.assertTrue(Path(config["output_file"]).exists())
            self.assertTrue(Path(config["report_file"]).exists())

    def test_insight_loads_monitor_output_and_reports_category_gaps(self) -> None:
        with tempfile.TemporaryDirectory() as temporary_directory:
            input_path = Path(temporary_directory) / "monitor-results.json"
            input_path.write_text(
                json.dumps(
                    {
                        "new_papers": [
                            {
                                "paper": {
                                    "title": "Ionogel electrolyte",
                                    "doi": "10.1000/insight",
                                    "year": 2026,
                                    "source_platform": "crossref",
                                }
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )

            papers = load_papers(input_path)
            coverage = analyze_coverage(
                papers,
                categories={"ionogel": {"keywords": ["ionogel"]}, "sensor": {"keywords": ["sensor"]}},
            )
            gaps = find_gaps(coverage)

        self.assertEqual(coverage["total"], 1)
        self.assertEqual(coverage["categories"]["ionogel"], 1)
        self.assertIn("sensor", gaps)


if __name__ == "__main__":
    unittest.main()
