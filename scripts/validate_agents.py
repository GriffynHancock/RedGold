#!/usr/bin/env python3
"""validate_agents.py -- CI check over the agent roster (spec §8, §9.1).

Build order step 8.

The invariant *"any agent that can run commands carries the safety block"* is machine-checkable at
PR time. Convention would not survive a tired operator adding an agent at 11pm -- so this runs in
CI and fails the build.

Three of these checks exist because of documented failures elsewhere, not because they seemed
tidy:

1. **`tools:` must be set explicitly.** An unset `tools:` field grants the agent everything. A
   roster where one card forgot the field is a roster with an unconstrained agent in it, and
   nothing about the file looks wrong.

2. **At most one card may use the expensive model.** "Escalate to the strongest model whenever
   [risk category]" reliably collapses into "always escalate" once the category is broad -- and for
   a security-auditing tool the natural category ("anything security-relevant") is *all of the
   work*, by definition. A neighbouring project hit exactly this and watched cost follow. So the
   tier split is enforced numerically rather than left to judgement.

3. **Plugin agents must not declare `hooks`, `mcpServers` or `permissionMode`.** Those fields are
   silently ignored for plugin-shipped agents. A card that declares them looks protected and is
   not.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
AGENTS_DIR = REPO_ROOT / "agents"

REQUIRED_FIELDS = ("name", "description", "model", "tools")
FORBIDDEN_FIELDS = ("hooks", "mcpServers", "permissionMode")

NETWORK_TOOLS = {"Bash", "WebFetch"}
NESTING_TOOLS = {"Agent", "Task", "TaskOutput", "AskUserQuestion"}

SCOPE_MARKER = "RG-SCOPE-GUARDED"
UNTRUSTED_MARKER = "UNTRUSTED DATA"
NESTING_MARKER = "## NESTING"

EXPENSIVE_MODELS = {"opus"}
MAX_EXPENSIVE_CARDS = 1

# The orchestrator is defined by what it cannot do.
LEAD = "rg-lead"


def parse_frontmatter(text: str) -> dict[str, str]:
    match = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not match:
        return {}
    fields: dict[str, str] = {}
    key = None
    for line in match.group(1).splitlines():
        if re.match(r"^\w[\w-]*:", line):
            key, _, value = line.partition(":")
            fields[key.strip()] = value.strip()
        elif key and line.startswith((" ", "\t")):
            fields[key] += " " + line.strip()
    return fields


def tool_list(value: str) -> list[str]:
    return [t.strip() for t in value.split(",") if t.strip()]


def validate() -> list[str]:
    errors: list[str] = []
    if not AGENTS_DIR.is_dir():
        return [f"{AGENTS_DIR} does not exist"]

    cards = sorted(AGENTS_DIR.glob("*.md"))
    if not cards:
        return ["no agent cards found"]

    expensive = []

    for path in cards:
        text = path.read_text(encoding="utf-8")
        fields = parse_frontmatter(text)
        label = path.name

        if not fields:
            errors.append(f"{label}: no YAML frontmatter")
            continue

        for field in REQUIRED_FIELDS:
            if not fields.get(field):
                errors.append(f"{label}: missing required frontmatter field '{field}'")

        for field in FORBIDDEN_FIELDS:
            if field in fields:
                errors.append(
                    f"{label}: declares '{field}', which is SILENTLY IGNORED for plugin-shipped "
                    "agents. Put enforcement in the engagement's .claude/settings.json instead -- "
                    "a card that declares it looks protected and is not."
                )

        if fields.get("name") and fields["name"] != path.stem:
            errors.append(f"{label}: frontmatter name '{fields['name']}' != filename '{path.stem}'")

        tools = tool_list(fields.get("tools", ""))
        if not tools:
            errors.append(
                f"{label}: 'tools' is empty or unset. An unset tools field grants the agent "
                "EVERYTHING, and nothing about the file looks wrong."
            )

        granted_nesting = set(tools) & NESTING_TOOLS
        if granted_nesting:
            errors.append(
                f"{label}: grants {', '.join(sorted(granted_nesting))}. Subagents cannot nest and "
                "the failure is silent -- delegation fails open and no executor runs."
            )

        if fields.get("model", "").lower() in EXPENSIVE_MODELS:
            expensive.append(label)

        # Routing quality: the description is the delegation router, not a label.
        description = fields.get("description", "")
        if path.stem != LEAD and "do not use" not in description.lower():
            errors.append(
                f"{label}: description has no 'Do NOT use for...' clause. The description is the "
                "delegation router; without a negative case it collides with its neighbours."
            )

        # The safety block is required of anything that can reach the network or a shell.
        if set(tools) & NETWORK_TOOLS:
            for marker, why in (
                (SCOPE_MARKER, "scope-guard acknowledgement"),
                (UNTRUSTED_MARKER, "untrusted-data clause"),
                (NESTING_MARKER, "nesting prohibition"),
            ):
                if marker not in text:
                    errors.append(f"{label}: is network-capable but carries no {why} ({marker})")

        if path.stem == LEAD:
            leaked = set(tools) & NETWORK_TOOLS
            if leaked:
                errors.append(
                    f"{label}: grants {', '.join(sorted(leaked))}. The orchestrator must be "
                    "structurally incapable of probing -- a previous engagement's orchestrator "
                    "drifted into verifying its own workers' findings."
                )

    if len(expensive) > MAX_EXPENSIVE_CARDS:
        errors.append(
            f"{len(expensive)} cards use an expensive model ({', '.join(expensive)}), limit is "
            f"{MAX_EXPENSIVE_CARDS}. 'Escalate whenever [risk category]' collapses to 'always "
            "escalate' once the category is broad -- and for a security tool the natural category "
            "is all of the work. Keep the tier split numeric."
        )

    return errors


def main() -> int:
    errors = validate()
    if errors:
        print(f"Agent roster validation FAILED ({len(errors)} problems):\n", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    count = len(list(AGENTS_DIR.glob("*.md")))
    print(f"Agent roster OK: {count} cards.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
