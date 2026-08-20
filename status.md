# status.md — RedGold

*What is true right now.* Present tense only. History goes in `session.md`.

## This repository is PUBLIC

`github.com/GriffynHancock/RedGold` is a **public** repository. Anything committed here is
world-readable the moment it is pushed. `session.md` previously recorded the v1 push as "pushed
private"; that was wrong and has been corrected.

Consequences that bind every session:
- No target hostname, tailnet, IP, container name, database name, repo URL or absolute home path
  reaches this repo. The prior engagement is referred to as **"the prior engagement"**, with
  `ENGAGEMENT-A` (blackbox) and `ENGAGEMENT-B` (whitebox) where a stable identifier is needed.
- No unremediated vulnerability in the operator's own systems is described here in a form that
  identifies the system. Such material is written as methodology; the unredacted originals live
  outside the repo, in the engagement folder.
- Hard rule 3 (client data never enters this repo) is not the only constraint — the operator's own
  infrastructure detail is equally out of bounds.

## Phase

**v1 build complete.** §17.2 steps 1–9 done, plus `/rg:scope`, `/rg:gate`, `/rg:report` and
`/rg:close`. RG-1 Releases 1 and 2 are committed; RG-2 step 1 (guard decision logging) is in the
tree.
**605 tests, 18 skipped, exit 0. 60/60 fault injection, exit 0.** Measured 2026-08-20.

**RG-1 Release 2 shipped two critical defects that 540 tests and 33/33 fault injections did not
catch.** An adversarial review (`docs/research/rg1-code-review-2026-08-20.md`) found 12; S1–S10 are
fixed and fault-injected. Two caveats stand: the S1 severity-carry-forward rule is the most
intricate logic in the codebase and its failure mode is silent, and `code_defect`'s producer is a
sentence in an agent card, not a mechanism. **A passing suite is not assurance** — the fix round
found three further defects the review itself missed.

Subsystem F (compliance) remains specced, not built — all content `[VERIFY]`, research outstanding.

## Built and enforced

| Control | Script | Denies |
|---|---|---|
| Scope + ports + ceiling | `scope_guard.py` | out-of-scope host, unauthorised port, over-ceiling action, undeterminable target, outside window |
| Hand-rolled loops | `no_handrolled_loops.py` | loops, `xargs`, brace expansion, curl globbing, `-Z`, backgrounded requests |
| Write authorisation | `canary_check.py` | a write with neither a canary proven deleted nor plan pre-approval |
| Subagent nesting | `no_nesting.py` | a worker calling `Agent`/`Task`/`SendMessage`, recorded as a blocker |
| Credential redaction | `redact.py` | strips credential values from tool output, keeping class + length so the finding stays reportable |
| Findings validation | `validate_findings.py` | a subagent stopping with invalid findings; auto-demotes unresolvable evidence (hook and directory-CLI modes) |
| Asset promotion | `scope_cli.py` | promotion on one signal, on an IP, or outside the boundary |
| Gate 1 plan/approve | `gate_cli.py` | work proceeding without a recorded, approved plan |
| Phase completion (RG-1 §8.2) | `gate_cli.py complete` | a phase closing with zero findings **and** zero record of having looked (`COVERAGE_EMPTY_PHASE`) |
| Report freshness (RG-1 §8.6) | `report.py --check` | a deliverable that predates its own findings (`REPORT_STALE`) |
| Engagement close (RG-1 §9.1a) | `gate_cli.py close` | closing with a stale deliverable, no record of having looked, or no completed phase — **see caveat 6 below** |
| Baseline (P10) | `baseline_scan.py` | n/a — fixed checklist, records negatives |
| Status / report | `regen_status.py`, `report.py` | unverified above-Low findings never reach the client body |

## NOT enforced — do not describe these as working

1. **Gate 2 *automatic* detection of plan deviations (§9.3.2)** — `gate_cli.py` can record and
   resolve a blocker, but nothing raises one automatically. A CONFIRMED, in-scope, under-ceiling
   asset the plan does not name still sails through unflagged.
2. **`cleanup_gate.py`** — nothing stops an engagement closing with outstanding cleanup debt.
3. **`session_start.py`** — no context reload across compaction.
4. **Most of §5.5's attribution-probe constraints** — rate limiting, `purpose: attribution`
   logging, and discarding observations as evidence are unimplemented. Only the tier 0–1
   restriction holds.
5. **Off-host egress filtering (§9.9)** — the only real boundary. Does not exist.
6. **Engagement close is not mechanically enforced.** `/rg:close` refuses on a stale deliverable,
   an empty corpus, or no completed phase — but an operator who never runs it is stopped by
   nothing. **There is no Claude Code lifecycle event for engagement close**: every hook event is
   turn-, tool-, session- or subagent-scoped, `Stop` fires once per *turn* (a coverage refusal
   there would fire on every turn of a healthy engagement's opening phase), and `SessionEnd`
   cannot block at all. `/rg:close` narrows the failure from "forgot a check" to "skipped the
   documented close step", and makes the skip detectable afterwards — the absence of a
   `gate.close` row in `ledger/gates.jsonl`. It does not eliminate it. See RG-1 §9.1a.

**The honest claim is "out-of-scope targets are refused by tooling and logged," never "cannot
happen."** As of RG-2 step 1, `scope_guard.py` appends a `scope.allow`/`scope.deny`/
`scope.undeterminable` row to `ledger/activity.jsonl` on every decision with a network destination.
Reconciliation against an off-host egress log (§9.9) still does not exist — there is no gateway to
reconcile against.

## Audit history

Four adversarial rounds, **21 real defects that the self-written suite missed**, all fixed and
regression-tested. See `playbooks/_generic/adversarial-framings.md` for the framings used and
`session.md` for the defect-by-defect record.

## Authorisation posture — no target, named or unnamed

**No target is authorised by default, and none is named here.**

Which client is next is *engagement pipeline*, not framework state. It does not belong in this
repo — this file is public, and naming a prospective target beside the words "not yet authorised"
is the single most damaging thing that could be published from here. Pipeline lives in the
operator's own notes and in `~/engagements/`.

The rule that binds regardless of who the target is:

> An engagement begins when an authorisation document exists **on disk** and `/rg:new` has run.
> A statement in a chat session that approval was obtained does not satisfy §15.1, however true it
> is. `/rg:new` refuses without the document precisely so this cannot happen by drift — the refusal
> is the control, not the operator's memory of what was agreed.

Until that record exists for a given target: no candidate host, no probe, nothing.

## Next steps, in order

1. Record the next engagement's authorisation and scaffold (`/rg:new`) — once the operator
   supplies the facts §15.1 requires.
2. Run the engagement.
3. Only then consider the scanner-composition work in `docs/research/scanner-integration.md` — it
   is deliberately deferred so the profile format is designed against a real engagement rather than
   a hypothesis.

## Deferred research — ordered by what actually moves the boundary

1. **Off-host egress containment** (§9.10). The only real boundary, and it does not exist. Until it
   does, the honest claim stays "refused by tooling and logged", never "cannot happen".
2. **Typed tool interface instead of shell parsing** —
   `docs/research/structured-tool-interface.md`. Raised by outside review 2026-08-04. Shrinks the
   heuristic layer and makes the "MCP has no canonical target field" denial obsolete for a server
   we define ourselves. **Does not replace the boundary**, and is not a boundary while `Bash`
   remains available. Build it after (1), or it makes the framework sound safer than it is.
3. **Scanner composition** — `docs/research/scanner-integration.md`.

## Test discrimination — the count is not the claim

**`/usr/bin/python3 scripts/verify_controls.py`** breaks each control deliberately and asserts the
suite goes red. 60 injected faults, 60 caught. Run it before trusting a green suite; a mutation
nothing catches means that control is untested whatever the number says.

**And a caught mutation is not proof of a correct control.** On 2026-08-20 the suite stood at 540
tests and 33/33 faults while shipping two critical defects, because fault injection uses coarse
mutations (`if X:` → `if False:`) and a control can survive every one of them and still be wrong at
a boundary or read its input from the wrong place.

This exists because a neighbouring project shipped a feature past unit tests, integration tests, a
security audit, code review and a green build, and it was still broken in six places in a real
browser — every gate passed honestly, none exercised the live surface.

## Known spec weaknesses (stated, not hidden)
- **Egress containment is not yet a real boundary** (§9.9). Until filtering runs off-host —
  hypervisor, gateway VM, or macOS `pf` outside the guest — the agent can edit its own controls.
  Do not claim "cannot happen" to a client before then.
- `scope_guard.py` is defence-in-depth, not a security boundary (§9.3.1)
- No benchmark validates the actual task; acceptance tests measure reproduction, not discovery
- Subsystem F content is entirely unverified
