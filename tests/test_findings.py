"""Tests for the findings schema and validator (build order steps 5 and 6).

Step 6's acceptance criterion -- "an evidence pointer that does not resolve auto-demotes the
record" -- is `TestAutoDemotion`. Step 5's acceptance against a prior engagement's real files is
in `test_validate_prior_engagement.py`.
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

import findings as findings_mod  # noqa: E402
import validate_findings  # noqa: E402

VALIDATOR = REPO / "scripts" / "validate_findings.py"


def good_record(**overrides) -> dict:
    record = {
        "id": "F-001",
        "asset": "https://app.example.invalid/api/profiles",
        "title": "Anonymous read access to profiles",
        "finding_class": "technical",
        "status": "PROVEN",
        "verified": "replayed",
        "confidence": "confirmed",
        "evidence_ptr": "evidence/F-001-anon-read.http",
        "severity": "high",
        "real_world_impact": "Any visitor can enumerate every user's email address.",
        "tested_at_tier": 1,
    }
    record.update(overrides)
    return record


class EngagementHarness(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        (self.root / "findings").mkdir()
        (self.root / "evidence").mkdir()
        (self.root / "ledger").mkdir()
        (self.root / "scope.yaml").write_text("engagement_id: t\n", encoding="utf-8")
        (self.root / "evidence" / "F-001-anon-read.http").write_text(
            "GET /api/profiles HTTP/1.1\n\nHTTP/1.1 200 OK\n[{\"email\":\"a@b.c\"}]\n",
            encoding="utf-8",
        )

    def write_findings(self, records: list[dict], name: str = "phase1.json") -> Path:
        path = self.root / "findings" / name
        path.write_text(json.dumps(records, indent=2), encoding="utf-8")
        return path

    def codes(self, record: dict) -> set[str]:
        return {v.code for v in findings_mod.validate_record(record, self.root).violations}


class TestEvidenceResolution(EngagementHarness):
    def test_existing_file_resolves(self):
        ok, _ = findings_mod.resolve_evidence("evidence/F-001-anon-read.http", self.root)
        self.assertTrue(ok)

    def test_missing_file_does_not_resolve(self):
        ok, reason = findings_mod.resolve_evidence("evidence/nope.http", self.root)
        self.assertFalse(ok)
        self.assertIn("does not exist", reason)

    def test_empty_pointer_does_not_resolve(self):
        self.assertFalse(findings_mod.resolve_evidence("", self.root)[0])

    def test_markdown_anchor_resolves(self):
        (self.root / "evidence" / "notes.md").write_text(
            "# Probe results\n\n## Anonymous read\n\nbody\n", encoding="utf-8")
        ok, reason = findings_mod.resolve_evidence("evidence/notes.md#anonymous-read", self.root)
        self.assertTrue(ok, reason)

    def test_missing_markdown_anchor_does_not_resolve(self):
        (self.root / "evidence" / "notes.md").write_text("# Probe results\n", encoding="utf-8")
        ok, reason = findings_mod.resolve_evidence("evidence/notes.md#no-such-heading", self.root)
        self.assertFalse(ok)
        self.assertIn("anchor", reason)

    def test_line_anchor_within_range(self):
        self.assertTrue(
            findings_mod.resolve_evidence("evidence/F-001-anon-read.http#L2", self.root)[0]
        )

    def test_line_anchor_beyond_end_does_not_resolve(self):
        ok, reason = findings_mod.resolve_evidence("evidence/F-001-anon-read.http#L900", self.root)
        self.assertFalse(ok)
        self.assertIn("outside", reason)

    def test_pointer_escaping_the_engagement_is_refused(self):
        # Evidence somebody else cannot open later is not evidence.
        ok, reason = findings_mod.resolve_evidence("../../../etc/passwd", self.root)
        self.assertFalse(ok)
        self.assertIn("outside the engagement", reason)


class TestRecordRules(EngagementHarness):
    def test_good_record_is_clean(self):
        self.assertEqual(self.codes(good_record()), set())

    def test_missing_required_field(self):
        record = good_record()
        del record["title"]
        self.assertIn("MISSING_FIELD", self.codes(record))

    def test_unknown_severity_rejected(self):
        self.assertIn("BAD_ENUM", self.codes(good_record(severity="catastrophic")))

    def test_unknown_finding_class_rejected(self):
        self.assertIn("BAD_ENUM", self.codes(good_record(finding_class="vibes")))

    def test_malformed_id_rejected(self):
        self.assertIn("BAD_ID", self.codes(good_record(id="finding-1")))

    def test_proven_technical_without_verification_is_blocked(self):
        self.assertIn("PROVEN_UNVERIFIED", self.codes(good_record(verified="none")))

    def test_proven_technical_missing_verified_field_is_blocked(self):
        record = good_record()
        del record["verified"]
        self.assertIn("PROVEN_UNVERIFIED", self.codes(record))

    def test_above_low_technical_without_verification_is_blocked(self):
        codes = self.codes(good_record(status="SPECULATED", verified="none", severity="medium"))
        self.assertIn("UNVERIFIED_ABOVE_LOW", codes)

    def test_low_technical_without_verification_is_allowed(self):
        codes = self.codes(good_record(status="SPECULATED", verified="none", severity="low"))
        self.assertNotIn("UNVERIFIED_ABOVE_LOW", codes)
        self.assertNotIn("PROVEN_UNVERIFIED", codes)

    def test_na_verification_rejected_for_technical(self):
        self.assertIn("NA_NOT_PERMITTED", self.codes(good_record(verified="n/a")))

    def test_na_verification_allowed_for_posture(self):
        # The carve-out that stops the validator rejecting every legitimate posture finding.
        codes = self.codes(good_record(
            finding_class="posture", verified="n/a", status="PROVEN", severity="high"))
        self.assertNotIn("NA_NOT_PERMITTED", codes)
        self.assertNotIn("UNVERIFIED_ABOVE_LOW", codes)

    def test_na_verification_still_needs_evidence(self):
        codes = self.codes(good_record(
            finding_class="posture", verified="n/a", evidence_ptr="evidence/missing.png"))
        self.assertIn("NA_WITHOUT_EVIDENCE", codes)

    def test_governance_above_low_with_na_is_clean(self):
        codes = self.codes(good_record(
            finding_class="governance", verified="n/a", severity="high", status="PROVEN"))
        self.assertEqual(codes, set())

    def test_speculated_above_low_is_advisory_not_blocking(self):
        result = findings_mod.validate_record(
            good_record(status="SPECULATED", verified="replayed", severity="high"), self.root)
        codes = {v.code for v in result.violations}
        self.assertIn("SPECULATED_ABOVE_LOW", codes)
        self.assertNotIn("SPECULATED_ABOVE_LOW", {v.code for v in result.blocking})

    def test_missing_impact_on_high_finding_is_advisory(self):
        record = good_record()
        del record["real_world_impact"]
        result = findings_mod.validate_record(record, self.root)
        self.assertIn("NO_IMPACT", {v.code for v in result.violations})

    def test_non_object_record_is_reported_not_skipped(self):
        result = findings_mod.validate_record("just a string", self.root)
        self.assertIn("BAD_RECORD", {v.code for v in result.violations})


class TestAutoDemotion(EngagementHarness):
    """Step 6 acceptance: an evidence pointer that does not resolve auto-demotes the record."""

    def test_unresolvable_evidence_rewrites_status_on_disk(self):
        path = self.write_findings([good_record(evidence_ptr="evidence/ghost.http")])
        demoted = validate_findings.demote_records(path, self.root)
        self.assertEqual(demoted, ["F-001"])
        written = json.loads(path.read_text())[0]
        self.assertEqual(written["status"], "SPECULATED")
        self.assertIn("auto-demoted", written["validator_note"])

    def test_resolvable_evidence_is_left_alone(self):
        path = self.write_findings([good_record()])
        self.assertEqual(validate_findings.demote_records(path, self.root), [])
        self.assertEqual(json.loads(path.read_text())[0]["status"], "PROVEN")

    def test_demotion_is_idempotent(self):
        path = self.write_findings([good_record(evidence_ptr="evidence/ghost.http")])
        validate_findings.demote_records(path, self.root)
        self.assertEqual(validate_findings.demote_records(path, self.root), [])


class TestHookBehaviour(EngagementHarness):
    def run_hook(self, agent_id: str = "rg-webtest-1") -> tuple[int, str]:
        payload = json.dumps({"cwd": str(self.root), "agent_id": agent_id,
                              "hook_event_name": "SubagentStop"})
        proc = subprocess.run(
            ["/usr/bin/python3", str(VALIDATOR)], input=payload,
            capture_output=True, text=True, timeout=30,
            env={"PATH": "/usr/bin:/bin", "RG_ENGAGEMENT_ROOT": str(self.root)},
        )
        return proc.returncode, proc.stderr

    def test_clean_findings_allow_stop(self):
        self.write_findings([good_record()])
        code, _ = self.run_hook()
        self.assertEqual(code, 0)

    def test_invalid_findings_block_stop_with_exit_2(self):
        self.write_findings([good_record(verified="none")])
        code, stderr = self.run_hook()
        self.assertEqual(code, 2, "exit 2 is what prevents the subagent stopping")
        self.assertIn("PROVEN_UNVERIFIED", stderr)

    def test_correction_message_names_the_record_and_the_fix(self):
        self.write_findings([good_record(verified="none")])
        _, stderr = self.run_hook()
        self.assertIn("F-001", stderr)
        self.assertIn("rg-verify", stderr)
        # The agent continues from where it is; it must not be told to re-run the phase.
        self.assertIn("continuing from where you are", stderr)

    def test_blocks_twice_then_escalates_to_a_blocker(self):
        self.write_findings([good_record(verified="none")])
        self.assertEqual(self.run_hook()[0], 2)
        self.assertEqual(self.run_hook()[0], 2)
        code, _ = self.run_hook()
        self.assertEqual(code, 0, "a hook that blocks forever is a hung engagement")
        rows = [json.loads(line) for line in
                (self.root / "ledger" / "blockers.jsonl").read_text().splitlines() if line.strip()]
        self.assertEqual(rows[-1]["kind"], "validation")
        self.assertTrue(rows[-1]["violations"])

    def test_attempt_counter_resets_after_a_clean_run(self):
        self.write_findings([good_record(verified="none")])
        self.assertEqual(self.run_hook()[0], 2)
        self.write_findings([good_record()])
        self.assertEqual(self.run_hook()[0], 0)
        self.write_findings([good_record(verified="none")])
        self.assertEqual(self.run_hook()[0], 2, "a fixed-then-rebroken record gets a fresh budget")

    def test_missing_engagement_does_not_hang_the_agent(self):
        proc = subprocess.run(
            ["/usr/bin/python3", str(VALIDATOR)], input=json.dumps({"cwd": "/"}),
            capture_output=True, text=True, timeout=30, env={"PATH": "/usr/bin:/bin"},
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("could not run", proc.stderr)


class TestRecordExtraction(EngagementHarness):
    def test_bare_list(self):
        self.assertEqual(len(findings_mod.extract_records([{"id": "F-001"}])), 1)

    def test_wrapped_under_a_key(self):
        for key in ("findings", "records", "results", "risks", "issues"):
            with self.subTest(key=key):
                self.assertEqual(len(findings_mod.extract_records({key: [{"id": "F-001"}]})), 1)

    def test_unrecognised_shape_yields_nothing_and_is_reported(self):
        # "no findings found" must never be indistinguishable from "everything passed".
        path = self.root / "findings" / "weird.json"
        path.write_text(json.dumps({"summary": "all good"}), encoding="utf-8")
        results, errors = findings_mod.validate_file(path, self.root)
        self.assertEqual(results, [])
        self.assertTrue(errors)


if __name__ == "__main__":
    unittest.main()
