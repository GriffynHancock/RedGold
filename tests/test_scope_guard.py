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
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import scope as scope_mod  # noqa: E402
import scope_guard  # noqa: E402

GUARD = REPO / "scripts" / "scope_guard.py"
PAYLOADS = REPO / "tests" / "fixtures" / "hook-payloads"
ENGAGEMENT = REPO / "tests" / "fixtures" / "engagement"


def run_guard(payload_name: str) -> tuple[int, dict | None]:
    """Run the hook exactly as Claude Code would: JSON on stdin, decision on stdout."""
    raw = (PAYLOADS / f"{payload_name}.json").read_text(encoding="utf-8")
    proc = subprocess.run(
        [sys.executable, str(GUARD)],
        input=raw,
        capture_output=True,
        text=True,
        timeout=30,
    )
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
