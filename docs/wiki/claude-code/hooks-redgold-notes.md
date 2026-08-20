---
title: RedGold-specific Claude Code hook facts
wiki_id: redgold-hooks-facts
question: Given the general hooks reference, what does that mean for RedGold's own enforcement design — specifically engagement close and the Stop hook?
subject: Claude Code / RedGold
status: verified
last_verified: 2026-08-20
verified_against: docs/specs/rg1-finding-integrity.md §9.1a, as committed 2026-08-20
recheck_trigger: if rg1-finding-integrity.md §9.1a is revised, or if the Claude Code hook event list changes (see claude-code-hooks.md)
sources:
  - url: docs/specs/rg1-finding-integrity.md
    kind: primary
related:
  - claude-code-hooks
---

# RedGold-specific Claude Code hook facts

This page records two conclusions established in `docs/specs/rg1-finding-integrity.md` §9.1a — not
general Claude Code facts, but what those facts imply for RedGold's own design. Read
`claude-code/hooks.md` first for the underlying event semantics.

## 1. No hook event corresponds to "engagement close"

RedGold's spec originally assumed a `Stop`-hook-based `cleanup_gate.py` could enforce closure
checks (coverage complete, report current) at the end of an engagement — §9.2 of
`07-enforcement.md` lists this as hook 7, and `status.md` records it as never built. It cannot be
built as specified, and the reason generalises beyond this one hook `[SOURCE:
rg1-finding-integrity.md §9.1a]`:

> "there is no Claude Code lifecycle event for 'engagement close', because an engagement is not an
> object the harness knows about." It spans sessions and is closed by an operator decision the
> harness never observes.

Every one of the 31 events is turn-, tool-, batch-, subagent-, task-, worktree-, or
session-scoped `[SOURCE: rg1-finding-integrity.md §9.1a, cross-checked against claude-code-hooks.md
§1]`. None spans "everything that happened across however many sessions this engagement took."
`SessionEnd` looked like the closest candidate and isn't — an engagement outlives a single session,
and `SessionEnd` cannot block even within that one session (see next section).

**Consequence, stated as the spec states it:** closure is implemented as an act, not a hook —
`gate_cli.py close` (`/rg:close`), which runs the coverage and report-currency checks in one place
and appends a `gate.close` row to `ledger/gates.jsonl`. This is opt-in the same way `gate_cli.py
approve` already is, and skipping it is now *detectable* (no `gate.close` row) rather than silently
absent. The spec is explicit that this does not eliminate the gap — an operator who never runs
`/rg:close` is still stopped by nothing; it only narrows the failure to a documented, detectable
one `[SOURCE: rg1-finding-integrity.md §9.1a]`.

## 2. `Stop` fires per turn — a coverage-emptiness check on it fires all engagement

The first hook considered for closure enforcement was `Stop`, because it's the only event that can
actually block a normal conversational turn from ending. It was rejected for closure duty for a
reason distinct from "wrong scope" — it is **actively harmful** at the cadence it fires:

> "`Stop` hook... Fires 'when Claude finishes responding' — once per turn, many times per
> engagement. Exit 2 'Prevents Claude from stopping, continues the conversation'... A refusal keyed
> on an empty corpus fires on every turn of a healthy engagement's opening phase — §2.3's
> disabled-gate failure again. And exit 2's actuator is the *model*, not the operator: it coerces
> the assistant to keep working at a remedy only the operator has (restore a component, re-scope,
> accept a gap with a recorded decision)." `[SOURCE: rg1-finding-integrity.md §9.1a]`

Two independent failure modes packed into that one paragraph, worth separating for reuse:

- **Cadence mismatch**: any `Stop`-hook check whose precondition is naturally false early in an
  engagement (e.g. "findings corpus is non-empty") will refuse on every turn until that
  precondition becomes true, not just once. A healthy engagement's recon phase produces no
  findings yet by design — the opening phase is the phase the check would fire on hardest.
- **Actuator mismatch**: exit 2 on `Stop` makes *the model* keep going, not the operator. If the
  actual remedy for the refusal is something only the operator can do (re-scope, restore a
  component, accept the gap), coercing the model to continue just produces more model output
  against a problem the model cannot solve.

**Consequence, stated as the spec states it:** `cleanup_gate.py` (still unbuilt, per `status.md`)
keeps a narrower remit than closure-checking. Coverage-emptiness is operator-actionable only, so it
does not belong behind a `Stop` hook; `cleanup_gate.py`'s own remit (pending/orphaned rows in
`ledger/cleanup.jsonl`) is agent-actionable — "the remedy is to delete the row" — which is exactly
what `Stop`'s exit-2 coercion is shaped for `[SOURCE: rg1-finding-integrity.md §9.1a]`. **The
general rule this yields**: before putting a check behind `Stop`, ask who can actually fix what it's
refusing on. If the fix requires the operator, `Stop` is the wrong event regardless of how urgent
the check feels — route it to a command the operator invokes deliberately instead.

## Related

- [Claude Code hooks reference](hooks.md) — the general event table this page's conclusions are
  built on, in particular the `Stop` and `SessionEnd` rows in §1.
