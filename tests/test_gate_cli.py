"""Tests for /rg:gate -- writing and approving the phase plan (spec §9.3.2, §9.7).

The acceptance test that matters: `canary_check.py` denies a tier-2 write with no plan, and
permits the same write once a plan naming it has been written and approved. Before this module
existed, `ledger/plan.json` had no producer at all, so path (b) of §9.4.1 -- client pre-approval --
was unreachable and tier-2 testing was blocked by construction.
"""

from __future__ import annotations

import io
import json
import os
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
environment: production
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


class TestEnvironmentGate(Harness):
    """RG-1 §3.1/§4.8: Gate 1 refuses an engagement that has not said which environment it is.

    Siting, by the §4.8 test -- *name a healthy engagement state at which this fires*: there is
    none. The declaration is a scope fact, written when scope.yaml is written, which is strictly
    before Gate 1. A healthy engagement has it by the time anyone asks to approve a plan.

    Contrast with the *discrepancy* between the declaration and what was observed, which cannot
    exist at Gate 1 at all -- every signal that would raise it requires contact with the asset,
    and under §9.7 no contact happens until after Gate 1 approves. That check lives at finding
    creation and report assembly instead. Sited here it would fire on 0% of everything, which
    §2.3 calls worse than a wrong rule because it reads as coverage.
    """

    def set_environment(self, line: "str | None"):
        text = "\n".join(l for l in SCOPE.splitlines() if not l.startswith("environment:"))
        if line is not None:
            text += f"\nenvironment: {line}"
        (self.root / "scope.yaml").write_text(text + "\n", encoding="utf-8")

    def test_approval_is_refused_when_no_environment_is_declared(self):
        self.write_plan()
        self.set_environment(None)
        code, _, err = self.approve()
        self.assertEqual(code, 1)
        self.assertIn("ENVIRONMENT_UNDECLARED", err)

    def test_approval_is_refused_on_unknown(self):
        self.write_plan()
        self.set_environment("unknown")
        code, _, err = self.approve()
        self.assertEqual(code, 1)
        self.assertIn("ENVIRONMENT_UNDECLARED", err)
        self.assertIn("unknown", err)

    def test_approval_is_refused_on_an_unrecognised_value(self):
        self.write_plan()
        self.set_environment("staging-ish")
        code, _, err = self.approve()
        self.assertEqual(code, 1)
        self.assertIn("ENVIRONMENT_UNDECLARED", err)
        self.assertIn("staging-ish", err)

    def test_a_refused_approval_writes_no_gate_row(self):
        # A refusal that still records an approval is not a refusal.
        self.write_plan()
        self.set_environment(None)
        self.approve()
        self.assertEqual(gate_cli.read_jsonl(self.root / "ledger" / "gates.jsonl"), [])

    def test_every_declared_environment_approves(self):
        # The gate must not fire on a healthy engagement -- a gate that does gets switched off.
        for value in gate_cli.scope_mod.ENVIRONMENTS:
            with self.subTest(environment=value):
                self.set_environment(value)
                self.write_plan()
                code, _, err = self.approve()
                self.assertEqual(code, 0, err)


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


    def test_rows_logged_before_a_denied_dispatch_do_not_exhaust_the_budget(self):
        """B-003 end to end: log-before-write means a refused attempt still leaves a row."""
        self.write_plan()  # max_writes = 10
        self.approve()

        rows = [{
            "purpose": "test", "state": "denied_not_sent", "method": "POST",
            "route_template": "/rest/v1/email_subscription",
            "operation": "POST /rest/v1/email_subscription",
        } for _ in range(10)]
        (self.root / "ledger" / "cleanup.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

        allow, reason = self.evaluate()
        self.assertTrue(allow, f"zero writes were dispatched, got: {reason}")


class TestDocumentedOperationLabelIsUsable(Harness):
    """B-002: a plan written with the documented `[:operation]` field must still authorise.

    `--write-endpoint METHOD:/route[:operation][:max_writes]` invites a human-readable flow label
    ("signup"). `canary_check.plan_preapproval()` matches the entry's `operation` against
    `resolve_operation()`'s identifier ("POST /route"), so a label silently made the plan entry
    unmatchable and the pre-approved write impossible to perform.
    """

    ROUTE = "/members/api/send-magic-link/"

    def write_labelled_plan(self, spec: str = None):
        args = ["plan", "--phase", "P3-webtest", "--asset", "A-014", "--max-tier", "2",
                "--write-endpoint", spec or f"POST:{self.ROUTE}:signup:2"]
        return self.run_cli(*args)

    def evaluate(self, method="POST", route=None, body='{"email":"RedGold-TEST-1@example.invalid"}'):
        command = (f"curl -sS -X {method} https://api.acme.example{route or self.ROUTE} "
                   f"-d '{body}'")
        return canary_check.evaluate(
            {"tool_name": "Bash", "tool_input": {"command": command}}, self.root)

    # --- the property that is broken ---------------------------------------------------

    def test_labelled_write_endpoint_is_accepted_by_canary_check(self):
        code, _, err = self.write_labelled_plan()
        self.assertEqual(code, 0, err)
        allow, reason = self.evaluate()
        self.assertTrue(allow, f"the plan names this write endpoint; got: {reason}")

    def test_the_human_label_survives_in_the_plan(self):
        self.write_labelled_plan()
        entry = json.loads((self.root / "ledger" / "plan.json").read_text())["write_endpoints"][0]
        self.assertEqual(entry["method"], "POST")
        self.assertEqual(entry["route_template"], self.ROUTE)
        self.assertEqual(entry["max_writes"], 2)
        self.assertEqual(entry["label"], "signup")

    # --- and the denials that must keep working ----------------------------------------

    def test_a_different_route_is_still_denied(self):
        self.write_labelled_plan()
        allow, reason = self.evaluate(route="/members/api/delete-account/")
        self.assertFalse(allow, "a route the plan does not name must not be authorised")
        self.assertIn("does not name", reason)

    def test_a_different_method_is_still_denied(self):
        self.write_labelled_plan()
        allow, reason = self.evaluate(method="DELETE")
        self.assertFalse(allow, "a method the plan does not name must not be authorised")
        self.assertIn("no write authorisation", reason)

    def test_a_write_with_no_plan_and_no_proven_canary_is_still_denied(self):
        # No plan at all, and no cleanup.jsonl row proving a canary for this operation was
        # created and deleted -- the original incident, still blocked.
        allow, reason = self.evaluate()
        self.assertFalse(allow)
        self.assertIn("no write authorisation", reason)

    def test_a_canary_that_never_reached_deleted_does_not_authorise(self):
        (self.root / "ledger" / "cleanup.jsonl").write_text(json.dumps({
            "purpose": "canary", "state": "pending", "method": "POST",
            "route_template": self.ROUTE, "operation": f"POST {self.ROUTE}",
        }) + "\n", encoding="utf-8")
        allow, reason = self.evaluate()
        self.assertFalse(allow, "a canary that was never proven deleted authorises nothing")
        self.assertIn("no write authorisation", reason)

    def test_exceeding_max_writes_is_still_denied(self):
        self.write_labelled_plan()  # max_writes = 2
        rows = [{"purpose": "test-write", "state": "pending", "method": "POST",
                 "route_template": self.ROUTE, "operation": f"POST {self.ROUTE}"}] * 2
        (self.root / "ledger" / "cleanup.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        allow, reason = self.evaluate()
        self.assertFalse(allow)
        self.assertIn("budget", reason.lower())

    def test_within_budget_is_allowed(self):
        self.write_labelled_plan()  # max_writes = 2
        (self.root / "ledger" / "cleanup.jsonl").write_text(json.dumps({
            "purpose": "test-write", "state": "pending", "method": "POST",
            "route_template": self.ROUTE, "operation": f"POST {self.ROUTE}",
        }) + "\n", encoding="utf-8")
        allow, reason = self.evaluate()
        self.assertTrue(allow, reason)


class TestPhaseCompletionCoverage(Harness):
    """RG-1 §8.2: a phase may not complete having done nothing.

    `ENGAGEMENT-B` held the only SOURCE_CODE asset, and its `findings/`, `evidence/`
    and `deliverables/` are empty directories with six 0-byte ledger files. Nothing refused to let
    it exist. "We found nothing" and "we did not look" must be mechanically distinguishable.
    """

    def complete(self, phase: str = "P3-webtest"):
        return self.run_cli("complete", "--phase", phase)

    def write_findings(self, records: list[dict]):
        (self.root / "findings").mkdir(exist_ok=True)
        (self.root / "findings" / "phase.json").write_text(json.dumps(records), encoding="utf-8")

    def write_coverage(self, rows: list[dict]):
        (self.root / "coverage.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    def finding(self, **overrides) -> dict:
        record = {"id": "F-001", "title": "Exposed .env file", "asset": "https://api.acme.example",
                  "finding_class": "technical", "severity": "high", "status": "PROVEN",
                  "verified": "replayed", "confidence": "confirmed",
                  "created": "2026-08-05T01:20:00Z"}
        record.update(overrides)
        return record

    def test_a_phase_with_no_findings_and_no_negatives_is_refused(self):
        code, _, err = self.complete()
        self.assertEqual(code, 1)
        self.assertIn("COVERAGE_EMPTY_PHASE", err)
        self.assertIn("P3-webtest", err)

    def test_a_phase_that_found_something_completes(self):
        self.write_findings([self.finding()])
        code, out, err = self.complete()
        self.assertEqual(code, 0, err)
        self.assertIn("P3-webtest", out)

    def test_a_phase_that_found_nothing_but_recorded_looking_completes(self):
        # The respectable outcome: checks ran and were clean. That is a result, not an absence.
        self.write_findings([self.finding(result="absent", severity="info", status="SPECULATED",
                                          verified="none")])
        code, out, err = self.complete()
        self.assertEqual(code, 0, err)

    def test_absent_rows_in_the_coverage_register_also_satisfy_the_rule(self):
        self.write_coverage([{"phase": "P3-webtest", "check_id": "header.hsts",
                              "asset_id": "A-014", "outcome": "absent"}])
        code, _, err = self.complete()
        self.assertEqual(code, 0, err)

    def test_records_that_only_say_the_check_could_not_run_do_not_satisfy_it(self):
        # `not_applicable` is "structurally meaningless here", not "looked and it was clean".
        # 36 of these against one dead port is precisely the shape that must still refuse.
        self.write_findings([self.finding(id=f"F-{i:03d}", result="not_applicable",
                                          severity="info") for i in range(36)])
        self.write_coverage([{"phase": "P3-webtest", "outcome": "not_attempted",
                              "reason": "component_down"}])
        code, _, err = self.complete()
        self.assertEqual(code, 1)
        self.assertIn("COVERAGE_EMPTY_PHASE", err)

    def test_another_phases_work_does_not_close_this_phase(self):
        self.write_coverage([{"phase": "P2-surface", "outcome": "absent"}])
        code, _, err = self.complete("P3-webtest")
        self.assertEqual(code, 1)
        self.assertIn("COVERAGE_EMPTY_PHASE", err)

    def test_completion_is_recorded_in_the_activity_ledger(self):
        self.write_findings([self.finding()])
        self.assertEqual(self.complete()[0], 0)
        rows = [json.loads(l) for l in
                (self.root / "ledger" / "activity.jsonl").read_text().splitlines() if l.strip()]
        self.assertEqual(rows[-1]["event_type"], "phase.complete")
        self.assertEqual(rows[-1]["phase"], "P3-webtest")

    def test_a_refused_completion_writes_no_ledger_row(self):
        self.assertEqual(self.complete()[0], 1)
        self.assertFalse((self.root / "ledger" / "activity.jsonl").is_file())


class TestEngagementClose(Harness):
    """RG-1 §9.1a: the binding site for the two Release 1 coverage rules.

    `report.py --check` and `gate_cli.py complete` are both opt-in -- an operator who runs neither
    is stopped by nothing, and under P1 a control that depends on someone remembering is not a
    control. There is no Claude Code lifecycle event for "engagement close" (every hook event is
    turn-, tool-, session- or subagent-scoped), so closure is made an act with a gate on it rather
    than an absence nobody records.
    """

    def close(self, *extra):
        return self.run_cli("close", *extra)

    def finding(self, **overrides) -> dict:
        record = {"id": "F-001", "title": "Exposed .env file", "asset": "https://api.acme.example",
                  "finding_class": "technical", "severity": "high", "status": "PROVEN",
                  "verified": "replayed", "confidence": "confirmed",
                  "created": "2026-08-05T01:20:00Z"}
        record.update(overrides)
        return record

    def write_findings(self, records: list[dict]):
        (self.root / "findings").mkdir(exist_ok=True)
        (self.root / "findings" / "phase.json").write_text(json.dumps(records), encoding="utf-8")

    def write_deliverable(self, *, newer_than_corpus: bool = True):
        path = self.root / "deliverables" / "report-tier1.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("# report\n", encoding="utf-8")
        # The corpus fixture is stamped 2026-08-05T01:20:00Z. Set the mtime explicitly rather
        # than relying on wall-clock ordering, which is what the prior engagement got wrong.
        stamp = 1786000000 if newer_than_corpus else 1000000000
        os.utime(path, (stamp, stamp))
        return path

    def complete_a_phase(self):
        code, _, err = self.run_cli("complete", "--phase", "P3-webtest")
        self.assertEqual(code, 0, err)

    def healthy_engagement(self):
        self.write_findings([self.finding()])
        self.complete_a_phase()
        self.write_deliverable()

    # --- the three refusals ----------------------------------------------------------------

    def test_an_engagement_that_recorded_nothing_cannot_close(self):
        code, _, err = self.close()
        self.assertEqual(code, 1)
        self.assertIn("COVERAGE_EMPTY_PHASE", err)

    def test_an_engagement_with_no_completed_phase_cannot_close(self):
        self.write_findings([self.finding()])
        self.write_deliverable()
        code, _, err = self.close()
        self.assertEqual(code, 1)
        self.assertIn("PHASE_NEVER_COMPLETED", err)

    def test_an_engagement_whose_deliverable_was_never_written_cannot_close(self):
        self.write_findings([self.finding()])
        self.complete_a_phase()
        code, _, err = self.close()
        self.assertEqual(code, 1)
        self.assertIn("REPORT_STALE", err)

    def test_an_engagement_whose_deliverable_predates_its_findings_cannot_close(self):
        self.write_findings([self.finding()])
        self.complete_a_phase()
        self.write_deliverable(newer_than_corpus=False)
        code, _, err = self.close()
        self.assertEqual(code, 1)
        self.assertIn("REPORT_STALE", err)

    def test_every_failing_check_is_named_not_only_the_first(self):
        # An operator who fixes one refusal and is immediately refused again for a different
        # reason learns to distrust the gate. All of it, at once.
        code, _, err = self.close()
        self.assertEqual(code, 1)
        self.assertIn("COVERAGE_EMPTY_PHASE", err)
        self.assertIn("PHASE_NEVER_COMPLETED", err)

    # --- the healthy path ------------------------------------------------------------------

    def test_a_complete_engagement_closes(self):
        self.healthy_engagement()
        code, out, err = self.close()
        self.assertEqual(code, 0, err)

    def test_closure_is_recorded_in_the_gates_ledger(self):
        self.healthy_engagement()
        self.assertEqual(self.close()[0], 0)
        rows = [json.loads(l) for l in
                (self.root / "ledger" / "gates.jsonl").read_text().splitlines() if l.strip()]
        closures = [r for r in rows if r.get("event_type") == "gate.close"]
        self.assertEqual(len(closures), 1)
        self.assertEqual(closures[0]["decision"], "closed")
        self.assertTrue(str(closures[0]["id"]).startswith("G-"))

    def test_a_refused_close_records_no_closure(self):
        # The absence of a gate.close row is the only evidence that an engagement was abandoned
        # rather than closed. A refused close that wrote one would destroy that signal.
        self.assertEqual(self.close()[0], 1)
        path = self.root / "ledger" / "gates.jsonl"
        rows = [json.loads(l) for l in path.read_text().splitlines() if l.strip()] \
            if path.is_file() else []
        self.assertEqual([r for r in rows if r.get("event_type") == "gate.close"], [])

    def test_recorded_negatives_alone_satisfy_the_coverage_half(self):
        # "We looked and found nothing" is a respectable outcome and must be able to close --
        # but it closes on a *deliverable*, exactly like every other engagement. The requirement
        # is "an engagement does not close on a deliverable that was never written"; it has no
        # exemption for engagements that found nothing, because those are precisely the
        # engagements whose report is the entire product.
        #
        # This test previously asserted `exit 0` with no deliverable on disk, on the reasoning
        # that "no findings exist, so there is nothing for a deliverable to predate". That is a
        # test written to match `freshness_violation`'s empty-corpus early return rather than to
        # match the rule the rule exists for. See the adversarial review, S3.
        (self.root / "coverage.jsonl").write_text(
            json.dumps({"phase": "P3-webtest", "check_id": "header.hsts", "asset_id": "A-014",
                        "outcome": "absent"}) + "\n", encoding="utf-8")
        self.complete_a_phase()
        self.write_deliverable()
        code, _, err = self.close()
        self.assertEqual(code, 0, err)

    def test_an_empty_corpus_does_not_exempt_the_deliverable(self):
        # S3. The false-assurance case: `close` exited 0 and printed "deliverables/report-tier1.md
        # postdates every finding" about a file that did not exist -- a fabricated assurance
        # emitted by the control whose whole purpose is to prevent fabricated assurance.
        (self.root / "coverage.jsonl").write_text(
            json.dumps({"phase": "P1", "check_id": "tls", "asset_id": "A-014",
                        "outcome": "absent"}) + "\n", encoding="utf-8")
        self.run_cli("complete", "--phase", "P1")
        code, out, err = self.close()
        self.assertEqual(code, 1)
        self.assertIn("REPORT_STALE", err)
        self.assertNotIn("postdates every finding", out)
        self.assertFalse((self.root / "deliverables" / "report-tier1.md").is_file())

    def test_a_phase_does_not_close_on_a_record_that_says_we_did_not_look(self):
        # S4. `phase_evidence`'s own docstring excludes both `not_applicable` ("structurally
        # meaningless here") and `not_attempted` ("did not look"); only the first was
        # implemented, so `not_attempted` fell through the `elif` and was counted as a finding.
        # A record that says "we did not look" is the canonical input this gate exists to refuse.
        self.write_findings([self.finding(
            id="F-001", title="Auth bypass -- did not look", result="not_attempted",
            reason="ceiling", severity="info", status="SPECULATED")])
        code, _, err = self.run_cli("complete", "--phase", "P1")
        self.assertEqual(code, 1)
        self.assertIn("COVERAGE_EMPTY_PHASE", err)

    def test_a_phase_still_closes_on_a_real_finding(self):
        # The other half of the siting test: the gate must not start firing on healthy input.
        self.write_findings([self.finding(result="present")])
        self.assertEqual(self.run_cli("complete", "--phase", "P1")[0], 0)

    def test_a_voided_gate_one_approval_stops_the_close(self):
        # S10. §9.7: an amended scope.yaml or an edited plan voids the approval -- including an
        # amendment that changes `environment` after Gate 1 approved it, which changes the cap
        # every agent-written record is scored against at report assembly. An engagement whose
        # approval was voided mid-flight was closing clean, with a `gate.close` row asserting
        # nothing about the gate it was closed under.
        self.write_plan()
        code, _, err = self.approve()
        self.assertEqual(code, 0, err)
        self.healthy_engagement()
        self.assertEqual(self.close()[0], 0)

        (self.root / "scope.yaml").write_text(
            SCOPE.replace("environment: production", "environment: development"),
            encoding="utf-8")
        code, _, err = self.close()
        self.assertEqual(code, 1)
        self.assertIn("GATE_1_VOID", err)

    def test_an_engagement_that_never_approved_a_plan_still_closes(self):
        # `approve` is opt-in and many engagements never write a plan. A close gate that refused
        # every unapproved engagement would fire on healthy input and get switched off; what it
        # can honestly assert is that an approval which *exists* is still valid.
        self.healthy_engagement()
        self.assertEqual(self.close()[0], 0)


class TestWriteEndpointParsing(unittest.TestCase):
    """The field syntax itself -- unambiguous, and shaped as canary_check consumes it."""

    def test_positional_label_and_budget(self):
        entry = gate_cli.parse_write_endpoint("POST:/members/api/send-magic-link/:signup:2")
        self.assertEqual(entry["operation"], "POST /members/api/send-magic-link/")
        self.assertEqual(entry["label"], "signup")
        self.assertEqual(entry["max_writes"], 2)

    def test_keyed_fields_are_order_independent(self):
        a = gate_cli.parse_write_endpoint("POST:/x:max=3:label=signup")
        b = gate_cli.parse_write_endpoint("POST:/x:label=signup:max=3")
        self.assertEqual(a, b)
        self.assertEqual(a["max_writes"], 3)
        self.assertEqual(a["label"], "signup")

    def test_bare_route_defaults(self):
        entry = gate_cli.parse_write_endpoint("post:/x")
        self.assertEqual(entry["method"], "POST")
        self.assertEqual(entry["operation"], "POST /x")
        self.assertEqual(entry["max_writes"], 1)
        self.assertIsNone(entry["label"])

    def test_bare_integer_third_field_is_the_budget(self):
        self.assertEqual(gate_cli.parse_write_endpoint("POST:/x:10")["max_writes"], 10)

    def test_route_template_is_normalised_like_canary_check_normalises_it(self):
        # An operator naming a literal id must not produce an entry that can never match.
        entry = gate_cli.parse_write_endpoint("DELETE:/api/notes/42")
        self.assertEqual(entry["route_template"], "/api/notes/{id}")
        self.assertEqual(entry["operation"], "DELETE /api/notes/{id}")

    def test_graphql_requires_a_mutation_name(self):
        with self.assertRaises(gate_cli.GateCliError) as ctx:
            gate_cli.parse_write_endpoint("POST:/graphql")
        self.assertIn("mutation", str(ctx.exception).lower())

    def test_graphql_mutation_name_becomes_the_operation(self):
        entry = gate_cli.parse_write_endpoint("POST:/graphql:op=deleteAccount:max=1")
        self.assertEqual(entry["operation"], "deleteAccount")

    def test_graphql_plan_entry_matches_only_its_own_mutation(self):
        self.assertEqual(
            gate_cli.parse_write_endpoint("POST:/graphql:op=createComment")["operation"],
            canary_check.resolve_operation(
                "/graphql", '{"operationName":"createComment"}', "POST"))


if __name__ == "__main__":
    unittest.main()
