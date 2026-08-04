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
            self.assertEqual(record["verified"], "n/a")

    def test_missing_headers_on_the_fixture_are_detected(self):
        records = self.run_scan()
        hsts = next(r for r in records if "strict-transport-security" in r["title"])
        self.assertEqual(hsts["result"], "present", "the fixture sets no security headers")

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


if __name__ == "__main__":
    unittest.main()
