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
import json
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

sys.path.insert(0, str(Path(__file__).resolve().parent))

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


def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


def make_finding(index: int, base: str, check: Check, probe: Probe, *, present: bool) -> dict:
    """Build a schema-conformant record. Negatives are recorded too (P10, P11)."""
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


def confirmed_targets(root: Path, boundary: scope_mod.Scope) -> list[str]:
    """CONFIRMED register rows only (§5.4). The baseline does not discover its own targets."""
    register = root / "assets" / "register.jsonl"
    if not register.is_file():
        return []
    targets: list[str] = []
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
        base = identifier if identifier.startswith("http") else f"https://{identifier}"
        targets.append(base.rstrip("/"))
    return targets


def in_boundary(boundary: scope_mod.Scope, url: str) -> bool:
    for host, port in scope_guard._targets_in_text(url):
        if any(scope_guard.entry_matches_target(e, host, port) for e in boundary.out_of_scope):
            return False
        if not any(scope_guard.entry_matches_target(e, host, port) for e in boundary.in_scope):
            return False
    return True


def scan(root: Path, *, targets: list[str] | None = None, start_index: int = 1) -> list[dict]:
    boundary = scope_mod.load(root / "scope.yaml")
    bases = targets if targets is not None else confirmed_targets(root, boundary)
    records: list[dict] = []
    index = start_index

    for base in bases:
        if not in_boundary(boundary, base):
            print(f"SKIP {base}: outside the authorization boundary", file=sys.stderr)
            continue

        root_probe = fetch(base + "/")

        for check in CHECKS:
            url = base + check.path
            probe = root_probe if check.path == "/" else fetch(url)
            present = check.detect(probe)
            write_evidence(root, index, check, url, probe)
            records.append(make_finding(index, base, check, probe, present=present))
            index += 1

        for header, consequence in SECURITY_HEADERS.items():
            present = header not in root_probe.headers and root_probe.status is not None
            check = Check(
                f"header_{header.replace('-', '_')}", "/",
                f"Security header missing: {header}", "low",
                lambda _p: False, consequence,
                f"Set the {header} response header.",
                finding_class="posture",
            )
            write_evidence(root, index, check, base + "/", root_probe)
            record = make_finding(index, base, check, root_probe, present=present)
            # Header posture is an observed configuration fact, not a replayable exploit (§10.3).
            record["verified"] = "n/a"
            records.append(record)
            index += 1

    return records


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
    print(f"Baseline complete: {len(records)} checks, {len(present)} conditions present.")
    for record in present:
        print(f"  [{record['severity']:8}] {record['title']}  ({record['asset']})")
    print(f"Written to {out_path}")
    print("Negative results are recorded too -- they are what makes the coverage claim honest.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
