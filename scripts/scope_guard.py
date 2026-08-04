#!/usr/bin/env python3
"""scope_guard.py -- PreToolUse hook. The core scope control (spec §9.3).

Build order step 3.

Reads a PreToolUse hook payload on stdin. Emits a deny decision on stdout as documented JSON,
always exiting 0.

WHAT THIS IS, PRECISELY (§9.3.1 -- read before quoting it to a client)
----------------------------------------------------------------------
This is **defence-in-depth against sloppy scope drift. It is NOT a security boundary.** Extracting
"what destination will this command reach" from an arbitrary shell string is not a solved problem;
Bash is Turing-complete and the target may not appear in the string at all. The honest claim is:

    "The tooling mechanically refuses out-of-scope targets in the ordinary case, and refuses
    outright when it cannot determine what it is about to touch."

Never "cannot happen". The real boundary is off-host egress filtering (§9.9), which does not exist
yet.

NOT IMPLEMENTED HERE
--------------------
§9.3.2 plan checking (steps 9-13: asset named in plan, test class authorised, write endpoint under
budget, live-confirm pending, plan/scope hash still valid) is **not built**. This module enforces
*scope*, not *the plan*. Do not describe Gate 2 as enforced until those checks exist and have tests
-- claiming an unenforced gate is exactly the finding audit #2 raised against this project.

TWO DESIGN DECISIONS WORTH KNOWING
----------------------------------
1. **On allow, this hook stays silent.** It emits a decision only to deny. Emitting an explicit
   "allow" would auto-approve the call and suppress the operator's normal permission prompt --
   a scope guard's job is to subtract permission, never to grant it.

2. **Every failure path denies.** Any exception, unreadable scope, unparseable window or
   undeterminable host produces a deny. A control that cannot evaluate must not permit. This
   matters because a PreToolUse hook that *crashes* fails open, so the entire body is wrapped.
"""

from __future__ import annotations

import base64
import binascii
import datetime as _dt
import ipaddress
import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scope as scope_mod  # noqa: E402

# --------------------------------------------------------------------------------------------
# Decision
# --------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class Decision:
    allow: bool
    reason: str = ""

    @staticmethod
    def permit() -> "Decision":
        return Decision(allow=True)

    @staticmethod
    def deny(reason: str) -> "Decision":
        return Decision(allow=False, reason=reason)


def emit(decision: Decision) -> None:
    """Write the hook's response. Silent on allow, by design."""
    if decision.allow:
        return
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": decision.reason,
            }
        },
        sys.stdout,
    )
    sys.stdout.write("\n")


# --------------------------------------------------------------------------------------------
# Blast-radius tiers (§6)
# --------------------------------------------------------------------------------------------

NETWORK_TOOLS = frozenset(
    {
        "curl", "wget", "nc", "ncat", "netcat", "telnet", "openssl",
        "nmap", "masscan", "ffuf", "gobuster", "dirb", "feroxbuster", "wfuzz",
        "nuclei", "httpx", "subfinder", "amass", "nikto", "whatweb", "wpscan",
        "sqlmap", "hydra", "medusa", "patator", "msfconsole", "msfvenom",
        "ab", "wrk", "siege", "slowhttptest", "dig", "host", "nslookup",
        # Service clients. These reach the network as surely as curl does, and on a target whose
        # database and cache ports are exposed they are exactly what gets reached for.
        "redis-cli", "mysql", "mysqladmin", "mysqldump", "psql", "mongo", "mongosh",
        "ssh", "scp", "sftp", "ftp", "smbclient", "ldapsearch", "snmpwalk", "rsync",
    }
)

# Tier 3: irreversible, sustained, or exploitative (§6).
TIER3_TOOLS = frozenset(
    {"sqlmap", "hydra", "medusa", "patator", "msfconsole", "msfvenom", "ab", "wrk", "siege", "slowhttptest"}
)

# Tier 2: bounded reversible writes, fuzzing, content discovery.
TIER2_TOOLS = frozenset({"ffuf", "gobuster", "dirb", "feroxbuster", "wfuzz", "nuclei", "nikto", "wpscan"})

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# Interpreters invoked with inline code. The destination is inside a program we are not going to
# evaluate, so the target is undeterminable by construction (§9.3.1).
INLINE_CODE_RE = re.compile(r"\b(python3?|perl|ruby|node|php)\b[^|;&]*\s-(c|e)\b")

# Target lists live in files this hook never opens (§9.3.1).
FILE_TARGET_LIST_RE = re.compile(r"(?:^|\s)-(?:-target-file|-input-file|iL|l|w)[\s=]+\S+")

# Variable indirection and command substitution: no literal host in the string.
INDIRECTION_RE = re.compile(r"\$\(|`|\$\{?[A-Za-z_][A-Za-z0-9_]*\}?")

# Re-execution of a script we cannot see.
SCRIPT_EXEC_RE = re.compile(
    r"\b(?:bash|sh|zsh|source|\.)\s+\S+\.(?:sh|bash|zsh|py|pl|rb)\b"
    r"|(?:^|[\s;&|])(?:\./|/)\S+\.(?:sh|bash|zsh|py|pl|rb)\b")

# RedGold's own tooling, invoked from `scripts/`. These are allowed past the *parser* checks --
# not because they are trusted, but because each one enforces the boundary itself, in code, using
# the functions in this very module. `verify_controls`-style tests assert that; if a script is
# added here without its own boundary check, the allowlist becomes the bypass.
#
# This exists because a hardening pass made the framework deny its own documented commands --
# including `rate_probe.sh`, the sanctioned burst path that the loop guard explicitly points at.
# A control that blocks the safe path pushes the operator toward the unsafe one.
FRAMEWORK_SCRIPTS = frozenset({
    "rate_probe.sh", "baseline_scan.py", "scope_cli.py", "new_engagement.py",
    "regen_status.py", "report.py", "validate_findings.py", "validate_agents.py",
    "verify_controls.py",
})
FRAMEWORK_INVOCATION_RE = re.compile(
    r"scripts/(" + "|".join(re.escape(n) for n in sorted(FRAMEWORK_SCRIPTS)) + r")\b")

# Harness- and shell-provided PATH variables. They cannot name a network destination, so treating
# them as "variable indirection, target unknowable" was collateral damage: it denied every
# documented command that used ${CLAUDE_PLUGIN_ROOT}. Still denied if one appears inside a URL.
SAFE_PATH_VARS_RE = re.compile(
    r"\$\{?(?:CLAUDE_PLUGIN_ROOT|CLAUDE_PROJECT_DIR|RG_ENGAGEMENT_ROOT|HOME|PWD)\}?")

# Host resolution overrides disconnect the literal name from the address contacted.
RESOLVE_OVERRIDE_RE = re.compile(r"--resolve\b|--connect-to\b|--proxy\b|-x\s")

URL_RE = re.compile(r"\b(https?)://([^\s'\"/\\;|)>]+)", re.IGNORECASE)
BARE_HOST_RE = re.compile(r"\b((?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,})\b", re.IGNORECASE)
BARE_HOST_PORT_RE = re.compile(
    r"\b((?:[a-z0-9](?:[a-z0-9-]*[a-z0-9])?\.)+[a-z]{2,})(?::(\d{1,5}))?\b", re.IGNORECASE
)

# A host-only boundary entry authorises the ordinary web ports and nothing else. Anything on a
# non-standard port must be named explicitly.
#
# This is not pedantry. One real target runs an in-scope app and an UNRELATED product's service on
# the same hostname, different ports. Matching on hostname alone cannot express "this host, but not
# that port", so a host-only match would silently authorise traffic to somebody else's system --
# a control that looks configured and is not.
DEFAULT_WEB_PORTS = frozenset({80, 443})
B64_RE = re.compile(r"\b[A-Za-z0-9+/]{12,}={0,2}\b")
B32_RE = re.compile(r"\b[A-Z2-7]{16,}={0,6}\b")


# The host regexes are nested-quantifier shaped and go quadratic on near-miss garbage: ~2s at
# 24KB, ~13s at 60KB, past this hook's own 30s timeout around 91KB. **A hook that times out
# fails open**, so a command too large to analyse is denied rather than scanned.
# No legitimate command comes close to this.
MAX_ANALYSABLE_COMMAND = 8192


def classify_tier(command: str) -> int:
    """Classify a command's blast radius. Errs high: an unclear command is not treated as safe."""
    lowered = command.lower()
    tokens = set(re.findall(r"[a-z0-9_.-]+", lowered))

    if tokens & TIER3_TOOLS:
        return 3
    # nmap scripts that brute-force, exploit, or DoS are tier 3 regardless of the base tool.
    if "nmap" in tokens and re.search(r"--script[\s=]\S*(exploit|brute|dos|vuln)", lowered):
        return 3

    method = re.search(r"-X\s*([A-Za-z]+)|--request[\s=]*([A-Za-z]+)", command)
    if method:
        verb = (method.group(1) or method.group(2) or "").upper()
        if verb in WRITE_METHODS:
            return 2
    # A body implies a write even without an explicit -X.
    if re.search(r"(?:^|\s)(?:-d|--data|--data-raw|--data-binary|--form|-F|-T|--upload-file)\b",
                 command):
        return 2
    if tokens & TIER2_TOOLS:
        return 2
    return 1


# --------------------------------------------------------------------------------------------
# Target extraction
# --------------------------------------------------------------------------------------------


class Undeterminable(Exception):
    """The destination cannot be established from the request. Callers must deny."""


def _decode_candidates(text: str) -> list[str]:
    """Decode base64/base32 blobs so an obfuscated host is matched, not missed (§9.3 step 3)."""
    out: list[str] = []
    for pattern, decoder in ((B64_RE, base64.b64decode), (B32_RE, base64.b32decode)):
        for blob in pattern.findall(text):
            padded = blob + "=" * (-len(blob) % (4 if decoder is base64.b64decode else 8))
            try:
                decoded = decoder(padded, validate=False)
            except (binascii.Error, ValueError):
                continue
            try:
                as_text = decoded.decode("utf-8")
            except UnicodeDecodeError:
                continue
            if as_text.isprintable():
                out.append(as_text)
    return out


# A bare dotted token is usually a filename, not a host. Without this, `curl https://in.scope
# -o out.txt` would read "out.txt" as an out-of-scope destination and deny a legitimate call --
# and a guard that fires constantly on false positives is one the operator learns to work around.
# Note the trade: `.sh` and `.zip` are real TLDs, so a host under one would be missed here. That
# is acceptable only because URLs are still matched by URL_RE regardless of extension.
_FILENAME_SUFFIXES = frozenset(
    {
        "txt", "json", "yaml", "yml", "py", "js", "ts", "md", "log", "csv", "tsv", "html", "htm",
        "xml", "conf", "cfg", "ini", "toml", "env", "pem", "key", "crt", "cer", "p12", "zip",
        "tar", "gz", "bz2", "xz", "out", "err", "bak", "tmp", "swp", "lock", "sql", "db",
        "sqlite", "png", "jpg", "jpeg", "gif", "pdf", "so", "dll", "exe", "bin", "sh", "bash",
        "jsonl", "har", "pcap", "cap", "http",
    }
)


def normalise_host(host: str) -> str:
    """Fold a hostname to lowercase ASCII/punycode.

    Without this, an `out_of_scope` entry written in punycode is bypassed by referencing the same
    host in its unicode form -- and vice versa. Both spellings resolve to the same machine, so
    treating them as different strings meant an explicit exclusion silently did nothing.
    """
    host = host.strip().rstrip(".").lower()
    if not host or host.isascii():
        return host
    try:
        return host.encode("idna").decode("ascii").lower()
    except (UnicodeError, UnicodeDecodeError, ValueError):
        # Cannot be normalised -- return as-is; the caller will fail to match it and deny.
        return host


def _hosts_in_text(text: str) -> set[str]:
    """Hostnames only, no ports. Used for parsing boundary patterns."""
    hosts: set[str] = set()
    for _scheme, authority in URL_RE.findall(text):
        host = authority.split("@")[-1].split(":")[0]
        if host:
            hosts.add(normalise_host(host))
    for host in BARE_HOST_RE.findall(text):
        host = normalise_host(host)
        if host.rsplit(".", 1)[-1] in _FILENAME_SUFFIXES and host not in hosts:
            continue
        hosts.add(host)
    return hosts


def _targets_in_text(text: str) -> set[tuple[str, int | None]]:
    """(host, port) pairs. Port is None where the text does not pin one.

    A URL without an explicit port carries its scheme's default, because that IS the port the
    request will reach.
    """
    targets: set[tuple[str, int | None]] = set()
    for scheme, authority in URL_RE.findall(text):
        authority = authority.split("@")[-1]
        host, _, port_text = authority.partition(":")
        host = normalise_host(host)
        if not host:
            continue
        if port_text.isdigit():
            targets.add((host, int(port_text)))
        else:
            targets.add((host, 443 if scheme.lower() == "https" else 80))
    for match in BARE_HOST_PORT_RE.finditer(text):
        host = normalise_host(match.group(1))
        if host.rsplit(".", 1)[-1] in _FILENAME_SUFFIXES:
            continue
        port = int(match.group(2)) if match.group(2) else None
        targets.add((host, port))
    return targets


# `[=\s]*` rather than `+` so an attached value is caught too: `-P3306`, and critically `-p-`,
# nmap's scan-every-port form, which a separator-requiring pattern misses entirely.
PORT_FLAG_RE = re.compile(r"(?:^|\s)(?:-p|-P|--port)(?:[=\s]*)(\S+)")
# DSN/keyword connection strings: `psql "host=h port=6379"`, `mysql --port=3306`.
DSN_PORT_RE = re.compile(r"\bport\s*=\s*(\d{1,5})\b", re.IGNORECASE)
POSITIONAL_PORT_RE = re.compile(
    r"\b(?:nc|ncat|netcat|telnet)\s+(?:-\S+\s+)*((?:[a-z0-9-]+\.)+[a-z]{2,})\s+(\d{1,5})\b",
    re.IGNORECASE,
)


def _explicit_port_flag(text: str) -> int | None:
    """A port pinned by flag: `-p 6379`, `-P 3306`, `--port=8025`.

    A range or list (`-p-`, `-p 1-65535`, `-p 80,443`) raises rather than being enumerated. A
    port sweep across a host where only the web ports are authorised is a scope question, and
    guessing which of those ports the operator meant is exactly the kind of inference this
    control must not make.
    """
    dsn = DSN_PORT_RE.search(text)
    if dsn:
        port = int(dsn.group(1))
        if 0 < port < 65536:
            return port
    match = PORT_FLAG_RE.search(text)
    if not match:
        return None
    value = match.group(1)
    if value.isdigit():
        port = int(value)
        return port if 0 < port < 65536 else None
    raise Undeterminable(
        f"port specification {value!r} is a range or list rather than a single port, so the set "
        "of destinations cannot be established"
    )


def _entry_port(entry: scope_mod.AssetEntry) -> int | None:
    """A port explicitly named in a boundary pattern, if any."""
    match = re.search(r"^(?:[a-z]+://)?[^/\s:]+:(\d{1,5})(?:/|$)", entry.pattern.strip(), re.IGNORECASE)
    return int(match.group(1)) if match else None


def extract_hosts(tool_name: str, tool_input: dict[str, Any]) -> set[tuple[str, int | None]]:
    """Return every (host, port) this call might reach. Raises Undeterminable rather than guessing."""
    if tool_name == "WebFetch":
        url = tool_input.get("url")
        if not isinstance(url, str) or not url.strip():
            raise Undeterminable("WebFetch call carries no url field")
        found = _targets_in_text(url)
        if not found:
            raise Undeterminable(f"no host could be parsed from url {url!r}")
        return found

    if tool_name.startswith("mcp__"):
        # Each MCP server defines its own schema; there is no canonical target field (§9.3.1).
        raise Undeterminable(
            f"MCP tool {tool_name!r} has no registered target-field mapping, so the destination "
            "cannot be determined"
        )

    if tool_name != "Bash":
        raise Undeterminable(f"unrecognised tool {tool_name!r}")

    command = tool_input.get("command")
    if not isinstance(command, str) or not command.strip():
        raise Undeterminable("Bash call carries no command")
    if len(command) > MAX_ANALYSABLE_COMMAND:
        raise Undeterminable(
            f"command is {len(command)} bytes, over the {MAX_ANALYSABLE_COMMAND}-byte limit this "
            "check can analyse in bounded time. Denying rather than scanning: a hook that times "
            "out fails open. Split the work into smaller commands, or write the payload to a "
            "file the target reads")

    # A RedGold script invocation is evaluated by that script, not by this parser.
    if FRAMEWORK_INVOCATION_RE.search(command):
        return set()

    expanded = command + "\n" + "\n".join(_decode_candidates(command))
    hosts = _targets_in_text(expanded)
    tokens = set(re.findall(r"[a-z0-9_.-]+", expanded.lower()))
    touches_network = bool(tokens & NETWORK_TOOLS) or bool(URL_RE.search(expanded))

    if not touches_network:
        # Nothing here reaches the network. Not this control's business.
        return set()

    # Every branch below is a known blind spot from §9.3.1. Each denies rather than guessing.
    if SCRIPT_EXEC_RE.search(command):
        raise Undeterminable("command executes a script file whose contents this check cannot see")
    if INLINE_CODE_RE.search(command):
        raise Undeterminable("command runs inline interpreter code; the destination is inside the program")
    if FILE_TARGET_LIST_RE.search(command):
        raise Undeterminable("targets are supplied from a file this check never opens")
    if RESOLVE_OVERRIDE_RE.search(command):
        raise Undeterminable(
            "command overrides host resolution (--resolve/--connect-to/proxy), so the literal "
            "hostname is disconnected from the address actually contacted"
        )
    # Blank out harness PATH variables before the indirection check -- but only where they are
    # not inside a URL, since `curl https://$HOST/` must still be undeterminable.
    url_spans = [m.span() for m in URL_RE.finditer(command)]
    def _outside_urls(match: re.Match[str]) -> bool:
        return not any(start <= match.start() < end for start, end in url_spans)
    probe = command
    for match in reversed([m for m in SAFE_PATH_VARS_RE.finditer(command) if _outside_urls(m)]):
        probe = probe[:match.start()] + "/SAFEPATH" + probe[match.end():]
    if INDIRECTION_RE.search(probe):
        raise Undeterminable("command uses variable or command substitution; no literal host is present")
    if not hosts:
        raise Undeterminable("a network tool was invoked but no destination could be parsed")

    # A port given by flag (`redis-cli -h host -p 6379`) belongs to the host it was given with.
    # Without this the host resolves with port None and a host-only boundary entry would wave it
    # through as though it were ordinary web traffic.
    flagged = _explicit_port_flag(expanded)
    if flagged is not None:
        hosts = {(h, flagged if p is None else p) for h, p in hosts}

    # `nc host 6379` carries its port positionally.
    for host, port_text in POSITIONAL_PORT_RE.findall(expanded):
        hosts.add((host.lower().rstrip("."), int(port_text)))

    return hosts


# --------------------------------------------------------------------------------------------
# Boundary matching (§5.1, §5.4)
# --------------------------------------------------------------------------------------------


def port_authorised(entry: scope_mod.AssetEntry, port: int | None) -> bool:
    entry_port = _entry_port(entry)
    if entry_port is not None:
        return port == entry_port
    return port is None or port in DEFAULT_WEB_PORTS


def entry_matches_target(entry: scope_mod.AssetEntry, host: str, port: int | None) -> bool:
    return entry_matches_host(entry, host) and port_authorised(entry, port)


def entry_matches_host(entry: scope_mod.AssetEntry, host: str) -> bool:
    """Hostname match only, ignoring ports. Port authorisation is a separate decision."""
    host = normalise_host(host)
    pattern = entry.pattern.strip().lower()
    kind = entry.asset_type

    if kind == "WILDCARD":
        base = normalise_host(pattern[2:] if pattern.startswith("*.") else pattern)
        return host == base or host.endswith("." + base)

    if kind in ("URL", "API"):
        parsed = _hosts_in_text(pattern) or {pattern.split("/")[0]}
        return host in {normalise_host(p) for p in parsed}

    if kind == "IP_ADDRESS":
        return host == pattern

    if kind == "CIDR":
        try:
            network = ipaddress.ip_network(pattern, strict=False)
            return ipaddress.ip_address(host) in network
        except ValueError:
            return False

    if kind == "SUPABASE_PROJECT":
        # A project ref resolves to a known managed hostname pair.
        return host in {f"{pattern}.supabase.co", f"db.{pattern}.supabase.co"}

    # SOURCE_CODE, GITHUB_ORG, HARDWARE and friends name no network destination. They cannot
    # authorise a request, and silently treating them as a match would widen the boundary.
    return False


def load_register(engagement_root: Path) -> set[str]:
    """CONFIRMED identifiers only. A CANDIDATE is structurally untouchable (§5.3)."""
    path = engagement_root / "assets" / "register.jsonl"
    if not path.exists():
        return set()
    confirmed: set[str] = set()
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise scope_mod.ScopeError(f"{path}:{lineno} is not valid JSON: {exc}") from exc
        if row.get("status") == "CONFIRMED":
            identifier = row.get("identifier")
            if isinstance(identifier, str):
                confirmed.add(identifier.lower().rstrip("."))
    return confirmed


# --------------------------------------------------------------------------------------------
# Time windows
# --------------------------------------------------------------------------------------------

_TZ_OFFSETS = {
    "UTC": 0, "GMT": 0, "Z": 0,
    "AEST": 10 * 60, "AEDT": 11 * 60, "ACST": 9 * 60 + 30, "ACDT": 10 * 60 + 30,
    "AWST": 8 * 60,
}

_WINDOW_RE = re.compile(
    r"^\s*(?P<days>weekdays|weekends|daily|everyday)\s+"
    r"(?P<start>\d{1,2}:\d{2})\s*-\s*(?P<end>\d{1,2}:\d{2})\s+"
    r"(?P<tz>[A-Za-z_/+]+)\s*$",
    re.IGNORECASE,
)


def within_testing_window(window: str, now_utc: _dt.datetime) -> bool:
    """Evaluate a testing window. An unparseable window raises, and the caller denies.

    Deliberately a small supported grammar rather than a best-effort natural-language parse:
    a window this check silently misreads is worse than one it refuses.
    """
    match = _WINDOW_RE.match(window)
    if not match:
        raise ScopeWindowError(
            f"constraints.testing_window {window!r} is not in a supported form. Use e.g. "
            "'weekdays 09:00-17:00 AEST' (days: weekdays|weekends|daily)."
        )
    tz_name = match.group("tz").upper()
    if tz_name not in _TZ_OFFSETS:
        raise ScopeWindowError(
            f"timezone {match.group('tz')!r} in constraints.testing_window is not recognised. "
            f"Supported: {', '.join(sorted(_TZ_OFFSETS))}."
        )
    local = now_utc.astimezone(_dt.timezone(_dt.timedelta(minutes=_TZ_OFFSETS[tz_name])))

    days = match.group("days").lower()
    is_weekend = local.weekday() >= 5
    if days == "weekdays" and is_weekend:
        return False
    if days == "weekends" and not is_weekend:
        return False

    start_h, start_m = (int(x) for x in match.group("start").split(":"))
    end_h, end_m = (int(x) for x in match.group("end").split(":"))
    minutes = local.hour * 60 + local.minute
    start, end = start_h * 60 + start_m, end_h * 60 + end_m

    # A window that crosses midnight ("22:00-06:00") is a normal thing for a client to agree to.
    # Comparing start <= now < end for one of those is false at every hour of the day, which
    # denied 24/7 while looking like a working configuration.
    if end <= start:
        return minutes >= start or minutes < end
    return start <= minutes < end


class ScopeWindowError(scope_mod.ScopeError):
    """The testing window could not be evaluated. Deny."""


# --------------------------------------------------------------------------------------------
# Evaluation
# --------------------------------------------------------------------------------------------


def evaluate(
    payload: dict[str, Any],
    boundary: scope_mod.Scope,
    confirmed: set[str],
    now_utc: _dt.datetime,
) -> Decision:
    tool_name = payload.get("tool_name") or ""
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        return Decision.deny("tool_input is not an object; cannot determine the target. Denying.")

    try:
        hosts = extract_hosts(tool_name, tool_input)
    except Undeterminable as exc:
        # §9.3 step 8. This is the honest admission that the parser is a heuristic.
        return Decision.deny(
            f"DENIED (undeterminable target): {exc}. RedGold denies rather than guesses when it "
            "cannot establish what a command will contact. Rewrite the call with a literal, "
            "in-scope destination, or raise a deviation blocker via /rg:gate."
        )

    if not hosts:
        return Decision.permit()

    # Authorization window (§5.1). Testing outside the signed dates is unauthorised, full stop.
    today = now_utc.date()
    if today < boundary.authorization.window_start or today > boundary.authorization.window_end:
        return Decision.deny(
            f"DENIED (outside authorization window): today is {today}; the signed engagement window "
            f"is {boundary.authorization.window_start} to {boundary.authorization.window_end}. "
            "Testing outside the window is not authorised. A written amendment is required."
        )

    if boundary.constraints.testing_window:
        try:
            inside = within_testing_window(boundary.constraints.testing_window, now_utc)
        except ScopeWindowError as exc:
            return Decision.deny(f"DENIED (testing window unevaluable): {exc}")
        if not inside:
            return Decision.deny(
                f"DENIED (outside testing window): the engagement permits testing only during "
                f"'{boundary.constraints.testing_window}'."
            )

    tier = classify_tier(tool_input.get("command", "")) if tool_name == "Bash" else 1
    if tier > boundary.ceiling:
        return Decision.deny(
            f"DENIED (ceiling): this action is tier {tier}; the engagement ceiling is "
            f"{boundary.ceiling} in mode '{boundary.mode}'. Raising a ceiling requires a written "
            "scope amendment, not a retry."
        )

    for host, port in sorted(hosts, key=lambda t: (t[0], t[1] or 0)):
        where = f"{host}:{port}" if port is not None else host

        # out_of_scope wins over in_scope, always (§5.1).
        for entry in boundary.out_of_scope:
            if entry_matches_target(entry, host, port):
                note = f" ({entry.note})" if entry.note else ""
                return Decision.deny(
                    f"DENIED (out of scope): '{where}' matches the explicit out_of_scope entry "
                    f"{entry.asset_type}:{entry.pattern}{note}. This exclusion overrides any "
                    "in_scope match and cannot be overridden by discovery."
                )

        host_matched = next((e for e in boundary.in_scope if entry_matches_host(e, host)), None)
        if host_matched is None:
            return Decision.deny(
                f"DENIED (out of scope): host '{host}' matches no in_scope entry in the signed "
                f"boundary for engagement '{boundary.engagement_id}'. Nothing an agent discovers "
                "can widen what an agent may do (§5.4). If the client owns this asset, promote it "
                "via /rg:scope with client confirmation."
            )

        matched = next((e for e in boundary.in_scope if entry_matches_target(e, host, port)), None)
        if matched is None:
            authorised = sorted(
                {str(_entry_port(e) or "80/443") for e in boundary.in_scope if entry_matches_host(e, host)}
            )
            return Decision.deny(
                f"DENIED (port not authorised): host '{host}' is in scope, but port {port} is not. "
                f"Authorised on this host: {', '.join(authorised)}. A host-only boundary entry "
                "covers the ordinary web ports and nothing else -- a different service on the same "
                "host may belong to an entirely different product. Name the port explicitly in "
                "scope.yaml via /rg:scope if the client authorised it."
            )

        # §5.4: active tooling targets only CONFIRMED register rows -- but §5.5 carves out
        # attribution probes, because TLS_SAN and CONTENT_FP signals can only be obtained BY
        # contacting the asset. Without this carve-out the invariant deadlocks: nothing can ever
        # be confirmed, so nothing can ever be touched, so a fresh engagement denies its own
        # first request.
        #
        # The carve-out is narrow and stays narrow: inside the boundary, tier 0-1 only.
        if host not in confirmed:
            if tier <= 1:
                # Permitted as an attribution probe. NOTE: §5.5 additionally requires that these
                # are rate-limited, logged with purpose=attribution, and that anything observed
                # is discarded as evidence rather than becoming a finding. Those three belong to
                # the ledger work in later steps and are NOT enforced here. Until they are, do
                # not describe attribution probing as fully constrained.
                continue
            return Decision.deny(
                f"DENIED (not confirmed): host '{host}' falls inside the boundary "
                f"({matched.asset_type}:{matched.pattern}) but is not a CONFIRMED row in the asset "
                f"register, and this is a tier {tier} action. Only tier 0-1 attribution probes are "
                "permitted against an unconfirmed asset (§5.5). Promotion requires two independent "
                "attribution signals, and an IP address never counts alone (§5.2). Promote it via "
                "/rg:scope, then retry."
            )

    return Decision.permit()


# --------------------------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------------------------


def find_engagement_root(payload: dict[str, Any]) -> Path:
    override = os.environ.get("RG_ENGAGEMENT_ROOT")
    if override:
        return Path(override)
    start = Path(payload.get("cwd") or os.getcwd())
    for candidate in [start, *start.parents]:
        if (candidate / "scope.yaml").is_file():
            return candidate
    raise scope_mod.ScopeError(
        f"no scope.yaml found at or above {start}. RedGold will not permit a network action "
        "without a loaded authorization boundary."
    )


def check_url(root: Path, url: str, tier: int) -> tuple[bool, str]:
    """Boundary check for RedGold's own tools. One implementation, two entry points --
    a second copy of this logic would drift away from the hook's."""
    boundary = scope_mod.load(root / "scope.yaml")
    confirmed = load_register(root)
    payload = {"tool_name": "WebFetch", "tool_input": {"url": url}}
    decision = evaluate(payload, boundary, confirmed, _dt.datetime.now(_dt.timezone.utc))
    if not decision.allow:
        return False, decision.reason
    if tier > boundary.ceiling:
        return False, (f"DENIED (ceiling): tier {tier} exceeds the engagement ceiling "
                       f"{boundary.ceiling}")
    return True, ""


def main() -> int:
    # Standalone boundary check, used by rate_probe.sh before it fires anything.
    if "--check-url" in sys.argv:
        args = sys.argv[1:]
        url = args[args.index("--check-url") + 1]
        root = Path(args[args.index("--root") + 1] if "--root" in args else ".").resolve()
        tier = int(args[args.index("--tier") + 1]) if "--tier" in args else 1
        try:
            allowed, reason = check_url(root, url, tier)
        except Exception as exc:  # noqa: BLE001
            print(f"DENIED (could not evaluate): {exc}", file=sys.stderr)
            return 1
        if not allowed:
            print(reason, file=sys.stderr)
            return 1
        return 0

    # The entire body is wrapped: an unhandled exception in a PreToolUse hook fails OPEN.
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook payload is not a JSON object")
        root = find_engagement_root(payload)
        boundary = scope_mod.load(root / "scope.yaml")
        confirmed = load_register(root)
        decision = evaluate(payload, boundary, confirmed, _dt.datetime.now(_dt.timezone.utc))
    except Exception as exc:  # noqa: BLE001 -- deliberately total
        decision = Decision.deny(
            f"DENIED (scope_guard could not evaluate this call): {type(exc).__name__}: {exc}. "
            "A control that cannot evaluate must not permit. Fix the engagement's scope "
            "configuration before continuing."
        )
    emit(decision)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
