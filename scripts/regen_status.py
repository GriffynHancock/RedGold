#!/usr/bin/env python3
"""regen_status.py -- regenerate status.md from the ledgers and findings (spec §7.2).

Build order step 9.

Acceptance criterion (§17.2): "`status.md` regenerates identically from ledger + findings."

WHY status.md IS DERIVED AND NOT WRITTEN
----------------------------------------
A hand-maintained status file drifts, and it drifts *toward optimism* -- the finding that turned
out to be wrong stays listed, the cleanup debt quietly stops being mentioned, the phase marked
"in progress" was abandoned. A previous engagement's status file recorded gate approvals in prose,
disconnected from the findings they authorised.

So nothing writes `status.md`. It is a projection of the ledgers, the findings and the register,
and if it says something those files do not, the file is wrong and regenerating fixes it.

**Determinism is the whole contract.** No `now()` anywhere in the output: the "as of" timestamp is
the latest event in the ledgers, not the moment the script ran. Everything is sorted. Running this
twice against unchanged inputs must produce byte-identical output, or the file cannot be diffed
and the guarantee is worthless.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import findings as findings_mod  # noqa: E402
import scope as scope_mod  # noqa: E402

MAX_LISTED_FINDINGS = 20
MAX_LISTED_ASSETS = 15

PHASES = [
    ("Scope agreed (Gate 0)", "scope.amend", "boundary committed"),
    ("Test plan approved (Gate 1)", "gate.approve", "plan approved"),
    ("Recon", "asset.candidate", "assets discovered"),
    ("Assets confirmed", "asset.promote", "assets promoted"),
    ("Active testing", "rate_probe.result", "bursts run"),
]


def read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                parsed = json.loads(line)
            except json.JSONDecodeError:
                continue
            # A valid JSON line that is not an object is not a record. Skipping it beats
            # crashing on `.get` later -- scope_guard already survives this input, and a
            # reader that dies on a half-written ledger is a reader that stops the engagement.
            if isinstance(parsed, dict):
                rows.append(parsed)
    return rows


def all_findings(root: Path) -> list[dict]:
    records: list[dict] = []
    directory = root / "findings"
    if not directory.is_dir():
        return records
    for path in sorted(directory.glob("*.json")):
        loaded, _ = findings_mod.load_records(path)
        records.extend(r for r in loaded if isinstance(r, dict))
    return records


def severity_rank(value: str) -> int:
    try:
        return findings_mod.SEVERITIES.index(str(value).lower())
    except ValueError:
        return -1


# --------------------------------------------------------------------------------------------
# The coverage gap, counted once (RG-1 §4.1, §4.1b).
#
# Two reasons a check did not run, and they say opposite things to a client: a service nobody
# could probe is an *unassessed service*; a check that is structurally meaningless against this
# origin is not a gap at all. This file and `report.py` used to decide that by opposite rules and
# could disagree by twelve on the same corpus, always in the flattering direction here. They now
# share these two definitions, so there is one rule and no drift to keep in step.
#
# The allow-list is on the *inapplicable* side on purpose. An unrecognised reason has to fall
# into the disclosing bucket: "we do not know why this check did not run" is a coverage gap, and
# resolving it the other way is how a gap disappears by being misspelt.
# --------------------------------------------------------------------------------------------

INAPPLICABLE_REASONS = frozenset({"scheme_inapplicable"})


def coverage_gap_size(record: dict) -> int:
    """How many checks this record stands for. One collapsed record can stand for many (§4.1b).

    `isinstance(True, int)` is True in Python, so the bool guard is not decoration: a JSON `true`
    in `checks_skipped` is malformed input, not one check, and both readers must agree on that.
    """
    count = record.get("checks_skipped")
    if isinstance(count, bool) or not isinstance(count, int) or count <= 0:
        return 1
    return count


def render(root: Path) -> str:
    boundary = scope_mod.load(root / "scope.yaml")
    register = read_jsonl(root / "assets" / "register.jsonl")
    candidates = read_jsonl(root / "assets" / "candidates.jsonl")
    activity = read_jsonl(root / "ledger" / "activity.jsonl")
    gates = read_jsonl(root / "ledger" / "gates.jsonl")
    cleanup = read_jsonl(root / "ledger" / "cleanup.jsonl")
    blockers = read_jsonl(root / "ledger" / "blockers.jsonl")
    records = all_findings(root)

    events = Counter(r.get("event_type") for r in activity + gates)
    timestamps = sorted(str(r.get("ts")) for r in activity + gates + cleanup + blockers
                        if r.get("ts"))
    as_of = timestamps[-1] if timestamps else "no recorded activity"

    out: list[str] = []
    add = out.append

    add(f"# status.md -- {boundary.engagement_id}")
    add("")
    add("*Generated by `regen_status.py` from the ledgers, findings and register.*")
    add("**Do not hand-edit.** Anything written here by hand is lost on the next regeneration,")
    add("and a hand-maintained status file drifts toward optimism.")
    add("")
    add(f"As of the latest recorded event: `{as_of}`")
    add("")

    add("## Phase")
    add("")
    add("| Phase | State | Evidence |")
    add("|---|---|---|")
    for label, event, noun in PHASES:
        count = events.get(event, 0)
        state = "**done**" if count else "not started"
        detail = f"{count} {noun}" if count else "-"
        add(f"| {label} | {state} | {detail} |")
    add(f"| Verification | {'**done**' if any(r.get('verified') in findings_mod.VERIFIED_STRONG for r in records) else 'not started'} | "
        f"{sum(1 for r in records if r.get('verified') in findings_mod.VERIFIED_STRONG)} findings re-executed |")
    add("")

    add("## Boundary")
    add("")
    add(f"- Mode `{boundary.mode}`, ceiling {boundary.ceiling}")
    add(f"- Window {boundary.authorization.window_start} to {boundary.authorization.window_end}")
    add(f"- Authorised by {boundary.authorization.signed_by} on {boundary.authorization.signed_date}")
    add("")
    for entry in boundary.in_scope:
        add(f"  - in scope: `{entry.asset_type}:{entry.pattern}`")
    for entry in boundary.out_of_scope:
        note = f" -- {entry.note}" if entry.note else ""
        add(f"  - OUT of scope: `{entry.asset_type}:{entry.pattern}`{note}")
    add("")

    add("## Assets")
    add("")
    add(f"- CONFIRMED: {len(register)}")
    for row in sorted(register, key=lambda r: str(r.get("asset_id")))[:MAX_LISTED_ASSETS]:
        add(f"  - `{row.get('asset_id')}` {row.get('identifier')}")
    if len(register) > MAX_LISTED_ASSETS:
        add(f"  - ... and {len(register) - MAX_LISTED_ASSETS} more in assets/register.jsonl")
    add(f"- CANDIDATE (untestable above tier 1): {len(candidates)}")
    for row in sorted(candidates, key=lambda r: str(r.get("asset_id")))[:MAX_LISTED_ASSETS]:
        add(f"  - `{row.get('asset_id')}` {row.get('identifier')}")
    if len(candidates) > MAX_LISTED_ASSETS:
        add(f"  - ... and {len(candidates) - MAX_LISTED_ASSETS} more in assets/candidates.jsonl")
    add("")

    add("## Findings")
    add("")
    if not records:
        add("None recorded.")
    else:
        # "absent" was checked and was not there; "not_applicable" was never checked at all.
        # Neither is a finding, and the second one must not be counted as one.
        non_findings = {"absent", "not_applicable"}
        by_severity = Counter(str(r.get("severity", "unknown")).lower() for r in records
                              if r.get("result") not in non_findings)
        add("| Severity | Count |")
        add("|---|---|")
        for level in reversed(findings_mod.SEVERITIES):
            if by_severity.get(level):
                add(f"| {level} | {by_severity[level]} |")
        add("")
        present = [r for r in records if r.get("result") not in non_findings]
        ordered = sorted(present, key=lambda r: (-severity_rank(r.get("severity", "")),
                                                 str(r.get("id"))))
        # Capped deliberately. A neighbouring project's orchestrator was instructed to read its
        # status file in full at every session start, and by then it was 1,652 lines -- burning a
        # large fraction of the context window before any work began, which their own audit named
        # as the precondition for observed model degradation. This file is current-truth and must
        # stay small enough to read; the findings themselves are the detail store.
        for record in ordered[:MAX_LISTED_FINDINGS]:
            verified = record.get("verified", "none")
            flag = "" if verified in findings_mod.VERIFIED_STRONG or verified == "n/a" \
                else "  **UNVERIFIED**"
            add(f"- `{record.get('id')}` [{record.get('severity')}] {record.get('title')}"
                f" ({record.get('status')}/{verified}){flag}")
        if len(ordered) > MAX_LISTED_FINDINGS:
            add(f"- ... and {len(ordered) - MAX_LISTED_FINDINGS} more, by descending severity, "
                "in `findings/`. This list is capped on purpose: status.md is read at every "
                "session start and must stay cheap to read.")
        checked = sum(1 for r in records if r.get("result") == "absent")
        if checked:
            add("")
            add(f"Additionally {checked} checks ran and found nothing. Recorded deliberately: "
                "a report that omits what it did not find overstates its own assurance.")
        # One record can stand for many checks (RG-1 §4.1b), so the honest number is the sum of
        # `checks_skipped`, never the record count. And a check that is structurally inapplicable
        # here is not an unassessed service.
        #
        # The allow-list is on the *inapplicable* bucket, and everything else is a gap -- the
        # disclosing direction, and the same rule `report.py` applies. This file used to
        # allow-list the *gap* bucket instead, so any `not_applicable_reason` it did not
        # recognise vanished: one typo, or one future third reason, and status.md -- the file
        # CLAUDE.md calls authoritative and the operator reads at every session start -- reported
        # zero unassessed services while the client report reported twelve. It failed open in the
        # flattering direction, which is the drift this whole file exists to prevent
        # (adversarial review, S8). One rule, imported, so the two cannot disagree again.
        gaps = [r for r in records if r.get("result") == "not_applicable"
                and r.get("not_applicable_reason") not in INAPPLICABLE_REASONS]
        untested = sum(coverage_gap_size(r) for r in gaps)
        if untested:
            unassessed = sorted({str(r.get("asset")) for r in gaps})
            add("")
            add(f"{untested} checks did NOT run against {', '.join(unassessed)}. Those services "
                "are unassessed, not clean.")
    add("")

    add("## Cleanup debt")
    add("")
    states = Counter(str(r.get("state")) for r in cleanup)
    pending = states.get("pending", 0)
    orphaned = states.get("orphaned", 0)
    if not cleanup:
        add("Nothing written yet.")
    else:
        add(f"- deleted: {states.get('deleted', 0)}")
        add(f"- pending: {pending}")
        add(f"- orphaned: {orphaned}")
    if pending or orphaned:
        add("")
        add(f"**The engagement does not close with {pending + orphaned} item(s) outstanding.**")
    add("")

    add("## Blockers")
    add("")
    open_blockers = [b for b in blockers if not b.get("resolved")]
    if not open_blockers:
        add("None.")
    else:
        for blocker in open_blockers:
            add(f"- [{blocker.get('kind')}] {blocker.get('reason')}")
    add("")

    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Regenerate status.md from the ledgers.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if the file on disk differs from what would be generated")
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    try:
        generated = render(root)
    except scope_mod.ScopeError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1

    target = root / "status.md"
    if args.check:
        current = target.read_text(encoding="utf-8") if target.is_file() else ""
        if current != generated:
            print("status.md is stale or hand-edited; run regen_status.py", file=sys.stderr)
            return 1
        print("status.md is current.")
        return 0

    target.write_text(generated, encoding="utf-8")
    print(f"Regenerated {target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
