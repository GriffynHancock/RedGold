#!/usr/bin/env python3
"""no_handrolled_loops.py -- PreToolUse hook. Denies hand-rolled request loops (spec §9.4).

Build order step 7.

THE INCIDENT THIS IS
--------------------
On a prior engagement an agent hand-rolled a rate-limit probe authorised for at most **ten**
requests. It sent **twenty**. The loop counted its own iterations while the body of the loop fired
two requests per pass, so a script quietly doubled its own authorised ceiling. It was caught,
logged and disclosed -- and the fix was then written into a design document and never enforced.

This is that fix as a code path. Bounded bursts go through `rate_probe.sh`, which counts dispatched
requests rather than iterations and owns its own stop condition.

WHAT COUNTS AS A LOOP
---------------------
More than `for` and `while`. The overrun did not need a loop keyword to happen, and neither do
several other ways to issue N requests from one command line:

- shell loops: `for`, `while`, `until`, `repeat`
- fan-out helpers: `xargs`, `parallel`, `seq | ...`
- brace expansion: `curl http://host/{1..20}` -- one command, twenty requests
- curl's own globbing: `curl http://host/[1-20]`
- curl's parallel mode: `-Z`, `--parallel`
- backgrounding a request with `&`

Every one of these issues an unbounded or operator-invisible number of requests, which is the
property that matters -- not the syntax.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scope_guard  # noqa: E402

# Iteration constructs. Word-boundary anchored so `formatter` is not a `for` loop.
LOOP_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("a shell for-loop", re.compile(r"(?:^|[;&|]|\s)for\s+\w+\s+in\b")),
    ("a shell while-loop", re.compile(r"(?:^|[;&|]|\s)while\b")),
    ("a shell until-loop", re.compile(r"(?:^|[;&|]|\s)until\b")),
    ("a zsh repeat-loop", re.compile(r"(?:^|[;&|]|\s)repeat\s+\d+")),
    ("xargs fan-out", re.compile(r"\bxargs\b")),
    ("GNU parallel", re.compile(r"\bparallel\b")),
    ("a seq-driven loop", re.compile(r"\bseq\b[^|;]*\|")),
    ("brace expansion", re.compile(r"\{\d+\.\.\d+\}")),
    ("curl URL globbing", re.compile(r"https?://\S*\[\d+-\d+\]")),
    ("curl parallel mode", re.compile(r"(?:^|\s)(?:-Z|--parallel)\b")),
    ("a backgrounded request", re.compile(r"&\s*$")),
    ("find -exec fan-out", re.compile(r"\bfind\b[^|;]*-exec\b")),
    ("a shell function used as a loop", re.compile(r"\b\w+\s*\(\s*\)\s*\{")),
    ("a watch loop", re.compile(r"(?:^|[;&|]|\s)watch\b")),
    ("a curl config file of URLs", re.compile(r"(?:^|\s)(?:-K|--config)\b")),
    ("a wget input file", re.compile(r"(?:^|\s)(?:-i|--input-file)\b")),
    ("recursive mirroring", re.compile(r"(?:^|\s)(?:-r|--recursive|-m|--mirror)\b")),
]

# The sanctioned path. A command that IS the rate probe is allowed through -- it owns its own
# counter, its own cap and its own stop condition.
# Must be the command being INVOKED, not merely a string appearing somewhere. Matching it
# anywhere let a real 50-iteration loop through by appending `# rate_probe.sh` as a comment.
SANCTIONED = re.compile(r"^\s*(?:bash\s+|sh\s+|/usr/bin/env\s+bash\s+)?\S*rate_probe\.sh\b")
COMMENT_RE = re.compile(r"(?<!\\)#(?=(?:[^'\"]*['\"][^'\"]*['\"])*[^'\"]*$).*$", re.MULTILINE)

# More than a handful of URLs on one command line is a burst, whatever the syntax.
MAX_URLS_PER_COMMAND = 3


def touches_network(command: str) -> bool:
    tokens = set(re.findall(r"[a-z0-9_.-]+", command.lower()))
    return bool(tokens & scope_guard.NETWORK_TOOLS) or bool(scope_guard.URL_RE.search(command))


def evaluate(command: str) -> tuple[bool, str]:
    """Returns (allow, reason-if-denied)."""
    command = COMMENT_RE.sub("", command).strip()
    if SANCTIONED.match(command):
        return True, ""
    if not touches_network(command):
        # A loop over local files is not this hook's business.
        return True, ""

    urls = scope_guard.URL_RE.findall(command)
    if len(urls) > MAX_URLS_PER_COMMAND:
        return False, (
            f"DENIED (request fan-out): this command names {len(urls)} URLs. A burst does not "
            "need a loop keyword to be a burst. Use scripts/rate_probe.sh, which counts "
            "dispatched requests against a hard cap and logs its plan before firing."
        )

    for description, pattern in LOOP_PATTERNS:
        if pattern.search(command):
            return False, (
                f"DENIED (hand-rolled request loop): this command combines {description} with a "
                "network request. On a prior engagement a hand-rolled loop authorised for 10 "
                "requests sent 20, because it counted its own iterations rather than the "
                "requests it dispatched.\n\n"
                "Use scripts/rate_probe.sh instead. It counts dispatched requests against a hard "
                "cap, stops at the first 429 or Retry-After, refuses concurrency, and logs its "
                "plan before firing. If you need a burst this does not cover, raise a deviation "
                "via /rg:gate rather than writing the loop by hand."
            )
    return True, ""


def emit_deny(reason: str) -> None:
    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }, sys.stdout)
    sys.stdout.write("\n")


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook payload is not a JSON object")
        if payload.get("tool_name") != "Bash":
            return 0
        command = (payload.get("tool_input") or {}).get("command")
        if not isinstance(command, str):
            return 0
        allow, reason = evaluate(command)
    except Exception as exc:  # noqa: BLE001 -- a crashed PreToolUse hook fails OPEN
        emit_deny(
            f"DENIED (no_handrolled_loops could not evaluate this call): {type(exc).__name__}: "
            f"{exc}. A control that cannot evaluate must not permit."
        )
        return 0

    if not allow:
        emit_deny(reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
