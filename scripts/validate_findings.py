#!/usr/bin/env python3
"""validate_findings.py -- SubagentStop hook. Findings validation (spec §9.6, §10).

Build order step 5.

WHY THE MESSAGE MATTERS MORE THAN THE EXIT CODE
-----------------------------------------------
**Exit 2 on `SubagentStop` prevents the subagent from stopping. It does not restart it.** The agent
continues from where it is, so the stderr message must be a specific correction instruction --
"record F-007 is missing evidence_ptr; capture the request/response to evidence/F-007-*.http, then
finish" -- not "invalid, try again". A vague message produces an agent thrashing against its own
broken output.

For the same reason this script counts attempts. After two failed corrections it stops blocking,
writes a `kind: validation` row to `ledger/blockers.jsonl`, and lets the agent stop -- because a
hook that blocks forever is a hung engagement, and a human needs to look at it.

AUTO-DEMOTION IS A WRITE
------------------------
An unresolvable evidence pointer demotes the record to SPECULATED (§9.6), and this script performs
that edit rather than reporting it. A warning about an unproven claim is precisely what gets
scrolled past under time pressure; a rewritten status is not.

Standalone use:
    /usr/bin/python3 scripts/validate_findings.py --path <engagement-or-file> [--no-demote]
"""

from __future__ import annotations

import argparse
import datetime as _dt
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import findings as findings_mod  # noqa: E402

MAX_CORRECTION_ATTEMPTS = 2
ATTEMPTS_FILE = "ledger/.validation_attempts.json"


def find_engagement_root(payload: dict) -> Path:
    override = os.environ.get("RG_ENGAGEMENT_ROOT")
    if override:
        return Path(override)
    start = Path(payload.get("cwd") or os.getcwd())
    for candidate in [start, *start.parents]:
        if (candidate / "scope.yaml").is_file():
            return candidate
    raise FileNotFoundError(f"no scope.yaml found at or above {start}")


def findings_files(root: Path) -> list[Path]:
    directory = root / "findings"
    if not directory.is_dir():
        return []
    return sorted(directory.glob("*.json"))


def demote_records(path: Path, root: Path) -> list[str]:
    """Rewrite PROVEN records whose evidence does not resolve. Returns demoted record ids.

    Never raises. A non-UTF-8 file or a read-only directory must not crash the hook -- an
    exception here would exit 1 with a traceback instead of the documented 0 or 2.
    """
    try:
        document = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError, json.JSONDecodeError):
        return []

    records = findings_mod.extract_records(document)
    demoted: list[str] = []
    for record in records:
        if not isinstance(record, dict):
            continue
        result = findings_mod.validate_record(record, root)
        if result.demoted and record.get("status") != "SPECULATED":
            record["status"] = "SPECULATED"
            note = record.get("validator_note") or ""
            stamp = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
            record["validator_note"] = (
                f"{note}\n[{stamp}] auto-demoted to SPECULATED: evidence pointer did not resolve."
            ).strip()
            demoted.append(str(record.get("id", "<no-id>")))

    if demoted:
        try:
            path.write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")
        except OSError:
            # Read-only engagement directory. Report the demotion rather than dying on it.
            return demoted
    return demoted


def collect(root: Path) -> tuple[list[findings_mod.RecordResult], list[str]]:
    results: list[findings_mod.RecordResult] = []
    errors: list[str] = []
    for path in findings_files(root):
        file_results, file_errors = findings_mod.validate_file(path, root)
        results.extend(file_results)
        errors.extend(file_errors)
    return results, errors


def read_attempts(root: Path) -> dict:
    path = root / ATTEMPTS_FILE
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def bump_attempts(root: Path, key: str) -> int:
    path = root / ATTEMPTS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    attempts = read_attempts(root)
    attempts[key] = attempts.get(key, 0) + 1
    path.write_text(json.dumps(attempts, indent=2) + "\n", encoding="utf-8")
    return attempts[key]


def clear_attempts(root: Path, key: str) -> None:
    attempts = read_attempts(root)
    if key in attempts:
        del attempts[key]
        (root / ATTEMPTS_FILE).write_text(json.dumps(attempts, indent=2) + "\n", encoding="utf-8")


def record_blocker(root: Path, key: str, violations: list[findings_mod.Violation]) -> None:
    path = root / "ledger" / "blockers.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds"),
        "kind": "validation",
        "actor": key,
        "reason": f"{len(violations)} findings violations survived "
                  f"{MAX_CORRECTION_ATTEMPTS} correction attempts",
        "violations": [{"record": v.record_id, "code": v.code, "message": v.message}
                       for v in violations],
    }
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


def format_correction(violations: list[findings_mod.Violation], demoted: list[str],
                      errors: list[str]) -> str:
    lines = ["Findings validation failed. Correct these specific records, then finish.", ""]
    for err in errors:
        lines.append(f"[FILE] {err}")
    for violation in violations:
        lines.append(violation.render())
    if demoted:
        lines.append("")
        lines.append(
            "Auto-demoted to SPECULATED (evidence did not resolve): " + ", ".join(demoted)
        )
    lines.append("")
    lines.append(
        "You are continuing from where you are -- you are not re-running the phase. Fix the "
        "records named above in findings/*.json, capture any missing evidence under evidence/, "
        "then stop."
    )
    return "\n".join(lines)


def run(root: Path, key: str, *, demote: bool, enforce_attempts: bool) -> tuple[int, str]:
    demoted: list[str] = []
    if demote:
        for path in findings_files(root):
            demoted.extend(demote_records(path, root))

    results, errors = collect(root)
    blocking = [v for r in results for v in r.blocking]
    advisory = [v for r in results for v in r.violations if not v.blocking]

    if not blocking and not errors:
        if enforce_attempts:
            clear_attempts(root, key)
        summary = f"{len(results)} findings validated"
        if demoted:
            summary += f"; {len(demoted)} auto-demoted ({', '.join(demoted)})"
        if advisory:
            summary += f"; {len(advisory)} advisory issues"
        return 0, summary

    if enforce_attempts:
        attempts = bump_attempts(root, key)
        if attempts > MAX_CORRECTION_ATTEMPTS:
            record_blocker(root, key, blocking)
            clear_attempts(root, key)
            return 0, (
                f"Findings still invalid after {MAX_CORRECTION_ATTEMPTS} correction attempts. "
                "Recorded a validation blocker in ledger/blockers.jsonl and allowing the stop; "
                "this needs the operator."
            )

    return 2, format_correction(blocking, demoted, errors)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Validate an engagement's findings records.")
    parser.add_argument("--path", default=None,
                        help="engagement dir or single findings file (standalone mode)")
    parser.add_argument("--no-demote", action="store_true",
                        help="report unresolvable evidence without rewriting status")
    args = parser.parse_args(argv)

    if args.path:
        target = Path(args.path).expanduser().resolve()
        if target.is_file():
            # Single-file mode used to print "an unresolvable pointer demotes this record" and
            # then not demote it -- the CLI contradicted its own output. Found by audit.
            if not args.no_demote:
                demoted = demote_records(target, target.parent)
                if demoted:
                    print(f"Auto-demoted to SPECULATED: {', '.join(demoted)}")
            results, errors = findings_mod.validate_file(target, target.parent)
            blocking = [v for r in results for v in r.blocking]
            advisory = [v for r in results for v in r.violations if not v.blocking]
            for err in errors:
                print(f"[FILE] {err}")
            for violation in blocking + advisory:
                print(violation.render())
            print(f"\n{len(results)} records, {len(blocking)} blocking, {len(advisory)} advisory")
            return 1 if (blocking or errors) else 0
        code, message = run(target, "cli", demote=not args.no_demote, enforce_attempts=False)
        print(message)
        return 0 if code == 0 else 1

    # Hook mode.
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook payload is not a JSON object")
        root = find_engagement_root(payload)
    except Exception as exc:  # noqa: BLE001
        # Unlike scope_guard, failing to validate is not a reason to block a stop forever.
        # Say so loudly on stderr and let the agent finish; a hung agent helps nobody.
        print(f"validate_findings could not run: {type(exc).__name__}: {exc}", file=sys.stderr)
        return 0

    key = str(payload.get("agent_id") or payload.get("session_id") or "unknown")
    try:
        code, message = run(root, key, demote=True, enforce_attempts=True)
    except Exception as exc:  # noqa: BLE001
        # The contract is 0 or 2. Anything else -- including a traceback -- is a defect, and
        # blocking a stop forever because the validator broke would hang the engagement.
        print(f"validate_findings failed and is allowing the stop: {type(exc).__name__}: {exc}",
              file=sys.stderr)
        return 0
    if code == 2:
        print(message, file=sys.stderr)
    return code


if __name__ == "__main__":
    raise SystemExit(main())
