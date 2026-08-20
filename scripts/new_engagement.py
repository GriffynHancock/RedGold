#!/usr/bin/env python3
"""new_engagement.py -- the /rg:new engagement scaffolder (spec §4, §7.1, §9.1, §15.1).

Build order step 4.

Creates `<root>/<client>-<yyyy-mm>/` with its boundary, its three-file contract, its ledgers, and
-- the part that matters -- an `.claude/settings.json` that actually wires enforcement.

WHY THIS SCRIPT IS FUSSY
------------------------
Three things it refuses to do, each because the alternative produces an engagement that looks
guarded and is not:

1. **It will not write a boundary it cannot parse.** The scope document is built, then round-tripped
   through `scope.py` before anything is written to disk. A malformed `scope.yaml` would make
   `scope_guard.py` deny every call -- which is safe, but bricks the engagement in a way that
   invites someone to disable the hook.

2. **It pins an absolute interpreter path and verifies it first.** `python3` on PATH is not
   necessarily the interpreter that has PyYAML. A hook that dies on import does not deny -- a
   crashed PreToolUse hook fails OPEN. So the interpreter is chosen at scaffold time, tested by
   actually importing yaml through it, and written into settings.json as an absolute path.

3. **It requires the authorization document to exist on disk.** Not a filename someone intends to
   create. No target is touched without a signed scope, and the cheapest place to enforce that is
   before the directory exists.
"""

from __future__ import annotations

import argparse
import json
import shlex
import subprocess
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scope as scope_mod  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
GUARD_PATH = REPO_ROOT / "scripts" / "scope_guard.py"
TEMPLATES = REPO_ROOT / "templates" / "engagement"

LEDGERS = ("gates.jsonl", "activity.jsonl", "cleanup.jsonl", "blockers.jsonl")


class ScaffoldError(Exception):
    """Refusal to scaffold. Always actionable."""


def split_asset(spec: str, flag: str) -> dict[str, str]:
    """Parse 'TYPE:pattern' or 'TYPE:pattern|note'. Split on the FIRST colon only, because a
    pattern is routinely a URL and contains its own."""
    if ":" not in spec:
        raise ScaffoldError(f"{flag} value {spec!r} must be of the form TYPE:pattern")
    asset_type, _, rest = spec.partition(":")
    pattern, _, note = rest.partition("|")
    asset_type = asset_type.strip().upper()
    entry = {"asset_type": asset_type, "pattern": pattern.strip()}
    if note.strip():
        entry["note"] = note.strip()
    if not entry["pattern"]:
        raise ScaffoldError(f"{flag} value {spec!r} has an empty pattern")
    return entry


def verify_interpreter(interpreter: str) -> str:
    """Prove this interpreter can actually run the guard before pinning it into settings.json."""
    path = Path(interpreter)
    if not path.is_absolute():
        raise ScaffoldError(
            f"--python must be an absolute path, got {interpreter!r}. A hook that relies on PATH "
            "resolution can silently pick an interpreter without PyYAML, and a hook that dies on "
            "import fails OPEN."
        )
    if not path.is_file():
        raise ScaffoldError(f"interpreter {interpreter} does not exist")
    probe = subprocess.run(
        [interpreter, "-c", "import yaml; print(yaml.__version__)"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if probe.returncode != 0:
        raise ScaffoldError(
            f"interpreter {interpreter} cannot import PyYAML, so scope_guard.py would crash on "
            f"every call and enforcement would fail open. stderr: {probe.stderr.strip()}\n"
            "Pick an interpreter that has PyYAML (on Debian/Kali, /usr/bin/python3 usually does) "
            "or install it there."
        )
    return probe.stdout.strip()


def build_scope_document(args: argparse.Namespace, engagement_id: str) -> dict:
    doc: dict = {
        "engagement_id": engagement_id,
        "client": {"name": args.client_name, "contact": args.client_contact},
        "authorization": {
            "document": args.auth_document,
            "signed_by": args.signed_by,
            "signed_date": args.signed_date,
            "window_start": args.window_start,
            "window_end": args.window_end,
        },
        "mode": args.mode,
        "ceiling": args.ceiling,
        # RG-1 §3.1. Required at scaffold time so that a fresh engagement is never born missing
        # the key Gate 1 demands -- a framework that creates documents its own gate refuses
        # teaches operators that the gate is noise. `unknown` is accepted here and refused at
        # Gate 1: recording that nobody has said yet is honest, proceeding on it is not.
        "environment": args.environment,
    }
    if args.emergency_contact:
        doc["authorization"]["emergency_contact"] = args.emergency_contact
    if args.crown_jewel:
        doc["crown_jewels"] = list(args.crown_jewel)
    doc["in_scope"] = [split_asset(s, "--in-scope") for s in args.in_scope]
    if args.out_of_scope:
        doc["out_of_scope"] = [split_asset(s, "--out-of-scope") for s in args.out_of_scope]
    constraints: dict = {"no_destructive": True}
    if args.testing_window:
        constraints["testing_window"] = args.testing_window
    if args.burst_cap:
        constraints["max_requests_per_burst"] = args.burst_cap
    if args.forbid:
        constraints["forbidden_actions"] = list(args.forbid)
    doc["constraints"] = constraints
    doc["notify"] = {"before_active": True}
    return doc


# Hooks are wired only if their script exists. A hook pointing at a script that is not built
# yet makes every matching call error, and an erroring hook is not a denying hook.
HOOK_WIRING = [
    # (event, matcher, script filename)
    ("PreToolUse", "Bash|WebFetch|mcp__.*", "scope_guard.py"),
    ("PreToolUse", "Bash", "no_handrolled_loops.py"),
    ("PreToolUse", "Bash|WebFetch", "canary_check.py"),
    ("PreToolUse", "Agent|Task|TaskOutput|AskUserQuestion", "no_nesting.py"),
    ("PostToolUse", "Bash|WebFetch|Read|mcp__.*", "redact.py"),
    ("SubagentStop", "*", "validate_findings.py"),
]


def settings_json(engagement_dir: Path, interpreter: str) -> dict:
    """The enforcement layer (§9.1)."""
    events: dict[str, list] = {}
    for event, matcher, filename in HOOK_WIRING:
        script = REPO_ROOT / "scripts" / filename
        if not script.is_file():
            continue
        # shlex.quote, not f-string interpolation: this string is executed by a shell, and an
        # engagement path containing a quote injected arbitrary content into EVERY wired hook
        # at once. The scaffolder writes the enforcement layer -- it is the last place that can
        # afford to build a shell command carelessly.
        command = (f"RG_ENGAGEMENT_ROOT={shlex.quote(str(engagement_dir))} "
                   f"{shlex.quote(interpreter)} {shlex.quote(str(script))}")
        entry = {"hooks": [{"type": "command", "command": command, "timeout": 30}]}
        if event == "PreToolUse":
            entry = {"matcher": matcher, **entry}
        events.setdefault(event, []).append(entry)
    return {"hooks": events}


def wired_scripts() -> list[str]:
    return [f for _, _, f in HOOK_WIRING if (REPO_ROOT / "scripts" / f).is_file()]


def render_template(name: str, mapping: dict[str, str]) -> str:
    text = (TEMPLATES / name).read_text(encoding="utf-8")
    for key, value in mapping.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def scaffold(args: argparse.Namespace) -> Path:
    engagement_id = f"{args.client}-{args.date}"
    root = Path(args.root).expanduser()
    engagement_dir = root / engagement_id

    # Refusals first, before anything exists on disk.
    if engagement_dir.exists() and not args.force:
        raise ScaffoldError(
            f"{engagement_dir} already exists. Refusing to overwrite an engagement directory -- "
            "it may hold evidence and ledger history. Use --force only if you are certain."
        )
    if not args.in_scope:
        raise ScaffoldError("--in-scope is required: an engagement with an empty boundary authorises nothing")

    auth_doc = Path(args.auth_document).expanduser()
    if not args.allow_missing_authorization and not auth_doc.is_file():
        raise ScaffoldError(
            f"authorization document {auth_doc} does not exist. No target is touched without a "
            "signed scope, and this is the cheapest place to check. Point --auth-document at the "
            "signed file, or pass --allow-missing-authorization if you are scaffolding a dry run "
            "that will never touch a target."
        )

    yaml_version = verify_interpreter(args.python)

    # Build the boundary and prove it parses BEFORE writing anything.
    document = build_scope_document(args, engagement_id)
    boundary = scope_mod.parse(document)          # raises ScopeError on anything malformed
    scope_text = boundary.dumps()
    scope_mod.loads(scope_text)                   # round-trip: what we write, we can read back

    # --- create the tree -------------------------------------------------------------------
    for sub in (".claude/rules", "assets", "findings", "evidence", "ledger/sessions", "deliverables"):
        (engagement_dir / sub).mkdir(parents=True, exist_ok=True)

    (engagement_dir / "scope.yaml").write_text(scope_text, encoding="utf-8")
    (engagement_dir / ".claude" / "settings.json").write_text(
        json.dumps(settings_json(engagement_dir, args.python), indent=2) + "\n", encoding="utf-8"
    )

    for name in ("register.jsonl", "candidates.jsonl"):
        (engagement_dir / "assets" / name).touch()
    for name in LEDGERS:
        (engagement_dir / "ledger" / name).touch()

    mapping = {
        "ENGAGEMENT_ID": engagement_id,
        "CLIENT_NAME": args.client_name,
        "CLIENT_CONTACT": args.client_contact,
        "SIGNED_BY": args.signed_by,
        "SIGNED_DATE": str(args.signed_date),
        "AUTH_DOCUMENT": args.auth_document,
        "WINDOW_START": str(args.window_start),
        "WINDOW_END": str(args.window_end),
        "MODE": args.mode,
        "ENVIRONMENT": boundary.environment,
        "CEILING": str(args.ceiling),
        "SCAFFOLD_DATE": date.today().isoformat(),
        "IN_SCOPE_SUMMARY": ", ".join(f"{e.asset_type}:{e.pattern}" for e in boundary.in_scope),
        "OUT_OF_SCOPE_SUMMARY": ", ".join(f"{e.asset_type}:{e.pattern}" for e in boundary.out_of_scope) or "none",
    }
    for name in ("CLAUDE.md", "status.md", "session.md"):
        (engagement_dir / name).write_text(render_template(name, mapping), encoding="utf-8")

    (engagement_dir / ".gitignore").write_text(
        "# Evidence and secrets stay local unless the engagement says otherwise.\n"
        ".secrets.env\n*.secrets.env\n__pycache__/\n", encoding="utf-8"
    )

    if not args.no_git:
        subprocess.run(["git", "init", "-q", str(engagement_dir)], check=False, timeout=60)

    print(f"Scaffolded {engagement_dir}")
    print(f"  boundary   : {len(boundary.in_scope)} in-scope, {len(boundary.out_of_scope)} out-of-scope")
    print(f"  mode       : {boundary.mode}, ceiling {boundary.ceiling}")
    print(f"  enforcement: {', '.join(wired_scripts())}")
    print(f"               via {args.python} (PyYAML {yaml_version})")
    print("  NOT enforced yet: plan/deviation checks (Gate 2), output redaction, cleanup gate")
    return engagement_dir


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="rg-new", description="Scaffold a RedGold engagement.")
    p.add_argument("--client", required=True, help="short slug, e.g. 'acme'")
    p.add_argument("--date", required=True, help="engagement month, YYYY-MM")
    p.add_argument("--root", default="~/engagements", help="where engagements live (never inside RedGold)")
    p.add_argument("--client-name", required=True)
    p.add_argument("--client-contact", required=True)
    p.add_argument("--auth-document", required=True, help="path to the signed authorization")
    p.add_argument("--signed-by", required=True)
    p.add_argument("--signed-date", required=True)
    p.add_argument("--window-start", required=True)
    p.add_argument("--window-end", required=True)
    p.add_argument("--emergency-contact", default=None)
    p.add_argument("--mode", choices=scope_mod.MODES, default="audit")
    p.add_argument("--environment", required=True, choices=scope_mod.ENVIRONMENT_VALUES,
                   help="which environment these assets are (RG-1 §3.1). No default: an "
                        "engagement that never established this reported a development stack as "
                        "a client's production system. 'unknown' is accepted here and refused at "
                        "Gate 1 -- ask the client, do not guess.")
    p.add_argument("--ceiling", type=int, default=2)
    p.add_argument("--in-scope", action="append", default=[], metavar="TYPE:pattern")
    p.add_argument("--out-of-scope", action="append", default=[], metavar="TYPE:pattern|note")
    p.add_argument("--crown-jewel", action="append", default=[])
    p.add_argument("--forbid", action="append", default=[], help="forbidden action, repeatable")
    p.add_argument("--testing-window", default=None, help="e.g. 'weekdays 09:00-17:00 AEST'")
    p.add_argument("--burst-cap", type=int, default=10)
    p.add_argument("--python", default="/usr/bin/python3", help="absolute interpreter for hooks")
    p.add_argument("--no-git", action="store_true")
    p.add_argument("--force", action="store_true")
    p.add_argument("--allow-missing-authorization", action="store_true",
                   help="dry runs only; never for an engagement that will touch a target")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        scaffold(args)
    except (ScaffoldError, scope_mod.ScopeError) as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
