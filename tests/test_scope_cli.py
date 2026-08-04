"""Tests for /rg:scope -- asset promotion and boundary amendment (spec §5.2, §5.3, §5.4)."""

from __future__ import annotations

import io
import json
import sys
import tempfile
import unittest
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import scope_cli  # noqa: E402

SCOPE = """engagement_id: promo-test
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
        (self.root / "assets").mkdir()
        (self.root / "ledger").mkdir()

    def run_cli(self, *argv) -> tuple[int, str, str]:
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = scope_cli.main(["--root", str(self.root), *argv])
        return code, out.getvalue(), err.getvalue()

    def register(self) -> list[dict]:
        return scope_cli.read_jsonl(self.root / "assets" / "register.jsonl")

    def candidates(self) -> list[dict]:
        return scope_cli.read_jsonl(self.root / "assets" / "candidates.jsonl")


class TestPromotionRules(Harness):
    def test_single_signal_is_refused(self):
        self.run_cli("add-candidate", "api.acme.example", "--signal", "TLS_SAN:api.acme.example@crt.sh")
        code, _, err = self.run_cli("promote", "api.acme.example", "--confirm")
        self.assertEqual(code, 1)
        self.assertIn("two independent", err)

    def test_two_independent_signals_promote(self):
        self.run_cli("add-candidate", "api.acme.example",
                     "--signal", "TLS_SAN:api.acme.example@crt.sh",
                     "--signal", "CONTENT_FP:bundle-hash@httpx")
        code, out, _ = self.run_cli("promote", "api.acme.example", "--confirm")
        self.assertEqual(code, 0)
        self.assertIn("CONFIRMED", out)
        self.assertEqual(len(self.register()), 1)
        self.assertEqual(self.candidates(), [])

    def test_same_signal_class_twice_is_still_one_class(self):
        # Two TLS_SAN observations are not two independent classes.
        self.run_cli("add-candidate", "api.acme.example",
                     "--signal", "TLS_SAN:api.acme.example@crt.sh",
                     "--signal", "TLS_SAN:api.acme.example@censys")
        code, _, err = self.run_cli("promote", "api.acme.example", "--confirm")
        self.assertEqual(code, 1)
        self.assertIn("two independent", err)

    def test_ip_valued_signal_is_refused_outright(self):
        # An IP cannot be recorded as evidence of ownership at all -- shared edge IPs cover
        # every tenant at that address, and this client base lives on exactly that.
        code, _, err = self.run_cli("add-candidate", "api.acme.example",
                                    "--signal", "CONTENT_FP:104.21.5.7@httpx")
        self.assertEqual(code, 1)
        self.assertIn("never attributes", err)
        self.assertEqual(self.candidates(), [])

    def test_there_is_no_ip_signal_class_at_all(self):
        # The rule is enforced by the vocabulary, not by a check someone must remember.
        self.assertNotIn("IP", scope_cli.SIGNAL_CLASSES)
        self.assertNotIn("IP_ADDRESS", scope_cli.SIGNAL_CLASSES)

    def test_asn_signal_still_counts_toward_two_classes(self):
        # ASN is legitimate corroboration when paired with an ownership signal.
        self.run_cli("add-candidate", "api.acme.example",
                     "--signal", "ASN_OWNER:AS13335@rdap", "--signal", "TLS_SAN:x@crt.sh")
        code, _, _ = self.run_cli("promote", "api.acme.example", "--confirm")
        self.assertEqual(code, 0)

    def test_client_confirmation_alone_is_sufficient(self):
        self.run_cli("add-candidate", "api.acme.example")
        code, out, _ = self.run_cli("promote", "api.acme.example", "--confirm",
                                    "--client-confirmed", "email 2026-08-05")
        self.assertEqual(code, 0)
        self.assertIn("CLIENT_CONFIRMED", out)

    def test_operator_sign_off_is_required(self):
        self.run_cli("add-candidate", "api.acme.example",
                     "--signal", "TLS_SAN:x@crt.sh", "--signal", "CONTENT_FP:y@httpx")
        code, _, err = self.run_cli("promote", "api.acme.example")
        self.assertEqual(code, 1)
        self.assertIn("--confirm", err)
        self.assertEqual(self.register(), [])

    def test_unknown_signal_class_is_refused(self):
        code, _, err = self.run_cli("add-candidate", "api.acme.example", "--signal", "VIBES:x@me")
        self.assertEqual(code, 1)
        self.assertIn("unrecognised signal class", err)


class TestPromotionCannotWidenScope(Harness):
    def test_asset_outside_boundary_cannot_be_promoted(self):
        self.run_cli("add-candidate", "api.other.example",
                     "--signal", "TLS_SAN:x@crt.sh", "--signal", "CONTENT_FP:y@httpx")
        code, _, err = self.run_cli("promote", "api.other.example", "--confirm")
        self.assertEqual(code, 1)
        self.assertIn("outside the authorization boundary", err)
        self.assertEqual(self.register(), [])

    def test_explicitly_excluded_asset_cannot_be_promoted(self):
        self.run_cli("add-candidate", "blog.acme.example",
                     "--signal", "TLS_SAN:x@crt.sh", "--signal", "CONTENT_FP:y@httpx")
        code, _, err = self.run_cli("promote", "blog.acme.example", "--confirm")
        self.assertEqual(code, 1)
        self.assertEqual(self.register(), [])

    def test_promoting_an_unknown_asset_is_refused(self):
        code, _, err = self.run_cli("promote", "never.seen.example", "--confirm")
        self.assertEqual(code, 1)
        self.assertIn("not in the candidate queue", err)

    def test_candidate_outside_boundary_is_warned_about_on_add(self):
        _, out, _ = self.run_cli("add-candidate", "api.other.example")
        self.assertIn("matches no in_scope entry", out)


class TestLedgering(Harness):
    def test_promotion_is_recorded_in_the_activity_ledger(self):
        self.run_cli("add-candidate", "api.acme.example",
                     "--signal", "TLS_SAN:x@crt.sh", "--signal", "CONTENT_FP:y@httpx")
        self.run_cli("promote", "api.acme.example", "--confirm")
        rows = [json.loads(l) for l in
                (self.root / "ledger" / "activity.jsonl").read_text().splitlines() if l.strip()]
        events = [r["event_type"] for r in rows]
        self.assertIn("asset.candidate", events)
        self.assertIn("asset.promote", events)
        promote_row = next(r for r in rows if r["event_type"] == "asset.promote")
        self.assertIn("TLS_SAN", promote_row["reason"])


class TestAmendment(Harness):
    def test_amend_requires_a_reason(self):
        with self.assertRaises(SystemExit):
            self.run_cli("amend", "--add", "URL:https://new.acme.example")

    def test_amend_adds_to_the_boundary_and_records_a_gate(self):
        code, out, _ = self.run_cli("amend", "--add", "URL:https://api.other.example",
                                    "--reason", "client added the asset in writing 2026-08-05")
        self.assertEqual(code, 0)
        self.assertIn("void", out, "prior approvals must be invalidated by an amendment")
        text = (self.root / "scope.yaml").read_text()
        self.assertIn("api.other.example", text)
        rows = [json.loads(l) for l in
                (self.root / "ledger" / "gates.jsonl").read_text().splitlines() if l.strip()]
        self.assertEqual(rows[-1]["event_type"], "scope.amend")
        self.assertIn("in writing", rows[-1]["reason"])

    def test_amendment_that_would_not_parse_is_refused(self):
        code, _, err = self.run_cli("amend", "--add", "NOT_A_TYPE:whatever",
                                    "--reason", "typo test")
        self.assertEqual(code, 1)
        self.assertIn("not a recognised asset type", err)
        self.assertNotIn("NOT_A_TYPE", (self.root / "scope.yaml").read_text())

    def test_amend_then_promote_works(self):
        self.run_cli("add-candidate", "api.other.example",
                     "--signal", "TLS_SAN:x@crt.sh", "--signal", "CONTENT_FP:y@httpx")
        self.run_cli("amend", "--add", "WILDCARD:*.other.example", "--reason", "signed amendment")
        code, _, _ = self.run_cli("promote", "api.other.example", "--confirm")
        self.assertEqual(code, 0)


class TestShow(Harness):
    def test_show_lists_boundary_and_promotability(self):
        self.run_cli("add-candidate", "api.acme.example", "--signal", "TLS_SAN:x@crt.sh")
        _, out, _ = self.run_cli("show")
        self.assertIn("promo-test", out)
        self.assertIn("*.acme.example", out)
        self.assertIn("not promotable", out)

    def test_refuses_outside_an_engagement(self):
        with tempfile.TemporaryDirectory() as empty:
            out, err = io.StringIO(), io.StringIO()
            with redirect_stdout(out), redirect_stderr(err):
                code = scope_cli.main(["--root", empty, "show"])
            self.assertEqual(code, 1)
            self.assertIn("no scope.yaml", err.getvalue())


if __name__ == "__main__":
    unittest.main()
