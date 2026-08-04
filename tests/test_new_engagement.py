"""Acceptance tests for build order step 4.

Acceptance criterion (§17.2): "Produces a complete engagement dir whose hooks fire and deny
correctly end-to-end."

"End-to-end" is taken literally here: these tests scaffold a real engagement, read the hook command
out of the generated `.claude/settings.json`, and execute *that exact string* through a shell with a
recorded payload on stdin. Nothing is re-derived. If the scaffolder writes a command that does not
work, these fail.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import new_engagement  # noqa: E402

PYTHON = "/usr/bin/python3"


def base_args(root: str, auth_doc: str, **overrides) -> list[str]:
    args = {
        "--client": "acme",
        "--date": "2026-08",
        "--root": root,
        "--client-name": "Acme Pty Ltd",
        "--client-contact": "founder@acme.example",
        "--auth-document": auth_doc,
        "--signed-by": "Jane Founder",
        "--signed-date": "2026-08-01",
        "--window-start": "2020-01-01",
        "--window-end": "2099-12-31",
        "--python": PYTHON,
        "--no-git": None,
    }
    args.update(overrides)
    out: list[str] = []
    for k, v in args.items():
        out.append(k)
        if v is not None:
            out.append(str(v))
    return out + ["--in-scope", "WILDCARD:*.acme.example"]


class ScaffoldHarness(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.auth_doc = self.root / "signed-roe.pdf"
        self.auth_doc.write_text("synthetic signed authorization", encoding="utf-8")
        self.addCleanup(self._tmp.cleanup)

    def scaffold(self, **overrides) -> int:
        return new_engagement.main(base_args(str(self.root), str(self.auth_doc), **overrides))

    @property
    def engagement(self) -> Path:
        return self.root / "acme-2026-08"


class TestProducesCompleteEngagement(ScaffoldHarness):
    def test_creates_every_required_path(self):
        self.assertEqual(self.scaffold(), 0)
        expected = [
            "scope.yaml", "CLAUDE.md", "status.md", "session.md", ".gitignore",
            ".claude/settings.json", "assets/register.jsonl", "assets/candidates.jsonl",
            "ledger/gates.jsonl", "ledger/activity.jsonl", "ledger/cleanup.jsonl",
            "ledger/blockers.jsonl",
        ]
        for rel in expected:
            with self.subTest(path=rel):
                self.assertTrue((self.engagement / rel).exists(), f"missing {rel}")
        for rel in ("findings", "evidence", "deliverables", "ledger/sessions", ".claude/rules"):
            self.assertTrue((self.engagement / rel).is_dir(), f"missing dir {rel}")

    def test_written_scope_reparses(self):
        self.scaffold()
        sys.path.insert(0, str(REPO / "scripts"))
        import scope as scope_mod

        boundary = scope_mod.load(self.engagement / "scope.yaml")
        self.assertEqual(boundary.engagement_id, "acme-2026-08")
        self.assertEqual(boundary.in_scope[0].pattern, "*.acme.example")

    def test_templates_have_no_unsubstituted_placeholders(self):
        self.scaffold()
        for name in ("CLAUDE.md", "status.md", "session.md"):
            text = (self.engagement / name).read_text(encoding="utf-8")
            self.assertNotIn("{{", text, f"{name} still contains an unsubstituted placeholder")

    def test_settings_pins_absolute_interpreter(self):
        self.scaffold()
        settings = json.loads((self.engagement / ".claude" / "settings.json").read_text())
        for event, entries in settings["hooks"].items():
            for entry in entries:
                command = entry["hooks"][0]["command"]
                self.assertIn(PYTHON, command)
                # The whole point: no bare `python3`, which could resolve to an interpreter
                # without PyYAML -- and a hook that dies on import fails OPEN.
                self.assertNotIn('"python3"', command)

    def test_every_built_control_is_wired(self):
        self.scaffold()
        settings = json.loads((self.engagement / ".claude" / "settings.json").read_text())
        wired = " ".join(e["hooks"][0]["command"]
                         for entries in settings["hooks"].values() for e in entries)
        for script in ("scope_guard.py", "no_handrolled_loops.py",
                       "canary_check.py", "validate_findings.py"):
            self.assertIn(script, wired, f"{script} exists but is not wired into the engagement")

    def test_no_hook_points_at_a_missing_script(self):
        # An erroring hook is not a denying hook.
        self.scaffold()
        settings = json.loads((self.engagement / ".claude" / "settings.json").read_text())
        import shlex as _shlex
        for entries in settings["hooks"].values():
            for entry in entries:
                # shlex.split, not a regex: the command is shell-quoted, and ordinary paths are
                # correctly left unquoted by shlex.quote.
                tokens = _shlex.split(entry["hooks"][0]["command"])
                scripts = [t for t in tokens if t.endswith((".py", ".sh"))]
                self.assertTrue(scripts, f"no script in: {entry['hooks'][0]['command']}")
                self.assertTrue(Path(scripts[0]).is_file(), f"{scripts[0]} does not exist")

    def test_hook_command_survives_a_hostile_engagement_path(self):
        """A quote in --root injected arbitrary shell content into EVERY wired hook at once.

        The scaffolder writes the enforcement layer; it is the last place that can afford to
        build a shell command by string interpolation.
        """
        import shlex as _shlex
        hostile = self.root / 'we"ird \'dir'
        hostile.mkdir()
        code = new_engagement.main(
            base_args(str(hostile), str(self.auth_doc)))
        self.assertEqual(code, 0)
        settings = json.loads(
            (hostile / "acme-2026-08" / ".claude" / "settings.json").read_text())
        for entries in settings["hooks"].values():
            for entry in entries:
                command = entry["hooks"][0]["command"]
                # It must still parse as a shell command, and yield exactly the three parts.
                tokens = _shlex.split(command)
                self.assertEqual(len(tokens), 3, f"injection changed the shape: {command}")
                self.assertTrue(tokens[0].startswith("RG_ENGAGEMENT_ROOT="))
                self.assertTrue(Path(tokens[2]).is_file())


class TestHooksFireEndToEnd(ScaffoldHarness):
    """Execute the generated hook command verbatim. This is the acceptance test."""

    def run_generated_hook(self, command_json: dict) -> tuple[int, str]:
        settings = json.loads((self.engagement / ".claude" / "settings.json").read_text())
        hook_command = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        proc = subprocess.run(
            hook_command,
            shell=True,
            input=json.dumps(command_json),
            capture_output=True,
            text=True,
            timeout=30,
        )
        return proc.returncode, proc.stdout

    def bash_payload(self, cmd: str) -> dict:
        return {"cwd": "/", "hook_event_name": "PreToolUse", "tool_name": "Bash",
                "tool_input": {"command": cmd}}

    def test_hook_denies_out_of_scope_host(self):
        self.scaffold()
        code, out = self.run_generated_hook(self.bash_payload("curl -s https://evil.example.com/"))
        self.assertEqual(code, 0)
        decision = json.loads(out)["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "deny")
        self.assertIn("out of scope", decision["permissionDecisionReason"].lower())

    def test_hook_denies_over_ceiling(self):
        self.scaffold(**{"--ceiling": 1})
        code, out = self.run_generated_hook(
            self.bash_payload("curl -X POST https://app.acme.example/v1/x -d '{}'")
        )
        self.assertEqual(code, 0)
        self.assertIn("ceiling", json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"].lower())

    def test_hook_denies_undeterminable_target(self):
        self.scaffold()
        code, out = self.run_generated_hook(self.bash_payload("curl -s https://$HOST/api"))
        self.assertEqual(code, 0)
        self.assertIn("undeterminable", json.loads(out)["hookSpecificOutput"]["permissionDecisionReason"].lower())

    def test_hook_allows_in_scope_tier_1(self):
        self.scaffold()
        code, out = self.run_generated_hook(self.bash_payload("curl -s https://app.acme.example/"))
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "", "an allowed call must produce no output")

    def test_hook_resolves_engagement_from_env_not_cwd(self):
        # cwd is '/' in every payload above. The scaffolder pins RG_ENGAGEMENT_ROOT so the guard
        # finds the right boundary regardless of where the agent happens to be working.
        self.scaffold()
        _, out = self.run_generated_hook(self.bash_payload("curl -s https://evil.example.com/"))
        self.assertIn("acme-2026-08", out)


class TestRefusals(ScaffoldHarness):
    def test_refuses_missing_authorization_document(self):
        self.assertEqual(
            new_engagement.main(base_args(str(self.root), str(self.root / "nope.pdf"))), 1
        )
        self.assertFalse(self.engagement.exists(), "refused scaffold must leave nothing behind")

    def test_refuses_to_overwrite_existing_engagement(self):
        self.assertEqual(self.scaffold(), 0)
        self.assertEqual(self.scaffold(), 1)

    def test_refuses_interpreter_without_pyyaml(self):
        fake = self.root / "fake-python"
        fake.write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        fake.chmod(0o755)
        self.assertEqual(self.scaffold(**{"--python": str(fake)}), 1)
        self.assertFalse(self.engagement.exists())

    def test_refuses_relative_interpreter(self):
        self.assertEqual(self.scaffold(**{"--python": "python3"}), 1)

    def test_refuses_ceiling_above_mode_default(self):
        self.assertEqual(self.scaffold(**{"--mode": "posture", "--ceiling": 3}), 1)
        self.assertFalse(self.engagement.exists())

    def test_refuses_redteam_without_emergency_contact(self):
        self.assertEqual(self.scaffold(**{"--mode": "redteam", "--ceiling": 3}), 1)

    def test_refuses_malformed_asset_spec(self):
        args = base_args(str(self.root), str(self.auth_doc))
        args[args.index("WILDCARD:*.acme.example")] = "no-colon-here"
        self.assertEqual(new_engagement.main(args), 1)


class TestWhiteAndBlackBox(ScaffoldHarness):
    """Both engagement shapes must scaffold, because the same target may be audited either way."""

    def test_black_box_wildcard_only(self):
        self.assertEqual(self.scaffold(), 0)

    def test_white_box_adds_source_code_asset(self):
        args = base_args(str(self.root), str(self.auth_doc)) + [
            "--in-scope", "SOURCE_CODE:github.com/acme/app",
            "--crown-jewel", "member submission media",
        ]
        self.assertEqual(new_engagement.main(args), 0)
        settings = (self.engagement / "scope.yaml").read_text()
        self.assertIn("SOURCE_CODE", settings)

    def test_source_code_asset_authorises_no_network_target(self):
        # A SOURCE_CODE entry names a repo, not a destination. It must not become a licence to
        # send requests to github.com.
        args = base_args(str(self.root), str(self.auth_doc)) + [
            "--in-scope", "SOURCE_CODE:github.com/acme/app"
        ]
        self.assertEqual(new_engagement.main(args), 0)
        settings = json.loads((self.engagement / ".claude" / "settings.json").read_text())
        hook_command = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        proc = subprocess.run(
            hook_command, shell=True,
            input=json.dumps({"cwd": "/", "tool_name": "Bash",
                              "tool_input": {"command": "curl -s https://github.com/acme/app"}}),
            capture_output=True, text=True, timeout=30,
        )
        self.assertIn("out of scope", proc.stdout.lower())


if __name__ == "__main__":
    unittest.main()
