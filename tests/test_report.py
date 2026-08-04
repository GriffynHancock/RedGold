"""Tests for /rg:report -- the client deliverable (spec §10.6, §16).

The report is where every earlier control either pays off or is revealed as decorative. These
tests are mostly about what must NOT appear.
"""

from __future__ import annotations

import json
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
