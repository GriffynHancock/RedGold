# RedGold

RedGold is a Claude Code plugin for authorized web and API security auditing of startup products
and small-business compliance work. It scaffolds an engagement with a machine-enforced scope
boundary, runs a staged audit through a capped agent roster, and produces a client report built
only from findings that were independently re-executed on disk — not from the conversation that
produced them.

This is unreleased commercial work belonging to the author. It is not a public tool.

## The problem it solves

An agentic auditor left to its own judgement will happily test something it was never authorised
to touch, claim a finding it cannot reproduce, and leave test data behind on someone else's
system. Each of those is a specific, well-known failure mode of letting an LLM drive live testing
without a mechanical layer underneath it:

- **Scope creep.** The agent finds an interesting-looking host next to the one it was told to
  test and just tries it.
- **Unverified findings.** The agent describes a vulnerability it reasoned about rather than one
  it actually triggered and observed.
- **Test debris.** The agent creates an account, a file, or a write, and never confirms it was
  removed.

RedGold's answer is to keep the agent's authority to act narrower than its ability to reason,
and to enforce that narrowing with code the agent cannot talk its way around — not with prose
instructions the agent is asked to follow.

## Architecture in brief

Two repos, deliberately separate:

- **The framework repo** (this one) — the plugin itself: commands, playbooks, control scripts,
  tests. No client or target data ever lives here (see `CLAUDE.md`, hard rule 3).
- **Per-engagement repos**, scaffolded by `/rg:new` into `~/engagements/<client>-<yyyy-mm>/` —
  one per client, holding that engagement's scope boundary, ledgers, evidence, and deliverable.
  Nothing crosses back into the framework repo except through `/rg:harvest` (see below), and only
  redacted.

Within an engagement, work is split between an **orchestrator** (`rg-lead`) that reads the
authorization boundary, proposes a phase plan, and dispatches work, and **worker** subagents that
actually run tests. Workers cannot spawn further subagents (`no_nesting.py`) and cannot see each
other's conversation state — only what the orchestrator puts in their brief and what is written to
the shared ledgers.

Every engagement directory runs on a three-file contract:

- **`CLAUDE.md`** — the engagement's own rules: what's authorised, what mode, hard limits.
- **`status.md`** — current state only, present tense, generated from the ledgers rather than
  hand-edited.
- **`session.md`** — the handoff: what changed, what's next, what not to repeat.

## Install and run

Validate the plugin manifest:

```sh
claude plugin validate .
```

Load it during development without publishing:

```sh
claude --plugin-dir /home/hiranya/RedGold
```

Scaffold a new engagement (operator-initiated; gathers authorization facts by asking, never by
inference):

```sh
/rg:new
```

Then the rest of the command set, run inside the engagement directory:

- **`/rg:scope`** — show the authorization boundary, record a discovered candidate asset, promote
  one to testable, or amend the boundary in writing.
- **`/rg:gate`** — present a phase plan for approval or resolve a recorded scope-deviation
  blocker. **Not built** — see below.
- **`/rg:harvest`** — at engagement close, promote redacted lessons into this repo's playbook
  library. **Not built** — see below.
- **`/rg:report`** — generate the client deliverable from validated findings on disk.

Take the exact invocations from `commands/*.md` — each command file documents its own flags,
refusals, and what it does and does not enforce.

## What is enforced

From `status.md`, one line per control, all wired on `PreToolUse`/`PostToolUse`/`SubagentStop`
unless noted:

| Control | Script | Denies |
|---|---|---|
| Scope + ports + ceiling | `scope_guard.py` | out-of-scope host, unauthorised port, over-ceiling action, undeterminable target, outside window |
| Hand-rolled loops | `no_handrolled_loops.py` | loops, `xargs`, brace expansion, curl globbing, `-Z`, backgrounded requests |
| Write authorisation | `canary_check.py` | a write with neither a canary proven deleted nor plan pre-approval |
| Subagent nesting | `no_nesting.py` | a worker calling `Agent`/`Task`, recorded as a blocker |
| Findings validation | `validate_findings.py` | a subagent stopping with invalid findings; auto-demotes unresolvable evidence |
| Credential redaction | `redact.py` | strips credential values from tool output, keeping class + length so the finding stays reportable |
| Asset promotion | `scope_cli.py` | promotion on one signal, on an IP, or outside the boundary |
| Baseline (P10) | `baseline_scan.py` | n/a — fixed checklist, records negatives |
| Status / report | `regen_status.py`, `report.py` | unverified above-Low findings never reach the client body |

## What is NOT enforced

Copied faithfully from `status.md` — do not describe any of these as working:

1. **Gate 2 / plan deviation (§9.3.2)** — `scope_guard.py` enforces *scope*, not *the plan*. A
   confirmed, in-scope, under-ceiling asset the plan does not name sails through. Gate 2 is
   currently a rule, not a control.
2. **`cleanup_gate.py`** — nothing stops an engagement closing with outstanding cleanup debt.
3. **`session_start.py`** — no context reload across compaction.
4. **Most §5.5 attribution-probe constraints** — rate limiting, `purpose: attribution` logging,
   and discarding observations as evidence are all unimplemented. Only the tier 0–1 restriction
   holds.
5. **Off-host egress filtering (§9.9)** — the only real boundary. Does not exist.

`scope_guard.py` is defence-in-depth, not a security boundary. The honest claim is
**"out-of-scope targets are refused by tooling and logged,"** never "cannot happen." Anything the
agent runs inside the same host as the enforcement layer can, in principle, edit that layer; there
is no filtering outside the guest that would stop it.

## Testing

```sh
/usr/bin/python3 -m unittest discover -s tests
/usr/bin/python3 scripts/verify_controls.py
```

The first is the ordinary suite. The second breaks each control deliberately — reverts the fix,
confirms the check now fails, restores it — to prove the tests would actually notice if a control
stopped working. A passing suite only shows the code does something; fault injection is what shows
that something would catch it stopping. Run the second script before trusting a green first one.

## The audit history

Three adversarial rounds — a hostile spec review, a structural audit of the design's internal
consistency, and a code-level audit run as two rotating hostile personas against the built
controls — found **21 real defects** that the project's own self-written suite and prior review
passes had missed, including one that let an unverified finding reach a client report. The
code-level round alone found 11 defects that 308 self-written tests had not caught, and every one
now has a regression test in `tests/test_audit_regressions.py`.

This is the honest headline for this project, not a footnote: a framework's own tests are written
by whoever wrote the code, and inherit the same blind spots exactly. The methodology — how to
frame an adversarial pass so it produces attacks instead of summaries, what each framing catches,
and the recorded yield of each round — is in `playbooks/_generic/adversarial-framings.md`. Run
those framings against this repo again before pointing it at a first real target.

## Interpreter note

Hooks must pin an absolute interpreter path that has PyYAML installed — `/usr/bin/python3` on this
machine — never a bare `python3` resolved through `$PATH`. A `PreToolUse` hook that dies on import
does not deny the tool call; it **fails open**, silently. `/rg:new` tests the interpreter by
actually importing `yaml` through it before pinning it into the scaffolded engagement's
`.claude/settings.json`.
