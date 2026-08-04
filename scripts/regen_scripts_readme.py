#!/usr/bin/env python3
"""regen_scripts_readme.py -- regenerate the file-inventory table in scripts/README.md.

WHY THIS EXISTS
----------------
`scripts/README.md` used to hand-list which scripts were built, and drifted: eight scripts that
were built, wired, and tested were still marked "not built" long after `status.md` and
`commands/new.md` had moved on. A cold-start read of `scripts/README.md` followed the stale table
down a dead end -- stale docs cost real time and tokens on every future run, not just this one.

So the file-inventory table is generated from what is actually on disk (`scripts/*.py`,
`scripts/*.sh`) plus `HOOK_WIRING` in `new_engagement.py` -- the same source of truth the
scaffolder itself reads -- and regenerated between the `<!-- BEGIN GENERATED -->` /
`<!-- END GENERATED -->` markers. Everything outside the markers, including the interpreter
section, is hand-written prose and is preserved verbatim.

Mirrors `regen_status.py`'s pattern: `render()` is pure and deterministic, `--check` exits 1 on
drift, plain invocation rewrites the file on disk.
"""

from __future__ import annotations

import argparse
import importlib.util
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = REPO_ROOT / "scripts"
README = SCRIPTS_DIR / "README.md"

BEGIN_MARKER = "<!-- BEGIN GENERATED -->"
END_MARKER = "<!-- END GENERATED -->"


def load_hook_wiring() -> list[tuple[str, str, str]]:
    """Import new_engagement.py's HOOK_WIRING without running it as __main__."""
    spec = importlib.util.spec_from_file_location(
        "new_engagement", SCRIPTS_DIR / "new_engagement.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return list(module.HOOK_WIRING)


def script_description(path: Path) -> str:
    """First line of the module docstring / header comment, minus the filename prefix."""
    text = path.read_text(encoding="utf-8")
    if path.suffix == ".py":
        match = re.search(r'^"""(.+?)$', text, re.MULTILINE)
        first_line = match.group(1) if match else ""
    else:
        # Shell scripts: the first `# name.sh -- description` comment line.
        match = re.search(r"^#\s*" + re.escape(path.name) + r"\s*--\s*(.+?)\s*$",
                          text, re.MULTILINE)
        first_line = match.group(1) if match else ""
    # Strip a leading "name.py -- " / "name.sh -- " prefix if the regex above didn't already.
    prefix = re.match(rf"^{re.escape(path.name)}\s*--\s*(.+)$", first_line)
    if prefix:
        first_line = prefix.group(1)
    return first_line.strip() or "(no description found)"


def discover_scripts() -> list[Path]:
    paths = sorted(SCRIPTS_DIR.glob("*.py")) + sorted(SCRIPTS_DIR.glob("*.sh"))
    return [p for p in paths if p.name not in {"regen_scripts_readme.py"}]


def wiring_for(name: str, wiring: list[tuple[str, str, str]]) -> str:
    events = [event for event, _matcher, filename in wiring if filename == name]
    if not events:
        return "not a hook -- invoked directly (CLI / command backend)"
    return ", ".join(f"`{e}`" for e in events)


def render_table() -> str:
    wiring = load_hook_wiring()
    lines = [
        "| Script | Description | Wired as a hook |",
        "|---|---|---|",
    ]
    for path in discover_scripts():
        desc = script_description(path)
        wired = wiring_for(path.name, wiring)
        lines.append(f"| `{path.name}` | {desc} | {wired} |")
    lines.append("")
    lines.append("Generated from `scripts/*.py`, `scripts/*.sh` on disk and `HOOK_WIRING` in "
                 "`new_engagement.py` -- run `regen_scripts_readme.py` after adding, removing, "
                 "or rewiring a script. For what is spec'd but not yet built, see `status.md`'s "
                 "\"Remaining v1 gaps\".")
    return "\n".join(lines)


def render(current: str) -> str:
    if BEGIN_MARKER not in current or END_MARKER not in current:
        raise ValueError(
            f"{README} is missing {BEGIN_MARKER} / {END_MARKER} markers -- cannot regenerate "
            "the table without a place to put it.")
    before, rest = current.split(BEGIN_MARKER, 1)
    _old_table, after = rest.split(END_MARKER, 1)
    return f"{before}{BEGIN_MARKER}\n\n{render_table()}\n\n{END_MARKER}{after}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Regenerate the file-inventory table in scripts/README.md.")
    parser.add_argument("--check", action="store_true",
                        help="exit 1 if scripts/README.md differs from what would be generated")
    args = parser.parse_args(argv)

    current = README.read_text(encoding="utf-8") if README.is_file() else ""
    try:
        generated = render(current)
    except ValueError as exc:
        print(f"REFUSED: {exc}", file=sys.stderr)
        return 1

    if args.check:
        if current != generated:
            print("scripts/README.md is stale or hand-edited; run regen_scripts_readme.py",
                  file=sys.stderr)
            return 1
        print("scripts/README.md is current.")
        return 0

    README.write_text(generated, encoding="utf-8")
    print(f"Regenerated {README}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
