"""Build order step 9 acceptance test.

Acceptance criterion (§17.2): "`status.md` regenerates identically from ledger + findings."

"Identically" is the whole contract. If regeneration is not deterministic the file cannot be
diffed, and a status file that cannot be diffed is one nobody can tell has drifted.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import regen_status  # noqa: E402
import report  # noqa: E402

SCOPE = """engagement_id: regen-test
client: {name: C, contact: c@example.invalid}
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
out_of_scope:
  - {asset_type: URL, pattern: "https://blog.acme.example", note: "third-party"}
constraints: {no_destructive: true}
"""


class Harness(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        (self.root / "scope.yaml").write_text(SCOPE, encoding="utf-8")
        for sub in ("assets", "ledger", "findings", "evidence"):
            (self.root / sub).mkdir()

    def jsonl(self, rel: str, *rows: dict):
        with (self.root / rel).open("a", encoding="utf-8") as handle:
            for row in rows:
                handle.write(json.dumps(row) + "\n")

    def write_findings(self, records: list[dict]):
        (self.root / "findings" / "phase1.json").write_text(
            json.dumps(records, indent=2), encoding="utf-8")

    def generate(self) -> str:
        return regen_status.render(self.root)


class TestDeterminism(Harness):
    def test_two_runs_are_byte_identical(self):
        self.jsonl("ledger/activity.jsonl",
                   {"ts": "2026-08-05T10:00:00Z", "event_type": "asset.promote"})
        self.assertEqual(self.generate(), self.generate())

    def test_output_contains_no_wall_clock_timestamp(self):
        """The 'as of' marker is the latest ledger event, never the moment the script ran.

        Otherwise every regeneration produces a diff and the guarantee is worthless.
        """
        self.jsonl("ledger/activity.jsonl",
                   {"ts": "2026-08-05T10:00:00Z", "event_type": "asset.promote"})
        self.assertIn("2026-08-05T10:00:00Z", self.generate())
        import datetime as dt
        today = dt.date.today().isoformat()
        self.assertNotIn(today, self.generate(), "output must not embed the current date")

    def test_ledger_row_order_does_not_change_the_output(self):
        rows = [{"ts": "2026-08-05T10:00:00Z", "event_type": "asset.promote"},
                {"ts": "2026-08-05T09:00:00Z", "event_type": "asset.candidate"}]
        self.jsonl("ledger/activity.jsonl", *rows)
        first = self.generate()
        (self.root / "ledger" / "activity.jsonl").unlink()
        self.jsonl("ledger/activity.jsonl", *reversed(rows))
        self.assertEqual(first, self.generate())

    def test_asset_order_does_not_change_the_output(self):
        a = {"asset_id": "A-001", "identifier": "a.acme.example", "status": "CONFIRMED"}
        b = {"asset_id": "A-002", "identifier": "b.acme.example", "status": "CONFIRMED"}
        self.jsonl("assets/register.jsonl", a, b)
        first = self.generate()
        (self.root / "assets" / "register.jsonl").unlink()
        self.jsonl("assets/register.jsonl", b, a)
        self.assertEqual(first, self.generate())


class TestItReflectsSourceOfTruth(Harness):
    def test_confirmed_and_candidate_assets_are_counted_separately(self):
        self.jsonl("assets/register.jsonl",
                   {"asset_id": "A-001", "identifier": "a.acme.example", "status": "CONFIRMED"})
        self.jsonl("assets/candidates.jsonl",
                   {"asset_id": "C-001", "identifier": "c.acme.example", "status": "CANDIDATE"})
        text = self.generate()
        self.assertIn("CONFIRMED: 1", text)
        self.assertIn("CANDIDATE (untestable above tier 1): 1", text)

    def test_out_of_scope_entries_are_shown(self):
        self.assertIn("OUT of scope", self.generate())

    def test_unverified_findings_are_marked(self):
        self.write_findings([{"id": "F-001", "title": "Anon read", "finding_class": "technical",
                              "status": "PROVEN", "severity": "high", "verified": "none"}])
        self.assertIn("**UNVERIFIED**", self.generate())

    def test_verified_findings_are_not_marked(self):
        self.write_findings([{"id": "F-001", "title": "Anon read", "finding_class": "technical",
                              "status": "PROVEN", "severity": "high", "verified": "replayed"}])
        self.assertNotIn("**UNVERIFIED**", self.generate())

    def test_findings_sorted_by_severity(self):
        self.write_findings([
            {"id": "F-001", "title": "Low thing", "finding_class": "technical",
             "status": "PROVEN", "severity": "low", "verified": "replayed"},
            {"id": "F-002", "title": "Critical thing", "finding_class": "technical",
             "status": "PROVEN", "severity": "critical", "verified": "replayed"},
        ])
        text = self.generate()
        self.assertLess(text.index("Critical thing"), text.index("Low thing"))

    def test_negative_results_are_counted_but_not_listed_as_findings(self):
        self.write_findings([
            {"id": "F-001", "title": "Env file", "finding_class": "technical",
             "status": "SPECULATED", "severity": "info", "verified": "none", "result": "absent"},
            {"id": "F-002", "title": "Open bucket", "finding_class": "technical",
             "status": "PROVEN", "severity": "high", "verified": "executed", "result": "present"},
        ])
        text = self.generate()
        self.assertIn("1 checks ran and found nothing", text)
        self.assertIn("Open bucket", text)

    def test_cleanup_debt_is_surfaced_loudly(self):
        self.jsonl("ledger/cleanup.jsonl",
                   {"ts": "2026-08-05T10:00:00Z", "state": "pending"},
                   {"ts": "2026-08-05T10:01:00Z", "state": "orphaned"})
        text = self.generate()
        self.assertIn("does not close with 2 item(s) outstanding", text)

    def test_open_blockers_are_listed(self):
        self.jsonl("ledger/blockers.jsonl",
                   {"ts": "2026-08-05T10:00:00Z", "kind": "nesting",
                    "reason": "worker tried to spawn a subagent"})
        self.assertIn("worker tried to spawn a subagent", self.generate())

    def test_resolved_blockers_are_not_listed(self):
        self.jsonl("ledger/blockers.jsonl",
                   {"ts": "2026-08-05T10:00:00Z", "kind": "nesting", "reason": "old thing",
                    "resolved": True})
        self.assertIn("None.", self.generate())


class TestCheckMode(Harness):
    def test_check_fails_on_a_hand_edited_file(self):
        # The point of deriving the file: hand edits are detectable, not merged.
        regen_status.main(["--root", str(self.root)])
        (self.root / "status.md").write_text("I edited this by hand\n", encoding="utf-8")
        self.assertEqual(regen_status.main(["--root", str(self.root), "--check"]), 1)

    def test_check_passes_immediately_after_regeneration(self):
        regen_status.main(["--root", str(self.root)])
        self.assertEqual(regen_status.main(["--root", str(self.root), "--check"]), 0)

    def test_regeneration_is_idempotent_on_disk(self):
        regen_status.main(["--root", str(self.root)])
        first = (self.root / "status.md").read_text()
        regen_status.main(["--root", str(self.root)])
        self.assertEqual(first, (self.root / "status.md").read_text())

    def test_refuses_outside_an_engagement(self):
        with tempfile.TemporaryDirectory() as empty:
            self.assertEqual(regen_status.main(["--root", empty]), 1)


class TestTheCoverageGapMatchesTheClientReport(Harness):
    """S8. `regen_status.py` and `report.py` counted the coverage gap by opposite rules.

    `report.py` allow-lists the *inapplicable* bucket and treats everything else as a gap -- the
    disclosing direction. `regen_status.py` allow-listed the *gap* bucket, so anything it did not
    recognise vanished. One typo or one future third `not_applicable_reason` and status.md -- the
    file CLAUDE.md calls authoritative and the operator reads at every session start -- reported
    zero unassessed services while the client report reported twelve.
    """

    def gap_record(self, **overrides) -> dict:
        record = {"id": "F-001", "title": "12 checks never sent",
                  "asset": "http://app.example.invalid:8025", "finding_class": "technical",
                  "status": "SPECULATED", "severity": "info", "result": "not_applicable",
                  "not_applicable_reason": "no_http_response", "checks_skipped": 12}
        record.update(overrides)
        return record

    def untested_in_status(self) -> int:
        text = self.generate()
        for line in text.splitlines():
            if "checks did NOT run" in line:
                return int(line.split()[0])
        return 0

    def untested_in_report(self) -> int:
        # Read the number off the client deliverable itself rather than re-deriving it. The whole
        # defect was two derivations of one number, so a test that carries a third proves nothing.
        (self.root / "deliverables").mkdir(exist_ok=True)
        for line in report.render(self.root, 1).splitlines():
            if "check(s) not performed" in line:
                return int(line.split("--")[1].split()[0])
        return 0

    def test_a_recognised_reason_agrees(self):
        self.write_findings([self.gap_record()])
        self.assertEqual(self.untested_in_status(), 12)
        self.assertEqual(self.untested_in_report(), 12)

    def test_an_unrecognised_reason_does_not_vanish_from_status(self):
        self.write_findings([self.gap_record(not_applicable_reason="connection_reset")])
        self.assertEqual(self.untested_in_report(), 12)
        self.assertEqual(self.untested_in_status(), 12)

    def test_a_zero_checks_skipped_still_counts_as_one_gap(self):
        self.write_findings([self.gap_record(checks_skipped=0)])
        self.assertEqual(self.untested_in_report(), 1)
        self.assertEqual(self.untested_in_status(), 1)

    def test_a_boolean_checks_skipped_is_not_a_count(self):
        # `True` is an `int` in Python. A JSON bool in this field is malformed input, not one
        # check, and both readers must agree on that.
        self.write_findings([self.gap_record(checks_skipped=True)])
        self.assertEqual(self.untested_in_report(), 1)
        self.assertEqual(self.untested_in_status(), 1)

    def test_a_structurally_inapplicable_check_is_not_a_gap_in_either(self):
        self.write_findings([self.gap_record(not_applicable_reason="scheme_inapplicable")])
        self.assertEqual(self.untested_in_report(), 0)
        self.assertEqual(self.untested_in_status(), 0)


if __name__ == "__main__":
    unittest.main()
