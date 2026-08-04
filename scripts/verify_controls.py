#!/usr/bin/env python3
"""verify_controls.py -- fault injection. Proves the tests discriminate.

A neighbouring project learned this the hard way, twice:

  "GREEN TESTS/AUDITS != A WORKING PRODUCT (learned the hard way 2026-07-14). The member-fields UI
  passed every unit/integration test + security audit + code review + green build and was still
  broken in 6 places in the real browser."

  "Counts are not coverage: the review history shows near-vacuous tests caught only by
  reviewer/advisor, and some suites were not executed at all."

A passing suite proves the code does something. It does not prove the tests would notice if the
code stopped doing it. This script breaks each control deliberately and asserts the suite goes
red. A mutation nothing catches means the control is untested, whatever the count says.

    /usr/bin/python3 scripts/verify_controls.py

It works on a **copy** of the repo in a temp directory. It never mutates the real tree.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
PYTHON = "/usr/bin/python3"


@dataclass
class Mutation:
    name: str
    file: str
    old: str
    new: str
    test_module: str
    breaks: str


MUTATIONS = [
    Mutation("scope_guard always permits", "scripts/scope_guard.py",
             '    tool_name = payload.get("tool_name") or ""',
             '    return Decision.permit()\n    tool_name = payload.get("tool_name") or ""',
             "tests.test_scope_guard", "every scope, port and ceiling denial"),

    Mutation("ceiling may be raised above the mode default", "scripts/scope.py",
             "    if ceiling > default_ceiling:", "    if False:",
             "tests.test_scope", "the §6 rule that a ceiling lowers but never raises"),

    Mutation("loop detection disabled", "scripts/no_handrolled_loops.py",
             "    for description, pattern in LOOP_PATTERNS:",
             '    return True, ""\n    for description, pattern in LOOP_PATTERNS:',
             "tests.test_step7_controls", "the 20-vs-10 request overrun"),

    Mutation("write authorisation disabled", "scripts/canary_check.py",
             "    if canary_proven(root, method, route, operation):",
             '    return True, ""\n    if canary_proven(root, method, route, operation):',
             "tests.test_step7_controls", "the undeletable-rows incident"),

    Mutation("nesting guard disabled", "scripts/no_nesting.py",
             'NESTING_TOOLS = frozenset({\n'
             '    "Agent", "Task", "TaskOutput", "TaskCreate", "TaskUpdate", "TaskList", "TaskGet", "TaskStop",\n'
             '    "SendMessage", "AskUserQuestion", "ExitPlanMode", "EnterPlanMode",\n'
             '})',
             "NESTING_TOOLS = frozenset()",
             "tests.test_agents", "silent subagent nesting"),

    Mutation("findings validation returns clean", "scripts/findings.py",
             "    return RecordResult(rid, violations)", "    return RecordResult(rid, [])",
             "tests.test_findings", "every findings schema and verification rule"),

    Mutation("evidence resolution always succeeds", "scripts/findings.py",
             '    if not candidate.is_file():', '    if False:',
             "tests.test_findings", "unresolvable evidence detection"),

    Mutation("promotion accepts a single signal", "scripts/scope_cli.py",
             "    if len(distinct) < 2:", "    if False:",
             "tests.test_scope_cli", "two-independent-signals attribution"),

    Mutation("baseline never finds an open bucket", "scripts/baseline_scan.py",
             "    if probe.status != 200:\n        return False\n    try:",
             "    return False\n    try:",
             "tests.test_baseline_scan", "the deterministic baseline's headline check"),

    Mutation("redaction disabled", "scripts/redact.py",
             "PATTERNS: list[tuple[str, re.Pattern[str]]] = [",
             "PATTERNS: list[tuple[str, re.Pattern[str]]] = []\n_DISABLED = [",
             "tests.test_redact", "credentials being kept out of the transcript"),

    Mutation("status regeneration becomes non-deterministic", "scripts/regen_status.py",
             '    as_of = timestamps[-1] if timestamps else "no recorded activity"',
             "    import datetime as _d\n    as_of = _d.datetime.now().isoformat()",
             "tests.test_regen_status", "byte-identical regeneration"),

    Mutation("report prints unverified findings", "scripts/report.py",
             '        if (needs_proof and not proven) or confidence != "confirmed":',
             "        if False:",
             "tests.test_report", "unverified findings being kept out of the client body"),

    Mutation("scaffolder skips interpreter verification", "scripts/new_engagement.py",
             "    yaml_version = verify_interpreter(args.python)",
             '    yaml_version = "unchecked"',
             "tests.test_new_engagement", "the fail-open interpreter hazard"),

    Mutation("agent roster validation returns clean", "scripts/validate_agents.py",
             "    return errors", "    return []",
             "tests.test_agents", "every agent card invariant"),

    Mutation("IDNA normalisation disabled", "scripts/scope_guard.py",
             '    host = host.strip().rstrip(".").lower()\n'
             '    if not host or host.isascii():\n'
             '        return host\n'
             '    try:\n'
             '        return host.encode("idna").decode("ascii").lower()\n'
             '    except (UnicodeError, UnicodeDecodeError, ValueError):\n'
             '        # Cannot be normalised -- return as-is; the caller will fail to match it and deny.\n'
             '        return host',
             '    return host.strip().rstrip(".").lower()',
             "tests.test_audit_regressions",
             "unicode/punycode spellings of the same host converging to one string"),

    Mutation("command-length bound raised enormously", "scripts/scope_guard.py",
             "MAX_ANALYSABLE_COMMAND = 8192", "MAX_ANALYSABLE_COMMAND = 1000000",
             "tests.test_audit_regressions",
             "the deny-rather-than-scan protection against the quadratic host regexes"),

    Mutation("wraparound testing window reverted", "scripts/scope_guard.py",
             "    if end <= start:\n"
             "        return minutes >= start or minutes < end\n"
             "    return start <= minutes < end",
             "    return start <= minutes < end",
             "tests.test_audit_regressions",
             "a 22:00-06:00 window, which would deny 24/7"),

    Mutation("scaffolder hook command reverts to f-string interpolation", "scripts/new_engagement.py",
             '        command = (f"RG_ENGAGEMENT_ROOT={shlex.quote(str(engagement_dir))} "\n'
             '                   f"{shlex.quote(interpreter)} {shlex.quote(str(script))}")',
             '        command = (f"RG_ENGAGEMENT_ROOT={engagement_dir} "\n'
             '                   f"{interpreter} {script}")',
             "tests.test_new_engagement",
             "shell injection via an engagement path or interpreter containing a quote"),

    Mutation("redaction count re-deduped", "scripts/redact.py",
             "    return text, found", "    return text, sorted(set(found))",
             "tests.test_audit_regressions",
             "the true count of redacted values, undercounted to the number of distinct classes"),

    Mutation("malformed JSONL tolerance removed", "scripts/regen_status.py",
             "            if isinstance(parsed, dict):\n"
             "                rows.append(parsed)",
             "            rows.append(parsed)",
             "tests.test_audit_regressions",
             "regen_status.py crashing on a non-object row instead of skipping it"),

    Mutation("framework-script allowlist emptied", "scripts/scope_guard.py",
             'FRAMEWORK_SCRIPTS = frozenset({\n'
             '    "rate_probe.sh", "baseline_scan.py", "scope_cli.py", "new_engagement.py",\n'
             '    "regen_status.py", "report.py", "validate_findings.py", "validate_agents.py",\n'
             '    "verify_controls.py",\n'
             '})',
             'FRAMEWORK_SCRIPTS = frozenset()',
             "tests.test_audit_regressions",
             "the framework denying its own documented commands, including rate_probe.sh"),
]


def run_module(root: Path, module: str) -> bool:
    """True if the test module PASSES."""
    proc = subprocess.run(
        [PYTHON, "-m", "unittest", module],
        cwd=root, capture_output=True, text=True, timeout=600,
    )
    return proc.returncode == 0


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp) / "repo"
        shutil.copytree(REPO, root, ignore=shutil.ignore_patterns(
            ".git", "__pycache__", "*.pyc"))

        print("Baseline: the suite must be green before any mutation means anything.")
        modules = sorted({m.test_module for m in MUTATIONS})
        for module in modules:
            if not run_module(root, module):
                print(f"  BASELINE FAILURE in {module} -- fix that first", file=sys.stderr)
                return 1
        print(f"  {len(modules)} modules green.\n")

        undetected: list[Mutation] = []
        print(f"Injecting {len(MUTATIONS)} faults:\n")

        for mutation in MUTATIONS:
            target = root / mutation.file
            original = target.read_text(encoding="utf-8")
            if mutation.old not in original:
                print(f"  SKIP    {mutation.name}")
                print(f"          mutation site not found in {mutation.file} -- "
                      "the code moved and this check is now vacuous")
                undetected.append(mutation)
                continue

            target.write_text(original.replace(mutation.old, mutation.new, 1), encoding="utf-8")
            try:
                still_green = run_module(root, mutation.test_module)
            finally:
                target.write_text(original, encoding="utf-8")

            if still_green:
                print(f"  MISSED  {mutation.name}")
                print(f"          {mutation.test_module} stayed GREEN with {mutation.breaks} broken")
                undetected.append(mutation)
            else:
                print(f"  caught  {mutation.name}")

        print()
        if undetected:
            print(f"{len(undetected)} of {len(MUTATIONS)} faults went undetected.", file=sys.stderr)
            print("Those controls are not actually covered, whatever the test count says.",
                  file=sys.stderr)
            return 1

        print(f"All {len(MUTATIONS)} injected faults were caught. The tests discriminate.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
