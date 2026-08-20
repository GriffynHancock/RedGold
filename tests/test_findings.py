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


class TestEnvironmentCap(EngagementHarness):
    """RG-1 §6 (D-1, provisional): a graduated cap, applied and recorded, never silently.

    Siting, by the §4.8 test -- *name a healthy engagement state at which this fires*: every one
    in which a finding exists and the engagement is not production. The input is the declared
    environment, which exists before the finding does, so the cap can run at the moment the record
    is written. It is a transform, not a refusal: it never blocks work, so there is no
    disabled-gate risk in siting it early.
    """

    def test_the_cap_table_is_one_constant(self):
        self.assertEqual(set(findings_mod.ENVIRONMENT_SEVERITY_CAP),
                         set(("production", "staging", "development", "ephemeral-preview")))

    def test_production_is_uncapped(self):
        record = findings_mod.apply_environment_cap(good_record(severity="critical"), "production")
        self.assertEqual(record["severity"], "critical")
        self.assertFalse(record["severity_derivation"]["env_cap_applied"])

    def test_the_graduated_cap_lowers_each_environment_to_its_band(self):
        for environment, expected in (("staging", "high"), ("development", "medium"),
                                      ("ephemeral-preview", "low")):
            with self.subTest(environment=environment):
                record = findings_mod.apply_environment_cap(
                    good_record(severity="critical"), environment)
                self.assertEqual(record["severity"], expected)
                self.assertTrue(record["severity_derivation"]["env_cap_applied"])
                self.assertEqual(record["severity_derivation"]["after_env_cap"], expected)
                self.assertEqual(record["severity_derivation"]["before_env_cap"], "critical")

    def test_posture_findings_take_the_posture_column(self):
        # F-048 and F-060 were `high` posture facts about a development box. The posture column
        # is what drops them without needing any of the precondition machinery.
        record = findings_mod.apply_environment_cap(
            good_record(severity="high", finding_class="posture", verified="n/a"), "development")
        self.assertEqual(record["severity"], "low")

    def test_the_cap_is_a_minimum_never_a_floor(self):
        # An engagement against production does not get a severity floor, and a low finding in
        # staging does not get raised to the staging cap.
        record = findings_mod.apply_environment_cap(good_record(severity="low"), "staging")
        self.assertEqual(record["severity"], "low")
        self.assertFalse(record["severity_derivation"]["env_cap_applied"])

    def test_no_step_after_scoring_can_raise_a_severity(self):
        # The global invariant of RG-1 §4, asserted over every environment and every severity.
        for environment in ("production", "staging", "development", "ephemeral-preview"):
            for severity in findings_mod.SEVERITIES:
                with self.subTest(environment=environment, severity=severity):
                    out = findings_mod.apply_environment_cap(
                        good_record(severity=severity), environment)
                    self.assertLessEqual(
                        findings_mod.SEVERITIES.index(out["severity"]),
                        findings_mod.SEVERITIES.index(severity))

    def test_an_unknown_environment_reads_as_production_and_does_not_cap(self):
        # Fail closed names a direction: the one that does not reduce what the client is told.
        for environment in ("", "unknown", "banana", None, "Development"):
            with self.subTest(environment=environment):
                record = findings_mod.apply_environment_cap(
                    good_record(severity="critical"), environment)
                self.assertEqual(record["severity"], "critical")
                self.assertEqual(record["environment_at_test"], "production")

    def test_an_unrecognised_severity_is_never_capped_into_looking_low(self):
        # The 2026-08-04 incident's shape. "Critical!!" must not become "medium" in development:
        # an unknown severity is not evidence that a finding is small.
        record = findings_mod.apply_environment_cap(
            good_record(severity="Critical!!"), "development")
        self.assertEqual(record["severity"], "Critical!!")
        self.assertFalse(record["severity_derivation"]["env_cap_applied"])

    def test_the_cap_is_idempotent(self):
        once = findings_mod.apply_environment_cap(good_record(severity="critical"), "development")
        twice = findings_mod.apply_environment_cap(dict(once), "development")
        self.assertEqual(twice["severity"], "medium")
        self.assertEqual(twice["severity_derivation"]["before_env_cap"], "critical")

    def test_environment_at_test_is_stamped_and_never_recomputed(self):
        # The environment at the moment of the test is a fact about the test. A record written
        # against a development asset does not become a production finding because the engagement
        # later re-declared itself.
        #
        # That rationale is sound in the *raising* direction and this test now exercises it there.
        # It previously asserted the lowering direction -- a record declaring `development` on a
        # `production` engagement taking a critical to a medium, uncontested -- which is not a
        # fact about the test at all, it is a contradiction between two declarations with no
        # cross-check anywhere. The requirement it should have encoded is that a record may raise
        # its own environment freely and may lower it only through the same `decision`/`reason`
        # ceremony §4.2 demands in the other direction. See
        # `TestARecordMayNotTalkDownItsOwnEnvironment` (adversarial review, S5).
        record = findings_mod.apply_environment_cap(
            good_record(severity="critical", environment_at_test="staging"), "development")
        self.assertEqual(record["environment_at_test"], "staging")
        self.assertEqual(record["severity"], "high")


class TestProductionNexus(EngagementHarness):
    """RG-1 §6.3/§6.4: the closed bypass vocabulary, and `code_defect` default-on."""

    def nexus(self, kind: str) -> dict:
        return {"kind": kind, "evidence_ptr": "evidence/F-001-anon-read.http"}

    def test_a_recognised_nexus_bypasses_the_cap(self):
        # The autopsy's worst case: a live, spend-capable API key in a development config. Capping
        # a live production credential at `low` because the box is a dev box is a worse error than
        # any of the findings the cap suppresses.
        record = findings_mod.apply_environment_cap(
            good_record(severity="critical", production_nexus=self.nexus("live_credential")),
            "development")
        self.assertEqual(record["severity"], "critical")
        self.assertFalse(record["severity_derivation"]["env_cap_applied"])
        self.assertEqual(record["severity_derivation"]["production_nexus_kind"], "live_credential")

    def test_the_bypass_vocabulary_is_closed(self):
        self.assertEqual(
            findings_mod.PRODUCTION_NEXUS_KINDS,
            ("live_credential", "production_data", "shared_infrastructure", "code_defect",
             "same_artifact"))

    def test_an_unrecognised_kind_bypasses_the_cap_and_blocks(self):
        # The disclosing direction and the correctness direction differ here, and we take both:
        # the severity is not quietly reduced by a field nobody can read, and the record cannot
        # reach a client until the field is fixed.
        record = good_record(severity="critical", production_nexus=self.nexus("vibes"))
        capped = findings_mod.apply_environment_cap(dict(record), "development")
        self.assertEqual(capped["severity"], "critical")
        self.assertIn("PRODUCTION_NEXUS_UNRECOGNISED", self.codes(record))

    def test_a_nexus_without_resolving_evidence_blocks(self):
        record = good_record(severity="critical",
                             production_nexus={"kind": "live_credential",
                                               "evidence_ptr": "evidence/nope.http"})
        self.assertIn("PRODUCTION_NEXUS_UNRESOLVED", self.codes(record))

    def test_a_clean_nexus_raises_nothing(self):
        record = good_record(severity="critical", production_nexus=self.nexus("code_defect"))
        self.assertNotIn("PRODUCTION_NEXUS_UNRECOGNISED", self.codes(record))
        self.assertNotIn("PRODUCTION_NEXUS_UNRESOLVED", self.codes(record))

    # --- code_defect default-on (§6.2 reason 3) ---------------------------------------------

    def test_a_codeaudit_finding_carries_code_defect_by_default(self):
        # The environment of a source-code finding is the code, not the box it was read on. Every
        # whitebox finding the prior engagement should have produced -- a missing unique
        # constraint, an absent fulfilment fallback, a dead sweeper, all affecting paying
        # customers in production -- would otherwise be capped by the laptop it was read on.
        record = findings_mod.apply_environment_cap(
            good_record(severity="critical", discovered_by="rg-codeaudit"), "development")
        self.assertEqual(record["production_nexus"]["kind"], "code_defect")
        self.assertTrue(record["production_nexus"]["default_applied"])
        self.assertEqual(record["severity"], "critical")

    def test_clearing_code_defect_must_be_explicit(self):
        # A test fixture, a seed script, a compose.dev.yaml -- genuinely dev-only code -- is
        # cleared by writing `production_nexus: null`, not by leaving the field out. The default
        # runs in the direction that discloses.
        record = findings_mod.apply_environment_cap(
            good_record(severity="critical", discovered_by="rg-codeaudit",
                        production_nexus=None), "development")
        self.assertIsNone(record["production_nexus"])
        self.assertEqual(record["severity"], "medium")

    def test_the_default_does_not_apply_to_other_producers(self):
        record = findings_mod.apply_environment_cap(
            good_record(severity="critical", discovered_by="baseline_scan"), "development")
        self.assertIsNone(record.get("production_nexus"))
        self.assertEqual(record["severity"], "medium")

    # --- the derivation is the audit trail --------------------------------------------------

    def test_a_hand_edited_severity_is_caught(self):
        record = findings_mod.apply_environment_cap(good_record(severity="critical"),
                                                    "development")
        self.assertNotIn("DERIVATION_MISMATCH", self.codes(record))
        record["severity"] = "critical"
        self.assertIn("DERIVATION_MISMATCH", self.codes(record))


class TestEnvironmentDiscrepancy(EngagementHarness):
    """RG-1 §4.2, re-sited (§4.8).

    The spec's prose put this at Gate 1. It cannot live there. Three of the four signals §2.4
    permits to block -- a `pk_test_`/`sk_test_` prefix in a **response body**, a framework debug
    page, a dev-tool service fingerprint -- require active contact with the asset, and under §9.7
    no contact happens until after Gate 1 approves the plan. Sited at Gate 1 the check fires on
    **0% of anything**, which §2.3 calls worse than a wrong rule because it reads as coverage.

    So the two concerns are split. The *declaration* is a scope fact and stays at Gate 1. The
    *discrepancy between declared and observed* runs where the observation lands.

    Siting, by the §4.8 test -- *name a healthy engagement state at which this fires*: an
    engagement declared `production` whose asset returns a test-mode payment key or answers as a
    mail catcher. That state exists only after a request has been made, which is exactly the
    point: the check has an input here and has none at Gate 1.
    """

    def signal(self, kind: str, detail: str = "pk_test_ in response body") -> dict:
        return {"kind": kind, "detail": detail,
                "evidence_ptr": "evidence/F-001-anon-read.http"}

    def test_a_blocking_signal_against_a_production_declaration_is_a_discrepancy(self):
        for kind in findings_mod.ENVIRONMENT_SIGNALS_BLOCKING:
            with self.subTest(kind=kind):
                record = good_record(environment_at_test="production",
                                     env_signals=[self.signal(kind)])
                self.assertIn("ENVIRONMENT_DISCREPANCY", self.codes(record))

    def test_the_same_signal_against_a_development_declaration_is_consistent(self):
        record = good_record(environment_at_test="development",
                             env_signals=[self.signal("dev_tool_fingerprint")])
        self.assertNotIn("ENVIRONMENT_DISCREPANCY", self.codes(record))

    def test_contributes_only_signals_never_produce_a_verdict_alone(self):
        # A naming convention is not a platform assertion: react-tweet.vercel.app and
        # swr.vercel.app are both production. A gate that fires on healthy input gets disabled.
        for kind in findings_mod.ENVIRONMENT_SIGNALS_CONTRIBUTES_ONLY:
            with self.subTest(kind=kind):
                record = good_record(environment_at_test="production",
                                     env_signals=[self.signal(kind)])
                self.assertNotIn("ENVIRONMENT_DISCREPANCY", self.codes(record))

    def test_an_unrecognised_signal_kind_is_not_a_blocking_verdict(self):
        record = good_record(environment_at_test="production",
                             env_signals=[self.signal("vibes")])
        self.assertNotIn("ENVIRONMENT_DISCREPANCY", self.codes(record))
        self.assertIn("ENVIRONMENT_SIGNAL_UNRECOGNISED", self.codes(record))

    def test_a_recorded_operator_decision_naming_which_side_was_wrong_clears_it(self):
        for decision in ("declaration_wrong", "signal_wrong"):
            with self.subTest(decision=decision):
                record = good_record(
                    environment_at_test="production",
                    env_signals=[self.signal("test_payment_key")],
                    environment_discrepancy_resolution={
                        "decision": decision, "by": "operator",
                        "reason": "client confirmed the sandbox key is deliberate on this host"})
                self.assertNotIn("ENVIRONMENT_DISCREPANCY", self.codes(record))

    def test_an_unrecognised_resolution_does_not_clear_it(self):
        # Fail closed: a resolution nobody can read is not a resolution, and a free-text decision
        # would absorb any sentence an agent wanted to write.
        record = good_record(
            environment_at_test="production",
            env_signals=[self.signal("test_payment_key")],
            environment_discrepancy_resolution={"decision": "fine", "reason": "looks ok"})
        self.assertIn("ENVIRONMENT_DISCREPANCY", self.codes(record))

    def test_a_resolution_without_a_reason_does_not_clear_it(self):
        record = good_record(
            environment_at_test="production",
            env_signals=[self.signal("test_payment_key")],
            environment_discrepancy_resolution={"decision": "signal_wrong", "reason": ""})
        self.assertIn("ENVIRONMENT_DISCREPANCY", self.codes(record))

    def test_the_classifier_never_sets_the_environment(self):
        # It may contradict a declaration; it may never conclude one. Setting requires a positive
        # conclusion from signals that are silent when absent, which is unsound.
        record = good_record(environment_at_test="production",
                             env_signals=[self.signal("dev_tool_fingerprint")])
        findings_mod.validate_record(record, self.root)
        self.assertEqual(record["environment_at_test"], "production")

    def test_the_discrepancy_blocks(self):
        record = good_record(environment_at_test="production",
                             env_signals=[self.signal("test_payment_key")])
        blocking = {v.code for v in findings_mod.validate_record(record, self.root).blocking}
        self.assertIn("ENVIRONMENT_DISCREPANCY", blocking)


# ------------------------------------------------------------------------------------------
# Adversarial review 2026-08-20 (docs/research/rg1-code-review-2026-08-20.md), S1/S2/S5.
#
# All three are severity-lowering defects in the one transform whose only job is to lower
# severities. The shared shape: a *security decision was reading from a producer-supplied
# field*. `severity_derivation` is an audit trail the scorer writes; before these tests it was
# also an input the scorer trusted, so any writer of a findings record could set the severity
# a client is shown by writing a different key.
# ------------------------------------------------------------------------------------------


class TestTheDerivationIsAnOutput(EngagementHarness):
    """S1. `severity_derivation` may not decide what `severity` becomes."""

    def test_a_stale_before_env_cap_cannot_lower_a_production_severity(self):
        # The review's reproducing input. Production is uncapped, so `env_cap_applied` is False
        # and §6.4's disclosure never prints -- yet the severity changed anyway. A proven,
        # independently verified `high` rendered to the client as `info`, silently.
        record = findings_mod.apply_environment_cap(
            {"id": "F-001", "finding_class": "technical", "severity": "critical",
             "severity_derivation": {"before_env_cap": "info"}},
            "production")
        self.assertEqual(record["severity"], "critical")
        self.assertEqual(record["severity_derivation"]["after_env_cap"], "critical")

    def test_a_stale_before_env_cap_cannot_lower_a_capped_severity_either(self):
        # Same defect on a capped engagement: the cap must floor at what the record actually
        # says, never at what a leftover derivation says.
        record = findings_mod.apply_environment_cap(
            good_record(severity="critical",
                        severity_derivation={"before_env_cap": "info"}),
            "development")
        self.assertEqual(record["severity"], "medium")

    def test_the_workflow_that_raises_a_severity_after_verification_survives_the_cap(self):
        # §10.3's mandated workflow: baseline_scan writes a record at its checklist severity and
        # stamps a derivation; rg-verify re-executes it and the operator raises the severity. The
        # stale derivation must not revert that.
        scanned = findings_mod.apply_environment_cap(good_record(severity="low"), "production")
        scanned["severity"] = "high"
        scanned["verified"] = "executed"
        re_scored = findings_mod.apply_environment_cap(scanned, "production")
        self.assertEqual(re_scored["severity"], "high")
        self.assertEqual(re_scored["severity_derivation"]["before_env_cap"], "high")

    def test_a_severity_lowered_below_its_own_derivation_is_caught_after_the_cap(self):
        # The direction that is not a workflow. §6 names DERIVATION_MISMATCH as "how a
        # hand-edited severity gets caught"; before this test it could not fire anywhere in the
        # report pipeline, because the cap rewrote `severity` to equal `after_env_cap`
        # immediately before validation.
        record = findings_mod.apply_environment_cap(good_record(severity="critical"),
                                                    "development")
        self.assertEqual(record["severity"], "medium")
        record["severity"] = "low"
        re_scored = findings_mod.apply_environment_cap(record, "development")
        self.assertIn("DERIVATION_MISMATCH", self.codes(re_scored))

    def test_the_cap_still_cannot_ratchet_a_severity_down_twice(self):
        once = findings_mod.apply_environment_cap(good_record(severity="critical"), "development")
        twice = findings_mod.apply_environment_cap(dict(once), "development")
        thrice = findings_mod.apply_environment_cap(dict(twice), "development")
        self.assertEqual(thrice["severity"], "medium")
        self.assertEqual(thrice["severity_derivation"]["before_env_cap"], "critical")
        self.assertTrue(thrice["severity_derivation"]["env_cap_applied"])


class TestTheCapCannotSilenceAVerificationGate(EngagementHarness):
    """S2. Capping a severity must not make `status` and `verified` gates unreachable.

    The requirement these encode: `UNVERIFIED_ABOVE_LOW` and `SPECULATED_ABOVE_LOW` are not
    statements about a presentation severity, they are statements about the *claim being made*.
    A severity transform must never be able to switch them off.
    """

    def test_capping_to_low_does_not_silence_the_verification_gate(self):
        record = findings_mod.apply_environment_cap(
            good_record(severity="critical", verified="none", status="SPECULATED"),
            "ephemeral-preview")
        self.assertEqual(record["severity"], "low")
        self.assertIn("UNVERIFIED_ABOVE_LOW", self.codes(record))

    def test_capping_to_low_does_not_silence_the_speculated_gate(self):
        record = findings_mod.apply_environment_cap(
            good_record(severity="critical", verified="none", status="SPECULATED"),
            "ephemeral-preview")
        self.assertIn("SPECULATED_ABOVE_LOW", self.codes(record))

    def test_a_genuinely_low_unverified_finding_still_passes(self):
        # The gate must not start firing on healthy input: a record that was never above Low is
        # not made unverifiable by this change.
        record = findings_mod.apply_environment_cap(
            good_record(severity="low", verified="none", status="SPECULATED"), "development")
        self.assertNotIn("UNVERIFIED_ABOVE_LOW", self.codes(record))
        self.assertNotIn("SPECULATED_ABOVE_LOW", self.codes(record))


class TestARecordMayNotTalkDownItsOwnEnvironment(EngagementHarness):
    """S5. A declaration-vs-declaration contradiction is not a fact, it is a contradiction.

    `environment_at_test` raising the environment above the scope is sound -- the environment at
    the moment of the test is a fact about the test, and raising discloses. Lowering it is a
    claim that the signed scope is wrong about its own engagement, and one agent-written key was
    enough to take a critical to a low on a production engagement, uncontested.
    """

    def test_a_record_cannot_lower_the_engagement_environment_uncontested(self):
        record = findings_mod.apply_environment_cap(
            good_record(severity="critical", environment_at_test="ephemeral-preview"),
            "production")
        self.assertEqual(record["severity"], "critical")
        self.assertEqual(record["environment_at_test"], "production")

    def test_the_contradiction_is_recorded(self):
        record = findings_mod.apply_environment_cap(
            good_record(severity="critical", environment_at_test="development"), "production")
        self.assertIn("ENVIRONMENT_DECLARATION_CONFLICT", self.codes(record))

    def test_an_operator_decision_lets_the_record_declaration_stand(self):
        # The same ceremony `environment_discrepancy_resolution` already demands in the other
        # direction: a closed-vocabulary decision and a non-empty reason.
        record = findings_mod.apply_environment_cap(
            good_record(severity="critical", environment_at_test="development",
                        environment_discrepancy_resolution={
                            "decision": "declaration_wrong", "by": "operator",
                            "reason": "this asset is the developer's laptop, not the prod stack"}),
            "production")
        self.assertEqual(record["environment_at_test"], "development")
        self.assertEqual(record["severity"], "medium")
        self.assertNotIn("ENVIRONMENT_DECLARATION_CONFLICT", self.codes(record))

    def test_a_record_may_still_raise_its_own_environment(self):
        # The disclosing direction needs no ceremony.
        record = findings_mod.apply_environment_cap(
            good_record(severity="critical", environment_at_test="production"), "development")
        self.assertEqual(record["environment_at_test"], "production")
        self.assertEqual(record["severity"], "critical")
        self.assertNotIn("ENVIRONMENT_DECLARATION_CONFLICT", self.codes(record))

    def test_a_matching_declaration_is_not_a_conflict(self):
        record = findings_mod.apply_environment_cap(
            good_record(severity="critical", environment_at_test="development"), "development")
        self.assertEqual(record["severity"], "medium")
        self.assertNotIn("ENVIRONMENT_DECLARATION_CONFLICT", self.codes(record))


class TestCodeDefectDefaultHasAProducer(EngagementHarness):
    """S6. `code_defect` default-on was inert: nothing wrote `discovered_by: "rg-codeaudit"`.

    A constant that only fires on input no producer generates is not a control, it is a test
    fixture. Every test of the default supplied `discovered_by` itself, so the suite proved the
    constant worked and could not see that it never ran.
    """

    def test_the_codeaudit_agent_card_instructs_the_producing_field(self):
        card = (REPO / "agents" / "rg-codeaudit.md").read_text(encoding="utf-8")
        for producer in findings_mod.CODE_DEFECT_PRODUCERS:
            self.assertIn(f'"discovered_by": "{producer}"', card)

    def test_clearing_the_default_costs_a_reason(self):
        # S6, second half. The clearing mechanism was asymmetric with every other bypass in RG-1:
        # `production_nexus: null` suppressed a whitebox finding with no reason, no `by`, and no
        # violation, while `environment_discrepancy_resolution` demands a closed-vocabulary
        # decision *and* a non-empty reason for the same kind of override. Four characters must
        # not be enough to take a critical to a medium.
        record = findings_mod.apply_environment_cap(
            good_record(severity="critical", discovered_by="rg-codeaudit",
                        production_nexus=None), "development")
        self.assertIn("CODE_DEFECT_CLEARED_WITHOUT_REASON", self.codes(record))

        record["code_defect_cleared"] = {
            "reason": "this is compose.dev.yaml; it is not deployed", "by": "operator"}
        self.assertNotIn("CODE_DEFECT_CLEARED_WITHOUT_REASON", self.codes(record))

    def test_every_code_defect_producer_is_a_real_agent(self):
        for producer in findings_mod.CODE_DEFECT_PRODUCERS:
            self.assertTrue((REPO / "agents" / f"{producer}.md").is_file(),
                            f"{producer} is in CODE_DEFECT_PRODUCERS but has no agent card")


if __name__ == "__main__":
    unittest.main()
