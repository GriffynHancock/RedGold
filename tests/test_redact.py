"""Tests for redact.py (spec §9.5).

The credential shapes below are the ones the upcoming engagement will actually meet: a live
Resend key, a Stripe test key and webhook secret, Cloudflare Stream credentials, a Supabase
service_role JWT, and a database password in a compose file.

**No real credential appears in this file.** Every value is synthetic and matches only the shape.
"""

from __future__ import annotations

import json
import subprocess
import sys
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import redact  # noqa: E402

HOOK = REPO / "scripts" / "redact.py"


class TestRedaction(unittest.TestCase):
    def assertRemoved(self, text: str, secret: str, label: str | None = None):
        out, found = redact.redact(text)
        self.assertNotIn(secret, out, f"secret survived redaction: {out}")
        self.assertTrue(found, "nothing was reported as found")
        if label:
            self.assertIn(label, found)
        return out

    def test_resend_key(self):
        out = self.assertRemoved(
            'anjali.resendApiKey = "re_AbCdEf0123456789AbCdEf0123456789"',
            "re_AbCdEf0123456789AbCdEf0123456789", "resend")
        # The class survives so the finding is still reportable.
        self.assertIn("re_", out)
        self.assertIn("REDACTED", out)

    def test_stripe_test_key(self):
        self.assertRemoved("sk_test_51AbCdEfGhIjKlMnOpQrStUv",
                           "sk_test_51AbCdEfGhIjKlMnOpQrStUv", "stripe-secret")

    def test_stripe_live_key(self):
        self.assertRemoved("sk_live_51AbCdEfGhIjKlMnOpQrStUv",
                           "sk_live_51AbCdEfGhIjKlMnOpQrStUv", "stripe-secret")

    def test_stripe_webhook_secret(self):
        self.assertRemoved("whsec_AbCdEf0123456789AbCdEf01",
                           "whsec_AbCdEf0123456789AbCdEf01", "stripe-webhook")

    def test_service_role_jwt(self):
        jwt = ("eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
               "eyJyb2xlIjoic2VydmljZV9yb2xlIiwiaWF0IjoxfQ."
               "AbCdEfGhIjKlMnOpQrStUvWxYz012345")
        self.assertRemoved(f"SUPABASE_SERVICE_KEY={jwt}", jwt, "jwt")

    def test_authorization_header(self):
        out = self.assertRemoved(
            "Authorization: Bearer AbCdEf0123456789AbCdEf0123456789",
            "AbCdEf0123456789AbCdEf0123456789")
        self.assertIn("Authorization: Bearer", out, "the header name must survive")

    def test_password_assignment(self):
        self.assertRemoved('MYSQL_ROOT_PASSWORD="s3cr3t-actual-value"',
                           "s3cr3t-actual-value", "assignment")

    def test_json_secret_field(self):
        self.assertRemoved('{"apiToken": "AbCdEf0123456789AbCdEf0123456789"}',
                           "AbCdEf0123456789AbCdEf0123456789")

    def test_private_key_block(self):
        pem = ("-----BEGIN RSA PRIVATE KEY-----\n"
               "MIIEpAIBAAKCAQEA0123456789abcdef\n"
               "-----END RSA PRIVATE KEY-----")
        self.assertRemoved(pem, "MIIEpAIBAAKCAQEA0123456789abcdef", "private-key")

    def test_github_token(self):
        self.assertRemoved("ghp_AbCdEf0123456789AbCdEf0123456789Ab",
                           "ghp_AbCdEf0123456789AbCdEf0123456789Ab", "github-token")

    def test_aws_access_key(self):
        self.assertRemoved("AKIAIOSFODNN7EXAMPLE", "AKIAIOSFODNN7EXAMPLE", "aws-access-key")

    def test_multiple_secrets_in_one_blob(self):
        text = ('resendApiKey="re_AbCdEf0123456789AbCdEf0123456789"\n'
                'stripeSecretKey="sk_test_51AbCdEfGhIjKlMnOpQrStUv"\n')
        out, found = redact.redact(text)
        self.assertNotIn("re_AbCdEf0123456789AbCdEf0123456789", out)
        self.assertNotIn("sk_test_51AbCdEfGhIjKlMnOpQrStUv", out)
        self.assertIn("resend", found)
        self.assertIn("stripe-secret", found)

    def test_length_is_preserved_in_the_marker(self):
        # The client needs to know a real 32-char key was there, not a placeholder.
        out, _ = redact.redact("re_AbCdEf0123456789AbCdEf0123456789")
        self.assertIn("-35]", out)


class TestItDoesNotOverreach(unittest.TestCase):
    """A redactor that fires on everything trains people to ignore the marker."""

    def assertUntouched(self, text: str):
        out, found = redact.redact(text)
        self.assertEqual(out, text, f"unexpectedly redacted: {found}")
        self.assertEqual(found, [])

    def test_ordinary_prose_is_untouched(self):
        self.assertUntouched("The login form accepts a password and returns a session cookie.")

    def test_html_and_json_without_secrets_are_untouched(self):
        self.assertUntouched('{"status":"ok","items":[{"id":1,"name":"alpha"}]}')

    def test_placeholder_values_are_not_redacted(self):
        # "the password is literally 'root'" is a finding; destroying it destroys the finding.
        out, _ = redact.redact('MYSQL_ROOT_PASSWORD="root"')
        self.assertIn("root", out)

    def test_changeme_placeholder_survives(self):
        out, _ = redact.redact("API_KEY=changeme")
        self.assertIn("changeme", out)

    def test_a_short_value_is_not_treated_as_a_secret(self):
        self.assertUntouched("TOKEN=ab")

    def test_http_response_body_is_untouched(self):
        self.assertUntouched("HTTP/1.1 200 OK\nContent-Type: application/json\n\n[]")


class TestHookBehaviour(unittest.TestCase):
    def run_hook(self, payload: dict) -> tuple[int, str]:
        proc = subprocess.run(["/usr/bin/python3", str(HOOK)], input=json.dumps(payload),
                              capture_output=True, text=True, timeout=30)
        return proc.returncode, proc.stdout

    def test_rewrites_tool_output(self):
        code, out = self.run_hook({
            "hook_event_name": "PostToolUse", "tool_name": "Bash",
            "tool_response": {"output": 'resendApiKey="re_AbCdEf0123456789AbCdEf0123456789"'}})
        self.assertEqual(code, 0)
        result = json.loads(out)["hookSpecificOutput"]
        self.assertNotIn("re_AbCdEf0123456789AbCdEf0123456789", result["updatedToolOutput"])
        self.assertIn("rotate", result["additionalContext"])

    def test_clean_output_produces_no_rewrite(self):
        code, out = self.run_hook({
            "hook_event_name": "PostToolUse", "tool_name": "Bash",
            "tool_response": {"output": "total 4\ndrwxr-xr-x 2 user user 4096 findings"}})
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "")

    def test_a_broken_payload_does_not_destroy_output(self):
        # A redactor that crashes must not also nuke the output the agent was waiting on.
        code, out = self.run_hook({"tool_response": None})
        self.assertEqual(code, 0)
        self.assertEqual(out.strip(), "")

    def test_garbage_stdin_is_survivable(self):
        proc = subprocess.run(["/usr/bin/python3", str(HOOK)], input="not json",
                              capture_output=True, text=True, timeout=30)
        self.assertEqual(proc.returncode, 0)
        self.assertEqual(proc.stdout.strip(), "")


if __name__ == "__main__":
    unittest.main()
