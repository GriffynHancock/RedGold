---
title: Deliverables, build order, and risks
question: What does the client receive, in what order is this built, and what could go wrong?
sections: [16, 17, 18]
spec: RedGold design
status: draft
date: 2026-08-03
---

## 16. Deliverables and service tiers

| Tier | Engagement | Mode | Client receives |
|---|---|---|---|
| **0** | Quick scan | `audit`, ceiling 1 | Single report: asset register + severity-ordered findings |
| **1** | Full audit | `audit`, ceiling 1 | Tier 0 + hardening playbook + calibrated next-steps |
| **2** | Full audit + handoff | `audit`, ceiling 2 | Tier 1 + regression suite + guardrail pack |
| **3** | Retainer | negotiated | Tier 2 + living asset register + drift monitoring + scheduled advisory feed |

Tier 0/1 is the volume business and the wedge — an audit is what a founder needs before anyone
funds anything more. Tier 2/3 is where the north star's recurring value lives.

---

## 17. Build order and acceptance tests

Subsystem A only. Each step has a test that must pass before the next begins.

### 17.1 The v1 cut

Subsystem A as specified is a large build for one person, and `scope_guard.py` in particular is a
bespoke policy engine for arbitrary shell commands, not "a script."

The cut follows from the product's own centre of gravity. **`audit` mode is ceiling 1, and ceiling 1
is read-only by definition** — so the entire write-testing apparatus is unnecessary for the tier
that §1.1 identifies as the volume business and the commercial wedge.

| | v1 — `posture` + `audit` (ceiling 2) | v2 — the rest |
|---|---|---|
| Enforcement | `scope_guard.py` incl. plan checks (§9.3.2), `baseline_scan.py`, `no_handrolled_loops.py`, `canary_check.py`, `rate_probe.sh`, `redact.py`, `session_start.py`, `cleanup_gate.py` | tier-3 `redteam` path, Gate 3 |
| Findings | schema, evidence capture, `validate_findings.py`, `rg-verify` gates, `finding_class` | — |
| Agents | all seven cards, `using-redgold`, three-file contract, ledgers, `regen_status.py` | agent `memory:` accumulation |
| Playbooks | **one hardcoded flagship (Supabase) plus `_generic/`** | `playbook-dispatch`, `index.yaml`, evals, `/rg:harvest` |
| Governance | §15.1–15.6, incl. write authorisation (§9.4.1) | §15.7 commercial items |
| Handoff (E) | hardening playbook | guardrail pack, regression suite, monitoring |

An earlier draft cut the write-testing apparatus from v1 on the reasoning that "audit is read-only."
**That reasoning was wrong** — §6 establishes that rate limiting is table stakes for an audit and
cannot be checked without writes. Since `audit` is the product, v1 carries the full write path
including canary gating and the cleanup credential. What defers is the *knowledge-scaling*
machinery (dispatch, evals, harvest, agent memory) and the tier-3 red-team path — neither of which
any first paying client needs.

Deferring dispatch until there is a second and third playbook is deliberate: dispatch solves a
problem that does not exist at n=1, and building it early means designing the index against a single
example.

Steps 1–9 below are v1. Steps 10 and 11 are v2.

### 17.2 Steps

| # | Build | Acceptance test |
|---|---|---|
| 1 | Plugin skeleton, `plugin.json`, marketplace manifest | Installs on a clean profile; `/rg:` commands appear |
| 2 | `scope.yaml` schema + parser | Rejects malformed scope; round-trips the prior engagement expressed as a boundary |
| 3 | `scope_guard.py` | Denies an out-of-scope host, a ceiling violation, a base64-obfuscated target, and an undeterminable host — proven by unit tests over recorded stdin JSON |
| 4 | Engagement scaffolder `/rg:new` | Produces a complete engagement dir whose hooks fire and deny correctly end-to-end |
| 5 | `validate_findings.py` | **Runs against the prior engagement's five `phase*.json` files and correctly flags their known gaps** |
| 5b | `baseline_scan.py` (P10) | The prior-engagement stack is scanned with no fingerprint supplied, and the known public bucket is found by the baseline alone |
| 6 | Findings schema + evidence capture | An evidence pointer that does not resolve auto-demotes the record |
| 7 | `no_handrolled_loops.py`, `rate_probe.sh`, `canary_check.py` | The prior-engagement 20-request overrun is denied; a write with no verified canary is denied |
| 8 | Agent roster | `rg-lead` cannot issue a network call — proven by an attempt that is denied. **A worker attempting to spawn a subagent is caught loudly, not silently ignored (§8.0).** A full phase runs end-to-end and the worker demonstrably executed |
| 9 | `using-redgold` + three-file contract + `regen_status.py` | `status.md` regenerates identically from ledger + findings |
| 10 | `playbook-dispatch` + `_generic/` + `backends/supabase` | Fingerprinting the prior-engagement stack loads the Supabase playbook **together with its declared `_generic/backend-authz` parent, and nothing else**; evals pass |
| 11 | `/rg:harvest` | A prior-engagement lesson lands in the correct version-keyed playbook file, redacted |

**Overall acceptance: the prior engagement can be re-run end-to-end under RedGold**, producing at
minimum the same findings with resolvable evidence, no ROE violations, and no cleanup debt.

---

## 18. Risks and open questions

**R1 — Hook friction mid-engagement.** A misfiring `scope_guard.py` blocks legitimate work at an
inconvenient moment. *Mitigation:* short timeouts (10–30s), a documented `/rg:scope` path to widen
the boundary properly, and clear denial reasons. Deliberately **not** mitigated by a bypass flag —
a bypass would defeat the control's entire purpose.

**R2 — Fail-closed denial-of-service against ourselves.** Denying when a host cannot be determined
will occasionally block harmless commands. Accepted: for a security tool, deny-by-default is
correct, and the fix is better host extraction, not a looser default.

**R3 — Verification cost.** `rg-verify` re-running every finding costs tokens and time. *Mitigation:*
verification is mandatory only above Low severity.

**R4 — Playbook staleness.** Version-keyed knowledge rots as products change. *Mitigation:* every
entry carries the engagement date it came from; dispatch surfaces the age; a stale entry is a seed
hypothesis, never a conclusion.

**R5 — Token/cost blowout.** Vendor and practitioner reporting (**not** peer-reviewed — flagged
because P9 holds client-facing claims to a stricter bar than this) describes failed agent runs
showing roughly 9x token amplification versus successful ones,
and full-context retry loops have been documented ballooning up to 50x. *Mitigation:* `maxTurns`
caps on every worker card, file-based handoff instead of inline payloads, and never resending full
context on retry.

**R6 — Legal exposure from attribution error.** The worst realistic failure is testing an asset the
client does not own. *Mitigation:* §5.4's invariant, two-signal attribution, IP never counting
alone, and the candidate queue being structurally unreachable.

**Open questions for implementation:**

- Should `rg-verify` run as a `context: fork` skill rather than a subagent, to keep verification
  output out of the Lead's context entirely?
- Is SQLite worth adopting over JSONL for findings once engagements exceed a few dozen records, or
  does the loss of greppability and git-diffability outweigh query convenience?
- Should the guardrail pack (E1) ship as a separate installable plugin for the client, rather than
  loose files copied into their repo?

---
