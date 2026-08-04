#!/usr/bin/env python3
"""scope_cli.py -- the /rg:scope command (spec §5.2, §5.3, §5.4).

Asset promotion and boundary amendment.

WHY THIS EXISTS AS CODE AND NOT AS A PROCEDURE
----------------------------------------------
Promotion from CANDIDATE to CONFIRMED is the moment an asset becomes testable above tier 1. If it
happens by hand-editing a JSONL file, then the rule "never promote on a single signal" is prose --
and this project's own audit history is a list of rules that were prose.

Two things it refuses:

- **Promotion on a single attribution signal.** Qualys' published confidence cascade treats
  ASN/domain/TLS-SAN matches as high confidence and bare org-name strings as medium, because org
  strings collide across registrars, resellers and hosts. Two independent classes, or explicit
  client confirmation.

- **Promotion on an IP address alone.** Cloudflare's edge IPs are shared across every proxied
  hostname; so are Vercel's and Netlify's, which is by definition where this client base lives.
  Favicon hashes fingerprint the platform, not the owner. An IP is corroboration, never identity.

Boundary amendment is separate and louder: it changes what was authorised, so it demands a written
reason and lands in `ledger/gates.jsonl`.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import ipaddress
import json
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scope as scope_mod  # noqa: E402
import scope_guard  # noqa: E402

SIGNAL_CLASSES = (
    "RDAP_REGISTRANT", "ASN_OWNER", "TLS_SAN", "CT_COOCCURRENCE", "DNS_CNAME_CHAIN",
    "CONTENT_FP", "ANALYTICS_ID", "COPYRIGHT_STRING", "AUTHENTICATED_CONFIRM", "CLIENT_CONFIRMED",
)

# Note what is NOT in SIGNAL_CLASSES: there is no IP class, deliberately. An IP address cannot be
# recorded as an attribution signal at all, so "IP never counts on its own" is enforced by the
# vocabulary rather than by a rule someone has to remember. `reject_ip_valued_signal` closes the
# remaining hole -- recording an IP as the *value* of some other class.

# A direct statement from the client is self-sufficient (§5.3).
SELF_SUFFICIENT = frozenset({"CLIENT_CONFIRMED"})


class ScopeCliError(Exception):
    """Refusal. Always actionable."""


def now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")


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
            raise ScopeCliError(f"{path}:{lineno} is not valid JSON: {exc}") from exc
        if not isinstance(parsed, dict):
            raise ScopeCliError(
                f"{path}:{lineno} is valid JSON but not an object -- an asset row must be a "
                "mapping. Fix or remove the line.")
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


def signal_classes(entry: dict) -> list[str]:
    out = []
    for signal in entry.get("attribution_signals") or []:
        if isinstance(signal, dict) and isinstance(signal.get("class"), str):
            out.append(signal["class"].upper())
    return out


def promotion_verdict(classes: list[str]) -> tuple[bool, str]:
    """Decide whether these signals justify CONFIRMED. Returns (ok, reason-if-not)."""
    distinct = set(classes)
    unknown = distinct - set(SIGNAL_CLASSES)
    if unknown:
        return False, (f"unrecognised attribution signal class(es): {', '.join(sorted(unknown))}. "
                       f"Valid: {', '.join(SIGNAL_CLASSES)}")
    if distinct & SELF_SUFFICIENT:
        return True, ""
    if len(distinct) < 2:
        return False, (f"only {len(distinct)} distinct attribution signal class "
                       f"({', '.join(sorted(distinct)) or 'none'}). Promotion requires two "
                       "independent classes, or explicit CLIENT_CONFIRMED (§5.2).")
    return True, ""


def reject_ip_valued_signal(signal_class: str, value: str) -> None:
    """Refuse an attribution signal whose value is a bare IP address.

    Shared edge IPs (Cloudflare, Vercel, Netlify) cover every tenant at that address, and this
    client base lives on exactly that infrastructure. Favicon hashes have the same problem: they
    fingerprint the platform, not the owner. An address is corroboration, never identity.
    """
    candidate = value.strip().split("/")[0]
    try:
        ipaddress.ip_address(candidate)
    except ValueError:
        return
    raise ScopeCliError(
        f"signal {signal_class}:{value} records a bare IP address as evidence of ownership. "
        "Shared edge IPs cover every tenant at that address, so an IP never attributes an asset "
        "to a client (§5.2). Record what the address let you observe instead -- a TLS_SAN, a "
        "content fingerprint, a CNAME chain."
    )


def normalise_identifier(raw: str) -> tuple[str, int | None]:
    """Reduce a candidate identifier to (bare host, port-or-None) -- one consistent form.

    A URL-shaped identifier (``http://127.0.0.1:8901``) was previously stored and matched
    verbatim. `entry_matches_host()` calls `normalise_host()` on whatever it is given, and
    `normalise_host()` does not parse URLs -- it just lowercases and strips a trailing dot. So a
    URL identifier compared against a URL-typed scope entry never matched: the whole scheme and
    path rode along as part of the "host", while a bare-host WILDCARD candidate worked fine. The
    register must hold the same shape regardless of how the operator typed the identifier, or
    `in_boundary()` silently refuses things that are actually in scope -- which reads as "outside
    the authorization boundary" and wrongly suggests amending scope when the real bug is a
    formatting mismatch.

    The port is kept, not discarded, and returned separately so callers can check it against a
    scope entry that names one explicitly (`entry_matches_target`) -- collapsing it into the host
    string would let a candidate on an authorised host but an unauthorised port promote silently,
    which is exactly the kind of scope-widening promotion must never do.
    """
    raw = raw.strip()
    if "://" in raw:
        parsed = urllib.parse.urlsplit(raw)
        host = (parsed.hostname or "").lower().rstrip(".")
        if not host:
            raise ScopeCliError(f"{raw!r} looks like a URL but no host could be parsed from it")
        return host, parsed.port
    return raw.lower().rstrip("."), None


def load_boundary(root: Path) -> scope_mod.Scope:
    return scope_mod.load(root / "scope.yaml")


def in_boundary(boundary: scope_mod.Scope, identifier: str, port: int | None = None) -> bool:
    if any(scope_guard.entry_matches_target(e, identifier, port) for e in boundary.out_of_scope):
        return False
    return any(scope_guard.entry_matches_target(e, identifier, port) for e in boundary.in_scope)


def matched_entry(boundary: scope_mod.Scope, identifier: str, port: int | None = None) -> str | None:
    return next(
        (f"{e.asset_type}:{e.pattern}" for e in boundary.in_scope
         if scope_guard.entry_matches_target(e, identifier, port)), None)


# --------------------------------------------------------------------------------------------
# Commands
# --------------------------------------------------------------------------------------------


def cmd_show(root: Path, args) -> int:
    boundary = load_boundary(root)
    register = read_jsonl(root / "assets" / "register.jsonl")
    candidates = read_jsonl(root / "assets" / "candidates.jsonl")

    print(f"engagement : {boundary.engagement_id}")
    print(f"mode       : {boundary.mode}, ceiling {boundary.ceiling}")
    print(f"window     : {boundary.authorization.window_start} to {boundary.authorization.window_end}")
    print("\nin scope:")
    for entry in boundary.in_scope:
        port = scope_guard._entry_port(entry)
        print(f"  {entry.asset_type:18} {entry.pattern}" + (f"   [port {port}]" if port else ""))
    if boundary.out_of_scope:
        print("\nout of scope (wins over in scope):")
        for entry in boundary.out_of_scope:
            note = f"  -- {entry.note}" if entry.note else ""
            print(f"  {entry.asset_type:18} {entry.pattern}{note}")
    print(f"\nCONFIRMED assets : {len(register)}")
    for row in register:
        print(f"  {row.get('asset_id','?'):8} {row.get('identifier','?')}")
    print(f"CANDIDATE assets : {len(candidates)}")
    for row in candidates:
        classes = ", ".join(sorted(set(signal_classes(row)))) or "no signals"
        ok, _ = promotion_verdict(signal_classes(row))
        print(f"  {row.get('asset_id','?'):8} {row.get('identifier','?')}  "
              f"[{classes}] {'PROMOTABLE' if ok else 'not promotable'}")
    return 0


def cmd_add_candidate(root: Path, args) -> int:
    boundary = load_boundary(root)
    candidates = read_jsonl(root / "assets" / "candidates.jsonl")
    register = read_jsonl(root / "assets" / "register.jsonl")

    identifier, port = normalise_identifier(args.identifier)
    if any(r.get("identifier") == identifier for r in candidates + register):
        raise ScopeCliError(f"{identifier} is already in the register or candidate queue")

    signals = []
    for raw in args.signal or []:
        cls, _, rest = raw.partition(":")
        value, _, source = rest.partition("@")
        cls = cls.strip().upper()
        if cls not in SIGNAL_CLASSES:
            raise ScopeCliError(f"unrecognised signal class {cls!r}. Valid: {', '.join(SIGNAL_CLASSES)}")
        reject_ip_valued_signal(cls, value)
        signals.append({"class": cls, "value": value.strip(), "source": source.strip() or "unrecorded"})

    row = {
        "asset_id": args.asset_id or f"C-{len(candidates) + 1:03d}",
        "asset_type": args.asset_type,
        "identifier": identifier,
        "port": port,
        "discovery_method": args.discovery_method,
        "attribution_signals": signals,
        "attribution_confidence": args.confidence,
        "matched_boundary_entry": matched_entry(boundary, identifier, port),
        "status": "CANDIDATE",
        "first_seen": now(),
        "last_seen": now(),
    }
    candidates.append(row)
    write_jsonl(root / "assets" / "candidates.jsonl", candidates)
    append_ledger(root, "activity.jsonl", {
        "ts": now(), "engagement_id": boundary.engagement_id, "event_type": "asset.candidate",
        "target": {"asset_id": row["asset_id"], "host": identifier},
        "decision": "allow", "reason": f"discovered via {args.discovery_method}",
    })
    ok, why = promotion_verdict(signal_classes(row))
    print(f"Added candidate {row['asset_id']} {identifier}")
    print(f"  promotable: {'yes' if ok else 'NO -- ' + why}")
    if row["matched_boundary_entry"] is None:
        print("  WARNING: matches no in_scope entry. It is not probeable at all until the "
              "boundary is amended or the client confirms it (§5.5 rule 2).")
    return 0


def cmd_promote(root: Path, args) -> int:
    boundary = load_boundary(root)
    candidates = read_jsonl(root / "assets" / "candidates.jsonl")
    register = read_jsonl(root / "assets" / "register.jsonl")
    identifier, typed_port = normalise_identifier(args.identifier)

    match = next((r for r in candidates if r.get("identifier") == identifier), None)
    if match is None:
        raise ScopeCliError(
            f"{identifier} is not in the candidate queue. Add it with 'add-candidate' first -- "
            "an asset cannot be promoted straight into the register."
        )

    # Prefer the port recorded when the candidate was added -- the operator may re-type
    # `promote` with just the bare host, and that must not silently drop a port an in-scope
    # entry named specifically.
    port = match.get("port") if match.get("port") is not None else typed_port

    if not in_boundary(boundary, identifier, port):
        raise ScopeCliError(
            f"{identifier} sits outside the authorization boundary (or matches an out_of_scope "
            "entry). Promotion does not widen scope. Amend the boundary in writing first: "
            "'scope_cli.py amend --add ... --reason ...'."
        )

    classes = signal_classes(match)
    if args.client_confirmed:
        match.setdefault("attribution_signals", []).append(
            {"class": "CLIENT_CONFIRMED", "value": args.client_confirmed, "source": "operator"})
        classes.append("CLIENT_CONFIRMED")

    ok, why = promotion_verdict(classes)
    if not ok:
        raise ScopeCliError(f"cannot promote {identifier}: {why}")

    if not args.confirm:
        raise ScopeCliError(
            f"{identifier} qualifies for promotion on signals [{', '.join(sorted(set(classes)))}] "
            "but operator sign-off is required. Re-run with --confirm."
        )

    match["status"] = "CONFIRMED"
    match["attribution_confidence"] = "HIGH"
    match["asset_id"] = args.asset_id or f"A-{len(register) + 1:03d}"
    match["last_seen"] = now()
    match["matched_boundary_entry"] = matched_entry(boundary, identifier, port)

    register.append(match)
    write_jsonl(root / "assets" / "register.jsonl", register)
    write_jsonl(root / "assets" / "candidates.jsonl",
                [r for r in candidates if r.get("identifier") != identifier])
    append_ledger(root, "activity.jsonl", {
        "ts": now(), "engagement_id": boundary.engagement_id, "event_type": "asset.promote",
        "target": {"asset_id": match["asset_id"], "host": identifier},
        "decision": "allow",
        "reason": f"promoted on signals: {', '.join(sorted(set(classes)))}",
    })
    print(f"Promoted {identifier} to CONFIRMED as {match['asset_id']}")
    print(f"  signals: {', '.join(sorted(set(classes)))}")
    print("  it is now testable up to the engagement ceiling")
    return 0


def cmd_amend(root: Path, args) -> int:
    boundary = load_boundary(root)
    document = boundary.to_dict()

    if args.add:
        entry_type, _, pattern = args.add.partition(":")
        document.setdefault("in_scope", []).append(
            {"asset_type": entry_type.strip().upper(), "pattern": pattern.strip()})
    if args.exclude:
        entry_type, _, rest = args.exclude.partition(":")
        pattern, _, note = rest.partition("|")
        entry = {"asset_type": entry_type.strip().upper(), "pattern": pattern.strip()}
        if note.strip():
            entry["note"] = note.strip()
        document.setdefault("out_of_scope", []).append(entry)
    if not args.add and not args.exclude:
        raise ScopeCliError("amend requires --add or --exclude")

    amended = scope_mod.parse(document)          # refuses to write anything that does not parse
    (root / "scope.yaml").write_text(amended.dumps(), encoding="utf-8")
    append_ledger(root, "gates.jsonl", {
        "ts": now(), "engagement_id": boundary.engagement_id, "event_type": "scope.amend",
        "decision": "allow", "reason": args.reason,
        "added": args.add, "excluded": args.exclude,
    })
    print(f"Boundary amended. Reason recorded: {args.reason}")
    print("NOTE: every gate approval derived from the previous scope is now void -- scope_hash "
          "has changed and plans must be re-approved (§9.7).")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rg-scope", description="Inspect and change an engagement boundary.")
    p.add_argument("--root", default=".", help="engagement directory")
    sub = p.add_subparsers(dest="command", required=True)

    sub.add_parser("show", help="print the boundary, register and candidate queue")

    add = sub.add_parser("add-candidate", help="record a discovered asset as CANDIDATE")
    add.add_argument("identifier")
    add.add_argument("--asset-type", default="URL")
    add.add_argument("--asset-id", default=None)
    add.add_argument("--discovery-method", default="unrecorded")
    add.add_argument("--confidence", default="LOW", choices=["LOW", "MEDIUM", "HIGH"])
    add.add_argument("--signal", action="append", metavar="CLASS:value@source",
                     help="repeatable, e.g. TLS_SAN:app.acme.example@crt.sh")

    promote = sub.add_parser("promote", help="promote a CANDIDATE to CONFIRMED")
    promote.add_argument("identifier")
    promote.add_argument("--asset-id", default=None)
    promote.add_argument("--confirm", action="store_true", help="operator sign-off")
    promote.add_argument("--client-confirmed", default=None,
                         help="record explicit client confirmation, e.g. 'email 2026-08-05'")

    amend = sub.add_parser("amend", help="change the authorization boundary in writing")
    amend.add_argument("--add", default=None, metavar="TYPE:pattern")
    amend.add_argument("--exclude", default=None, metavar="TYPE:pattern|note")
    amend.add_argument("--reason", required=True)
    return p


COMMANDS = {"show": cmd_show, "add-candidate": cmd_add_candidate,
            "promote": cmd_promote, "amend": cmd_amend}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    root = Path(args.root).expanduser().resolve()
    try:
        if not (root / "scope.yaml").is_file():
            raise ScopeCliError(f"no scope.yaml in {root}. Run this inside an engagement directory.")
        return COMMANDS[args.command](root, args)
    except (ScopeCliError, scope_mod.ScopeError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
