"""report.py -- the client deliverable (spec §10.6, §16).

Build order step 9 / `/rg:report`.

WHAT THIS REFUSES TO DO
-----------------------
The report is generated from validated findings on disk and nothing else. It cannot be talked into
including a claim, because it never sees the conversation that produced one.

- **Unverified technical findings above Low do not appear in the body.** They move to the coverage
  section as open questions. Published false-positive rates for autonomous vulnerability detection
  run 15.3-45.8% across six frontier models; on the margin an unverified finding is close to a coin
  flip, and a client cannot tell the difference by reading it.
- **A finding whose evidence pointer does not resolve is demoted, not printed.**
- **A rollup and its constituents are counted once.** Naive concatenation across phase files
  inflates the finding count, which flatters us.
- **`[VERIFY]`-marked content never reaches a client.**

WHY COVERAGE IS A SECTION AND NOT A FOOTNOTE
--------------------------------------------
Everything tested-and-clean, everything de-scoped, every unconfirmed finding, each with a
recommended next action. A report that quietly omits what it did not test overstates its own
assurance -- which is the fastest way for a solo contractor to lose a client permanently. It is
also half of what the client is paying to learn: "we tried to break this and could not" is a
result.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import findings as findings_mod  # noqa: E402
import regen_status  # noqa: E402
import scope as scope_mod  # noqa: E402

TIERS = {
    0: "Asset register and severity-ordered findings",
    1: "Tier 0, plus hardening guidance and calibrated next steps",
}

SEVERITY_BLURB = {
    "critical": "Fix before anyone else sees the product.",
    "high": "Fix this week.",
    "medium": "Fix before launch.",
    "low": "Worth doing; not urgent.",
    "info": "Informational.",
}


# Blocking defects that mean "not proven yet" rather than "malformed". These route a record to
# Open Questions; anything else routes it out of the report entirely.
VERIFICATION_CODES = frozenset({
    "PROVEN_UNVERIFIED", "UNVERIFIED_ABOVE_LOW", "NA_NOT_PERMITTED",
})


def severity_rank(value: str) -> int:
    return regen_status.severity_rank(value)


def result_codes(record: dict, root: Path) -> list:
    return findings_mod.validate_record(record, root).blocking


def needs_verification(record: dict) -> bool:
    """Does this record require independent re-execution before a client sees it?

    **Fails closed on an unrecognised or missing severity.** An unknown severity is not evidence
    that a finding is low-severity; it is evidence that we do not know, and a report is the last
    place to resolve an ambiguity in the flattering direction.
    """
    if str(record.get("finding_class", "technical")).lower() != "technical":
        return False
    severity = str(record.get("severity", "")).lower()
    if severity not in findings_mod.SEVERITIES:
        return True
    return severity in findings_mod.ABOVE_LOW


def is_rollup(record: dict, rollup_ids: set[str]) -> bool:
    return str(record.get("id")) in rollup_ids


def classify(records: list[dict], root: Path) -> dict[str, list[dict]]:
    """Split findings into what may be reported, what may not, and why.

    Returns keys: body, unverified, absent, invalid, rollup_constituents.
    """
    corpus_violations = findings_mod.validate_corpus(records)
    rollup_of: dict[str, list[str]] = {}
    for violation in corpus_violations:
        if violation.code == "ROLLUP":
            constituents = violation.message.split("references ")[1].split(" --")[0]
            rollup_of[violation.record_id] = [c.strip() for c in constituents.split(",")]

    # A constituent of a reported rollup is not counted again.
    superseded_by_rollup = {c for ids in rollup_of.values() for c in ids}

    buckets: dict[str, list[dict]] = {
        "body": [], "unverified": [], "absent": [], "invalid": [], "rollup_constituents": [],
    }

    for record in records:
        if not isinstance(record, dict):
            continue
        if record.get("result") == "absent":
            buckets["absent"].append(record)
            continue

        # Any blocking defect that is not purely about verification means the record cannot be
        # trusted enough to print. An earlier version excluded only evidence defects and let
        # everything else through -- so a record with severity "Critical!!" (an unrecognised
        # string) skipped the verification gate below, because "critical!!" is not in the
        # known above-Low set, and landed unverified in the client body.
        #
        # That is the project's own recurring failure: a downstream consumer trusting an upstream
        # hook to have already rejected bad input, instead of enforcing the guarantee itself.
        blocking_codes = {v.code for v in result_codes(record, root)}
        if blocking_codes - VERIFICATION_CODES:
            buckets["invalid"].append(record)
            continue

        if str(record.get("id")) in superseded_by_rollup:
            buckets["rollup_constituents"].append(record)
            continue

        verified = str(record.get("verified", "none")).lower()
        klass = str(record.get("finding_class", "technical")).lower()
        confidence = str(record.get("confidence", "unconfirmed")).lower()

        needs_proof = needs_verification(record)
        proven = verified in findings_mod.VERIFIED_STRONG or (
            verified == "n/a" and klass in findings_mod.NO_EXPLOIT_CLASSES)

        if (needs_proof and not proven) or confidence != "confirmed":
            buckets["unverified"].append(record)
        else:
            buckets["body"].append(record)

    return buckets


def render(root: Path, tier: int) -> str:
    boundary = scope_mod.load(root / "scope.yaml")
    register = regen_status.read_jsonl(root / "assets" / "register.jsonl")
    candidates = regen_status.read_jsonl(root / "assets" / "candidates.jsonl")
    cleanup = regen_status.read_jsonl(root / "ledger" / "cleanup.jsonl")
    records = regen_status.all_findings(root)
    buckets = classify(records, root)

    out: list[str] = []
    add = out.append

    add(f"# Security assessment -- {boundary.client_name}")
    add("")
    add(f"Engagement `{boundary.engagement_id}`. Tier {tier}: {TIERS[tier]}.")
    add(f"Authorised by {boundary.authorization.signed_by} on "
        f"{boundary.authorization.signed_date}; tested between "
        f"{boundary.authorization.window_start} and {boundary.authorization.window_end}.")
    add("")

    # --- summary ---------------------------------------------------------------------------
    body = sorted(buckets["body"],
                  key=lambda r: (-severity_rank(r.get("severity", "")), str(r.get("id"))))
    counts = Counter(str(r.get("severity", "")).lower() for r in body)

    add("## What we found")
    add("")
    if not body:
        add("No confirmed findings. That is a real result, not an empty report -- see")
        add("**What we checked and did not find** below for what was actually exercised.")
    else:
        add("| Severity | Count | What it means |")
        add("|---|---|---|")
        for level in reversed(findings_mod.SEVERITIES):
            if counts.get(level):
                add(f"| {level} | {counts[level]} | {SEVERITY_BLURB.get(level, '')} |")
    add("")

    # --- findings --------------------------------------------------------------------------
    if body:
        add("## Findings")
        add("")
        for record in body:
            add(f"### {record.get('id')} -- {record.get('title')}")
            add("")
            add(f"**Severity:** {record.get('severity')}  |  "
                f"**Status:** {record.get('status')}  |  "
                f"**Independently verified:** {record.get('verified')}")
            add("")
            if record.get("real_world_impact"):
                add(f"**What it means for you.** {record['real_world_impact']}")
                add("")
            if record.get("asset"):
                add(f"**Where.** `{record['asset']}`")
                add("")
            if record.get("remediation"):
                add(f"**How to fix it.** {record['remediation']}")
                add("")
            if record.get("evidence_ptr"):
                add(f"**Evidence.** `{record['evidence_ptr']}`")
                add("")

    # --- assets ----------------------------------------------------------------------------
    add("## What you own that is exposed to the internet")
    add("")
    add("Founders routinely do not know this list. Clicking through a dashboard creates cloud")
    add("objects and changes configuration invisibly, so this register is a deliverable in its")
    add("own right.")
    add("")
    if register:
        add("| Asset | Confirmed by |")
        add("|---|---|")
        for row in sorted(register, key=lambda r: str(r.get("asset_id"))):
            signals = ", ".join(sorted({s.get("class", "") for s in
                                        row.get("attribution_signals") or []}))
            add(f"| `{row.get('identifier')}` | {signals or 'operator'} |")
    else:
        add("No assets were confirmed during this engagement.")
    add("")
    if candidates:
        add(f"A further {len(candidates)} asset(s) look like yours but were **not** confirmed, and")
        add("were therefore never tested. They are listed in the appendix; confirm or exclude them")
        add("before the next engagement.")
        add("")

    # --- coverage --------------------------------------------------------------------------
    add("## What we checked and did not find")
    add("")
    add("This section is not padding. A report that lists only what broke tells you nothing about")
    add("whether the rest holds, and omitting what was not tested overstates the assurance this")
    add("assessment gives you.")
    add("")
    absent = buckets["absent"]
    if absent:
        add(f"{len(absent)} checks ran and found nothing:")
        add("")
        for record in sorted(absent, key=lambda r: str(r.get("title"))):
            add(f"- {record.get('title')}")
        add("")

    if buckets["unverified"]:
        add("### Open questions -- not confirmed, not dismissed")
        add("")
        add("Each of these is a signal we could not independently reproduce within this")
        add("engagement's scope. They are reported as open rather than presented as findings,")
        add("because an unverified claim is close to a coin flip and you cannot tell which by")
        add("reading it.")
        add("")
        for record in sorted(buckets["unverified"], key=lambda r: str(r.get("id"))):
            add(f"- **{record.get('title')}** ({record.get('severity')}) -- "
                f"next step: re-test with {'source access' if boundary.mode == 'audit' else 'more time'}.")
        add("")

    if buckets["invalid"]:
        add("### Recorded but not reportable")
        add("")
        add(f"{len(buckets['invalid'])} record(s) could not be substantiated by evidence that")
        add("resolves, and are excluded from the findings above rather than being presented with")
        add("a caveat.")
        add("")

    # --- tier 1 ------------------------------------------------------------------------------
    if tier >= 1 and body:
        add("## Where to start")
        add("")
        add("In order, by what reduces the most risk per hour of your time:")
        add("")
        for i, record in enumerate(body[:5], 1):
            add(f"{i}. **{record.get('title')}** -- {record.get('remediation', 'see above')}")
        add("")

    # --- cleanup -----------------------------------------------------------------------------
    add("## Test data we created")
    add("")
    if not cleanup:
        add("No data was written to your systems during this engagement.")
    else:
        states = Counter(str(r.get("state")) for r in cleanup)
        add(f"{len(cleanup)} record(s) were written, all marked "
            f"`RedGold-TEST-{boundary.engagement_id}-<n>`.")
        add("")
        add(f"- removed by us: {states.get('deleted', 0)}")
        add(f"- still present: {states.get('pending', 0) + states.get('orphaned', 0)}")
        add("")
        if states.get("pending") or states.get("orphaned"):
            add("**Still present.** Remove them with:")
            add("")
            add("```sql")
            add(f"DELETE FROM <table> WHERE <text_column> LIKE 'RedGold-TEST-{boundary.engagement_id}-%';")
            add("```")
            add("")
            add("An application whose own operators cannot delete test data has a data-lifecycle")
            add("problem worth addressing in its own right.")
    add("")

    # --- limits ------------------------------------------------------------------------------
    add("## Limits of this assessment")
    add("")
    add(f"- Testing was confined to the authorised boundary and stopped at blast-radius tier "
        f"{boundary.ceiling}. Nothing outside it was touched.")
    add("- Automated scope enforcement refuses out-of-scope targets and logs the refusal. It is")
    add("  defence in depth, not a guarantee that no other system could ever be reached.")
    if candidates:
        add(f"- {len(candidates)} candidate asset(s) were left untested pending confirmation.")
    add("- A finding not listed here is a finding we did not make, which is not the same as a")
    add("  vulnerability that does not exist.")
    add("")

    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the client deliverable.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--tier", type=int, default=1, choices=sorted(TIERS))
    parser.add_argument("--out", default=None)
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    try:
        text = render(root, args.tier)
    except scope_mod.ScopeError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1

    out_path = Path(args.out) if args.out else root / "deliverables" / f"report-tier{args.tier}.md"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
