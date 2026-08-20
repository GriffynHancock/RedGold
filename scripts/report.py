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
import datetime as _dt
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


# --------------------------------------------------------------------------------------------
# Report freshness (RG-1 §8.6). A deliverable may not predate its own inputs.
#
# The prior engagement's only client deliverable was written at 20:38 and said "No confirmed
# findings" and "No assets were confirmed"; `findings/baseline.json` was written at 01:20 the
# following morning with eleven findings including a critical, and `assets/register.jsonl` at
# 01:11 with six confirmed assets. Nothing detected the ordering. Every other control in RG-1 is
# irrelevant to a client who receives that file, so this one is cheap and goes first.
# --------------------------------------------------------------------------------------------

REPORT_STALE = "REPORT_STALE"


def parse_created(value) -> "_dt.datetime | None":
    """A record's `created` stamp as an aware datetime, or None if it cannot be read.

    None is not "old" and not "new" -- it is "unknown", and the caller treats unknown as stale.
    """
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    try:
        parsed = _dt.datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=_dt.timezone.utc)
    return parsed


def corpus_freshness(records: list) -> tuple:
    """(newest readable `created`, records seen, records whose `created` could not be read)."""
    stamps = []
    unreadable = 0
    total = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        total += 1
        parsed = parse_created(record.get("created"))
        if parsed is None:
            unreadable += 1
        else:
            stamps.append(parsed)
    return (max(stamps) if stamps else None), total, unreadable


def freshness_violation(root: Path, deliverable: Path) -> "str | None":
    """The `REPORT_STALE` refusal reason, or None if the deliverable postdates its corpus.

    **Fails closed in the direction that does not reduce what the client is told.** A deliverable
    that cannot be *shown* to postdate the corpus is treated exactly like one that does not:
    a missing file, and a corpus whose timestamps cannot be read, both refuse.
    """
    records = regen_status.all_findings(root)
    newest, total, unreadable = corpus_freshness(records)

    # "A deliverable that was never written" is checked FIRST, before the empty-corpus exemption.
    # The exemption used to come first, so an engagement with zero finding records and one clean
    # row in the coverage register cleared every refusal and closed with no client deliverable in
    # existence -- while `close` printed "report-tier1.md postdates every finding" about a file
    # that did not exist. That is a fabricated assurance emitted by the control whose whole
    # purpose is to prevent fabricated assurance (adversarial review, S3).
    #
    # The rule has no exemption for engagements that found nothing. Those are precisely the
    # engagements whose report is the entire product: "we tried to break this and could not" is
    # the result the client paid for, and it does not exist until it is written down.
    if not deliverable.is_file():
        return (f"{REPORT_STALE}: {deliverable.name} does not exist. An engagement does not "
                f"close on a deliverable that was never written ({total} finding record(s) on "
                "disk). Run report.py.")
    if total == 0:
        # Nothing to predate. An engagement with no records at all is caught by the zero-zero
        # rule (RG-1 §8.2) at phase completion, not here.
        return None
    if unreadable:
        return (f"{REPORT_STALE}: {unreadable} of {total} finding record(s) carry no readable "
                "`created` timestamp, so this deliverable cannot be shown to postdate them. "
                "An unreadable timestamp is not evidence that the report is current.")

    written = _dt.datetime.fromtimestamp(deliverable.stat().st_mtime, _dt.timezone.utc)
    if written < newest:
        return (f"{REPORT_STALE}: {deliverable.name} was written {written.isoformat()} but the "
                f"newest of {total} finding record(s) was recorded {newest.isoformat()}. The "
                "deliverable predates its own inputs and cannot describe them. Re-run report.py.")
    return None


def result_codes(record: dict, root: Path) -> list:
    return findings_mod.validate_record(record, root).blocking


def needs_verification(record: dict) -> bool:
    """Does this record require independent re-execution before a client sees it?

    **Fails closed on an unrecognised or missing severity.** An unknown severity is not evidence
    that a finding is low-severity; it is evidence that we do not know, and a report is the last
    place to resolve an ambiguity in the flattering direction.

    **Keys on the pre-cap severity** (`findings.gating_severity`), for the reason set out there:
    the environment cap's job is to lower a severity, and a severity transform must never be able
    to make a `status`/`verified` gate unreachable. Capping to `low` -- which `ephemeral-preview`
    does unconditionally -- silenced this gate entirely, and walked a SPECULATED, never-verified
    `critical` into the client body (adversarial review, S2).
    """
    if str(record.get("finding_class", "technical")).lower() != "technical":
        return False
    if str(record.get("severity", "")).lower() not in findings_mod.SEVERITIES:
        return True
    return findings_mod.gating_severity(record) in findings_mod.ABOVE_LOW


def is_rollup(record: dict, rollup_ids: set[str]) -> bool:
    return str(record.get("id")) in rollup_ids


def engagement_environment(root: Path) -> str:
    """The declared environment, resolved fail-closed to `production`.

    A scope that cannot be read is not evidence that the engagement was non-production, so an
    unreadable boundary caps nothing. The refusal for an undeclared environment lives at Gate 1
    (`gate_cli.cmd_approve`), where it can be acted on; a report that silently capped every
    severity because it could not read scope.yaml would be the flattering failure.
    """
    try:
        return scope_mod.effective_environment(scope_mod.load(root / "scope.yaml").environment)
    except scope_mod.ScopeError:
        return "production"


def classify(records: list[dict], root: Path,
             environment: "str | None" = None) -> dict[str, list[dict]]:
    """Split findings into what may be reported, what may not, and why.

    Returns keys: body, unverified, absent, invalid, rollup_constituents.

    The environment cap (RG-1 §6) is applied here, on copies, before anything is bucketed. This
    is the assembly-time half of the cap: `baseline_scan` caps its own output at write time, but
    every agent-written record reaches a client through this function and nowhere else. Order
    matters and is part of the specification -- the cap runs *before* the §10.3 verification gate
    below, and that gate reads `severity` rather than any pre-cap value, so a record scored
    critical and capped to medium in development is gated on what the client would actually be
    told.
    """
    if environment is None:
        environment = engagement_environment(root)
    records = findings_mod.apply_environment_cap_to_corpus(records, environment)

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
        "not_applicable": [], "environment_discrepancy": [],
    }

    for record in records:
        if not isinstance(record, dict):
            continue
        if record.get("result") == "absent":
            buckets["absent"].append(record)
            continue
        # A check that could not be performed is neither a finding nor a clean result. It is a
        # named gap, and it gets its own section rather than being folded in with the checks that
        # actually ran -- the coverage claim has to distinguish the two.
        if record.get("result") == "not_applicable":
            buckets["not_applicable"].append(record)
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
        # RG-1 §4.2's action clause, and the reason this check is sited here rather than at Gate
        # 1: the affected findings do not enter the report body until the discrepancy is resolved
        # by a recorded operator decision naming which side was wrong. Checked before the general
        # malformed-record branch so the client-facing reason is the specific one.
        if "ENVIRONMENT_DISCREPANCY" in blocking_codes:
            buckets["environment_discrepancy"].append(record)
            continue
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
    environment = scope_mod.effective_environment(boundary.environment)
    buckets = classify(records, root, environment)

    out: list[str] = []
    add = out.append

    add(f"# Security assessment -- {boundary.client_name}")
    add("")
    add(f"Engagement `{boundary.engagement_id}`. Tier {tier}: {TIERS[tier]}.")
    add(f"Authorised by {boundary.authorization.signed_by} on "
        f"{boundary.authorization.signed_date}; tested between "
        f"{boundary.authorization.window_start} and {boundary.authorization.window_end}.")
    add("")

    # The corpus this document was generated from, stated in the document (RG-1 §8.6). A staleness
    # check that only a script can see is a staleness check nobody runs; a client, or the operator
    # re-reading the file a week later, can compare these two numbers against `findings/`.
    newest_created, corpus_total, corpus_unreadable = corpus_freshness(records)
    add(f"Generated from {corpus_total} finding record(s); the newest was recorded "
        f"{newest_created.isoformat() if newest_created else 'at no readable timestamp'}.")
    if corpus_unreadable:
        add(f"{corpus_unreadable} of those record(s) carry no readable `created` timestamp, so "
            "this document cannot be shown to postdate them.")
    add("Any record newer than that timestamp is not described here, and this document is stale.")
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
            # RG-1 §6.4: recorded, never silently applied. The required sentence is the
            # derivation one -- it says where we looked, never that the client is safe.
            derivation = record.get("severity_derivation") or {}
            if derivation.get("env_cap_applied"):
                add(f"**Why this severity.** Rated {record.get('severity')} because it was "
                    f"observed in a {derivation.get('environment_at_test')} environment. The "
                    f"same issue in your production system would be rated "
                    f"{derivation.get('before_env_cap')}.")
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

    # Two reasons a check did not run, and they say opposite things to a client (RG-1 §4.1). A
    # service nobody could probe is an unassessed service; a check that is meaningless against
    # this origin is not a gap at all. Printing them in one list would either manufacture a hole
    # the assessment does not have, or bury a real one among structural non-events.
    unassessed: dict[str, int] = {}
    inapplicable: dict[str, int] = {}
    for record in buckets["not_applicable"]:
        # The collapsed record stands for every check it names (RG-1 §4.1b), so the count is
        # `checks_skipped`, not one per record. One definition, shared with `regen_status.py` --
        # the two used to count this by opposite rules and could disagree by twelve on the same
        # corpus (adversarial review, S8).
        count = regen_status.coverage_gap_size(record)
        target = (inapplicable
                  if record.get("not_applicable_reason") in regen_status.INAPPLICABLE_REASONS
                  else unassessed)
        asset = str(record.get("asset"))
        target[asset] = target.get(asset, 0) + count

    if unassessed:
        add("### What we could NOT check")
        add("")
        add("These checks did not run. They are listed because a service nobody probed is an")
        add("unassessed service, not a clean one, and reporting it as clean would overstate the")
        add("coverage of this assessment.")
        add("")
        for asset, count in sorted(unassessed.items()):
            add(f"- **{asset}** -- {count} check(s) not performed; this service is unassessed.")
        add("")

    if inapplicable:
        add("### Checks that do not apply here")
        add("")
        add("These checks were skipped because they have no meaning against the service in")
        add("question -- not because they were missed. They are listed so that the count above")
        add("is not read as covering them.")
        add("")
        for asset, count in sorted(inapplicable.items()):
            add(f"- **{asset}** -- {count} check(s) not applicable to this service.")
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

    if buckets["environment_discrepancy"]:
        add("### Held back -- the environment we were told about and the one we saw disagree")
        add("")
        add(f"{len(buckets['environment_discrepancy'])} record(s) were observed on assets that")
        add("emitted signals of a non-production environment while being declared production.")
        add("They are held out of the findings above until that disagreement is resolved, because")
        add("rating them either way would be a guess about which system you actually run:")
        add("")
        for record in sorted(buckets["environment_discrepancy"], key=lambda r: str(r.get("id"))):
            kinds = ", ".join(sorted({str(s.get("kind")) for s
                                      in findings_mod.blocking_env_signals(record)}))
            add(f"- **{record.get('title')}** (`{record.get('asset')}`) -- observed: {kinds}.")
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
    if any((r.get("severity_derivation") or {}).get("env_cap_applied")
           for r in buckets["body"] + buckets["unverified"]):
        # Required wherever the severity model reduced a rating (RG-1 §11.2). A client who
        # cannot see what was reduced cannot audit the reduction.
        add(f"- Some severities above were **reduced** because the assets were tested in a "
            f"`{environment}` environment rather than in production. Each one states its "
            "original rating and the reason. Nothing was removed from this document by that "
            "reduction: findings the model rated down are listed with their reasons rather than "
            "dropped. The reduction is a statement about where we looked, not about whether the "
            "issue matters.")
    add("")

    return "\n".join(out) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate the client deliverable.")
    parser.add_argument("--root", default=".")
    parser.add_argument("--tier", type=int, default=1, choices=sorted(TIERS))
    parser.add_argument("--out", default=None)
    parser.add_argument("--check", action="store_true",
                        help="do not write; exit 1 if the deliverable on disk predates the "
                             "newest finding record (RG-1 §8.6, REPORT_STALE)")
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    out_path = Path(args.out) if args.out else root / "deliverables" / f"report-tier{args.tier}.md"

    if args.check:
        violation = freshness_violation(root, out_path)
        if violation:
            print(f"REFUSED: {violation}", file=sys.stderr)
            return 1
        print(f"{out_path} postdates every finding record.")
        return 0

    try:
        text = render(root, args.tier)
    except scope_mod.ScopeError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    print(f"Wrote {out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
