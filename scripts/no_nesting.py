#!/usr/bin/env python3
"""no_nesting.py -- PreToolUse hook. A worker attempting to spawn a subagent is caught LOUDLY.

Build order step 8 (spec §8.0).

**Subagents cannot spawn subagents, and the failure is silent.** Delegation fails open: no
specialised executor ever runs, and the pipeline reports success while doing nothing. For a
security tool that is the worst available failure, because the output is an empty engagement
wearing the costume of a completed one.

Silence is the problem, so this hook exists to make the attempt noisy. It denies with an
explanation, and it records the attempt to `ledger/blockers.jsonl` so it survives the session --
a denial the agent then papers over would otherwise leave no trace that a phase never ran.

The main session is not a subagent, so it is unaffected: the hook only fires when the payload
carries an `agent_id`/`agent_type`, which is present exactly when a subagent is the caller.
"""

from __future__ import annotations

import datetime as _dt
import json
import os
import sys
from pathlib import Path

# Every tool that dispatches to, or converses with, another agent or the operator. A hardcoded
# list missed `SendMessage`, which is a real tool in this harness.
NESTING_TOOLS = frozenset({
    "Agent", "Task", "TaskOutput", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "TaskStop",
    "SendMessage", "AskUserQuestion", "ExitPlanMode", "EnterPlanMode",
})


def emit_deny(reason: str) -> None:
    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }, sys.stdout)
    sys.stdout.write("\n")


def record_blocker(payload: dict, tool_name: str) -> None:
    root = os.environ.get("RG_ENGAGEMENT_ROOT")
    if not root:
        start = Path(payload.get("cwd") or os.getcwd())
        for candidate in [start, *start.parents]:
            if (candidate / "scope.yaml").is_file():
                root = str(candidate)
                break
    if not root:
        return
    path = Path(root) / "ledger" / "blockers.jsonl"
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps({
                "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
                "kind": "nesting",
                "actor": payload.get("agent_type") or payload.get("agent_id"),
                "reason": f"worker attempted to call {tool_name}; subagents cannot nest",
            }) + "\n")
    except OSError:
        pass  # never let a logging failure turn a denial into an allow


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook payload is not a JSON object")
        tool_name = payload.get("tool_name") or ""
        is_subagent = bool(payload.get("agent_id") or payload.get("agent_type"))
        if not is_subagent or tool_name not in NESTING_TOOLS:
            return 0
    except Exception as exc:  # noqa: BLE001
        emit_deny(f"DENIED (no_nesting could not evaluate this call): {type(exc).__name__}: {exc}")
        return 0

    record_blocker(payload, tool_name)
    emit_deny(
        f"DENIED (nesting): a worker attempted to call `{tool_name}`. Subagents cannot spawn "
        "subagents in this harness, and the failure is SILENT -- delegation fails open and no "
        "executor ever runs, so the phase would report success while doing nothing.\n\n"
        "This attempt has been recorded as a blocker so it is not lost. Write what you need to "
        "`ledger/blockers.jsonl` and stop; the command layer dispatches, not you."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
