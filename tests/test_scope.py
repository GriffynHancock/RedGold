"""Acceptance tests for build order step 2.

Acceptance criterion (§17.2): "Rejects malformed scope; round-trips a real engagement
expressed as a boundary."

stdlib unittest, deliberately: these tests gate a security control and must run on a bare
interpreter without first installing a test framework.

    /usr/bin/python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import scope  # noqa: E402

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "scope-prior-engagement.yaml"


class TestRoundTrip(unittest.TestCase):
    """A real engagement expressed as a boundary survives parse -> dump -> parse unchanged."""

    def test_fixture_parses(self):
        s = scope.load(FIXTURE)
        self.assertEqual(s.engagement_id, "prior-engagement-anon")
        self.assertEqual(s.mode, "audit")
        self.assertEqual(s.ceiling, 2)
        self.assertEqual(len(s.in_scope), 2)
        self.assertEqual(len(s.out_of_scope), 1)
        self.assertEqual(s.constraints.max_requests_per_burst, 10)
        self.assertIn("user geolocation and presence data", s.crown_jewels)

    def test_round_trip_is_stable(self):
        first = scope.load(FIXTURE)
        second = scope.loads(first.dumps())
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first, second)

    def test_round_trip_is_idempotent(self):
        # A second dump must be byte-identical to the first, or "round-trips" is doing no work.
        first = scope.load(FIXTURE)
        self.assertEqual(first.dumps(), scope.loads(first.dumps()).dumps())

    def test_out_of_scope_note_survives(self):
        s = scope.load(FIXTURE)
        self.assertEqual(s.out_of_scope[0].note, "third-party hosted, not the client's")


class TestRejectsMalformed(unittest.TestCase):
    """Every rejection below is a boundary that must never load."""

    def _expect_rejected(self, text: str, needle: str):
        with self.assertRaises(scope.ScopeError) as ctx:
            scope.loads(text)
        self.assertIn(needle, str(ctx.exception).lower())

    def setUp(self):
        self.base = FIXTURE.read_text(encoding="utf-8")

    def test_not_yaml(self):
        self._expect_rejected("engagement_id: [unclosed", "not valid yaml")

    def test_not_a_mapping(self):
        self._expect_rejected("- just\n- a\n- list\n", "mapping at the top level")

    def test_empty_document(self):
        self._expect_rejected("", "mapping at the top level")

    def test_missing_engagement_id(self):
        self._expect_rejected(
            self.base.replace("engagement_id: prior-engagement-anon", ""), "engagement_id"
        )

    def test_malformed_engagement_id(self):
        self._expect_rejected(
            self.base.replace("prior-engagement-anon", "Prior Engagement 2026"), "lowercase"
        )

    def test_unknown_asset_type(self):
        self._expect_rejected(
            self.base.replace("asset_type: SUPABASE_PROJECT", "asset_type: KUBERNETES_CLUSTER"),
            "not a recognised asset type",
        )

    def test_empty_in_scope_authorises_nothing(self):
        text = self.base.replace(
            '  - {asset_type: WILDCARD, pattern: "*.example.invalid"}\n'
            '  - {asset_type: SUPABASE_PROJECT, pattern: "anonprojectref00"}\n',
            "  []\n",
        )
        self._expect_rejected(text, "at least one asset")

    def test_ceiling_may_not_exceed_mode_default(self):
        # The core §6 rule: a declared ceiling lowers, never raises.
        self._expect_rejected(self.base.replace("ceiling: 2", "ceiling: 3"), "exceeds the default ceiling")

    def test_ceiling_may_lower(self):
        s = scope.loads(self.base.replace("ceiling: 2", "ceiling: 1"))
        self.assertEqual(s.ceiling, 1)

    def test_ceiling_out_of_tier_range(self):
        self._expect_rejected(self.base.replace("ceiling: 2", "ceiling: 7"), "outside the tier range")

    def test_unknown_mode(self):
        self._expect_rejected(self.base.replace("mode: audit", "mode: pentest"), "must be one of")

    def test_posture_mode_capped_at_one(self):
        self._expect_rejected(
            self.base.replace("mode: audit", "mode: posture"), "exceeds the default ceiling"
        )

    def test_redteam_requires_emergency_contact(self):
        text = self.base.replace("mode: audit", "mode: redteam")
        self._expect_rejected(text, "emergency_contact")

    def test_redteam_with_emergency_contact_loads(self):
        text = self.base.replace("mode: audit", "mode: redteam").replace(
            "  signed_by: Anonymised Signatory",
            "  signed_by: Anonymised Signatory\n  emergency_contact: Named Person +61 400 000 000",
        )
        s = scope.loads(text)
        self.assertEqual(s.mode, "redteam")

    def test_window_end_before_start(self):
        self._expect_rejected(self.base.replace("window_end: 2026-08-03", "window_end: 2026-07-01"), "precedes")

    def test_missing_authorization_document(self):
        self._expect_rejected(
            self.base.replace("  document: ../authorization/anonymised-signed-roe.pdf\n", ""),
            "document",
        )

    def test_burst_cap_true_is_not_a_cap(self):
        # bool is a subclass of int in Python; 'true' must not silently become a cap of 1.
        self._expect_rejected(
            self.base.replace("max_requests_per_burst: 10", "max_requests_per_burst: true"),
            "positive integer",
        )

    def test_burst_cap_zero_rejected(self):
        self._expect_rejected(
            self.base.replace("max_requests_per_burst: 10", "max_requests_per_burst: 0"),
            "positive integer",
        )

    def test_missing_client_contact(self):
        self._expect_rejected(self.base.replace("  contact: founder@example.invalid\n", ""), "contact")


class TestFailureIsNotPermission(unittest.TestCase):
    """A boundary that cannot be loaded must raise, never return an empty permissive scope."""

    def test_missing_file_raises(self):
        with self.assertRaises(scope.ScopeError):
            scope.load(Path("/nonexistent/scope.yaml"))

    def test_every_failure_is_a_scope_error(self):
        # Callers enforce on `except ScopeError -> DENY`. Anything escaping that base class
        # would bypass the deny path, so assert the hierarchy explicitly.
        self.assertTrue(issubclass(scope.ScopeDependencyError, scope.ScopeError))


if __name__ == "__main__":
    unittest.main()
