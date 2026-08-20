---
description: Close the engagement. Refuses on a stale deliverable, an engagement with no record of having looked, or no completed phase. Operator-initiated only.
argument-hint: [--tier N]
disable-model-invocation: true
---

# /rg:close — the engagement close gate

Backed by `scripts/gate_cli.py close`. Do not simulate this command: do not declare an engagement
closed conversationally, and never write a `gate.close` row the command refused to write. The
absence of that row is the only evidence on disk that an engagement was abandoned rather than
finished.

```
scripts/gate_cli.py close --root ENGAGEMENT_DIR [--tier 1]
```

## Why this exists

RG-1 Release 1 shipped two coverage rules and **both were opt-in**. `report.py --check` catches a
deliverable that predates its own findings; `gate_cli.py complete --phase` catches a phase closed
with no record of having looked. An operator who ran neither was stopped by nothing, and under P1
— *enforcement is mechanical, never advisory* — a control that depends on someone remembering is
not a control.

The specced remedy was hook 7, `cleanup_gate.py`, a `Stop` hook (`07-enforcement.md` §9.2). **It
does not work.** `Stop` fires once per *turn*, many times per engagement, so a refusal keyed on an
empty corpus would fire on every turn of a healthy engagement's opening phase — a gate that fires
on healthy input is a gate that gets switched off. And exit 2 on `Stop` continues the conversation:
its actuator is the model, which cannot restore a downed component, re-scope a phase, or accept a
coverage gap with a recorded decision. Those are the operator's. `SessionEnd` fires at the right
cardinality but cannot block at all.

**There is no Claude Code lifecycle event for "engagement close", because an engagement is not an
object the harness knows about.** Every hook event is turn-, tool-, session- or subagent-scoped. So
closure is an act with a gate on it rather than an absence nobody records.

## What it refuses

| Code | Fires when | Fix |
|---|---|---|
| `COVERAGE_EMPTY_PHASE` | The engagement has zero findings **and** zero recorded negative results across every phase | Record what was checked — an `absent` finding record per clean check, or an `absent` row in `coverage.jsonl` |
| `PHASE_NEVER_COMPLETED` | No `phase.complete` row exists in `ledger/activity.jsonl` | `gate_cli.py complete --phase <name>` for each phase worked. This is what makes the zero-zero rule bind |
| `REPORT_STALE` | `deliverables/report-tierN.md` is missing, or its mtime predates the newest `created` stamp in `findings/*.json`, or a record's stamp cannot be read | Re-run `/rg:report` |

Every failing check is named at once, not one per run. An operator who fixes one refusal and is
immediately refused for a different reason learns to distrust the gate.

On success it appends a `gate.close` row to `ledger/gates.jsonl` with a generated id, the list of
completed phases, and a timestamp.

## What it does NOT do — do not describe this as enforced

An operator who walks away without running `/rg:close` is **still stopped by nothing**. This
command narrows the failure from *"forgot one of several checks"* to *"skipped the documented close
step"*, and makes that skip detectable after the fact. It does not eliminate it.

It also does **not** check cleanup debt. `cleanup_gate.py` (outstanding `pending`/`orphaned` rows
in `ledger/cleanup.jsonl`, §9.2) remains unbuilt, and cleanup debt is agent-actionable in a way
coverage is not — it belongs in its own control, not in this one.
