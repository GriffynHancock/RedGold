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

SCOPE_WITH_URL_ENTRY = """engagement_id: promo-url-test
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
  - {asset_type: URL, pattern: "http://127.0.0.1:8901"}
constraints: {no_destructive: true}
"""

SCOPE_MULTI_PORT_HOST = """engagement_id: promo-multiport-test
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
  - {asset_type: URL, pattern: "http://127.0.0.1"}
  - {asset_type: URL, pattern: "http://127.0.0.1:2368"}
  - {asset_type: URL, pattern: "http://127.0.0.1:3306"}
  - {asset_type: URL, pattern: "http://127.0.0.1:6379"}
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


class URLHarness(Harness):
    """A boundary whose only in-scope entry is a URL naming a specific host and port --
    the repro case for the URL-identifier promotion bug."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        (self.root / "scope.yaml").write_text(SCOPE_WITH_URL_ENTRY, encoding="utf-8")
        (self.root / "assets").mkdir()
        (self.root / "ledger").mkdir()

    def add_and_promote(self, identifier: str) -> tuple[int, str, str]:
        self.run_cli("add-candidate", identifier,
                     "--signal", "TLS_SAN:localtest.example@manual",
                     "--signal", "CONTENT_FP:matches-build-hash@manual")
        return self.run_cli("promote", identifier, "--confirm")


class TestURLTypedCandidatePromotion(URLHarness):
    def test_url_identifier_matching_a_url_scope_entry_promotes(self):
        code, out, err = self.add_and_promote("http://127.0.0.1:8901")
        self.assertEqual(code, 0, err)
        self.assertIn("CONFIRMED", out)
        register = self.register()
        self.assertEqual(len(register), 1)
        # The register holds one consistent form -- a bare host, not the raw URL string.
        self.assertEqual(register[0]["identifier"], "127.0.0.1")
        self.assertEqual(register[0]["port"], 8901)

    def test_url_identifier_on_a_host_outside_the_boundary_is_refused(self):
        code, _, err = self.add_and_promote("http://10.0.0.5:8901")
        self.assertEqual(code, 1)
        self.assertIn("outside the authorization boundary", err)
        self.assertEqual(self.register(), [])

    def test_url_identifier_on_an_authorised_host_but_unauthorised_port_is_refused(self):
        # Same host as the scope entry, different port. Must not promote -- an entry that names
        # a specific port authorises exactly that port, not the whole host on any port.
        code, _, err = self.add_and_promote("http://127.0.0.1:9999")
        self.assertEqual(code, 1)
        self.assertIn("outside the authorization boundary", err)
        self.assertEqual(self.register(), [])

class TestBareHostPromotionIsUnchanged(Harness):
    """The URL-normalisation fix must not touch the already-working bare-host path."""

    def test_bare_host_promotes_as_before(self):
        self.run_cli("add-candidate", "api.acme.example",
                     "--signal", "TLS_SAN:api.acme.example@crt.sh",
                     "--signal", "CONTENT_FP:bundle-hash@httpx")
        code, out, err = self.run_cli("promote", "api.acme.example", "--confirm")
        self.assertEqual(code, 0, err)
        self.assertIn("CONFIRMED", out)
        register = self.register()
        self.assertEqual(register[0]["identifier"], "api.acme.example")
        self.assertIsNone(register[0]["port"])

    def test_bare_host_outside_boundary_is_still_refused(self):
        self.run_cli("add-candidate", "api.other.example",
                     "--signal", "TLS_SAN:x@crt.sh", "--signal", "CONTENT_FP:y@httpx")
        code, _, err = self.run_cli("promote", "api.other.example", "--confirm")
        self.assertEqual(code, 1)
        self.assertIn("outside the authorization boundary", err)


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


class MultiPortHarness(Harness):
    """One hostname carrying several distinct in-scope services, each on its own port.

    This is the shape a real engagement hit: seven services behind one host, each named as its
    own in_scope entry. Each is a separate asset and must get its own row.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        (self.root / "scope.yaml").write_text(SCOPE_MULTI_PORT_HOST, encoding="utf-8")
        (self.root / "assets").mkdir()
        (self.root / "ledger").mkdir()

    def add(self, identifier: str, **kw) -> tuple[int, str, str]:
        return self.run_cli("add-candidate", identifier,
                            "--signal", "TLS_SAN:localtest.example@manual",
                            "--signal", "CONTENT_FP:matches-build-hash@manual",
                            *kw.pop("extra", ()))


class TestCandidateDedupIsPerHostAndPort(MultiPortHarness):
    def test_two_ports_on_one_host_are_two_separate_candidates(self):
        code_a, _, err_a = self.add("http://127.0.0.1:2368")
        code_b, _, err_b = self.add("http://127.0.0.1:3306")
        self.assertEqual(code_a, 0, err_a)
        self.assertEqual(code_b, 0, err_b)

        rows = self.candidates()
        self.assertEqual(len(rows), 2, rows)
        self.assertEqual([r["identifier"] for r in rows], ["127.0.0.1", "127.0.0.1"])
        self.assertEqual(sorted(r["port"] for r in rows), [2368, 3306])
        self.assertEqual(len({r["asset_id"] for r in rows}), 2)
        # Each must bind to the boundary entry that actually names its port.
        self.assertEqual({r["port"]: r["matched_boundary_entry"] for r in rows},
                         {2368: "URL:http://127.0.0.1:2368", 3306: "URL:http://127.0.0.1:3306"})

    def test_all_seven_services_on_one_host_can_be_filed(self):
        ports = [2368, 3306, 6379]
        for port in ports:
            code, _, err = self.add(f"http://127.0.0.1:{port}")
            self.assertEqual(code, 0, err)
        code, _, err = self.add("127.0.0.1")            # the bare-host / port-80 service
        self.assertEqual(code, 0, err)
        rows = self.candidates()
        self.assertEqual(len(rows), 4, rows)
        self.assertEqual(sorted(r["port"] for r in rows if r["port"]), ports)
        self.assertEqual(len({r["asset_id"] for r in rows}), 4)

    def test_same_host_and_same_port_twice_is_still_refused(self):
        self.assertEqual(self.add("http://127.0.0.1:2368")[0], 0)
        code, _, err = self.add("http://127.0.0.1:2368")
        self.assertEqual(code, 1)
        self.assertIn("2368", err)
        self.assertEqual(len(self.candidates()), 1)

    def test_bare_host_with_no_port_twice_is_still_refused(self):
        self.assertEqual(self.add("127.0.0.1")[0], 0)
        code, _, err = self.add("127.0.0.1")
        self.assertEqual(code, 1)
        self.assertIn("127.0.0.1", err)
        self.assertEqual(len(self.candidates()), 1)

    def test_a_host_and_port_already_CONFIRMED_is_refused_too(self):
        self.assertEqual(self.add("http://127.0.0.1:2368")[0], 0)
        self.assertEqual(self.run_cli("promote", "http://127.0.0.1:2368", "--confirm")[0], 0)
        code, _, err = self.add("http://127.0.0.1:2368")
        self.assertEqual(code, 1)
        self.assertIn("register", err)


class TestPromoteIsPerHostAndPort(MultiPortHarness):
    def test_promote_picks_the_candidate_on_the_named_port(self):
        self.add("http://127.0.0.1:2368")
        self.add("http://127.0.0.1:3306")
        code, out, err = self.run_cli("promote", "http://127.0.0.1:3306", "--confirm")
        self.assertEqual(code, 0, err)
        register = self.register()
        self.assertEqual(len(register), 1)
        self.assertEqual(register[0]["port"], 3306)
        self.assertEqual(register[0]["matched_boundary_entry"], "URL:http://127.0.0.1:3306")

    def test_promoting_one_port_leaves_the_other_ports_queued(self):
        self.add("http://127.0.0.1:2368")
        self.add("http://127.0.0.1:3306")
        self.add("http://127.0.0.1:6379")
        self.assertEqual(self.run_cli("promote", "http://127.0.0.1:3306", "--confirm")[0], 0)
        remaining = self.candidates()
        self.assertEqual(sorted(r["port"] for r in remaining), [2368, 6379])

    def test_promoting_a_port_that_was_never_filed_is_refused(self):
        self.add("http://127.0.0.1:2368")
        code, _, err = self.run_cli("promote", "http://127.0.0.1:6379", "--confirm")
        self.assertEqual(code, 1)
        self.assertIn("6379", err)
        self.assertEqual(self.register(), [])
        self.assertEqual(len(self.candidates()), 1)

    def test_bare_host_promote_is_refused_when_the_host_is_ambiguous(self):
        self.add("http://127.0.0.1:2368")
        self.add("http://127.0.0.1:3306")
        code, _, err = self.run_cli("promote", "127.0.0.1", "--confirm")
        self.assertEqual(code, 1)
        self.assertIn("2368", err)
        self.assertIn("3306", err)
        self.assertEqual(self.register(), [])
        self.assertEqual(len(self.candidates()), 2)

    def test_bare_host_promote_still_works_when_there_is_exactly_one_candidate(self):
        # The documented convenience: re-typing `promote` without the port must not drop a port
        # the in_scope entry named specifically.
        self.add("http://127.0.0.1:2368")
        code, _, err = self.run_cli("promote", "127.0.0.1", "--confirm")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.register()[0]["port"], 2368)


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
