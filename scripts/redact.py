#!/usr/bin/env python3
"""redact.py -- PostToolUse hook. Keeps credentials out of the transcript (spec §9.5).

Build order step 9 (v1 enforcement).

A security audit reads configuration for a living. On a white-box engagement the very first thing
`rg-codeaudit` opens is likely to contain live provider keys -- and everything a tool returns is
written to the transcript on disk, which then lives in the engagement directory, gets committed,
and outlasts the engagement.

**Redaction preserves the finding while destroying the secret.** "A live Resend key is present in
a dev config" is a real finding and must survive; the 36 characters after `re_` must not. So every
replacement keeps the prefix and the length:

    re_AbCdEf0123456789...  ->  re_[REDACTED-32]

That is enough to report the class of credential, prove it was real rather than a placeholder, and
tell the client which one to rotate -- without the value itself ever reaching disk.

WHAT THIS IS NOT
----------------
It is not a guarantee. A secret in a format nobody anticipated passes straight through, and a
sufficiently unusual encoding defeats any pattern list. It reduces blast radius; it does not make
handling a target's config safe. The rule that actually protects the client is still "do not
exfiltrate what you do not need".

FAILURE MODE
------------
If this hook errors it must emit nothing and exit 0, leaving the output untouched. A redactor that
crashes must not also destroy the tool output the agent was waiting on -- that would turn a
privacy control into a denial-of-service against the engagement.
"""

from __future__ import annotations

import json
import re
import sys

# Ordered: longest/most specific first, so a generic rule cannot eat a specific one's match.
PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    # PEM private keys -- whole block.
    ("private-key", re.compile(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----", re.DOTALL)),
    # JWTs (three base64url segments). Supabase service_role keys are JWTs.
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")),
    # Provider keys with a stable prefix.
    ("stripe-secret", re.compile(r"\bsk_(?:live|test)_[A-Za-z0-9]{16,}\b")),
    ("stripe-restricted", re.compile(r"\brk_(?:live|test)_[A-Za-z0-9]{16,}\b")),
    ("stripe-webhook", re.compile(r"\bwhsec_[A-Za-z0-9]{16,}\b")),
    ("resend", re.compile(r"\bre_[A-Za-z0-9_-]{16,}\b")),
    ("openai", re.compile(r"\bsk-[A-Za-z0-9]{20,}\b")),
    ("anthropic", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("aws-access-key", re.compile(r"\b(?:AKIA|ASIA)[0-9A-Z]{16}\b")),
    ("slack-token", re.compile(r"\bxox[baprs]-[A-Za-z0-9-]{10,}\b")),
    ("google-api-key", re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b")),
    ("sendgrid", re.compile(r"\bSG\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\b")),
    # Credentials embedded in a connection string: postgres://user:pass@host, redis://:pass@h.
    # These carry no keyword, so the assignment rule never saw them.
    ("connection-string", re.compile(r"(?i)\b([a-z][a-z0-9+.-]*://[^\s:/@]*:)([^\s@/]{4,})(?=@)")),
    # Bearer/Authorization headers, whatever the token shape.
    ("authorization", re.compile(r"(?i)\b(authorization\s*:\s*(?:bearer|basic)\s+)(\S{8,})")),
    ("apikey-header", re.compile(r"(?i)\b((?:x-api-key|apikey|api-key)\s*:\s*)(\S{8,})")),
    # Assignment-shaped secrets: PASSWORD=..., "secret": "...", SECRET_KEY: ...
    ("assignment", re.compile(
        r"(?i)\b([\"']?[A-Z0-9_]*(?:PASSWORD|PASSWD|SECRET|TOKEN|API_?KEY|PRIVATE_?KEY|"
        r"CREDENTIAL|ACCESS_?KEY)[A-Z0-9_]*[\"']?\s*[:=]\s*[\"']?)([^\s\"',;}\)]{6,})")),
]

# Values that are obviously not secrets. Redacting these is noise that trains people to ignore
# the marker, and it destroys legitimate findings ("the password is literally 'root'").
PLACEHOLDERS = frozenset({
    "null", "none", "nil", "true", "false", "undefined", "changeme", "password", "secret",
    "your-api-key", "xxx", "xxxx", "redacted", "example", "placeholder", "todo", "root",
})


def _mask(value: str, label: str) -> str:
    return f"[REDACTED-{label}-{len(value)}]"


def redact(text: str) -> tuple[str, list[str]]:
    """Returns (redacted text, list of credential classes found)."""
    found: list[str] = []

    for label, pattern in PATTERNS:
        if pattern.groups == 2:
            def replace(match: re.Match[str], _label: str = label) -> str:
                value = match.group(2)
                # Already handled by a more specific rule. Re-redacting would destroy the
                # credential class, which is the part that makes the finding reportable.
                if "[REDACTED-" in value:
                    return match.group(0)
                if value.strip("\"'").lower() in PLACEHOLDERS:
                    return match.group(0)
                found.append(_label)
                return match.group(1) + _mask(value, _label)
            text = pattern.sub(replace, text)
        else:
            def replace_whole(match: re.Match[str], _label: str = label) -> str:
                value = match.group(0)
                if "[REDACTED-" in value:
                    return value
                if value.lower() in PLACEHOLDERS:
                    return value
                found.append(_label)
                # Keep the prefix so the credential class stays reportable.
                prefix = value[:7] if len(value) > 12 else ""
                return f"{prefix}{_mask(value, _label)}"
            text = pattern.sub(replace_whole, text)

    # `found` is every replacement, in order. Callers that want the classes can dedupe; the
    # COUNT must be the number of values removed, or "removed 1 credential" is reported when
    # fifty thousand were.
    return text, found


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            return 0
        original = payload.get("tool_response")
        if isinstance(original, dict):
            original = original.get("output") or original.get("stdout") or ""
        if not isinstance(original, str) or not original:
            return 0

        redacted, found = redact(original)
        if not found:
            return 0
        classes = sorted(set(found))

        json.dump({
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "updatedToolOutput": redacted,
                "additionalContext": (
                    f"redact.py removed {len(found)} credential value(s) of class(es): "
                    f"{', '.join(classes)}. The presence of a real credential is itself reportable "
                    "-- record it as a finding and tell the client to rotate it. Do not attempt "
                    "to recover the value."
                ),
            }
        }, sys.stdout)
        sys.stdout.write("\n")
    except Exception:  # noqa: BLE001
        # Never destroy tool output because the redactor failed.
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
