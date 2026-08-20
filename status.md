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
`/rg:close`. RG-1 Releases 1 and 2 and RG-2 step 1 (guard decision logging) are **all committed**
— they landed together in `acbc165`. RG-1 Release 3 has not started.
**605 passed, 18 skipped, 141 subtests, exit 0. 60/60 fault injection, exit 0.**
Measured 2026-08-20 against `de109fa` with `/usr/bin/python3`.

**Read `docs/wiki/architecture/current.md` §6 alongside this file.** It walks every control against
the field it actually reads and finds **nineteen that cannot fire on any input a current producer
generates**. The tables below have been corrected against it; where a control is listed as working,
that page is the thing that would show otherwise.

**RG-1 Release 2 shipped two critical defects that 540 tests and 33/33 fault injections did not
catch.** An adversarial review (`docs/research/rg1-code-review-2026-08-20.md`) found 12; **S1–S11
are fixed and fault-injected. S12 is not** — it is `in_phase`'s missing `phase` producer, filed
there as *low, unproven*, and the architecture review has since proven it and re-ranked it as the
second-worst defect in the repo (item 8 above, §6 D-2). Two further caveats stand: the S1
severity-carry-forward rule is the most intricate logic in the codebase and its failure mode is
silent, and `code_defect`'s producer is a sentence in an agent card, not a mechanism — a residual
`docs/wiki/architecture/current.md` §6 D-15 argues may rest on a false premise about the hook
payload, marked `[VERIFY]` and unchecked against a running hook. **A passing suite is not
assurance** — the fix round found three further defects the review itself missed, and the
architecture review then found nineteen that no test or fault could have found at all.

Subsystem F (compliance) remains specced, not built — all content `[VERIFY]`, research outstanding.

## Built and enforced

| Control | Script | Denies |
|---|---|---|
| Scope + ports + ceiling | `scope_guard.py` | out-of-scope host, unauthorised port, over-ceiling action, undeterminable target, outside window |
| Hand-rolled loops | `no_handrolled_loops.py` | loops, `xargs`, brace expansion, curl globbing, `-Z`, backgrounded requests |
| Write authorisation | `canary_check.py` | a write with neither a canary proven deleted nor plan pre-approval |
| Subagent nesting | `no_nesting.py` | a worker calling `Agent`, `Task`, `TaskOutput` or `AskUserQuestion`, recorded as a blocker. **`SendMessage` and 7 other nesting tools are not wired** — item 10 below |
| Findings validation | `validate_findings.py` | a subagent stopping with invalid findings; auto-demotes unresolvable evidence (hook and directory-CLI modes). **Four of its checks are inert on this path** — item 9 below |
| Asset promotion | `scope_cli.py` | promotion on one signal, on an IP, or outside the boundary |
| Gate 1 plan/approve | `gate_cli.py` | work proceeding without a recorded, approved plan. Records intent; **no action joins to it** — item 12 below |
| Engagement close (RG-1 §9.1a) | `gate_cli.py close` | closing with no completed phase (`PHASE_NEVER_COMPLETED`) or a voided Gate 1 (`GATE_1_VOID`). Its other two refusals are items 7 and 8 below — **see caveat 6** |
| Baseline (P10) | `baseline_scan.py` | n/a — fixed checklist, records negatives. **It also self-certifies** — item 11 below |
| Status / report | `regen_status.py`, `report.py` | an above-Low finding whose `verified` field is weak never reaches the client body. **This is not the same as "nothing unverified reaches the client"** — item 11 below |

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

---

Items 7–14 were **moved out of the "Built and enforced" table on 2026-08-20** by the currency audit,
on the evidence of `docs/wiki/architecture/current.md` §6. Each is wired, tested, and cannot fire —
or fires on everything, which is the same defect wearing the other mask. None of them may be
described as working until the named producer exists.

7. **Report freshness (`REPORT_STALE`) — inverted, not merely inert (§6 D-1).** `report.py --check`
   and `/rg:close` read `created` on **every** record in `findings/*.json`, and refuse outright when
   any record's timestamp will not parse. `created` has **no producer except `baseline_scan.py`**,
   and no agent card mentions the field. So the first freehand finding an agent writes permanently
   blocks `/rg:report --check` and `/rg:close`, with a message that does not name the offending
   record. This is the disabled-gate failure from CLAUDE.md design judgement 2 in its pure form:
   *name a healthy state at which this fires* — every one of them. Do not claim report freshness is
   enforced until an agent-facing `created` producer exists.

8. **Phase-scoped coverage (`COVERAGE_EMPTY_PHASE`) — degrades to one engagement-wide check
   (§6 D-2).** `gate_cli.in_phase` discriminates on a `phase` field that **nothing anywhere writes**,
   and it counts an untagged record toward whichever phase is being closed. With no producer, every
   phase is satisfied by any finding anywhere in the engagement: `complete --phase recon` with real
   findings, then `--phase webtest`, `--phase codeaudit`, `--phase verify` with zero work each, all
   pass. `PHASE_NEVER_COMPLETED` at close needs only one `phase.complete` row. The thing RG-1 §8.2
   calls *"the single most important thing in this section"* is currently satisfied by one baseline
   scan. The second half of the check — an `absent` row in `coverage.jsonl` — has no producer either
   (§6 D-4), so the refusal message offers a remedy the operator cannot perform.

9. **Four `validate_findings.py` checks are inert at `SubagentStop` (§6 D-5, D-6, D-7).**
   `ENVIRONMENT_DISCREPANCY`, the `code_defect` `production_nexus` default,
   `CODE_DEFECT_CLEARED_WITHOUT_REASON`'s cleared-vs-never-set distinction, and form (b) of
   `DERIVATION_MISMATCH` all read fields stamped by `findings.apply_environment_cap` — which the
   `SubagentStop` path never calls. They are live only at report assembly, the last possible moment,
   after the agent that could have re-examined the asset has stopped. RG-1 §4.2 claims the check runs
   at *"finding creation … and report assembly"*; the finding-creation half works only for
   `baseline_scan`, which calls the cap itself.

10. **8 of `no_nesting.py`'s 12 nesting tools are unguarded (§6 D-8).** `NESTING_TOOLS` names twelve;
    the matcher `new_engagement.py` writes is `Agent|Task|TaskOutput|AskUserQuestion`, and the
    harness treats that as an **exact alternation**, not a prefix. `TaskCreate`, `TaskUpdate`,
    `TaskList`, `TaskGet`, `TaskStop`, `SendMessage`, `ExitPlanMode` and `EnterPlanMode` never invoke
    the hook. `SendMessage` is called out in the script's own comment as a real tool a hardcoded list
    had already missed once. The list was fixed; the wiring was not.

11. **The baseline self-certifies, and three of its checks fire on `status == 200` (§6 D-10, D-11).**
    `baseline_scan.make_finding` writes `"verified": "executed"` on any check whose predicate
    returned true, so P2 — *a finding is not a finding until something other than the model verified
    it* — is satisfied by the producer's own claim, and `UNVERIFIED_ABOVE_LOW` is structurally
    unreachable from the only mechanical producer. Compounding it, `_admin_reachable` is
    `return probe.status == 200` and backs `admin_open` (**critical**), `ghost_admin_open` (high) and
    `actuator_open` (high). Against an SPA that serves `200` for unknown paths — the modal shape for
    this client segment — the pair writes `status: PROVEN`, `verified: executed`,
    `confidence: confirmed` with a resolving evidence pointer, passes every gate in
    `validate_record` and every branch of `report.classify`, and lands a **fabricated critical in
    "What we found"**. RG-1 §5.3 specifies the fix (`grant_evidence: status_only`); §4.5 specifies
    `VERIFIED_BY_SELF`. Neither is built (RG-1 §9.2 records E3 as not landed).

12. **No action joins to any approval — `gate_ref` is null in every activity row (§6 D-14).**
    `scope_guard.build_activity_row` stamps `"gate_ref": None` and says why. Gate 1's
    `plan_hash`/`scope_hash` staleness rule therefore binds in exactly two places: `rate_probe.sh`
    and `gate_cli close`. Every other network action in an engagement is unattributable to any
    approval, so `/rg:gate approve` is a record of intent rather than a gate on action.

13. **`[VERIFY]` content is not stripped from deliverables (§6 D-19).** `report.py`'s module
    docstring lists *"`[VERIFY]`-marked content never reaches a client"* among the things the report
    refuses to do, and `agents/rg-report.md` repeats it as an instruction. **There is no such check.**
    `grep -n VERIFY scripts/report.py` matches only the docstring sentence. Hard rule 1 is currently
    enforced by a docstring and an agent instruction. RG-1 §11.2's literal deny-list for the
    `8 of 11` scoreboard is unbuilt too.

14. **`crown_jewels` and `forbidden_actions` are parsed and read by nothing (§6 D-16).** Both are
    type-checked, round-tripped and serialised into `scope.yaml`. `crown_jewels` is Gate 0's headline
    output; `forbidden_actions` is a client's explicit "leave this alone" list. Neither has any
    consumer anywhere in the code. A client-facing promise with no mechanism.

15. **Credential redaction depends on an undocumented harness field, and its behaviour has never been
    observed (§6 D-9, partially corrected).** `redact.py` emits
    `hookSpecificOutput.updatedToolOutput`. That field is **absent from the published hooks reference
    page** but **present in Anthropic's own CHANGELOG at v2.1.121** — *"PostToolUse hooks can now
    replace tool output for all tools … (previously MCP-only)"* — and the installed binary is
    **2.1.212**, verified 2026-08-20. So the field is real and the version is adequate; the
    architecture review's original reading (that it "may be entirely inert") was drawn from this
    repo's own incomplete schema page and is corrected. `docs/wiki/claude-code/hooks.md` §3.1 now
    records it.
    **What is not resolved, and is why this stays out of the table above:** an undocumented field can
    be removed by any release without a deprecation note, and the control does not self-test;
    `PostToolUse` fires only on tool *success*, so `PostToolUseFailure` carries no hook and that is a
    coverage hole; `new_engagement.settings_json` attaches a `matcher` only for `PreToolUse`, so
    `redact.py`'s declared matcher is discarded and it runs on every tool call; and
    `tests/test_redact.py` asserts only that the *script emits* the field, never that the *harness
    honours* it. The mutation study scores this file at **55%**. **Nothing here has been observed
    against a running hook.** The five-minute test still settles it: wire the hook, return a fake
    `sk_test_` in tool output, read the transcript. Until that is run, do not describe redaction as
    proven.

**The honest claim is "out-of-scope targets are refused by tooling and logged," never "cannot
happen."** As of RG-2 step 1, `scope_guard.py` appends a `scope.allow`/`scope.deny`/
`scope.undeterminable` row to `ledger/activity.jsonl` on every decision with a network destination.
Reconciliation against an off-host egress log (§9.9) still does not exist — there is no gateway to
reconcile against.

## Audit history

**Eight adversarial rounds are now recorded, not four.** The "four rounds, 21 defects" line stood
here until 2026-08-20 and was already four rounds out of date when it was read.

| Round | Record | Yield |
|---|---|---|
| 1–4 | `playbooks/_generic/adversarial-framings.md`, `docs/sessions/2026-08-03-04-sessions-001-004.md` | **21 real defects** the self-written suite missed, all fixed and regression-tested |
| 5 | `docs/research/session-audit-2026-08-20.md` | 23 claims checked: 16 supported, 5 overstated, 2 contradicted |
| 6 | `docs/research/rg1-code-review-2026-08-20.md` | **12 defects** in RG-1 Releases 1–2 (2 critical, 3 high, 4 medium, 3 low); S1–S10 fixed and fault-injected; the fix round found 3 more the review missed |
| 7 | `docs/research/test-suite-review-2026-08-20.md` | 126 valid fine-grained mutations, **40 survive a green suite — 68% mutation score**; measured against `c0a20bd`, a commit later rewritten into `acbc165` |
| 8 | `docs/wiki/architecture/current.md` §6 | **19 controls that cannot fire**, 13 of them new; the moved items 7–15 above |

The standing lesson does not change with the count: **every round after the first found defects the
previous round's fixes had introduced or failed to generalise.** §6.2 of the architecture page states
the mechanism — each fix was verified against the path that produced the bug report and against no
other path.

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

**This ordering is contested and the disagreement is unresolved.**
`docs/research/strategic-review.md` §5 argues that step 1 has been blocked for 16 days on a fact the
operator has not supplied, and that the briefing's §18 acceptance test — *run the framework end to
end against a target the operator owns* — requires no client, no authorisation from anyone else, no
containment build and no new code, and would unblock steps 2 and 3 today. §4 of the same document
argues the opposite of the current sequencing in three further places (stop specifying ahead of
implementation, stop the containment programme above its cheap 20%, stop deepening RG-1). **No
decision has been recorded either way.** Both readings are live; this list is the older one.

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

**Two independent measurements now bound what the 60/60 is worth, and both are worse than the
number suggests.**

- `docs/research/test-suite-review-2026-08-20.md` scored the suite at **68% fine-grained mutation**
  — 40 of 126 valid mutations survive green — with survivors clustered on band boundaries, closed
  vocabularies and fail-closed defaults. `no_handrolled_loops.py` scores 25% and `redact.py` 55%:
  the two files this repo most often describes as working. Its measurements are against `c0a20bd`
  (564 tests, 45 faults), a commit later rewritten into `acbc165`; the current tree is 605/60 and
  the mutation study has not been re-run against it.
- `docs/wiki/architecture/current.md` §7 states the harder limit: **every one of the 19 defects in
  its §6 is invisible to all 60 faults**, because mutating a control that cannot fire changes no
  test outcome. Fault injection proves the suite notices a control breaking. It cannot notice a
  control that was never able to fire.

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
- **Nineteen wired controls cannot fire on current input** — `docs/wiki/architecture/current.md` §6.
  Nine of them are disclaimed as items 7–15 above; the rest are recorded on that page. The finding
  underneath all nineteen is that **no dataflow contract exists**: no document states which component
  writes which field at which lifecycle point, so a control can be sited against a field that has no
  producer and everything still passes.
- **The five sub-projects disagree about four shared nouns** — `docs/research/strategic-review.md`
  §1. `environment` divergence is modelled twice incompatibly (RG-2 §8.3's `parity` block vs RG-4
  §8.3's `environment-delta.yaml`); three documents assume three different engagement lifecycles;
  `asset` has silently become four artifacts; and `evidence` has a transient-vs-durable collision.
  **None is resolved.** The disagreements are cross-referenced in the specs themselves; the design
  questions are open.
- **The framework has never run against a live target, and the briefing §18 acceptance test has
  never been run at all** — including against a target the operator owns, which needs nothing the
  operator does not already have.
