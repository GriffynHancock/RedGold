---
description: Present a phase plan for operator approval, or resolve a recorded deviation blocker. Operator-initiated only.
argument-hint: [plan | blockers | resolve <id>]
disable-model-invocation: true
---

# /rg:gate — approval decisions

**STATUS: NOT IMPLEMENTED (v0.1.0 skeleton). Build order steps 3–4.**

Do not simulate this command. Do not approve a plan conversationally, do not clear a blocker by
saying it is cleared, and never record an approval the operator did not give. Tell the operator
this command is not built yet and stop.

An audit of this framework already caught one gate that was prose with no enforcing code path.
A stub that behaves like a gate reproduces that exact anti-pattern.

## What it will do (spec §9.7)

- `plan` — present the machine-readable phase plan emitted by `rg-lead` for **Gate 1** approval.
  Gate 1 pre-authorizes *classes of test* against *named endpoints*. A worker escalating within
  what the plan already covers proceeds without prompting.
- `blockers` — list **Gate 2** deviations: a worker that reached a test class or an endpoint the
  plan does not name records a blocker to `ledger/blockers.jsonl` and halts.
- `resolve` — record the operator's decision on a blocker, written to `ledger/gates.jsonl`.

Every decision is appended to the ledger with its authorizing clause, so the final report can state
exactly when testing escalated and under whose approval.

## Acceptance test

Covered by step 3 (`scope_guard.py` denials) and step 4 (hooks fire and deny end-to-end).
