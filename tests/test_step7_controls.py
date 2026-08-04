"""Build order step 7 acceptance test.

Acceptance criterion (§17.2): "The [prior engagement's] 20-request overrun is denied; a write with
no verified canary is denied."

Both halves are a real incident turned into an exit code:

  * a hand-rolled loop authorised for 10 requests that sent 20, because it counted iterations
    while the loop body dispatched two requests per pass;
  * 15 undeletable rows and 6 orphaned rows left in a live client database, because writes ran
    faster than cleanup could be guaranteed.
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

import canary_check  # noqa: E402
import no_handrolled_loops as loops  # noqa: E402

LOOP_HOOK = REPO / "scripts" / "no_handrolled_loops.py"
CANARY_HOOK = REPO / "scripts" / "canary_check.py"
RATE_PROBE = REPO / "scripts" / "rate_probe.sh"


class TestTheOverrunIsDenied(unittest.TestCase):
    """First half of the acceptance criterion."""

    def assertDenied(self, command: str):
        allow, reason = loops.evaluate(command)
        self.assertFalse(allow, f"should have been denied: {command}")
        return reason

    def assertAllowed(self, command: str):
        allow, _ = loops.evaluate(command)
        self.assertTrue(allow, f"should have been allowed: {command}")

    def test_the_original_shape_is_denied(self):
        # The actual incident: a shell loop whose body fired two requests per pass.
        reason = self.assertDenied(
            'for i in $(seq 1 10); do curl -s -X PATCH https://api.example.invalid/rows; '
            'curl -s https://api.example.invalid/verify; done'
        )
        self.assertIn("hand-rolled request loop", reason)
        self.assertIn("rate_probe.sh", reason)

    def test_while_loop_denied(self):
        self.assertDenied('while true; do curl -s https://api.example.invalid/; done')

    def test_xargs_fanout_denied(self):
        self.assertDenied('seq 1 20 | xargs -P4 -I{} curl -s https://api.example.invalid/{}')

    def test_brace_expansion_is_a_loop(self):
        # One command, twenty requests, no loop keyword anywhere.
        self.assertDenied('curl -s https://api.example.invalid/items/{1..20}')

    def test_curl_url_globbing_is_a_loop(self):
        self.assertDenied('curl -s "https://api.example.invalid/items/[1-20]"')

    def test_curl_parallel_mode_denied(self):
        self.assertDenied('curl -Z -s https://api.example.invalid/a https://api.example.invalid/b')

    def test_backgrounded_request_denied(self):
        self.assertDenied('curl -s https://api.example.invalid/slow &')

    def test_gnu_parallel_denied(self):
        self.assertDenied('parallel curl -s https://api.example.invalid/{} ::: 1 2 3')

    # --- what must still be allowed --------------------------------------------------------

    def test_single_request_allowed(self):
        self.assertAllowed('curl -s https://api.example.invalid/health')

    def test_loop_over_local_files_allowed(self):
        # Not this hook's business. A guard that fires on everything gets routed around.
        self.assertAllowed('for f in findings/*.json; do jq . "$f"; done')

    def test_the_sanctioned_probe_is_allowed(self):
        self.assertAllowed(
            'bash scripts/rate_probe.sh --url https://api.example.invalid/x --gate-ref G-002 --max 10'
        )

    def test_word_boundaries_do_not_produce_false_positives(self):
        self.assertAllowed('curl -s https://api.example.invalid/formatter')
        self.assertAllowed('curl -s https://api.example.invalid/whilelist')

    # --- as a hook -------------------------------------------------------------------------

    def test_hook_emits_a_deny_decision(self):
        payload = json.dumps({"tool_name": "Bash", "tool_input": {
            "command": 'for i in 1 2 3; do curl -s https://api.example.invalid/; done'}})
        proc = subprocess.run(["/usr/bin/python3", str(LOOP_HOOK)], input=payload,
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0)
        decision = json.loads(proc.stdout)["hookSpecificOutput"]
        self.assertEqual(decision["permissionDecision"], "deny")

    def test_hook_is_silent_when_allowing(self):
        payload = json.dumps({"tool_name": "Bash", "tool_input": {
            "command": 'curl -s https://api.example.invalid/'}})
        proc = subprocess.run(["/usr/bin/python3", str(LOOP_HOOK)], input=payload,
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.stdout.strip(), "")

    def test_garbage_input_denies_rather_than_crashing(self):
        proc = subprocess.run(["/usr/bin/python3", str(LOOP_HOOK)], input="not json",
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0)
        self.assertIn("could not evaluate", proc.stdout)


class CanaryHarness(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        (self.root / "ledger").mkdir()
        (self.root / "scope.yaml").write_text("engagement_id: t\n", encoding="utf-8")

    def decide(self, command: str):
        return canary_check.evaluate(
            {"tool_name": "Bash", "tool_input": {"command": command}}, self.root)

    def add_cleanup_row(self, **row):
        with (self.root / "ledger" / "cleanup.jsonl").open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row) + "\n")

    def write_plan(self, plan: dict):
        (self.root / "ledger" / "plan.json").write_text(json.dumps(plan), encoding="utf-8")


class TestWriteWithoutCanaryIsDenied(CanaryHarness):
    """Second half of the acceptance criterion."""

    def test_write_with_no_canary_and_no_plan_is_denied(self):
        allow, reason = self.decide(
            "curl -X POST https://api.example.invalid/rest/v1/subscriptions -d '{}'")
        self.assertFalse(allow)
        self.assertIn("no write authorisation", reason.lower())
        self.assertIn("15 undeletable rows", reason)

    def test_reads_are_not_affected(self):
        self.assertTrue(self.decide("curl -s https://api.example.invalid/rest/v1/x")[0])

    def test_canary_proven_deleted_unblocks_the_same_operation(self):
        self.add_cleanup_row(purpose="canary", state="deleted", method="POST",
                             route_template="/rest/v1/subscriptions",
                             operation="POST /rest/v1/subscriptions")
        self.assertTrue(self.decide(
            "curl -X POST https://api.example.invalid/rest/v1/subscriptions -d '{}'")[0])

    def test_a_canary_still_pending_does_not_unblock(self):
        # The incident was precisely that deletion failed. A created canary proves nothing.
        self.add_cleanup_row(purpose="canary", state="pending", method="POST",
                             route_template="/rest/v1/subscriptions",
                             operation="POST /rest/v1/subscriptions")
        self.assertFalse(self.decide(
            "curl -X POST https://api.example.invalid/rest/v1/subscriptions -d '{}'")[0])

    def test_an_orphaned_canary_does_not_unblock(self):
        self.add_cleanup_row(purpose="canary", state="orphaned", method="POST",
                             route_template="/rest/v1/subscriptions",
                             operation="POST /rest/v1/subscriptions")
        self.assertFalse(self.decide(
            "curl -X POST https://api.example.invalid/rest/v1/subscriptions -d '{}'")[0])

    def test_canary_for_one_operation_does_not_unblock_another(self):
        self.add_cleanup_row(purpose="canary", state="deleted", method="POST",
                             route_template="/rest/v1/notes",
                             operation="POST /rest/v1/notes")
        self.assertFalse(self.decide(
            "curl -X POST https://api.example.invalid/rest/v1/subscriptions -d '{}'")[0])

    def test_canary_for_one_method_does_not_unblock_another(self):
        self.add_cleanup_row(purpose="canary", state="deleted", method="POST",
                             route_template="/rest/v1/notes", operation="POST /rest/v1/notes")
        self.assertFalse(self.decide("curl -X DELETE https://api.example.invalid/rest/v1/notes")[0])


class TestPreApprovalPath(CanaryHarness):
    """§9.4.1 -- a canary alone dead-ends where RLS correctly forbids anonymous deletes."""

    def test_plan_preapproval_permits_the_write(self):
        self.write_plan({"write_endpoints": [
            {"method": "POST", "route_template": "/rest/v1/subscriptions", "max_writes": 3}]})
        self.assertTrue(self.decide(
            "curl -X POST https://api.example.invalid/rest/v1/subscriptions -d '{}'")[0])

    def test_exhausted_budget_denies(self):
        self.write_plan({"write_endpoints": [
            {"method": "POST", "route_template": "/rest/v1/subscriptions", "max_writes": 2}]})
        for _ in range(2):
            self.add_cleanup_row(purpose="test-data", state="pending", method="POST",
                                 route_template="/rest/v1/subscriptions",
                                 operation="POST /rest/v1/subscriptions")
        allow, reason = self.decide(
            "curl -X POST https://api.example.invalid/rest/v1/subscriptions -d '{}'")
        self.assertFalse(allow)
        self.assertIn("budget", reason)

    def test_plan_covering_a_different_route_does_not_help(self):
        self.write_plan({"write_endpoints": [
            {"method": "POST", "route_template": "/rest/v1/notes", "max_writes": 5}]})
        self.assertFalse(self.decide(
            "curl -X POST https://api.example.invalid/rest/v1/subscriptions -d '{}'")[0])


class TestOperationIdentity(CanaryHarness):
    def test_path_ids_are_normalised_to_a_template(self):
        self.assertEqual(canary_check.normalise_route("/api/users/42/comments/7"),
                         "/api/users/{id}/comments/{id}")

    def test_uuids_are_normalised(self):
        self.assertEqual(
            canary_check.normalise_route("/api/s/3f2504e0-4f89-11d3-9a0c-0305e82c3301"),
            "/api/s/{id}")

    def test_canary_keyed_by_template_not_literal_url(self):
        self.add_cleanup_row(purpose="canary", state="deleted", method="DELETE",
                             route_template="/api/notes/{id}",
                             operation="DELETE /api/notes/{id}")
        # A different literal id, same operation -- the canary applies.
        self.assertTrue(self.decide("curl -X DELETE https://api.example.invalid/api/notes/991")[0])

    def test_graphql_without_an_operation_name_is_denied(self):
        allow, reason = self.decide(
            "curl -X POST https://api.example.invalid/graphql -d '{\"foo\":1}'")
        self.assertFalse(allow)
        self.assertIn("operation not identifiable", reason.lower())

    def test_graphql_canary_does_not_unblock_a_different_mutation(self):
        self.add_cleanup_row(purpose="canary", state="deleted", method="POST",
                             route_template="/graphql", operation="createComment")
        allow, _ = self.decide(
            'curl -X POST https://api.example.invalid/graphql '
            '-d \'{"operationName":"deleteAccount","query":"mutation deleteAccount {x}"}\'')
        self.assertFalse(allow, "a canary for createComment must never unblock deleteAccount")

    def test_graphql_canary_unblocks_its_own_mutation(self):
        self.add_cleanup_row(purpose="canary", state="deleted", method="POST",
                             route_template="/graphql", operation="createComment")
        allow, _ = self.decide(
            'curl -X POST https://api.example.invalid/graphql '
            '-d \'{"operationName":"createComment","query":"mutation createComment {x}"}\'')
        self.assertTrue(allow)


class TestRateProbeScript(unittest.TestCase):
    """The sanctioned path the loop hook points at."""

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        (self.root / "scope.yaml").write_text(
            "engagement_id: probe-test\n"
            "client: {name: C, contact: c@example.invalid}\n"
            "authorization: {document: a.pdf, signed_by: S, signed_date: 2020-01-01,\n"
            "  window_start: 2020-01-01, window_end: 2099-12-31}\n"
            "mode: audit\nceiling: 2\n"
            'in_scope: [{asset_type: WILDCARD, pattern: "*.example.invalid"}]\n'
            "constraints: {no_destructive: true, max_requests_per_burst: 10}\n",
            encoding="utf-8")

    def run_probe(self, *args) -> subprocess.CompletedProcess:
        return subprocess.run(
            ["bash", str(RATE_PROBE), "--root", str(self.root), *args],
            capture_output=True, text=True, timeout=60)

    def test_refuses_without_a_gate_reference(self):
        proc = self.run_probe("--url", "http://127.0.0.1:9/")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--gate-ref is required", proc.stderr)

    def test_refuses_a_cap_above_the_scope_limit(self):
        # The whole point: a burst ceiling may be lowered here, never raised.
        proc = self.run_probe("--url", "http://127.0.0.1:9/", "--gate-ref", "G-002", "--max", "20")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("exceeds scope.yaml's cap of 10", proc.stderr)

    def test_refuses_outside_an_engagement(self):
        with tempfile.TemporaryDirectory() as empty:
            proc = subprocess.run(
                ["bash", str(RATE_PROBE), "--root", empty, "--url", "http://127.0.0.1:9/",
                 "--gate-ref", "G-002"],
                capture_output=True, text=True, timeout=60)
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("no scope.yaml", proc.stderr)

    def test_counter_increments_once_per_dispatch(self):
        """The invariant that the original bug violated.

        Asserted against the source: exactly one `sent=$((sent + 1))` and exactly one dispatch
        site inside the loop. A second curl in the body is how 10 became 20.
        """
        source = RATE_PROBE.read_text()
        loop_body = source.split("while [[ \"$sent\" -lt \"$cap\" ]]; do")[1].split("\ndone")[0]
        self.assertEqual(loop_body.count("sent=$((sent + 1))"), 1)
        self.assertEqual(loop_body.count('code="$(curl'), 2,
                         "two branches (with and without a body), but only one runs per pass")
        self.assertNotIn("&\n", loop_body, "no backgrounding -- requests are strictly sequential")


if __name__ == "__main__":
    unittest.main()
