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
             "    description = next(",
             '    return True, ""\n    description = next(',
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

    # --- RG-1 release 1: the coverage counterweights (§8.6, §8.2) --------------------------
    # Everything else in RG-1 subtracts severity. These two are the only things stopping the
    # programme's measurable output being "fewer findings", which is indistinguishable from a
    # hollow engagement. A control without a fault to break it grows the count, not the coverage.

    Mutation("stale-report gate disabled", "scripts/report.py",
             "    if written < newest:", "    if False:",
             "tests.test_report",
             "a deliverable that predates its own findings closing the engagement"),

    Mutation("zero-zero rule disabled", "scripts/gate_cli.py",
             "    if not finding_count and not absent_count:", "    if False:",
             "tests.test_gate_cli",
             "a phase completing with zero findings and zero record of having looked"),

    # The two above are opt-in: an operator who runs neither `report.py --check` nor
    # `gate_cli.py complete` is stopped by nothing. `close` is the one place both are
    # unconditionally applied, so it is the only thing making either of them bind.
    Mutation("engagement close gate disabled", "scripts/gate_cli.py",
             "    if reasons:", "    if False:",
             "tests.test_gate_cli",
             "an engagement closing with a stale deliverable, no record of having looked, or no "
             "completed phase"),

    # --- RG-1 release 2, E2: the applicability filter (§4.1) --------------------------------

    Mutation("HSTS scheme filter removed", "scripts/baseline_scan.py",
             '    if header == "strict-transport-security":', "    if False:",
             "tests.test_baseline_scan",
             "HSTS demanded of a plaintext origin -- a category error that filed two findings "
             "whose own impact string contradicts itself on a connection already in plaintext"),

    # The other half of E2 is that collapsing twelve records into one must not collapse the
    # *number* with them. A gap that shrinks when you tidy the storage is a gap being hidden.
    Mutation("collapsed coverage record understates the gap", "scripts/baseline_scan.py",
             '        "checks_skipped": len(skipped_checks),',
             '        "checks_skipped": 1,',
             "tests.test_baseline_scan",
             "twelve checks that never ran being reported as one"),

    # --- RG-1 release 2, E1: the environment gate (§3.1, §4.2, §6) --------------------------
    #
    # Seven of eleven findings on a live engagement -- including the only critical -- were
    # artifacts of testing a development stack on the operator's laptop and reporting its
    # dev-only components as the client's production system. The engagement never once asked
    # what environment it was in. Each fault below is one of the answers going missing again.

    Mutation("environment gate disabled", "scripts/gate_cli.py",
             "    if refusal:", "    if False:",
             "tests.test_gate_cli",
             "Gate 1 approving an engagement that never established which environment it is "
             "testing -- the omitted question that generated all seven bad findings"),

    Mutation("environment vocabulary opened", "scripts/scope.py",
             "    if value not in ENVIRONMENTS:", "    if False:",
             "tests.test_scope",
             "an unrecognised environment string clearing Gate 1, and then selecting no cap "
             "column that exists"),

    Mutation("environment cap inverted", "scripts/findings.py",
             "        index = min(SEVERITIES.index(before), SEVERITIES.index(cap))",
             "        index = max(SEVERITIES.index(before), SEVERITIES.index(cap))",
             "tests.test_findings",
             "the cap becoming a floor -- a `low` finding in staging raised to `high` by the "
             "environment it was found in, which is the one direction RG-1's pipeline forbids"),

    Mutation("unknown environment reads as non-production", "scripts/findings.py",
             '    if isinstance(value, str) and value in ENVIRONMENT_SEVERITY_CAP:\n'
             '        return value\n'
             '    return "production"',
             '    if isinstance(value, str) and value in ENVIRONMENT_SEVERITY_CAP:\n'
             '        return value\n'
             '    return "development"',
             "tests.test_findings",
             "an unanswered question capping a client's severities -- fail-closed inverted into "
             "the flattering direction, which is the 2026-08-04 `Critical!!` incident's shape"),

    Mutation("code_defect default removed", "scripts/findings.py",
             '    if str(record.get("discovered_by", "")) in CODE_DEFECT_PRODUCERS \\',
             '    if False and str(record.get("discovered_by", "")) in CODE_DEFECT_PRODUCERS \\',
             "tests.test_findings",
             "every whitebox finding capped by the laptop the source was read on -- the missing "
             "unique constraint, the absent fulfilment fallback and the dead sweeper, all three "
             "affecting paying customers in production"),

    Mutation("environment discrepancy rule disabled", "scripts/findings.py",
             '    if contradicting and str(record.get("environment_at_test", "")) == "production" \\',
             '    if False and str(record.get("environment_at_test", "")) == "production" \\',
             "tests.test_findings",
             "an asset contradicting its own declared environment and nothing noticing"),

    Mutation("discrepant findings reach the report body", "scripts/report.py",
             '        if "ENVIRONMENT_DISCREPANCY" in blocking_codes:', "        if False:",
             "tests.test_report",
             "§4.2's action clause -- the affected findings not entering the report body until "
             "an operator has said which side was wrong"),

    # --- RG-2 step 1: the reconciliation tripwire's guard half (rg2-containment §5) ----------
    #
    # Until this landed, `status.md` and the README claimed out-of-scope targets were "refused by
    # tooling and logged". The second half was false. These faults are each a way for it to
    # quietly become false again -- either by logging nothing, or by logging something that
    # cannot be joined against the gateway's egress log, which is the only reason the rows exist.

    Mutation("decision logging disabled", "scripts/scope_guard.py",
             "    try:\n        if root is None:",
             "    return\n    try:\n        if root is None:",
             "tests.test_scope_guard",
             "every scope.allow/scope.deny row -- reconciliation blind in both directions again"),

    Mutation("allow decisions stop being logged", "scripts/scope_guard.py",
             "    if decision.allow and not targets:\n        return None",
             "    if decision.allow:\n        return None",
             "tests.test_scope_guard",
             "the §9.9 incident row: a gateway block on traffic the guard allowed is only "
             "detectable if the allow was recorded"),

    Mutation("logging an allow becomes an allow decision", "scripts/scope_guard.py",
             "    if decision.allow:\n        return\n",
             '    if decision.allow:\n'
             '        json.dump({"hookSpecificOutput": {"hookEventName": "PreToolUse",\n'
             '                   "permissionDecision": "allow",\n'
             '                   "permissionDecisionReason": "logged"}}, sys.stdout)\n'
             '        return\n',
             "tests.test_scope_guard",
             "§5.2.1 -- the guard auto-approving the call and suppressing the operator's own "
             "permission prompt, which is privilege escalation wearing a logging feature's coat"),

    Mutation("a ledger write failure fails the tool call", "scripts/scope_guard.py",
             "    except Exception as exc:  # noqa: BLE001 -- deliberately total; see the module docstring\n"
             "        print(",
             "    except Exception as exc:  # noqa: BLE001 -- deliberately total; see the module docstring\n"
             "        raise\n"
             "        print(",
             "tests.test_scope_guard",
             "§5.2.2 -- a full disk turning every tool call into a crash, which gets the hook "
             "disabled, after which nothing is logged at all"),

    Mutation("undeterminable denials folded into scope.deny", "scripts/scope_guard.py",
             "    elif reason.startswith(UNDETERMINABLE_PREFIX):",
             "    elif False:",
             "tests.test_scope_guard",
             "the one metric that shows the target parser degrading over time"),

    Mutation("guard resolves hosts in-guest", "scripts/scope_guard.py",
             '    path = root / "ledger" / RESOLUTION_LEDGER',
             '    import socket  # a resolver the target can poison\n'
             '    path = root / "ledger" / RESOLUTION_LEDGER',
             "tests.test_scope_guard",
             "the ban on in-guest resolution -- a lookup inside the workload is both egress and "
             "poisonable by the target it is looking up"),

    Mutation("a missing resolution record reads as resolved", "scripts/scope_guard.py",
             "        else:\n            missing = True",
             "        else:\n            missing = False",
             "tests.test_scope_guard",
             "the unresolved marker -- a row with no IPs that claims to have them is a join that "
             "silently matches nothing"),

    Mutation("corr_id is constant", "scripts/scope_guard.py",
             '    value = (int(moment.timestamp() * 1000) << 80) | int.from_bytes(os.urandom(10), "big")',
             "    value = 0",
             "tests.test_scope_guard",
             "the exact join key, and with it any ability to spot a gap in the rows"),

    Mutation("ledger truncates instead of appending", "scripts/scope_guard.py",
             "    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)",
             "    handle = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)",
             "tests.test_scope_guard",
             "every decision but the last one"),

    Mutation("check_url stops logging", "scripts/scope_guard.py",
             "    record_decision(root, payload, decision, boundary=boundary, confirmed=confirmed,\n"
             '                    operation=f"check_url: {url}", tier=tier)',
             "    pass",
             "tests.test_scope_guard",
             "§5.2.4 -- rate_probe.sh, RedGold's own sanctioned burst path, showing up on the "
             "gateway as unattributed traffic and training the operator to dismiss the alarm"),

    Mutation("attribution probes stop being marked", "scripts/scope_guard.py",
             "    probe = decision.allow and any(host not in confirmed for host, _ in targets)",
             "    probe = False",
             "tests.test_scope_guard",
             "§5.3 -- the unenforced §5.5 carve-out going back to being invisible outside a code "
             "comment"),

    Mutation("scope_hash no longer pins the scope file", "scripts/scope_guard.py",
             '    return "sha256:" + hashlib.sha256(path.read_bytes()).hexdigest()',
             '    return "sha256:" + hashlib.sha256(b"").hexdigest()',
             "tests.test_scope_guard",
             "which boundary a decision was made against -- an amended scope inheriting the "
             "audit trail of the old one"),

    # --- the adversarial review of 2026-08-20 (docs/research/rg1-code-review-2026-08-20.md) ---
    #
    # Twelve defects, two critical, every one of them green against 540 tests and 33 injected
    # faults. That is the lesson these entries exist to stop repeating: the faults below are not
    # "more coverage", they are the specific reverts that the previous 33 could not see, because
    # they perturbed values where the defects were in *which field a decision reads from* and
    # *which severity a gate keys on*.

    # S1 -- critical. The cap derived its pre-cap severity from `severity_derivation`, a field on
    # the record that every producer can write, and wrote the result back over `severity`. On a
    # production engagement the cap is None, so nothing is disclosed -- and the severity changed
    # anyway. A proven, independently verified `high` rendered to the client as `low`.
    Mutation("the cap reads its input back from the record", "scripts/findings.py",
             '    before = str(record.get("severity", ""))',
             '    before = prior["before_env_cap"] \\\n'
             '        if isinstance(prior.get("before_env_cap"), str) and prior["before_env_cap"] \\\n'
             '        else str(record.get("severity", ""))',
             "tests.test_findings",
             "the one property that makes the cap a transform rather than a severity-setting "
             "primitive any writer of a findings record can drive"),

    # S1, second half. Without the stamp, DERIVATION_MISMATCH cannot fire anywhere in the report
    # pipeline: the cap rewrites `severity` to equal `after_env_cap` immediately before
    # `validate_record` compares the two, so they are equal by construction on the only path a
    # client's document travels.
    Mutation("a severity lowered beneath its own audit trail is not recorded", "scripts/findings.py",
             '    if conflict is not None:\n        derivation["derivation_conflict"] = conflict',
             '    if False:\n        derivation["derivation_conflict"] = conflict',
             "tests.test_findings",
             "the control §6 names as 'how a hand-edited severity gets caught', on the only path "
             "that reaches a client"),

    # S2 -- critical. `UNVERIFIED_ABOVE_LOW` and `SPECULATED_ABOVE_LOW` keyed on the POST-cap
    # severity, so capping to `low` -- which ephemeral-preview does unconditionally -- silenced
    # both, and a SPECULATED, never-verified `critical` reached the client report body.
    Mutation("the verification gates key on the capped severity", "scripts/findings.py",
             "    return SEVERITIES[max(ranks)]",
             '    return str(record.get("severity", "")).lower()',
             "tests.test_findings",
             "§10.3 itself -- a severity transform switching off the gates that are about "
             "`status` and `verified` and are not about severity at all"),

    Mutation("the report's verification gate keys on the capped severity", "scripts/report.py",
             "    return findings_mod.gating_severity(record) in findings_mod.ABOVE_LOW",
             '    return str(record.get("severity", "")).lower() in findings_mod.ABOVE_LOW',
             "tests.test_report",
             "the report's own promise that unverified technical findings above Low do not "
             "appear in the body -- the same class as the audit defect that put an unverified "
             "finding into a client report"),

    # S3 -- high. The empty-corpus exemption ran before the does-the-file-exist check, so an
    # engagement with zero findings closed with no client deliverable in existence, while `close`
    # printed that the file postdated every finding.
    Mutation("an empty corpus exempts the deliverable again", "scripts/report.py",
             '    if not deliverable.is_file():\n        return (f"{REPORT_STALE}: {deliverable.name} does not exist.',
             '    if total == 0:\n        return None\n'
             '    if not deliverable.is_file():\n        return (f"{REPORT_STALE}: {deliverable.name} does not exist.',
             "tests.test_gate_cli",
             "an engagement closing with no client deliverable at all, and a fabricated assurance "
             "about the file printed by the control that exists to prevent fabricated assurance"),

    # S4 -- high. `not_attempted` -- "we did not look" -- fell through the `elif` and was counted
    # as a finding, so a phase closed on a single record proving nobody probed anything.
    Mutation("a record saying we did not look counts as a finding", "scripts/gate_cli.py",
             "        elif result not in NOT_A_FINDING_RESULTS:",
             '        elif result != "not_applicable":',
             "tests.test_gate_cli",
             "the zero-zero rule, against the canonical input it exists to refuse"),

    # S5 -- high. A record's own `environment_at_test` overrode the signed scope downward with no
    # cross-check anywhere: one agent-written key took a critical to a low on production.
    Mutation("a record may talk its own environment down again", "scripts/findings.py",
             '    return engagement, {"engagement_declared": engagement, "record_declared": stated}',
             "    return stated, None",
             "tests.test_findings",
             "the declaration-vs-declaration check -- the half of §4.2 that needs no signals and "
             "no contact with the asset, only scope.yaml and the record"),

    # S6 -- medium. The `code_defect` default was gated on a value nothing in the repository
    # produced, so it fired on 0% of everything while reading as coverage.
    Mutation("the code_defect producer stops producing", "agents/rg-codeaudit.md",
             '"discovered_by": "rg-codeaudit"', '"discovered_by": "baseline_scan"',
             "tests.test_findings",
             "every whitebox finding on a development-declared engagement capped by the laptop "
             "the source was read on -- the default working perfectly on input no producer emits"),

    Mutation("clearing the code_defect default costs nothing again", "scripts/findings.py",
             "        if not isinstance(reason, str) or not reason.strip():",
             "        if False:",
             "tests.test_findings",
             "the one bypass in RG-1 cheaper than the thing it bypasses -- four characters "
             "suppressing a whitebox finding with no reason, no `by` and no violation"),

    # S7 -- medium. This gate's action clause holds every finding on the asset out of the client
    # report body, so a false positive is a suppression event. Both reverts below fire it on
    # ordinary production traffic.
    Mutation("a publishable test key is a blocking signal again", "scripts/baseline_scan.py",
             'TEST_KEY_RE = re.compile(r"\\bsk_test_[A-Za-z0-9]{8,}")',
             'TEST_KEY_RE = re.compile(r"\\b[ps]k_test_[A-Za-z0-9]{8,}")',
             "tests.test_baseline_scan",
             "every production docs page, 'try it' widget and SDK landing page that embeds a "
             "`pk_test_` key exactly as the vendor intends"),

    Mutation("ambiguous dev-tool tokens return to the header list", "scripts/baseline_scan.py",
             'DEV_TOOL_HEADER_TOKENS = ("mailpit", "mailhog", "mailcatcher", "adminer",\n'
             '                          "webpack-dev-server")',
             'DEV_TOOL_HEADER_TOKENS = ("mailpit", "mailhog", "mailcatcher", "mailtrap", "adminer",\n'
             '                          "webpack-dev-server", "vite", "flower")',
             "tests.test_baseline_scan",
             "a production Celery dashboard, a Vite-built SPA and anything whose banner says "
             "Mailtrap -- the reasoning was written out for the title list and never crossed the "
             "two-line gap to the header list"),

    # S8 -- medium. status.md and the client report counted the coverage gap by opposite rules and
    # could disagree by twelve on the same corpus, always flatteringly in status.md.
    Mutation("status.md allow-lists the gap bucket again", "scripts/regen_status.py",
             '        gaps = [r for r in records if r.get("result") == "not_applicable"\n'
             '                and r.get("not_applicable_reason") not in INAPPLICABLE_REASONS]',
             '        gaps = [r for r in records if r.get("not_applicable_reason") == "no_http_response"\n'
             '                or (r.get("result") == "not_applicable" and "not_applicable_reason" not in r)]',
             "tests.test_regen_status",
             "the file CLAUDE.md calls authoritative reporting zero unassessed services while "
             "the client report reports twelve -- failing open in the flattering direction"),

    # S9 -- medium. `hash()` is randomised per process, so a re-scan re-raised the same asset's
    # blocker under a new id and `resolve` could never stick to the asset.
    Mutation("blocker ids come from hash() again", "scripts/baseline_scan.py",
             '    return "B-" + hashlib.sha256(base.encode("utf-8")).hexdigest()[:12]',
             '    return f"B-{abs(hash(base)) % 1000:03d}"',
             "tests.test_baseline_scan",
             "a discrepancy that is permanently unresolvable by re-scan, and a 1-in-1000 "
             "collision that resolves the wrong asset's blocker"),

    # S10 -- low. `close` never called `check_gate`, so an engagement whose approval was voided
    # mid-flight -- including by an amendment changing `environment` -- closed clean.
    Mutation("close stops validating Gate 1", "scripts/gate_cli.py",
             "    if approval_id is not None:", "    if False:",
             "tests.test_gate_cli",
             "§9.7 -- a `gate.close` row asserting nothing about the gate it was closed under"),

    # Not from the review: confirmed live by running the evaluator. `-i`/`-r`/`-m` were matched
    # tool-blind, so the hook denied `curl -i` and `curl -m 5` -- among the safest commands in the
    # product. A refusal that fires on healthy input gets the hook switched off (§2.3), and a
    # switched-off hook is every hand-rolled loop back again.
    Mutation("wget's flags are matched tool-blind again", "scripts/no_handrolled_loops.py",
             '    ("a wget input file", re.compile(r"\\bwget\\b"),',
             '    ("a wget input file", re.compile(r""),',
             "tests.test_step7_controls",
             "`curl -i https://host/health` -- close to the single most ordinary command an "
             "operator types -- being refused by the loop guard"),
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
