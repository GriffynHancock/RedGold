# status.md — RedGold

*What is true right now.* Present tense only. History goes in `session.md`.

## Phase
| Phase | State | Note |
|---|---|---|
| Design spec (A–F) | **complete** | 16 files, `docs/specs/redgold/` |
| Briefing condensation | **complete** | `docs/REDGOLD-BRIEFING.md` |
| Implementation | **steps 1–9 done — `/rg:report` exists** | All of §17.2 steps 1–9 pass their acceptance tests. **341 tests green**, plus 14/14 fault injection. Plus `/rg:scope` and the report generator. Pipeline runs end-to-end on a real engagement |
| Remaining v1 gaps | **3 items, listed below** | §17.1's v1 column also names `session_start.py`, `cleanup_gate.py` and scope_guard's §9.3.2 plan checks. None are built |
| Subsystem F (compliance) | **specced, not built** | all content `[VERIFY]`, research outstanding |

## Immediate objective
**Demo tomorrow.** The pitch is **leverage and velocity**, not a product. Narrative:

| Beat | Claim | Evidence |
|---|---|---|
| **After 2 days** | "I can audit automatically — tens of man-hours, near zero marginal cost" | Prior-engagement case study (`docs/demo/`), and Anjali if the snapshot lands |
| **In a few weeks** | "The framework that mechanically refuses out-of-scope and unauthorised actions" | Spec §9, `scope_guard.py`, the gate model |
| **In a few months** | "Isolation and defence in depth — down to model outputs — with SIEM integration" | Subsystem G (§9.10), event envelope (§9.11) |
| **The close** | "You could hire me for anything. This is the leverage I bring." | The trajectory itself is the argument |

Audience: technical in the early 2000s, marketing since ~2015. Favour flow and consequence over
implementation detail. Diagrams in Mermaid.

## Demo targets
Operational detail for each engagement (hostnames, IPs, repo paths, container names) lives in that
engagement's own directory under `~/engagements/`, which is gitignored and never enters this repo.
This table only records access mode and status.

| Target | Access | Notes |
|---|---|---|
| **Engagement A (prior)** | **ARTIFACTS ONLY — no live testing** | Full prior findings held in that engagement's own directory. Known finding classes: public storage bucket, precise geo on public sessions, no rate limiting on write endpoints. Owner-authorized previously — **confirm authorization still current before touching** |
| **Anjali** | white-box | Ghost CMS fork. Repo path and host recorded in that engagement's own directory. Operator owns it — self-authorized |

## Environment verified
- `gh` CLI authed (GriffynHancock, keyring token)
- tailscale up; target host reachable (see engagement directory for hostname/IP)
- Kali VM, Burp, chrome-devtools MCP plugin present
- **Unverified:** whether Claude Code itself needs separate GitHub auth for private repo reads

## Open blockers
| # | Blocker | State |
|---|---|---|
| B-1 | Prior-engagement authorization | **RESOLVED — NOT CURRENT.** Do **not** touch the live target. Mine the existing artifacts in that engagement's own directory only. Treat prior findings as one early data point, not the picture |
| B-2 | Anjali scope | **RESOLVED — tailscale host only. Snapshot confirmed landed (operator, 2026-08-04), so testing is no longer gated.** Private repo is a fork of Ghost (large, not vibe-coded). Recon map: `docs/demo/aqnjali-pre-audit.md`. Same-host containers on that engagement's host belong to a different product — **out of scope, do not touch**. Ask the operator before any live action |

## Demo artefacts
- `docs/demo/case-study-anonymous-audit.md` — **CLEARED TO SHOW.** Owner permission granted on
  condition of anonymity; anonymised (renamed, sector + stack generalised). Accuracy-checked against
  the phase artifacts — all six flagged claims SUPPORTED. Three corrections applied: location finding
  now includes the video-call link + invitee list; "dependencies came back clean" downgraded to two
  named open questions; §3 now discloses the 20-vs-10 rate-limit overrun and uses it as the hinge into
  why enforcement must be mechanical. Table now uses PROVEN/SPECULATED consistently.
- `docs/demo/case-study-verification.md` — claim-by-claim verification against the prior engagement's `phase*.json` artifacts (held in that engagement's own directory).
- `docs/demo/aqnjali-pre-audit.md` — Anjali white-box recon map (note: filename typo).

## Outstanding research (agents died on session limit, not dispatched)
1. Compliance stage-1 orienting pass (highest value, cheapest)
2. Privacy Act small-business exemption removal — date, instrument, threshold
3. Verification pass on the second-audit fixes
4. Evidence-relevance audit (does each citation support the inference drawn from it)
5. Compliance stage-2: seven remaining narrow passes

## Built and enforced (v1)

| Control | Script | Denies |
|---|---|---|
| Scope + ports + ceiling | `scope_guard.py` | out-of-scope host, unauthorised port, over-ceiling action, undeterminable target, outside window |
| Hand-rolled loops | `no_handrolled_loops.py` | loops, `xargs`, brace expansion, curl globbing, `-Z`, backgrounded requests |
| Write authorisation | `canary_check.py` | a write with neither a canary proven deleted nor plan pre-approval |
| Subagent nesting | `no_nesting.py` | a worker calling `Agent`/`Task`, recorded as a blocker |
| Findings validation | `validate_findings.py` | a subagent stopping with invalid findings; auto-demotes unresolvable evidence (hook and directory-CLI modes) |
| Credential redaction | `redact.py` | strips credential values from tool output, keeping class + length so the finding stays reportable |
| Asset promotion | `scope_cli.py` | promotion on one signal, on an IP, or outside the boundary |
| Baseline (P10) | `baseline_scan.py` | n/a — fixed checklist, records negatives |
| Status / report | `regen_status.py`, `report.py` | unverified above-Low findings never reach the client body |

## Test discrimination — the count is not the claim

**`/usr/bin/python3 scripts/verify_controls.py`** breaks each control deliberately and asserts the
suite goes red. 14 injected faults, 14 caught. Run it before trusting a green suite; a mutation
nothing catches means that control is untested whatever the number says.

This exists because a neighbouring project shipped a feature past unit tests, integration tests, a
security audit, code review and a green build, and it was still broken in six places in a real
browser — every gate passed honestly, none exercised the live surface.

## NOT enforced — do not describe these as working

1. **Gate 2 / plan deviation (§9.3.2)** — `scope_guard.py` enforces *scope*, not *the plan*. A
   CONFIRMED, in-scope, under-ceiling asset the plan does not name sails through. Gate 2 is
   currently a rule, not a control.
2. **`cleanup_gate.py`** — nothing stops an engagement closing with outstanding cleanup debt.
3. **`session_start.py`** — no context reload across compaction.
4. **§5.5 attribution-probe constraints** — rate limiting, `purpose: attribution` logging, and
   discarding observations as evidence are all unimplemented. Only the tier 0–1 restriction holds.
5. **Off-host egress filtering (§9.9)** — the only real boundary. Does not exist.

## Independent audit — 2026-08-04

Two hostile subagents, different framings ("the controls do not work" / "the docs overstate the
code"), found **11 real defects that 308 self-written tests missed** — including one that let an
unverified finding reach a client report. All fixed; all covered by
`tests/test_audit_regressions.py`. **Treat that ratio as the standing estimate of what
self-written tests catch on their own.** Audit before a first run, not after.

## Known spec weaknesses (stated, not hidden)
- **Egress containment is not yet a real boundary** (§9.9). Until filtering runs off-host —
  hypervisor, gateway VM, or macOS `pf` outside the guest — the agent can edit its own controls.
  Do not claim "cannot happen" to a client before then.
- `scope_guard.py` is defence-in-depth, not a security boundary (§9.3.1)
- No benchmark validates the actual task; acceptance tests measure reproduction, not discovery
- Subsystem F content is entirely unverified
