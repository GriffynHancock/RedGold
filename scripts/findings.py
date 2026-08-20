"""findings.py -- the findings schema, evidence resolution, and validation rules (spec §10).

Build order steps 5 and 6.

`validate_findings.py` is the hook that enforces these rules; this module is where they live so the
same logic is reachable from a CLI, from the report generator, and from tests without going through
a hook payload.

THE RULE THAT DOES THE MOST WORK
--------------------------------
`evidence_ptr` must resolve to a file that exists -- and for `file.md#anchor`, to an anchor that
exists in it. On a prior engagement this field was free-text prose: a human citation no script
could check, which is a large part of why the validator was never built and the claims were never
mechanically tested.

Published false-positive rates for *autonomous* vulnerability detection run 15.3-45.8% across six
frontier models (arXiv 2605.23243). At those rates an unverified finding is close to a coin flip,
which is why an unresolvable evidence pointer demotes a record to SPECULATED rather than producing
a warning somebody scrolls past.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

FINDING_CLASSES = ("technical", "posture", "governance", "compliance")
STATUSES = ("PROVEN", "SPECULATED")
VERIFIED_LEVELS = ("none", "replayed", "executed", "n/a")
CONFIDENCES = ("confirmed", "probable", "unconfirmed")

# Ordered. Index comparison is how "above Low" is decided.
SEVERITIES = ("info", "low", "medium", "high", "critical")
ABOVE_LOW = set(SEVERITIES[SEVERITIES.index("low") + 1:])

# Verification levels that count as independently established (§10.3).
VERIFIED_STRONG = frozenset({"replayed", "executed"})

# Classes whose severity rests on an observed fact rather than a demonstrated exploit, and which
# may therefore exceed Low with verified: n/a. Without this carve-out the validator would reject
# every legitimate posture finding on every engagement.
NO_EXPLOIT_CLASSES = frozenset({"posture", "governance"})

REQUIRED_FIELDS = ("id", "title", "finding_class", "status", "severity")

ID_RE = re.compile(r"^F-\d{3,}$")

MODEL_VERSION = "rg-sev/1"

# --------------------------------------------------------------------------------------------
# The environment cap (RG-1 §6) -- PROVISIONAL (D-1), adopted provisionally by the operator and
# AWAITING SIGN-OFF. It is deliberately one table: reversing the decision, or moving any band, is
# a change to these five rows and nothing else. Do not write a cap value anywhere but here.
#
# Why a graduated cap and not a flat `low` for everything non-production: a flat cap buries the
# worst example the autopsy found -- a live, spend-capable API key sitting in a development
# config. Capping a live production credential at `low` because the box is a dev box is a worse
# error than any of the findings the cap suppresses. And the flat proposal's bypass was a free
# text "stated reason", which absorbs any sentence an agent wants to write; `production_nexus` is
# a closed vocabulary with a resolving evidence pointer per kind, which cannot absorb a
# disclaimer.
#
# `None` means uncapped. Two columns because a posture fact and an exploited defect are not the
# same claim about the same box (§5.5).
# --------------------------------------------------------------------------------------------

ENVIRONMENT_SEVERITY_CAP = {
    "production":        {"technical": None,     "posture": None},
    "staging":           {"technical": "high",   "posture": "medium"},
    "development":       {"technical": "medium", "posture": "low"},
    "ephemeral-preview": {"technical": "low",    "posture": "low"},
}

# Ordered least-to-most disclosing: `production` is uncapped, `ephemeral-preview` caps hardest.
# Index comparison is how "a record is talking its own environment *down*" is decided (§6.2).
ENVIRONMENT_STRENGTH = ("ephemeral-preview", "development", "staging", "production")

# The bypass. Closed, five values, each requiring its own resolving evidence pointer (§6.4).
PRODUCTION_NEXUS_KINDS = (
    "live_credential", "production_data", "shared_infrastructure", "code_defect", "same_artifact",
)

# `rg-codeaudit` reads a SOURCE_CODE asset: the environment of a source-code finding is the code,
# not the box it was read on. The default therefore runs in the direction that discloses, and
# genuinely dev-only code must be cleared explicitly (§6.2 reason 3).
#
# THE PRODUCER IS AN INSTRUCTION, NOT A MECHANISM -- read this before trusting the default.
# Until 2026-08-20 nothing in the repository wrote this value: `agents/rg-codeaudit.md` never
# mentioned the findings schema, no template or command emitted it, and the only occurrences were
# in tests that supplied the field themselves. So the constant worked perfectly on input no
# producer generated, and every whitebox finding on a development-declared engagement was capped
# by the laptop the source was read on -- the precise outcome it exists to prevent (adversarial
# review, S6). `test_findings.TestCodeDefectDefaultHasAProducer` is what stops that recurring
# silently: it asserts the agent card still instructs the field.
#
# It is an agent card, so it is an instruction to a model and not an enforced invariant (CLAUDE.md
# design judgement 4). The mechanical alternative -- stamping `discovered_by` from the subagent
# type in the `SubagentStop` hook -- is not available: the hook payload carries `agent_id` and
# `session_id`, neither of which names the agent type. **Recorded as a residual rather than
# described as enforced.**
CODE_DEFECT_PRODUCERS = frozenset({"rg-codeaudit"})


# --------------------------------------------------------------------------------------------
# ENVIRONMENT_DISCREPANCY (RG-1 §4.2) -- re-sited, and the reason is worth keeping.
#
# The spec's prose puts this at Gate 1. It cannot live there. Three of the four signals §2.4
# permits to *block* -- a `pk_test_`/`sk_test_` prefix in a **response body**, a framework debug
# page, a dev-tool service fingerprint -- require active contact with the asset, and under §9.7
# no contact happens until after Gate 1 has approved the plan. Sited at Gate 1 the check fires on
# 0% of anything, which is the failure §2.3 names: worse than a wrong rule, because it reads as
# coverage. §4.2's own action clause is report-time ("the affected findings do not enter the
# report body"), which is where it belongs.
#
# So the two concerns are split, because they were two checks conflated into one:
#   * the *declaration* is a scope fact, required in scope.yaml, refused at Gate 1;
#   * the *discrepancy between declared and observed* is computable only once signals exist, and
#     runs where the observation lands -- finding creation and report assembly.
#
# The classifier may never *set* `environment`, and may *contradict* a declaration. Setting
# requires a positive conclusion from signals that are silent when absent, which is unsound;
# contradicting requires only that a declaration and an observation disagree, which is sound.
# --------------------------------------------------------------------------------------------

# Blocking. Each has one meaning, established rather than assumed.
ENVIRONMENT_SIGNALS_BLOCKING = (
    "test_payment_key",       # a vendor-defined prefix (pk_test_/sk_test_) with one meaning
    "dev_tool_fingerprint",   # Mailpit, MailHog, mailcatcher, Mailtrap, Adminer, vite, flower
    "framework_debug_page",   # a framework-branded verbose error or debug page
    "nonprod_cert",           # cert subject localhost/RFC1918/*.local -- flag-for-review
)

# Recorded, printed, never a verdict alone. A naming convention is not a platform assertion:
# `react-tweet.vercel.app` and `swr.vercel.app` are both production.
ENVIRONMENT_SIGNALS_CONTRIBUTES_ONLY = (
    "hostname_convention", "ephemeral_path", "dev_identifier", "published_sourcemap",
    "platform_header",
)

ENVIRONMENT_SIGNAL_KINDS = ENVIRONMENT_SIGNALS_BLOCKING + ENVIRONMENT_SIGNALS_CONTRIBUTES_ONLY

# A closed vocabulary, because §4.2 requires the resolution to name **which side was wrong**, and
# a free-text field absorbs any sentence an agent wants to write.
DISCREPANCY_DECISIONS = ("declaration_wrong", "signal_wrong")


def blocking_env_signals(record: dict) -> list:
    """The signals on this record that are permitted to produce a verdict."""
    signals = record.get("env_signals")
    if not isinstance(signals, list):
        return []
    return [s for s in signals
            if isinstance(s, dict) and s.get("kind") in ENVIRONMENT_SIGNALS_BLOCKING]


def discrepancy_resolution(record: dict) -> "dict | None":
    """The operator decision that clears a discrepancy, or None if there is not a usable one."""
    resolution = record.get("environment_discrepancy_resolution")
    if not isinstance(resolution, dict):
        return None
    if resolution.get("decision") not in DISCREPANCY_DECISIONS:
        return None
    reason = resolution.get("reason")
    if not isinstance(reason, str) or not reason.strip():
        return None
    return resolution


def cap_column(finding_class: Any) -> str:
    """Which column of the cap table this record is scored against."""
    return "posture" if str(finding_class or "").lower() in NO_EXPLOIT_CLASSES else "technical"


def resolve_environment(value: Any) -> str:
    """Anything unresolvable reads as `production`, which is the uncapped column.

    Deliberately duplicated from `scope.effective_environment` rather than imported: this module
    is loaded by the `SubagentStop` hook, and a hook that dies on an import does not enforce. The
    two are kept in step by `test_findings.TestEnvironmentCap` and `test_scope.TestEnvironment`
    asserting the same table.
    """
    if isinstance(value, str) and value in ENVIRONMENT_SEVERITY_CAP:
        return value
    return "production"


def environment_cap(environment: Any, finding_class: Any) -> "str | None":
    """The severity ceiling for this (environment, class), or None for uncapped.

    Membership test then indexed read. No `dict.get(value, default)` anywhere in this file's rank
    lookups: a defaulting lookup is how an unrecognised string silently becomes the most
    flattering value, which is exactly how `"Critical!!"` passed a membership test on 2026-08-04.
    """
    return ENVIRONMENT_SEVERITY_CAP[resolve_environment(environment)][cap_column(finding_class)]


def production_nexus_kind(record: dict) -> "str | None":
    """The declared nexus kind, or None when there is no usable declaration.

    An **unrecognised** kind returns itself rather than None: the cap is bypassed (the disclosing
    direction) *and* `validate_record` raises a blocking violation (the correctness direction).
    The two directions differ here and we take both -- a severity must not be quietly reduced by
    a field nobody can read, and the record must not reach a client while the field is unreadable.
    """
    nexus = record.get("production_nexus")
    if not isinstance(nexus, dict):
        return None
    kind = nexus.get("kind")
    return kind if isinstance(kind, str) and kind else None


def environment_at_test(record: dict, environment: Any) -> tuple[str, "dict | None"]:
    """(the environment this record is scored against, a declaration conflict or None).

    A record may carry its own `environment_at_test`: the environment at the moment of the test
    is a fact about the test, and re-declaring the engagement later does not change it. But that
    is only half a rule, and the missing half (adversarial review, S5) was a one-key suppression
    primitive -- on a `production` engagement, `environment_at_test: ephemeral-preview` took a
    critical to a low with nothing anywhere comparing the two declarations.

    So the rule is directional, exactly as `production_nexus` is:

    - **Raising** the environment above the signed scope discloses more, and needs no ceremony.
    - **Lowering** it below the signed scope is a claim that the scope is wrong about its own
      engagement. It costs the same `environment_discrepancy_resolution` ceremony §4.2 already
      demands in the other direction -- a closed-vocabulary decision and a non-empty reason.
      Unopposed, the signed scope wins and the contradiction is recorded.

    Note this is a *declaration-vs-declaration* check: it needs no signals and no contact with
    the asset, which is why it can be sited here rather than waiting for §2.4's signal table.
    """
    engagement = resolve_environment(environment)
    declared = record.get("environment_at_test")
    if declared is None:
        return engagement, None

    stated = resolve_environment(declared)
    if stated == engagement:
        return stated, None
    if ENVIRONMENT_STRENGTH.index(stated) > ENVIRONMENT_STRENGTH.index(engagement):
        return stated, None          # raising -- the disclosing direction
    if discrepancy_resolution(record) is not None:
        return stated, None          # lowering, contested and resolved by an operator
    return engagement, {"engagement_declared": engagement, "record_declared": stated}


def apply_environment_cap(record: dict, environment: Any) -> dict:
    """Stamp `environment_at_test`, apply the §6 cap, and record what it did. Idempotent.

    Three properties implemented deliberately, per §6.4:

    - **Recorded, never silently applied.** `severity_derivation` carries the pre-cap severity,
      the cap that was applied and the result, so the report can say *"rated medium because it
      was observed in a development environment; the same issue in your production system would
      be rated high"* -- which is more useful to a client than either number alone, and is the
      sentence the prior engagement's findings should have contained.
    - **`min`, never `max`.** An engagement against production does not get a severity floor.
    - **Idempotent.** Capping an already-capped severity is a no-op because the cap is `min`.

    THE DERIVATION IS AN OUTPUT, NOT AN INPUT
    -----------------------------------------
    `severity_derivation` used to supply the pre-cap severity this function scored from, and the
    result was written back over `record["severity"]`. `severity_derivation` lives *on the
    record*, so every writer of a findings record could set the severity a client is shown by
    writing a different key -- including on a `production` engagement, where the cap is `None`,
    `env_cap_applied` is `False`, and §6.4's disclosure therefore never prints. A proven,
    independently verified `high` rendered as `low` with no disclosure at all (adversarial
    review, S1). A security decision must not read from a mutable, producer-supplied field.

    The authoritative pre-cap severity is now `record["severity"]`, always. The only thing the
    prior derivation is consulted for is *what to disclose* -- carrying an older, higher
    `before_env_cap` forward across a re-run so the §6.4 sentence does not degrade -- and it is
    trusted for that only when it demonstrably describes this record: its `after_env_cap` must
    equal the record's current severity, and its `before_env_cap` must rank at or above it. Any
    other prior derivation is discarded.

    Discarded in which direction matters, so the two are distinguished:

    - `severity` **above** the recorded `after_env_cap` is §10.3's mandated workflow -- rg-verify
      re-executes a finding and the operator raises it. Re-score from `severity`, no complaint.
    - `severity` **below** the recorded `after_env_cap` is a severity lowered beneath what the
      scorer computed, in the flattering direction, corroborated by nothing. That is what §6
      names DERIVATION_MISMATCH for, and stamping `derivation_conflict` is what makes the code
      fireable inside `report.classify` at all -- previously the cap rewrote `severity` to equal
      `after_env_cap` immediately before `validate_record` compared them.
    """
    if not isinstance(record, dict):
        return record

    at_test, declaration_conflict = environment_at_test(record, environment)
    record["environment_at_test"] = at_test

    if str(record.get("discovered_by", "")) in CODE_DEFECT_PRODUCERS \
            and "production_nexus" not in record:
        record["production_nexus"] = {
            "kind": "code_defect",
            "evidence_ptr": record.get("evidence_ptr"),
            "default_applied": True,
        }

    prior = record.get("severity_derivation")
    prior = prior if isinstance(prior, dict) else {}
    before = str(record.get("severity", ""))

    prior_before = prior.get("before_env_cap")
    prior_after = prior.get("after_env_cap")
    conflict = None
    if isinstance(prior_after, str) and prior_after in SEVERITIES and before in SEVERITIES:
        if SEVERITIES.index(before) < SEVERITIES.index(prior_after):
            conflict = {"recorded_after_env_cap": prior_after, "record_severity": before}
        elif prior_after == before and isinstance(prior_before, str) \
                and prior_before in SEVERITIES \
                and SEVERITIES.index(prior_before) >= SEVERITIES.index(before):
            before = prior_before

    kind = production_nexus_kind(record)
    cap = None if kind else environment_cap(at_test, record.get("finding_class"))

    applied = False
    after = before
    # An unrecognised severity is never capped. "We do not know what this is" must not resolve to
    # "it is medium" -- that is a reduction in what the client is told, made on no evidence. The
    # record is caught elsewhere by the fail-closed severity checks in `report.needs_verification`.
    if cap is not None and before in SEVERITIES:
        index = min(SEVERITIES.index(before), SEVERITIES.index(cap))
        after = SEVERITIES[index]
        applied = after != before

    derivation = {
        "model_version": MODEL_VERSION,
        "before_env_cap": before,
        "environment_at_test": at_test,
        "env_cap": cap,
        "env_cap_applied": applied,
        "after_env_cap": after,
        "production_nexus_kind": kind,
    }
    if conflict is not None:
        derivation["derivation_conflict"] = conflict
    if declaration_conflict is not None:
        derivation["environment_declaration_conflict"] = declaration_conflict
    record["severity_derivation"] = derivation
    record["severity"] = after
    return record


def gating_severity(record: dict) -> str:
    """The severity §10.3's gates key on: the highest rating this record has carried.

    The environment cap lowers a severity to describe *where a thing was observed*. It must never
    lower a record out of a gate that is not about severity at all: `UNVERIFIED_ABOVE_LOW` and
    `SPECULATED_ABOVE_LOW` are statements about `verified` and `status`. Capping a technical
    finding to `low` -- which `ephemeral-preview` does unconditionally -- silenced both, and a
    SPECULATED, never-verified `critical` reached the client report body asserting that it "would
    be rated critical in your production system" (adversarial review, S2).

    Keying the gates on the pre-cap severity rather than reordering the pipeline is deliberate.
    The cap must still run *before* bucketing, because the printed severity and §6.4's disclosure
    both depend on it; and `report.classify` is not the only caller -- the `SubagentStop` hook
    validates records the cap has never touched. A rule expressed as "run this gate before the
    cap" would hold in one caller. Expressed as "these gates key on the highest severity this
    record has carried" it holds in every caller, in any order, and needs no coordination.

    `max` of the two, not the recorded pre-cap value alone: on the hook path the derivation is
    still producer-supplied, so a record claiming a *lower* pre-cap severity than its own
    `severity` must not be able to gate itself down that way either.
    """
    ranks = []
    for value in (record.get("severity"),
                  (record.get("severity_derivation") or {}).get("before_env_cap")
                  if isinstance(record.get("severity_derivation"), dict) else None):
        if isinstance(value, str) and value.lower() in SEVERITIES:
            ranks.append(SEVERITIES.index(value.lower()))
    if not ranks:
        return str(record.get("severity", "")).lower()
    return SEVERITIES[max(ranks)]


def apply_environment_cap_to_corpus(records: list, environment: Any) -> list:
    """The cap over a whole corpus, on copies. Callers keep their own records unmutated."""
    out = []
    for record in records:
        out.append(apply_environment_cap(dict(record), environment)
                   if isinstance(record, dict) else record)
    return out


@dataclass(frozen=True)
class Violation:
    """One defect in one record.

    `blocking` violations stop a subagent. `demotes` violations rewrite the record's status --
    they are not merely reported, because a warning about an unproven claim is exactly the thing
    that gets ignored under time pressure.
    """

    record_id: str
    code: str
    message: str
    fix: str
    blocking: bool = True
    demotes: bool = False

    def render(self) -> str:
        return f"[{self.code}] {self.record_id}: {self.message}\n    FIX: {self.fix}"


@dataclass
class RecordResult:
    record_id: str
    violations: list[Violation] = field(default_factory=list)

    @property
    def demoted(self) -> bool:
        return any(v.demotes for v in self.violations)

    @property
    def blocking(self) -> list[Violation]:
        return [v for v in self.violations if v.blocking]


# --------------------------------------------------------------------------------------------
# Evidence
# --------------------------------------------------------------------------------------------

_HEADING_RE = re.compile(r"^#{1,6}\s+(.*?)\s*$", re.MULTILINE)
_EXPLICIT_ANCHOR_RE = re.compile(r'<a\s+(?:id|name)=["\']([^"\']+)["\']', re.IGNORECASE)


def slugify_heading(text: str) -> str:
    """GitHub-style heading slug: lowercase, punctuation dropped, spaces to hyphens."""
    text = re.sub(r"[`*_~\[\]()]", "", text).strip().lower()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"\s+", "-", text)


def anchors_in_markdown(text: str) -> set[str]:
    anchors = {slugify_heading(h) for h in _HEADING_RE.findall(text)}
    anchors |= set(_EXPLICIT_ANCHOR_RE.findall(text))
    return anchors


def looks_like_prose_pointer(pointer: str) -> bool:
    """True when the value is a human citation rather than a machine-checkable pointer.

    Prior-engagement pointers look like:

        'Burp/signup-auth-v1-user-post (X-Client-Info header); phase2_evidence/probes.md#1'

    -- several references, separated by semicolons, with parenthetical commentary. The files
    referenced genuinely exist, so a naive check that hand-parses the prose reports it clean.
    That is exactly the failure §10.2 describes: a citation no script can check, which is why
    the validator was never built the first time. The defect is the format, not the evidence.
    """
    return ";" in pointer or " (" in pointer


def resolve_evidence(pointer: str, root: Path) -> tuple[bool, str]:
    """Resolve an evidence pointer. Returns (ok, reason-if-not).

    Accepts `path`, `path#anchor`, and `path#Lnn` (a line number). Anything outside the
    engagement directory is refused -- an evidence pointer that escapes the engagement is not
    evidence anyone can audit later.
    """
    if not isinstance(pointer, str) or not pointer.strip():
        return False, "evidence_ptr is empty"

    raw_path, _, anchor = pointer.partition("#")
    raw_path = raw_path.strip()
    if not raw_path:
        return False, f"evidence_ptr {pointer!r} has no file part"

    candidate = (root / raw_path).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return False, f"evidence_ptr {pointer!r} points outside the engagement directory"

    if not candidate.is_file():
        return False, f"evidence file {raw_path} does not exist"

    if not anchor:
        return True, ""

    if re.fullmatch(r"L\d+", anchor):
        line_no = int(anchor[1:])
        total = len(candidate.read_text(encoding="utf-8", errors="replace").splitlines())
        if line_no < 1 or line_no > total:
            return False, f"evidence anchor #{anchor} is outside {raw_path} ({total} lines)"
        return True, ""

    if candidate.suffix.lower() not in (".md", ".markdown"):
        # A non-markdown file cannot carry a heading anchor. Substring presence is the only
        # honest check available.
        body = candidate.read_text(encoding="utf-8", errors="replace")
        if anchor in body:
            return True, ""
        return False, f"anchor {anchor!r} does not appear in {raw_path}"

    body = candidate.read_text(encoding="utf-8", errors="replace")
    available = anchors_in_markdown(body)
    if slugify_heading(anchor) in available or anchor in available:
        return True, ""
    return False, f"anchor #{anchor} not found in {raw_path}"


# --------------------------------------------------------------------------------------------
# Validation
# --------------------------------------------------------------------------------------------


def _enum(record: dict, key: str, allowed: Iterable[str], rid: str, violations: list[Violation],
          *, required: bool = True, lower: bool = False) -> str | None:
    value = record.get(key)
    if value is None:
        if required:
            violations.append(Violation(
                rid, "MISSING_FIELD", f"required field '{key}' is missing",
                f"add '{key}', one of: {', '.join(allowed)}",
            ))
        return None
    if not isinstance(value, str):
        violations.append(Violation(
            rid, "BAD_TYPE", f"'{key}' must be a string, got {type(value).__name__}",
            f"set '{key}' to one of: {', '.join(allowed)}",
        ))
        return None
    normalised = value.lower() if lower else value
    if normalised not in allowed:
        violations.append(Violation(
            rid, "BAD_ENUM", f"'{key}' value {value!r} is not recognised",
            f"use one of: {', '.join(allowed)}",
        ))
        return None
    return normalised


def validate_record(record: Any, root: Path, *, strict_id: bool = True) -> RecordResult:
    """Apply §10's rules to a single findings record.

    `strict_id=False` for records from a prior engagement, whose identifier convention predates
    this schema. Complaining about that would bury the substantive findings under cosmetics.
    """
    if not isinstance(record, dict):
        return RecordResult("<not-an-object>", [Violation(
            "<not-an-object>", "BAD_RECORD", "findings record is not a JSON object",
            "each record must be an object with at least id, title, finding_class, status, severity",
        )])

    rid = str(record.get("id") or "<no-id>")
    violations: list[Violation] = []

    for key in REQUIRED_FIELDS:
        if key not in record or record.get(key) in (None, ""):
            violations.append(Violation(
                rid, "MISSING_FIELD", f"required field '{key}' is missing or empty",
                f"add '{key}' to record {rid}",
            ))

    if strict_id and "id" in record and isinstance(record["id"], str) and not ID_RE.match(record["id"]):
        violations.append(Violation(
            rid, "BAD_ID", f"id {record['id']!r} is not of the form F-NNN",
            "renumber the record, e.g. F-007",
        ))

    finding_class = _enum(record, "finding_class", FINDING_CLASSES, rid, violations, lower=True)
    status = _enum(record, "status", STATUSES, rid, violations)
    severity = _enum(record, "severity", SEVERITIES, rid, violations, lower=True)
    verified = _enum(record, "verified", VERIFIED_LEVELS, rid, violations, required=False, lower=True)
    _enum(record, "confidence", CONFIDENCES, rid, violations, required=False, lower=True)

    # --- evidence (§10.2) -------------------------------------------------------------------
    pointer = record.get("evidence_ptr")
    evidence_ok = False
    if pointer in (None, ""):
        # posture/governance still need a dated pointer; technical always needs one.
        violations.append(Violation(
            rid, "NO_EVIDENCE", "record carries no evidence_ptr",
            "capture the request/response to evidence/<id>-<slug>.http and reference it",
            demotes=(status == "PROVEN"),
        ))
    elif looks_like_prose_pointer(str(pointer)):
        violations.append(Violation(
            rid, "EVIDENCE_NOT_CHECKABLE",
            f"evidence_ptr is a prose citation, not a resolvable pointer: {str(pointer)[:70]!r}",
            "one pointer per record, of the form evidence/<id>-<slug>.http or file.md#anchor. "
            "Split multiple citations into separate records and move commentary into the "
            "finding body -- a pointer no script can check is why this was never validated",
            demotes=True,
        ))
    else:
        evidence_ok, reason = resolve_evidence(pointer, root)
        if not evidence_ok:
            violations.append(Violation(
                rid, "EVIDENCE_UNRESOLVED", reason,
                "capture the evidence to a real file under evidence/ and point at it; "
                "an unresolvable pointer demotes this record to SPECULATED",
                demotes=True,
            ))

    # The severity the §10.3 gates key on: the highest this record has carried, pre-cap. A
    # severity transform must not be able to make a `status`/`verified` gate unreachable.
    claimed = gating_severity(record) if severity else severity

    # --- verification rules (§10.3) ---------------------------------------------------------
    if finding_class == "technical":
        if status == "PROVEN" and verified not in VERIFIED_STRONG:
            violations.append(Violation(
                rid, "PROVEN_UNVERIFIED",
                f"technical finding is PROVEN but verified={verified or 'absent'!r}",
                "have rg-verify re-execute it and set verified to 'replayed' or 'executed', "
                "or downgrade status to SPECULATED",
            ))
        if claimed in ABOVE_LOW and verified not in VERIFIED_STRONG:
            violations.append(Violation(
                rid, "UNVERIFIED_ABOVE_LOW",
                f"technical finding is severity {claimed} but not independently verified",
                "no technical finding above Low reaches a client without 'replayed' or 'executed'; "
                "verify it or lower the severity",
            ))
        if record.get("tested_at_tier") is None:
            violations.append(Violation(
                rid, "NO_TIER", "technical finding does not record tested_at_tier",
                "set tested_at_tier to the blast-radius tier of the test that produced it (§6)",
                blocking=False,
            ))

    if verified == "n/a" and finding_class not in NO_EXPLOIT_CLASSES:
        violations.append(Violation(
            rid, "NA_NOT_PERMITTED",
            f"verified 'n/a' is only valid for {' or '.join(sorted(NO_EXPLOIT_CLASSES))}, "
            f"not finding_class {finding_class!r}",
            "there is an exploit to replay here -- verify it, or reclassify the finding",
        ))

    if verified == "n/a" and not evidence_ok:
        violations.append(Violation(
            rid, "NA_WITHOUT_EVIDENCE",
            "verified 'n/a' requires a dated evidence pointer (config export, screenshot, "
            "interview note)",
            "attach the observed artifact under evidence/ and point at it",
        ))

    # --- internal consistency ---------------------------------------------------------------
    if status == "SPECULATED" and claimed in ABOVE_LOW and finding_class == "technical":
        violations.append(Violation(
            rid, "SPECULATED_ABOVE_LOW",
            f"record is SPECULATED yet rated {claimed}",
            "a claim that is not proven cannot carry an above-Low technical severity; "
            "verify it or lower the severity",
            blocking=False,
        ))

    # --- the environment cap's audit trail (RG-1 §6) -----------------------------------------
    #
    # `production_nexus` is the one field that can *raise* what a client is told relative to the
    # cap, so it is the one field an under-specified value must not be able to quietly exercise.
    nexus = record.get("production_nexus")
    # Turning the `code_defect` default off costs the same ceremony every other override in RG-1
    # costs. It used to cost nothing: `production_nexus: null` on a whitebox record suppressed the
    # default with no reason, no `by`, no evidence and no violation, while
    # `environment_discrepancy_resolution` four functions up demands a closed-vocabulary decision
    # *and* a non-empty reason for an override of exactly the same kind (adversarial review, S6).
    # A bypass that is cheaper than the thing it bypasses is the free-text escape hatch this
    # vocabulary exists to close.
    if nexus is None and "production_nexus" in record \
            and str(record.get("discovered_by", "")) in CODE_DEFECT_PRODUCERS:
        cleared = record.get("code_defect_cleared")
        reason = cleared.get("reason") if isinstance(cleared, dict) else None
        if not isinstance(reason, str) or not reason.strip():
            violations.append(Violation(
                rid, "CODE_DEFECT_CLEARED_WITHOUT_REASON",
                "the code_defect default was cleared with `production_nexus: null` but nothing "
                "says why this code never runs in production",
                "add `code_defect_cleared: {reason: ..., by: ...}`. The environment of a "
                "source-code finding is the code, not the box it was read on, so clearing the "
                "default is a claim that this particular code is dev-only -- a test fixture, a "
                "seed script, a compose.dev.yaml. State it. Four characters must not be enough "
                "to take a critical to a medium",
            ))
    if nexus is not None:
        if not isinstance(nexus, dict):
            violations.append(Violation(
                rid, "PRODUCTION_NEXUS_UNRECOGNISED",
                f"production_nexus must be an object or null, got {type(nexus).__name__}",
                f"use {{kind: <one of {', '.join(PRODUCTION_NEXUS_KINDS)}>, evidence_ptr: ...}}, "
                "or null to record that there is no production nexus",
            ))
        else:
            kind = nexus.get("kind")
            if kind not in PRODUCTION_NEXUS_KINDS:
                violations.append(Violation(
                    rid, "PRODUCTION_NEXUS_UNRECOGNISED",
                    f"production_nexus.kind {kind!r} is not a recognised kind",
                    f"use one of: {', '.join(PRODUCTION_NEXUS_KINDS)}. The environment cap is "
                    "bypassed while this is unreadable -- the severity is not quietly reduced by "
                    "a field nobody can parse -- but the record cannot reach a client until it "
                    "names a kind that exists",
                ))
            nexus_ptr = nexus.get("evidence_ptr")
            nexus_ok, nexus_reason = (False, "production_nexus carries no evidence_ptr") \
                if not nexus_ptr else resolve_evidence(str(nexus_ptr), root)
            if not nexus_ok:
                violations.append(Violation(
                    rid, "PRODUCTION_NEXUS_UNRESOLVED", nexus_reason,
                    "a nexus claim is what lifts this record above the environment cap, so it "
                    "carries its own resolving evidence pointer -- the credential, the production "
                    "data, the shared component or the code path. A bypass supported by prose is "
                    "the free-text escape hatch this vocabulary exists to close",
                ))

    # --- ENVIRONMENT_DISCREPANCY (§4.2), sited where the observation lands --------------------
    signals = record.get("env_signals")
    if isinstance(signals, list):
        for signal in signals:
            kind = signal.get("kind") if isinstance(signal, dict) else signal
            if kind not in ENVIRONMENT_SIGNAL_KINDS:
                violations.append(Violation(
                    rid, "ENVIRONMENT_SIGNAL_UNRECOGNISED",
                    f"env_signals entry {kind!r} is not a recognised signal kind",
                    f"use one of: {', '.join(ENVIRONMENT_SIGNAL_KINDS)}. An unrecognised signal "
                    "is recorded and never produces a verdict -- a rule that can fire on a value "
                    "nobody defined is a rule with no meaning",
                    blocking=False,
                ))
    contradicting = blocking_env_signals(record)
    if contradicting and str(record.get("environment_at_test", "")) == "production" \
            and discrepancy_resolution(record) is None:
        kinds = ", ".join(sorted({str(s.get("kind")) for s in contradicting}))
        violations.append(Violation(
            rid, "ENVIRONMENT_DISCREPANCY",
            f"declared environment_at_test 'production', but the asset emitted {kinds}",
            "resolve this before the finding reaches a client, by recording which side was "
            "wrong: `environment_discrepancy_resolution: {decision: declaration_wrong | "
            "signal_wrong, reason: ..., by: ...}`. The classifier never sets the environment -- "
            "it only contradicts a declaration, and a declaration contradicted by the asset "
            "itself is the exact condition under which a development stack got reported as a "
            "client's production system",
        ))

    derivation = record.get("severity_derivation")
    if isinstance(derivation, dict) and isinstance(derivation.get("after_env_cap"), str):
        if str(record.get("severity", "")) != derivation["after_env_cap"]:
            violations.append(Violation(
                rid, "DERIVATION_MISMATCH",
                f"severity {record.get('severity')!r} does not equal "
                f"severity_derivation.after_env_cap {derivation['after_env_cap']!r}",
                "the derivation is the audit trail that makes a disposition reproducible from "
                "the record alone. Re-run the scorer rather than editing `severity` by hand -- "
                "a hand-edited severity is exactly what this catches",
            ))
    # The same control, on the path that produces the client's document. `report.classify` runs
    # the cap over the whole corpus before validating anything, so the comparison above is equal
    # by construction there and DERIVATION_MISMATCH could not fire on the only path a client's
    # document travels. The cap stamps this key when it finds a severity beneath the one its own
    # earlier run recorded -- the flattering direction, corroborated by nothing.
    if isinstance(derivation, dict) and isinstance(derivation.get("derivation_conflict"), dict):
        conflict = derivation["derivation_conflict"]
        violations.append(Violation(
            rid, "DERIVATION_MISMATCH",
            f"severity {conflict.get('record_severity')!r} is below the "
            f"{conflict.get('recorded_after_env_cap')!r} this record's own severity_derivation "
            "recorded, so it was lowered by something other than the scorer",
            "re-run the scorer rather than editing `severity` by hand. Raising a severity after "
            "rg-verify re-executes a finding is the §10.3 workflow and needs nothing; lowering "
            "one below its own audit trail is the direction that flatters us, and it has to be "
            "the scorer's output or an explicit re-score, not an edit",
        ))

    if isinstance(derivation, dict) \
            and isinstance(derivation.get("environment_declaration_conflict"), dict):
        conflict = derivation["environment_declaration_conflict"]
        violations.append(Violation(
            rid, "ENVIRONMENT_DECLARATION_CONFLICT",
            f"record declares environment_at_test "
            f"{conflict.get('record_declared')!r} while the signed scope declares "
            f"{conflict.get('engagement_declared')!r}, which is the direction that lowers the "
            "cap. The scope was used and this record's declaration was not",
            "a record may raise its own environment freely -- that discloses. Lowering it below "
            "the signed scope costs the same ceremony §4.2 demands in the other direction: "
            "`environment_discrepancy_resolution: {decision: declaration_wrong | signal_wrong, "
            "reason: ..., by: ...}`. One agent-written key must not be enough to take a critical "
            "to a low on a production engagement",
            blocking=False,
        ))

    impact = record.get("real_world_impact")
    if finding_class == "technical" and severity in ABOVE_LOW and not impact:
        violations.append(Violation(
            rid, "NO_IMPACT", "no real_world_impact stated for an above-Low technical finding",
            "state the concrete impact -- 'can read any user's email address', not "
            "'may lead to data exposure' (§10.4 gate 3)",
            blocking=False,
        ))

    return RecordResult(rid, violations)


# --------------------------------------------------------------------------------------------
# Legacy normalisation
# --------------------------------------------------------------------------------------------
#
# Records from a pre-RedGold engagement use a different vocabulary. Validating them raw produces
# the wrong result in the most misleading way available: hundreds of cosmetic complaints about id
# format and missing fields, and *silence* on the substantive rules, because the rules key off a
# `finding_class` field those records do not have.
#
# Normalising first is what makes the acceptance test meaningful -- the point is to flag the real
# gaps, not to prove the schema changed.

LEGACY_SEVERITY_MAP = {
    # "positive" recorded a control that held. That is a first-class result (§10.6) but it is not
    # a vulnerability severity, so it maps to informational rather than being rejected.
    "positive": "info",
}
LEGACY_CONFIDENCE_MAP = {"high": "confirmed", "medium": "probable", "low": "unconfirmed"}

SUPERSEDES_RE = re.compile(r"[Rr]esolves\s+([A-Z][A-Z0-9]*-[A-Z]?\d+)")
REFERENCE_ID_RE = re.compile(r"\b([A-Z][A-Z0-9]*-[A-Z]?\d+)\b")


def normalise_legacy(record: dict) -> dict:
    """Map a pre-RedGold record into the current vocabulary.

    The honest mapping for `verified` is **"none"**. That engagement had no independent
    re-execution step -- `rg-verify` did not exist -- so claiming anything stronger would launder
    the exact gap this validator is meant to expose. High `confidence` is a model's self-report,
    which is not verification.
    """
    out = dict(record)
    out.setdefault("finding_class", "technical")
    out.setdefault("verified", "none")

    severity = str(record.get("severity", "")).lower()
    out["severity"] = LEGACY_SEVERITY_MAP.get(severity, severity)

    confidence = str(record.get("confidence", "")).lower()
    if confidence in LEGACY_CONFIDENCE_MAP:
        out["confidence"] = LEGACY_CONFIDENCE_MAP[confidence]

    return out


def validate_corpus(records: list[dict]) -> list[Violation]:
    """Checks that only make sense across the whole set of findings, not one record at a time.

    Two rules, both of which a per-record validator structurally cannot catch:

    1. **Superseded-but-stale.** A later record states it resolves an earlier one, while the
       earlier record still says SPECULATED. The engagement learned the answer and the finding
       never got updated -- so a report generated from these files would tell the client an open
       question is open when it was closed.

    2. **Rollup double-counting.** A synthesis record that references constituent records will be
       counted twice if the files are naively concatenated, inflating the finding count.
    """
    violations: list[Violation] = []
    by_id = {str(r.get("id")): r for r in records if isinstance(r, dict) and r.get("id")}

    for record in records:
        if not isinstance(record, dict):
            continue
        source_id = str(record.get("id", "<no-id>"))

        for key, value in record.items():
            if key == "references" or not isinstance(value, str):
                continue
            for target_id in SUPERSEDES_RE.findall(value):
                target = by_id.get(target_id)
                if target is None:
                    continue
                if str(target.get("status", "")).upper() == "SPECULATED":
                    violations.append(Violation(
                        target_id, "STALE_SUPERSEDED",
                        f"still marked SPECULATED, but {source_id} states it resolves this "
                        f"(in '{key}')",
                        f"update {target_id} to reflect what {source_id} established, or remove "
                        "the supersession claim. A report built from these files would tell the "
                        "client an open question is still open.",
                    ))

        # Constituent references live in free text, not in `references` -- that field holds
        # external URLs. So scan the same text fields the supersession check reads.
        #
        # `evidence_ptr` is excluded: an evidence filename legitimately contains a record id
        # (`evidence/F-001-anon-read.http`), and reading that as "F-002 synthesises F-001" would
        # silently drop a real finding from the report as a double-count. A file path is not a
        # claim of synthesis.
        skip = {"references", "evidence_ptr", "id"}
        text = " ".join(v for k, v in record.items()
                        if isinstance(v, str) and k not in skip)
        constituents = sorted({t for t in REFERENCE_ID_RE.findall(text)
                               if t in by_id and t != source_id})
        if constituents:
            violations.append(Violation(
                source_id, "ROLLUP",
                f"references {', '.join(constituents)} -- counting both this and those "
                "double-counts the same issue",
                "mark this as a rollup so the report counts it once, or drop the "
                "constituent records from the client-facing list",
                blocking=False,
            ))

    return violations


def extract_records(document: Any) -> list[Any]:
    """Pull findings records out of a document, tolerating the shapes these files come in.

    Accepts a bare list, or an object with a findings-ish key. Anything else yields nothing,
    and the caller reports that as a defect rather than silently validating zero records --
    "no findings found" must never be indistinguishable from "all findings passed".
    """
    if isinstance(document, list):
        return document
    if isinstance(document, dict):
        for key in ("findings", "records", "results", "risks", "issues"):
            value = document.get(key)
            if isinstance(value, list):
                return value
    return []


def load_records(path: Path, *, legacy: bool = False) -> tuple[list[Any], list[str]]:
    try:
        document = json.loads(path.read_text(encoding="utf-8", errors="replace"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return [], [f"{path.name}: cannot be read as JSON ({exc})"]

    records = extract_records(document)
    if not records:
        return [], [f"{path.name}: no findings records found -- is the top-level shape right?"]

    if legacy:
        records = [normalise_legacy(r) if isinstance(r, dict) else r for r in records]
    return records, []


def validate_file(path: Path, root: Path, *, legacy: bool = False) -> tuple[list[RecordResult], list[str]]:
    """Validate one findings file. Returns (per-record results, file-level errors)."""
    records, errors = load_records(path, legacy=legacy)
    if errors:
        return [], errors
    return [validate_record(r, root, strict_id=not legacy) for r in records], []
