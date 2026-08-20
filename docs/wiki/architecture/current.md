---
title: RedGold architecture as it stands, 2026-08-20
wiki_id: architecture-current
question: What is RedGold today — its parts, its agents, its controls, its lifecycle, and which field does each control actually read at the moment it runs?
subject: RedGold architecture
status: partial
last_verified: 2026-08-20
verified_against: repo working tree at commit c0a20bd. Every code claim read from the file named. Specs read at the same commit.
recheck_trigger: re-derive §4 and §6 after any commit touching scripts/findings.py, scripts/report.py, scripts/gate_cli.py, scripts/baseline_scan.py, scripts/new_engagement.py or agents/*.md
sources:
  - url: docs/specs/redgold/README.md
    kind: primary
  - url: docs/specs/rg1-finding-integrity.md
    kind: primary
  - url: docs/specs/rg2-containment.md
    kind: primary
  - url: docs/wiki/claude-code/hooks.md
    kind: secondary
related:
  - architecture-proposed
  - claude-code-hooks
  - redgold-hooks-facts
---

# RedGold architecture as it stands

**This page is descriptive.** It records what exists on 2026-08-20. It proposes nothing. The
proposal is [proposed.md](proposed.md) and is a separate document on purpose.

Where a spec and the code disagree, **the code is reported as the truth and the disagreement is
recorded as a defect**, per CLAUDE.md design judgement 5 (*check the code, not the document
describing the code*).

## Index

| § | Contains |
|---|---|
| 1 | The three parts, and the trust boundaries between them |
| 2 | The agent roster — as shipped, and where it differs from the spec |
| 3 | The engagement lifecycle, ordered, derived from the code |
| 4 | The field-level producer/consumer map — the thing that did not exist |
| 5 | The control inventory, graded, sited on the lifecycle |
| 6 | The mechanical walk: controls whose inputs are unproduced, late, or overwritten |
| 7 | Built / specced / neither |
| 8 | Where the composition does not cohere |

---

## 1. The three parts, and the trust boundaries

CLAUDE.md names three systems with different trust properties; RG-4 adds a fourth upstream of all
of them `[SOURCE: docs/specs/rg4-scoping-questionnaire.md §1.3]`. Conflating any two is a design
error, and the boundaries between them are where the design's real content lives.

| Part | Principal | Runs on | Trust | Built? |
|---|---|---|---|---|
| **0. Client scoping** — `rg-scoping` skill | the client | the client's own Claude, on documents the operator may not read | **Weakest of all.** No hooks, no ledgers, no enforcement. Everything it emits is a client claim over an untrusted channel | **Not built.** RG-4 is a design document; `rg4_ingest.py` does not exist |
| **1. Framework development** — this repo | operator | macOS or a working guest | Trusted. **No client data, no targets, ever** (hard rule 3) | Built |
| **2. Deployment and scoping** — `rg-setup` | operator's macOS account | macOS host, *outside* containment | Trusted. Host access. Never touches a target | **Not built.** Specced in `rg2-containment.md` §3.1 |
| **3. Auditing and pentesting** — the worker agents | `redgold`, non-sudo, `--cap-drop=ALL` container | `rg-work` VM | **Untrusted.** No host access, no principal on the filtering machine | Agents built; **the containment they are specified to run inside does not exist** |

`[SOURCE: CLAUDE.md; docs/specs/rg2-containment.md §3]`

### 1.1 The boundaries, and which of them is real

| Boundary | Direction | What enforces it today |
|---|---|---|
| Client documents → bundle | client → operator | **Nothing.** A prompt in the client's Claude. RG-4 §10 states this plainly: *"It is a prompt. A user who wants a different bundle can get one."* |
| Bundle → `scope.yaml` | operator ingest | **Partially.** `new_engagement.py` refuses a boundary that does not parse, an absent authorization document, and an interpreter without PyYAML. `rg4_ingest.py` does not exist |
| Framework repo ↔ engagement repo | both | Convention plus hard rule 3. **No mechanism.** `/rg:harvest` is a command, not a filter |
| Workload → network | outbound | `scope_guard.py`, a **heuristic**. The real boundary — off-host egress filtering — **does not exist** `[SOURCE: status.md "NOT enforced" item 5]` |
| Workload → operator (findings, evidence) | outbound | **Nothing mechanical.** Every byte is attacker-influenced. `rg2-containment.md` §3.3 specifies seven rules for this direction; none is implemented |
| Guest → host (VM RPC channel) | outbound | **Nothing.** `rg2-containment.md` §4.1 establishes the `guest_rpc.rpci.auth.cmd.info-*` restriction is **off by default**, so this is a present-tense hole, not a research question |

**The single most load-bearing sentence about the current state:** the only layer graded
**BOUNDARY** in `rg2-containment.md` §1.1 — nftables default-deny on a separate VM — is the one
layer that has not been built. Everything that exists is graded advisory, heuristic,
defence-in-depth or detection by RedGold's own convention.

### 1.2 The grading convention used throughout this page

From `rg2-containment.md` §1, extended there beyond `07-enforcement.md` §9.8's four grades:

- **Boundary** — stops the thing regardless of the workload's cooperation, enforced outside the
  workload's blast radius.
- **Boundary precondition** — not the control, but if it fails the boundary is *bypassed* rather
  than weakened.
- **Defence-in-depth** — raises cost, survivable to defeat.
- **Heuristic** — works on the ordinary case, enumerably defeatable.
- **Detection** — stops nothing, proves what happened.
- **Advisory** — a prompt.

One grade is used on this page that the convention does not have, because the walk in §6 needed
it: **inert** — a control that is wired, tested, and cannot fire on any input a current producer
generates.

---

## 2. The agent roster — as shipped

Seven cards exist in `agents/`. The cap of seven is deliberate and holds
`[SOURCE: docs/specs/redgold/06-agents.md §8]`.

| Agent | Model | Memory | `tools:` **as shipped** | Runs as |
|---|---|---|---|---|
| `rg-lead` | opus | — | Read, Grep, Glob, Write | **main session**, never dispatched |
| `rg-recon` | sonnet | project | Bash, WebFetch, Read, Write | subagent |
| `rg-surface` | sonnet | project | Bash, WebFetch, Read, Write | subagent |
| `rg-codeaudit` | sonnet | project | Read, Grep, Glob, Bash, Write | subagent |
| `rg-webtest` | sonnet | project | Bash, WebFetch, Read, Write | subagent |
| `rg-verify` | sonnet | — | **Bash, WebFetch, Read** | subagent |
| `rg-report` | sonnet | — | Read, Write | subagent |

`[SOURCE: agents/*.md frontmatter, read 2026-08-20]`

### 2.1 Three divergences from the spec, each with a consequence

**(a) `chrome-devtools` is specified for three agents and granted to none.**
`06-agents.md` §8 lists `chrome-devtools` in the tools column for `rg-surface`, `rg-webtest` and
`rg-verify`. No shipped card contains the string `chrome`. The consequence lands hardest on
`rg-verify`, whose card instructs: *"XSS → headless browser; confirm the script actually executed
(DOM mutation or dialog)"* `[SOURCE: agents/rg-verify.md:19-20]`. That instruction has no
mechanism behind it. XBOW's non-LLM verification gate — a headless browser confirming execution —
is cited as prior art for RedGold's whole verification model
`[SOURCE: docs/REDGOLD-BRIEFING.md §19]`, and it is not installed.

**(b) `rg-verify` is instructed to write and has no write tool.**
Its card says *"write a blocker to `ledger/blockers.jsonl` and stop"* and *"write your output to
disk"*. Its grant is `Bash, WebFetch, Read`. RG-1 §7.3 already caught the *wrong* half of this —
an earlier research document claimed the agent "cannot write even if told to", and the audit
correctly overturned that, because **`Bash` is a write path**. The residual after that correction
is what matters here and is stated in RG-1 §7.3 itself: *"the actual defect is: no schema, no
mandated output path, and nothing that parses the unstructured output."* Neither
`findings/review.jsonl` nor `merge_review.py` exists. So the verification verdict has, today, **no
transport at all** — which is failure mode FM-4 from the prior-engagement autopsy, unfixed.

**(c) §8.7's Output Contract does not exist on any card.**
`06-agents.md` §8.7: *"every worker card carries an explicit Output Contract section specifying
the exact JSON it must return, and the `SubagentStop` hook validates it."* `grep -l "Output
Contract" agents/*.md` returns nothing. The `SubagentStop` hook (`validate_findings.py`) exists
and validates against `findings.py`'s schema — but no card tells any agent what that schema is,
with one partial exception (`rg-codeaudit`, which names exactly one field, `discovered_by`).

**This third divergence is the root of most of §6.** The validator enforces roughly two dozen
rules over a fifteen-field record shape that **no agent has ever been told to produce**.

### 2.2 The nesting constraint, and the one thing it actually rests on

`rg-lead` runs in the main session because subagents cannot spawn subagents and the failure is
silent `[SOURCE: docs/specs/redgold/06-agents.md §8.0]`. This is one of the design's better
decisions and it survives attack (see [proposed.md](proposed.md) §3). The mechanical backstop is
`no_nesting.py`, and §6 records that its wiring does not match its own vocabulary.

### 2.3 What the roster does not have

- **No `rg-setup`.** RG-2 §3.1 assigns seven duties to a control-tier setup agent, including
  running `rg-recon` *outside* containment. No such agent exists, and the plugin architecture
  provides no way to express "this agent runs on a different machine".
- **No `rg-scoping`.** RG-4's client-side skill. Not built.
- **No `rg-reconcile`.** RG-2 §5.6's gateway/guard log join. Not built, and has nothing to join
  against.

---

## 3. The engagement lifecycle, ordered

**Derived from the code, not from the spec's narrative.** `[INFERRED]` where a step's ordering is
implied by a file dependency rather than stated. This ordering is the x-axis of §4 and §5; a
control's position on it is what §6 checks.

| # | Point | What runs | Writes | Enforced ordering? |
|---|---|---|---|---|
| **L0** | Client scoping | *(nothing built)* | — | n/a |
| **L1** | Scaffold | `new_engagement.py` → `/rg:new` | `scope.yaml`, `.claude/settings.json`, empty `assets/*.jsonl`, empty `ledger/{gates,activity,cleanup,blockers}.jsonl`, `CLAUDE.md`, `status.md`, `session.md` | **Yes** — refuses if the authorization document is absent, if the boundary does not round-trip, or if the pinned interpreter lacks PyYAML |
| **L2** | Candidate discovery | `rg-recon` → `scope_cli.py add-candidate` | `assets/candidates.jsonl` row; `activity.jsonl:asset.candidate` | No. Nothing requires L2 before L3 |
| **L3** | Promotion | operator → `scope_cli.py promote --confirm` | moves row to `assets/register.jsonl` with `status: CONFIRMED`; `activity.jsonl:asset.promote` | **Yes** — two independent signal classes or `CLIENT_CONFIRMED`, inside the boundary, operator `--confirm` |
| **L4** | Plan | `rg-lead` → `gate_cli.py plan` | `ledger/plan.json`; `activity.jsonl:plan.write` | **Yes** — refuses an asset not CONFIRMED, refuses `--max-tier` above the scope ceiling |
| **L5** | **Gate 1 — approve** | operator → `gate_cli.py approve` | `gates.jsonl:gate.approve` with `plan_hash`, `scope_hash`, `environment` | **Yes** — refuses an undeclared/`unknown`/unrecognised `environment` |
| **L6** | Baseline (P10) | `baseline_scan.py` | `findings/baseline.json`, `evidence/F-NNN-*.http`, possibly `blockers.jsonl:ENVIRONMENT_DISCREPANCY` | **No.** Nothing requires L5 before L6, and `baseline_scan.py` never reads `gates.jsonl` |
| **L7** | Active testing | `rg-surface`, `rg-webtest`, `rg-codeaudit` (+ `rate_probe.sh` for bursts) | `findings/*.json`, `evidence/*`, `cleanup.jsonl`, `activity.jsonl:rate_probe.{plan,result}` | Per-call only: `scope_guard.py`, `no_handrolled_loops.py`, `canary_check.py` fire PreToolUse |
| **L7'** | Subagent stop | `validate_findings.py` (`SubagentStop`) | rewrites `status` on demotion; `blockers.jsonl:validation` after 2 attempts | **Yes**, exit 2 blocks the stop — but see §6 |
| **L8** | Verification | `rg-verify` | *(no mandated artifact — see §2.1b)* | No |
| **L9** | Phase completion | `gate_cli.py complete --phase` | `activity.jsonl:phase.complete` | **Yes** — `COVERAGE_EMPTY_PHASE` |
| **L10** | Report | `report.py` → `/rg:report` | `deliverables/report-tier<N>.md` | **Yes** — refuses if `scope.yaml` will not load |
| **L11** | Status regeneration | `regen_status.py` | `status.md` | Deterministic projection |
| **L12** | Close | `gate_cli.py close` | `gates.jsonl:gate.close` | **Yes** — `COVERAGE_EMPTY_PHASE`, `PHASE_NEVER_COMPLETED`, `REPORT_STALE`, `GATE_1_VOID` |
| **L13** | Harvest | `/rg:harvest` | framework `playbooks/` | Command only |

### 3.1 The ordering that is enforced, and the ordering that is convention

Only four transitions are mechanically enforced: **L3 before L4** (`cmd_plan` refuses an
unconfirmed asset), **L4 before L5** (`cmd_approve` refuses with no plan on disk), **L9 before
L12** (`PHASE_NEVER_COMPLETED`), and **L10 before L12** (`REPORT_STALE`).

Everything else is convention. In particular:

- **L5 does not gate L6 or L7.** `scope_guard.py`'s module docstring says so outright: *"§9.3.2
  plan checking (steps 9–13 …) is **not built**. This module enforces *scope*, not *the plan*."*
  So the Gate 1 approval that RG-1 §4.2 relies on to establish "no contact happens until after
  Gate 1" is **not enforced** — a fact that matters directly in §6, because two controls are sited
  on the assumption that it is.
- **L8 is entirely optional and produces nothing.** There is no artifact whose absence signals
  that verification did not run.

### 3.2 Where hooks fire on that lifecycle

Wired per-engagement by `new_engagement.py`, not by the plugin — plugin-shipped agents cannot set
`hooks` `[SOURCE: docs/wiki/claude-code/hooks.md §4]`.

| Event | Matcher **as written into settings.json** | Script | Lifecycle points |
|---|---|---|---|
| PreToolUse | `Bash\|WebFetch\|mcp__.*` | `scope_guard.py` | L2, L6, L7, L8 |
| PreToolUse | `Bash` | `no_handrolled_loops.py` | L7 |
| PreToolUse | `Bash\|WebFetch` | `canary_check.py` | L7 |
| PreToolUse | `Agent\|Task\|TaskOutput\|AskUserQuestion` | `no_nesting.py` | any subagent turn |
| PostToolUse | **(no matcher — see §6 D-14)** | `redact.py` | every tool call |
| SubagentStop | *(no matcher)* | `validate_findings.py` | L7' |

`[SOURCE: scripts/new_engagement.py:137-165]`. Note that `session_start.py` and `cleanup_gate.py`
appear in `07-enforcement.md` §9.1's table and are **not wired, because they do not exist** —
`new_engagement.py` deliberately skips a hook whose script is absent, which is correct and is why
the omission is silent.

---

## 4. The field-level producer/consumer map

**This did not exist before this page.** Read the "Producer" column first: a control reading a
field whose producer is *none* cannot fire, and a control reading a field whose producer runs
*later* than the control cannot fire either.

Legend: **P** = writes it · **M** = mutates it after another component wrote it · **R** = reads
it for a decision. Lifecycle points are §3's L-numbers.

### 4.1 `scope.yaml`

| Field | Producer | At | Mutated by | Read by (for a decision) |
|---|---|---|---|---|
| `engagement_id` | `new_engagement.py` | L1 | `scope_cli.amend` (rewrite) | test-data marker, report header, ledger rows |
| `authorization.window_start/end` | `new_engagement.py` | L1 | `scope_cli.amend` | `scope_guard.evaluate` (L2/L6/L7) |
| `authorization.emergency_contact` | `new_engagement.py` | L1 | — | `scope.parse` — **required for `redteam` only** |
| `mode` | `new_engagement.py` | L1 | — | `scope.parse` ceiling default; `report.render` |
| `ceiling` | `new_engagement.py` | L1 | — | `scope_guard.evaluate`; `gate_cli.cmd_plan`; `scope_guard.check_url` |
| `environment` | `new_engagement.py` (**required flag**) | L1 | `scope_cli.amend` (**silently, via round-trip**) | `gate_cli.cmd_approve` (L5); `baseline_scan.scan` (L6); `report.classify` (L10) |
| `in_scope[]` / `out_of_scope[]` | `new_engagement.py` | L1 | `scope_cli.amend` | `scope_guard`, `scope_cli.in_boundary`, `baseline_scan.in_boundary` |
| `constraints.testing_window` | `new_engagement.py` | L1 | — | `scope_guard.within_testing_window` |
| `constraints.max_requests_per_burst` | `new_engagement.py` (default 10) | L1 | — | `rate_probe.sh` |
| `crown_jewels[]` | `new_engagement.py` | L1 | — | **Nothing.** Round-tripped, printed nowhere, scored nowhere |
| `constraints.forbidden_actions[]` | `new_engagement.py` | L1 | — | **Nothing.** Parsed and validated; no consumer |
| `notify.before_active` | `new_engagement.py` (always `true`) | L1 | — | **Nothing** |
| `environment_established`, `environment_source` | **none** (RG-1 §3.1 requires both) | — | — | specced for `report.py`; unbuilt |
| per-asset `environment` | **none** (RG-1 §3.1) | — | — | specced for `scope_cli` promotion; unbuilt |
| `parity` block | **none** (RG-2 §8.3 requires it) | — | — | specced for `report.py`; unbuilt |
| `authority`, `platforms[]` | **none** (RG-4 D-3, "the smallest blocking item") | — | — | §15.1 requires three platform facts with nowhere to live |

### 4.2 `assets/register.jsonl` and `candidates.jsonl`

| Field | Producer | At | Read by |
|---|---|---|---|
| `asset_id` | `scope_cli` (`C-NNN` / `A-NNN`) | L2/L3 | `gate_cli.cmd_plan`; `scope_guard.load_asset_ids` (labelling only) |
| `identifier` (bare host) | `scope_cli.normalise_identifier` | L2 | `scope_guard.load_register` → the CONFIRMED set; `baseline_scan.confirmed_targets` |
| `port` | `scope_cli.normalise_identifier` | L2 | `baseline_scan.base_url`; **not** by `scope_guard.load_register` |
| `status` | `scope_cli.cmd_promote` | L3 | `scope_guard.evaluate` (tier ≥2 requires CONFIRMED); `baseline_scan`; `gate_cli.cmd_plan` |
| `attribution_signals[]` | `scope_cli.cmd_add_candidate` / `--client-confirmed` | L2/L3 | `promotion_verdict`; `report.render` (asset table) |
| `matched_boundary_entry` | `scope_cli` | L2/L3 | printed only |
| `reach`, `signup_open`, `reachable_population`, per-asset `env_signals` | **none** (RG-1 §3.2 says a CONFIRMED asset without these **fails promotion**) | — | the §4.7 scorer, which does not exist |

### 4.3 The findings record — the field that matters most is in the last block

Two producers exist. **`baseline_scan.py` is the only mechanical one.** "Agent" below means a
worker writing `findings/*.json` freehand, with no card telling it the schema (§2.1c).

**Fields with a mechanical producer:**

| Field | Producer | At | Mutated by | Read for a decision by |
|---|---|---|---|---|
| `id` | `baseline_scan` (`F-{index:03d}`, restarts at 1 per run) | L6 | — | `validate_record` (`ID_RE`), `validate_corpus` (`by_id`) |
| `asset` | `baseline_scan` | L6 | — | `report.render` grouping; `baseline_scan` signal join |
| `finding_class` | `baseline_scan` | L6 | — | cap column; `NA_NOT_PERMITTED`; `needs_verification` |
| `status` | `baseline_scan` (`PROVEN` iff `present`) | L6 | **`validate_findings.demote_records`** (→`SPECULATED`) | `PROVEN_UNVERIFIED`, `SPECULATED_ABOVE_LOW` |
| `verified` | `baseline_scan` (**`executed` iff `present`** — self-certified) | L6 | — | `PROVEN_UNVERIFIED`, `UNVERIFIED_ABOVE_LOW`, `report.classify` |
| `confidence` | `baseline_scan` | L6 | — | `report.classify` body/unverified split |
| `severity` | `baseline_scan` (constant on the `Check` tuple) | L6 | **`apply_environment_cap`** (L6 and again at L10) | everything |
| `evidence_ptr` | `baseline_scan` (writes the file too) | L6 | — | `resolve_evidence` → `EVIDENCE_UNRESOLVED` (demotes) |
| `result` | `baseline_scan` (`present`/`absent`/`not_applicable`) | L6 | — | `report.classify`, `regen_status`, `gate_cli.phase_evidence` — **three different rules, see §6 D-3** |
| `not_applicable_reason`, `checks_skipped` | `baseline_scan` | L6 | — | `regen_status.coverage_gap_size`, `report` unassessed/inapplicable split |
| `created` | `baseline_scan` | L6 | — | **`report.freshness_violation`** → `REPORT_STALE` at L10 and L12 |
| `discovered_by` | `baseline_scan` (`"baseline_scan"`) | L6 | — | `CODE_DEFECT_PRODUCERS` membership |
| `env_signals[]` | `baseline_scan.env_signals` — **2 of 4 blocking kinds** | L6, *after* the cap loop | — | `ENVIRONMENT_DISCREPANCY` |
| `environment_at_test` | **`apply_environment_cap`** | L6 and L10 | recomputed each call | `ENVIRONMENT_DISCREPANCY`; cap column |
| `production_nexus` | `apply_environment_cap` (`code_defect` default), else agent | L6/L10 | — | cap bypass; `PRODUCTION_NEXUS_*` |
| `severity_derivation` | `apply_environment_cap` | L6 and L10 | overwritten on every call | `DERIVATION_MISMATCH`; `gating_severity`; report disclosure sentence |
| `validator_note` | `validate_findings.demote_records` | L7' | — | nothing |

**Fields the validator reads that have no mechanical producer at all:**

| Field | Who is supposed to write it | Read by | Consequence |
|---|---|---|---|
| `verified_by` | `rg-verify` (RG-1 §4.5) | **nothing in the code** | `VERIFIED_BY_SELF` is specced and unbuilt; FM-3 unfixed |
| `real_world_impact` | agent | `NO_IMPACT` (non-blocking); report body | advisory only |
| `tested_at_tier` | agent (`baseline_scan` sets 1) | `NO_TIER` (non-blocking) | — |
| `gate_ref` | agent | **nothing** — `scope_guard` stamps `null` and says so | Gate 1 cannot be joined to any action |
| `phase` | **nobody** | `gate_cli.in_phase` | see §6 **D-2** |
| `created` on an agent-written record | agent, untold | `report.freshness_violation` | see §6 **D-1** — the highest-impact finding on this page |
| `precondition`, `grants`, `dominated_by`, `impact_demonstrated`, `cvss_v4_vector`, `attack_refs`, `routes_tested`, `credentials_tested`, `scope_of_conclusion` | agent, per RG-1 §3.3 | nothing (the scorer does not exist) | RG-1 §§4.3, 4.4, 4.7, 8.5 are entirely unbuilt |
| `obligation_refs`, `data_classes`, `notifiable_assessment` | Subsystem F | nothing | specced, all `[VERIFY]` |

### 4.4 Ledgers and side files

| File | Producer | Consumer | State |
|---|---|---|---|
| `ledger/plan.json` | `gate_cli.cmd_plan` | `canary_check.plan_preapproval`; `check_gate` hash | Built |
| `ledger/gates.jsonl` | `gate_cli` (approve/close/resolve), `scope_cli.amend` | `check_gate`, `close_violations`, `regen_status` | Built |
| `ledger/activity.jsonl` | `scope_guard.record_decision`, `scope_cli`, `gate_cli`, `rate_probe.sh` | `regen_status`, `completed_phases` | Built |
| `ledger/cleanup.jsonl` | **agents, by hand** | `canary_check.canary_proven` / `writes_already_made`; `report.render`; `regen_status` | Producer is an instruction in `agents/rg-webtest.md` |
| `ledger/blockers.jsonl` | `validate_findings`, `no_nesting`, `baseline_scan.raise_blocker` | `gate_cli.cmd_blockers/resolve`, `regen_status` | Built |
| `coverage.jsonl` | **none** | **`gate_cli.phase_evidence` reads it** | RG-1 §8.1 specced; no producer. See §6 **D-4** |
| `ledger/resolution.jsonl` | **none** (RG-2 §4 control tier) | `scope_guard.load_resolution` | Reader built ahead of writer, deliberately and honestly |
| `provision.json` | **none** (RG-2 §4) | `scope_guard._ruleset_hash` | Same |
| `findings/review.jsonl` | **none** | `merge_review.py`, which also does not exist | RG-1 E4 |
| `ledger/suppression.jsonl` | **none** | RG-1 §4.3 brake 4 | unbuilt |
| `assets/surface.jsonl` | **none** | RG-3 §5 | unbuilt |
| `ledger/sessions/` | **none** (`session_start.py` unbuilt) | — | directory created empty by `/rg:new` |

---

## 5. The control inventory, graded and sited

Every control in the repo, with the grade it honestly earns (§1.2), the lifecycle point it fires
at, and the fields it reads. **"Reads" is the column §6 walks.**

### 5.1 Controls that are built and can fire

| Control | Grade | Fires at | Reads |
|---|---|---|---|
| Boundary parse / fail-closed `ScopeError` | Boundary precondition | L1 and every load | `scope.yaml` bytes |
| `--auth-document` must exist on disk | Heuristic (an operator flag defeats it) | L1 | filesystem |
| Interpreter pinned + PyYAML proven | **Boundary precondition** | L1 | `subprocess` probe |
| Boundary round-trip before write | Defence-in-depth | L1 | parsed `Scope` |
| Promotion: 2 signal classes or `CLIENT_CONFIRMED` | Defence-in-depth | L3 | `attribution_signals[].class` |
| Promotion: no bare-IP signal value | Defence-in-depth | L3 | signal value |
| Promotion: inside boundary, `out_of_scope` wins | Defence-in-depth | L3 | `in_scope`/`out_of_scope`, host, port |
| Promotion: multi-service host must name a port | Defence-in-depth | L3 | candidate `port` |
| Plan: asset must be CONFIRMED | Defence-in-depth | L4 | `register.jsonl:status` |
| Plan: `max_tier ≤ ceiling` | Defence-in-depth | L4 | `scope.ceiling` |
| Plan: GraphQL write endpoint must name a mutation | Defence-in-depth | L4 | route string |
| `ENVIRONMENT_UNDECLARED` | Defence-in-depth | **L5** | `scope.environment` |
| `scope_guard`: out-of-scope host | **Heuristic** | L2/L6/L7/L8 | `tool_input`, `in_scope`, `out_of_scope` |
| `scope_guard`: port not authorised | Heuristic | same | parsed port, entry port |
| `scope_guard`: undeterminable target → deny | Heuristic (**the honest half**) | same | command string |
| `scope_guard`: tier > ceiling | Heuristic | same | command string, `ceiling` |
| `scope_guard`: outside authorization window | Defence-in-depth | same | `window_start/end`, clock |
| `scope_guard`: outside testing window | Defence-in-depth | same | `constraints.testing_window`, clock |
| `scope_guard`: CONFIRMED required above tier 1 | Defence-in-depth | same | `register.jsonl` |
| `scope_guard`: >8192-byte command → deny | Defence-in-depth (anti-timeout) | same | command length |
| `scope_guard`: total exception wrapper → deny | **Boundary precondition** | same | — |
| Decision logging → `activity.jsonl` | **Detection** | same | decision, `resolution.jsonl`, `provision.json` |
| `no_handrolled_loops` | Heuristic | L7 | command string |
| `canary_check`: write needs canary-deleted or plan pre-approval | Defence-in-depth | L7 | `cleanup.jsonl`, `plan.json` |
| `canary_check`: undeterminable GraphQL op → deny | Defence-in-depth | L7 | body/command |
| `canary_check`: budget counts dispatched, not logged | Defence-in-depth | L7 | `cleanup.jsonl:state` |
| `rate_probe.sh`: counts dispatches, caps at `scope.yaml`, requires `--gate-ref`, logs before firing | Defence-in-depth | L7 | `scope.yaml`, `check_gate` |
| `EVIDENCE_UNRESOLVED` / `EVIDENCE_NOT_CHECKABLE` → **demote** | Defence-in-depth (a transform, not a gate) | L7', L10 | `evidence_ptr`, filesystem |
| `PROVEN_UNVERIFIED`, `UNVERIFIED_ABOVE_LOW`, `NA_*` | Defence-in-depth | L7', L10 | `status`, `verified`, `gating_severity` |
| `PRODUCTION_NEXUS_UNRECOGNISED` / `_UNRESOLVED` | Defence-in-depth | L7', L10 | `production_nexus` |
| `CODE_DEFECT_CLEARED_WITHOUT_REASON` | Defence-in-depth | L7', L10 | `production_nexus`, `code_defect_cleared`, `discovered_by` |
| Environment cap (§6) | **Transform**, not a gate | L6, L10 | `severity`, `environment_at_test`, `finding_class`, `production_nexus` |
| `gating_severity` (pre-cap severity for gates) | Defence-in-depth | L7', L10 | `severity`, `severity_derivation.before_env_cap` |
| `report.classify` malformed-record exclusion | Defence-in-depth | L10 | all blocking codes |
| `COVERAGE_EMPTY_PHASE` | Defence-in-depth | **L9** and L12 | `findings/*.json:result`, `coverage.jsonl:outcome` |
| `REPORT_STALE` | Defence-in-depth | L10, **L12** | deliverable mtime, `created` on every record |
| `PHASE_NEVER_COMPLETED` | Defence-in-depth | L12 | `activity.jsonl:phase.complete` |
| `GATE_1_VOID` (`plan_hash`/`scope_hash` re-check) | Defence-in-depth | L12 | `gates.jsonl`, `plan.json`, `scope.yaml` |
| `validate_findings` two-attempt cap → blocker | Defence-in-depth | L7' | attempt counter |
| `verify_controls.py` — 60 injected faults | **Detection** (of a broken control, in CI) | dev-time | the suite |

### 5.2 Controls that are built and **cannot fire on current input** — see §6

`ENVIRONMENT_DISCREPANCY` at `SubagentStop` · `DERIVATION_MISMATCH` (both forms, on the report
path) · `code_defect` default at `SubagentStop` · `no_nesting` for 7 of its 12 tools ·
`redact.py`'s declared matcher · `in_phase` phase discrimination · the `coverage.jsonl` half of
`phase_evidence` · `resolution`/`ruleset_hash` fields in every activity row.

### 5.3 Controls that are specified and do not exist

`session_start.py` · `cleanup_gate.py` · Gate 2 automatic deviation detection · off-host egress
filtering (**the only layer graded BOUNDARY**) · `rg-reconcile` · §5.5's attribution-probe rate
limit and evidence discard · `merge_review.py` + `review.jsonl` · `VERIFIED_BY_SELF` ·
`IMPACT_NOT_EXECUTED` · the §4.7 scorer, §4.3 domination, §4.4 `REACH_UNENUMERATED`, §8.3 asset
coverage assertions, §8.5 scope-bounded negatives, §8.4 `chain_scan.py` · RG-1 §5's static
`grants` table and the `low` scanner ceiling · the `8 of 11` deny-list · RG-3's `profiles/` tree ·
RG-4's `rg4_ingest.py` and `rg-scoping` · Subsystem F in its entirety.
