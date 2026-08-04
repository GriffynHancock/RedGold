# status.md — RedGold

*What is true right now.* Present tense only. History goes in `session.md`.

## Phase

**v1 build complete.** §17.2 steps 1–9 done, plus `/rg:scope`, `/rg:gate` and `/rg:report`.
**406 tests, 18 skipped, exit 0. 21/21 fault injection, exit 0.** Pushed to a private repo.

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

**The honest claim is "out-of-scope targets are refused by tooling and logged," never "cannot
happen."**

## Audit history

Four adversarial rounds, **21 real defects that the self-written suite missed**, all fixed and
regression-tested. See `playbooks/_generic/adversarial-framings.md` for the framings used and
`session.md` for the defect-by-defect record.

## Immediate objective — opensesh is NOT YET AUTHORISED

The next engagement is **opensesh**, and it is **NOT YET AUTHORISED IN THE FRAMEWORK'S TERMS**.

> The operator states (2026-08-04, in session) that approval has been obtained for non-destructive
> testing that creates a small amount of junk data. **The scope facts have not been recorded and no
> authorization document exists on disk.** Before anything touches this target, the operator must
> supply: who approved it and when; the hosts and any non-standard ports; the engagement window
> dates; confirmation of mode/ceiling (non-destructive with junk data reads as `audit` / ceiling 2);
> and anything explicitly excluded. Then write the authorization record and run `/rg:new`.
> **Do not test on the strength of a chat message.** `/rg:new` refuses without an authorization
> document precisely so this cannot happen by drift.

## Open blockers

| # | Blocker | State |
|---|---|---|
| B-1 | opensesh authorisation | **Prohibited until the scope record exists on disk — not a flat, permanent prohibition.** The operator has stated in-session that approval was obtained; that statement alone does not satisfy §15.1. The prohibition lifts the moment the authorisation facts named in the Immediate objective above are recorded and `/rg:new` has run. Until then: no candidate host, no probe, nothing |

## Next steps, in order

1. Record the opensesh authorisation and scaffold (`/rg:new`) — once the operator supplies the
   facts named above.
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
suite goes red. 21 injected faults, 21 caught. Run it before trusting a green suite; a mutation
nothing catches means that control is untested whatever the number says.

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
