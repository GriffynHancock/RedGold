"""Regression tests for bypasses found by an independent audit, 2026-08-04.

Two hostile subagents were pointed at this code with different framings: one told to prove the
controls do not work, one told to prove the documentation overstates them. Between them they found
11 real defects that the 308 tests written alongside the code did not catch -- because those tests
share the author's blind spots exactly.

**That is the point of this file.** Every test below corresponds to something that was ALLOWED and
should have been DENIED, verified by execution before the fix and after it. None of these would
have been written without an adversary.
"""

from __future__ import annotations

import datetime as _dt
import json
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import canary_check  # noqa: E402
import findings as findings_mod  # noqa: E402
import no_handrolled_loops as loops  # noqa: E402
import no_nesting  # noqa: E402
import redact  # noqa: E402
import regen_status  # noqa: E402
import report  # noqa: E402
import scope as scope_mod  # noqa: E402
import scope_cli  # noqa: E402
import scope_guard  # noqa: E402


class TestMethodExtraction(unittest.TestCase):
    """`-XDELETE` with no space is valid curl. A `\\s+` pattern missed it, which bypassed write
    authorisation and tier classification simultaneously -- the single strongest finding."""

    def test_attached_method_flag_is_read(self):
        for verb in ("DELETE", "POST", "PUT", "PATCH"):
            with self.subTest(verb=verb):
                cmd = f"curl -X{verb} https://a.example.invalid/x"
                self.assertEqual(canary_check.extract_method(cmd), verb)

    def test_attached_method_flag_sets_tier_2(self):
        self.assertEqual(scope_guard.classify_tier("curl -XPOST https://a.example.invalid/x"), 2)

    def test_request_flag_without_separator(self):
        self.assertEqual(
            canary_check.extract_method("curl --request=DELETE https://a.example.invalid/x"),
            "DELETE")

    def test_upload_file_is_a_write(self):
        for flag in ("-T f.txt", "--upload-file f.txt"):
            with self.subTest(flag=flag):
                cmd = f"curl {flag} https://a.example.invalid/x"
                self.assertEqual(canary_check.extract_method(cmd), "PUT")
                self.assertEqual(scope_guard.classify_tier(cmd), 2)


class TestLoopGuardBypasses(unittest.TestCase):
    def deny(self, command: str):
        allow, _ = loops.evaluate(command)
        self.assertFalse(allow, f"allowed: {command}")

    def test_sanctioned_string_in_a_comment_does_not_sanction(self):
        # A real 50-iteration loop was waved through by appending `# rate_probe.sh`.
        self.deny("for i in $(seq 1 50); do curl https://a.example.invalid/; done # rate_probe.sh")

    def test_sanctioned_string_in_an_argument_does_not_sanction(self):
        self.deny('for i in 1 2 3; do curl https://a.example.invalid/rate_probe.sh; done')

    def test_the_real_probe_is_still_sanctioned(self):
        allow, _ = loops.evaluate(
            "bash scripts/rate_probe.sh --url https://a.example.invalid/x --gate-ref G-002")
        self.assertTrue(allow)

    def test_find_exec_fanout(self):
        self.deny("find . -name '*.txt' -exec curl https://a.example.invalid/ ;")

    def test_many_positional_urls_is_a_burst(self):
        self.deny("curl " + " ".join(f"https://a.example.invalid/{i}" for i in range(12)))

    def test_a_couple_of_urls_is_not_a_burst(self):
        # The line has to be somewhere; two calls is not a fan-out.
        allow, _ = loops.evaluate(
            "curl https://a.example.invalid/a https://a.example.invalid/b")
        self.assertTrue(allow)

    def test_recursive_shell_function(self):
        self.deny("f() { curl https://a.example.invalid/$1; }; f 1")

    def test_curl_config_file_of_urls(self):
        self.deny("curl -K urls.conf")

    def test_wget_input_file(self):
        self.deny("wget -i urls.txt")

    def test_wget_recursive_mirror(self):
        self.deny("wget --mirror https://a.example.invalid/")


class TestScopeGuardBypasses(unittest.TestCase):
    def test_locally_invoked_script_is_undeterminable(self):
        # Renaming a tier-3 tool (`sqlmap` -> `./sqlmap-wrapper.sh`) evaded tier classification
        # entirely, because classification is token-based. Denying script invocation closes it.
        with self.assertRaises(scope_guard.Undeterminable):
            scope_guard.extract_hosts(
                "Bash", {"command": "./sqlmap-wrapper.sh -u https://a.example.invalid/"})

    def test_absolute_path_script_is_undeterminable(self):
        with self.assertRaises(scope_guard.Undeterminable):
            scope_guard.extract_hosts(
                "Bash", {"command": "/opt/tools/probe.py --target https://a.example.invalid/"})

    def test_dsn_style_port_is_extracted(self):
        # `psql "host=h port=6379"` evaded the `-p` flag pattern and reached a non-standard port
        # on an in-scope host.
        targets = scope_guard.extract_hosts(
            "Bash", {"command": 'psql "host=a.example.invalid port=6379 user=x"'})
        self.assertIn(("a.example.invalid", 6379), targets)


class TestCanaryBypasses(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        (self.root / "ledger").mkdir()
        (self.root / "scope.yaml").write_text("engagement_id: t\n", encoding="utf-8")

    def decide(self, command: str):
        return canary_check.evaluate({"tool_name": "Bash", "tool_input": {"command": command}},
                                     self.root)

    def test_graphql_mutation_by_get_is_still_a_write(self):
        allow, _ = self.decide(
            'curl "https://a.example.invalid/graphql?query=mutation%20deleteAccount"')
        self.assertFalse(allow, "a mutation is a write whatever verb carries it")

    def test_attached_method_flag_reaches_write_authorisation(self):
        allow, _ = self.decide("curl -XDELETE https://a.example.invalid/api/notes")
        self.assertFalse(allow)

    def test_alphabetic_segment_is_not_treated_as_an_id(self):
        # `deleteallaccounts` was normalising to `{id}`, collapsing distinct operations onto one
        # canary key -- so a canary for a harmless route unblocked a dangerous one.
        self.assertEqual(canary_check.normalise_route("/api/deleteallaccounts"),
                         "/api/deleteallaccounts")

    def test_genuine_opaque_ids_are_still_normalised(self):
        self.assertEqual(canary_check.normalise_route("/api/s/3f2504e04f8911d3"), "/api/s/{id}")

    def test_two_different_long_routes_do_not_share_a_canary(self):
        self.assertNotEqual(canary_check.normalise_route("/api/deleteallaccounts"),
                            canary_check.normalise_route("/api/listallaccounts"))


class TestNestingToolCoverage(unittest.TestCase):
    def test_send_message_is_a_nesting_tool(self):
        # A hardcoded five-tool list missed SendMessage, which is real in this harness.
        self.assertIn("SendMessage", no_nesting.NESTING_TOOLS)

    def test_task_family_is_covered(self):
        for tool in ("Task", "TaskCreate", "TaskUpdate", "TaskOutput", "TaskStop"):
            self.assertIn(tool, no_nesting.NESTING_TOOLS)


class TestRedactionGaps(unittest.TestCase):
    def test_connection_string_credentials(self):
        # No keyword nearby, so the assignment rule never saw it.
        out, found = redact.redact("DATABASE_URL=postgres://appuser:s3cretpassword@db.host/x")
        self.assertNotIn("s3cretpassword", out)
        self.assertIn("connection-string", found)

    def test_redis_url_credentials(self):
        out, _ = redact.redact("redis://:hunter2hunter2@cache.host:6379/0")
        self.assertNotIn("hunter2hunter2", out)

    def test_the_host_survives_so_the_finding_is_reportable(self):
        out, _ = redact.redact("postgres://appuser:s3cretpassword@db.host/x")
        self.assertIn("db.host", out)


class TestReportFailsClosed(unittest.TestCase):
    """The claim "unverified findings never reach the client body" was FALSE.

    `classify()` computed "is this above Low?" from the raw severity string, so an unrecognised
    value skipped the verification gate entirely and landed in the report -- and in the tier-1
    "Where to start" list.
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        (self.root / "scope.yaml").write_text(
            "engagement_id: t\nclient: {name: C, contact: c@example.invalid}\n"
            "authorization: {document: a.pdf, signed_by: S, signed_date: 2020-01-01,\n"
            "  window_start: 2020-01-01, window_end: 2099-12-31}\n"
            "mode: audit\nceiling: 2\n"
            'in_scope: [{asset_type: WILDCARD, pattern: "*.example.invalid"}]\n'
            "constraints: {no_destructive: true}\n", encoding="utf-8")
        for sub in ("assets", "ledger", "findings", "evidence", "deliverables"):
            (self.root / sub).mkdir()
        (self.root / "evidence" / "e.http").write_text("GET /\n\n200 OK\n", encoding="utf-8")

    def record(self, **overrides) -> dict:
        base = {"id": "F-001", "title": "SHOULD NOT APPEAR", "finding_class": "technical",
                "status": "SPECULATED", "verified": "none", "confidence": "confirmed",
                "severity": "high", "evidence_ptr": "evidence/e.http",
                "real_world_impact": "total compromise", "remediation": "x", "tested_at_tier": 1}
        base.update(overrides)
        return base

    def body(self, records: list[dict]) -> str:
        (self.root / "findings" / "p.json").write_text(json.dumps(records), encoding="utf-8")
        return report.render(self.root, 1).split("## What we checked")[0]

    def test_unrecognised_severity_does_not_reach_the_body(self):
        self.assertNotIn("SHOULD NOT APPEAR", self.body([self.record(severity="Critical!!")]))

    def test_missing_severity_does_not_reach_the_body(self):
        record = self.record()
        del record["severity"]
        self.assertNotIn("SHOULD NOT APPEAR", self.body([record]))

    def test_unrecognised_severity_does_not_reach_where_to_start(self):
        (self.root / "findings" / "p.json").write_text(
            json.dumps([self.record(severity="Critical!!")]), encoding="utf-8")
        text = report.render(self.root, 1)
        if "Where to start" in text:
            self.assertNotIn("SHOULD NOT APPEAR", text.split("Where to start")[1])

    def test_unknown_severity_is_treated_as_needing_verification(self):
        # Fails closed: an unknown severity is not evidence that a finding is low-severity.
        self.assertTrue(report.needs_verification({"finding_class": "technical",
                                                   "severity": "Critical!!"}))
        self.assertTrue(report.needs_verification({"finding_class": "technical"}))

    def test_malformed_record_is_excluded_not_merely_flagged(self):
        record = self.record(severity="high", verified="replayed", status="PROVEN")
        del record["title"]
        (self.root / "findings" / "p.json").write_text(json.dumps([record]), encoding="utf-8")
        buckets = report.classify([record], self.root)
        self.assertIn(record, buckets["invalid"])

    def test_a_valid_verified_finding_still_reaches_the_body(self):
        # The fix must not swing to excluding everything.
        good = self.record(title="LEGITIMATE FINDING", status="PROVEN", verified="replayed")
        self.assertIn("LEGITIMATE FINDING", self.body([good]))


class TestFrameworkCanRunItself(unittest.TestCase):
    """Round 2, framing F3: "these controls fight each other".

    A hardening pass widened `SCRIPT_EXEC_RE` to deny locally-invoked scripts and `INDIRECTION_RE`
    to deny `$VAR`. Collateral: the framework denied its own documented commands -- including
    `rate_probe.sh`, the sanctioned burst path the loop guard explicitly points operators at.
    **A control that blocks the safe path pushes the operator toward the unsafe one.**
    """

    def allowed(self, command: str):
        try:
            scope_guard.extract_hosts("Bash", {"command": command})
        except scope_guard.Undeterminable as exc:
            self.fail(f"framework command denied: {command}\n  -> {exc}")

    def denied(self, command: str):
        with self.assertRaises(scope_guard.Undeterminable, msg=f"should be denied: {command}"):
            scope_guard.extract_hosts("Bash", {"command": command})

    def test_sanctioned_burst_path_is_not_denied_by_the_scope_guard(self):
        self.allowed('bash "${CLAUDE_PLUGIN_ROOT}/scripts/rate_probe.sh" '
                     "--url https://app.example.invalid/x --gate-ref G-002")

    def test_documented_scope_cli_invocation_is_not_denied(self):
        # `httpx` appearing only as a signal-source citation flipped `touches_network`.
        self.allowed('/usr/bin/python3 "${CLAUDE_PLUGIN_ROOT}/scripts/scope_cli.py" --root . '
                     "add-candidate api.acme.example --signal 'CONTENT_FP:bundle@httpx'")

    def test_documented_tool_invocations_are_not_denied(self):
        for script in ("baseline_scan.py --root .", "report.py --root . --tier 1",
                       "regen_status.py --root .", "validate_findings.py --path ."):
            with self.subTest(script=script):
                self.allowed(f'/usr/bin/python3 "${{CLAUDE_PLUGIN_ROOT}}/scripts/{script}"')

    def test_every_documented_command_is_runnable(self):
        """Parse shell blocks out of commands/*.md; none may be denied by our own guard."""
        import re as _re
        for path in sorted((REPO / "commands").glob("*.md")):
            for block in _re.findall(r"```sh\n(.*?)```", path.read_text(), _re.S):
                for line in block.splitlines():
                    line = line.strip().rstrip("\\")
                    if not line or line.startswith("#") or line.startswith("RG="):
                        continue
                    if "scripts/" not in line:
                        continue
                    with self.subTest(file=path.name, line=line[:60]):
                        self.allowed(line)

    def test_allowlist_is_exactly_what_was_reviewed(self):
        """The allowlist is safe ONLY because each script enforces the boundary itself.

        Add a network-capable script without its own check and the allowlist becomes the hole.
        This is the tripwire: it fails the moment the set changes.
        """
        self.assertEqual(
            scope_guard.FRAMEWORK_SCRIPTS,
            {"rate_probe.sh", "baseline_scan.py", "scope_cli.py", "new_engagement.py",
             "regen_status.py", "report.py", "validate_findings.py", "validate_agents.py",
             "verify_controls.py"},
            "allowlist changed -- prove the new script enforces the boundary, then update this "
            "test deliberately",
        )

    def _probe_scope(self, root: Path):
        (root / "scope.yaml").write_text(
            "engagement_id: rp\nclient: {name: C, contact: c@example.invalid}\n"
            "authorization: {document: a.pdf, signed_by: S, signed_date: 2020-01-01,\n"
            "  window_start: 2020-01-01, window_end: 2099-12-31}\n"
            "mode: audit\nceiling: 2\n"
            'in_scope: [{asset_type: WILDCARD, pattern: "*.example.invalid"}]\n'
            "constraints: {no_destructive: true, max_requests_per_burst: 10}\n",
            encoding="utf-8")

    def _run_probe(self, root: Path, url: str):
        import subprocess as _sp
        return _sp.run(["bash", str(REPO / "scripts" / "rate_probe.sh"), "--root", str(root),
                        "--url", url, "--gate-ref", "G-002"],
                       capture_output=True, text=True, timeout=90)

    def test_rate_probe_refuses_a_destination_outside_the_boundary(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._probe_scope(root)
            proc = self._run_probe(root, "https://evil.example.com/")
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("outside the authorization boundary", proc.stderr)
            self.assertFalse((root / "ledger" / "activity.jsonl").exists(),
                             "must refuse BEFORE logging a plan or firing anything")

    def test_rate_probe_refuses_an_unauthorised_port(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            self._probe_scope(root)
            proc = self._run_probe(root, "http://app.example.invalid:3003/")
            self.assertNotEqual(proc.returncode, 0)
            self.assertIn("port 3003 is not", proc.stderr)

    # --- the exemptions must stay narrow ---------------------------------------------------

    def test_a_lookalike_script_elsewhere_is_still_denied(self):
        self.denied("bash /tmp/evil/rate_probe.sh --url https://evil.example.com/")

    def test_an_arbitrary_local_script_is_still_denied(self):
        self.denied("./my-probe.sh --target https://evil.example.com/")

    def test_a_safe_path_variable_inside_a_url_is_still_undeterminable(self):
        self.denied("curl https://$HOME/api")
        self.denied("curl https://${CLAUDE_PLUGIN_ROOT}/api")

    def test_command_substitution_is_still_denied(self):
        self.denied("curl https://$(cat /tmp/h)/x")

    def test_an_unknown_variable_is_still_denied(self):
        self.denied("curl https://x.example.invalid/$SECRET_PATH")


class TestPunycodeNormalisation(unittest.TestCase):
    """`normalise_host` must fold unicode and punycode spellings of the same hostname to the
    same string. Before the fix, an `out_of_scope` entry written in one form was silently
    bypassed by addressing the identical machine in the other form -- and an `in_scope` entry
    likewise failed to authorise its own unicode/punycode twin."""

    UNICODE_HOST = "café.example.invalid"

    def puny(self, host: str) -> str:
        return host.encode("idna").decode("ascii")

    def test_wildcard_entry_in_punycode_matches_unicode_target(self):
        entry = scope_mod.AssetEntry("WILDCARD", "*." + self.puny(self.UNICODE_HOST))
        self.assertTrue(scope_guard.entry_matches_host(entry, self.UNICODE_HOST))

    def test_wildcard_entry_in_unicode_matches_punycode_target(self):
        entry = scope_mod.AssetEntry("WILDCARD", "*." + self.UNICODE_HOST)
        self.assertTrue(scope_guard.entry_matches_host(entry, self.puny(self.UNICODE_HOST)))

    def test_url_entry_in_punycode_matches_unicode_target(self):
        entry = scope_mod.AssetEntry("URL", "https://" + self.puny(self.UNICODE_HOST) + "/")
        self.assertTrue(scope_guard.entry_matches_host(entry, self.UNICODE_HOST))

    def test_url_entry_in_unicode_matches_punycode_target(self):
        entry = scope_mod.AssetEntry("URL", "https://" + self.UNICODE_HOST + "/")
        self.assertTrue(scope_guard.entry_matches_host(entry, self.puny(self.UNICODE_HOST)))

    def test_ascii_host_is_unchanged(self):
        self.assertEqual(scope_guard.normalise_host("app.example.invalid"), "app.example.invalid")

    def test_trailing_dot_and_uppercase_are_folded(self):
        self.assertEqual(scope_guard.normalise_host("APP.Example.Invalid."), "app.example.invalid")

    def test_host_that_cannot_be_idna_encoded_does_not_raise(self):
        # 70 repeated non-ASCII characters overflow a single IDNA label ("label too long"),
        # which raises UnicodeEncodeError from host.encode("idna"). normalise_host must catch
        # this and return a value rather than propagating -- a control that crashes on a weird
        # hostname fails open on the crash path, defeating "every failure path denies".
        hostile = "é" * 70 + ".example.invalid"
        try:
            result = scope_guard.normalise_host(hostile)
        except (UnicodeError, ValueError) as exc:  # pragma: no cover - documents the failure
            self.fail(f"normalise_host raised on an unencodable host: {exc}")
        self.assertIsInstance(result, str)


class ValidateFindingsHookHarness(unittest.TestCase):
    """Shared fixture for driving validate_findings.py the way the wired SubagentStop hook does:
    over stdin, as a subprocess, so a crash shows up as a traceback on stderr rather than being
    swallowed by calling functions in-process."""

    SCOPE = (
        "engagement_id: vf-test\n"
        "client: {name: C, contact: c@example.invalid}\n"
        "authorization:\n"
        "  document: a.pdf\n"
        "  signed_by: S\n"
        "  signed_date: 2020-01-01\n"
        "  window_start: 2020-01-01\n"
        "  window_end: 2099-12-31\n"
        "mode: audit\n"
        "ceiling: 2\n"
        'in_scope:\n  - {asset_type: WILDCARD, pattern: "*.example.invalid"}\n'
        "constraints: {no_destructive: true}\n"
    )

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        (self.root / "scope.yaml").write_text(self.SCOPE, encoding="utf-8")
        for sub in ("assets", "ledger", "findings", "evidence", "deliverables"):
            (self.root / sub).mkdir()

    def run_hook(self) -> subprocess.CompletedProcess:
        payload = json.dumps({"cwd": str(self.root)})
        return subprocess.run(
            [sys.executable, str(REPO / "scripts" / "validate_findings.py")],
            input=payload, capture_output=True, text=True, timeout=30,
        )

    def assert_survives(self, proc: subprocess.CompletedProcess):
        self.assertIn(proc.returncode, (0, 2),
                      f"validate_findings must exit 0 or 2, got {proc.returncode}\n"
                      f"stderr: {proc.stderr}")
        self.assertNotIn("Traceback (most recent call last)", proc.stderr,
                         f"validate_findings crashed instead of failing cleanly:\n{proc.stderr}")


class TestValidateFindingsSurvivesInvalidUtf8(ValidateFindingsHookHarness):
    def test_invalid_utf8_bytes_do_not_crash_the_hook(self):
        (self.root / "findings" / "bad.json").write_bytes(b"\xff\xfe not valid utf-8 or json")
        self.assert_survives(self.run_hook())


class TestValidateFindingsSurvivesReadOnlyDirectory(ValidateFindingsHookHarness):
    def test_read_only_findings_directory_does_not_crash_the_hook(self):
        record = {
            "id": "F-001", "title": "t", "finding_class": "technical", "status": "PROVEN",
            "verified": "replayed", "confidence": "confirmed", "severity": "high",
            "evidence_ptr": "evidence/missing.http", "real_world_impact": "x",
            "remediation": "x", "tested_at_tier": 1,
        }
        (self.root / "findings" / "p.json").write_text(json.dumps([record]), encoding="utf-8")
        findings_dir = self.root / "findings"
        findings_dir.chmod(0o500)

        def restore():
            findings_dir.chmod(0o700)

        self.addCleanup(restore)
        self.assert_survives(self.run_hook())


class TestCommandLengthBound(unittest.TestCase):
    """The host regexes go quadratic on near-miss garbage, and a PreToolUse hook that times out
    fails open. MAX_ANALYSABLE_COMMAND denies rather than scans an oversized command -- the fix
    only works if that denial happens fast, so this test times it.

    Building the oversized fixture FROM the live constant (`"x" * MAX_ANALYSABLE_COMMAND`) proves
    a bound exists but not that it is set to a sane value -- whatever the constant is mutated to,
    a fixture derived from it is bigger by construction and the tests still pass. The two tests
    below instead pin the constant's *value* directly, and time a fixture of a hardcoded size that
    does not move when the constant does.
    """

    def test_constant_is_within_a_sane_range(self):
        # Lower bound: too small and ordinary long commands (a big curl payload, a long argument
        # list) get denied as "undeterminable" even though they are perfectly analysable in
        # bounded time -- the guard becomes a nuisance the operator works around.
        # Upper bound: too large and the quadratic host-regex work becomes reachable within a
        # command size a hook will actually see, reintroducing the timeout-fails-open risk this
        # bound exists to prevent (measured ~2s at 24KB, ~13s at 60KB, past the 30s hook timeout
        # around 91KB). 32768 stays comfortably below that cliff.
        self.assertGreaterEqual(scope_guard.MAX_ANALYSABLE_COMMAND, 1024,
                                "bound is too small for legitimate long commands")
        self.assertLessEqual(scope_guard.MAX_ANALYSABLE_COMMAND, 32768,
                             "bound is large enough to reintroduce the quadratic-regex timeout "
                             "this control exists to prevent")

    def test_oversized_command_is_denied(self):
        command = "curl https://a.example.invalid/" + ("x" * scope_guard.MAX_ANALYSABLE_COMMAND)
        with self.assertRaises(scope_guard.Undeterminable):
            scope_guard.extract_hosts("Bash", {"command": command})

    def test_normal_length_command_is_unaffected(self):
        found = scope_guard.extract_hosts("Bash", {"command": "curl https://a.example.invalid/"})
        self.assertIn(("a.example.invalid", 443), found)

    def test_fixed_size_near_miss_garbage_stays_fast(self):
        # A HARDCODED 64KB fixture -- not derived from MAX_ANALYSABLE_COMMAND -- of hostname-shaped
        # text that never quite completes a match (long runs of "a-a-a-a." never resolved by a
        # trailing bare label). This is the shape that makes BARE_HOST_RE/BARE_HOST_PORT_RE go
        # quadratic.
        #
        # With the real bound (8192) the length check denies this before the regexes ever run --
        # microseconds. If MAX_ANALYSABLE_COMMAND is raised past ~65KB (e.g. mutated to 1000000),
        # the length check no longer fires at this fixed size and the quadratic regex actually
        # runs against it, which measured 17s+ locally -- more than 10x the 1s budget asserted
        # here. Because the fixture size is fixed, raising the constant is what makes this test do
        # (and fail) the quadratic work; it does not scale away with the mutation the way a
        # constant-derived fixture would.
        fragment = "a-a-a-a-a-a-a-a-a-a-a-a-a-a-a-a."
        repeats = 65536 // len(fragment) + 1
        garbage = (fragment * repeats)[:65536]
        command = "curl " + garbage

        start = time.perf_counter()
        try:
            scope_guard.extract_hosts("Bash", {"command": command})
        except scope_guard.Undeterminable:
            pass
        elapsed = time.perf_counter() - start

        self.assertLess(elapsed, 1.0,
                        f"64KB near-miss-garbage command took {elapsed:.3f}s to resolve -- the "
                        "quadratic host regex ran instead of being short-circuited by the length "
                        "bound. Either MAX_ANALYSABLE_COMMAND has been raised past this fixture's "
                        "size, or the regex itself has regressed.")


class TestWraparoundTestingWindow(unittest.TestCase):
    """A window crossing midnight ("daily 22:00-06:00 UTC") previously evaluated
    `start <= now < end` even when start > end, which is false at every hour of the day --
    denying testing 24/7 while the config looked perfectly valid."""

    def _utc(self, iso: str) -> _dt.datetime:
        return _dt.datetime.fromisoformat(iso).replace(tzinfo=_dt.timezone.utc)

    def test_inside_window_before_midnight(self):
        self.assertTrue(
            scope_guard.within_testing_window("daily 22:00-06:00 UTC", self._utc("2026-08-05T23:00")))

    def test_inside_window_after_midnight(self):
        self.assertTrue(
            scope_guard.within_testing_window("daily 22:00-06:00 UTC", self._utc("2026-08-05T02:00")))

    def test_outside_window_in_the_middle_of_the_day(self):
        self.assertFalse(
            scope_guard.within_testing_window("daily 22:00-06:00 UTC", self._utc("2026-08-05T12:00")))

    def test_start_minute_is_inclusive_and_end_minute_is_exclusive(self):
        # Non-wraparound window, to pin down the boundary semantics the wraparound branch must
        # also respect.
        self.assertTrue(
            scope_guard.within_testing_window("daily 09:00-17:00 UTC", self._utc("2026-08-05T09:00")))
        self.assertFalse(
            scope_guard.within_testing_window("daily 09:00-17:00 UTC", self._utc("2026-08-05T17:00")))

    def test_weekdays_still_excludes_weekends_when_the_window_wraps(self):
        # 2026-08-08 is a Saturday.
        self.assertFalse(
            scope_guard.within_testing_window("weekdays 22:00-06:00 UTC", self._utc("2026-08-08T23:00")))
        # 2026-08-05 is a Wednesday.
        self.assertTrue(
            scope_guard.within_testing_window("weekdays 22:00-06:00 UTC", self._utc("2026-08-05T23:00")))


class TestMalformedJsonlRowsDoNotCrashReaders(unittest.TestCase):
    """A valid JSON line that is not an object (a bare string, a bare list) used to crash both
    readers via unguarded `.get()`/attribute access. `regen_status.read_jsonl` now skips such
    rows; `scope_cli.read_jsonl` now raises a clear `ScopeCliError` instead of an
    AttributeError/TypeError."""

    SCOPE = (
        "engagement_id: jsonl-test\n"
        "client: {name: C, contact: c@example.invalid}\n"
        "authorization:\n"
        "  document: a.pdf\n"
        "  signed_by: S\n"
        "  signed_date: 2020-01-01\n"
        "  window_start: 2020-01-01\n"
        "  window_end: 2099-12-31\n"
        "mode: audit\n"
        "ceiling: 2\n"
        'in_scope:\n  - {asset_type: WILDCARD, pattern: "*.example.invalid"}\n'
        "constraints: {no_destructive: true}\n"
    )

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        (self.root / "scope.yaml").write_text(self.SCOPE, encoding="utf-8")
        for sub in ("assets", "ledger", "findings", "evidence"):
            (self.root / sub).mkdir()

    def write_register(self, *lines: str):
        (self.root / "assets" / "register.jsonl").write_text(
            "\n".join(lines) + "\n", encoding="utf-8")

    def test_regen_status_read_jsonl_skips_a_bare_string_row(self):
        self.write_register(
            '"just a string"',
            json.dumps({"asset_id": "A-1", "identifier": "app.example.invalid", "status": "CONFIRMED"}),
        )
        rows = regen_status.read_jsonl(self.root / "assets" / "register.jsonl")
        self.assertEqual(rows, [{"asset_id": "A-1", "identifier": "app.example.invalid",
                                 "status": "CONFIRMED"}])

    def test_regen_status_read_jsonl_skips_a_bare_list_row(self):
        self.write_register("[1, 2]")
        self.assertEqual(regen_status.read_jsonl(self.root / "assets" / "register.jsonl"), [])

    def test_regen_status_render_still_produces_output_with_a_malformed_row_present(self):
        self.write_register(
            '"just a string"',
            json.dumps({"asset_id": "A-1", "identifier": "app.example.invalid", "status": "CONFIRMED"}),
        )
        text = regen_status.render(self.root)
        self.assertIn("jsonl-test", text)
        self.assertIn("app.example.invalid", text)

    def test_scope_cli_read_jsonl_raises_a_clear_error_on_a_bare_string_row(self):
        path = self.root / "assets" / "register.jsonl"
        path.write_text('"just a string"\n', encoding="utf-8")
        with self.assertRaises(scope_cli.ScopeCliError):
            scope_cli.read_jsonl(path)

    def test_scope_cli_read_jsonl_raises_a_clear_error_on_a_bare_list_row(self):
        path = self.root / "assets" / "register.jsonl"
        path.write_text("[1, 2]\n", encoding="utf-8")
        with self.assertRaises(scope_cli.ScopeCliError):
            scope_cli.read_jsonl(path)


class TestRedactionCountsReplacements(unittest.TestCase):
    """`redact()` used to report the number of distinct credential *classes* found, not the
    number of values redacted -- "1 credential" when fifty were removed. `found` must contain
    one entry per replacement; only the display layer (the hook's additionalContext message)
    should dedupe, and only for the list of classes, never for the count."""

    def test_n_distinct_secrets_of_the_same_class_reports_n(self):
        keys = [f"sk_live_{'A' * 8}{i:08d}" for i in range(5)]
        text = " ".join(f"STRIPE_KEY_{i}={key}" for i, key in enumerate(keys))
        _, found = redact.redact(text)
        self.assertEqual(found.count("stripe-secret"), 5)
        self.assertEqual(len(found), 5)

    def test_the_text_is_fully_redacted(self):
        keys = [f"sk_live_{'A' * 8}{i:08d}" for i in range(5)]
        text = " ".join(keys)
        out, _ = redact.redact(text)
        for key in keys:
            self.assertNotIn(key, out)

    def test_hook_additional_context_lists_each_class_once_but_counts_in_full(self):
        keys = [f"sk_live_{'A' * 8}{i:08d}" for i in range(5)]
        text = " ".join(keys)

        proc = subprocess.run(
            [sys.executable, str(REPO / "scripts" / "redact.py")],
            input=json.dumps({"tool_response": {"output": text}}),
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(proc.returncode, 0)
        payload = json.loads(proc.stdout)
        context = payload["hookSpecificOutput"]["additionalContext"]
        self.assertIn("removed 5 credential value(s)", context)
        # The class name appears exactly once in the message, despite five values of that class.
        self.assertEqual(context.count("stripe-secret"), 1)


if __name__ == "__main__":
    unittest.main()
