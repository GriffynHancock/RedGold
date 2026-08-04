"""Tests for /rg:gate -- writing and approving the phase plan (spec §9.3.2, §9.7).

The acceptance test that matters: `canary_check.py` denies a tier-2 write with no plan, and
permits the same write once a plan naming it has been written and approved. Before this module
existed, `ledger/plan.json` had no producer at all, so path (b) of §9.4.1 -- client pre-approval --
was unreachable and tier-2 testing was blocked by construction.
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import gate_cli  # noqa: E402
import canary_check  # noqa: E402

RATE_PROBE = REPO / "scripts" / "rate_probe.sh"

SCOPE = """engagement_id: gate-test
client: {name: C, contact: c@example.invalid}
authorization:
  document: ../a.pdf
  signed_by: S
  signed_date: 2020-01-01
  window_start: 2020-01-01
  window_end: 2099-12-31
mode: audit
ceiling: 2
in_scope:
  - {asset_type: WILDCARD, pattern: "*.acme.example"}
constraints: {no_destructive: true, max_requests_per_burst: 10}
"""

CONFIRMED_ASSET = {
    "asset_id": "A-014",
    "asset_type": "URL",
    "identifier": "api.acme.example",
    "discovery_method": "manual",
    "attribution_signals": [],
    "attribution_confidence": "HIGH",
    "matched_boundary_entry": "WILDCARD:*.acme.example",
    "status": "CONFIRMED",
    "first_seen": "2026-01-01T00:00:00+00:00",
    "last_seen": "2026-01-01T00:00:00+00:00",
}


class Harness(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        (self.root / "scope.yaml").write_text(SCOPE, encoding="utf-8")
        (self.root / "assets").mkdir()
        (self.root / "ledger").mkdir()
        (self.root / "assets" / "register.jsonl").write_text(
            json.dumps(CONFIRMED_ASSET) + "\n", encoding="utf-8")

    def run_cli(self, *argv) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = gate_cli.main(["--root", str(self.root), *argv])
        return code, out.getvalue(), err.getvalue()

    def write_plan(self, **overrides):
        args = ["plan", "--phase", "P3-webtest", "--asset", "A-014", "--max-tier", "2",
                "--write-endpoint", "POST:/rest/v1/email_subscription:10"]
        return self.run_cli(*args)

    def approve(self):
        return self.run_cli("approve", "--reason", "test approval")


class TestPlan(Harness):
    def test_unconfirmed_asset_is_refused(self):
        code, _, err = self.run_cli("plan", "--phase", "P3", "--asset", "A-999", "--max-tier", "1")
        self.assertEqual(code, 1)
        self.assertIn("A-999", err)
        self.assertIn("not CONFIRMED", err)
        self.assertIn("/rg:scope promote", err)
        self.assertFalse((self.root / "ledger" / "plan.json").is_file())

    def test_max_tier_above_ceiling_is_refused(self):
        code, _, err = self.run_cli("plan", "--phase", "P3", "--asset", "A-014", "--max-tier", "3")
        self.assertEqual(code, 1)
        self.assertIn("exceeds the engagement ceiling", err)
        self.assertFalse((self.root / "ledger" / "plan.json").is_file())

    def test_valid_plan_is_written(self):
        code, out, _ = self.write_plan()
        self.assertEqual(code, 0)
        self.assertIn("NOT yet approved", out)
        plan = json.loads((self.root / "ledger" / "plan.json").read_text())
        self.assertEqual(plan["phase"], "P3-webtest")
        self.assertEqual(plan["assets"], ["A-014"])
        self.assertEqual(plan["write_endpoints"][0]["method"], "POST")
        self.assertEqual(plan["write_endpoints"][0]["route_template"], "/rest/v1/email_subscription")
        self.assertEqual(plan["write_endpoints"][0]["max_writes"], 10)


class TestApprove(Harness):
    def test_approve_with_no_plan_is_refused(self):
        code, _, err = self.approve()
        self.assertEqual(code, 1)
        self.assertIn("no ledger/plan.json exists", err)

    def test_approved_gate_validates(self):
        self.write_plan()
        code, out, _ = self.approve()
        self.assertEqual(code, 0)
        self.assertIn("Approved as G-001", out)
        ok, reason = gate_cli.check_gate(self.root, "G-001")
        self.assertTrue(ok, reason)

    def test_gate_ids_increment(self):
        self.write_plan()
        self.approve()
        self.write_plan()
        code, out, _ = self.approve()
        self.assertEqual(code, 0)
        self.assertIn("Approved as G-002", out)

    def test_editing_scope_after_approval_invalidates_the_gate(self):
        self.write_plan()
        self.approve()
        ok, _ = gate_cli.check_gate(self.root, "G-001")
        self.assertTrue(ok)

        scope_path = self.root / "scope.yaml"
        scope_path.write_text(scope_path.read_text() + "\n# amended\n", encoding="utf-8")

        ok, reason = gate_cli.check_gate(self.root, "G-001")
        self.assertFalse(ok)
        self.assertIn("scope.yaml has changed", reason)
        self.assertIn("void", reason)

    def test_editing_plan_after_approval_invalidates_it(self):
        self.write_plan()
        self.approve()
        plan_path = self.root / "ledger" / "plan.json"
        plan = json.loads(plan_path.read_text())
        plan["max_tier"] = 1
        plan_path.write_text(json.dumps(plan), encoding="utf-8")

        ok, reason = gate_cli.check_gate(self.root, "G-001")
        self.assertFalse(ok)
        self.assertIn("been edited", reason)
        self.assertIn("void", reason)

    def test_unknown_gate_ref_does_not_validate(self):
        ok, reason = gate_cli.check_gate(self.root, "G-404")
        self.assertFalse(ok)
        self.assertIn("does not exist", reason)


class TestBlockersAndResolve(Harness):
    def test_no_unresolved_blockers(self):
        code, out, _ = self.run_cli("blockers")
        self.assertEqual(code, 0)
        self.assertIn("no unresolved", out)

    def test_resolve_with_no_blockers_is_refused(self):
        code, _, err = self.run_cli("resolve", "1", "--decision", "allow", "--reason", "x")
        self.assertEqual(code, 1)
        self.assertIn("no unresolved blockers", err)

    def test_resolve_by_index_and_id(self):
        (self.root / "ledger" / "blockers.jsonl").write_text(
            json.dumps({"id": "B-001", "kind": "deviation", "raised_by": "rg-webtest",
                        "detail": "new asset", "raised": "2026-01-01T00:00:00Z",
                        "resolved": None, "resolution": None}) + "\n", encoding="utf-8")
        code, out, _ = self.run_cli("resolve", "1", "--decision", "allow", "--reason", "client ok'd it")
        self.assertEqual(code, 0)
        self.assertIn("B-001", out)
        rows = [json.loads(l) for l in
                (self.root / "ledger" / "blockers.jsonl").read_text().splitlines() if l.strip()]
        self.assertIsNotNone(rows[0]["resolved"])
        gate_rows = [json.loads(l) for l in
                     (self.root / "ledger" / "gates.jsonl").read_text().splitlines() if l.strip()]
        self.assertEqual(gate_rows[-1]["event_type"], "gate.resolve")
        self.assertEqual(gate_rows[-1]["decision"], "allow")


class TestRatePropeGateWiring(Harness):
    def run_probe(self, gate_ref: str) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(RATE_PROBE), "--root", str(self.root), "--gate-ref", gate_ref,
             "--url", "https://api.acme.example/rest/v1/email_subscription", "--max", "1"],
            capture_output=True, text=True, timeout=30,
        )

    def test_unknown_gate_ref_is_refused(self):
        proc = self.run_probe("G-404")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("does not exist", proc.stderr)

    def test_stale_gate_ref_is_refused(self):
        self.write_plan()
        self.approve()
        scope_path = self.root / "scope.yaml"
        scope_path.write_text(scope_path.read_text() + "\n# amended\n", encoding="utf-8")
        proc = self.run_probe("G-001")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("scope.yaml has changed", proc.stderr)


class TestEndToEndWriteAuthorisation(Harness):
    """The acceptance test: canary_check.py denies, then permits, the same write."""

    def evaluate(self, method="POST"):
        payload = {
            "tool_name": "Bash",
            "tool_input": {
                "command": (f"curl -sS -X {method} "
                            "https://api.acme.example/rest/v1/email_subscription "
                            '-d \'{"email":"a@b.example"}\'')
            },
        }
        return canary_check.evaluate(payload, self.root)

    def test_denied_then_permitted_after_plan_and_approval(self):
        allow, reason = self.evaluate()
        self.assertFalse(allow, "should be denied before any plan exists")
        self.assertIn("no write authorisation", reason)

        code, _, _ = self.write_plan()
        self.assertEqual(code, 0)
        code, _, _ = self.approve()
        self.assertEqual(code, 0)

        allow, reason = self.evaluate()
        self.assertTrue(allow, f"should be permitted after plan + approval, got: {reason}")

    def test_budget_exhaustion_denies_again(self):
        self.write_plan()  # max_writes = 10
        self.approve()

        # 10 non-canary writes already recorded against this exact operation.
        rows = []
        for i in range(10):
            rows.append({
                "purpose": "test-write", "state": "orphaned", "method": "POST",
                "route_template": "/rest/v1/email_subscription",
                "operation": "POST /rest/v1/email_subscription",
            })
        (self.root / "ledger" / "cleanup.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

        allow, reason = self.evaluate()
        self.assertFalse(allow)
        self.assertIn("budget", reason.lower())


if __name__ == "__main__":
    unittest.main()
