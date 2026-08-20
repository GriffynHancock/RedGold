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
import canary_check  # noqa: E402  -- the consumer of write_endpoints; one source of truth
import regen_status  # noqa: E402  -- one reader for findings/*.json, not a second one here
import report  # noqa: E402  -- one implementation of the REPORT_STALE comparison, not a second

PLAN_PATH = "ledger/plan.json"
GATES_LEDGER = "ledger/gates.jsonl"
BLOCKERS_LEDGER = "ledger/blockers.jsonl"
COVERAGE_REGISTER = "coverage.jsonl"


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


WRITE_ENDPOINT_SYNTAX = "METHOD:/route/template[:label][:max_writes] (or [:label=NAME][:op=NAME][:max=N])"


def parse_write_endpoint(raw: str) -> dict:
    """'METHOD:/route/template[:label][:max_writes]' -> the dict canary_check.py reads.

    canary_check.plan_preapproval() matches a write against {method, route_template, operation}
    and reads an integer max_writes budget -- this is the one place that shape is produced, so
    the shape produced here must be the shape produced by canary_check.resolve_operation() at
    check time, not something that merely looks like it.

    `operation` is a machine identifier, not prose: `"{METHOD} {route_template}"` for a plain
    REST route, the mutation name for GraphQL. B-002: an operator following the old
    `[:operation]` syntax wrote the flow label `signup` into it, which no request can ever
    resolve to, and the pre-approved write became unperformable. The label is now kept as
    `label` (informational, ignored by the checker) and `operation` is derived.
    """
    parts = raw.split(":")
    if len(parts) < 2:
        raise GateCliError(
            f"--write-endpoint {raw!r} must be at least 'METHOD:/route/template'"
        )
    method = parts[0].strip().upper()
    route_raw = parts[1].strip()
    if not route_raw.startswith("/"):
        raise GateCliError(
            f"--write-endpoint {raw!r}: route template {route_raw!r} must start with '/'")
    # Fold path parameters exactly as the checker will, so a literal id in the plan cannot
    # produce an entry that no intercepted request can ever match.
    route = canary_check.normalise_route(route_raw)

    label: str | None = None
    op_name: str | None = None
    max_writes: int | None = None

    for field in parts[2:]:
        field = field.strip()
        if not field:
            continue
        key, sep, value = field.partition("=")
        key, value = key.strip().lower(), value.strip()
        if sep:
            if key in ("op", "operation"):
                op_name = value or None
            elif key in ("max", "max_writes"):
                if not value.isdigit():
                    raise GateCliError(
                        f"--write-endpoint {raw!r}: max_writes {value!r} is not an integer")
                max_writes = int(value)
            elif key == "label":
                label = value or None
            else:
                raise GateCliError(
                    f"--write-endpoint {raw!r}: unknown field {field!r}. Expected 'label=', "
                    f"'op=' or 'max='. Syntax: {WRITE_ENDPOINT_SYNTAX}")
        elif field.isdigit():
            if max_writes is not None:
                raise GateCliError(f"--write-endpoint {raw!r}: max_writes given twice")
            max_writes = int(field)
        elif label is None:
            label = field
        else:
            raise GateCliError(
                f"--write-endpoint {raw!r}: cannot tell what {field!r} means. Name the fields: "
                f"{WRITE_ENDPOINT_SYNTAX}")

    if max_writes is None:
        max_writes = 1
    if max_writes < 1:
        raise GateCliError(f"--write-endpoint {raw!r}: max_writes must be at least 1")

    if "graphql" in route.lower():
        # One route, many mutations. canary_check refuses to guess here and so must the plan --
        # an entry that covered the whole /graphql route would pre-approve deleteAccount along
        # with createComment.
        operation = op_name or label
        if not operation:
            raise GateCliError(
                f"--write-endpoint {raw!r}: {route} is a GraphQL endpoint, where one route serves "
                "many mutations. Name the mutation explicitly, e.g. "
                f"'{method}:{route}:op=createComment:max={max_writes}'.")
    else:
        operation = f"{method} {route}"
        if op_name and op_name != operation:
            raise GateCliError(
                f"--write-endpoint {raw!r}: op={op_name!r} cannot match anything. For a plain REST "
                f"route the operation identifier is always {operation!r} (that is what "
                "canary_check.resolve_operation() computes for an intercepted request). A "
                f"human-readable flow name goes in 'label=' instead: '{method}:{route}:"
                f"label={op_name}:max={max_writes}'.")

    return {"method": method, "route_template": route, "operation": operation,
            "label": label, "max_writes": max_writes}


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
        label = f" ({w['label']})" if w.get("label") else ""
        print(f"    {w['method']} {w['route_template']}{label} "
              f"operation={w['operation']!r} max_writes={w['max_writes']}")
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

    # RG-1 §3.1/§4.8 -- the environment gate. `environment` is a *scope fact*: it exists in
    # scope.yaml from the moment the boundary is written, which is strictly before Gate 1, so
    # there is no healthy engagement state at which this refusal fires. That is the test a
    # control's siting has to pass (§4.8), and it is why this refusal lives here while the
    # *discrepancy* between the declaration and what was later observed does not: every signal
    # that raises a discrepancy needs contact with the asset, and no contact happens until after
    # this gate approves the plan (§9.7). A check sited before its input can exist fires on 0%
    # of everything and reads as coverage.
    #
    # Refusing here rather than in `scope.parse()` is D-6: `ScopeError` is DENY-by-contract and
    # five scripts call `scope.load()`, so a parse-time failure would also block the report that
    # explains the refusal.
    boundary = scope_mod.load(scope_path)
    refusal = scope_mod.environment_refusal(boundary.environment)
    if refusal:
        raise GateCliError(refusal)

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
    row["environment"] = boundary.environment
    append_ledger(root, GATES_LEDGER.split("/")[-1], row)
    print(f"Approved as {gate_id}")
    print(f"  environment: {boundary.environment}")
    print(f"  plan_hash  : {row['plan_hash']}")
    print(f"  scope_hash : {row['scope_hash']}")
    print(f"\nCite this in rate_probe.sh and other tier-2 calls: --gate-ref {gate_id}")
    return 0


# --------------------------------------------------------------------------------------------
# Phase completion -- the zero-zero rule (RG-1 §8.2).
#
# An engagement with no findings is a possible and respectable outcome. An engagement with no
# findings AND no record of having looked is not an engagement. The prior whitebox engagement held
# the only SOURCE_CODE asset in scope and produced empty directories and 0-byte ledgers; nothing
# in the framework refused to let it quietly exist. `regen_status.py` is not the place for this --
# it would have rendered every phase "not started", correctly, and said so to nobody. The gap is
# the absence of anything that *refuses*.
# --------------------------------------------------------------------------------------------


def in_phase(row: dict, phase: "str | None") -> bool:
    """Does this artifact count as work on `phase`?

    An artifact that declares no phase counts toward whichever phase is being closed. The
    alternative -- attributing untagged records to no phase -- would make every phase unclosable
    until a `phase` field exists on every producer, and a gate that fires on healthy input is a
    gate that gets switched off.

    `phase is None` means "the whole engagement", which is what `cmd_close` asks for.
    """
    if phase is None:
        return True
    declared = row.get("phase")
    return declared is None or str(declared) == phase


# Dispositions that are neither a finding nor a clean check. The docstring below named both from
# the start; only `not_applicable` was implemented, so `not_attempted` -- "we did not look", a
# first-class disposition with its own closed reason vocabulary -- fell through the `elif` and was
# counted as a finding. A single record saying nobody probed anything closed a phase (adversarial
# review, S4).
NOT_A_FINDING_RESULTS = frozenset({"not_applicable", "not_attempted"})


def phase_evidence(root: Path, phase: "str | None") -> tuple[int, int]:
    """(findings recorded for this phase, negative results recorded for this phase).

    A negative result is an `absent` record: a check that ran and was clean. `not_applicable`
    ("structurally meaningless here") and `not_attempted` ("did not look") are neither -- counting
    them would let a phase close on 36 records proving that nobody probed anything.
    """
    finding_count = 0
    absent_count = 0

    for record in regen_status.all_findings(root):
        if not in_phase(record, phase):
            continue
        result = str(record.get("result", "")).lower()
        if result == "absent":
            absent_count += 1
        elif result not in NOT_A_FINDING_RESULTS:
            finding_count += 1

    for row in read_jsonl(root / COVERAGE_REGISTER):
        if in_phase(row, phase) and str(row.get("outcome", "")).lower() == "absent":
            absent_count += 1

    return finding_count, absent_count


def cmd_complete(root: Path, args) -> int:
    finding_count, absent_count = phase_evidence(root, args.phase)

    if not finding_count and not absent_count:
        raise GateCliError(
            f"COVERAGE_EMPTY_PHASE: phase {args.phase!r} has zero findings and zero recorded "
            "negative results, so nothing on disk distinguishes 'we looked and found nothing' "
            "from 'we did not look'. Record what was checked -- an `absent` finding record per "
            f"clean check, or an `absent` row in {COVERAGE_REGISTER} -- or re-scope the phase. "
            "An engagement with no findings is a respectable outcome; an engagement with no "
            "record of having looked is not an engagement."
        )

    append_ledger(root, "activity.jsonl", {
        "ts": now(), "event_type": "phase.complete", "decision": "allow",
        "phase": args.phase, "findings": finding_count, "negatives": absent_count,
        "reason": f"{finding_count} finding(s) and {absent_count} recorded negative(s)",
    })
    print(f"Phase {args.phase!r} complete: {finding_count} finding(s), "
          f"{absent_count} recorded negative(s).")
    return 0


# --------------------------------------------------------------------------------------------
# Engagement close -- the binding site for the two Release 1 coverage rules (RG-1 §9.1a).
#
# `report.py --check` and `complete --phase` are both opt-in. An operator who runs neither is
# stopped by nothing, and under P1 -- enforcement is mechanical, never advisory -- a control that
# depends on someone remembering is not a control.
#
# The specced remedy was hook 7, `cleanup_gate.py`, a `Stop` hook (07-enforcement.md §9.2). It does
# not work, for two independent reasons that were checked against the harness documentation rather
# than assumed. `Stop` fires *once per turn*, many times per engagement, so a refusal keyed on an
# empty corpus fires on every turn of a healthy engagement's opening phase -- the disabled-gate
# failure RG-1 §2.3 exists to prevent. And exit 2 on `Stop` "prevents Claude from stopping,
# continues the conversation": its actuator is the *model*, which cannot perform any of the
# remedies (restore a downed component, re-scope, accept a gap with a recorded decision). Those are
# the operator's. `SessionEnd` fires at the right cardinality but *cannot block* -- exit 2 there
# only prints -- and an engagement spans many sessions anyway.
#
# The general finding: **there is no Claude Code lifecycle event for "engagement close", because an
# engagement is not an object the harness knows about.** Every hook event is turn-, tool-, session-
# or subagent-scoped. So closure is made an *act* with a gate on it, rather than an absence nobody
# records. This is opt-in exactly as `approve` is opt-in -- what changes is that skipping it is now
# detectable, because an engagement with no `gate.close` row was not closed.
#
# It does not eliminate the failure. An operator who walks away is still stopped by nothing. Do not
# describe engagement close as mechanically enforced.
# --------------------------------------------------------------------------------------------


def completed_phases(root: Path) -> list[str]:
    """Phases with a recorded `phase.complete` row -- i.e. phases the zero-zero rule was run on."""
    rows = read_jsonl(root / "ledger" / "activity.jsonl")
    return [str(r.get("phase")) for r in rows if r.get("event_type") == "phase.complete"]


def close_violations(root: Path, tier: int) -> list[str]:
    """Every reason this engagement may not close, not merely the first.

    An operator who fixes one refusal and is immediately refused for a different reason learns to
    distrust the gate, and a distrusted gate gets switched off.
    """
    reasons: list[str] = []

    # C2's substance (§8.2), applied to the engagement rather than one phase.
    finding_count, absent_count = phase_evidence(root, None)
    if not finding_count and not absent_count:
        reasons.append(
            "COVERAGE_EMPTY_PHASE: this engagement has zero findings and zero recorded negative "
            "results across every phase, so nothing on disk distinguishes 'we looked and found "
            "nothing' from 'we did not look'. An engagement with no findings is a respectable "
            "outcome; an engagement with no record of having looked is not an engagement."
        )

    # C2's mechanism. The zero-zero rule only fires when someone runs `complete`; requiring at
    # least one completed phase is what turns it from opt-in into a precondition of closure.
    if not completed_phases(root):
        reasons.append(
            "PHASE_NEVER_COMPLETED: no phase has a `phase.complete` row in "
            "ledger/activity.jsonl, so the phase-completion coverage rule (RG-1 §8.2) has never "
            "been run against this engagement. Close each phase you worked: "
            "'gate_cli.py complete --phase <name>'."
        )

    # C1 (§8.6). One implementation, imported -- a second mtime comparison here would be a second
    # thing to keep in step with the first.
    deliverable = root / "deliverables" / f"report-tier{tier}.md"
    stale = report.freshness_violation(root, deliverable)
    if stale:
        reasons.append(stale)

    # Gate 1 (§9.7). An amended scope.yaml or an edited plan voids the approval -- including an
    # amendment that changes `environment` after Gate 1 approved it, which changes the cap every
    # agent-written record is scored against at report assembly (`report.classify`). `close` never
    # asked, so an engagement whose approval was voided mid-flight closed with exit 0 and a
    # `gate.close` row asserting nothing about the gate it was closed under (adversarial review,
    # S10).
    #
    # Only checked when an approval exists. `approve` is opt-in and many engagements never write
    # a plan; refusing every unapproved engagement would fire on healthy input, and a gate that
    # fires on healthy input gets switched off (§4.8). What this can honestly assert is that an
    # approval which *does* exist is still valid for the tree being closed. The residual --
    # an engagement that never approved anything closes without a gate check -- is real, and is
    # the same residual `approve` itself carries.
    approval_id = latest_approval_id(root, {})
    if approval_id is not None:
        ok, reason = check_gate(root, approval_id)
        if not ok:
            reasons.append(
                f"GATE_1_VOID: {reason} An engagement does not close under an approval that no "
                "longer holds: re-approve the current plan against the current scope "
                "('gate_cli.py approve'), or record why the amendment does not need one."
            )

    return reasons


def cmd_close(root: Path, args) -> int:
    reasons = close_violations(root, args.tier)

    if reasons:
        raise GateCliError(
            "this engagement may not close.\n\n  "
            + "\n\n  ".join(reasons)
            + "\n\nFix every item above, then re-run 'gate_cli.py close'."
        )

    gate_id = next_gate_id(root)
    append_ledger(root, GATES_LEDGER.split("/")[-1], {
        "id": gate_id,
        "gate": 1,
        "event_type": "gate.close",
        "decision": "closed",
        "phases_completed": completed_phases(root),
        "closed_by": args.by,
        "ts": now(),
    })
    print(f"Engagement closed as {gate_id}")
    print(f"  phases completed : {', '.join(completed_phases(root)) or '(none)'}")
    print(f"  deliverable      : deliverables/report-tier{args.tier}.md postdates every finding")
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
    plan.add_argument(
        "--write-endpoint", action="append",
        metavar="METHOD:/route/template[:label][:max_writes]",
        help="repeatable. Fields after the route may be named to remove any ambiguity: "
             "'label=NAME' (human-readable flow name, informational), 'max=N' (write budget, "
             "default 1), 'op=NAME' (GraphQL mutation name -- REQUIRED for a /graphql route, "
             "and not accepted for a plain REST route, whose operation identifier is always "
             "'METHOD /route/template'). Positionally, a bare integer is max_writes and any "
             "other bare value is the label. Example: "
             "'POST:/members/api/send-magic-link/:signup:2'")
    plan.add_argument("--live-confirm", action="append", metavar="CLASS", help="repeatable")
    plan.add_argument("--expected-cleanup", default=None)
    plan.add_argument("--plan-id", default=None)

    sub.add_parser("show", help="print the current plan and its approval state")

    approve = sub.add_parser("approve", help="record operator approval of the current plan (Gate 1)")
    approve.add_argument("--by", default="operator")
    approve.add_argument("--reason", default=None)

    complete = sub.add_parser(
        "complete", help="mark a phase complete; refuses a phase with no findings and no "
                         "recorded negative results (RG-1 §8.2, COVERAGE_EMPTY_PHASE)")
    complete.add_argument("--phase", required=True)

    close = sub.add_parser(
        "close", help="close the engagement; refuses on a stale deliverable, an engagement with "
                      "no record of having looked, or no completed phase (RG-1 §9.1a)")
    close.add_argument("--tier", type=int, default=1,
                       help="which deliverable to check for staleness (default 1)")
    close.add_argument("--by", default="operator")

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
    "plan": cmd_plan, "show": cmd_show, "approve": cmd_approve, "complete": cmd_complete,
    "close": cmd_close, "blockers": cmd_blockers, "resolve": cmd_resolve,
    "validate": cmd_validate,
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
