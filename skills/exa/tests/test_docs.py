from __future__ import annotations

import json
import re
import unittest

from _support import SKILL_ROOT

REPO_ROOT = SKILL_ROOT.parents[1]
DEPRECATED = (
    "deep_researcher", "linkedin_search_exa", "company_research_exa",
    "get_code_context_exa", "deep_search_exa", "crawling_exa",
)


def frontmatter(path):
    text = path.read_text(encoding="utf-8")
    self_closing, header, _body = text.split("---", 2)
    if self_closing.strip():
        raise AssertionError("frontmatter must start at byte zero")
    values = {}
    for line in header.splitlines():
        match = re.match(r"^([a-zA-Z0-9_-]+):\s*(.*)$", line)
        if match:
            values[match.group(1)] = match.group(2).strip()
    return values, text


class DocumentationContractTests(unittest.TestCase):
    def test_parent_and_agent_frontmatter_and_routing(self) -> None:
        parent, parent_text = frontmatter(SKILL_ROOT / "SKILL.md")
        self.assertEqual(parent["name"], "exa")
        self.assertIn("description", parent)
        helper_path = SKILL_ROOT / "exa-agent.md"
        self.assertTrue(helper_path.is_file())
        helper, helper_text = frontmatter(helper_path)
        self.assertEqual(helper["name"], "exa-agent")
        self.assertTrue(helper["description"])
        self.assertEqual(helper["context"], "fork")
        self.assertIn("exa-agent.md", parent_text)
        self.assertIn("agent_run", parent_text)
        self.assertLess(len(parent_text.splitlines()), 500)
        self.assertIn("objective", helper_text)

    def test_agent_guide_has_coverage_resume_and_batch_boundaries(self) -> None:
        text = (SKILL_ROOT / "exa-agent.md").read_text(encoding="utf-8").lower()
        for term in (
            "objective", "universe", "segments", "coverage target",
            "output fields", "evidence requirements", "exclusions",
            "outputschema", "--run-id", "--previous-run-id",
            "best-effort discovery", "dedup", "gaps", "zdr",
            "bounded concurrency", "backoff", "checkpoint", "output file",
        ):
            with self.subTest(term=term):
                self.assertIn(term, text)
        self.assertRegex(text, r"(do not|never).{0,80}(complete|exhaustive)")

    def test_readme_and_parent_document_five_commands(self) -> None:
        parent = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        readme = (SKILL_ROOT / "README.md").read_text(encoding="utf-8")
        for command in (
            "web_search_exa", "web_fetch_exa", "web_search_advanced_exa",
            "get_config_info", "agent_run",
        ):
            self.assertIn(command, parent)
            self.assertIn(command, readme)
        for term in ("--run-id", "--previous-run-id", "--wait-seconds", "failed", "cancelled"):
            self.assertIn(term, readme)
        self.assertNotIn("python -m scripts.exa_cli", parent + readme)

    def test_env_example_matches_standalone_cli_configuration(self) -> None:
        text = (SKILL_ROOT / ".env.example").read_text(encoding="utf-8")
        for name in (
            "EXA_API_KEY", "EXA_API_URL", "EXA_DEBUG",
            "EXA_MAX_RETRY_WAIT", "EXA_AUTH_SCHEME",
        ):
            with self.subTest(name=name):
                self.assertIn(name, text)
        for unsupported in (
            "ENABLED_TOOLS", "DEFAULT_SEARCH_TYPE", "MCP_MAX_DURATION_SECONDS",
            "AGENT_CALL_WINDOW_MS",
        ):
            with self.subTest(unsupported=unsupported):
                self.assertNotIn(unsupported, text)
        self.assertIn("--wait-seconds", text)
        self.assertIn("--poll-interval", text)

    def test_references_deprecated_names_marketplace_and_local_files(self) -> None:
        parent = (SKILL_ROOT / "SKILL.md").read_text(encoding="utf-8")
        for name in DEPRECATED:
            self.assertNotIn(name, parent)
        references = sorted((SKILL_ROOT / "references").glob("*.md"))
        self.assertEqual(len(references), 11)
        marketplace = json.loads(
            (REPO_ROOT / ".claude-plugin" / "marketplace.json").read_text(
                encoding="utf-8"
            )
        )
        exa = next(plugin for plugin in marketplace["plugins"] if plugin["name"] == "exa")
        self.assertEqual(exa["source"], "./skills/exa")
        self.assertFalse((SKILL_ROOT / "CLAUDE.local.md").exists())
        self.assertFalse((SKILL_ROOT / "scripts" / "CLAUDE.local.md").exists())


if __name__ == "__main__":
    unittest.main()
