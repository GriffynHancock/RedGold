# RedGold

RedGold is a Claude Code plugin for authorized web and API security auditing of startup products
and small-business compliance work. It scaffolds an engagement with a machine-enforced scope
boundary, runs a staged audit through a capped agent roster, and produces a client report built
only from findings that were independently re-executed on disk — not from the conversation that
produced them.

## Running an engagement

The shortest honest path from nothing to a report. Every command below is a real invocation —
run `/rg:<name>` inside Claude Code, or read the matching file in `commands/*.md` for the full
flag set, refusals, and worked examples before typing anything.

1. **Install.** From the framework repo root:

   ```sh
   /plugin marketplace add ~/RedGold
   /plugin install rg@redgold
   ```

   For a one-session dev run without installing, launch Claude Code with
   `claude --plugin-dir ~/RedGold` instead.

2. **Scaffold the engagement.** `/rg:new` — gathers the authorization facts by asking (who
   authorized it, what they can authorize, the signed document's path, the window, and for
   `redteam` a named emergency contact) and writes `~/engagements/<client>-<yyyy-mm>/`. It
   **refuses if the authorization document does not exist on disk** — have it saved before you
   start.

3. **Record and promote assets.** Inside the engagement directory:

   ```sh
   /rg:scope add-candidate <host> --discovery-method "..." --signal 'CLASS:value@source' --signal 'CLASS:value@source'
   /rg:scope promote <host> --confirm
   ```

   Promotion needs **two independent attribution-signal classes** (or explicit
   `CLIENT_CONFIRMED`) plus the operator's `--confirm`. It never widens scope — an asset outside
   the boundary is refused, not promoted.

4. **Gate before any tier-2 write.** `/rg:gate plan` writes the phase plan naming the assets,
   test classes, and write endpoints with their budgets; `/rg:gate approve` records the
   operator's sign-off. **This is required before any tier-2 write** — `canary_check.py` only
   permits a write on a canary proven deleted or on this pre-approval, and skipping the gate is
   why writes get denied, not a bug to work around.

5. **Baseline, then test.** Run the fixed-checklist baseline against confirmed assets
   (`scripts/baseline_scan.py --root .`), then run the staged audit through the agent roster,
   recording findings as they're independently reproduced on disk.

6. **Report.** `/rg:report` regenerates `status.md` from the ledgers and writes
   `deliverables/report-tier<N>.md` from validated findings only — nothing from the conversation
   that produced a claim.

### Demo prompt

Paste this into a session opened inside an engagement directory to pick up where the last one
left off:

```
Read scope.yaml and status.md. List the CONFIRMED assets and run the P10 baseline
(scripts/baseline_scan.py --root .) against them. For anything you find, record a finding with
an evidence_ptr that resolves on disk — not prose — then run
scripts/validate_findings.py --root . before telling me what you found.
```

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
- **`/rg:gate`** — write and approve the phase plan (Gate 1), or list and resolve a recorded
  scope-deviation blocker (Gate 2). Gate 1 (`plan`, `show`, `approve`, `blockers`, `resolve`) is
  built and backs `canary_check.py`'s pre-approval path — see `commands/gate.md`. The part that
  is **not built** is the automatic detection that raises a Gate 2 blocker in the first place
  (§9.3.2 plan-deviation checking in `scope_guard.py`); `blockers`/`resolve` work on whatever a
  blocker-writer records, and nothing currently writes one automatically.
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

1. **Gate 2 detection / plan deviation (§9.3.2)** — Gate 1 (`plan`, `approve`) and Gate 2's
   resolution path (`blockers`, `resolve`) are built (`scripts/gate_cli.py`). What is missing is
   the automatic check: `scope_guard.py` enforces *scope*, not *the plan*, so a confirmed,
   in-scope, under-ceiling asset the plan does not name sails through without ever raising a
   blocker to resolve.
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
