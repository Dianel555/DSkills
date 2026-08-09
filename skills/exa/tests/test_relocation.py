from __future__ import annotations

import unittest

from _support import SKILL_ROOT


class RelocationContractTests(unittest.TestCase):
    def test_package_is_flat_beside_launcher(self) -> None:
        package = SKILL_ROOT / "scripts" / "exa_cli"
        self.assertTrue(package.is_dir())
        self.assertFalse((SKILL_ROOT / "exa_cli").exists())
        self.assertFalse((package / "commands").exists())
        for name in (
            "__init__.py", "__main__.py", "config.py", "client.py",
            "output.py", "search.py", "fetch.py", "advanced.py",
            "config_info.py",
        ):
            self.assertTrue((package / name).is_file(), name)

    def test_source_file_line_limits(self) -> None:
        launcher = SKILL_ROOT / "scripts" / "exa_cli.py"
        self.assertLessEqual(len(launcher.read_text(encoding="utf-8").splitlines()), 20)
        package = SKILL_ROOT / "scripts" / "exa_cli"
        for path in package.glob("*.py"):
            self.assertLessEqual(len(path.read_text(encoding="utf-8").splitlines()),
                                 250, path.name)


if __name__ == "__main__":
    unittest.main()
