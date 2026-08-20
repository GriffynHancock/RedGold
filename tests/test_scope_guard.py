"""Acceptance tests for build order step 3.

Acceptance criterion (§17.2): "Denies an out-of-scope host, a ceiling violation, a base64-obfuscated
target, and an undeterminable host -- proven by unit tests over recorded stdin JSON."

The four required denials are marked ACCEPTANCE below. Everything else is supporting coverage,
including a class that asserts the control's *known blind spots* so they cannot be quietly
reclassified as covered.

    /usr/bin/python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import datetime as _dt
import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import scope as scope_mod  # noqa: E402
import scope_guard  # noqa: E402

GUARD = REPO / "scripts" / "scope_guard.py"
PAYLOADS = REPO / "tests" / "fixtures" / "hook-payloads"
ENGAGEMENT = REPO / "tests" / "fixtures" / "engagement"

# The guard now appends a decision row to <root>/ledger/activity.jsonl (RG-2 §5). Running the
# recorded payloads against the checked-in fixture directory would therefore write into the repo
# on every test run, so every subprocess run is pointed at a throwaway copy instead. The payload's
# `cwd` is rewritten rather than RG_ENGAGEMENT_ROOT being set, so find_engagement_root's directory
# walk stays exercised -- it is part of what these tests cover.
_SHARED: tempfile.TemporaryDirectory | None = None
_SHARED_ROOT: Path | None = None


def setUpModule() -> None:
    global _SHARED, _SHARED_ROOT
    _SHARED = tempfile.TemporaryDirectory()
    _SHARED_ROOT = engagement_copy(Path(_SHARED.name))


def tearDownModule() -> None:
    if _SHARED is not None:
        _SHARED.cleanup()


def engagement_copy(parent: Path) -> Path:
    dst = parent / "engagement"
    shutil.copytree(ENGAGEMENT, dst)
    return dst


def payload_for(payload_name: str, root: Path) -> str:
    payload = json.loads((PAYLOADS / f"{payload_name}.json").read_text(encoding="utf-8"))
    payload["cwd"] = str(root)
    return json.dumps(payload)


def run_guard_at(root: Path, payload_name: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(GUARD)],
        input=payload_for(payload_name, root),
        capture_output=True,
        text=True,
        timeout=30,
    )


def read_activity(root: Path) -> list[dict]:
    path = root / "ledger" / "activity.jsonl"
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def run_guard(payload_name: str) -> tuple[int, dict | None]:
    """Run the hook exactly as Claude Code would: JSON on stdin, decision on stdout."""
    assert _SHARED_ROOT is not None
    proc = run_guard_at(_SHARED_ROOT, payload_name)
    out = proc.stdout.strip()
    return proc.returncode, (json.loads(out) if out else None)


def deny_reason(result: dict | None) -> str:
    assert result is not None, "expected a decision, got silence (which means ALLOW)"
    hook = result["hookSpecificOutput"]
    assert hook["hookEventName"] == "PreToolUse"
    assert hook["permissionDecision"] == "deny"
    return hook["permissionDecisionReason"].lower()


class TestAcceptanceDenials(unittest.TestCase):
    """The four denials §17.2 step 3 requires, each over a recorded stdin payload."""

    def test_acceptance_denies_out_of_scope_host(self):
        code, result = run_guard("deny-out-of-scope-host")
        self.assertEqual(code, 0)
        self.assertIn("out of scope", deny_reason(result))
        self.assertIn("evil.example.com", deny_reason(result))

    def test_acceptance_denies_ceiling_violation(self):
        # sqlmap is tier 3; the engagement is mode 'audit', ceiling 2.
        code, result = run_guard("deny-ceiling-tier3")
        self.assertEqual(code, 0)
        reason = deny_reason(result)
        self.assertIn("ceiling", reason)
        self.assertIn("tier 3", reason)

    def test_acceptance_denies_base64_obfuscated_target(self):
        # The literal target is in scope; an out-of-scope host is hidden in a base64 header value.
        code, result = run_guard("deny-base64-obfuscated")
        self.assertEqual(code, 0)
        self.assertIn("evil.example.com", deny_reason(result))

    def test_acceptance_denies_undeterminable_host(self):
        code, result = run_guard("deny-undeterminable-variable")
        self.assertEqual(code, 0)
        self.assertIn("undeterminable target", deny_reason(result))


class TestAlwaysExitsZero(unittest.TestCase):
    """Denial rides on the JSON body, not the exit code. A non-zero exit is a different signal."""

    def test_every_payload_exits_zero(self):
        for path in sorted(PAYLOADS.glob("*.json")):
            with self.subTest(payload=path.stem):
                code, _ = run_guard(path.stem)
                self.assertEqual(code, 0)


class TestAllows(unittest.TestCase):
    """Silence is allow. The guard subtracts permission; it never grants it."""

    def test_in_scope_confirmed_read_is_silent(self):
        code, result = run_guard("allow-in-scope-get")
        self.assertEqual(code, 0)
        self.assertIsNone(result, "an allowed call must produce no output")

    def test_non_network_command_is_silent(self):
        _, result = run_guard("allow-non-network")
        self.assertIsNone(result)

    def test_in_scope_write_under_ceiling_is_silent(self):
        # tier 2 write, ceiling 2 -- permitted, because an audit that cannot write cannot
        # check rate limiting (§6).
        _, result = run_guard("allow-in-scope-write")
        self.assertIsNone(result)

    def test_webfetch_in_scope_is_silent(self):
        _, result = run_guard("allow-webfetch-in-scope")
        self.assertIsNone(result)

    def test_output_filename_is_not_read_as_a_host(self):
        # 'curl https://app.example.invalid/health -o out.txt' must not deny on "out.txt".
        _, result = run_guard("allow-in-scope-get")
        self.assertIsNone(result)


class TestOtherDenials(unittest.TestCase):
    def test_explicit_out_of_scope_beats_in_scope(self):
        # marketing.example.invalid is CONFIRMED and matches the in_scope wildcard, but is
        # explicitly excluded. out_of_scope wins, always (§5.1).
        _, result = run_guard("deny-explicit-out-of-scope")
        reason = deny_reason(result)
        self.assertIn("out_of_scope entry", reason)
        self.assertIn("third-party hosted", reason)

    def test_unconfirmed_asset_allows_tier_1_attribution_probe(self):
        # staging.example.invalid is a CANDIDATE inside the boundary. A tier-1 GET is permitted
        # as an attribution probe (§5.5) -- without this the invariant deadlocks, because the
        # signals that confirm an asset can only be obtained by contacting it.
        _, result = run_guard("deny-not-confirmed")
        self.assertIsNone(result)

    def test_unconfirmed_asset_denies_tier_2_write(self):
        # The carve-out buys the right to identify, never the right to test.
        _, result = run_guard("deny-not-confirmed-write")
        reason = deny_reason(result)
        self.assertIn("not confirmed", reason)
        self.assertIn("tier 2", reason)

    def test_mcp_without_target_mapping_is_denied(self):
        _, result = run_guard("deny-mcp-no-target-field")
        self.assertIn("no registered target-field mapping", deny_reason(result))

    def test_file_target_list_is_denied(self):
        _, result = run_guard("deny-undeterminable-filelist")
        self.assertIn("file this check never opens", deny_reason(result))

    def test_inline_interpreter_code_is_denied(self):
        _, result = run_guard("deny-undeterminable-inline")
        self.assertIn("inline interpreter code", deny_reason(result))

    def test_resolve_override_is_denied(self):
        _, result = run_guard("deny-resolve-override")
        self.assertIn("overrides host resolution", deny_reason(result))

    def test_webfetch_out_of_scope_is_denied(self):
        _, result = run_guard("deny-webfetch-out-of-scope")
        self.assertIn("out of scope", deny_reason(result))


class TestKnownBlindSpots(unittest.TestCase):
    """These assert what the control does NOT catch (§9.3.1).

    They exist so a documented limitation cannot drift into an assumed capability. If one of
    these starts failing because coverage improved, that is good news -- update the test and the
    client-facing claim together, never one without the other.
    """

    def test_executing_a_script_file_is_not_caught(self):
        # The inspected call is 'bash ./run_probe.sh'. Whatever the script contacts is invisible
        # to this hook. This is precisely why scope_guard is not a security boundary, and why the
        # real control must be off-host egress filtering (§9.9).
        _, result = run_guard("deny-undeterminable-script")
        self.assertIsNone(
            result,
            "if this now denies, coverage improved -- update §9.3.1 and the client claim too",
        )


class TestFailsClosed(unittest.TestCase):
    """A control that cannot evaluate must not permit."""

    def test_missing_scope_file_denies(self):
        payload = json.dumps(
            {"cwd": "/", "tool_name": "Bash", "tool_input": {"command": "curl https://x.example.invalid"}}
        )
        proc = subprocess.run(
            [sys.executable, str(GUARD)], input=payload, capture_output=True, text=True, timeout=30
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("no scope.yaml found", proc.stdout.lower())

    def test_garbage_stdin_denies_rather_than_crashing(self):
        proc = subprocess.run(
            [sys.executable, str(GUARD)], input="not json at all", capture_output=True, text=True, timeout=30
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("could not evaluate", proc.stdout.lower())

    def test_empty_stdin_denies(self):
        proc = subprocess.run(
            [sys.executable, str(GUARD)], input="", capture_output=True, text=True, timeout=30
        )
        self.assertEqual(proc.returncode, 0)
        self.assertIn("deny", proc.stdout.lower())


class TestTierClassification(unittest.TestCase):
    def test_plain_get_is_tier_1(self):
        self.assertEqual(scope_guard.classify_tier("curl -s https://a.example.invalid/"), 1)

    def test_explicit_write_method_is_tier_2(self):
        self.assertEqual(scope_guard.classify_tier("curl -X POST https://a.example.invalid/"), 2)

    def test_body_implies_a_write(self):
        self.assertEqual(scope_guard.classify_tier("curl --data 'x=1' https://a.example.invalid/"), 2)

    def test_exploitation_tool_is_tier_3(self):
        self.assertEqual(scope_guard.classify_tier("sqlmap -u https://a.example.invalid/"), 3)

    def test_load_generator_is_tier_3(self):
        self.assertEqual(scope_guard.classify_tier("ab -n 10000 https://a.example.invalid/"), 3)

    def test_nmap_brute_script_escalates_to_tier_3(self):
        self.assertEqual(
            scope_guard.classify_tier("nmap --script ssh-brute a.example.invalid"), 3
        )


class TestBoundaryMatching(unittest.TestCase):
    def test_wildcard_matches_subdomain_and_apex(self):
        e = scope_mod.AssetEntry("WILDCARD", "*.example.invalid")
        self.assertTrue(scope_guard.entry_matches_host(e, "app.example.invalid"))
        self.assertTrue(scope_guard.entry_matches_host(e, "example.invalid"))

    def test_wildcard_does_not_match_lookalike_suffix(self):
        # The classic bug: 'notexample.invalid' must not match '*.example.invalid'.
        e = scope_mod.AssetEntry("WILDCARD", "*.example.invalid")
        self.assertFalse(scope_guard.entry_matches_host(e, "notexample.invalid"))
        self.assertFalse(scope_guard.entry_matches_host(e, "example.invalid.evil.com"))

    def test_cidr_membership(self):
        e = scope_mod.AssetEntry("CIDR", "10.0.0.0/24")
        self.assertTrue(scope_guard.entry_matches_host(e, "10.0.0.7"))
        self.assertFalse(scope_guard.entry_matches_host(e, "10.0.1.7"))

    def test_supabase_project_resolves_to_managed_host(self):
        e = scope_mod.AssetEntry("SUPABASE_PROJECT", "anonprojectref00")
        self.assertTrue(scope_guard.entry_matches_host(e, "anonprojectref00.supabase.co"))
        self.assertFalse(scope_guard.entry_matches_host(e, "other.supabase.co"))

    def test_non_network_asset_types_authorise_nothing(self):
        # A GITHUB_ORG entry names no network destination and must not authorise a request.
        e = scope_mod.AssetEntry("GITHUB_ORG", "github.com/acme")
        self.assertFalse(scope_guard.entry_matches_host(e, "github.com"))


class TestPortAwareness(unittest.TestCase):
    """One hostname can serve an in-scope app and an unrelated product on another port.

    Matching on hostname alone cannot express "this host, but not that port", so a host-only
    match would silently authorise traffic to somebody else's system.
    """

    SCOPE = """
engagement_id: port-test
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
  - {asset_type: URL, pattern: "http://host.example.invalid"}
  - {asset_type: URL, pattern: "http://host.example.invalid:2368"}
out_of_scope:
  - {asset_type: URL, pattern: "http://host.example.invalid:3003", note: "unrelated product"}
constraints: {no_destructive: true}
"""

    def setUp(self):
        self.boundary = scope_mod.loads(self.SCOPE)
        self.now = _dt.datetime(2026, 8, 5, 3, 0, tzinfo=_dt.timezone.utc)

    def decide(self, command: str) -> scope_guard.Decision:
        return scope_guard.evaluate(
            {"tool_name": "Bash", "tool_input": {"command": command}},
            self.boundary,
            set(),
            self.now,
        )

    def test_default_web_ports_allowed_by_host_only_entry(self):
        self.assertTrue(self.decide("curl -s http://host.example.invalid/").allow)
        self.assertTrue(self.decide("curl -s https://host.example.invalid/").allow)

    def test_explicitly_named_port_allowed(self):
        self.assertTrue(self.decide("curl -s http://host.example.invalid:2368/ghost/").allow)

    def test_unrelated_product_on_same_host_is_denied(self):
        # The motivating case: an unrelated service bound on the same hostname, another port.
        decision = self.decide("curl -s http://host.example.invalid:3003/api/status")
        self.assertFalse(decision.allow)
        self.assertIn("3003", decision.reason)

    def test_unnamed_port_denied_even_without_an_out_of_scope_entry(self):
        # Defence by default, not by blocklist: 6379 is named nowhere, and is refused anyway.
        decision = self.decide("redis-cli -h host.example.invalid -p 6379 PING")
        self.assertFalse(decision.allow)

    def test_database_port_on_in_scope_host_is_denied(self):
        decision = self.decide("curl -s http://host.example.invalid:3306/")
        self.assertFalse(decision.allow)
        self.assertIn("port not authorised", decision.reason.lower())

    def test_denial_names_what_is_authorised(self):
        decision = self.decide("curl -s http://host.example.invalid:8025/")
        self.assertIn("80/443", decision.reason)
        self.assertIn("2368", decision.reason)

    def test_out_of_scope_port_beats_in_scope_host(self):
        decision = self.decide("curl -s http://host.example.invalid:3003/")
        self.assertIn("unrelated product", decision.reason)

    def test_port_flag_binds_to_the_host_it_was_given_with(self):
        decision = self.decide("mysql -h host.example.invalid -P 3306 -u root -e 'SELECT 1'")
        self.assertFalse(decision.allow)
        self.assertIn("3306", decision.reason)

    def test_positional_port_is_recognised(self):
        decision = self.decide("nc -vz host.example.invalid 6379")
        self.assertFalse(decision.allow)
        self.assertIn("6379", decision.reason)

    def test_port_range_is_undeterminable_not_enumerated(self):
        decision = self.decide("nmap -p- host.example.invalid")
        self.assertFalse(decision.allow)
        self.assertIn("undeterminable", decision.reason.lower())

    def test_port_list_is_undeterminable(self):
        decision = self.decide("nmap -p 80,443,3003 host.example.invalid")
        self.assertFalse(decision.allow)
        self.assertIn("undeterminable", decision.reason.lower())

    def test_port_entry_does_not_leak_to_other_ports(self):
        e = scope_mod.AssetEntry("URL", "http://host.example.invalid:2368")
        self.assertTrue(scope_guard.port_authorised(e, 2368))
        self.assertFalse(scope_guard.port_authorised(e, 443))
        self.assertFalse(scope_guard.port_authorised(e, None))


class TestTestingWindow(unittest.TestCase):
    def _utc(self, iso: str) -> _dt.datetime:
        return _dt.datetime.fromisoformat(iso).replace(tzinfo=_dt.timezone.utc)

    def test_inside_weekday_window(self):
        # 2026-08-05 is a Wednesday. 01:00 UTC = 11:00 AEST.
        self.assertTrue(
            scope_guard.within_testing_window("weekdays 09:00-17:00 AEST", self._utc("2026-08-05T01:00"))
        )

    def test_outside_weekday_window_by_hour(self):
        # 23:00 UTC Wed = 09:00 AEST Thu... use a clearly-outside time: 12:00 UTC = 22:00 AEST.
        self.assertFalse(
            scope_guard.within_testing_window("weekdays 09:00-17:00 AEST", self._utc("2026-08-05T12:00"))
        )

    def test_weekend_excluded(self):
        # 2026-08-08 is a Saturday.
        self.assertFalse(
            scope_guard.within_testing_window("weekdays 09:00-17:00 AEST", self._utc("2026-08-08T01:00"))
        )

    def test_unparseable_window_raises_rather_than_passing(self):
        with self.assertRaises(scope_guard.ScopeWindowError):
            scope_guard.within_testing_window("business hours-ish, ask me", self._utc("2026-08-05T01:00"))

    def test_unknown_timezone_raises(self):
        with self.assertRaises(scope_guard.ScopeWindowError):
            scope_guard.within_testing_window("weekdays 09:00-17:00 XYZ", self._utc("2026-08-05T01:00"))


RESOLUTION_ROWS = [
    {"host": "app.example.invalid", "ips": ["203.0.113.10", "203.0.113.11"],
     "ts": "2026-08-20T09:00:00Z", "ttl": 300, "resolver": "control-tier"},
    {"host": "marketing.example.invalid", "ips": ["198.51.100.7"],
     "ts": "2026-08-20T09:00:00Z", "ttl": 300, "resolver": "control-tier"},
]


class TestDecisionLogging(unittest.TestCase):
    """RG-2 §5 -- the guard must leave a reconcilable record of every decision.

    Until this existed, `status.md` and the README claimed out-of-scope targets were "refused by
    tooling and logged". The second half was false: no ledger row was written on allow or on deny.
    These tests are what make the claim true.

    The two constraints §5.2 names are load-bearing and each has a test below:
      1. logging an allow must not *become* an allow decision (that would auto-approve the call
         and suppress the operator's permission prompt);
      2. a ledger write failure must not fail the tool call.
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = engagement_copy(Path(self.tmp.name))

    def write_resolution(self, rows=None) -> None:
        ledger = self.root / "ledger"
        ledger.mkdir(parents=True, exist_ok=True)
        (ledger / "resolution.jsonl").write_text(
            "".join(json.dumps(r) + "\n" for r in (RESOLUTION_ROWS if rows is None else rows)),
            encoding="utf-8",
        )

    def guard(self, payload_name: str) -> subprocess.CompletedProcess:
        return run_guard_at(self.root, payload_name)

    def rows(self) -> list[dict]:
        return read_activity(self.root)

    # -- the envelope -------------------------------------------------------------------------

    def test_allow_writes_a_scope_allow_row(self):
        proc = self.guard("allow-in-scope-get")
        self.assertEqual(proc.returncode, 0)
        rows = self.rows()
        self.assertEqual(len(rows), 1, "an allowed network call must leave exactly one row")
        row = rows[0]
        self.assertEqual(row["event_type"], "scope.allow")
        self.assertEqual(row["decision"], "allow")
        self.assertEqual(row["severity"], "info")
        self.assertEqual(row["engagement_id"], "guard-test")
        self.assertEqual(row["target"]["host"], "app.example.invalid")
        self.assertEqual(row["target"]["port"], 443)
        self.assertEqual(row["target"]["asset_id"], "A-001")
        self.assertTrue(row["target"]["operation"].startswith("Bash: curl"))
        self.assertEqual(row["actor"]["session"], "test")
        self.assertEqual(row["tier"], 1)
        self.assertTrue(row["ts"].endswith("Z"))

    def test_allow_row_is_not_an_allow_decision(self):
        # §5.2.1. The whole feature is worse than nothing if logging the allow also *emits* one:
        # an explicit permissionDecision would auto-approve the call and suppress the operator's
        # prompt, turning a logging change into silent privilege escalation.
        proc = self.guard("allow-in-scope-get")
        self.assertEqual(proc.stdout.strip(), "", "an allowed call must still produce no stdout")
        self.assertNotIn("permissionDecision", proc.stdout)
        self.assertEqual(len(self.rows()), 1)

    def test_emit_stays_silent_on_allow(self):
        # Same rule at the unit level, so a future edit to emit() cannot reintroduce it.
        import io
        import contextlib
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            scope_guard.emit(scope_guard.Decision.permit())
        self.assertEqual(buf.getvalue(), "")

    def test_deny_writes_a_scope_deny_row(self):
        proc = self.guard("deny-out-of-scope-host")
        row = self.rows()[0]
        self.assertEqual(row["event_type"], "scope.deny")
        self.assertEqual(row["decision"], "deny")
        self.assertEqual(row["severity"], "high")
        self.assertIn("out of scope", row["reason"].lower())
        emitted = json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertEqual(row["reason"], emitted, "the logged reason must be the emitted reason")

    def test_undeterminable_is_its_own_event_type(self):
        # §5.1: folding it into scope.deny hides the single best metric for a degrading parser.
        self.guard("deny-undeterminable-variable")
        row = self.rows()[0]
        self.assertEqual(row["event_type"], "scope.undeterminable")
        self.assertEqual(row["decision"], "deny")

    def test_undeterminable_prefix_constant_tracks_the_emitted_reason(self):
        # The event_type split is derived from the reason prefix evaluate() writes. If someone
        # reworded that string, undeterminable denials would silently be logged as scope.deny.
        proc = self.guard("deny-undeterminable-inline")
        emitted = json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertTrue(emitted.startswith(scope_guard.UNDETERMINABLE_PREFIX))

    def test_every_row_carries_the_common_envelope_fields(self):
        self.write_resolution()
        self.guard("allow-in-scope-get")
        self.guard("deny-out-of-scope-host")
        self.assertEqual(len(self.rows()), 2)
        for row in self.rows():
            for field in ("ts", "engagement_id", "event_type", "actor", "target", "decision",
                          "reason", "tier", "gate_ref", "scope_hash", "ruleset_hash", "corr_id",
                          "severity"):
                self.assertIn(field, row)
            for field in ("asset_id", "host", "port", "resolved_ips", "operation"):
                self.assertIn(field, row["target"])

    def test_scope_hash_matches_the_scope_file(self):
        import hashlib
        self.guard("allow-in-scope-get")
        digest = hashlib.sha256((self.root / "scope.yaml").read_bytes()).hexdigest()
        self.assertEqual(self.rows()[0]["scope_hash"], "sha256:" + digest)

    def test_corr_id_is_a_ulid_and_unique_per_decision(self):
        self.guard("allow-in-scope-get")
        self.guard("allow-in-scope-get")
        ids = [r["corr_id"] for r in self.rows()]
        self.assertEqual(len(ids), 2)
        self.assertNotEqual(ids[0], ids[1])
        for value in ids:
            self.assertEqual(len(value), 26)
            self.assertTrue(set(value) <= set("0123456789ABCDEFGHJKMNPQRSTVWXYZ"), value)
        self.assertLessEqual(ids[0], ids[1], "ULIDs are time-ordered")

    def test_rows_append_rather_than_truncate(self):
        for _ in range(3):
            self.guard("deny-out-of-scope-host")
        self.assertEqual(len(self.rows()), 3)

    # -- resolved_ips (ADDITION 1) -------------------------------------------------------------

    def test_resolved_ips_are_stamped_from_the_resolution_ledger(self):
        self.write_resolution()
        self.guard("allow-in-scope-get")
        row = self.rows()[0]
        self.assertEqual(row["target"]["resolved_ips"], ["203.0.113.10", "203.0.113.11"])
        self.assertIsNone(row.get("reason_code"))

    def test_a_host_with_no_resolution_record_is_unresolved_not_guessed(self):
        self.write_resolution(rows=[])
        self.guard("allow-in-scope-get")
        row = self.rows()[0]
        self.assertEqual(row["target"]["resolved_ips"], [])
        self.assertEqual(row["reason_code"], "unresolved")

    def test_missing_resolution_ledger_is_unresolved_not_an_error(self):
        self.guard("allow-in-scope-get")
        row = self.rows()[0]
        self.assertEqual(row["target"]["resolved_ips"], [])
        self.assertEqual(row["reason_code"], "unresolved")

    def test_the_guard_never_resolves_a_host_itself(self):
        # §5.1: an in-guest lookup is both a side effect and something a poisoned resolver can
        # steer. resolved_ips comes from the control tier's record or it is empty. This is a
        # source-level assertion because the property is "no code path can do it", not "this one
        # did not".
        source = (REPO / "scripts" / "scope_guard.py").read_text(encoding="utf-8")
        for forbidden in ("getaddrinfo", "gethostbyname", "import socket", "dns.resolver"):
            self.assertNotIn(forbidden, source,
                             f"{forbidden!r} in scope_guard.py means the guard can resolve in-guest")

    # -- attribution probes (§5.3) --------------------------------------------------------------

    def test_attribution_probe_is_visible_in_the_ledger(self):
        # staging.example.invalid is a CANDIDATE inside the boundary; a tier-1 GET rides the §5.5
        # carve-out. The rate limit and evidence-discard halves are still unenforced, but the
        # carve-out is no longer invisible outside a code comment.
        self.guard("deny-not-confirmed")
        row = self.rows()[0]
        self.assertEqual(row["decision"], "allow")
        self.assertEqual(row["purpose"], "attribution")
        self.assertEqual(row["reason_code"], "attribution_probe")
        # §5.1 and §5.3 both claim `reason_code`, and they collide precisely here: an unconfirmed
        # host is the one least likely to have a resolution record. The join-integrity signal must
        # survive the collision, so it also lives in target.resolution.
        self.assertEqual(row["target"]["resolution"], "unresolved")
        self.assertEqual(row["target"]["resolved_ips"], [])

    def test_a_second_host_in_the_same_command_is_not_dropped(self):
        # §5.1's envelope assumes one destination per decision; one command can name several, and
        # a dropped host is a gateway row this side cannot be joined to.
        self.write_resolution()
        payload = {
            "session_id": "test", "cwd": str(self.root), "tool_name": "Bash",
            "tool_input": {"command": "curl -s https://api.example.invalid/a "
                                      "https://app.example.invalid/b"},
        }
        subprocess.run([sys.executable, str(GUARD)], input=json.dumps(payload),
                       capture_output=True, text=True, timeout=30)
        row = self.rows()[0]
        self.assertEqual(row["target"]["host"], "api.example.invalid")
        self.assertEqual(row["target"]["additional_hosts"], ["app.example.invalid:443"])
        # api.* has no resolution record, app.* does: a partial stamp, not a silent full one.
        self.assertEqual(row["target"]["resolution"], "partial")
        self.assertEqual(row["target"]["resolved_ips"], ["203.0.113.10", "203.0.113.11"])

    def test_ordinary_confirmed_traffic_is_not_marked_as_attribution(self):
        self.guard("allow-in-scope-get")
        self.assertIsNone(self.rows()[0].get("purpose"))

    # -- what is deliberately not logged --------------------------------------------------------

    def test_non_network_allow_writes_no_row(self):
        # `ls -la ./findings` reaches no destination. A row with no join key is noise in a log
        # whose only purpose is joining against the gateway's.
        self.guard("allow-non-network")
        self.assertEqual(self.rows(), [])

    # -- check_url, the sanctioned burst path (§5.2.4) -------------------------------------------

    def test_check_url_logs_its_decision(self):
        proc = subprocess.run(
            [sys.executable, str(GUARD), "--check-url", "https://app.example.invalid/x",
             "--root", str(self.root)],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(proc.returncode, 0)
        row = self.rows()[0]
        self.assertEqual(row["event_type"], "scope.allow")
        self.assertTrue(row["target"]["operation"].startswith("check_url:"))

    def test_check_url_denial_logs_too(self):
        proc = subprocess.run(
            [sys.executable, str(GUARD), "--check-url", "https://evil.example.com/x",
             "--root", str(self.root)],
            capture_output=True, text=True, timeout=30,
        )
        self.assertEqual(proc.returncode, 1)
        self.assertEqual(self.rows()[0]["event_type"], "scope.deny")

    # -- failure must not fail the tool call (§5.2.2) --------------------------------------------

    def _break_the_ledger(self) -> None:
        # A file where the directory must be: mkdir fails, and it fails the same way for root.
        (self.root / "ledger").write_text("not a directory\n", encoding="utf-8")

    def test_ledger_write_failure_does_not_change_an_allow(self):
        self._break_the_ledger()
        proc = self.guard("allow-in-scope-get")
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "", "a logging failure must not deny a legal call")
        self.assertIn("ledger.write_fail", proc.stderr)

    def test_ledger_write_failure_does_not_change_a_deny(self):
        self._break_the_ledger()
        proc = self.guard("deny-out-of-scope-host")
        self.assertEqual(proc.returncode, 0)
        self.assertIn("out of scope", proc.stdout.lower())
        self.assertIn("ledger.write_fail", proc.stderr)

    def test_a_corrupt_resolution_ledger_does_not_fail_the_call(self):
        ledger = self.root / "ledger"
        ledger.mkdir(parents=True, exist_ok=True)
        (ledger / "resolution.jsonl").write_text("{not json\n[]\n", encoding="utf-8")
        proc = self.guard("allow-in-scope-get")
        self.assertEqual(proc.stdout.strip(), "")
        self.assertEqual(self.rows()[0]["target"]["resolved_ips"], [])


class TestNoDecisionIsAnAllow(unittest.TestCase):
    """No payload, in any state, may make this hook grant permission."""

    def test_no_payload_ever_emits_an_allow_decision(self):
        for path in sorted(PAYLOADS.glob("*.json")):
            with self.subTest(payload=path.stem):
                _, result = run_guard(path.stem)
                if result is not None:
                    self.assertEqual(
                        result["hookSpecificOutput"]["permissionDecision"], "deny")


class TestAuthorizationWindow(unittest.TestCase):
    def test_before_window_start_denies(self):
        boundary = scope_mod.load(ENGAGEMENT / "scope.yaml")
        payload = {"tool_name": "Bash", "tool_input": {"command": "curl https://app.example.invalid/"}}
        decision = scope_guard.evaluate(
            payload,
            boundary,
            {"app.example.invalid"},
            _dt.datetime(2019, 6, 1, tzinfo=_dt.timezone.utc),
        )
        self.assertFalse(decision.allow)
        self.assertIn("outside authorization window", decision.reason.lower())


if __name__ == "__main__":
    unittest.main()
