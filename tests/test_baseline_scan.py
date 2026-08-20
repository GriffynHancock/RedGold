"""Build order step 5b acceptance test -- the deterministic baseline (P10).

**A deviation from the written acceptance test, stated plainly.**

§17.2 step 5b says: "The [prior engagement's] stack is scanned with no fingerprint supplied, and
the known public bucket is found by the baseline alone."

That target is **NOT AUTHORISED**. `status.md` blocker B-1 is explicit: artifacts only, do not
touch the live host. So the canonical acceptance test cannot be run, and running it would be the
exact failure this framework exists to prevent -- testing an asset we are not authorised to touch,
because a document told us to.

What runs instead: a local fixture that reproduces the *shape* of that finding -- an object-storage
listing returned to an unauthenticated caller -- and the baseline must find it with no fingerprint
supplied. That proves the mechanism. It does not prove the historical claim, and this file is the
record of that difference.
"""

from __future__ import annotations

import json
import os
import socketserver
import subprocess
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import baseline_scan  # noqa: E402
import findings as findings_mod  # noqa: E402
import report as report_mod  # noqa: E402

# A storage listing shaped like the real one: object names, ids, timestamps. Twelve entries,
# matching the prior engagement's twelve exposed profile-photo folders.
BUCKET_LISTING = json.dumps([
    {"name": f"user-{i:02d}/avatar.jpg", "id": f"obj-{i:02d}",
     "updated_at": "2026-07-30T10:00:00Z", "metadata": {"size": 20481}}
    for i in range(1, 13)
]).encode()


class FixtureHandler(BaseHTTPRequestHandler):
    def log_message(self, *args):  # silence the test output
        pass

    def do_GET(self):  # noqa: N802
        if self.path == "/storage/v1/object/list/public":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(BUCKET_LISTING)))
            self.end_headers()
            self.wfile.write(BUCKET_LISTING)
            return
        if self.path == "/":
            body = b"<html><body>fixture app</body></html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.send_header("Content-Length", "0")
        self.end_headers()


SCOPE_TEMPLATE = """engagement_id: baseline-test
client: {{name: C, contact: c@example.invalid}}
authorization:
  document: ../a.pdf
  signed_by: S
  signed_date: 2020-01-01
  window_start: 2020-01-01
  window_end: 2099-12-31
mode: audit
ceiling: 2
in_scope:
  - {{asset_type: URL, pattern: "http://127.0.0.1:{port}"}}
constraints: {{no_destructive: true}}
"""


class TestBaseline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        cls.port = cls.server.server_address[1]
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        (self.root / "scope.yaml").write_text(
            SCOPE_TEMPLATE.format(port=self.port), encoding="utf-8")
        (self.root / "evidence").mkdir()
        (self.root / "findings").mkdir()
        (self.root / "assets").mkdir()

    def run_scan(self, targets=None):
        return baseline_scan.scan(self.root, targets=targets or [self.base])

    # --- the acceptance criterion ------------------------------------------------------------

    def test_public_bucket_found_with_no_fingerprint_supplied(self):
        records = self.run_scan()
        bucket = [r for r in records
                  if "storage listing" in r["title"].lower() and r["result"] == "present"]
        self.assertEqual(len(bucket), 1, "the baseline must find the open listing unaided")
        self.assertEqual(bucket[0]["status"], "PROVEN")
        self.assertEqual(bucket[0]["severity"], "high")

    def test_detection_is_shape_based_not_vendor_based(self):
        # Nothing told the scanner what stack this is. The check must not key off a fingerprint,
        # because it runs before one is known.
        source = (REPO / "scripts" / "baseline_scan.py").read_text()
        detector = source.split("def _bucket_listing")[1].split("\ndef ")[0]
        # Strip the docstring -- it names vendors precisely to explain why the logic does not.
        body = detector.split('"""')[-1]
        for vendor in ("supabase", "firebase", "s3", "amazonaws"):
            self.assertNotIn(vendor, body.lower(),
                             "the bucket check must not depend on knowing the vendor")

    def test_bucket_check_fires_on_a_differently_shaped_payload(self):
        # Stronger than reading the source: a listing wrapped under a different key, with none
        # of the fixture's field names, must still trip the check.
        probe = baseline_scan.Probe(200, {}, json.dumps(
            {"objects": [{"key": "a/b.png", "size": 12}, {"key": "c/d.png", "size": 34}]}))
        self.assertTrue(baseline_scan._bucket_listing(probe))

    def test_bucket_check_ignores_an_empty_listing(self):
        self.assertFalse(baseline_scan._bucket_listing(
            baseline_scan.Probe(200, {}, json.dumps([]))))

    def test_bucket_check_ignores_non_listing_json(self):
        self.assertFalse(baseline_scan._bucket_listing(
            baseline_scan.Probe(200, {}, json.dumps({"message": "not found"}))))

    # --- negatives are first-class -----------------------------------------------------------

    def test_absent_conditions_are_recorded_not_dropped(self):
        records = self.run_scan()
        absent = [r for r in records if r["result"] == "absent"]
        self.assertTrue(absent, "negative results are half of what a coverage claim rests on")
        env = next(r for r in records if ".env" in r["title"] or "Environment file" in r["title"])
        self.assertEqual(env["result"], "absent")
        self.assertEqual(env["severity"], "info")
        self.assertEqual(env["status"], "SPECULATED")

    def test_every_check_produces_a_record(self):
        records = self.run_scan()
        expected = len(baseline_scan.CHECKS) + len(baseline_scan.SECURITY_HEADERS)
        self.assertEqual(len(records), expected)

    def test_run_is_deterministic(self):
        # P11: the baseline is identical every time. Two runs must agree on every verdict.
        first = {(r["title"], r["result"]) for r in self.run_scan()}
        second = {(r["title"], r["result"]) for r in self.run_scan()}
        self.assertEqual(first, second)

    # --- output is schema-conformant ---------------------------------------------------------

    def test_records_pass_the_findings_validator(self):
        """The baseline writes through the normal schema, so the validator must accept it."""
        records = self.run_scan()
        blocking = []
        for record in records:
            result = findings_mod.validate_record(record, self.root)
            blocking.extend(v.render() for v in result.blocking)
        self.assertEqual(blocking, [], "\n".join(blocking))

    def test_evidence_files_are_actually_written(self):
        records = self.run_scan()
        for record in records:
            path = self.root / record["evidence_ptr"]
            self.assertTrue(path.is_file(), f"missing evidence for {record['id']}")
            self.assertIn("GET ", path.read_text())

    def test_header_findings_are_posture_with_na_verification(self):
        records = self.run_scan()
        headers = [r for r in records if r["title"].startswith("Security header missing")]
        self.assertTrue(headers)
        for record in headers:
            self.assertEqual(record["finding_class"], "posture")
            if record["result"] == "not_applicable":
                # A check that was never evaluated has not been "observed and found to need no
                # replay" -- `n/a` is a claim about an exploit, and there was no observation to
                # make a claim about. `none` is the honest value (RG-1 §4.1a).
                self.assertEqual(record["verified"], "none")
            else:
                self.assertEqual(record["verified"], "n/a")

    def test_missing_headers_on_the_fixture_are_detected(self):
        records = self.run_scan()
        csp = next(r for r in records if "content-security-policy" in r["title"])
        self.assertEqual(csp["result"], "present", "the fixture sets no security headers")

    # --- E2(a): the scheme/protocol applicability filter (RG-1 §4.1a) ------------------------

    def test_hsts_is_not_a_finding_against_a_plaintext_origin(self):
        # The fixture is served over http://. HSTS delivered over plaintext is ignored by every
        # user agent, and the impact string this check generates -- "a downgrade to plaintext is
        # not prevented" -- contradicts itself on a connection that is already plaintext.
        records = self.run_scan()
        hsts = next(r for r in records if "strict-transport-security" in r["title"])
        self.assertEqual(hsts["result"], "not_applicable")
        self.assertEqual(hsts["not_applicable_reason"], "scheme_inapplicable")
        self.assertEqual(hsts["severity"], "info")

    def test_the_scheme_filter_only_removes_hsts_and_only_over_plaintext(self):
        # A filter that also silenced CSP, or that silenced HSTS on https, would be a coverage
        # loss wearing an applicability rule's clothes.
        self.assertFalse(baseline_scan.header_applicable(
            "http://example.invalid", "strict-transport-security"))
        self.assertTrue(baseline_scan.header_applicable(
            "https://example.invalid", "strict-transport-security"))
        for header in ("content-security-policy", "x-content-type-options"):
            self.assertTrue(baseline_scan.header_applicable("http://example.invalid", header))

    def test_a_skipped_hsts_check_is_still_recorded_not_silently_dropped(self):
        # "We did not look" and "there was nothing to look for" must stay distinguishable.
        records = self.run_scan()
        self.assertEqual(len(records),
                         len(baseline_scan.CHECKS) + len(baseline_scan.SECURITY_HEADERS))
        hsts = next(r for r in records if "strict-transport-security" in r["title"])
        self.assertTrue((self.root / hsts["evidence_ptr"]).is_file())

    # --- the environment cap, threaded through the loop (RG-1 §6, E1) -------------------------
    #
    # Siting, by the §4.8 test -- *name a healthy engagement state at which this fires*: every
    # scan of a non-production engagement that finds something. The declared environment exists
    # in scope.yaml before the scan starts, so the record can be stamped and capped at the moment
    # it is written -- which is what makes `environment_at_test` a fact about the test rather
    # than a value recomputed later from whatever scope.yaml says by then.

    def set_environment(self, value: str):
        path = self.root / "scope.yaml"
        path.write_text(path.read_text(encoding="utf-8") + f"environment: {value}\n",
                        encoding="utf-8")

    def bucket_finding(self, records):
        return next(r for r in records
                    if "storage listing" in r["title"].lower() and r["result"] == "present")

    def test_scanner_findings_are_stamped_with_the_environment_they_were_seen_in(self):
        self.set_environment("development")
        for record in self.run_scan():
            self.assertEqual(record["environment_at_test"], "development")

    def test_a_high_scanner_finding_is_capped_in_development(self):
        self.set_environment("development")
        record = self.bucket_finding(self.run_scan())
        self.assertEqual(record["severity"], "medium")
        self.assertTrue(record["severity_derivation"]["env_cap_applied"])
        self.assertEqual(record["severity_derivation"]["before_env_cap"], "high")

    def test_the_same_finding_is_uncapped_in_production(self):
        self.set_environment("production")
        record = self.bucket_finding(self.run_scan())
        self.assertEqual(record["severity"], "high")
        self.assertFalse(record["severity_derivation"]["env_cap_applied"])

    def test_an_undeclared_environment_caps_nothing(self):
        # The fixture scope declares no environment. Fail-closed here means "do not reduce what
        # the client is told" -- the refusal for an undeclared environment is Gate 1's job.
        record = self.bucket_finding(self.run_scan())
        self.assertEqual(record["severity"], "high")
        self.assertEqual(record["environment_at_test"], "production")

    def test_capped_records_still_pass_the_validator(self):
        self.set_environment("ephemeral-preview")
        for record in self.run_scan():
            result = findings_mod.validate_record(record, self.root)
            self.assertEqual([v.render() for v in result.blocking], [], record["id"])

    # --- the environment signals the scanner can actually see (RG-1 §2.4, §4.2) ---------------

    def test_a_test_mode_secret_key_in_a_response_body_is_a_blocking_signal(self):
        # `sk_test_` -- the *secret* prefix. This test used to assert the same verdict for
        # `pk_test_`, which is a **publishable** key: designed to be embedded in a page, and
        # routinely present on production documentation pages, "try it" widgets and SDK landing
        # pages. The requirement it should have encoded is §2.4's standard for a *blocking*
        # signal -- "a vendor-defined prefix with ONE meaning" -- and `pk_test_` has two. Since
        # this gate's action clause holds every finding on the asset out of the client report
        # body, asserting it on the ambiguous prefix encoded a suppression trigger as correct
        # behaviour (adversarial review, S7).
        probe = baseline_scan.Probe(200, {}, 'const stripeSecret="sk_test_51H8xQ2abcdefg";')
        self.assertEqual([s["kind"] for s in baseline_scan.env_signals(probe)],
                         ["test_payment_key"])

    def test_a_live_payment_key_is_not_a_nonprod_signal(self):
        probe = baseline_scan.Probe(200, {}, 'window.stripeKey="pk_live_51H8xQ2abcdefg";')
        self.assertEqual(baseline_scan.env_signals(probe), [])

    def test_a_dev_tool_fingerprint_in_a_server_header_is_a_blocking_signal(self):
        probe = baseline_scan.Probe(200, {"server": "Mailpit"}, "")
        self.assertEqual([s["kind"] for s in baseline_scan.env_signals(probe)],
                         ["dev_tool_fingerprint"])

    def test_the_fingerprint_does_not_fire_on_ordinary_production_responses(self):
        # A gate that fires on healthy input gets disabled, and a disabled gate is this whole
        # counterfactual undone. A Vite-built SPA deployed to production commonly still ships the
        # default `<title>Vite App</title>`; that is a build tool, not a dev server.
        for headers, body in (
            ({"server": "nginx"}, "<title>Acme</title>"),
            ({"server": "Vercel", "x-vercel-cache": "HIT"}, "<title>Acme</title>"),
            ({}, "<title>Vite App</title>"),
            ({}, "We use Mailtrap and MailHog in our stack. Read our blog!"),
        ):
            with self.subTest(headers=headers):
                self.assertEqual(
                    baseline_scan.env_signals(baseline_scan.Probe(200, headers, body)), [])

    def test_signals_are_attached_to_the_findings_from_that_asset(self):
        probe = baseline_scan.Probe(200, {"server": "Mailpit"}, "")
        self.assertTrue(baseline_scan.env_signals(probe))

    def test_every_emitted_signal_kind_is_one_the_validator_recognises(self):
        # A signal the scanner emits and the validator cannot read is a rule that never fires.
        for kind in baseline_scan.EMITTED_SIGNAL_KINDS:
            self.assertIn(kind, findings_mod.ENVIRONMENT_SIGNAL_KINDS)

    # --- it stays inside the boundary --------------------------------------------------------

    def test_target_outside_the_boundary_is_skipped(self):
        records = baseline_scan.scan(self.root, targets=["http://127.0.0.2:9/"])
        self.assertEqual(records, [], "the baseline must not probe outside the boundary")

    def test_scanning_without_confirmed_assets_yields_nothing(self):
        # The baseline does not discover its own targets -- it reads CONFIRMED register rows.
        (self.root / "assets" / "register.jsonl").write_text("", encoding="utf-8")
        self.assertEqual(baseline_scan.scan(self.root), [])

    def test_candidate_assets_are_not_scanned(self):
        (self.root / "assets" / "register.jsonl").write_text(
            json.dumps({"identifier": f"127.0.0.1:{self.port}", "status": "CANDIDATE"}) + "\n",
            encoding="utf-8")
        self.assertEqual(baseline_scan.scan(self.root), [])



# ================================================================================================
# One hostname, several ports (regression)
# ================================================================================================
#
# A live engagement filed six CONFIRMED assets on ONE hostname at six different ports -- web,
# MySQL, Redis, two Mailpit HTTP listeners and SMTP. The baseline produced twelve checks six times
# over, every one of them aimed at `https://<bare-host>/` with no port: the same target scanned
# once per register row. Two failures, and the second is the serious one.
#
#   1. Six identical copies of every finding, with six ids and six evidence files, overstating
#      both effort and breadth in anything built from them.
#   2. The services on 3306/6379/1025 were never contacted at all, yet appeared in the run with a
#      full complement of "absent" results -- a clean baseline recorded for services nobody
#      probed. A check that did not happen must never render as a check that passed.
#
# An asset is (host, port). The port is never dropped.


class RawGreetingHandler(socketserver.BaseRequestHandler):
    """A service that speaks something other than HTTP -- a MySQL-shaped server greeting.

    Stands in for MySQL/Redis/SMTP: the server talks first, so an HTTP client gets a reply that
    is not a status line.
    """

    def handle(self):
        self.request.sendall(b"\x4a\x00\x00\x00\x0a8.0.36-nonhttp-fixture\x00")


class MultiPortHarness(unittest.TestCase):
    """One host, three ports: two real HTTP services and one that does not speak HTTP."""

    @classmethod
    def setUpClass(cls):
        cls.http_a = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        cls.http_b = ThreadingHTTPServer(("127.0.0.1", 0), FixtureHandler)
        cls.raw = socketserver.ThreadingTCPServer(("127.0.0.1", 0), RawGreetingHandler)
        cls.raw.daemon_threads = True
        cls.servers = [cls.http_a, cls.http_b, cls.raw]
        for server in cls.servers:
            threading.Thread(target=server.serve_forever, daemon=True).start()
        cls.port_a = cls.http_a.server_address[1]
        cls.port_b = cls.http_b.server_address[1]
        cls.port_raw = cls.raw.server_address[1]
        cls.ports = [cls.port_a, cls.port_b, cls.port_raw]

    @classmethod
    def tearDownClass(cls):
        for server in cls.servers:
            server.shutdown()
            server.server_close()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        entries = "\n".join(f'  - {{asset_type: URL, pattern: "http://127.0.0.1:{p}"}}'
                            for p in self.ports)
        (self.root / "scope.yaml").write_text(
            SCOPE_TEMPLATE.format(port=self.port_a).replace(
                f'  - {{asset_type: URL, pattern: "http://127.0.0.1:{self.port_a}"}}', entries),
            encoding="utf-8")
        for name in ("evidence", "findings", "assets"):
            (self.root / name).mkdir()
        self.write_register(self.ports)

    def write_register(self, ports):
        rows = [{"asset_id": f"A-{i:03d}", "asset_type": "URL", "identifier": "127.0.0.1",
                 "port": port, "status": "CONFIRMED"}
                for i, port in enumerate(ports, 1)]
        (self.root / "assets" / "register.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")

    def base(self, port):
        return f"http://127.0.0.1:{port}"


class TestTargetsAreHostAndPort(MultiPortHarness):
    def test_each_confirmed_port_becomes_its_own_target(self):
        boundary = baseline_scan.scope_mod.load(self.root / "scope.yaml")
        targets = baseline_scan.confirmed_targets(self.root, boundary)
        self.assertEqual(sorted(targets), sorted(self.base(p) for p in self.ports))

    def test_the_bare_host_is_never_the_target_when_a_port_is_recorded(self):
        boundary = baseline_scan.scope_mod.load(self.root / "scope.yaml")
        for target in baseline_scan.confirmed_targets(self.root, boundary):
            self.assertRegex(target, r":\d+$",
                             "a register row's port must survive into the scanned target")

    def test_repeated_rows_for_one_host_and_port_are_scanned_once(self):
        self.write_register([self.port_a, self.port_a, self.port_a])
        boundary = baseline_scan.scope_mod.load(self.root / "scope.yaml")
        self.assertEqual(baseline_scan.confirmed_targets(self.root, boundary),
                         [self.base(self.port_a)])


class TestNoDuplicatedWork(MultiPortHarness):
    def test_finding_ids_are_unique_across_ports(self):
        records = baseline_scan.scan(self.root)
        ids = [r["id"] for r in records]
        self.assertEqual(len(ids), len(set(ids)))

    def test_no_check_and_target_pair_is_emitted_twice(self):
        records = baseline_scan.scan(self.root)
        pairs = [(r["asset"], r["title"]) for r in records]
        duplicates = {p for p in pairs if pairs.count(p) > 1}
        self.assertEqual(duplicates, set(),
                         "the same check against the same target must be recorded once")

    def test_every_confirmed_service_is_represented_exactly_once(self):
        records = baseline_scan.scan(self.root)
        assets = {r["asset"] for r in records}
        self.assertEqual(assets, {self.base(p) for p in self.ports})
        per_check = len(baseline_scan.CHECKS) + len(baseline_scan.SECURITY_HEADERS)
        # Two services answer HTTP and get the full checklist; the third answers nothing and gets
        # one collapsed coverage record naming all of it (RG-1 §4.1b).
        self.assertEqual(len(records), per_check * 2 + 1)

    def test_evidence_files_are_not_shared_between_services(self):
        records = baseline_scan.scan(self.root)
        pointers = [r["evidence_ptr"] for r in records]
        self.assertEqual(len(pointers), len(set(pointers)))


class TestHttpServiceOnANonStandardPortIsActuallyProbed(MultiPortHarness):
    def test_the_second_http_port_is_reached_not_merely_recorded(self):
        # The fixture on port B serves the open object listing. If the port were dropped, the
        # scan would report "absent" for a condition that is demonstrably present.
        records = baseline_scan.scan(self.root)
        for port in (self.port_a, self.port_b):
            hits = [r for r in records
                    if r["asset"] == self.base(port) and "storage listing" in r["title"].lower()]
            self.assertEqual(len(hits), 1)
            self.assertEqual(hits[0]["result"], "present",
                             f"the service on port {port} was never actually contacted")


class TestNonHttpPortIsAnHonestGapNotAPass(MultiPortHarness):
    def records_for_raw_port(self):
        return [r for r in baseline_scan.scan(self.root)
                if r["asset"] == self.base(self.port_raw)]

    def test_http_checks_against_a_non_http_service_are_never_recorded_absent(self):
        for record in self.records_for_raw_port():
            self.assertNotEqual(
                record["result"], "absent",
                f"{record['title']} was never sent to a service that speaks HTTP, so recording "
                "it as 'checked and absent' manufactures a false negative")

    def test_they_are_recorded_as_not_applicable_with_the_reason(self):
        records = self.records_for_raw_port()
        self.assertTrue(records, "the gap must be visible in the output, not omitted")
        for record in records:
            self.assertEqual(record["result"], "not_applicable")
            self.assertEqual(record["severity"], "info")
            self.assertNotEqual(record["status"], "PROVEN")
            self.assertIn("not tested", record["real_world_impact"].lower())

    def test_the_evidence_shows_what_the_service_actually_said(self):
        for record in self.records_for_raw_port():
            text = (self.root / record["evidence_ptr"]).read_text()
            self.assertIn("[no response]", text)

    def test_a_not_applicable_result_is_not_reported_as_a_finding(self):
        records = baseline_scan.scan(self.root)
        buckets = report_mod.classify(records, self.root)
        reported = {r["id"] for r in buckets["body"] + buckets["unverified"]}
        for record in records:
            if record["result"] == "not_applicable":
                self.assertNotIn(record["id"], reported,
                                 "a check that never ran must not surface as a finding")

    def test_not_applicable_records_still_pass_the_schema_validator(self):
        for record in self.records_for_raw_port():
            result = findings_mod.validate_record(record, self.root)
            self.assertEqual([v.render() for v in result.blocking], [])

    # --- E2(b): one coverage record per dead asset, not one per (check x dead asset) ---------
    #
    # A live engagement emitted 36 `not_applicable` records -- twelve checks against each of three
    # services that never answered HTTP -- for what is one coverage fact about three assets. The
    # cartesian product of the checklist and the asset list is not a set of results.

    def test_a_dead_asset_produces_exactly_one_coverage_record(self):
        self.assertEqual(len(self.records_for_raw_port()), 1)

    def test_the_collapsed_record_names_every_check_it_stands_for(self):
        record = self.records_for_raw_port()[0]
        expected = ([c.key for c in baseline_scan.CHECKS]
                    + [f"header_{h.replace('-', '_')}" for h in baseline_scan.SECURITY_HEADERS])
        self.assertEqual(record["skipped_checks"], expected)
        self.assertEqual(record["checks_skipped"], len(expected))
        self.assertEqual(record["not_applicable_reason"], "no_http_response")

    def test_collapsing_records_does_not_shrink_the_reported_coverage_gap(self):
        # Collapsing 12 records into 1 must not turn "twelve checks did not run" into "one check
        # did not run". The count is the honest number; the record count is an implementation
        # detail of how it is stored.
        record = self.records_for_raw_port()[0]
        self.assertEqual(record["checks_skipped"],
                         len(baseline_scan.CHECKS) + len(baseline_scan.SECURITY_HEADERS))


class NonProdHandler(BaseHTTPRequestHandler):
    """A service that says, in its own response, that it is not production."""

    def log_message(self, *args):
        pass

    def do_GET(self):  # noqa: N802
        body = (b'<html><head><title>App</title></head><body>'
                b'<script>const k="sk_test_51H8xQ2abcdefg";</script>'
                b'</body></html>')
        if self.path == "/storage/v1/object/list/public":
            body = BUCKET_LISTING
        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class TestDeclarationContradictedByTheAsset(unittest.TestCase):
    """RG-1 §4.2 end to end, at the site where its input exists.

    The engagement declares `production`; the asset hands back a test-mode payment key. That
    contradiction is unobservable at Gate 1 -- no request has been made yet (§9.7) -- and fully
    observable here, one request in. Everything downstream follows from the record.
    """

    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), NonProdHandler)
        cls.port = cls.server.server_address[1]
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.base = f"http://127.0.0.1:{cls.port}"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        (self.root / "scope.yaml").write_text(
            SCOPE_TEMPLATE.format(port=self.port) + "environment: production\n", encoding="utf-8")
        for name in ("evidence", "findings", "assets", "ledger"):
            (self.root / name).mkdir()

    def scan(self):
        return baseline_scan.scan(self.root, targets=[self.base])

    def test_the_observed_signal_is_recorded_on_the_findings_from_that_asset(self):
        for record in self.scan():
            self.assertEqual([s["kind"] for s in record["env_signals"]], ["test_payment_key"])

    def test_the_scanner_does_not_overrule_the_declaration(self):
        # It contradicts; it never sets. A model may not overrule a client's declaration about
        # its own systems -- it may only refuse to publish while the two disagree.
        for record in self.scan():
            self.assertEqual(record["environment_at_test"], "production")

    def test_a_blocker_is_raised_for_the_operator(self):
        self.scan()
        rows = [json.loads(l) for l in
                (self.root / "ledger" / "blockers.jsonl").read_text().splitlines() if l.strip()]
        self.assertEqual(len(rows), 1, "one blocker per asset, not one per finding")
        self.assertEqual(rows[0]["kind"], "ENVIRONMENT_DISCREPANCY")
        self.assertIsNone(rows[0]["resolved"])

    def test_the_affected_findings_do_not_enter_the_report_body(self):
        records = self.scan()
        buckets = report_mod.classify(records, self.root)
        self.assertTrue(buckets["environment_discrepancy"])
        self.assertEqual(buckets["body"], [])

    def test_a_matching_declaration_raises_nothing(self):
        # The whole point of splitting the check: `development` plus a dev signal is a consistent
        # engagement, and nothing about it should be held back.
        path = self.root / "scope.yaml"
        path.write_text(path.read_text().replace("environment: production",
                                                 "environment: development"), encoding="utf-8")
        records = self.scan()
        self.assertEqual(report_mod.classify(records, self.root)["environment_discrepancy"], [])
        self.assertFalse((self.root / "ledger" / "blockers.jsonl").exists())


class TestTheSignalsDoNotFireOnProductionTraffic(unittest.TestCase):
    """S7. This gate's action clause removes findings from the client report body, so a false
    positive here is a *suppression* event, not a nuisance -- every finding on the asset is held
    back until an operator records which side was wrong.

    §4.8's second test -- *name a healthy state at which this fires* -- was never run against a
    corpus of realistic production responses. There were several.
    """

    def signals(self, headers: dict, body: str) -> list:
        return [s["kind"] for s in
                baseline_scan.env_signals(baseline_scan.Probe(200, headers, body))]

    def test_a_publishable_test_key_on_a_docs_page_is_not_a_verdict(self):
        # `pk_test_` is designed to be embedded in a page and is routinely present on production
        # documentation, "try it" widgets and SDK landing pages. Only the *secret* prefix has one
        # meaning, which is the standard §2.4 requires of a blocking signal.
        self.assertEqual(
            self.signals({}, "<title>API keys</title>Use your test key "
                             "<code>pk_test_51HxYzAbCdEfGhIjK</code> to try this."),
            [])

    def test_a_secret_test_key_is_still_a_verdict(self):
        self.assertEqual(self.signals({}, 'STRIPE_SECRET="sk_test_51HxYzAbCdEfGhIjK"'),
                         ["test_payment_key"])

    def test_a_production_celery_dashboard_banner_is_not_a_verdict(self):
        # Flower is a production monitoring UI for Celery. It was removed from the *title* token
        # list for exactly this reason, with the reasoning written out -- and retained in the
        # header list, matched as a bare substring of the server banner.
        self.assertEqual(self.signals({"server": "Flower/2.0"}, ""), [])

    def test_a_production_page_mentioning_mailtrap_in_a_header_is_not_a_verdict(self):
        self.assertEqual(self.signals({"x-powered-by": "Mailtrap-Edge/1.2"}, ""), [])

    def test_a_production_spa_built_with_vite_is_not_a_verdict(self):
        self.assertEqual(self.signals({"server": "nginx", "x-powered-by": "Vite"},
                                      "<title>Acme</title>"), [])

    def test_a_real_dev_mail_catcher_is_still_a_verdict(self):
        # The other direction: dropping the ambiguous tokens must not empty the signal.
        for headers in ({"server": "Mailpit"}, {"server": "MailHog"},
                        {"x-powered-by": "Adminer"}, {"server": "webpack-dev-server"}):
            with self.subTest(headers=headers):
                self.assertEqual(self.signals(headers, ""), ["dev_tool_fingerprint"])


class TestBlockerIdsAreDeterministic(unittest.TestCase):
    """S9. `abs(hash(base)) % 1000` -- Python randomises `str.__hash__` per process, so
    re-running the scan re-raised the same asset's blocker under a new id and `gate_cli resolve`
    could never stick to the asset. Two distinct assets also collided at roughly 1 in 1000, and
    `cmd_resolve` takes the first match, so resolving one silently resolved the wrong blocker.
    """

    def test_the_same_asset_gets_the_same_id_in_a_fresh_interpreter(self):
        code = ("import sys; sys.path.insert(0, %r); import baseline_scan; "
                "print(baseline_scan.blocker_id('https://app.example.invalid'))"
                % str(REPO / "scripts"))
        ids = {subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                              env={**os.environ, "PYTHONHASHSEED": str(seed)}).stdout.strip()
               for seed in (0, 1, 2, 3)}
        self.assertEqual(len(ids), 1, f"id varies with the interpreter's hash seed: {ids}")

    def test_distinct_assets_get_distinct_ids(self):
        assets = [f"https://host{i}.example.invalid" for i in range(500)]
        ids = {baseline_scan.blocker_id(a) for a in assets}
        self.assertEqual(len(ids), len(assets))


if __name__ == "__main__":
    unittest.main()
