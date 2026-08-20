#!/usr/bin/env python3
"""baseline_scan.py -- the deterministic baseline (spec P10).

Build order step 5b.

WHY A SCRIPT AND NOT AN AGENT
-----------------------------
In an independent evaluation (Wavestone/RiskInsight, 2026) an agentic pentester **fabricated a
critical JWT algorithm-confusion finding with a proof-of-exploit that did not work**, while
**missing an exposed admin interface protected by default credentials** -- "a vulnerability no
human pentester would overlook". The same evaluation records prolonged fixation on one irrelevant
path at the expense of coverage.

So: agentic judgement decides *where to look next*. It must never decide *whether to check the
obvious*. This checklist is fixed, runs on every engagement, and runs **before any fingerprint is
known** -- it is deliberately not playbook-dispatched, because dispatch is conditional and that is
the opposite of what this principle requires.

Negative results are recorded. "Checked for an exposed .git, absent" is a first-class output: it
is what lets the report make an honest coverage claim (P11).

EVERY CHECK IS TIER 1
---------------------
Unauthenticated GETs a normal visitor could make. No writes, no payloads, no credentials. The
scan additionally re-checks each target against the boundary itself before probing -- it is
normally invoked through Bash and so already passes under `scope_guard.py`, but a control that
assumes it is being supervised is not much of a control.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

import findings as findings_mod  # noqa: E402  -- one implementation of the environment cap
import scope as scope_mod  # noqa: E402
import scope_guard  # noqa: E402

USER_AGENT = "RedGold-baseline/1.0 (authorized security assessment)"
TIMEOUT = 10


@dataclass
class Probe:
    status: int | None
    headers: dict[str, str]
    body: str
    error: str | None = None


def fetch(url: str, *, method: str = "GET") -> Probe:
    request = urllib.request.Request(url, method=method, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            body = response.read(65536).decode("utf-8", errors="replace")
            return Probe(response.status, {k.lower(): v for k, v in response.headers.items()}, body)
    except urllib.error.HTTPError as exc:
        body = exc.read(65536).decode("utf-8", errors="replace") if exc.fp else ""
        return Probe(exc.code, {k.lower(): v for k, v in (exc.headers or {}).items()}, body)
    except Exception as exc:  # noqa: BLE001 -- a failed probe is a result, not a crash
        return Probe(None, {}, "", error=f"{type(exc).__name__}: {exc}")


# --------------------------------------------------------------------------------------------
# The checklist
# --------------------------------------------------------------------------------------------


@dataclass
class Check:
    key: str
    path: str
    title: str
    severity: str
    detect: Callable[[Probe], bool]
    impact: str
    remediation: str
    finding_class: str = "technical"


def _looks_like_env(probe: Probe) -> bool:
    return probe.status == 200 and bool(re.search(r"^[A-Z_]{3,}=\S", probe.body, re.MULTILINE))


def _looks_like_git_config(probe: Probe) -> bool:
    return probe.status == 200 and "[core]" in probe.body


def _directory_listing(probe: Probe) -> bool:
    return probe.status == 200 and bool(
        re.search(r"<title>Index of /|Directory listing for", probe.body, re.IGNORECASE))


def _admin_reachable(probe: Probe) -> bool:
    # 401/403 means it exists and is guarded -- that is the control working, not a finding.
    return probe.status == 200


def _bucket_listing(probe: Probe) -> bool:
    """A storage listing returned to an unauthenticated caller.

    Deliberately shape-based rather than vendor-specific: this check must fire before any
    fingerprint is known, so it cannot key off "this is Supabase".
    """
    if probe.status != 200:
        return False
    try:
        payload = json.loads(probe.body)
    except (json.JSONDecodeError, ValueError):
        return False
    if isinstance(payload, dict):
        payload = payload.get("items") or payload.get("objects") or payload.get("data") or []
    if not isinstance(payload, list) or not payload:
        return False
    entry_keys = {"name", "id", "key", "updated_at", "created_at", "metadata", "size"}
    return any(isinstance(item, dict) and entry_keys & set(item) for item in payload)


def _source_map_exposed(probe: Probe) -> bool:
    return probe.status == 200 and ('"sources"' in probe.body or '"mappings"' in probe.body)


def _wildcard_cors(probe: Probe) -> bool:
    origin = probe.headers.get("access-control-allow-origin", "")
    credentials = probe.headers.get("access-control-allow-credentials", "").lower()
    return origin == "*" and credentials == "true"


CHECKS: list[Check] = [
    Check("env_exposed", "/.env", "Environment file served to anonymous visitors", "critical",
          _looks_like_env,
          "Anyone on the internet can read the application's configuration, which routinely "
          "includes database credentials and API keys.",
          "Remove the file from the deployed bundle and rotate every credential it contained."),
    Check("git_exposed", "/.git/config", "Git metadata served to anonymous visitors", "high",
          _looks_like_git_config,
          "The repository's history can be reconstructed, including secrets removed in later "
          "commits.",
          "Block .git at the web server or remove it from the deployment artifact."),
    Check("dir_listing", "/", "Directory listing enabled", "low", _directory_listing,
          "File and directory names are enumerable, which speeds up finding everything else.",
          "Disable automatic directory indexes."),
    Check("admin_open", "/admin", "Admin interface reachable without authentication", "critical",
          _admin_reachable,
          "An administrative interface answers anonymous requests with content rather than a "
          "login challenge.",
          "Put the interface behind authentication and restrict it by network where possible."),
    Check("ghost_admin_open", "/ghost/api/admin/site/", "Admin API reachable anonymously", "high",
          _admin_reachable,
          "An administrative API endpoint answers unauthenticated requests.",
          "Require authentication on every administrative route."),
    Check("actuator_open", "/actuator/env", "Diagnostic endpoint exposed", "high",
          _admin_reachable,
          "A diagnostics endpoint exposes runtime configuration to anonymous callers.",
          "Disable diagnostics in production or bind them to localhost."),
    Check("bucket_public", "/storage/v1/object/list/public",
          "Object storage listing readable anonymously", "high", _bucket_listing,
          "Stored objects can be enumerated by anyone, with no login. Where those objects are "
          "user photos or documents, this exposes real people's data directly.",
          "Set the bucket to private and serve objects through signed, expiring URLs."),
    Check("sourcemap", "/static/js/main.js.map", "Source map published", "low",
          _source_map_exposed,
          "The application's original source is recoverable from the deployed bundle.",
          "Stop shipping source maps to production, or restrict them."),
    Check("wildcard_cors", "/", "Wildcard CORS with credentials", "high", _wildcard_cors,
          "Any origin can make credentialed cross-site requests and read the responses.",
          "Replace the wildcard with an explicit origin allowlist."),
]

# Header posture is evaluated from the root response rather than its own request.
SECURITY_HEADERS = {
    "strict-transport-security": "HSTS not set; a downgrade to plaintext is not prevented",
    "content-security-policy": "no CSP; injected script has no second line of defence",
    "x-content-type-options": "MIME sniffing not disabled",
}

# --------------------------------------------------------------------------------------------
# Applicability (RG-1 §4.1). Two different reasons a check does not run, kept distinguishable.
#
#   no_http_response      the service never answered an HTTP request, so nothing was sent to it.
#                         That IS a coverage gap: the service is unassessed.
#   scheme_inapplicable   the check is structurally meaningless against this origin, so there was
#                         nothing to send. That is NOT a coverage gap, and reporting it as one
#                         would manufacture a hole in a report that does not have one.
#
# Collapsing the two into a single "not applicable" bucket is how "we could not look" and "there
# was nothing to look for" become indistinguishable to a reader, and P11 turns on that distinction.
# --------------------------------------------------------------------------------------------

NOT_APPLICABLE_REASONS = frozenset({"no_http_response", "scheme_inapplicable"})


def header_applicable(base: str, header: str) -> bool:
    """Is this header check meaningful against this origin? (RG-1 §4.1a)

    Strict-Transport-Security delivered over plaintext is ignored by user agents: the header only
    has meaning on a connection an attacker cannot already read. Demanding it of a plain-HTTP
    origin is a category error, and the impact string the check generates -- "a downgrade to
    plaintext is not prevented" -- contradicts itself on a connection that is already plaintext.
    A live engagement filed two such findings against two plaintext services.

    Deliberately narrow: one header, one scheme. Any wider and this stops being an applicability
    rule and starts being a coverage loss.
    """
    if header == "strict-transport-security":
        return urllib.parse.urlsplit(base).scheme != "http"
    return True


def header_check(header: str, consequence: str) -> Check:
    return Check(
        f"header_{header.replace('-', '_')}", "/",
        f"Security header missing: {header}", "low",
        lambda _p: False, consequence,
        f"Set the {header} response header.",
        finding_class="posture",
    )


def all_check_keys() -> list[str]:
    """Every check key the baseline would run against a service that answers HTTP."""
    return ([c.key for c in CHECKS]
            + [f"header_{h.replace('-', '_')}" for h in SECURITY_HEADERS])


# --------------------------------------------------------------------------------------------
# Environment signals (RG-1 §2.4) -- observations, never conclusions.
#
# These are the only two of §2.4's four blocking signals a black-box HTTP probe can actually see.
# A framework debug page and a certificate subject need a different vantage point and are NOT
# implemented here; recording that plainly is better than a table that implies coverage it does
# not have. `x-vercel-deployment-url` is deliberately absent: it is a *request* header Vercel
# injects on the way in to a customer's function, so a scanner standing outside the deployment
# never observes it on preview or on production. A rule that can never fire is worse than a wrong
# rule, because it reads as coverage. `server: Vercel` is not a substitute -- it was present on
# four production responses, so a classifier keyed on it would fire on every Vercel production
# engagement, which is the disabled-gate failure arriving through the replacement signal.
#
# The classifier may contradict a declaration. It may never set one.
# --------------------------------------------------------------------------------------------

# **Secret** test keys only. `pk_test_` is a *publishable* key: it is designed to be embedded in
# a page, and is routinely present on production documentation pages, "try it" widgets and SDK
# landing pages. Treating it identically to `sk_test_` made this blocking signal fire on healthy
# production traffic -- and this gate's action clause holds every finding on the asset out of the
# client report body, so a false positive here is a suppression event, not a nuisance
# (adversarial review, S7). A blocking signal needs one meaning; only the secret prefix has one.
TEST_KEY_RE = re.compile(r"\bsk_test_[A-Za-z0-9]{8,}")
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)

FINGERPRINT_HEADERS = ("server", "x-powered-by")
# Matched in a server banner, where the string is the service identifying itself. `vite`,
# `mailtrap` and `flower` are deliberately absent for the same reason they are absent from the
# title list below -- Flower is a *production* Celery monitoring UI, Mailtrap and Vite are
# ordinary products with ordinary production sites, and all three were matched here as bare
# substrings of the concatenated banner. The reasoning was written out for the title list and
# never crossed the two-line gap to this one.
DEV_TOOL_HEADER_TOKENS = ("mailpit", "mailhog", "mailcatcher", "adminer",
                          "webpack-dev-server")
# Matched in a page title, where a false positive is a real risk. Only service UIs whose title is
# the product name, and deliberately NOT `vite` (a Vite-built SPA deployed to production commonly
# still ships the default `<title>Vite App</title>` -- that is a build tool, not a dev server) or
# `mailtrap`/`flower`, which have ordinary marketing sites someone could legitimately host.
DEV_TOOL_TITLE_TOKENS = ("mailpit", "mailhog", "mailcatcher", "adminer")

EMITTED_SIGNAL_KINDS = ("test_payment_key", "dev_tool_fingerprint")


def env_signals(probe: Probe) -> list[dict]:
    """Non-production signals observable in one HTTP response. Silent when absent."""
    signals: list[dict] = []
    match = TEST_KEY_RE.search(probe.body or "")
    if match:
        signals.append({
            "kind": "test_payment_key",
            "detail": f"{match.group(0)[:11]}... in the response body",
        })
    banner = " ".join(str(probe.headers.get(h, "")) for h in FINGERPRINT_HEADERS).lower()
    title = " ".join(TITLE_RE.findall(probe.body or "")).lower()
    tool = next((t for t in DEV_TOOL_HEADER_TOKENS if t in banner), None) \
        or next((t for t in DEV_TOOL_TITLE_TOKENS if t in title), None)
    if tool:
        signals.append({"kind": "dev_tool_fingerprint", "detail": f"{tool} identified itself"})
    return signals


def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


NOT_APPLICABLE_TEXT = {
    "no_http_response": (
        "NOT TESTED: {base} did not answer an HTTP request ({detail}), so the {count} HTTP-shaped "
        "checks of the baseline checklist were never sent to it ({keys}). This is a coverage gap, "
        "not a clean result -- the service is unassessed."),
    "scheme_inapplicable": (
        "NOT APPLICABLE: {base} is a plaintext origin, and this check has no meaning over "
        "plaintext ({detail}). Nothing was sent and nothing is claimed. This is not a coverage "
        "gap and not a clean result: there was no question to ask here."),
}


def make_not_applicable(index: int, base: str, check: Check, probe: Probe, *, reason: str,
                        skipped_checks: list[str], detail: str | None = None) -> dict:
    """One record for checks that were **not performed**, and the reason they were not.

    Two distinct reasons, because they say opposite things to a client (`NOT_APPLICABLE_REASONS`).

    `skipped_checks` may name many checks in one record. A live engagement emitted **36**
    `not_applicable` records -- the cartesian product of a twelve-item checklist with three
    services that never answered HTTP -- for what is one coverage fact about three assets. A
    cartesian product is not a set of results. The count is preserved in `checks_skipped` so that
    collapsing the records does not shrink the reported gap: the honest number is twelve checks
    that did not run, stored once instead of twelve times.
    """
    if reason not in NOT_APPLICABLE_REASONS:
        raise ValueError(f"unrecognised not_applicable reason {reason!r}")
    return {
        "id": f"F-{index:03d}",
        "asset": base,
        "title": check.title,
        "finding_class": check.finding_class,
        "status": "SPECULATED",
        # Not "n/a": nothing was observed here at all, and the schema reserves "n/a" for
        # posture facts that have no exploit to replay (§10.3).
        "verified": "none",
        "confidence": "unconfirmed",
        "severity": "info",
        "evidence_ptr": f"evidence/F-{index:03d}-{check.key}.http",
        "real_world_impact": NOT_APPLICABLE_TEXT[reason].format(
            base=base,
            detail=detail or probe.error or "no HTTP response",
            count=len(skipped_checks),
            keys=", ".join(skipped_checks),
        ),
        "remediation": ("Re-test this service with a tool that speaks its protocol."
                        if reason == "no_http_response" else "None required."),
        "tested_at_tier": 1,
        "result": "not_applicable",
        "not_applicable_reason": reason,
        "skipped_checks": list(skipped_checks),
        "checks_skipped": len(skipped_checks),
        "discovered_by": "baseline_scan",
        "created": now(),
    }


def make_finding(index: int, base: str, check: Check, probe: Probe, *, present: bool,
                 applicable: bool = True) -> dict:
    """Build a schema-conformant record. Negatives are recorded too (P10, P11).

    `applicable=False` records a check that was **not performed** -- the service did not answer an
    HTTP request at all, so an HTTP-shaped check could not be sent to it. That is deliberately not
    "absent": absent means the request went out and the condition was not there, and rendering an
    unsent check as absent manufactures a false negative and inflates the coverage claim. The gap
    is written down loudly instead (P11).
    """
    if not applicable:
        return make_not_applicable(index, base, check, probe, reason="no_http_response",
                                   skipped_checks=[check.key])
    return {
        "id": f"F-{index:03d}",
        "asset": base,
        "title": check.title,
        "finding_class": check.finding_class,
        "status": "PROVEN" if present else "SPECULATED",
        # An automated GET that observed the condition is a mechanical demonstration.
        "verified": "executed" if present else "none",
        "confidence": "confirmed" if present else "unconfirmed",
        "severity": check.severity if present else "info",
        "evidence_ptr": f"evidence/F-{index:03d}-{check.key}.http",
        "real_world_impact": check.impact if present else
        f"Checked for {check.title.lower()}; not present.",
        "remediation": check.remediation if present else "None required.",
        "tested_at_tier": 1,
        "result": "present" if present else "absent",
        "discovered_by": "baseline_scan",
        "created": now(),
    }


def write_evidence(root: Path, index: int, check: Check, url: str, probe: Probe) -> None:
    path = root / "evidence" / f"F-{index:03d}-{check.key}.http"
    path.parent.mkdir(parents=True, exist_ok=True)
    lines = [f"GET {url}", f"User-Agent: {USER_AGENT}", ""]
    if probe.error:
        lines.append(f"[no response] {probe.error}")
    else:
        lines.append(f"HTTP {probe.status}")
        lines.extend(f"{k}: {v}" for k, v in sorted(probe.headers.items()))
        lines.append("")
        lines.append(probe.body[:4000])
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


TLS_PORTS = frozenset({443, 8443})


def row_port(row: dict) -> int | None:
    port = row.get("port")
    if isinstance(port, bool):
        return None
    if isinstance(port, int):
        return port
    if isinstance(port, str) and port.strip().isdigit():
        return int(port.strip())
    return None


def base_url(identifier: str, port: int | None) -> str:
    """(host, port) -> the URL the scan will actually address.

    The register stores the bare host in `identifier` and the port in its own field, because an
    asset is identified by (host, port) -- see `scope_cli.normalise_identifier`. Rebuilding the
    base from the identifier alone drops the port, which is how six distinct services behind one
    hostname collapsed into six scans of the same bare host.
    """
    scheme = "https"
    if "://" in identifier:
        parsed = urllib.parse.urlsplit(identifier)
        host = (parsed.hostname or "").lower()
        scheme = parsed.scheme or "https"
        port = parsed.port if parsed.port is not None else port
    else:
        host = identifier.strip().lower().rstrip(".")
        if port is not None and port not in TLS_PORTS:
            scheme = "http"
    if ":" in host and not host.startswith("["):  # IPv6 literal
        host = f"[{host}]"
    return f"{scheme}://{host}" + (f":{port}" if port is not None else "")


def confirmed_targets(root: Path, boundary: scope_mod.Scope) -> list[str]:
    """CONFIRMED register rows only (§5.4). The baseline does not discover its own targets."""
    register = root / "assets" / "register.jsonl"
    if not register.is_file():
        return []
    targets: list[str] = []
    seen: set[tuple[str, int | None]] = set()
    for line in register.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        if row.get("status") != "CONFIRMED":
            continue
        identifier = row.get("identifier")
        if not isinstance(identifier, str):
            continue
        base = base_url(identifier, row_port(row)).rstrip("/")
        parsed = urllib.parse.urlsplit(base)
        key = (parsed.hostname or "", parsed.port)
        if key in seen:
            # Two rows for the same service scan it twice, and every finding is then filed twice
            # under two ids. Deduplication is on (host, port) -- never on the host alone.
            continue
        seen.add(key)
        targets.append(base)
    return targets


def alternate_scheme(base: str) -> str | None:
    """The same (host, port) over the other scheme, or None if the port is implicit.

    Only ever applied where the port is explicit: swapping the scheme on a base without one
    changes 443 to 80, which is a different service and therefore a different asset.
    """
    parsed = urllib.parse.urlsplit(base)
    if parsed.port is None:
        return None
    other = "http" if parsed.scheme == "https" else "https"
    return f"{other}://{parsed.netloc}"


def probe_root(base: str) -> tuple[str, Probe]:
    """Probe-then-decide: does this service answer HTTP at all, and over which scheme?

    A port number is not evidence of a protocol. A static "HTTP ports" allowlist would have
    skipped the Mailpit listeners on 8025/8026 and the Ghost app on 2368 -- exactly the silent
    coverage loss this is here to prevent. So the scan asks the service instead, and the answer
    is what decides whether the HTTP checklist applies.
    """
    probe = fetch(base + "/")
    if probe.status is not None:
        return base, probe
    alternate = alternate_scheme(base)
    if alternate is None:
        return base, probe
    alternate_probe = fetch(alternate + "/")
    if alternate_probe.status is not None:
        return alternate, alternate_probe
    scheme = urllib.parse.urlsplit(base).scheme
    other = urllib.parse.urlsplit(alternate).scheme
    return base, Probe(None, {}, "", error=(
        f"over {scheme}: {probe.error}; over {other}: {alternate_probe.error}"))


def in_boundary(boundary: scope_mod.Scope, url: str) -> bool:
    for host, port in scope_guard._targets_in_text(url):
        if any(scope_guard.entry_matches_target(e, host, port) for e in boundary.out_of_scope):
            return False
        if not any(scope_guard.entry_matches_target(e, host, port) for e in boundary.in_scope):
            return False
    return True


def scan(root: Path, *, targets: list[str] | None = None, start_index: int = 1) -> list[dict]:
    boundary = scope_mod.load(root / "scope.yaml")
    # RG-1 §6/E1. The environment at the moment of the test is a fact about the test, so it is
    # stamped and the cap applied as each record is written -- not recomputed later from whatever
    # scope.yaml happens to say by then. An undeclared or unrecognised value resolves to
    # `production`, which is uncapped: an unanswered question must never be the reason a client
    # is told less. The refusal for an unanswered question belongs to Gate 1.
    environment = scope_mod.effective_environment(boundary.environment)
    bases = targets if targets is not None else confirmed_targets(root, boundary)
    records: list[dict] = []
    signals_by_asset: dict[str, list[dict]] = {}
    index = start_index

    for base in bases:
        if not in_boundary(boundary, base):
            print(f"SKIP {base}: outside the authorization boundary", file=sys.stderr)
            continue

        base, root_probe = probe_root(base)
        # The service answered HTTP, or it did not. Nothing below pretends otherwise.
        applicable = root_probe.status is not None
        if not applicable:
            # RG-1 §4.1b: the whole checklist short-circuits to ONE record naming every check it
            # stands for, instead of one record per (check x dead asset). The loops below are not
            # entered at all -- the collapse is structural, not a filter applied afterwards.
            print(f"NOT HTTP {base}: {root_probe.error} -- the HTTP checklist does not apply "
                  "here and is recorded as not tested, not as absent", file=sys.stderr)
            unreachable = Check(
                "unreachable", "/",
                "Baseline HTTP checklist not performed: service does not answer HTTP", "low",
                lambda _p: False, "", "", finding_class="technical",
            )
            write_evidence(root, index, unreachable, base + "/", root_probe)
            records.append(make_not_applicable(
                index, base, unreachable, root_probe,
                reason="no_http_response", skipped_checks=all_check_keys()))
            index += 1
            continue

        observed = env_signals(root_probe)
        if observed:
            signals_by_asset[base] = observed

        for check in CHECKS:
            url = base + check.path
            probe = root_probe if check.path == "/" else fetch(url)
            present = check.detect(probe)
            write_evidence(root, index, check, url, probe)
            records.append(
                make_finding(index, base, check, probe, present=present, applicable=True))
            index += 1

        for header, consequence in SECURITY_HEADERS.items():
            check = header_check(header, consequence)
            write_evidence(root, index, check, base + "/", root_probe)
            if not header_applicable(base, header):
                # RG-1 §4.1a. Recorded, never silently dropped: a check that was skipped for a
                # structural reason and a check that was never thought of must not look the same.
                records.append(make_not_applicable(
                    index, base, check, root_probe, reason="scheme_inapplicable",
                    skipped_checks=[check.key],
                    detail="HSTS served over plaintext is ignored by user agents"))
                index += 1
                continue
            record = make_finding(index, base, check, root_probe,
                                  present=header not in root_probe.headers, applicable=True)
            # Header posture is an observed configuration fact, not a replayable exploit (§10.3).
            record["verified"] = "n/a"
            records.append(record)
            index += 1

    # One pass, one implementation, shared with `report.classify` -- two independent cap
    # implementations would be two things to keep in step, and the one that drifted would be the
    # one nobody noticed.
    for record in records:
        findings_mod.apply_environment_cap(record, environment)
        for signal in signals_by_asset.get(record["asset"], []):
            record.setdefault("env_signals", []).append(dict(signal))

    # RG-1 §4.2. One blocker per contradicted asset, not one per finding: the operator has one
    # decision to make -- which side was wrong -- and twelve copies of it is a queue, not a
    # decision. `validate_record` holds the affected findings out of the report body meanwhile.
    for base, signals in sorted(signals_by_asset.items()):
        if environment != "production" or not signals:
            continue
        kinds = ", ".join(sorted({s["kind"] for s in signals}))
        raise_blocker(root, base, kinds, signals)
    return records


def blocker_id(base: str) -> str:
    """A stable id for this asset's blocker.

    Was `f"B-{abs(hash(base)) % 1000:03d}"`. Python randomises `str.__hash__` per process, so
    re-running the scan re-raised the same asset's blocker under a new id -- `ledger/blockers.jsonl`
    accumulated duplicates and `gate_cli.py resolve` could never stick to the asset, making the
    discrepancy permanently unresolvable by re-scan. Two distinct assets also collided at roughly
    1 in 1000 per pair, and `cmd_resolve` takes the first match, so resolving one silently
    resolved the wrong blocker and left the other unaddressed (adversarial review, S9).

    A content hash: same asset, same id, in every process, forever; and a 12-hex-digit space
    rather than a thousand slots.
    """
    return "B-" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:12]


def raise_blocker(root: Path, base: str, kinds: str, signals: list[dict]) -> None:
    path = root / "ledger" / "blockers.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "id": blocker_id(base),
            "kind": "ENVIRONMENT_DISCREPANCY",
            "raised_by": "baseline_scan",
            "asset": base,
            "detail": (
                f"scope.yaml declares environment: production, but {base} emitted {kinds}. "
                "Resolve by recording which side was wrong -- the declaration or the signal. "
                "Findings from this asset are held out of the report body until you do."),
            "signals": signals,
            "resolved": None,
            "ts": now(),
        }) + "\n")
    print(f"BLOCKER {base}: declared production, observed {kinds}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the deterministic baseline (P10).")
    parser.add_argument("--root", default=".", help="engagement directory")
    parser.add_argument("--target", action="append", default=None,
                        help="override targets (testing); defaults to CONFIRMED register rows")
    parser.add_argument("--out", default="findings/baseline.json")
    args = parser.parse_args(argv)

    root = Path(args.root).expanduser().resolve()
    try:
        records = scan(root, targets=args.target)
    except scope_mod.ScopeError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1

    if not records:
        print("No CONFIRMED in-scope assets to scan. Promote assets via /rg:scope first.",
              file=sys.stderr)
        return 1

    out_path = root / args.out
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(records, indent=2) + "\n", encoding="utf-8")

    present = [r for r in records if r["result"] == "present"]
    # The number that matters is checks skipped, not records written -- one collapsed record can
    # stand for twelve checks (RG-1 §4.1b), and printing the record count would understate the gap.
    untested = [r for r in records if r.get("not_applicable_reason") == "no_http_response"]
    print(f"Baseline complete: {len(records)} records, {len(present)} conditions present.")
    for record in present:
        print(f"  [{record['severity']:8}] {record['title']}  ({record['asset']})")
    if untested:
        assets = sorted({r["asset"] for r in untested})
        skipped = sum(r.get("checks_skipped", 1) for r in untested)
        print(f"{skipped} checks did NOT run: {', '.join(assets)} did not answer HTTP. "
              "Those services are unassessed -- not clean.")
    print(f"Written to {out_path}")
    print("Negative results are recorded too -- they are what makes the coverage claim honest.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
