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

---

## 6. The mechanical walk

**The invariant:** *a control must read only fields that are already written when it runs, and
must not read a field that something between production and the check overwrites.*

Six violations were already known on 2026-08-20 and are recorded elsewhere. Walking §4's map
against §5's "reads" column found **nineteen**, of which **thirteen are new**. Each is stated as
*what it reads → why it cannot work → what it costs.*

Ordered by consequence, not by discovery.

### D-1 — `REPORT_STALE` fires on 100% of any engagement with an agent-written finding

*Reads:* `created`, on **every** record in `findings/*.json`.
*Why it fails:* `report.freshness_violation` refuses outright when any record's `created` cannot
be parsed — *"An unreadable timestamp is not evidence that the report is current."* That fail-closed
direction is correct. But **`created` has no producer except `baseline_scan.py`**, and no agent
card mentions the field (§2.1c). So the first freehand finding an agent writes without a `created`
stamp makes `report.py --check` and `/rg:close` refuse permanently, with a message that does not
say which record is at fault.
*Cost:* the disabled-gate failure in its purest form. `gate_cli.close_violations` returns *every*
reason at once precisely so an operator does not learn to distrust the gate — and this defect
guarantees they will, on the first real engagement. It is also the exact inverse of RG-1 §4.8's
test: **name a healthy engagement state at which this fires.** Every one of them.
*Status:* **new.**

### D-2 — phase discrimination in `COVERAGE_EMPTY_PHASE` is inert

*Reads:* `phase` on findings records and on `coverage.jsonl` rows, via `gate_cli.in_phase`.
*Why it fails:* **nothing anywhere writes `phase` onto a finding.** `grep` finds the key only in
`gate_cli`'s own `activity.jsonl` row and in tests. `in_phase` deliberately treats an untagged
record as counting toward whichever phase is being closed — a reasonable degradation rule in
isolation — so with *no* producer, **every phase is satisfied by any finding anywhere in the
engagement.**
*Cost:* `complete --phase recon` with real findings, then `complete --phase webtest`,
`--phase codeaudit`, `--phase verify` with zero work each, all pass. `PHASE_NEVER_COMPLETED` at
close requires only *one* `phase.complete` row. So the mechanism RG-1 §8.2 calls *"the single most
important thing in this section"* — the thing that would have stopped ENGAGEMENT-B existing
quietly — degrades to a single engagement-wide check that one baseline scan satisfies.
*Status:* **new.**

### D-3 — `not_attempted` is understood by one reader of three

*Reads:* `result` on a findings record.
*Why it fails:* `gate_cli.NOT_A_FINDING_RESULTS` was corrected on 2026-08-20 to
`{"not_applicable", "not_attempted"}` (adversarial review S4). **The correction was not carried to
the other two readers.** `regen_status.render` uses `non_findings = {"absent", "not_applicable"}`;
`report.classify` buckets only `absent` and `not_applicable`.
*Cost:* a record meaning *"we did not look"* is counted as a finding in `status.md` — the file
CLAUDE.md calls authoritative and the operator reads at every session start — and in
`report.classify` it falls through to the ordinary path, where it can be validated, severity-capped
and **printed to the client as a finding or an open question.** This is defect S8's exact shape
(two readers, opposite rules, one corpus) recurring in a third place, one round after S8 was fixed
by consolidating two readers.
*Status:* **new.**

### D-4 — the `coverage.jsonl` half of `phase_evidence` has no producer

*Reads:* `coverage.jsonl` rows with `outcome: absent`.
*Why it fails:* RG-1 §8.1 specifies the coverage register; §9.3 lists it as Release 3; nothing
writes it. `gate_cli.phase_evidence` reads it anyway (correctly — the reader before the writer is
a deliberate pattern here).
*Cost:* bounded and honest today, because the `findings/*.json` half does fire. Recorded because
it means `COVERAGE_EMPTY_PHASE` is satisfied only by a findings record, so *"record what was
checked — … or an `absent` row in `coverage.jsonl`"* names a remedy the operator cannot perform.
A refusal message that offers an impossible fix is how a gate loses credibility.
*Status:* **new** (as a composition observation; the unbuilt register is known).

### D-5 — `ENVIRONMENT_DISCREPANCY` fires on 0% at `SubagentStop`

*Reads:* `env_signals` **and** `environment_at_test == "production"`.
*Why it fails:* `environment_at_test` is written by `findings.apply_environment_cap`. On the
report path `report.classify` calls the cap over the whole corpus first, so the field exists. **On
the `SubagentStop` path it never runs** — `validate_findings.run` → `validate_file` →
`validate_record`, with no cap anywhere. The field is absent, the string comparison against
`"production"` fails, and the check is silent.
*Cost:* the check is live only at report assembly, which is the last possible moment — after the
agent that could have re-examined the asset has stopped. RG-1 §4.2 states the check runs at *"finding
creation … and report assembly"*; the finding-creation half works for `baseline_scan` (which calls
the cap itself) and is dead for every agent-written record.
*Status:* **new.** This is the same defect class as the known `ENVIRONMENT_DISCREPANCY`-at-Gate-1
error, one lifecycle point later, and it survived the fix for it.

### D-6 — the `code_defect` default never applies at `SubagentStop` either

*Reads:* `discovered_by == "rg-codeaudit"`.
*Why it fails:* same mechanism as D-5 — the default is stamped inside `apply_environment_cap`.
`rg-codeaudit` writes a finding, the hook validates it, and at that moment the record has no
`production_nexus`. It acquires one only if and when `report.classify` runs.
*Cost:* bounded, because the report path is the one that matters for the cap. But
`CODE_DEFECT_CLEARED_WITHOUT_REASON` — the ceremony that stops a four-character
`"production_nexus": null` taking a critical to a medium — reads `"production_nexus" in record`,
so at the hook it also cannot distinguish "cleared" from "never set". The S6 fix is one path short.
*Status:* **new.**

### D-7 — `DERIVATION_MISMATCH` has two forms and each is dead on one of the two paths

*Reads:* form (a) `severity != severity_derivation.after_env_cap`; form (b)
`severity_derivation.derivation_conflict`.
*Why it fails:* form (a) cannot fire in `report.classify`, and the code says so in a comment —
the cap runs first, so the comparison is equal by construction. Form (b) was added for exactly
that reason. But form (b)'s input is stamped **by the cap**, so on the `SubagentStop` path — where
the cap never runs — **form (b) cannot fire either**. Each path is covered by one form and blind
to the other.
*Cost:* a hand-edited `severity` **below** a record's own recorded `after_env_cap` — the
flattering direction, which is the whole point of the control — is caught at report assembly and
not at the hook. Partial coverage presented as full.
*Status:* **new.** The S1 fix is correct as far as it goes; this is its untested other half.

### D-8 — `no_nesting.py` guards 4 of the 12 tools it knows about

*Reads:* the PreToolUse matcher, before the script is ever invoked.
*Why it fails:* `NESTING_TOOLS` is `{Agent, Task, TaskOutput, TaskCreate, TaskUpdate, TaskList,
TaskGet, TaskStop, SendMessage, AskUserQuestion, ExitPlanMode, EnterPlanMode}`. The matcher
`new_engagement.py` writes is `Agent|Task|TaskOutput|AskUserQuestion`. Per the harness's documented
matcher rules, a pattern of letters/digits/`_`/`-`/spaces/`,`/`|` is an **exact alternation
match**, not a prefix `[SOURCE: docs/wiki/claude-code/hooks.md §5]` — so `TaskCreate`,
`TaskUpdate`, `TaskList`, `TaskGet`, `TaskStop`, `SendMessage`, `ExitPlanMode` and `EnterPlanMode`
never invoke the hook.
*Cost:* `SendMessage` is called out in the script's own comment as *"a real tool in this harness"*
that a hardcoded list had previously missed. The list was fixed; the wiring was not. Eight of
twelve nesting paths are unguarded, and the failure mode the control exists for — *"a pipeline
that reports success while doing nothing"* — is silent.
*Status:* **new.**

### D-9 — `redact.py` may be entirely inert `[VERIFY]`

*Reads:* `payload["tool_response"]`; emits
`hookSpecificOutput.updatedToolOutput`.
*Two independent problems.* First, `new_engagement.settings_json` attaches a `matcher` **only when
`event == "PreToolUse"`**, so `redact.py`'s declared `Bash|WebFetch|Read|mcp__.*` matcher is
discarded and it runs on every tool call. That is over-firing, which is survivable.
Second, and seriously: **`updatedToolOutput` does not appear in the documented hook JSON output
schema.** The schema this repo recorded from primary sources lists `hookSpecificOutput.updatedInput`
and nothing for modifying tool *output* `[SOURCE: docs/wiki/claude-code/hooks.md §3]`.
`tests/test_redact.py` asserts that the *script emits the field*; nothing asserts the *harness
honours it*.
*Cost:* if the field is not honoured, "Credential redaction" — listed in `status.md`'s **Built and
enforced** table — removes nothing from the transcript, and the only thing that reaches the model
is the `additionalContext` note saying credentials were removed. A control that reports having
acted while doing nothing is worse than an absent one.
*Status:* **new. `[VERIFY]` before anything is done about it** — a five-minute test settles it: run
a session with the hook wired, return a fake `sk_test_` in tool output, and read the transcript
file. Do not rewrite the script on the strength of this page.

### D-10 — `UNVERIFIED_ABOVE_LOW` is structurally unreachable from the only mechanical producer

*Reads:* `verified` ∈ {`replayed`, `executed`}.
*Why it fails:* `baseline_scan.make_finding` writes `"verified": "executed"` on any check whose
predicate returned true. The scanner attests its own independent verification.
*Cost:* P2 — *"a finding is not a finding until something other than the model verified it"* — is
satisfied by the producer's own claim. RG-1 §4.5 names this exactly (*"the rule is satisfied by the
exact thing it exists to catch"*), prescribes the fix (`VERIFIED_BY_SELF` + stop writing
`executed`), and marks it **E3, not landed**. It is recorded here because a reader of the control
inventory would otherwise count `UNVERIFIED_ABOVE_LOW` as covering the baseline.
*Status:* **known** (RG-1 §9.2 states E3 did not land), but not reflected in `status.md`.

### D-11 — three baseline checks fire on `status == 200` and land in the client body

*Reads:* `probe.status`.
*Why it fails:* `_admin_reachable` is `return probe.status == 200`, used by `admin_open`
(**critical**), `ghost_admin_open` (high) and `actuator_open` (high). Combined with D-10 the record
is written `status: PROVEN`, `verified: executed`, `confidence: confirmed`, with a resolving
evidence pointer — which passes **every** gate in `findings.validate_record` and every branch of
`report.classify`, straight into **What we found**.
*Cost:* against a single-page application that serves `200` for unknown paths — the modal
deployment shape for this exact client segment (Vercel/Netlify SPA) — this fabricates a critical
and two highs per asset. It is the Wavestone failure (*"fabricated a critical … with a
proof-of-exploit that did not work"*) reproduced by the deterministic component that exists to
prevent it. RG-1 §5.3 specifies the fix (`grant_evidence: status_only`, enforced by an assertion
over `CHECKS` at import time); it is unbuilt.
*Status:* **known as FM-2**, but its composition with D-10 — that the two together produce a
client-facing critical with nothing in the pipeline able to stop it — is **new**.

### D-12 — `scope_cli.py amend` silently destroys every key `scope.py` does not model

*Reads/writes:* `cmd_amend` does `document = boundary.to_dict()`, mutates, re-parses, and writes
`amended.dumps()` over `scope.yaml`.
*Why it fails:* `Scope.to_dict()` emits exactly the modelled fields. Any other key — a comment, a
future `parity` block (RG-2 §8.3), `authority`/`platforms` (RG-4 D-3), `environment_established`,
`environment_source`, per-asset `environment` — is present in the parsed document and absent from
the output.
*Cost:* today it destroys operator comments. The moment any of the four specced blocks lands
without a matching `to_dict()` entry, the first amendment deletes a client's signed attestation of
dev/prod divergence, and `scope_hash` changes so the deletion looks like a legitimate amendment.
`new_engagement.py`'s round-trip assertion has the same blind spot, and RG-1 §9.2's E1 row already
flags it in passing (*"silently drops any field missing from `to_dict()`"*) without generalising it
to `amend`.
*Status:* **new** for `amend`.

### D-13 — there is no finding-id allocator

*Reads:* `id`, in `ID_RE`, in `validate_corpus`'s `by_id` map, and in `REFERENCE_ID_RE`.
*Why it fails:* `baseline_scan.scan` numbers from `start_index=1` and `main()` never passes
anything else. Agents writing `findings/webtest.json` have no allocator and no instruction.
`regen_status.all_findings` concatenates every `findings/*.json`.
*Cost:* three compounding failures on collision. `validate_corpus` builds `by_id` by
last-write-wins, so one of two `F-001`s vanishes from corpus-level checks. `REFERENCE_ID_RE`
scanning free text then matches the *other* record's id and raises a spurious `ROLLUP`, which
`report.classify` uses to move a real finding into `rollup_constituents` — **dropping it from the
client's document**. And a second baseline run over a changed register renumbers everything, so
evidence filenames and `dominated_by`/rollup references silently re-point.
*Status:* **new.**

### D-14 — `gate_ref` is null in every activity row, so no action joins to an approval

*Reads:* `activity.jsonl:gate_ref`.
*Why it fails:* `scope_guard.build_activity_row` stamps `"gate_ref": None` and documents why —
*"The hook payload carries no gate reference and the guard does not read `gates.jsonl`."* That is
honest. The consequence is not recorded anywhere.
*Cost:* Gate 1's `plan_hash`/`scope_hash` staleness rule is enforced in exactly two places —
`rate_probe.sh` (which passes `--gate-ref`) and `gate_cli.close`. **Every other network action in
the engagement is unattributable to any approval**, so `/rg:gate approve` is a record of intent
rather than a gate on action, and RG-2 §5.5's reconciliation table cannot distinguish "approved
traffic" from "traffic".
*Status:* **new** as a stated consequence.

### D-15 — `findings.py` gives a reason for a residual that the harness documentation contradicts

*Reads:* the `SubagentStop` payload.
*Why it matters:* `findings.py`'s `CODE_DEFECT_PRODUCERS` comment says the mechanical alternative —
stamping `discovered_by` from the subagent type in the hook — *"is not available: the hook payload
carries `agent_id` and `session_id`, neither of which names the agent type."* The wiki page
recorded from primary sources the same day says the common stdin fields include **`agent_type`**,
present on subagent-scoped events, of which `SubagentStop` is one
`[SOURCE: docs/wiki/claude-code/hooks.md §2]`.
*Cost:* if the wiki is right, S6's residual — *"the producer is a sentence in an agent card, not a
mechanism"*, called out in `status.md` as one of two standing caveats — is closable with a few
lines, and has been left open on a false premise. **`[VERIFY]`: the wiki page's own sourcing caveat
applies, and this specific row is exactly the kind it says to re-fetch before relying on.** Two
documents written the same day contradict each other on a load-bearing fact; neither has been
checked against a running hook.
*Status:* **new.**

### D-16 — `crown_jewels` and `forbidden_actions` are validated and read by nothing

*Reads:* nothing.
*Why it matters:* both are parsed, type-checked, round-tripped and serialised. `crown_jewels` is
Gate 0's headline output (*"Operator + Lead agree scope, crown jewels, ceiling"*) and is a `+1`
modifier in RG-1 §4.7's scorer, which does not exist. `forbidden_actions` is a client's explicit
"leave this alone" list with no enforcement path at all.
*Cost:* a client-facing promise with no mechanism. This is CLAUDE.md design judgement 4 —
*a control nobody is forced to run is not a control* — in the degenerate case where nobody can run
it.
*Status:* **new.**

### D-17 — RG-1 §4.2's siting argument rests on an ordering nothing enforces

*Reads:* the assumption that *"no contact happens until after Gate 1 has approved the plan
(§9.7)"*.
*Why it matters:* that sentence is the load-bearing justification for moving
`ENVIRONMENT_DISCREPANCY` off Gate 1 — and it is the justification for `ENVIRONMENT_UNDECLARED`
being sufficient at Gate 1. **Nothing enforces it.** `scope_guard.py` states it does not implement
plan checking; `baseline_scan.py` never reads `gates.jsonl`; an agent may probe a CONFIRMED
in-scope host at tier 1 with no plan and no approval in existence.
*Cost:* the reasoning is still *correct* — a discrepancy check at Gate 1 would fire on 0% because
signals need contact — but the argument is right for the wrong reason. The real reason is that
signals are written by producers that run later, not that the lifecycle forbids earlier contact.
More consequentially: `environment` can be declared, approved at Gate 1, then amended, and
`scope_cli.amend` prints a warning while nothing re-checks it until `close`.
*Status:* **new.**

### D-18 — `finding_class: compliance` is routed through the exploit column of the environment cap

*Reads:* `findings.cap_column(finding_class)` and `NO_EXPLOIT_CLASSES`.
*Why it fails:* `compliance` is already a member of `FINDING_CLASSES`. `NO_EXPLOIT_CLASSES` is
`{posture, governance}`. `cap_column` returns `"technical"` for anything outside that set, so a
compliance finding is scored against the **exploit** column: capped at `high` on staging,
`medium` on development, `low` on ephemeral-preview. **An obligation gap does not become less
severe because it was observed on a dev box** — the cap's entire justification (*"a statement about
where we looked"*) does not apply to a claim about a legal obligation.
Second half: `validate_record` raises blocking `NA_NOT_PERMITTED` whenever `verified == "n/a"` and
the class is outside `NO_EXPLOIT_CLASSES`. A compliance gap has no exploit to replay, so
`verified: "n/a"` is its only honest value — and it is refused. **Every compliance finding is
currently unrepresentable.**
*Cost:* Subsystem F is specced, not built, so nothing is broken today. It is recorded here because
the vocabulary shipped ahead of the machinery and a reader of `FINDING_CLASSES` would reasonably
assume the class works.
*Status:* **new.**

### D-19 — `report.py` claims to strip `[VERIFY]` content and contains no such check

*Reads:* nothing.
*Why it fails:* `report.py`'s module docstring lists, among the things the report refuses to do:
*"`[VERIFY]`-marked content never reaches a client."* `grep -n VERIFY scripts/report.py` matches
only that sentence. `agents/rg-report.md` repeats the rule as an instruction. There is no filter in
`render`, no filter in `classify`, and no validator code for it.
*Cost:* hard rule 1 — *nothing marked `[VERIFY]` reaches a client or a marketing claim* — is
enforced by an agent instruction and a docstring. RG-1 §11.2 additionally specifies a **literal
deny-list** for the `8 of 11` scoreboard with its own injected fault; that is unbuilt too. Both are
one-function controls guarding the repo's most consequential hard rule.
*Status:* **new.**

### 6.1 Two smaller items, recorded without a number

- **`env_signals` are attached after the cap loop** in `baseline_scan.scan`, so
  `apply_environment_cap` never sees them. Harmless today (the cap does not read them) and fragile
  the moment it does.
- **`scope_guard.load_register` folds the CONFIRMED set to bare hostnames**, discarding `port`,
  while `scope_cli` treats `(host, port)` as asset identity. A CONFIRMED asset on one port
  therefore satisfies the CONFIRMED test for every port on that host. Mitigated — not closed — by
  the separate port-authorisation check against `in_scope`.

### 6.2 What the walk says about the six already known

Five of the six were fixed by moving a control or by adding a producer. **None of the fixes
generalised**: `COVERAGE_EMPTY_PHASE` moved from `cmd_approve` to `cmd_complete` and nobody asked
whether its *other* input (`phase`) had a producer — D-2. `ENVIRONMENT_DISCREPANCY` moved off Gate
1 and nobody asked whether its input existed on the *other* path it now runs on — D-5.
`DERIVATION_MISMATCH` gained a second form for the report path and nobody asked whether that form
worked on the hook path — D-7. The `not_attempted` fix landed in one of three readers — D-3.

**The pattern is that each fix was verified against the path that produced the bug report, and
against no other path.** That is what a dataflow contract is for, and its absence is the finding
underneath all seventeen.

---

## 7. Built / specced / neither

Modelled on `status.md`'s "NOT enforced" section, which is the honesty standard in this repo.

**Built and can fire:** everything in §5.1. 605 tests, 60/60 injected faults
`[SOURCE: status.md, measured 2026-08-20]`. Read `status.md`'s own caveat with it: *a passing suite
is not assurance*, and fault injection uses coarse mutations that a wrongly-sited control survives.
**Every defect in §6 is invisible to all 60 faults**, because a mutation to a control that cannot
fire changes no test outcome.

**Built and inert:** §5.2 — eight controls, described in `status.md` or a spec as working. Two
further controls (D-19) are described in a docstring and an agent card and were never written at
all.

**Specced, not built:** §5.3. The largest items by consequence:

1. **Off-host egress filtering.** The only layer RedGold's own grading calls a **boundary**.
2. **The RG-1 severity model** — `precondition`, `grants`, domination, the §4.7 scorer, the
   reviewer merge. RG-1's index reads as a built system; §9.2 records that E3, E4 and E5 did not
   land, and Release 3 has not started. `severity_derivation` in the code carries three keys; the
   spec's example carries eleven, and the spec's own `DERIVATION_MISMATCH` is defined against
   `after_review`, a key nothing writes.
3. **The coverage register** (`coverage.jsonl`), which two shipped controls already read.
4. **`rg-setup`, `rg-scoping`, `rg4_ingest.py`** — parts 0 and 2 of the four-part architecture.
5. **RG-3's `profiles/` tree.** RedGold today has one scanner: a nine-check hand-written checklist.

**Neither specced nor built — named because their absence is load-bearing:**

- Anything that tells an agent the findings schema (§2.1c). Every RG-1 rule presumes it.
- Any allocator for finding ids (D-13).
- Any mechanism placing an agent on a different trust tier, which RG-2 §3.1 requires for
  `rg-recon`.
- Any consumer for `crown_jewels` or `forbidden_actions` (D-16).
- Subsystem F: all content `[VERIFY]`, research outstanding.

---

## 8. Where the composition does not cohere

Six structural incoherences, distinct from the field-level defects in §6.

**8.1 The verification chain has no closing link.** P2 requires something other than the model to
verify a finding. `rg-verify` re-executes; but it has no `Write` tool, no mandated output path, no
schema, no parser, no `chrome-devtools`, and there is no field-level route from its verdict back
to the record — `verified_by` has no producer and `merge_review.py` does not exist. Meanwhile the
one mechanical producer self-certifies (D-10). **The whole `verified` axis is, today, written only
by the party it constrains.**

**8.2 RG-2's three-tier split and the plugin architecture are incompatible as written.** RG-2 §3.1
promotes to a rule that `rg-recon` runs on the control tier, outside containment. `rg-recon` ships
as a plugin subagent that runs in the same session, on the same machine, under the same hooks as
`rg-webtest`. There is no expressible way to place a subagent on a different host, and RG-2 does
not name one.

**8.3 RG-1 assumes a lifecycle RG-1 does not enforce.** See D-17. Two of RG-1's control-siting
decisions are justified by §9.7's ordering; §9.7 is prose.

**8.4 RG-2 (containment) and RG-2 (rate control) are two documents under one name, and they
disagree about what the boundary buys.** `rg2-containment.md` §10.1 item 3 states plainly that the
firewall does nothing about harm at a permitted destination. `rg2-rate-control.md` §1 takes that as
its premise and concludes the control belongs in a wrapper (`scan_run.py`) that does not exist.
Neither is built, and the shared "RG-2" label invites a reader to think one covers the other.

**8.5 RG-3's premise contradicts the state of RG-1.** RG-3 inherits RG-1's `low` scanner ceiling
"unconditionally", and derives it from `VERIFIED_BY_SELF` — which is **unbuilt** (D-10). So the
ceiling RG-3 treats as already enforced is enforced by nothing, and RG-3's §4 argument that a
per-template `grants` table is unnecessary rests on it.

**8.6 The three-file contract has a fourth file nobody generates.** `CLAUDE.md` / `status.md` /
`session.md` is the stated contract, with `status.md` generated by `regen_status.py`. `session.md`
is specified as append-only with a HANDOFF block *"injected by `session_start.py`"* — which does
not exist, so `session.md` is hand-maintained, which is the exact property `regen_status.py` was
built to eliminate for its sibling.

### 8.7 One thing that composes better than it looks

The **fail-closed direction rule** — *"'fail closed' names a direction, not a value, and the
direction is always the one that does not reduce what the client is told"* (RG-1 §3.4) — is
implemented consistently across five independent components written by different agents:
`scope.effective_environment` → `production`, `findings.resolve_environment` → `production`,
`report.needs_verification` on an unknown severity → `True`, `report.freshness_violation` on an
unreadable timestamp → refuse, `regen_status.INAPPLICABLE_REASONS` allow-listing the *non-gap*
side, `canary_check.NEVER_DISPATCHED_STATES` allow-listing the *exonerated* side. Each was
arrived at separately and none of them points the wrong way. That is the strongest evidence in the
repo that the principles are doing real work rather than decorating it.
