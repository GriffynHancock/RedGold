---
title: RedGold architecture — index
wiki_id: architecture-index
question: Which of these two pages describes RedGold as it is, and which proposes changing it?
subject: RedGold architecture
status: partial
last_verified: 2026-08-20
verified_against: repo working tree at commit c0a20bd (2026-08-20); scripts/*.py, agents/*.md, docs/specs/**, docs/wiki/claude-code/hooks.md read directly in the session that produced these pages
recheck_trigger: before relying on the dataflow map (current.md §4) or the defect list (current.md §6) to plan work — both are derived from code that is under active change; re-derive after any commit touching scripts/findings.py, scripts/report.py, scripts/gate_cli.py or scripts/baseline_scan.py
sources:
  - url: docs/specs/redgold/README.md
    kind: primary
  - url: docs/specs/rg1-finding-integrity.md
    kind: primary
  - url: docs/specs/rg2-containment.md
    kind: primary
related:
  - architecture-current
  - architecture-proposed
  - claude-code-hooks
---

# RedGold architecture

Two pages. **They are not the same kind of document and must never be read as one.**

| Page | Kind | What it is |
|---|---|---|
| [current.md](current.md) — `architecture-current` | **Descriptive** | RedGold as it actually stands on 2026-08-20, assembled in one place for the first time. Every claim is sourced to a file in this repo. Where the code and a spec disagree, the code wins and the disagreement is recorded. **Nothing in it is a proposal.** |
| [proposed.md](proposed.md) — `architecture-proposed` | **A proposal. Not adopted. Not decided.** | An adversarial rearrangement, written under the standard *assume every decision is wrong until proven otherwise mechanically, by strict logic, or by a high-authority primary source.* Nothing in it describes RedGold. Nothing in it has been agreed. |

If you are trying to find out what RedGold does, read `current.md` and stop. If you are trying to
decide what to build next, read `current.md` first and then `proposed.md`, and treat every
proposal in the second as an argument to be checked, not a plan to be executed.

## Why these pages exist

Nearly all of RedGold's design was written on 2026-08-20 by roughly thirty agents, each specced
against its own evidence, none reading the others' output `[SOURCE: operator brief, 2026-08-20]`.
The individual documents are unusually rigorous. **Nobody had checked whether the pieces compose.**

Six defects of one shape were found that day, independently, by six different agents. The shape:

> **A control must read only fields that are already written when it runs, and must not read a
> field that something between production and the check overwrites.**

Violations present as a gate that fires on 100% of input, a gate that fires on 0%, or a default
that is inert. The 0% case is the dangerous one, because it reads as coverage. The diagnosis is
that RedGold has **no dataflow contract**: specs state what must be checked; nothing records which
component writes each field, at which lifecycle point, who reads it, and who mutates it in
between. `current.md` §3–§4 is that contract, written for the first time; §6 is the mechanical
walk of it, which found **eleven further instances beyond the six already known**.

## Standing caveats on both pages

- Where either page relies on a conclusion from another document in this repo, that conclusion is
  **one agent's analysis and has not itself been audited**. Several such conclusions were
  overturned on 2026-08-20, including a prescribed defect fix that was wrong
  `[SOURCE: docs/research/session-audit-2026-08-20.md; docs/specs/rg1-finding-integrity.md §7.3]`.
- Claims about Claude Code harness behaviour derive from [claude-code/hooks.md](../claude-code/hooks.md),
  whose own `status` is `partial` and whose sourcing caveat applies transitively.
- `[VERIFY]` in either page means exactly what it means everywhere else in this repo: unconfirmed,
  must not reach a client or a design decision without checking first.
