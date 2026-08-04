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

    # --- verification rules (§10.3) ---------------------------------------------------------
    if finding_class == "technical":
        if status == "PROVEN" and verified not in VERIFIED_STRONG:
            violations.append(Violation(
                rid, "PROVEN_UNVERIFIED",
                f"technical finding is PROVEN but verified={verified or 'absent'!r}",
                "have rg-verify re-execute it and set verified to 'replayed' or 'executed', "
                "or downgrade status to SPECULATED",
            ))
        if severity in ABOVE_LOW and verified not in VERIFIED_STRONG:
            violations.append(Violation(
                rid, "UNVERIFIED_ABOVE_LOW",
                f"technical finding is severity {severity} but not independently verified",
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
    if status == "SPECULATED" and severity in ABOVE_LOW and finding_class == "technical":
        violations.append(Violation(
            rid, "SPECULATED_ABOVE_LOW",
            f"record is SPECULATED yet rated {severity}",
            "a claim that is not proven cannot carry an above-Low technical severity; "
            "verify it or lower the severity",
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
