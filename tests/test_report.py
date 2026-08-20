"""Tests for /rg:report -- the client deliverable (spec §10.6, §16).

The report is where every earlier control either pays off or is revealed as decorative. These
tests are mostly about what must NOT appear.
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import report  # noqa: E402

SCOPE = """engagement_id: report-test
client: {name: Acme Pty Ltd, contact: founder@acme.example}
authorization:
  document: ../a.pdf
  signed_by: Jane Founder
  signed_date: 2026-08-01
  window_start: 2026-08-01
  window_end: 2026-08-30
mode: audit
ceiling: 2
in_scope:
  - {asset_type: WILDCARD, pattern: "*.acme.example"}
constraints: {no_destructive: true}
"""


def finding(**overrides) -> dict:
    record = {
        "id": "F-001", "title": "Anonymous read access to profiles",
        "asset": "https://api.acme.example/profiles",
        "finding_class": "technical", "status": "PROVEN", "verified": "replayed",
        "confidence": "confirmed", "severity": "high",
        "evidence_ptr": "evidence/F-001.http",
        "real_world_impact": "Any visitor can read every user's email address.",
        "remediation": "Enable row-level security on the profiles table.",
        "tested_at_tier": 1,
    }
    record.update(overrides)
    return record


class Harness(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        (self.root / "scope.yaml").write_text(SCOPE, encoding="utf-8")
        for sub in ("assets", "ledger", "findings", "evidence", "deliverables"):
            (self.root / sub).mkdir()
        (self.root / "evidence" / "F-001.http").write_text("GET /profiles\n\n200 OK\n",
                                                           encoding="utf-8")

    def write(self, records: list[dict]):
        (self.root / "findings" / "phase1.json").write_text(json.dumps(records), encoding="utf-8")

    def render(self, tier: int = 1) -> str:
        return report.render(self.root, tier)


class TestWhatAppears(Harness):
    def test_verified_confirmed_finding_appears(self):
        self.write([finding()])
        text = self.render()
        self.assertIn("Anonymous read access to profiles", text)
        self.assertIn("Any visitor can read every user's email address.", text)
        self.assertIn("Enable row-level security", text)

    def test_findings_are_severity_ordered(self):
        self.write([finding(id="F-001", title="Low thing", severity="low"),
                    finding(id="F-002", title="Critical thing", severity="critical")])
        text = self.render()
        self.assertLess(text.index("Critical thing"), text.index("Low thing"))

    def test_coverage_section_is_always_present(self):
        self.write([finding()])
        self.assertIn("What we checked and did not find", self.render())

    def test_negative_results_are_listed(self):
        self.write([finding(), finding(id="F-002", title="Exposed .env file", result="absent",
                                       severity="info", status="SPECULATED", verified="none")])
        text = self.render()
        self.assertIn("1 checks ran and found nothing", text)
        self.assertIn("Exposed .env file", text)

    def test_empty_report_says_so_honestly(self):
        self.write([])
        text = self.render()
        self.assertIn("No confirmed findings", text)
        self.assertIn("not an empty report", text)

    def test_tier_1_adds_prioritised_next_steps(self):
        self.write([finding()])
        self.assertIn("Where to start", self.render(tier=1))
        self.assertNotIn("Where to start", self.render(tier=0))


class TestWhatMustNotAppear(Harness):
    def test_unverified_high_finding_is_not_in_the_body(self):
        self.write([finding(verified="none")])
        text = self.render()
        self.assertIn("Open questions", text)
        # It appears as an open question, never with a severity heading in Findings.
        self.assertNotIn("### F-001", text)

    def test_unresolvable_evidence_keeps_it_out_entirely(self):
        self.write([finding(evidence_ptr="evidence/does-not-exist.http")])
        text = self.render()
        self.assertIn("Recorded but not reportable", text)
        self.assertNotIn("### F-001", text)

    def test_prose_evidence_pointer_keeps_it_out(self):
        self.write([finding(evidence_ptr="Burp/thing (commentary); notes.md#1")])
        self.assertNotIn("### F-001", self.render())

    def test_unconfirmed_confidence_is_not_in_the_body(self):
        self.write([finding(confidence="probable")])
        self.assertNotIn("### F-001", self.render())

    def test_rollup_constituents_are_not_double_counted(self):
        rollup = finding(id="F-100", title="Location data exposed",
                         real_world_impact="Synthesis of F-001 and F-002.")
        self.write([finding(id="F-001"), finding(id="F-002", title="Second thing"), rollup])
        text = self.render()
        self.assertIn("Location data exposed", text)
        # F-001 and F-002 are referenced by the rollup, so they are not counted again.
        self.assertNotIn("### F-001 --", text)

    def test_low_severity_unverified_technical_still_appears(self):
        # The rule is about findings ABOVE Low; a Low finding does not need re-execution.
        self.write([finding(severity="low", verified="none", status="SPECULATED")])
        self.assertIn("### F-001", self.render())

    def test_posture_finding_with_na_appears_above_low(self):
        # Posture severity rests on an observed fact, not a demonstrated exploit.
        self.write([finding(finding_class="posture", verified="n/a", severity="high",
                            title="No MFA on the admin console")])
        self.assertIn("No MFA on the admin console", self.render())


class TestCleanupAppendix(Harness):
    def test_no_writes_says_so(self):
        self.write([finding()])
        self.assertIn("No data was written", self.render())

    def test_outstanding_test_data_gets_a_removal_query(self):
        (self.root / "ledger" / "cleanup.jsonl").write_text(
            json.dumps({"state": "orphaned"}) + "\n", encoding="utf-8")
        self.write([finding()])
        text = self.render()
        self.assertIn("Still present", text)
        self.assertIn("LIKE 'RedGold-TEST-report-test-%'", text)
        self.assertIn("data-lifecycle", text)


class TestLimitsAreStated(Harness):
    def test_the_guard_is_not_oversold(self):
        self.write([finding()])
        text = self.render()
        self.assertIn("defence in depth, not a guarantee", text)

    def test_absence_of_a_finding_is_not_claimed_as_absence_of_a_flaw(self):
        self.write([finding()])
        self.assertIn("not the same as a", self.render())

    def test_ceiling_is_disclosed(self):
        self.write([finding()])
        self.assertIn("tier 2", self.render())

    def test_untested_candidates_are_disclosed(self):
        (self.root / "assets" / "candidates.jsonl").write_text(
            json.dumps({"asset_id": "C-001", "identifier": "staging.acme.example",
                        "status": "CANDIDATE"}) + "\n", encoding="utf-8")
        self.write([finding()])
        self.assertIn("candidate asset(s) were left untested", self.render())


class TestReportFreshness(Harness):
    """RG-1 §8.6: a deliverable may not predate its own inputs.

    The prior engagement's deliverable was written 2026-08-04 20:38 and said "No confirmed findings" while
    `findings/baseline.json` (2026-08-05 01:20) held eleven, including a critical. Nothing
    detected it. Every other control in RG-1 is irrelevant to a client who receives that file.
    """

    EPOCH_OLD = 1_700_000_000  # well before any `created` used below
    EPOCH_NEW = 1_900_000_000  # well after

    def deliverable(self) -> Path:
        return self.root / "deliverables" / "report-tier1.md"

    def write_deliverable(self, mtime: int) -> Path:
        path = self.deliverable()
        path.write_text("# stale\n", encoding="utf-8")
        os.utime(path, (mtime, mtime))
        return path

    def check(self) -> tuple[int, str]:
        import io
        from contextlib import redirect_stderr, redirect_stdout
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = report.main(["--root", str(self.root), "--tier", "1", "--check"])
        return code, out.getvalue() + err.getvalue()

    def test_a_deliverable_older_than_the_newest_finding_is_refused(self):
        self.write([finding(created="2026-08-05T01:20:00Z")])
        self.write_deliverable(self.EPOCH_OLD)
        code, text = self.check()
        self.assertEqual(code, 1)
        self.assertIn("REPORT_STALE", text)
        self.assertIn("2026-08-05T01:20:00", text)

    def test_a_deliverable_newer_than_every_finding_passes(self):
        self.write([finding(created="2026-08-05T01:20:00Z")])
        self.write_deliverable(self.EPOCH_NEW)
        code, text = self.check()
        self.assertEqual(code, 0, text)
        self.assertNotIn("REPORT_STALE", text)

    def test_a_missing_deliverable_with_findings_on_disk_is_refused(self):
        self.write([finding(created="2026-08-05T01:20:00Z")])
        code, text = self.check()
        self.assertEqual(code, 1)
        self.assertIn("REPORT_STALE", text)

    def test_an_unparseable_created_stamp_cannot_certify_freshness(self):
        # Fail closed: an unreadable timestamp is not evidence that the report is current.
        self.write([finding(created="last Tuesday")])
        self.write_deliverable(self.EPOCH_NEW)
        code, text = self.check()
        self.assertEqual(code, 1)
        self.assertIn("REPORT_STALE", text)

    def test_an_engagement_with_no_records_at_all_is_not_stale(self):
        # Nothing to predate. The zero-zero rule (§8.2) is what catches this case, not this one.
        self.write([])
        self.write_deliverable(self.EPOCH_OLD)
        code, text = self.check()
        self.assertEqual(code, 0, text)

    def test_regenerating_the_report_clears_the_staleness(self):
        self.write([finding(created="2026-08-05T01:20:00Z")])
        self.write_deliverable(self.EPOCH_OLD)
        self.assertEqual(self.check()[0], 1)
        self.assertEqual(report.main(["--root", str(self.root), "--tier", "1"]), 0)
        self.assertEqual(self.check()[0], 0)

    def test_the_header_states_the_corpus_it_was_written_from(self):
        # Staleness must be visible in the artifact itself, not only to a script nobody runs.
        self.write([finding(created="2026-08-05T01:20:00Z"),
                    finding(id="F-002", title="Second", created="2026-08-04T09:00:00Z")])
        text = self.render()
        self.assertIn("2026-08-05T01:20:00", text)
        self.assertIn("2 finding record(s)", text)


class TestEnvironmentCapInTheReport(Harness):
    """RG-1 §6: the cap runs at report assembly too, not only in the scanner.

    Siting, by the §4.8 test -- *name a healthy engagement state at which this fires*: any
    engagement against a non-production environment that has produced a finding. `report.render`
    is the last point at which every producer's records are in one place, so it is where an
    agent-written record (rg-webtest, rg-codeaudit) is capped. The scanner caps its own output at
    write time; without this pass, nothing else's output is capped at all.
    """

    def set_environment(self, value: str):
        (self.root / "scope.yaml").write_text(
            SCOPE + f"environment: {value}\n", encoding="utf-8")

    def test_a_high_finding_in_development_is_capped_and_says_so(self):
        self.set_environment("development")
        self.write([finding(severity="high")])
        text = self.render()
        self.assertIn("medium", text)
        self.assertNotIn("| high |", text)

    def test_the_same_finding_in_production_is_not_capped(self):
        self.set_environment("production")
        self.write([finding(severity="high")])
        self.assertIn("| high |", self.render())

    def test_an_undeclared_environment_does_not_cap(self):
        # Fail closed in the direction that does not reduce what the client is told: a missing
        # declaration must never be the reason a finding got smaller.
        self.write([finding(severity="high")])
        self.assertIn("| high |", self.render())

    def test_the_report_states_why_a_severity_was_reduced(self):
        # A cap the client cannot see is a suppression the client cannot audit. The required
        # sentence is the derivation one, and it is a statement about where we looked -- never
        # about whether the client is safe.
        self.set_environment("development")
        self.write([finding(severity="critical")])
        text = self.render()
        self.assertIn("development", text)
        self.assertIn("production system would be rated", text)

    def test_a_production_nexus_survives_the_cap_in_the_report(self):
        self.set_environment("development")
        self.write([finding(severity="high", production_nexus={
            "kind": "live_credential", "evidence_ptr": "evidence/F-001.http"})])
        self.assertIn("| high |", self.render())


class TestEnvironmentDiscrepancyInTheReport(Harness):
    """RG-1 §4.2's action clause, at the place its input can exist.

    Siting, by the §4.8 test -- *name a healthy engagement state at which this fires*: an
    engagement declared production whose asset answered with a test-mode payment key. That state
    exists only after a request was made. At Gate 1, which runs before any request (§9.7), the
    same check would fire on 0% of engagements and read as coverage.
    """

    def discrepant(self, **overrides):
        return finding(environment_at_test="production", env_signals=[
            {"kind": "test_payment_key", "detail": "pk_test_ in response body",
             "evidence_ptr": "evidence/F-001.http"}], **overrides)

    def test_a_contradicted_declaration_keeps_the_finding_out_of_the_body(self):
        self.write([self.discrepant()])
        buckets = report.classify([self.discrepant()], self.root)
        self.assertEqual([r["id"] for r in buckets["environment_discrepancy"]], ["F-001"])
        self.assertEqual(buckets["body"], [])

    def test_the_report_says_why_it_was_held_back(self):
        self.write([self.discrepant()])
        text = self.render()
        self.assertIn("test_payment_key", text)
        self.assertIn("disagree", text)

    def test_a_recorded_operator_decision_lets_it_through(self):
        self.write([self.discrepant(environment_discrepancy_resolution={
            "decision": "signal_wrong", "by": "operator",
            "reason": "the key is a deliberate sandbox key on a production marketing page"})])
        self.assertIn("Anonymous read access", self.render())


class TestTheCapCannotWalkARecordIntoTheBody(Harness):
    """S2, end to end. The report's own preamble promises "unverified technical findings above
    Low do not appear in the body". Capping to `low` made that promise conditional on the
    environment, which is not what it says and not what a client reads it as.
    """

    def preview_scope(self):
        (self.root / "scope.yaml").write_text(
            SCOPE.replace("mode: audit", "mode: audit\nenvironment: ephemeral-preview"),
            encoding="utf-8")

    def test_a_speculated_unverified_critical_does_not_reach_the_body(self):
        self.preview_scope()
        self.write([finding(
            id="F-001", title="Remote code execution in the upload handler",
            status="SPECULATED", severity="critical", verified="none", confidence="confirmed",
            real_world_impact="An attacker can run arbitrary code on the server.")])
        text = self.render()
        self.assertNotIn("## Findings", text)
        self.assertIn("Open questions", text)
        self.assertNotIn("An attacker can run arbitrary code on the server.", text)

    def test_the_body_never_asserts_a_production_rating_for_an_unverified_claim(self):
        # The harm is worse than a mis-rating: the body asserted, in the framework's own voice,
        # that an unreproduced claim "would be rated critical in your production system".
        self.preview_scope()
        self.write([finding(status="SPECULATED", severity="critical", verified="none")])
        self.assertNotIn("would be rated critical", self.render())

    def test_a_verified_capped_finding_still_reaches_the_body_with_its_disclosure(self):
        # The transform itself is correct and must keep working: a properly verified finding
        # capped by its environment is printed, with §6.4's disclosure.
        self.preview_scope()
        text = (self.write([finding(severity="critical", verified="executed",
                                    status="PROVEN", confidence="confirmed")]), self.render())[1]
        self.assertIn("## Findings", text)
        self.assertIn("**Severity:** low", text)
        self.assertIn("would be rated critical", text)


class TestAStaleDerivationCannotRewriteTheClientsSeverity(Harness):
    """S1, end to end. A production engagement, one proven and independently verified `high`
    record whose `severity_derivation` carries a leftover `before_env_cap: "low"` from an earlier
    pass. It rendered to the client as `low`, with no disclosure at all -- because §6.4's
    disclosure is keyed on `env_cap_applied`, and production is uncapped, so nothing was applied.
    """

    def test_the_severity_the_client_reads_is_the_records_own(self):
        (self.root / "scope.yaml").write_text(
            SCOPE.replace("mode: audit", "mode: audit\nenvironment: production"),
            encoding="utf-8")
        self.write([finding(
            id="F-001", title="Anonymous read of every user row",
            status="PROVEN", verified="executed", confidence="confirmed", severity="high",
            real_world_impact="Anyone can read every registered user's email address.",
            severity_derivation={"before_env_cap": "low"})])
        text = self.render()
        self.assertIn("**Severity:** high", text)
        self.assertNotIn("**Severity:** low", text)


class TestCli(Harness):
    def test_writes_the_deliverable(self):
        self.write([finding()])
        self.assertEqual(report.main(["--root", str(self.root), "--tier", "1"]), 0)
        self.assertTrue((self.root / "deliverables" / "report-tier1.md").is_file())

    def test_refuses_outside_an_engagement(self):
        with tempfile.TemporaryDirectory() as empty:
            self.assertEqual(report.main(["--root", empty]), 1)


if __name__ == "__main__":
    unittest.main()
