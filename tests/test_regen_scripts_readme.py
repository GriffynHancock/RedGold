"""Acceptance test for regen_scripts_readme.py.

scripts/README.md used to hand-list which scripts were built and drifted -- eight built, wired,
tested scripts were still marked "not built" long after status.md and commands/new.md had moved
on. This is the tripwire: `--check` must pass against the file as committed, and must fail the
moment the table drifts from what HOOK_WIRING and the files on disk actually say.
"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import regen_scripts_readme  # noqa: E402


class TestCheckMode(unittest.TestCase):
    def test_check_passes_against_the_file_on_disk(self):
        """The file in the repo must already be regenerated -- this is what stops the drift
        this test exists to catch from recurring: a passing --check here means the checked-in
        README and the real state of scripts/ agree, right now."""
        self.assertEqual(regen_scripts_readme.main(["--check"]), 0)

    def test_check_fails_on_a_hand_edited_table(self):
        original = regen_scripts_readme.README.read_text(encoding="utf-8")
        self.addCleanup(lambda: regen_scripts_readme.README.write_text(
            original, encoding="utf-8"))
        regen_scripts_readme.README.write_text(
            original.replace("scope_guard.py", "scope_guard.py (hand-edited, now stale)"),
            encoding="utf-8")
        self.assertEqual(regen_scripts_readme.main(["--check"]), 1)

    def test_regeneration_is_idempotent(self):
        original = regen_scripts_readme.README.read_text(encoding="utf-8")
        self.addCleanup(lambda: regen_scripts_readme.README.write_text(
            original, encoding="utf-8"))
        self.assertEqual(regen_scripts_readme.main([]), 0)
        first = regen_scripts_readme.README.read_text(encoding="utf-8")
        self.assertEqual(regen_scripts_readme.main([]), 0)
        self.assertEqual(first, regen_scripts_readme.README.read_text(encoding="utf-8"))


class TestRenderLogic(unittest.TestCase):
    def test_render_refuses_without_markers(self):
        with self.assertRaises(ValueError):
            regen_scripts_readme.render("# scripts/\n\nno markers here\n")

    def test_every_built_script_is_wired_correctly(self):
        table = regen_scripts_readme.render_table()
        self.assertIn("| `scope_guard.py` |", table)
        self.assertIn("`PreToolUse`", table)
        # A script that is invoked directly (a CLI backend, not a hook) must say so, not "not
        # built" -- that phrase is exactly what went stale and cost a cold-start audit real time.
        self.assertNotIn("not built", table)
        self.assertIn("gate_cli.py", table)


if __name__ == "__main__":
    unittest.main()
