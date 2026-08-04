#!/usr/bin/env python3
"""gate_cli.py -- the /rg:gate command (spec §9.3.2, §9.7).

Build order steps 3-4, the piece the earlier stub deferred.

WHY THIS EXISTS
----------------
`canary_check.py` permits a tier-2 write on one of two roads: a canary proven deleted, or the
operation named in `ledger/plan.json` as client pre-approved. Nothing produced `plan.json` --
`/rg:gate` was an explicit NOT IMPLEMENTED stub -- so path (b) was unreachable by any documented
route on a target where anonymous callers cannot delete their own rows (the framework's own core
client segment). This module is what makes path (b) real: writing the plan, recording the
operator's approval, and letting other scripts (`canary_check.py`, `rate_probe.sh`) check a gate
reference against it.

Gate 1 (plan approval) and Gate 2 (deviation resolution) both land in `ledger/gates.jsonl`, per
§9.7. `check_gate()` at the bottom is the validation helper other scripts import: it answers
whether a gate reference exists, was approved, and whether its `plan_hash`/`scope_hash` still
match the files on disk. An amended scope or an edited plan voids the approval (§9.7) -- the two
hashes are how that rule is enforced rather than assumed.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scope as scope_mod  # noqa: E402

PLAN_PATH = "ledger/plan.json"
GATES_LEDGER = "ledger/gates.jsonl"
BLOCKERS_LEDGER = "ledger/blockers.jsonl"


class GateCliError(Exception):
    """Refusal. Always actionable."""


def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


# --------------------------------------------------------------------------------------------
# Ledger I/O -- same shape as scope_cli.py, deliberately.
# --------------------------------------------------------------------------------------------


def read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            parsed = json.loads(line)
        except json.JSONDecodeError as exc:
            raise GateCliError(f"{path}:{lineno} is not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise GateCliError(f"{path}:{lineno} is valid JSON but not an object")
        rows.append(parsed)
    return rows


def write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


def append_ledger(root: Path, name: str, row: dict) -> None:
    path = root / "ledger" / name
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row) + "\n")


# --------------------------------------------------------------------------------------------
# Hashing -- plan_hash and scope_hash, the §9.7 staleness check.
# --------------------------------------------------------------------------------------------


def canonical_plan_bytes(plan: dict) -> bytes:
    """A stable serialisation so re-approving after a whitespace-only edit is not required, but
    any content change (a route, a max_writes budget, a phase) changes the hash."""
    return json.dumps(plan, sort_keys=True, separators=(",", ":")).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def plan_hash_of(plan_path: Path) -> str:
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    return "sha256:" + sha256_hex(canonical_plan_bytes(plan))


def scope_hash_of(scope_path: Path) -> str:
    return "sha256:" + sha256_hex(scope_path.read_bytes())


# --------------------------------------------------------------------------------------------
# Plan loading / write-endpoint parsing
# --------------------------------------------------------------------------------------------


def load_plan(root: Path) -> dict:
    path = root / PLAN_PATH
    if not path.is_file():
        raise GateCliError(
            "no ledger/plan.json exists. Write one first: 'gate_cli.py plan --phase ... "
            "--asset ... --max-tier ...'."
        )
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise GateCliError(f"ledger/plan.json is not valid JSON: {exc}") from exc


def parse_write_endpoint(raw: str) -> dict:
    """'METHOD:/route/template[:operation][:max_writes]' -> the dict canary_check.py reads.

    canary_check.plan_preapproval() matches a write against {method, route_template, operation}
    and reads an integer max_writes budget -- this is the one place that shape is produced.
    """
    parts = raw.split(":")
    if len(parts) < 2:
        raise GateCliError(
            f"--write-endpoint {raw!r} must be at least 'METHOD:/route/template'"
        )
    method = parts[0].strip().upper()
    route = parts[1].strip()
    if not route.startswith("/"):
        raise GateCliError(f"--write-endpoint {raw!r}: route template {route!r} must start with '/'")
    operation: str | None = None
    max_writes = 1

    rest = parts[2:]
    if len(rest) == 1:
        # Ambiguous third field: a bare integer is max_writes, anything else is an operation name.
        if rest[0].strip().isdigit():
            max_writes = int(rest[0].strip())
        elif rest[0].strip():
            operation = rest[0].strip()
    elif len(rest) >= 2:
        operation = rest[0].strip() or None
        budget = rest[1].strip()
        if not budget.isdigit():
            raise GateCliError(f"--write-endpoint {raw!r}: max_writes {budget!r} is not an integer")
        max_writes = int(budget)

    if max_writes < 1:
        raise GateCliError(f"--write-endpoint {raw!r}: max_writes must be at least 1")

    return {"method": method, "route_template": route, "operation": operation, "max_writes": max_writes}


# --------------------------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------------------------


def cmd_plan(root: Path, args) -> int:
    if not (root / "scope.yaml").is_file():
        raise GateCliError(f"no scope.yaml in {root}. Run this inside an engagement directory.")
    boundary = scope_mod.load(root / "scope.yaml")

    max_tier = args.max_tier if args.max_tier is not None else boundary.ceiling
    if max_tier > boundary.ceiling:
        raise GateCliError(
            f"--max-tier {max_tier} exceeds the engagement ceiling of {boundary.ceiling} set in "
            "scope.yaml. A plan may not authorise testing above the ceiling the client agreed."
        )

    register = read_jsonl(root / "assets" / "register.jsonl")
    confirmed = {
        str(r.get("asset_id")): r for r in register if r.get("status") == "CONFIRMED"
    }
    confirmed_by_identifier = {
        str(r.get("identifier")): r for r in register if r.get("status") == "CONFIRMED"
    }
    for asset in args.asset or []:
        if asset not in confirmed and asset not in confirmed_by_identifier:
            raise GateCliError(
                f"asset {asset!r} is not CONFIRMED in assets/register.jsonl. A plan can only name "
                f"assets already promoted. Promote it first: '/rg:scope promote {asset} --confirm' "
                "(or the appropriate identifier), or check the spelling."
            )

    write_endpoints = [parse_write_endpoint(w) for w in (args.write_endpoint or [])]

    plan = {
        "plan_id": args.plan_id or "PL-001",
        "created_ts": now(),
        "phase": args.phase,
        "assets": list(args.asset or []),
        "max_tier": max_tier,
        "test_classes": list(args.test_class or []),
        "write_endpoints": write_endpoints,
        "live_confirm": list(args.live_confirm or []),
        "expected_cleanup": args.expected_cleanup,
    }

    plan_path = root / PLAN_PATH
    plan_path.parent.mkdir(parents=True, exist_ok=True)
    plan_path.write_text(json.dumps(plan, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    append_ledger(root, "activity.jsonl", {
        "ts": now(), "event_type": "plan.write", "decision": "allow",
        "reason": f"plan written for phase {args.phase}, max_tier {max_tier}",
    })

    print(f"Wrote {PLAN_PATH} for phase {args.phase!r}")
    print(f"  assets         : {', '.join(plan['assets']) or '(none)'}")
    print(f"  max_tier       : {max_tier}")
    print(f"  test_classes   : {', '.join(plan['test_classes']) or '(none)'}")
    print(f"  write_endpoints: {len(write_endpoints)}")
    for w in write_endpoints:
        op = f" op={w['operation']}" if w["operation"] else ""
        print(f"    {w['method']} {w['route_template']}{op} max_writes={w['max_writes']}")
    print("\nNOT yet approved. Run 'gate_cli.py approve' to authorise it (Gate 1, §9.7).")
    return 0


def cmd_show(root: Path, args) -> int:
    plan_path = root / PLAN_PATH
    if not plan_path.is_file():
        print("no plan exists. Write one with 'gate_cli.py plan ...'.")
        return 0
    plan = json.loads(plan_path.read_text(encoding="utf-8"))
    print(json.dumps(plan, indent=2, sort_keys=True))

    gate_id = latest_approval_id(root, plan)
    if gate_id is None:
        print("\napproval state: NOT APPROVED")
        return 0

    ok, reason = check_gate(root, gate_id)
    if ok:
        print(f"\napproval state: APPROVED as {gate_id}")
    else:
        print(f"\napproval state: {gate_id} exists but is INVALID -- {reason}")
    return 0


def latest_approval_id(root: Path, plan: dict) -> str | None:
    """The most recent gate.approve row, regardless of whether it is still valid for this plan."""
    rows = read_jsonl(root / "ledger" / GATES_LEDGER.split("/")[-1])
    approvals = [r for r in rows if r.get("event_type") == "gate.approve"]
    if not approvals:
        return None
    return approvals[-1].get("id")


def next_gate_id(root: Path) -> str:
    rows = read_jsonl(root / "ledger" / GATES_LEDGER.split("/")[-1])
    highest = 0
    for row in rows:
        rid = str(row.get("id", ""))
        if rid.startswith("G-") and rid[2:].isdigit():
            highest = max(highest, int(rid[2:]))
    return f"G-{highest + 1:03d}"


def cmd_approve(root: Path, args) -> int:
    plan_path = root / PLAN_PATH
    if not plan_path.is_file():
        raise GateCliError(
            "no ledger/plan.json exists -- nothing to approve. Write a plan first: "
            "'gate_cli.py plan --phase ... --asset ... --max-tier ...'."
        )
    scope_path = root / "scope.yaml"
    if not scope_path.is_file():
        raise GateCliError(f"no scope.yaml in {root}. Run this inside an engagement directory.")

    gate_id = next_gate_id(root)
    row = {
        "id": gate_id,
        "gate": 1,
        "event_type": "gate.approve",
        "decision": "approved",
        "plan_hash": plan_hash_of(plan_path),
        "scope_hash": scope_hash_of(scope_path),
        "approved_by": args.by,
        "rationale": args.reason,
        "ts": now(),
    }
    append_ledger(root, GATES_LEDGER.split("/")[-1], row)
    print(f"Approved as {gate_id}")
    print(f"  plan_hash  : {row['plan_hash']}")
    print(f"  scope_hash : {row['scope_hash']}")
    print(f"\nCite this in rate_probe.sh and other tier-2 calls: --gate-ref {gate_id}")
    return 0


def cmd_blockers(root: Path, args) -> int:
    rows = read_jsonl(root / "ledger" / BLOCKERS_LEDGER.split("/")[-1])
    unresolved = [r for r in rows if r.get("resolved") is None]
    if not unresolved:
        print("no unresolved blockers")
        return 0
    for i, row in enumerate(unresolved, 1):
        print(f"[{i}] {row.get('id', '?')} kind={row.get('kind', '?')} "
              f"raised_by={row.get('raised_by', '?')}")
        print(f"    {row.get('detail', '')}")
    return 0


def cmd_resolve(root: Path, args) -> int:
    rows = read_jsonl(root / "ledger" / BLOCKERS_LEDGER.split("/")[-1])
    unresolved = [r for r in rows if r.get("resolved") is None]
    if not unresolved:
        raise GateCliError("no unresolved blockers to resolve")

    target = None
    if args.blocker.isdigit():
        idx = int(args.blocker)
        if 1 <= idx <= len(unresolved):
            target = unresolved[idx - 1]
    if target is None:
        target = next((r for r in unresolved if r.get("id") == args.blocker), None)
    if target is None:
        raise GateCliError(
            f"{args.blocker!r} does not match an unresolved blocker's index or id. "
            "Run 'gate_cli.py blockers' to list them."
        )

    resolved_ts = now()
    target["resolved"] = resolved_ts
    target["resolution"] = f"{args.decision}: {args.reason}"
    write_jsonl(root / "ledger" / BLOCKERS_LEDGER.split("/")[-1], rows)

    gate_id = next_gate_id(root)
    append_ledger(root, GATES_LEDGER.split("/")[-1], {
        "id": gate_id,
        "gate": 2,
        "event_type": "gate.resolve",
        "decision": args.decision,
        "blocker_id": target.get("id"),
        "reason": args.reason,
        "resolved_by": args.by,
        "ts": resolved_ts,
    })
    print(f"Blocker {target.get('id')} resolved: {args.decision} -- {args.reason}")
    print(f"Recorded as {gate_id} in ledger/gates.jsonl")
    return 0


def cmd_validate(root: Path, args) -> int:
    ok, reason = check_gate(root, args.gate_ref)
    if ok:
        print(f"{args.gate_ref}: valid")
        return 0
    print(f"REFUSED: {reason}", file=sys.stderr)
    return 1


# --------------------------------------------------------------------------------------------
# check_gate() -- the validation helper other scripts import (canary_check.py, rate_probe.sh via
# 'gate_cli.py validate'). Given an engagement root and a gate reference, answers whether it
# exists, was approved, and whether plan_hash/scope_hash still match the files on disk.
# --------------------------------------------------------------------------------------------


def check_gate(root: Path, gate_ref: str) -> tuple[bool, str]:
    """(exists and approved and fresh, reason-if-not).

    An amended scope or an edited plan voids the approval (§9.7): both are re-hashed here and
    compared against what was true when the gate was approved.
    """
    try:
        rows = read_jsonl(root / "ledger" / GATES_LEDGER.split("/")[-1])
    except GateCliError as exc:
        return False, str(exc)

    approvals = [r for r in rows if r.get("id") == gate_ref and r.get("event_type") == "gate.approve"]
    if not approvals:
        return False, f"gate {gate_ref!r} does not exist (no gate.approve row with that id) in ledger/gates.jsonl"
    approval = approvals[-1]

    plan_path = root / PLAN_PATH
    scope_path = root / "scope.yaml"
    if not plan_path.is_file():
        return False, f"gate {gate_ref} was approved but ledger/plan.json no longer exists"
    if not scope_path.is_file():
        return False, f"gate {gate_ref} was approved but scope.yaml no longer exists"

    try:
        current_plan_hash = plan_hash_of(plan_path)
    except json.JSONDecodeError as exc:
        return False, f"ledger/plan.json is not valid JSON: {exc}"
    current_scope_hash = scope_hash_of(scope_path)

    if approval.get("plan_hash") != current_plan_hash:
        return False, (
            f"gate {gate_ref} is stale: ledger/plan.json has been edited since approval and its "
            "plan_hash no longer matches. An edited plan voids its approval (§9.7) -- re-run "
            "'gate_cli.py approve'."
        )
    if approval.get("scope_hash") != current_scope_hash:
        return False, (
            f"gate {gate_ref} is stale: scope.yaml has changed since approval and its scope_hash "
            "no longer matches. An amended scope voids every gate approval derived from it (§9.7) "
            "-- re-run 'gate_cli.py approve'."
        )
    return True, ""


# --------------------------------------------------------------------------------------------
# CLI wiring
# --------------------------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rg-gate", description="Present and approve the phase plan (Gate 1/2, §9.7).")
    p.add_argument("--root", default=".", help="engagement directory")
    sub = p.add_subparsers(dest="command", required=True)

    plan = sub.add_parser("plan", help="write ledger/plan.json for operator approval")
    plan.add_argument("--phase", required=True)
    plan.add_argument("--asset", action="append", metavar="ASSET_ID", help="repeatable")
    plan.add_argument("--max-tier", type=int, default=None)
    plan.add_argument("--test-class", action="append", metavar="CLASS", help="repeatable")
    plan.add_argument("--write-endpoint", action="append",
                      metavar="METHOD:/route/template[:operation][:max_writes]", help="repeatable")
    plan.add_argument("--live-confirm", action="append", metavar="CLASS", help="repeatable")
    plan.add_argument("--expected-cleanup", default=None)
    plan.add_argument("--plan-id", default=None)

    sub.add_parser("show", help="print the current plan and its approval state")

    approve = sub.add_parser("approve", help="record operator approval of the current plan (Gate 1)")
    approve.add_argument("--by", default="operator")
    approve.add_argument("--reason", default=None)

    sub.add_parser("blockers", help="list unresolved Gate 2 deviations")

    resolve = sub.add_parser("resolve", help="record the operator's decision on a blocker (Gate 2)")
    resolve.add_argument("blocker", metavar="index-or-id")
    resolve.add_argument("--decision", required=True, choices=["allow", "deny"])
    resolve.add_argument("--reason", required=True)
    resolve.add_argument("--by", default="operator")

    validate = sub.add_parser("validate", help="check a gate reference (used by rate_probe.sh)")
    validate.add_argument("--gate-ref", required=True)

    return p


COMMANDS = {
    "plan": cmd_plan, "show": cmd_show, "approve": cmd_approve,
    "blockers": cmd_blockers, "resolve": cmd_resolve, "validate": cmd_validate,
}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    try:
        if args.command != "validate" and not (root / "scope.yaml").is_file():
            raise GateCliError(f"no scope.yaml in {root}. Run this inside an engagement directory.")
        return COMMANDS[args.command](root, args)
    except (GateCliError, scope_mod.ScopeError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
