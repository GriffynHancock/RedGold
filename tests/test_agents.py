"""Build order step 8 acceptance test -- the agent roster.

Acceptance criterion (§17.2): "`rg-lead` cannot issue a network call -- proven by an attempt that
is denied. A worker attempting to spawn a subagent is caught loudly, not silently ignored (§8.0).
A full phase runs end-to-end and the worker demonstrably executed."

**The third clause is NOT covered here, and saying so is the point.** Running a full phase means
dispatching real agents against a real target, which costs real tokens and needs an authorised
engagement. What is covered: the roster's invariants, and the nesting denial. The end-to-end phase
is exercised in the live prior-engagement run, not in this suite. Do not read a green suite as evidence that
a phase has ever run.

Most of these are **mutation tests**: they break a card on purpose and assert the validator
notices. A checker nobody has watched fail is a checker nobody knows works.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import validate_agents  # noqa: E402

AGENTS = REPO / "agents"
NESTING_HOOK = REPO / "scripts" / "no_nesting.py"
EXPECTED_ROSTER = {
    "rg-lead", "rg-recon", "rg-surface", "rg-codeaudit", "rg-webtest", "rg-verify", "rg-report",
}


def card(name: str) -> str:
    return (AGENTS / f"{name}.md").read_text(encoding="utf-8")


def frontmatter(name: str) -> dict[str, str]:
    return validate_agents.parse_frontmatter(card(name))


class TestRosterAsShipped(unittest.TestCase):
    def test_roster_validates(self):
        self.assertEqual(validate_agents.validate(), [])

    def test_roster_is_the_expected_seven(self):
        actual = {p.stem for p in AGENTS.glob("*.md")}
        self.assertEqual(actual, EXPECTED_ROSTER)

    def test_roster_is_capped(self):
        # Growth happens in the playbook library, not the roster: flooding delegation with
        # options makes automatic routing less reliable.
        self.assertLessEqual(len(list(AGENTS.glob("*.md"))), 7)

    def test_lead_has_no_network_tools(self):
        tools = validate_agents.tool_list(frontmatter("rg-lead")["tools"])
        self.assertNotIn("Bash", tools)
        self.assertNotIn("WebFetch", tools)

    def test_no_card_grants_a_nesting_tool(self):
        for path in AGENTS.glob("*.md"):
            tools = set(validate_agents.tool_list(frontmatter(path.stem).get("tools", "")))
            self.assertEqual(tools & validate_agents.NESTING_TOOLS, set(), path.name)

    def test_exactly_one_card_uses_the_expensive_model(self):
        expensive = [p.stem for p in AGENTS.glob("*.md")
                     if frontmatter(p.stem).get("model", "").lower() in validate_agents.EXPENSIVE_MODELS]
        self.assertEqual(expensive, ["rg-lead"])

    def test_verify_and_report_carry_no_memory(self):
        # A verifier that remembers why it believed something is a worse skeptic; a report writer
        # should work only from validated findings on disk.
        for name in ("rg-verify", "rg-report"):
            self.assertNotIn("memory", frontmatter(name), f"{name} must carry no memory")

    def test_report_has_no_network_tools(self):
        tools = validate_agents.tool_list(frontmatter("rg-report")["tools"])
        self.assertNotIn("Bash", tools)
        self.assertNotIn("WebFetch", tools)

    def test_every_network_capable_card_carries_the_safety_block(self):
        for path in AGENTS.glob("*.md"):
            tools = set(validate_agents.tool_list(frontmatter(path.stem).get("tools", "")))
            if tools & validate_agents.NETWORK_TOOLS:
                text = card(path.stem)
                self.assertIn(validate_agents.SCOPE_MARKER, text, path.name)
                self.assertIn(validate_agents.UNTRUSTED_MARKER, text, path.name)
                self.assertIn(validate_agents.NESTING_MARKER, text, path.name)

    def test_descriptions_carry_a_negative_routing_case(self):
        for path in AGENTS.glob("*.md"):
            if path.stem == "rg-lead":
                continue
            self.assertIn("do not use", frontmatter(path.stem)["description"].lower(), path.name)


class TestValidatorCatchesRegressions(unittest.TestCase):
    """Mutation tests. Break a card; the checker must notice."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self._tmp.name) / "agents"
        shutil.copytree(AGENTS, self.dir)
        self._original = validate_agents.AGENTS_DIR
        validate_agents.AGENTS_DIR = self.dir
        self.addCleanup(self._restore)

    def _restore(self):
        validate_agents.AGENTS_DIR = self._original
        self._tmp.cleanup()

    def mutate(self, name: str, old: str, new: str):
        path = self.dir / f"{name}.md"
        text = path.read_text()
        self.assertIn(old, text, f"mutation target {old!r} not present in {name}")
        path.write_text(text.replace(old, new, 1))

    def assertFlags(self, needle: str):
        errors = validate_agents.validate()
        self.assertTrue(any(needle.lower() in e.lower() for e in errors),
                        f"expected an error mentioning {needle!r}, got: {errors}")

    def test_giving_the_lead_bash_is_caught(self):
        # The acceptance criterion, as a mutation: an orchestrator that could probe is rejected.
        self.mutate("rg-lead", "tools: Read, Grep, Glob, Write", "tools: Read, Grep, Glob, Write, Bash")
        self.assertFlags("structurally incapable of probing")

    def test_giving_the_lead_webfetch_is_caught(self):
        self.mutate("rg-lead", "tools: Read, Grep, Glob, Write", "tools: Read, Write, WebFetch")
        self.assertFlags("structurally incapable of probing")

    def test_unset_tools_field_is_caught(self):
        # The lesson: an unset tools field grants everything and the file looks fine.
        self.mutate("rg-webtest", "tools: Bash, WebFetch, Read, Write", "tools:")
        self.assertFlags("grants the agent EVERYTHING")

    def test_granting_a_nesting_tool_is_caught(self):
        self.mutate("rg-webtest", "tools: Bash, WebFetch, Read, Write",
                    "tools: Bash, WebFetch, Read, Write, Agent")
        self.assertFlags("cannot nest")

    def test_removing_the_scope_marker_is_caught(self):
        self.mutate("rg-webtest", validate_agents.SCOPE_MARKER, "scope stuff")
        self.assertFlags("scope-guard acknowledgement")

    def test_removing_the_untrusted_data_clause_is_caught(self):
        self.mutate("rg-recon", "## UNTRUSTED DATA", "## Notes")
        self.assertFlags("untrusted-data clause")

    def test_declaring_hooks_in_frontmatter_is_caught(self):
        self.mutate("rg-recon", "model: sonnet", "model: sonnet\nhooks: ./hooks.json")
        self.assertFlags("silently ignored")

    def test_declaring_permission_mode_is_caught(self):
        self.mutate("rg-recon", "model: sonnet", "model: sonnet\npermissionMode: bypassPermissions")
        self.assertFlags("silently ignored")

    def test_a_second_expensive_card_is_caught(self):
        # The cost lesson, enforced numerically rather than left to judgement.
        self.mutate("rg-webtest", "model: sonnet", "model: opus")
        self.assertFlags("always escalate")

    def test_name_filename_mismatch_is_caught(self):
        self.mutate("rg-verify", "name: rg-verify", "name: rg-verifier")
        self.assertFlags("!=")

    def test_missing_negative_routing_case_is_caught(self):
        text = (self.dir / "rg-recon.md").read_text()
        stripped = re.sub(r"Do NOT use[^\n]*", "", text)
        (self.dir / "rg-recon.md").write_text(stripped)
        self.assertFlags("delegation router")


class TestNestingIsCaughtLoudly(unittest.TestCase):
    """§8.0: the failure mode is silence, so the test is that it is not silent."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        (self.root / "scope.yaml").write_text("engagement_id: t\n", encoding="utf-8")
        (self.root / "ledger").mkdir()

    def run_hook(self, payload: dict) -> tuple[int, str]:
        proc = subprocess.run(
            ["/usr/bin/python3", str(NESTING_HOOK)], input=json.dumps(payload),
            capture_output=True, text=True, timeout=30,
            env={"PATH": "/usr/bin:/bin", "RG_ENGAGEMENT_ROOT": str(self.root)})
        return proc.returncode, proc.stdout

    def test_worker_spawning_a_subagent_is_denied(self):
        _, out = self.run_hook({"tool_name": "Agent", "agent_id": "a1",
                                "agent_type": "rg-webtest", "tool_input": {}})
        decision = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "deny")
        self.assertIn("silent", decision["permissionDecisionReason"].lower())

    def test_the_attempt_is_recorded_so_it_survives_the_session(self):
        self.run_hook({"tool_name": "Agent", "agent_id": "a1", "agent_type": "rg-webtest",
                       "tool_input": {}})
        rows = [json.loads(l) for l in
                (self.root / "ledger" / "blockers.jsonl").read_text().splitlines() if l.strip()]
        self.assertEqual(rows[-1]["kind"], "nesting")
        self.assertEqual(rows[-1]["actor"], "rg-webtest")

    def test_all_nesting_tools_are_covered(self):
        for tool in ("Agent", "Task", "TaskOutput", "AskUserQuestion"):
            with self.subTest(tool=tool):
                _, out = self.run_hook({"tool_name": tool, "agent_id": "a1", "tool_input": {}})
                self.assertTrue(out.strip(), f"{tool} was silently allowed")

    def test_the_main_session_is_unaffected(self):
        # No agent_id means the caller is the session, which may legitimately dispatch.
        _, out = self.run_hook({"tool_name": "Agent", "tool_input": {}})
        self.assertEqual(out.strip(), "")

    def test_ordinary_worker_tools_are_unaffected(self):
        _, out = self.run_hook({"tool_name": "Bash", "agent_id": "a1",
                                "tool_input": {"command": "ls"}})
        self.assertEqual(out.strip(), "")


if __name__ == "__main__":
    unittest.main()
