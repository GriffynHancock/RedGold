---
title: RG-1 — finding integrity
date: 2026-08-20
status: draft
question: What must a finding record carry, and what must the framework mechanically check, so that the seven bad findings the prior engagement produced could not have been produced — without turning the framework into a suppression engine?
---

# RG-1 — finding integrity

Sub-project RG-1. Extends `docs/specs/redgold/08-findings-and-verification.md` (§10). **The §10.1
schema is settled: this document adds fields and never restructures.** Every rule in §10.2–10.6
survives unchanged, and §10.3's central rule — *no `technical` finding above Low reaches a client
without `replayed` or `executed`* — is load-bearing here and is re-asserted at §5.2.

Evidence base: `docs/research/prior-engagement-autopsy.md` (what failed),
`docs/research/exploitability-severity-model.md` (the design),
`docs/research/rg1-implementation-surface.md` (the code map). Where those three conflict with
`docs/research/session-audit-2026-08-20.md`, **the audit wins**; every such override is named in
place.

## Index

| § | Contains |
|---|---|
| 1 | Purpose and the evidence for it |
| 2 | Pre-spec verification — the Vercel deployment-header check, and what it costs the discrepancy gate |
| 3 | Schema additions |
| 4 | The mechanical rules |
| 5 | The scanner-findings interface — the 12 baseline checks |
| 6 | The environment cap — **PROVISIONAL** |
| 7 | The adversarial reviewer's contract |
| 8 | The coverage counterweights — specced first, shipped first |
| 9 | Build order, tests, and injected faults |
| 10 | What this does NOT do |
| 11 | Provisional items and citation bars |
| 12 | Open decisions for the operator |

---

## 1. Purpose, and the evidence for it

Eleven findings reached ENGAGEMENT-A's `status.md`. **One** was a genuine, production-relevant,
correctly-rated result; three were correctly-rated low posture facts; **seven — including the only
critical and two of the three highs — were artifacts of testing a Docker dev stack on the operator's
laptop and reporting its dev-only components as the client's production system**
(`docs/research/prior-engagement-autopsy.md:17-22`). Separately, the whitebox engagement, which held the only
`SOURCE_CODE` asset, produced **zero artifacts of any kind** (`prior-engagement-autopsy.md:22, 36, 39-43`).

The engagement's reasoning was locally sound at every step. It never once asked *what environment am
I in* or *what does the attacker already have to hold* (`prior-engagement-autopsy.md:24-26`). Those two omitted
questions generate all seven bad findings. RG-1 makes both questions required fields and both answers
mechanically consumed.

### 1.1 The eight failure modes, and which of them RG-1 addresses

From `prior-engagement-autopsy.md` §C. Column 3 is this document's section.

| FM | Failure | Autopsy cite | RG-1 answer |
|---|---|---|---|
| FM-1 | **Environment blindness.** No step established whether the target was production. | `:304-335` | §3 `environment_at_test`, §6 cap, §4.2 discrepancy |
| FM-2 | **Fixed severity table decoupled from the observed response.** `_admin_reachable` is `return probe.status == 200`; severity is a constant on the `Check` tuple. | `:337-355` (predicate at `scripts/baseline_scan.py:104-106`; severity at `:158`, applied at `:235`) | §5.3 `grant_evidence: status_only` pins such checks to the info band |
| FM-3 | **Self-certified verification.** The discoverer writes the field attesting independent verification. | `:357-379` (`scripts/baseline_scan.py:232-233`) | §4.5 `VERIFIED_BY_SELF`; `baseline_scan.py:233` stops writing `executed` |
| FM-4 | **Verification verdicts land in prose and are never merged.** `rg-verify` argued F-005 high→low correctly; `findings/baseline.json:78` still says `high`. | `:381-401` (`findings/verification.md:184-186, 251-252`) | §7 `findings/review.jsonl` + `merge_review.py` |
| FM-5 | **Reasoned escalation past the last executed step.** The disclaimer was written by the agent, in the same field as the claim, and nothing read it. | `:403-423` (`findings/webtest.json:12, 114`) | §4.6 `IMPACT_NOT_EXECUTED` lint |
| FM-6 | **Chains rated by novelty rather than capability delta.** F-107 (`critical`) over F-103 (`high`), where F-107 requires F-103's capability and yields strictly less. | `:425-443` | §4.3 dominance rule over `precondition`/`grants` |
| FM-7 | **Checklist × asset cartesian emitted as findings.** 36 `not_applicable` records for one coverage fact about three assets; HSTS demanded of a plaintext origin. | `:445-459` | §4.1 applicability filter (E2) |
| FM-8 | **Blast radius asserted, never enumerated.** *"Any host that can reach TCP 6379 on this tailnet"*, with no denominator, four times. | `:461-478` | §3 `reachable_population.established_by`, §4.4 `REACH_UNENUMERATED` |

The autopsy's own summary of the shape: FM-1 and FM-8 are *where is this thing and who can get to
it*; FM-5, FM-6 and FM-2 are *what did I actually do versus what am I claiming*; FM-3 and FM-4 are
the framework failing to carry its own answers between components (`prior-engagement-autopsy.md:480-488`).

### 1.2 The two things that must not be lost

**(a) Section F.** The autopsy's false-negative section is the constraint that stops this programme
becoming a suppression engine. Nothing in §§3–7 would have suppressed the real, unfound defects:
the preview-route entitlement-parameter bypass (`prior-engagement-autopsy.md:677-715`), the missing
unique constraint on the payments ledger's natural business key (`:756-762`), the absent fulfilment
fallback (`:763-767`), the dead stale-lock reaper (`:768-772`), the live spend-capable Resend
key in a dev config (`:782-791`). §8 is what makes those findable; §6.3's `code_defect` nexus is what
stops the environment cap from burying them once found.

**(b) The autopsy's own closing line.** *"The largest single improvement available to this framework
is not a suppression rule — it is running the whitebox engagement"* (`prior-engagement-autopsy.md:778-780`).
§8.3 is the mechanical form of that sentence.

---

## 2. Pre-spec verification — `x-vercel-deployment-url`

`exploitability-severity-model.md:773` makes a `nonprod-signal-present` classifier verdict against a
declared `production` a **blocking** `ENVIRONMENT_DISCREPANCY`, and its top-ranked signal is
`x-vercel-deployment-url` resolving to a `*.vercel.app` host (`:780`). The audit flagged this as the
one place an unverified signal produces a *refusal*, and warned that if the header is present on
production responses too, every Vercel-hosted production engagement trips a blocking violation at
Gate 1 — *"a gate that fires on healthy inputs gets disabled, and a disabled gate is the E1
counterfactual undone"* (`session-audit-2026-08-20.md:576-597`).

### 2.1 What was actually observed

Four ordinary unauthenticated `HEAD` requests to public marketing/documentation sites, 2026-08-20.
No target, no scope implication, no security testing. `curl -sI <url>`, response headers only.

| Host | `x-vercel-*` response headers observed |
|---|---|
| `https://vercel.com` | `x-vercel-cache: HIT`, `x-vercel-id: syd1::iad1::h9wbx-1787184354756-4e6a723e510c` |
| `https://nextjs.org` | `x-vercel-cache: HIT`, `x-vercel-id: syd1::cle1::5hf9w-1787184355147-38a40ccfdce2` |
| `https://react-tweet.vercel.app` | `x-vercel-cache: HIT`, `x-vercel-id: syd1::tqtkt-1787184361381-38534e28ab04` |
| `https://swr.vercel.app` | `x-vercel-id: syd1::r9vjw-1787184361831-70dbc75d11e1` |

**`x-vercel-deployment-url` was present on none of the four.** All four returned `server: Vercel`.
Two are custom-domain production sites; two are `*.vercel.app` production aliases.

### 2.2 What Vercel's own documentation says

Both pages fetched 2026-08-20.

- `vercel.com/docs/headers/response-headers` (page `last_updated: 2026-07-08`) enumerates the
  headers "included in Vercel deployment responses". The complete `x-vercel-*` set on that page is
  **`x-vercel-cache` and `x-vercel-id`**. `x-vercel-deployment-url` does not appear on it at all.
- `vercel.com/docs/headers/request-headers` (page `last_updated: 2025-12-13`) lists
  `x-vercel-deployment-url` under **request** headers — "The following headers are sent to each
  Vercel deployment and can be used to process the request before sending back a response. These
  headers can be read from the Request object in your Vercel Function." Its entry reads verbatim:
  *"This header represents the unique deployment, not the preview URL or production domain. For
  example, `*.vercel.app`."*

### 2.3 The finding, and its consequence

**`x-vercel-deployment-url` is a request header Vercel injects on the way *in* to the customer's
function. It is not a response header.** A black-box scanner standing outside the deployment never
observes it, on preview or on production. The research document's premise — that it is a strong
nonprod signal "present even on custom-domain requests" — is true of the *request* the function
sees and false of the *response* RedGold can read.

This is a stronger result than the audit anticipated. The audit's remedy was to narrow the signal
("header resolves to a `*.vercel.app` host **and** the request Host is also `*.vercel.app`") or to
demote it. Neither applies: **the signal is not observable at all from RedGold's vantage point, so
it must be removed from the classifier entirely, not narrowed.**

Three consequences, all binding on §4.2:

1. **Delete `x-vercel-deployment-url` from the signal table.** It is not a weak signal; it is a
   signal RedGold cannot see. Leaving it in would create a rule that can never fire, which is worse
   than a wrong rule because it reads as coverage.
2. **`server: Vercel` is not a substitute.** It was present on all four production responses. Any
   classifier keyed on Vercel *hosting* would fire on every Vercel production engagement — exactly
   the disabled-gate failure the audit predicted, arriving through the replacement signal.
3. **A request `Host` matching `*.vercel.app` remains a legitimate *contributes-only* signal**, at
   the same weight as the other hostname conventions in §4.2's table (`staging.`, `dev.`, `.ts.net`,
   RFC1918). It is a naming convention, not a platform assertion: `react-tweet.vercel.app` and
   `swr.vercel.app` are both production. It may never emit a verdict alone.

**Netlify deploy-preview headers are `[VERIFY]` and are specified conservatively.** They were not
checked in this session. Until an equivalent observation exists, they are contributes-only and may
not produce a blocking verdict, per the task constraint: do not block on an unproven signal.

### 2.4 What the discrepancy check blocks on instead

`ENVIRONMENT_DISCREPANCY` retains its **blocking** status, but only on signals whose semantics were
established. Per `session-audit-2026-08-20.md:696-701`, the blocking path ships for the four
unambiguous signals only:

> **CORRECTION, 2026-08-20, made while building release 2 — where this check runs.** An earlier
> draft of this section and of §4.2 described `ENVIRONMENT_DISCREPANCY` as firing **at Gate 1**.
> That is wrong, and it is the same defect §4.8 already records against `COVERAGE_EMPTY_PHASE`.
> Three of the four signals in the table below — a `pk_test_`/`sk_test_` prefix in a **response
> body**, a framework debug page, a dev-tool service fingerprint — require active contact with the
> asset, and under §9.7 no contact happens until *after* Gate 1 approves the plan. Sited at Gate 1
> the check fires on **0% of anything**, which §2.3 calls worse than a wrong rule because it reads
> as coverage. §4.2's own action clause was already report-time.
>
> **The two concerns are different checks that were conflated, and are now split** (§4.2, §4.8):
>
> - The **declared** `environment` is a *scope fact*. It is a required key in `scope.yaml`,
>   available at scoping time, and a missing / empty / `unknown` / unrecognised value **blocks
>   Gate 1** (`ENVIRONMENT_UNDECLARED`, `gate_cli.cmd_approve`). Fail closed for *scoring*:
>   unresolvable reads as `production`, which is the uncapped column.
> - The **discrepancy between declared and observed** is computable only once signals exist. It
>   runs where the observation lands — finding creation (`baseline_scan`) and report assembly
>   (`report.classify`) — raises a blocker in `ledger/blockers.jsonl`, and gates the affected
>   findings out of the report body per §4.2's action clause. It does **not** block Gate 1.
>
> **Signals implemented in release 2, and signals not.** `baseline_scan.env_signals()` emits
> `test_payment_key` and `dev_tool_fingerprint` — the two a black-box HTTP probe can actually see.
> **`framework_debug_page` and `nonprod_cert` are in the validator's vocabulary and no producer
> emits them**: the first needs body heuristics narrow enough not to fire on a page that merely
> mentions a framework, the second needs certificate introspection the scanner does not do. They
> are named here rather than left implicit, because a table that lists four signals and detects
> two is the same "reads as coverage" failure in miniature. The `prod-signal-present` direction —
> declared `staging`, actually production — is **not implemented at all**: its conjunction needs
> `reach`, certificate facts and observed PII, none of which any producer records yet. That
> direction is the one §4.2 calls the case that matters most, and it is unbuilt.
>
> The dev-tool fingerprint is matched in `server` / `x-powered-by` banners for all eight tools, and
> in a page `<title>` for only four of them. `vite` is deliberately excluded from title matching: a
> Vite-built SPA deployed to production commonly still ships the default `<title>Vite App</title>`,
> and a gate that fires on healthy input gets disabled.

| Signal | Blocking verdict permitted | Basis |
|---|---|---|
| Self-signed cert, or cert subject is `localhost`/RFC1918/`*.local` | `nonprod-signal-present` | `test-library-composition.md:625-627` — near-conclusive when present, silent when absent. *Except:* an internal corporate CA looks self-signed and is legitimate production, so this presents as **flag-for-review**, not a bare verdict |
| `pk_test_` / `sk_test_` payment key prefix in a response body | `nonprod-signal-present` | A vendor-defined prefix with one meaning |
| Framework-branded verbose error or debug page | `nonprod-signal-present`, **and a finding in its own right** when the environment reads as production | — |
| Dev-tool service fingerprint: Mailpit, MailHog, mailcatcher, Mailtrap, Adminer, webpack-dev-server, vite, flower | `nonprod-signal-present` | The signal that fires on the prior engagement four times over (`exploitability-severity-model.md:798-800`) |

Everything else — hostname convention (including `*.vercel.app`), ephemeral storage path (`/tmp/…`),
`[-_]dev\b` in a container or asset identifier, a published `.js.map`, `server: Vercel` — is
**contributes-only**: recorded on the asset row, printed in the report's environment section, never
a verdict on its own and never blocking.

The `prod-signal-present` direction (§4.2, the declared-`staging`-but-actually-production case) is
unaffected by this finding and keeps its conjunction unchanged.

---

## 3. Schema additions

**Additive only.** Every field in §10.1 keeps its name, type and meaning. `severity` remains the
single authoritative value `report.py` and `regen_status.py` read.

### 3.1 `scope.yaml` — new keys

| Key | Type | Vocabulary | Default | Fail-closed behaviour | Written by | Read by |
|---|---|---|---|---|---|---|
| `environment` | str, **required** | `production` \| `staging` \| `development` \| `ephemeral-preview` \| `unknown` | none — absent is not a default | Absent / empty / `unknown` / unrecognised → **`gate_cli.cmd_approve` refuses Gate 1** | operator, `new_engagement.py` | `gate_cli.py`, `baseline_scan.py`, `report.py` |
| `environment_established` | str, required when `environment` is set | `client-declared` \| `operator-owned` | none | same refusal | operator | `report.py` (banner provenance) |
| `environment_source` | str, required, **must resolve** under §10.2 | path or `path#anchor` | none | unresolvable → same refusal | operator | `report.py` |
| per-asset `environment` | str, optional override | as above | inherits top level | **narrowing only** — an asset under a `development` engagement may not be marked `production`; widening is a scope change and goes back through `/rg:new` | operator | `scope_cli.py` promotion |
| per-asset `signup_open` | bool | — | **`true`** | Unknown → `true`, the value that makes `public-account` cheapest and severity highest | operator / recon | scorer |

`unknown` is deliberately **a legal value to type and an illegal value to proceed on**
(`exploitability-severity-model.md:640-644`). Making it unrepresentable pushes an operator to guess
`production` to clear the gate, which manufactures a false client declaration. Recording `unknown`
and being stopped is honest; guessing is not.

**Where the refusal lives.** `gate_cli.cmd_approve()` (`scripts/gate_cli.py:330-358`), **not**
`scope.parse()`. `ScopeError` is DENY-by-contract (`scripts/scope.py:10-12`) and `scope.load()` is
called by `baseline_scan.scan()`, `report.render()`, `regen_status.render()` and both `gate_cli`
commands (`rg1-implementation-surface.md:86-91`), so a hard parse error blocks everything that reads
scope, including the report that would explain the refusal. `parse()` accepts the key and validates
membership; `cmd_approve` is the gate. See open decision **D-6**.

### 3.2 `assets/register.jsonl` — new per-asset fields

A CONFIRMED asset without these **fails promotion** rather than defaulting
(`exploitability-severity-model.md:1436-1439`).

| Field | Vocabulary | Fail-closed |
|---|---|---|
| `reach` | `internet` (0) \| `adjacent-untrusted` (1) \| `adjacent-trusted` (2) \| `host-local` (3) \| `physical` (4) | unknown/missing → **`internet`** (rank 0, maximum severity delta) |
| `environment` | as §3.1 | unresolvable to any environment → **`production`**, no cap. Cited precedent, not invented: SSVC System Exposure 1.0.1, assume `Open` when the level cannot be determined |
| `signup_open` | bool | → `true` |
| `reachable_population` | `{description, count, established_by}`; `established_by` ∈ `enumerated` \| `client-declared` \| `unestablished` | → `unestablished`, which demotes `reach` one rank toward `adjacent-untrusted` — **raising** severity |
| `env_signals` | list of contributes-only observations from §2.4 | empty list |

`reach` is a property of the **asset**, not of the finding, resolved once during recon
(`exploitability-severity-model.md:373-378`). A finding inherits it. That is what stops each finding
relitigating reach in prose — which is how *"any host that can reach TCP 6379"* got written four
times without ever being answered.

### 3.3 Finding record — new fields

| Field | Type | Vocabulary | Required on | Default / fail-closed |
|---|---|---|---|---|
| `environment_at_test` | str | §3.1 vocabulary minus `unknown` | **all classes** | **`production`** (SSVC precedent). Stamped from the asset **at write time, never recomputed** — the environment at the moment of the test is a fact about the test |
| `precondition` | object | `{reach, capability, subject, data, established_by}` | `technical` above `low` (required); at/below `low` (recommended); `posture`/`governance`/`compliance` **not applicable** | see §3.4 — two different defaults for the same unknown |
| `grants` | object | `{capability, subject, data, scope_change[]}` | `technical` above `low` — **required, blocking** | **no default exists.** Missing → blocking; present-but-unrecognised value → blocking |
| `dominated_by` | str \| null | a finding id | when `precondition.established_by == demonstrated` **and** `precondition.capability` rank > 0 | null |
| `production_nexus` | object \| null | `{kind, evidence_ptr}`; `kind` ∈ `live_credential` \| `production_data` \| `shared_infrastructure` \| `code_defect` \| `same_artifact` | required when `environment_at_test != production` and severity exceeds the cap | unrecognised `kind` → **treated as present (cap bypassed, severity higher) AND blocking** — the disclosing direction and the correctness direction differ, and we take both |
| `reachable_population` | object | inherited from the asset row | `technical` above `low` | `established_by: unestablished` |
| `verified_by` | str | agent name | `technical` above `low` | absent / empty / `== discovered_by` → **demote severity to `low`** |
| `impact_demonstrated` | bool | — | — | `false` |
| `severity_derivation` | object | see §3.5 | **all classes** (identity for `posture`/`governance`) | written by the scorer, **never by an agent** |
| `cvss_v4_vector` | str | CVSS v4.0 vector | `technical` above `low` | malformed → **non-blocking**. Interchange only; nothing computes on it |
| `attack_refs` | list[str] | ATT&CK ids | never | `[]`. **Never computed on** — ATT&CK tactics are not totally ordered and the tactic set changed under a stable name this year |
| `routes_tested`, `credentials_tested`, `scope_of_conclusion` | list, list, str | — | `info` `technical` records whose text asserts a capability-level negative (§8.5) | blocking when the lint matches and they are absent |

Two vocabularies referenced above, both closed, both versioned by `model_version`:

- `capability` (Axis B, used identically by `precondition` and `grants` — that identity is what makes
  the comparison a rank comparison rather than an essay):
  `none` 0 · `public-account` 1 · `tenant-user` 2 · `elevated-app-role` 3 · `env-secret-read` 4 ·
  `host-fs-read` 5 · `host-code-exec` 6 · `host-root` 7.
- `data`: `none` 0 · `own` 1 · `tenant` 2 · `all` 3.
- `scope_change` entries: `lateral` · `persistence` · `evasion` · `amplification`, each with a
  required evidence-bearing companion field (`scope_change_target` / `survives` / `control_degraded`
  / `amplification_factor` — a denominator, not an adjective). An agent may **not** invent a fifth;
  it records `scope_change_proposed: "<text>"`, which does not defeat domination and raises
  non-blocking `NEW_SCOPE_CHANGE_KIND` routed to the reviewer and `/rg:harvest`.
- `precondition.established_by`: `demonstrated` · `scope-declared` · `client-declared` (all three
  permit domination) · `asserted` · `unestablished` (neither permits it).

**`env-secret-read` (4) outranks `elevated-app-role` (3)** because reading every message an
environment sends yields the reset and magic-link token for every account including every staff
account — it contains app-admin as a consequence. This rung exists because one engagement had a mail
catcher; it is shaped by that one engagement and the vocabulary is versioned for exactly that reason
(`exploitability-severity-model.md:1264-1267`).

**`docker`-group membership maps to `host-root` (7), not `host-code-exec` (6)** — and this mapping
carries a `[VERIFY]` marker **in the body, not only in an appendix**, per
`session-audit-2026-08-20.md:756`. The reasoning is sound; the primary source was never fetched. See
§11.2 for the bar this imposes.

### 3.4 Fail-closed, stated as a direction

The rule this project already has: an unknown or missing `severity` string must never read as
low-severity (`scripts/report.py:71-84`, which documents *"Fails closed on an unrecognised or missing
severity"*). It was paid for by a real incident — an unrecognised string, `"Critical!!"`, passing a
membership test on 2026-08-04. The new fields inherit it, and inheriting it correctly requires
stating something the original never had to:

> **"Fail closed" names a direction, not a value, and the direction is always "the one that does not
> reduce what the client is told". A field feeding two rules that cut opposite ways therefore takes
> two different defaults from the same unknown input.**

`precondition` is exactly such a field, and this is the one the task asked to be worked out and
justified:

| Rule consuming it | What it does with a weaker precondition | Safe direction | Behaviour on unknown / missing / unrecognised |
|---|---|---|---|
| §4.7 exploitability delta | A **weaker** precondition **raises** severity | Assume the **weakest** precondition | Score as `reach: internet`, `capability: none` — the maximum |
| §4.3 domination | A **stronger** precondition **lowers** severity to `info` | Do not fire | `established_by` defaults to `unestablished`, which is not one of the three permitted values, so Brake 1 makes the rule **inert** |

So an unknown precondition produces a finding **scored at its maximum and immune to suppression**,
plus a blocking `PRECONDITION_UNDECLARED` on any `technical` finding above `low`. The record cannot
reach the report body without being answered, and while it is unanswered it is loud rather than
quiet. That is the safe direction, and it is safe in both of the two senses that matter: it does not
shrink the client's disclosure, and it does not hand an agent a way to make a finding disappear by
declining to fill a field in.

`grants` is different and **blocks rather than defaulting**. There is no safe default for *what does
this give the attacker*: defaulting it low suppresses, defaulting it high fabricates an impact claim
that §10.4 gate 3 and §20.5 both forbid.

**Implementation rule, applying everywhere:** no rank or band lookup uses `dict.get(value, default)`.
Every lookup is an explicit membership test followed by an indexed read, with the unknown branch
written out. A defaulting `.get` is how an unknown string silently becomes rank 0, and rank 0 on
`grants` is a silent suppression. `report.py` re-checks membership itself rather than trusting the
validator hook to have rejected bad input — trusting an upstream validator is this project's
recurring third-instance failure and must not become the fourth.

### 3.5 The complete record, new fields in place

Field order preserved from §10.1; new fields grouped after the settled ones. This is F-107 as it
would be written under RG-1 — the finding the prior engagement rated `critical`.

```json
{
  "id": "F-107",
  "asset_id": "A-004",
  "asset": "http://host.example.ts.net:8025",
  "title": "Magic-link token readable from the environment's mail catcher",
  "finding_class": "technical",
  "obligation_refs": [],
  "data_classes": [],
  "notifiable_assessment": "not_assessed",
  "status": "PROVEN",
  "verified": "executed",
  "confidence": "confirmed",
  "evidence_ptr": "evidence/F-107-magic-link.http",
  "severity": "info",
  "likelihood": null,
  "real_world_impact": "…",
  "tested_at_tier": 1,
  "gate_ref": "G-002",
  "playbook_ref": null,
  "standard_refs": [],
  "remediation": "…",
  "cost_tier": "$",
  "cleanup_required": false,
  "discovered_by": "rg-webtest",
  "verified_by": "rg-verify",
  "created": "2026-08-05T01:20:00Z",

  "environment_at_test": "development",
  "production_nexus": null,

  "precondition": {
    "reach": "adjacent-trusted",
    "capability": "env-secret-read",
    "subject": "asset:A-004",
    "data": "all",
    "established_by": "demonstrated"
  },
  "grants": {
    "capability": "tenant-user",
    "subject": "asset:A-004",
    "data": "tenant",
    "scope_change": []
  },
  "dominated_by": "F-103",

  "reachable_population": {
    "description": "hosts on <tailnet>.ts.net",
    "count": null,
    "established_by": "unestablished"
  },

  "impact_demonstrated": false,
  "cvss_v4_vector": "CVSS:4.0/AV:A/AC:L/AT:N/PR:N/UI:N/VC:H/VI:N/VA:N/SC:N/SI:N/SA:N",
  "attack_refs": [],

  "severity_derivation": {
    "model_version": "rg-sev/1",
    "grant_band": "medium",
    "delta": -1,
    "modifier": 0,
    "base": "low",
    "after_domination": "info",
    "env_cap_applied": false,
    "after_env_cap": "info",
    "after_review": "info",
    "dominated_by": "F-103",
    "labels": ["PRECONDITION-INVERTED"]
  },
  "review_ptr": "findings/review.jsonl#F-107"
}
```

`severity_derivation` is the audit trail and is what makes the disposition reproducible from the
record alone. A record whose `severity` does not equal its `severity_derivation.after_review` is a
blocking `DERIVATION_MISMATCH` — that is how a hand-edited severity gets caught.

---

## 4. The mechanical rules

**Order is part of the specification, not an implementation detail.** The autopsy's deepest
structural complaint is that these steps were never sequenced.

```
0. ASSET RESOLUTION   reach, environment, signup_open, reachable_population → assets/register.jsonl
                      the DECLARATION is checked at Gate 1 (ENVIRONMENT_UNDECLARED, §3.1);
                      the DISCREPANCY cannot be computed here — no contact has happened (§4.2)
1. APPLICABILITY      scheme/protocol filter — is this check meaningful on this asset (§4.1)
2. BASE SEVERITY      grant band + exploitability delta + one modifier               (§4.7)
3. DOMINATION         dominated() → cap info, label PRECONDITION-INVERTED            (§4.3)
4. ENVIRONMENT CAP    min(severity, cap[environment]) unless production_nexus        (§6)
5. VERIFICATION GATE  §10.3 unchanged, plus verified_by != discovered_by             (§4.5)
6. REVIEWER MERGE     min(severity, review.severity_recommendation)                  (§7.4)
7. REPORT             body / dominated / open-questions / coverage-gaps
                      ENVIRONMENT_DISCREPANCY gates the affected findings out here   (§4.2)
```

**Global invariant: no step after step 2 can raise a severity.** Testable in one assertion over
`severity_derivation`. It is what makes the pipeline safe to compose — whatever else goes wrong, it
cannot inflate. The corresponding honest cost is stated once here and paid for in §8: *a
monotone-decreasing pipeline is a machine for producing false negatives.*

Each rule below is stated as **input read → comparison performed → action on failure.**

### 4.1 Applicability filter (autopsy E2) — pipeline step 1

**Two sub-rules.**

**(a) HSTS on a plaintext origin.**
*Input:* `urlsplit(base).scheme` for the asset under test.
*Comparison:* is the `strict-transport-security` entry of the `SECURITY_HEADERS` loop
(`scripts/baseline_scan.py:402-417`) about to be evaluated against `scheme == "http"`?
*Action:* **skip the check and record nothing as a finding.** Write one `coverage.jsonl` row with
`outcome: not_applicable`. HSTS served over plaintext is ignored by user agents; asking a plain-HTTP
origin to set it is a category error, and the impact string it generates — *"a downgrade to
plaintext is not prevented"* — contradicts itself on a connection that is already plaintext
(`prior-engagement-autopsy.md:219-231`). Kills F-046 and F-058 outright.

**(b) One coverage record per dead asset, not per (check × dead asset).**
*Input:* the outcome of the **first** probe against each asset.
*Comparison:* did it return a non-HTTP protocol error?
*Action:* stop probing that asset and emit **one** `not_applicable` record naming all skipped checks,
instead of one per check. The `for check in CHECKS:` loop at `scripts/baseline_scan.py:390-400` and
the `SECURITY_HEADERS` loop at `:402-417` both short-circuit; the `applicable=False` branch of
`make_finding()` (`:202-225`) moves outside both loops. Collapses 36 records into 3.

*Do this before threading `environment` through the same loop* (`rg1-implementation-surface.md:460-465`)
— do not add environment-awareness to code about to be rewritten.

### 4.2 `ENVIRONMENT_DISCREPANCY` — at the observation, blocking

**Two checks, not one. The split is the correction recorded at §2.4 and generalised at §4.8.**

| | Where the input exists | Where the check runs | What it does |
|---|---|---|---|
| **(a) The declaration** — is there a usable `environment`? | `scope.yaml`, from the moment the boundary is written | `gate_cli.cmd_approve` (Gate 1) | `ENVIRONMENT_UNDECLARED`, blocking. §3.1 |
| **(b) The discrepancy** — does the asset contradict it? | only after a request has been made (§9.7 puts that after Gate 1) | finding creation (`baseline_scan.scan`) and report assembly (`report.classify`) | `ENVIRONMENT_DISCREPANCY`, blocking; a blocker row; the affected findings do not enter the report body |

The §4.8 test applied to each — *name a healthy engagement state at which this fires*:

- **(a)** none. Every healthy engagement has written `scope.yaml` before it asks to approve a plan.
- **(b)** an engagement declared `production` whose asset returns a test-mode payment key or
  answers as a mail catcher. That state exists only after contact — which is precisely why the
  check cannot be sited at Gate 1, where the answer is "none, on either the healthy or the
  unhealthy side, because the input does not exist yet".

*Input:* declared `environment_at_test` on the record (stamped from the asset row, else
`scope.yaml`); the record's `env_signals`, written by whatever made contact.
*Comparison:*

| Classifier verdict | Declared `production` | Declared `staging`/`development`/`ephemeral-preview` |
|---|---|---|
| `nonprod-signal-present` (one of §2.4's four blocking signals) | **`ENVIRONMENT_DISCREPANCY`, blocking** | consistent; record the signals |
| `prod-signal-present` | consistent | **`ENVIRONMENT_DISCREPANCY`, blocking** — the case that matters most, because it is the one where the cap suppresses real risk |
| `no-signal`, or contributes-only signals only | accepted | accepted, and the report states that the declaration is the only support |

`prod-signal-present` requires a **conjunction**, never one signal: `reach: internet` **plus at least
one** of a publicly-resolving CA-issued cert on a registered apex domain; a live payment key prefix
(`pk_live_`/`sk_live_`); non-synthetic PII or real user-generated content observed in a response; a
production-shaped analytics or error-reporting endpoint.

*Action on failure:* the affected findings do not enter the report body until the discrepancy is
resolved by a **recorded operator decision naming which side was wrong**. The classifier never sets
`environment`; it only contradicts a declaration.

**As built (release 2).** The decision is a closed two-value vocabulary on the record —
`environment_discrepancy_resolution: {decision: declaration_wrong | signal_wrong, reason, by}` —
and an unrecognised `decision`, or an empty `reason`, does not clear the violation. A free-text
resolution would absorb any sentence an agent wanted to write, which is FM-5's shape. The scanner
additionally appends **one blocker per contradicted asset** (not one per finding) to
`ledger/blockers.jsonl`, so the operator sees it in `gate_cli.py blockers` and closes it through
the existing Gate 2 path. The report renders held-back records in their own section naming the
signal observed — a suppression the client cannot see is a suppression the client cannot audit.

An **unrecognised** signal kind raises non-blocking `ENVIRONMENT_SIGNAL_UNRECOGNISED` and produces
no verdict. A rule that can fire on a value nobody defined is a rule with no meaning.

**Reconciling the two halves of the research document.** `exploitability-severity-model.md:762-765`
says the classifier "can never confidently emit `production`"; `:773-775` and `:847-853` define a
`prod-signal-present` verdict that concludes toward production. These are not in conflict once
stated in one sentence, which the source never does (`session-audit-2026-08-20.md:355-366`):
**the classifier may never *set* `environment`, and it may *contradict* a declaration in either
direction.** Setting requires a positive conclusion from silence-when-absent signals, which is
unsound; contradicting requires only that a declared value and an observed conjunction disagree,
which is sound. An implementer reading §3.5 alone would build only half of this.

**Reachability does not feed the classifier.** If `reach == internet` implied
`environment == production`, then "an internet-exposed development environment" becomes
unrepresentable — the finding consumes its own subject. Instead exposure has three separate
consumers: it sets `reach` (§4.7), it emits `NONPROD_INTERNET_EXPOSED` as its own `high` `posture`
finding when `environment_at_test != production` **and** `reach == internet` (exempt from the
environment cap, because capping a finding *about* the environment *by* the environment is circular),
and it contributes one term to the `prod-signal-present` conjunction above.

### 4.3 Domination (autopsy E6 / FM-6) — pipeline step 3

*Input:* `precondition` and `grants` off **one** record.
*Comparison:*

```python
def dominated(record) -> bool:
    """True when the attacker already holds everything this finding would give them."""
    pre, grant = record["precondition"], record["grants"]
    if grant.get("scope_change"):                       # 1. a scope change is a real gain
        return False
    if DATA_RANK[grant["data"]] > DATA_RANK[pre["data"]]:   # 2. new data reach is a real gain
        return False
    if grant["subject"] != pre["subject"]:              # 3. different subject = lateral
        return False
    return CAPABILITY_RANK[grant["capability"]] <= CAPABILITY_RANK[pre["capability"]]  # 4.
```

*Action when true and all four brakes clear:* severity is **capped at `info`**, the record is
labelled `PRECONDITION-INVERTED`, and it moves to a report subsection titled *Findings already
implied by a more serious finding*, cross-referenced to its dominator, keeping its evidence pointer.
**The record is never deleted and never dropped from the document.** A validator test asserts this,
because the natural implementation is a filter and the natural filter loses it.

**The four brakes** — these are what stop the rule deleting real findings, and they are the reason
this is safe to ship:

1. **The precondition must have been *established*, not asserted.** `established_by` ∈
   `{asserted, unestablished}` makes `dominated()` inert and raises non-blocking
   `PRECONDITION_UNPROVEN`, routing the finding to open questions **at its computed severity**.
   *This is the single most important line in the design.* Without it, any finding an agent wanted
   to make disappear could be made to disappear by claiming a strong precondition — the judgement
   escape hatch the autopsy's E6 warned about (`prior-engagement-autopsy.md:658-660`).
2. **The data axis.** An IDOR grants no new privilege rung and is the finding most likely to be
   wrongly suppressed. `DATA_RANK` growth defeats domination on its own. This brake exists
   specifically to stop the rule destroying the entire IDOR/BOLA family.
3. **Domination caps; it never deletes.**
4. **The rule is measured.** Every firing appends to `ledger/suppression.jsonl`
   (`{finding_id, rule, inputs, dominating_finding, model_version, at}`), and the suppression rate
   per engagement is a reported number in `status.md`. A rule that fires on 60% of findings is a
   rule that is wrong, and counting is the only way to know.

**There is deliberately no override boolean.** All four brakes are structural — they turn on facts
about other records or declared vocabulary. A free-text override would be used, would be used a lot,
and would be used most on exactly the findings that most needed the rule.

`DOMINATION_UNSUPPORTED` (blocking): `dominated_by` names a finding whose `grants` do not meet the
claimed precondition. This is the mechanised, blocking form of the existing `ROLLUP` rule
(`scripts/findings.py:418-429`), which today fires with `blocking=False` and does nothing.

### 4.4 `REACH_UNENUMERATED` (FM-8)

*Input:* `reach` and `reachable_population.established_by` on the asset row.
*Comparison:* is `reach == adjacent-trusted` with `established_by == unestablished`?
*Action:* non-blocking `REACH_UNENUMERATED`, and `reach` is **demoted one rank** toward
`adjacent-untrusted` for scoring — which **raises** severity. An overlay whose membership nobody has
counted is not demonstrably controlled. This is FM-8 made mechanical: the intensifier *"anyone"* now
costs a rank until someone writes down who.

### 4.5 `VERIFIED_BY_SELF` (autopsy E3 / FM-3) — pipeline step 5

*Input:* `finding_class`, `severity`, `verified_by`, `discovered_by`.
*Comparison:* `finding_class == "technical"` and `severity in ABOVE_LOW` and (`verified_by` absent,
empty, or `== discovered_by`).
*Action:* **blocking violation that demotes severity to `low`** — following `EVIDENCE_UNRESOLVED`'s
precedent (`scripts/findings.py:258-263`), which demotes rather than warns because *"a warning about
an unproven claim is exactly the thing that gets ignored under time pressure"* (`:56-58`).

**Demote `severity`; do not fabricate a `verified` value.** `report.needs_verification()`
(`scripts/report.py:71-84`) tests `severity in ABOVE_LOW`, so demoting severity naturally stops
routing the now-`low` record into the unverified bucket. Rewriting `verified` instead would compose
badly and would also be a lie about what was executed.

**Paired change:** `scripts/baseline_scan.py:233` must stop writing `"verified": "executed"` on its
own output. Today it writes `executed` on any `present=True` check, which is why
`UNVERIFIED_ABOVE_LOW` (`scripts/findings.py:274-280`) is **structurally unreachable from the
baseline producer** — the rule is satisfied by the exact thing it exists to catch
(`session-audit-2026-08-20.md:40-48`). A scanner observation is `verified: "none"` until `rg-verify`
re-runs it. This correctly parks every future high-severity baseline hit at `low`, which is the
intended behaviour and was not happening.

**§10.3 survives intact.** *"No `technical` finding above Low reaches a client without `replayed` or
`executed`"* runs at step 5, after every severity transform in this document, and it is a gate on
**disclosure** rather than a severity transform, so nothing here routes around it. Two compatibility
notes: (i) the new fields can only lower severity, so a record caught by `UNVERIFIED_ABOVE_LOW`
before is still caught or is now below Low and moot — coverage strictly increases; (ii) the gate
must read **`severity`, not `severity_derivation.base`**, or a record scored `critical` and capped
to `medium` in development would be gated on its base value. Assert this in a test, because the
tempting implementation reads the base.

### 4.6 `IMPACT_NOT_EXECUTED` (autopsy E5 / FM-5)

*Input:* `real_world_impact` and `verified` on any record at `high` or `critical`.
*Comparison:* does the impact string contain any of the non-execution markers — `not tested`,
`not attempted`, `not exercised`, `was not`, `reasoned from`, `well-known path`, `would allow`,
`could also`, `not proven`? Every one of these appears **verbatim** in F-101 or F-107
(`findings/webtest.json:12, 114`).
*Action:* **non-blocking** violation routing the record into `report.py`'s open-questions section
rather than the findings body — **unless** the record carries `impact_demonstrated: true` with its
own resolving `evidence_ptr` for the impact step specifically, not the primitive step.

Its whole value is that the disclaimer is *already in the record* and nothing reads it. The honesty
was present; the transport was missing.

*Implementation note:* `IMPACT_NOT_EXECUTED` must be added to `report.classify()`'s
`VERIFICATION_CODES` set (`scripts/report.py:58-60`) or the record is silently dropped by the
`blocking_codes - VERIFICATION_CODES` check at `:131-133`.

### 4.7 Scoring — pipeline step 2

*Input:* `grants` (band), `precondition` (delta), one modifier.
*Comparison:*

`grant_band = max(capability_band, data_band)`, where capability bands are
`none`→info, `public-account`→low, `tenant-user`→medium, `elevated-app-role`/`env-secret-read`/`host-fs-read`→high,
`host-code-exec`/`host-root`→critical; and data bands are `none`→info, `own`→low, `tenant`/`all`→high.

`delta` = sum of: reach (`internet` +1, `adjacent-untrusted` 0, `adjacent-trusted` −1, `host-local`
−2, `physical` −2) and capability (`none` 0, `public-account` 0 if `signup_open` else −1,
`tenant-user` −1, `elevated-app-role`/`env-secret-read` −1, `host-fs-read`/`host-code-exec`/`host-root`
−2), clamped to [−2, +1].

`modifier` = **at most one band, take the strongest, never stack**: `data_classes` includes
`personal_information`/`financial`/`health`/`credentials` **and** `grants.data == all` → +1;
`scope_change` includes `persistence` → +1; includes `evasion` → +1; asset in `crown_jewels` → +1.

`base_severity = clamp(SEVERITIES[index(grant_band) + delta + modifier], info, critical)`.

Non-stacking is a blunt choice and is recorded as one (`exploitability-severity-model.md:1266-1269`):
a crown-jewel asset holding financial data with a persistence-granting bug gets one +1, not three. A
blunt rule that is understood beats a nuanced one that is not. Revisit after two engagements.

**The `info` row is not a rounding artefact.** A finding that grants nothing is `info` from every
starting position, and that row alone is the correct disposition of F-005 — the response body is
site title, description, accent colour, locale, url, version and `site_uuid`
(`evidence/F-005-ghost_admin_open.http:16`), fetched by the unauthenticated admin login page by
design.

### 4.8 New validator codes, complete

Added to `scripts/findings.py`, following the existing code convention.

| Code | Fires when | Blocking | Effect on severity |
|---|---|---|---|
| `ENVIRONMENT_UNDECLARED` | `scope.yaml` has no usable `environment` — absent, empty, `unknown` or unrecognised | yes (at **Gate 1**, `gate_cli.cmd_approve`) | — |
| `ENVIRONMENT_DISCREPANCY` | a §2.4 blocking signal on the record contradicts its `environment_at_test` (§4.2) | yes (at **finding creation and report assembly** — *never* at Gate 1, where the input cannot exist) | — |
| `ENVIRONMENT_SIGNAL_UNRECOGNISED` | an `env_signals` entry names a kind outside the closed vocabulary | no | — |
| `PRODUCTION_NEXUS_UNRECOGNISED` | `production_nexus.kind` is not one of the five (§6.4) | yes — **and the cap is bypassed**, the two directions taken together | — |
| `PRODUCTION_NEXUS_UNRESOLVED` | the nexus carries no `evidence_ptr`, or one that does not resolve | yes | — |
| `DERIVATION_MISMATCH` (env-cap form) | `severity != severity_derivation.after_env_cap` | yes | — |
| `PRECONDITION_UNDECLARED` | `technical` above `low` with no `precondition` | yes | — |
| `PRECONDITION_UNPROVEN` | `established_by` ∈ `{asserted, unestablished}` on a record claiming domination | no | routes to open questions at computed severity |
| `GRANTS_UNDECLARED` | `technical` above `low` with `grants` missing, or an unrecognised value inside it | yes | — |
| `PRECONDITION_INVERTED` | `dominated()` true and brakes clear | no | caps to `info`, keeps record in document |
| `DOMINATION_UNSUPPORTED` | `dominated_by` names a finding whose `grants` do not meet the precondition | yes | — |
| `REACH_UNENUMERATED` | `adjacent-trusted` with `established_by: unestablished` | no | demotes reach one rank — **raises** severity |
| `VERIFIED_BY_SELF` | `technical` above `low`, `verified_by` absent/empty/`== discovered_by` | yes | demotes to `low` |
| `IMPACT_NOT_EXECUTED` | above-`low`, impact matches the marker list, no `impact_demonstrated` + own evidence | no | routes to open questions |
| `DERIVATION_MISMATCH` | `severity != severity_derivation.after_review` | yes | — |
| `NO_REVIEW_VERDICT` | `technical` above `low` with no row in `findings/review.jsonl` | no | excludes from report body → coverage gaps |
| `NEW_SCOPE_CHANGE_KIND` | `scope_change_proposed` present | no | — → §7.5 |
| `GRANT_AXIS_GAP` | §5.4 — the grant is real but neither axis models it | no | — → §7.5 |
| `COVERAGE_EMPTY_PHASE` | §8.2 zero-zero | yes (at `gate_cli.py complete --phase`, **phase completion**) | — |
| `REPORT_STALE` | deliverable mtime precedes the newest finding | yes (at `report.py --check`, and at `gate_cli.py close`) | — |
| `PHASE_NEVER_COMPLETED` | engagement close with no `phase.complete` row in `ledger/activity.jsonl` | yes (at `gate_cli.py close`) | — |
| `UNJOINED_CHAIN` | §8.4 graph match | yes | — *(deferred, see §9)* |

**On the enforcement site of `COVERAGE_EMPTY_PHASE`, stated because an earlier draft of this
document got it wrong in both directions.** The rule fires at **phase completion**, never at
`cmd_approve`. `cmd_approve` is Gate 1 plan approval, which by §9.7 runs *before any testing* — at
that moment every healthy engagement has zero findings and zero coverage records, so a zero-zero
check sited there fires on **100% of healthy inputs**. That is the disabled-gate failure mode §2.3
and D-4 exist to prevent, reproduced inside this document's own build table. The general rule the
mistake illustrates: **a control must be sited at a lifecycle point later than the earliest moment
its input can exist, and the check is "name a healthy engagement state at which this fires."**

**The rule caught a second instance of itself, in this document, before release 2 shipped.**
`ENVIRONMENT_DISCREPANCY` was specced at Gate 1 in §2 and §4.2's original heading, while §4.2's
action clause was already report-time. Three of its four blocking signals need contact with the
asset, and §9.7 puts all contact after Gate 1 — so the Gate 1 siting fires on 0% of engagements,
healthy or otherwise. The fix is the one this rule prescribes: **split the check at the point where
its two inputs become available at different times.** The declaration is a scope fact and stays at
Gate 1; the contradiction is an observation and moves to where observations land. §2.4 and §4.2
record the corrected form.

Two corollaries worth stating, because both were reached while applying the test to every rule in
release 2:

1. **The test has two answers, not one, and both matter.** *"Name a healthy state at which this
   fires"* catches a gate sited too early (it fires on everything). *"Name any state at which this
   fires"* catches a gate sited before its input exists (it fires on nothing). `COVERAGE_EMPTY_PHASE`
   at `cmd_approve` failed the first; `ENVIRONMENT_DISCREPANCY` at Gate 1 failed the second. A rule
   that passes both is one whose input exists and whose healthy case is quiet.
2. **A transform is not a gate, and the test applies differently.** The environment cap (§6) fires
   on every non-production finding — 100% of a healthy engagement's corpus — and that is correct,
   because it refuses nothing and blocks no work. The disabled-gate failure is a property of
   *refusals*, not of *severity transforms*. What a transform owes instead is a recorded derivation,
   which §6.4 requires and which `DERIVATION_MISMATCH` enforces.

**`PHASE_NEVER_COMPLETED` is what makes `COVERAGE_EMPTY_PHASE` bind.** The zero-zero rule refuses a
phase that is completed empty; it says nothing about a phase that is never completed at all, and an
operator who simply never runs `complete` is stopped by nothing. Requiring at least one recorded
`phase.complete` before an engagement may close is the cheapest thing that converts the phase gate
from opt-in into a precondition of closure. See §9.1a for why this is a command and not a hook.

---

## 5. The scanner-findings interface — **PROVISIONAL (P-2)**

> **PROVISIONAL — awaiting operator sign-off.** This is the largest genuine gap in the research and
> the audit ranks it second (`session-audit-2026-08-20.md:516-537`). The severity model requires
> `precondition` and `grants` on every `technical` finding above `low` and both are **agent
> declarations**; a `grep -in 'fuzz|nuclei|DAST|scanner output'` over that document returns **zero
> matches** (`:305-307`). `baseline_scan.py` has 12 checks that produce findings mechanically with no
> agent in the loop. Until this is settled, `validate_record()` cannot require the fields, and a
> requirement that is conditional-on-nothing is not a requirement. **This blocks RG-1's schema and
> blocks RG-3 entirely.**

### 5.1 The three options, and the one recommended

| Option | What it means | Why not / why |
|---|---|---|
| A. Scanner findings capped at `low` by construction | Defensible, and roughly what E3 + "stop self-certifying" already achieves — but then RG-3's pinned libraries can **never** produce an above-Low finding without a subsequent agent pass, which is a significant product statement |
| B. A static per-check mapping table | Cheap for `baseline_scan.py`'s 12 checks; **unbounded** for nuclei's template corpus |
| C. An agent post-processes every scanner record | Reintroduces exactly the judgement the pinned libraries were adopted to remove |

**Recommendation: A **and** B together, and it is not a compromise — they answer two different
questions.**

- **B supplies the fields.** Without a static table, `GRANTS_UNDECLARED` fires on every scanner
  record, or the field is quietly optional and the whole dominance mechanism becomes advisory. The
  table also gives `chain_scan.py` (§8.4) the graph edges it needs; a check with no declared grant
  has no edges and participates in no chain.
- **A supplies the ceiling, and it is already implied.** §4.5's `VERIFIED_BY_SELF` demotes any
  `technical` finding above `low` whose `verified_by` is absent or equals `discovered_by`. Baseline
  records have no `verified_by` and never will until `rg-verify` re-runs them. So scanner output is
  already capped at `low` by an existing rule. **Stating the cap explicitly is what stops two
  mechanisms silently disagreeing later** — and it makes the product statement in option A something
  the operator signs rather than something that emerges.

The static values are therefore **floors, not verdicts**. `rg-verify` may propose a record-specific
`grants` from the observed response through §7's challenge path; nothing else may overwrite them.

### 5.2 The table — 9 endpoint checks

Precondition is uniform across all nine and is not a judgement call: the scanner made an
unauthenticated request from wherever the asset sits and observed the response.

```json
"precondition": {
  "reach": "<inherited from assets/register.jsonl>",
  "capability": "none",
  "subject": "asset:<asset_id>",
  "data": "none",
  "established_by": "demonstrated"
}
```

`established_by: demonstrated` is honest here and does **not** require a `dominated_by`: rank 0
requires nothing to hold, so `DOMINATION_UNSUPPORTED` only checks `dominated_by` when
`precondition.capability` rank > 0 (§3.3).

`grants`, per check. `Check` (`scripts/baseline_scan.py:78-87`) gains three fields: `grants`,
`grant_evidence`, and `discloses`.

| # | `key` | path | severity today | `grants.capability` | `grants.data` | band | `grant_evidence` |
|---|---|---|---|---|---|---|---|
| 1 | `env_exposed` | `/.env` | critical | `env-secret-read` | `all` | high (→ critical with `credentials` in `data_classes`) | `content_shaped` |
| 2 | `git_exposed` | `/.git/config` | high | `none` | `none` | info | `content_shaped`, **`discloses: source`** — see §5.4 |
| 3 | `dir_listing` | `/` | low | `none` | `none` | info | `content_shaped` |
| 4 | `admin_open` | `/admin` | critical | `none` | `none` | info | **`status_only`** — see §5.3 |
| 5 | `ghost_admin_open` | `/ghost/api/admin/site/` | high | `none` | `none` | info | **`status_only`** |
| 6 | `actuator_open` | `/actuator/env` | high | `none` | `none` | info | **`status_only`** |
| 7 | `bucket_public` | `/storage/v1/object/list/public` | high | `none` | `all` | high | `content_shaped` |
| 8 | `sourcemap` | `/static/js/main.js.map` | low | `none` | `none` | info | `content_shaped`, **`discloses: source`** |
| 9 | `wildcard_cors` | `/` | high | `none` | `own` | low | `content_shaped` |

Notes on the four that are not obvious:

- **1 `env_exposed`** — the detector is content-shaped (`^[A-Z_]{3,}=\S`, `scripts/baseline_scan.py:89-90`),
  so a hit really is environment content. `env-secret-read` / `all` is the correct rung and the
  static assignment is sound. This is the one baseline check that legitimately reaches `critical`.
- **7 `bucket_public`** — the detector parses JSON and tests for object-entry keys
  (`:105-121`), so a hit is a real listing. `capability: none` / `data: all` bands `high`. The
  honest boundary: listing object *metadata* is not reading object *bodies*. This is the assignment
  most worth a reviewer challenge and it is flagged as such rather than tuned.
- **9 `wildcard_cors`** — the detector is precise (`ACAO: *` **and** `ACAC: true`, `:127-131`). What
  it grants depends on what the credentialed endpoints return, which is unknowable statically — but
  `data: own` is exactly right and not a fudge: the attacker gains cross-origin read of *the
  victim's own* authenticated responses. Bands `low`.
- **5 `ghost_admin_open`** — F-005. Bands `info`, which is the autopsy's adjudicated answer
  (`prior-engagement-autopsy.md:149-174`) and what `rg-verify` recommended and had discarded.

### 5.3 Fallback (a) — checks whose predicate reads only `probe.status`

Checks 4, 5 and 6 use `_admin_reachable`, which is `return probe.status == 200` and nothing else
(`scripts/baseline_scan.py:104-106`). This is FM-2 verbatim.

**Rule:** *a check whose `detect` predicate reads only `probe.status` may not declare a `grants`
above `{capability: none, data: none}`.* Declared as `grant_evidence: status_only` on the `Check`
definition, mechanically enforced by an assertion over `CHECKS` at import time.

This is the autopsy's own formulation made structural: *"a check whose only predicate is
`status == 200` cannot distinguish 'endpoint exists' from 'endpoint leaks', and therefore must not
be allowed to emit above `low` on its own. That rule is a one-line property of the check definition,
not of the response"* (`prior-engagement-autopsy.md:351-355`).

**The escape is not a bypass, it is a different producer.** A record-specific `grants` may be
supplied by an agent that read the response body — `rg-webtest` or `rg-verify` — in which case
`discovered_by`/`verified_by` differ, §4.5 does not demote, and the finding can exceed `low` on its
merits. The static floor constrains the *scanner*, not the finding.

**A better detector also lifts the floor.** `actuator_open` in particular could carry
`env-secret-read` / `all` if its predicate tested for Spring Boot's `{"activeProfiles":…,"propertySources":[…]}`
shape rather than a bare 200. That is a check-definition improvement, tracked as RG-3 work, not a
schema question. Until then it declares `status_only` and bands `info`.

### 5.4 Fallback (b) — grants neither axis models

Checks 2 (`git_exposed`) and 8 (`sourcemap`) disclose the application's **own source and
configuration**. That is a real loss and it is not a privilege rung (Axis B is about attacker
capability) and it is not on the data axis (`none|own|tenant|all` is about *customer* data). Rating
them by forcing a fit would either fabricate an impact or suppress a real one.

**Rule:** declare `grants: {capability: none, data: none}`, add the non-computed annotation
`discloses: source`, and raise non-blocking **`GRANT_AXIS_GAP`**, routed to §7.5's
vocabulary-extension path. **Do not invent a rung in this document.** The correct extension path is
the one the design already has: three occurrences across two engagements opens a candidate rule with
its citations, and the operator writes it or rejects it with a reason. One instance is not a
vocabulary — the same discipline the research document applies to its own `artefact` type
(`exploitability-severity-model.md:1861-1863`).

Consequence, stated plainly: **`.git/config` exposure currently bands `info` and is capped at `low`
by §5.1.** That is an under-rating and it is a known one. It is the safe direction only because
§8's coverage register still records the check as `present` and the report still lists it — a
suppressed severity with a visible record is recoverable; a fabricated rung is not.

### 5.5 The three header checks

`strict-transport-security`, `content-security-policy`, `x-content-type-options` are
`finding_class: posture` and are **exempt from the precondition machinery entirely**
(`exploitability-severity-model.md:1340-1347`). There is no exploit to have a precondition for —
the same reasoning that gives them `verified: n/a` under §10.3. Extending the ladder to them would
reject every legitimate posture finding, which is the exact failure the posture carve-out exists to
prevent.

They still carry `environment_at_test` and still take the environment cap at the `posture` column
(§6), which is what correctly drops F-048 and F-060 without needing a ladder at all. HSTS on a
plaintext origin never reaches this point — §4.1(a) removes it one step earlier.

### 5.6 Does this generalise to nuclei?

**Partly, and the honest answer is that it does not settle RG-3.** The static-table approach works
here because 12 is a reviewable number and each `Check` is a hand-written object RedGold owns.
nuclei's template corpus is `v10.4.7` and thousands of templates maintained by someone else; a
per-template `grants` table is not maintainable and inventing one from template metadata is exactly
the fabrication hard rule 2 forbids.

What this section **does** settle for RG-3: **option A applies unconditionally to any scanner
output.** A pinned-library record has no `verified_by`, so §4.5 caps it at `low` whatever its
template says. RG-3 may therefore ship pinned scanners without solving the grants problem, at the
cost of the product statement that pinned scanner output is `low` until an agent verifies it. The
per-template mapping question is deferred to RG-3 and is explicitly **not answered here**.

Cross-reference, brief, because it touches provenance and determinism fields: **the correct nuclei
pinning flags are `-t <dir>` plus `-duc`. `-td` exists at `v3.11.1` as the boolean short form of
`--template-display`**, so `nuclei -td /pinned/templates` does not error — it sets a display flag and
leaves the path as an unconsumed argument, running against nuclei's *default* template resolution
while appearing to have pinned (`session-audit-2026-08-20.md:208-229`). A pin that silently does not
apply is worse than no pin, because it is reported as applied. Any `provenance`/`determinism` field
RG-1 records about a scanner run must be derived from the *actual* resolved template directory, not
from the flag string. Full treatment belongs to RG-3.

---

## 6. The environment cap — **PROVISIONAL (P-1)**

> **BUILT IN RELEASE 2, STILL PROVISIONAL (D-1) — adopted provisionally, awaiting operator
> sign-off.** Option 2's numbers are implemented as the single constant
> `findings.ENVIRONMENT_SEVERITY_CAP`, carrying the same marker in its comment. Reversing the
> decision, or moving any band, is a change to those five rows and nothing else — no cap value is
> written anywhere but there. The `production_nexus` bypass, the closed five-value kind
> vocabulary, and the `code_defect` default for `rg-codeaudit` are all built as specced below.

> **PROVISIONAL — awaiting operator sign-off. This is a decision, not research.** Two source
> documents give different numbers, differing by up to **two bands** on the same finding, with
> different bypass mechanisms and different evidentiary burdens on the bypass
> (`session-audit-2026-08-20.md:338-351`). Neither document states that it is overriding the other.
> The spec must pick explicitly and record why, so nobody re-derives the conflict from the autopsy.

### 6.1 The two candidates

| | Non-production cap | Bypass | Source |
|---|---|---|---|
| **Option 1 — flat** | `technical` findings capped at **`low`** for *any* `environment != production` | `applies_to_production: true` **with a stated reason** | `prior-engagement-autopsy.md:573-576` (E1) |
| **Option 2 — graduated** | `staging` → **`high`**, `development` → **`medium`**, `ephemeral-preview` → **`low`** (posture column: `medium`/`low`/`low`) | `production_nexus`, a **five-value closed vocabulary**, each kind requiring its own resolving evidence pointer | `exploitability-severity-model.md:43-44, 663-728` |

### 6.2 Recommendation: **Option 2**, with the reasoning recorded

Four reasons, ordered by weight.

1. **Option 1 buries the autopsy's own worst-case example.** F.5 is a live, spend-capable Resend API
   key (`re_…`, 36 chars, not sandboxed, posting to the live Resend API) sitting in a development
   config on a laptop whose services all bind `0.0.0.0` (`prior-engagement-autopsy.md:764-772`). Under Option
   1 that is `low` unless someone writes a sentence. **Capping a live production credential at `low`
   because the box is a dev box is a worse error than any of the seven findings the cap suppresses**
   — it is precisely the "guardrail set that only subtracts" the autopsy warns against.
2. **`applies_to_production: true` "with a stated reason" is a free-text field, and a stated reason
   absorbs any sentence an agent wants to write.** That is the same structural weakness FM-5
   documents: the agent wrote honest, qualified prose *in the field that carried the severity claim*
   and nothing read it (`prior-engagement-autopsy.md:411-416`). A closed enum with a resolving evidence
   pointer per kind cannot absorb a disclaimer. This is the stronger of the two differences between
   the options — the bypass matters more than the number.
3. **`code_defect` is what makes the whole programme safe to ship.** Every whitebox finding in §F.4
   — the missing unique constraint, the absent fulfilment fallback, the dead sweeper, all three
   affecting paying customers in production — carries it automatically, because `rg-codeaudit`
   operates on a `SOURCE_CODE` asset. **The environment of a source-code finding is the code, not
   the box it was read on.** `rg-codeaudit` sets `production_nexus.kind: code_defect` by default on
   every finding it emits; genuinely dev-only code (a test fixture, a seed script, a
   `compose.dev.yaml`) must **explicitly clear it** — the default runs in the direction that
   discloses. Option 1 has no equivalent, and deploying it would have suppressed the only findings
   the engagement most needed to produce.
4. **A cap, not a shift, in both options — and the graduated version makes the cap say something
   useful.** `severity_derivation.env_cap_applied: true` and `after_env_cap` let the report say
   *"Rated medium because it was observed in a development environment. The same issue in your
   production system would be rated high"* — which is far more useful to a client than either number
   alone, and is the sentence F-103 should have contained.

### 6.3 The cost of choosing Option 2, stated

Option 2 leaves up to two more bands of severity standing on a dev box than Option 1 would. On the
prior engagement's corpus that is the difference between F-101/F-103 landing at `low` and landing at `medium`.
Three things already cut in the same direction and make the residual acceptable:

- the `reach` axis costs `adjacent-trusted` a full band (§4.7) — most of the gap between how F-101
  was rated and how it should have been;
- §4.5 caps every self-certified scanner finding at `low` independently;
- §4.3's domination caps F-107 at `info` before the environment cap is even reached.

**This is the residual the operator is signing for.** If the operator prefers the flat cap, the
change is one table and one bypass field, and §6.2's reason 3 becomes a hard requirement rather than
a property: `code_defect` (or an equivalent) must exist under Option 1 too, or the whitebox findings
die.

### 6.4 The rule, once decided

*Input:* `severity` after domination; `environment_at_test`; `production_nexus`.
*Comparison:* `production_nexus` present and its `kind` recognised with a resolving `evidence_ptr`?
*Action:*
- **yes** → no cap. Record `env_cap_applied: false` with the nexus kind.
- **no** → `severity = min(severity, CAP[environment_at_test])`, using the class-appropriate column.
  Record `env_cap_applied: true` and `after_env_cap`.
- **`kind` unrecognised** → cap bypassed (disclosing direction) **and** blocking (correctness
  direction). Both.

Three properties that must be implemented deliberately:

- **Applied after domination and before the §10.3 verification gate.** Capping first would let a
  `development` cap mask a domination that should have been recorded, losing the `dominated_by`
  cross-reference.
- **Recorded, never silently applied.**
- **`min`, never `max`.** An engagement against production does not get a floor.

`NONPROD_INTERNET_EXPOSED` (§4.2) is **exempt** from the cap.

---

## 7. The adversarial reviewer's contract

Layer two. The gate of §§4–6 handles volume; the reviewer handles what survives. Its existence is
FM-4: `rg-verify` produced a correct `high`→`low` rejection on F-005, argued it in detail
(`findings/verification.md:184-186`), recorded it in the summary (`:251-252`), and
`findings/baseline.json:78` still says `"severity": "high"`. **The reasoning step succeeded
completely and changed nothing.**

### 7.1 What it receives

| Provided | Why |
|---|---|
| The full record, including `precondition`, `grants`, `severity_derivation` | The subject |
| Every file its `evidence_ptr` resolves to, **in full** | Gate 2 is unanswerable without the raw request and response |
| The resolved asset row: `reach`, `environment`, `signup_open`, `reachable_population` | The precondition is asset-derived; the reviewer must be able to challenge the asset row, not only the record |
| **The candidate dominators** — every other finding whose `grants.capability` rank ≥ this record's `precondition.capability` rank | The mechanised form of the F-107/F-103 comparison. The reviewer does not have to remember the corpus; the comparison is handed to it |
| The vocabulary spec at its pinned `model_version` | So a challenge names a rung that exists |
| The six gates of §10.4 verbatim, with the adversarial framing | Unchanged from today |

| **Not** provided | Why |
|---|---|
| The draft report or any client-facing text | Its job is the finding, not the narrative. Showing it the report invites it to optimise the document |
| Other agents' prose reasoning, including `verification.md` | Independence. FM-4's failure was prose; re-feeding prose reproduces it |
| The severity another reviewer assigned | Where two reviewers run, they run blind and the merge takes the minimum |
| Network access to the target | This is the review pass, not the re-execution pass. Re-execution is a separate, earlier invocation with its own tier and gate approval |

### 7.2 What it may change — and the argument for downward-only

**It may lower a severity. It may never raise one.**

The argument: raising severity has no verification behind it. §10.3's central rule is that no
technical finding above Low reaches a client without independent re-execution, and P2 states a
finding is not a finding until something other than the model has verified it. A reviewer that
raises `medium` to `high` on the strength of reasoning has produced a new above-Low claim **by
reading** — exactly the act the framework forbids everywhere else. The calibration numbers point the
same way: §20.1's **15.3–45.8% false-positive band for autonomous detection across six frontier
models** (arXiv 2605.23243, 150 balanced samples) is the rate at which a model asserting a
vulnerability is wrong, and an upward revision is an assertion of that kind.

The asymmetry is the point. The worst case of an over-eager downgrade is a finding demoted to a
coverage section where the client can still see it, and §8 is built to catch it. The worst case of
an over-eager upgrade is the sloptimism §20.6 documents killing bug bounty programmes — curl
terminated, Internet Bug Bounty paused, Bugcrowd triage +334% in three weeks.

**But the reviewer must have somewhere to put "this is under-rated", or it will put it in the
severity field anyway.** That is `coverage_challenge`: a structured claim that the finding *would*
be more serious if a named test were run, plus the test. It does not touch severity. It lands in the
coverage register (§8.1) as `not_attempted` with reason `reviewer_challenge`, and it **blocks phase
completion** until run or explicitly deferred with a recorded reason. This is the channel that would
have carried the autopsy's F.1 — *"F-106 concludes about a capability having tested one route; test
`/p/:uuid?member_status=paid`"* — converting an unactionable opinion into a two-request task.

| Field | Reviewer may |
|---|---|
| `severity` | recommend **lower only**, via `severity_recommendation` |
| `precondition.*` | challenge with a proposed value + basis; **does not apply**. Raises `PRECONDITION_CHALLENGED` for operator resolution |
| `grants.*` | same. The highest-value challenge type, because `grants` is a declaration and a lazy declaration produces a low severity |
| `verified`, `verified_by`, `evidence_ptr` | **nothing.** These are facts about what was executed |
| `environment_at_test`, `production_nexus` | challenge only. The environment is a client declaration; a model may not overrule it |
| gates 1–6 | record pass/fail per gate — the existing §10.4 output, finally serialised |
| `verdict` | `VALIDATED` / `REJECTED` / `NEEDS-WORK` |
| coverage | append `coverage_challenge` entries |
| anything else | nothing. **The reviewer never writes to `findings/*.json`** |

### 7.3 Output schema, and the E4 correction — **PROVISIONAL (P-4)**

> **The research premise for E4 is wrong and the audit corrects it**
> (`session-audit-2026-08-20.md:50-63`). `rg1-implementation-surface.md:274-275` says `rg-verify`
> "cannot write a verification file even if told to" because its tools are `Bash, WebFetch, Read`.
> **`Bash` is a write path.** `agents/rg-verify.md` already instructs the agent to *"write a blocker
> to `ledger/blockers.jsonl` and stop"* and, under HANDOFF, to *"write your output to disk"*. No hook
> restricts it: there is no `hooks.json` and no `.claude/settings.json`, and `scope_guard.py` gates
> network calls, not writes.
>
> **The actual defect is: no schema, no mandated output path, and nothing that parses the
> unstructured output.** Verdicts land as free prose (`findings/verification.md`) that no script
> reads. Spec the fix as *a required structured verdict at a mandated path, with a schema, and a
> merge that fails closed on a missing row* — **not** as a tool grant. A tool grant alone fixes
> nothing.

**Mandated path:** `findings/review.jsonl`. JSONL, one object per line, one line per reviewed
finding — not a document, because the failure being fixed is that the verdict lived in prose.

```json
{
  "schema": "rg-review/1",
  "finding_id": "F-005",
  "reviewer": "rg-verify",
  "reviewer_pass": 2,
  "framing": "assume-every-finding-is-a-false-positive",
  "reviewed_at": "2026-08-20T09:14:00Z",
  "model_version": "rg-sev/1",
  "gates": {
    "1_reproducible_poc": "pass", "2_http_evidence": "pass", "3_impact_verified": "fail",
    "4_in_scope": "pass", "5_real_vulnerability": "fail", "6_client_reproducible": "pass"
  },
  "verdict": "REJECTED",
  "severity_recommendation": "info",
  "severity_rationale": "Response body is site title, description, accent colour, locale, url, version and site_uuid. /ghost/api/admin/site/ is fetched by the unauthenticated admin login page by design. No capability and no non-public data are conveyed.",
  "challenges": [
    {"field": "grants.data", "asserted": "tenant", "reviewer_value": "none",
     "basis": "evidence/F-005-ghost_admin_open.http#L16"}
  ],
  "dominating_finding": null,
  "coverage_challenge": [],
  "rationale_ptr": "findings/verification.md#f-005-admin-api-reachable-anonymously",
  "overturn": true
}
```

`verification.md` **survives unchanged** as the human narrative — its reasoning was correct and it is
genuinely useful. It simply stops being the transport. `rationale_ptr` must resolve under §10.2, so
narrative and verdict cannot drift apart without a validator noticing.

**On granting `Write`: recommended no, for now.** The correct write mechanism is a single
`Bash` heredoc append per verdict, followed by a mandatory `merge_review.py --validate` pass that
rejects the whole file on the first unparseable line. Reasons: (i) the failure is schema conformance,
not capability, and a `Write` grant addresses neither; (ii) `Bash` is already granted, so the grant
adds a capability without removing one — under hard rule 6, a tool grant to a high-risk agent needs a
reason beyond convenience; (iii) validation-on-read is required regardless, so it must be built
either way, and once built, the write mechanism stops mattering. **Grant `Write` only if the heredoc
path proves unreliable in practice, and record the reason if so.** Open decision **D-3**.

### 7.4 The merge path — mechanical

`merge_review.py`, run by `/rg:report` and `/rg:gate` **before either produces output**.

```python
def merge(record, review):
    """Apply a review verdict. Monotone downward, by construction."""
    if review is None:
        record["_no_verdict"] = True          # → NO_REVIEW_VERDICT, coverage gaps
        return record
    rec_i = SEVERITIES.index(record["severity"])            # membership-checked, no .get
    rev_i = SEVERITIES.index(review["severity_recommendation"])
    final = SEVERITIES[min(rec_i, rev_i)]                    # never max
    record["severity"] = final
    record["severity_derivation"]["after_review"] = final
    record["review_ptr"] = f"findings/review.jsonl#{review['finding_id']}"
    return record
```

Six rules, each closing a specific failure mode:

1. **`min`, never `max`.** §7.2's argument made mechanical: the permission to raise does not exist in
   the code, so it cannot be exercised by a persuasive rationale. Property-tested over all 5×5
   severity pairs.
2. **A missing verdict row is not neutral.** Every `technical` finding above `low` requires one.
   Without it the record does not enter the report body; it goes to coverage gaps labelled *"not
   reviewed"*. **This inverts the current default**, where an unreviewed finding is published and a
   reviewed-and-rejected one is also published.
3. **An unparseable `review.jsonl` fails closed at the file level, not the row level.** If the file
   cannot be read, *every* above-Low technical finding goes to coverage gaps. A partially-parsed
   review file that silently publishes the rows it could not read is the same class of bug as
   trusting an upstream validator.
4. **Both severities are printed.** Where they differ, the report shows the computed value, the
   reviewed value and the `rationale_ptr`. The client sees that a downgrade happened and why — which
   is what makes the suppression auditable.
5. **Challenges do not merge.** A `challenges` entry raises `PRECONDITION_CHALLENGED` /
   `GRANTS_CHALLENGED` for the operator, blocking report generation until resolved by editing the
   record or dismissing with a recorded reason. The reviewer cannot rewrite the scorer's inputs, or
   the two layers collapse into one.
6. **Idempotent and re-runnable.** `after_review` is recomputed from `base` each time, never applied
   cumulatively, so running the merge twice does not ratchet a severity down twice.

### 7.5 Measurement, and how judgement becomes vocabulary

Four numbers, defined so each means one thing, written to `ledger/review.jsonl` and reported in
`status.md` after every engagement: `reviewed`, `overturn_rate`, `challenge_rate`, and
**`coverage_challenge_yield`** (coverage challenges that, once run, produced a finding / coverage
challenges run) — the most important of the four, because it is the only one that measures whether
the reviewer improves *coverage* rather than only trimming.

**Two-sided alarm.** `overturn_rate` > 40% on an engagement **blocks the next engagement's Gate 1**:
a reviewer overturning half the corpus means the mechanical layer is producing garbage the advisory
layer is quietly cleaning up, which is the layering failing. `overturn_rate` < 5% over three
engagements means the reviewer is not earning its cost *or* has been captured by the gate's outputs.
Neither number is good news alone.

**Extension path** (`/rg:harvest` aggregates across engagements): the same
`(field, asserted → reviewer_value)` pair in **≥3 overturns across ≥2 engagements** opens a candidate
structural rule in `playbooks/_generic/severity-rules.md` with its three citations, which the
operator writes as a deterministic check or rejects with a reason. The same
`scope_change_proposed` (or three semantically equivalent) ≥3 times is a candidate
`SCOPE_CHANGE_KINDS` value requiring a `model_version` bump. A `GRANT_AXIS_GAP` or an
out-of-ladder `grants.capability` named ≥2 times is a candidate rung, requiring a `model_version`
bump and re-scoring of the corpus at the new version.

### 7.6 Where this sits relative to P1 — stated, not argued away

P1 is that **enforcement is mechanical, never advisory**. The reviewer is a language model exercising
judgement and its verdict is not mechanical. **That is a real violation and it is recorded as one.**

What is mechanical, precisely: the gate of §§4–6 (enum lookups and rank comparisons over declared
fields — models supply *inputs*, which is true of every control in the framework including
`scope_guard.py`); the **merge** (`min()`, a required row, a fail-closed file read); the **consequence
of the reviewer's absence** (no verdict row → no report body, deterministically, whether it failed to
run, crashed, or emitted garbage); and the **direction** of its influence (`max` does not appear in
the code).

What is advisory: the content of the verdict, the severity recommendation, and the challenges.

Why the layering makes it acceptable — three claims, each checkable:

1. **The reviewer is strictly an additional filter, never the sole authority.** Everything it can
   lower, the mechanical gate could also have lowered — same scale, same records, downward only.
   There is no outcome reachable via the reviewer that is not reachable via the gate. It cannot
   expand what the framework asserts; it can only contract it.
2. **Its failure modes are asymmetric and the dangerous one is closed.** It cannot inflate (no
   `max`), cannot create a finding (writes only `review.jsonl`), cannot mark something verified (no
   write to `verified`), cannot overrule the client's environment declaration (challenge only). The
   remaining failure mode is over-suppression, and §8 is built specifically to catch it.
3. **It is measured, with a two-sided alarm** (§7.5). An advisory component that is counted is a
   different object from one that is trusted.

**The honest residual.** If the reviewer is systematically, quietly wrong in the downward direction —
consistently under-rating a whole class of finding — the framework produces cleaner reports that are
wrong, and **none of the three claims above catches it.** The only thing that catches it is §8 plus
an outside adjudication of a real engagement's corpus, which is what the prior-engagement autopsy was.
**Budget one autopsy per two engagements.** That is not a control; it is a practice, and it belongs
in the engagement cadence rather than being discovered again the hard way. Open decision **D-8**.

---

## 8. The coverage counterweights — specced first, shipped first

**Everything in §§4–7 reduces the false-positive rate. None of it increases coverage.** The prior
engagement's worse failure was not looking: the whitebox engagement held the only `SOURCE_CODE`
asset and produced zero artifacts, three confirmed customer-affecting defects went unfound, a live
spend-capable credential sat in a config nobody read, and one finding held both halves of a chain
and never joined them.

**A guardrail programme shipped without this section makes a hollow engagement look cleaner** — and
its measurable output, "fewer findings", is indistinguishable from success. This section is
therefore specced before the rest is built, and §8.6 and §8.2 ship **before** E2.

> **PROVISIONAL (P-3) — resolved here, recorded so it is not re-litigated.** The two source documents
> disagree: `rg1-implementation-surface.md:505-508` puts the coverage counterweight **last**;
> `exploitability-severity-model.md:1978-1988` and `:1934` put the two cheapest coverage rules
> **first**, *"without them the whole programme is a suppression engine"*. The audit's judgement is
> that this is the strongest argument in either document and the one the orchestrator's summary
> inverted (`session-audit-2026-08-20.md:182-194, 492-514`). **Coverage-first is adopted.** The
> orders are compatible: §8.6 and §8.2 touch none of E1–E5's functions, so
> `rg1-implementation-surface`'s E2 → E1 → E3 → E5 → E4 applies unchanged **after** they land.

### 8.1 The coverage register

`coverage.jsonl` — a first-class artifact alongside `findings/`, written by every phase, one record
per (check × asset).

```json
{"phase": "baseline", "check_id": "header.hsts", "asset_id": "A-002",
 "outcome": "absent", "evidence_ptr": "evidence/cov-A-002-hsts.http",
 "at": "2026-08-20T09:00:00Z"}
```

`outcome` is a closed enum: `present` (a finding was emitted) · `absent` (looked, clean) ·
`not_applicable` (structurally meaningless here — §4.1's HSTS-on-plaintext, and the 36 HTTP probes
at MySQL/Redis/SMTP, now **one record per asset** naming all skipped checks) · `not_attempted` (did
not look).

**`not_attempted` requires a `reason` from a closed vocabulary**, and this field does the work:

| Reason | Consequence |
|---|---|
| `out_of_scope` | Listed in the report's scope section |
| `ceiling` | Listed as "not tested — requires authorisation for X" |
| `blocked_by` | Listed; the named blocker **must exist** in `ledger/blockers.jsonl` |
| `component_down` | **Blocking at phase completion** — see below |
| `time` | Listed prominently; requires operator acknowledgement |
| `reviewer_challenge` | Blocking until run or explicitly deferred (§7.2) |

**`component_down` is deliberately the harshest.** It is what the autopsy's F.3 was: the Ghost admin
SPA and the member Portal bundle both 502'd, so Google SSO and the WebAuthn passkey flows — *"the
largest net-new auth surface"*, where the operator's own pre-audit said the real findings live — were
recorded as a coverage gap and the engagement moved on to Redis and header posture
(`prior-engagement-autopsy.md:723-737`). **The engagement's behaviour was honest and it was also the wrong
outcome.** A phase carrying any `component_down` record cannot be marked complete; the operator must
restore the component, re-scope explicitly, or accept it with a recorded decision that appears
verbatim in the report's coverage section.

The register also fixes an accounting bug the autopsy found: `status.md:66` claimed *"32 checks ran
and found nothing"* against 28 `absent` records in the file (`prior-engagement-autopsy.md:795-797`). With a
register that number is a count of rows rather than a derived figure, and it is checkable.

### 8.2 The zero-zero rule — **ships first**

*Input:* `findings/*.json` and `coverage.jsonl` for the phase being closed.
*Comparison:* does the phase have **zero findings and zero `absent` coverage records**?
*Action:* `gate_cli.py` **refuses**, raising `COVERAGE_EMPTY_PHASE`.

Five lines, and it is the single most important thing in this section. It is what would have stopped
`ENGAGEMENT-B` — whose `findings/`, `evidence/` and `deliverables/` are empty directories
and whose six ledger files are 0 bytes (`prior-engagement-autopsy.md:36`) — from being a thing that quietly
existed.

**An engagement with no findings is a possible and respectable outcome. An engagement with no
findings *and no record of having looked* is not an engagement.** The rule generalises: *"we found
nothing" and "we did not look" must be mechanically distinguishable at every level of the system.*
That is the same principle `extract_records` already applies at the file level and
`baseline_scan.py:196-200` already applies at the check level. It is missing only at the phase
level, which is the level that matters most.

Note `regen_status.py` is **not** where this goes. `regen_status.render()` derives its phase table
purely from event counts (`scripts/regen_status.py:113-124`) and would have correctly rendered every
whitebox phase as "not started". The gap is not in its logic; it is the absence of anything that
**refuses to let an engagement close** while every phase reads "not started"
(`rg1-implementation-surface.md:329-341`).

### 8.3 Asset coverage assertions

*Input:* `assets/register.jsonl` joined to `coverage.jsonl`.
*Comparison:* does every CONFIRMED asset appear in ≥1 coverage record per phase claiming to cover it?
*Action:* `gate_cli.py` refuses phase completion unless the phase carries a **named gap naming that
asset**.

Two corollaries, both prior-engagement failures:

- **A `SOURCE_CODE` asset in scope with no `rg-codeaudit` coverage records is a blocking gap at
  engagement close.** This alone is the mechanical form of *"run the whitebox engagement"*, which the
  autopsy names as the largest single improvement available to the framework — **larger than every
  suppression rule in this document combined**.
- **Coverage is per asset, not per host.** `:8025` and `:8026` being one Mailpit process
  (`assets/register.jsonl:5`) means they are one asset for finding purposes — deduplicating F-060
  against F-048 — but coverage must still record that **both ports were probed**, or the dedup
  silently erases evidence of work done.

### 8.4 Unjoined-chain detection — **deferred, deliberately**

`chain_scan.py` builds an edge from finding F to check C when F's `grants` satisfy C's declared
`precondition` on capability rank, data rank, reach compatibility, artefact type and environment, and
raises blocking `UNJOINED_CHAIN` for every edge whose coverage record is `not_attempted`.

On the prior engagement: F-106 grants `artefact: post-identifier` at `capability: none`; the preview-route check
declares `precondition: {capability: none, artefact: post-identifier}`; the edge exists, the check
was never attempted, and the engagement would be blocked from closing until it ran — two requests.
**The engagement held both halves of the chain in the same JSON file, written in the same session,
and never joined them.**

This is the constructive twin of §4.3: the same comparison that suppresses F-107 as dominated also
*discovers* that two findings compose. One comparison, two uses, opposite directions.

**Deferred out of RG-1** for the reason the source document gives against its own proposal: the
artefact-type vocabulary is derived from **one** instance (`post-identifier`), and one instance is
not a vocabulary (`exploitability-severity-model.md:1855-1863`). It also requires check definitions
to declare preconditions and artefact types, which today they do not. Design it against the next real
corpus, after §8.1–8.3.

### 8.5 Scope-bounded negatives

The rule that catches F-104 and F-106, neither of which any severity rule touches.

*Input:* `real_world_impact` and `title` on a record at `info` with `finding_class: technical`.
*Comparison:* does the text match a negative-capability phrase — `cannot`, `not disclosed`,
`requires authentication`, `is not`, `demands`, `no access`, `not reachable`, `safe`?
*Action:* three fields become **required** (blocking when absent): `routes_tested`,
`credentials_tested`, `scope_of_conclusion`. The report renders the conclusion **prefixed by
`scope_of_conclusion`**, never bare.

F-104 becomes: *"On the single blank-password probe attempted, MySQL required credentials. No other
credential was tested; `no_destructive` and the approved plan excluded credential testing."* That
sentence is true, is what the engagement actually established, and is **not reassuring** — which is
correct, because the ground truth is `bind_address = *`, `root` and `ghost` both at grant-host `'%'`,
and a default-shaped root password (`prior-engagement-autopsy.md:273-278`). The engagement had no basis for
the word *"good"*.

This is the propagation FM-8's cousin needs: a constraint (no credential testing) that did not reach
the finding now travels **with** the conclusion, because it is a required field on the same record.

*Paired requirement:* a `not_attempted` coverage record with reason `ceiling` must exist for the
untested half, so the gap appears in the coverage section as well as in the finding's wording.

### 8.6 Report freshness — **ships first**

*Input:* deliverable mtime; newest `findings/*.json` record `created` timestamp.
*Comparison:* is the deliverable older than the newest finding?
*Action:* refuse to close the engagement, raising `REPORT_STALE`. Additionally **embed the newest
finding's `created` timestamp and the corpus record count in the report's own header**, so staleness
is visible in the artifact itself and not only to a script that may not be run.

`deliverables/report-tier1.md` was written `2026-08-04 20:38`; `findings/baseline.json` is
`2026-08-05 01:20`; `assets/register.jsonl` is `2026-08-05 01:11`. The report says *"No confirmed
findings"* and *"No assets were confirmed during this engagement"* while `status.md` lists six
CONFIRMED assets and eleven findings including a critical (`prior-engagement-autopsy.md:511-529`).

**The engagement's sole client deliverable is empty, and nothing detected that. Every other control
in this document is irrelevant to a client who receives that file.** Five lines, and it is the
cheapest thing here by an order of magnitude.

---

## 9. Build order, tests, and injected faults

**Coverage first, then `rg1-implementation-surface`'s order.** Each item names: files touched, tests
that break, and the **injected fault** it needs in `scripts/verify_controls.py`.

On the last of those: `verify_controls.py` copies the repo to a temp dir and, for each of **21**
`Mutation(name, file, old, new, test_module, breaks)` entries (`:45-169`), replaces `old` with `new`
in one file, runs the named test module, and asserts it goes **red**. It has **no entry for any of
the six RG-1 changes today** (`rg1-implementation-surface.md:444-455`). **A new control without a
corresponding injected fault grows the test count without growing discrimination** — the count is
not the claim.

### 9.1 Release 1 — coverage. No dependencies. Ships before E2.

| # | Item | Files touched | Tests that break | Injected fault |
|---|---|---|---|---|
| **C1** | §8.6 report freshness (`REPORT_STALE`) | `scripts/report.py` (`main()`, `:340-358`; header block `:167-173`) | `tests/test_report.py` — new case: report older than newest finding must refuse | *"stale-report gate disabled"*: the mtime comparison → `if False:`. Module `tests.test_report` |
| **C2** | §8.2 zero-zero (`COVERAGE_EMPTY_PHASE`) | `scripts/gate_cli.py` (`cmd_complete`, the `complete --phase` subcommand) — **not** `cmd_approve`, see §4.8 | `tests/test_gate_cli.py` — new case: phase with zero findings and zero `absent` records must refuse | *"zero-zero rule disabled"*: the emptiness test → `if False:`. Module `tests.test_gate_cli` |
| **C3** | §9.1a engagement close (`PHASE_NEVER_COMPLETED`) — the binding site for C1 and C2 | `scripts/gate_cli.py` (`cmd_close`), `commands/close.md` | `tests/test_gate_cli.py` — new case: close with a stale report, an empty corpus, or no completed phase must refuse | *"close gate disabled"*: the refusal test → `if False:`. Module `tests.test_gate_cli` |

Ten lines between C1 and C2. **They are the only thing preventing RG-1's first release from being a
pure suppression release** — and C3 is what stops them being opt-in.

### 9.1a Why closure is a command and not a hook

C1 and C2 as first built were both **opt-in**: an operator who never ran `report.py --check` or
`gate_cli.py complete` was stopped by nothing. Under P1 (*enforcement is mechanical, never
advisory*) a control that depends on someone remembering is not a control. The obvious remedy is
hook 7 of `07-enforcement.md` §9.2 — `cleanup_gate.py`, a `Stop` hook — which `status.md` records
as never built. **It does not work, and the reason generalises.**

| Candidate | What the harness actually does | Verdict |
|---|---|---|
| `Stop` hook | Fires *"when Claude finishes responding"* — **once per turn**, many times per engagement. Exit 2 *"Prevents Claude from stopping, continues the conversation"* | **Wrong twice.** A refusal keyed on an empty corpus fires on every turn of a healthy engagement's opening phase — §2.3's disabled-gate failure again. And exit 2's actuator is the *model*, not the operator: it coerces the assistant to keep working at a remedy only the operator has (restore a component, re-scope, accept a gap with a recorded decision) |
| `SessionEnd` hook | Fires *"when a session terminates"*. Exit 2 *"Shows stderr to user only"* — the docs place it among events *"that already happened or can't be prevented"* | **Cannot refuse.** A control that can only print is advisory, which is what P1 forbids. An engagement also spans many sessions, so session end is not engagement close |
| Any other event | The event list is `SessionStart`, `Setup`, `UserPromptSubmit`, `UserPromptExpansion`, `PreToolUse`, `PermissionRequest`, `PermissionDenied`, `PostToolUse`, `PostToolUseFailure`, `PostToolBatch`, `Notification`, `MessageDisplay`, `SubagentStart`, `SubagentStop`, `TaskCreated`, `TaskCompleted`, `Stop`, `StopFailure`, `TeammateIdle`, `InstructionsLoaded`, `ConfigChange`, `CwdChanged`, `DirectoryAdded`, `FileChanged`, `WorktreeCreate`, `WorktreeRemove`, `PreCompact`, `PostCompact`, `Elicitation`, `ElicitationResult`, `SessionEnd` | Every one is **turn-, tool-, session- or subagent-scoped.** None is engagement-scoped |

**The finding, stated plainly: there is no Claude Code lifecycle event for "engagement close",
because an engagement is not an object the harness knows about.** It spans sessions and is closed by
an operator decision the harness never observes. The spec assumed a close path the platform does not
provide, and no hook can supply one.

So closure is made an **act** rather than an absence: `gate_cli.py close` (`/rg:close`), which runs
C1 and C2 in one place and appends a `gate.close` row to `ledger/gates.jsonl`. This is opt-in in
exactly the sense `gate_cli.py approve` is opt-in, which the framework already accepts for its
flagship gate. What changes is that skipping it is now **detectable**: an engagement with no
`gate.close` row was not closed, and that absence is a fact on disk rather than a thing nobody
recorded.

**The honest residual, which no amount of engineering removes here:** an operator who abandons an
engagement without running `/rg:close` is still stopped by nothing. `/rg:close` narrows the failure
from *"forgot one of several checks"* to *"skipped the documented close step"* — it does not
eliminate it. Do not describe engagement close as mechanically enforced.

**`cleanup_gate.py` keeps its own remit and is still unbuilt.** Coverage does **not** belong in it,
for a reason worth recording: cleanup debt (`pending`/`orphaned` rows in `ledger/cleanup.jsonl`) is
*agent-actionable* — the remedy is to delete the row, which is exactly what exit 2 on `Stop` is
shaped for — whereas coverage emptiness is *operator-actionable* only. Two controls with different
remedies and different actors do not share a hook merely because both sound like "things that
should be true at the end".

### 9.2 Release 2 — the E-series, in `rg1-implementation-surface` order

**Status, 2026-08-20: E2 and E1 are built.** E3, E5 and E4 are not. What landed, and what did not:

| Landed | Not landed, and named so nobody reads the table above as a report of state |
|---|---|
| §4.1a scheme filter; §4.1b one collapsed coverage record per dead asset, with `checks_skipped` preserving the true number | §5's static 12-row `grants` table and the `low` scanner ceiling (**D-2**) — those are E3's, not E2's, and D-2 is therefore **not yet implemented in any form** |
| §3.1 `environment` in `scope.yaml` (required key, closed vocabulary, `unknown` typable and un-proceedable), Gate 1 refusal, `new_engagement.py --environment` required | §3.1's `environment_established` and `environment_source` keys, and the per-asset `environment` override. Deferred deliberately: each is a further required key, and the fixture churn is only worth paying once the report banner that consumes them exists |
| §6 the graduated cap as one constant, both columns, `production_nexus` bypass, `code_defect` default-on for `rg-codeaudit`, `env_cap_applied`/`before_env_cap`/`after_env_cap` recorded, `DERIVATION_MISMATCH` | §3.2's `assets/register.jsonl` fields (`reach`, `signup_open`, `reachable_population`, `env_signals` on the asset row). Signals are carried on the **finding** in release 2, because no producer writes an asset row with them |
| §4.2 split and re-sited: declaration at Gate 1, discrepancy at observation and report assembly, with a blocker row and a closed resolution vocabulary | The `prod-signal-present` direction (declared `staging`, actually production) — its conjunction needs `reach`, cert facts and observed PII, none of which exist yet. **This is the direction §4.2 itself calls the one that matters most, and it is unbuilt.** |

| # | Item | Files touched | Tests that break | Injected fault |
|---|---|---|---|---|
| **E2** | §4.1 applicability filter | `scripts/baseline_scan.py:181-185, 390-417`, `make_finding()` `:192-244` | `tests/test_baseline_scan.py` — `MultiPortHarness` (uncommitted, `:220-…`) asserts **one `not_applicable` record per check per port**; those assertions must be rewritten for the collapsed form. `tests/test_regen_status.py`, `tests/test_report.py` count assertions shift (the code that prints does not change — it iterates by `result` and `asset`, not by record count) | *"HSTS scheme filter removed"*: the `scheme == "http"` guard → `if False:`. Module `tests.test_baseline_scan` |
| **E1** | §3.1/§3.2 `environment` + §6 cap + §4.2 discrepancy | `scripts/scope.py` (`Scope` dataclass `:151-163`, `parse()` `:277-364`, `to_dict()` `:165-181`), `scripts/gate_cli.py:330-358`, `scripts/new_engagement.py:97-127, 254-280`, `scripts/findings.py`, `scripts/report.py:156-337` (mandatory banner), `scripts/scope_cli.py` promotion | **Most of the suite.** `tests/fixtures/engagement/scope.yaml` and `tests/fixtures/scope-prior-engagement.yaml` both lack `environment:`; every test rooting an engagement off either — `test_scope`, `test_scope_guard`, `test_scope_cli`, `test_gate_cli`, `test_baseline_scan`, `test_report`, `test_regen_status`, `test_new_engagement` — breaks the moment the key is required. **Add the key to both fixtures in the same commit.** `new_engagement.py`'s round-trip assertion (`:202-203`) silently drops any field missing from `to_dict()` | *"environment gate disabled"*: `cmd_approve`'s environment check → `if False:`. Module `tests.test_gate_cli`. **Second fault** *"environment cap inverted"*: `min(severity, cap)` → `max(severity, cap)`. Module `tests.test_findings` |
| **E3** | §4.5 `verified_by` / `VERIFIED_BY_SELF` | `scripts/findings.py:202-323`, `scripts/baseline_scan.py:233` | `tests/test_baseline_scan.py` asserts `verified == "executed"` on `present=True` records — those become `"none"`. `tests/test_findings.py` needs the new rule. `tests/test_report.py` needs a case proving a baseline-discovered high without independent verification prints at `low` **in the body**, not in the unverified bucket at `high` | *"self-certification permitted"*: the `verified_by == discovered_by` comparison → `if False:`. Module `tests.test_findings` |
| **E5** | §4.6 `IMPACT_NOT_EXECUTED` | `scripts/findings.py` `validate_record()`, `scripts/report.py:58-60` (`VERIFICATION_CODES`) | `tests/test_findings.py`, `tests/test_report.py` — a record carrying only this advisory violation must land in Open Questions, not be dropped by `blocking_codes - VERIFICATION_CODES` at `:131-133` | *"impact lint disabled"*: the marker list → `frozenset()`. Module `tests.test_findings` |
| **E4** | §7.3/§7.4 `review.jsonl` + `merge_review.py` | new `scripts/merge_review.py`, `scripts/findings.py` (schema), `scripts/regen_status.py`, `scripts/report.py`, `agents/rg-verify.md` (mandated path + schema + per-finding requirement) | new `tests/test_merge_review.py`; `tests/test_report.py`, `tests/test_regen_status.py` for the no-verdict → coverage-gaps path | *"reviewer may raise"*: `min(rec_i, rev_i)` → `max(rec_i, rev_i)`. **Second fault** *"missing verdict is neutral"*: the `review is None` branch → `return record` without setting `_no_verdict`. Module `tests.test_merge_review` |

**Sequencing constraints, from `rg1-implementation-surface.md` §9:**

- **E2 before E1.** Both touch `baseline_scan.py`'s per-check loop. Restructure the loop first, then
  thread `environment` through the already-simplified version — do not add environment-awareness to
  code about to be rewritten.
- **E1 and E3 must be designed together.** Both land in `findings.validate_record()` and both use
  **severity demotion** as their enforcement, via the same `EVIDENCE_UNRESOLVED` precedent. If both
  fire on one record, the `Violation` list and the final `severity` need **one agreed order of
  application**, not two competing single-field writers. *This is the single highest sequencing risk
  on the list.* The order is fixed by §4's pipeline: domination (3) → environment cap (4) →
  verification gate (5).
- **E3 ships before E4, but is not *done* until E4.** `verified_by != discovered_by` is close to
  meaningless until something other than `baseline_scan` populates `verified_by`. Build E3's schema
  field and demotion rule first — it correctly parks every self-certified baseline high at `low`
  immediately — but until E4 gives `rg-verify` a documented way to write `verified_by: "rg-verify"`
  back, the demotion is **permanent for every finding regardless of whether it was reviewed**. Say so
  in `status.md` while that window is open.
- **E5 is independent** and can slot in anywhere, including first. It shares no mutated state.

### 9.3 Release 3 and beyond

§8.1 coverage register → §8.3 asset assertions → §8.5 scope-bounded negatives → §4.3 domination
ladder + §4.7 scorer (new `tests/test_severity_model.py`, fixtures transcribed from
`exploitability-severity-model.md` §4.4) → §8.4 `chain_scan.py`, designed against the **next** real
corpus.

Two further faults belong to this release:

| Item | Injected fault |
|---|---|
| §3.4 no-defaulting-lookup rule | *"rank lookup defaults to zero"*: `CAPABILITY_RANK[value]` → `CAPABILITY_RANK.get(value, 0)`. Module `tests.test_severity_model`. This is the 2026-08-04 incident's exact shape and must be caught |
| §11.2 mechanical citation bar | *"marketing deny-list emptied"*: the literal deny-list frozenset → `frozenset()`. Module `tests.test_report` |

**Total after release 2: 33 injected faults, all caught.** 21 pre-RG-1, +3 for release 1 (C1–C3),
+9 for release 2 — more than the two this table predicted for E2 and E1, because each control got a
fault aimed at the *direction* it can fail in rather than one aimed at the feature: the cap
inverted to a floor, fail-closed inverted so an unknown environment caps, the `code_defect` default
removed, the discrepancy rule disabled, the discrepancy routing removed from the report, the
vocabulary opened, and the collapsed coverage record understating its own gap. The last is the one
worth keeping: collapsing twelve records into one must not collapse the *number* with them, and
nothing else in the suite would have noticed if it had. Every one of the RG-1 changes gets at least one,
per `rg1-implementation-surface.md:450-455`.

### 9.4 One prerequisite that is engineering, not research

`scripts/scope_guard.py` **writes no ledger row on allow *or* deny.** `evaluate()` ends
`return Decision.permit()` with no side effect (`:687`); `emit()` is documented *"Silent on allow, by
design"* with an early return (`:76-79`); denials go to stdout as a `PreToolUse` response and, on
`--check-url`, to stderr (`:734-737`). There is no `open()`, no append, no JSONL anywhere in the
decision path. `docs/specs/redgold/07-enforcement.md:433` requires reconciliation between the
off-host egress log and `scope_guard`'s decisions — **there is no decision log to reconcile against,
in either direction**, so that requirement currently describes software that does not exist.

The fix is one append in `emit()` before the early return. It belongs to **RG-2**, not RG-1, and is
recorded here only so it is not rediscovered as a research finding.

---

## 10. What this does NOT do

In the style of `status.md`'s "NOT enforced" section and §9.3.1. **Do not describe any of the
following as working.**

1. **This programme only subtracts severity.** §§4–7 are a monotone-decreasing pipeline by explicit
   design (§4's global invariant). **It cannot make the framework find anything it would not have
   found.** It cannot catch:
   - the `/p/:uuid?member_status=paid` gated-content bypass — that needs §8.4, deferred;
   - the missing unique constraint on the payments ledger, the absent fulfilment fallback, or the dead
     the stale-lock reaper — those need the whitebox engagement to **run**, which is §8.3;
   - the live Resend key — that needs a source-code asset to be read;
   - the Google SSO and WebAuthn passkey surface — that needs `component_down` to block (§8.1).

   Five of the six most valuable things the prior-engagement autopsy identified are in §8, not §§4–7.

2. **Nothing here validates the model.** The "8 of 11" retrospective scoreboard is not a benchmark
   and is barred from client-facing use by §11.2. There is no out-of-sample measurement of any rule
   in this document. The first real validation is: freeze the model, tag it in git, run it against
   the **next** engagement's findings *before* adjudication, then adjudicate.

3. **`grants` is a declaration, and a lazy declaration produces a low severity.** This is the
   model's largest attack surface. §7 exists mostly to police it, and §7 is advisory (§7.6). A
   record-level `grants` under-declaration by an agent that is not challenged is a silent
   suppression that nothing in this document catches.

4. **The reviewer's systematic downward bias is not caught by anything mechanical** (§7.6, "the
   honest residual"). Only an outside autopsy catches it.

5. **The environment classifier can never conclude `production` by itself** (§4.2). Its `no-signal`
   case accepts whatever was declared. A client who declares `staging` about a production system and
   whose system emits none of the four conjunction terms is believed.

5a. **Two of the four blocking environment signals have no producer** (§2.4, as built).
    `framework_debug_page` and `nonprod_cert` are in the vocabulary and nothing emits them; the
    `prod-signal-present` direction is not implemented at all. `ENVIRONMENT_DISCREPANCY` therefore
    fires today on exactly two observations: a test-mode payment key prefix in a response body, and
    a dev-tool service fingerprint in a server banner or a service UI's page title. Do not describe
    environment classification as covering the §2.4 table.

6. **The `x-vercel-deployment-url` signal is gone and nothing replaces it** (§2.3). RedGold has no
   platform-header-based nonprod signal for Vercel-hosted targets. Netlify's equivalent is
   `[VERIFY]`, unchecked, and specified as contributes-only until it is checked.

7. **`.git/config` and source-map exposure are under-rated at `info`/`low`** and will stay under-rated
   until the grant vocabulary gains a rung from evidence (§5.4). This is a known, recorded
   under-rating, not an oversight.

8. **Scanner output cannot exceed `low` without an agent pass** (§5.1). That is a product statement
   and it is the recommended design, not an accident. RG-3's pinned libraries inherit it.

9. **`chain_scan.py`, the coverage register, asset assertions and scope-bounded negatives are
   specced and unbuilt** at the end of release 2. Do not describe coverage as enforced beyond §8.2
   and §8.6 until §8.1/§8.3/§8.5 land.

10. **`scope_guard.py` still writes no decision log** (§9.4), so nothing in this document is
    reconcilable against an egress record. That is RG-2.

11. **None of this is a security boundary.** `scope_guard.py` remains defence-in-depth (§9.3.1), and
    off-host egress filtering — the only real boundary — still does not exist. An agent that
    compromises its own VM can edit every rule in this document. The honest claim stays *"out-of-scope
    targets are refused by tooling and logged"*, never *"cannot happen"*.

**The honest claim for RG-1, once built: "findings carry a declared environment and a declared
precondition, and the framework mechanically caps severity when they do not support the claim, while
recording every cap it applied." Never "our findings are accurate."**

---

## 11. Provisional items and citation bars

### 11.1 The five provisional items, indexed

| # | Item | Section | State |
|---|---|---|---|
| **P-1** | Environment cap values and bypass mechanism | §6 | **Decision, not research.** Both options presented; Option 2 (graduated + `production_nexus`) recommended with reasoning; awaiting operator sign-off. Supersedes the autopsy's flat `low` / `applies_to_production` — recorded here so nobody re-derives the conflict from `prior-engagement-autopsy.md:573-576` |
| **P-2** | The scanner-findings interface | §5 | **The largest genuine gap.** Static table + explicit `low` ceiling recommended. Settles `baseline_scan.py`; explicitly does **not** settle nuclei's corpus, which is RG-3 |
| **P-3** | Build order — coverage first | §8, §9.1 | **Resolved.** §8.6 + §8.2 ship before E2; `rg1-implementation-surface`'s E2→E1→E3→E5→E4 applies after |
| **P-4** | E4's premise is corrected | §7.3 | `rg-verify` **can** already write via `Bash`. The defect is no schema, no mandated path, nothing that parses the output. Do not spec a tool grant as the fix |
| **P-5** | Two citations needing shoring up | §11.2 | Mechanical bars specified below |

### 11.2 Two citations, and the mechanical bar on each

**(a) `docker`-group → `host-root`.** §3.3 maps `docker` group membership (or daemon-socket access)
to rank 7, on the reasoning that `docker run -v /:/host --privileged` is root in one documented step.
The reasoning is sound. **The claim was never fetched from Docker's own documentation**
(`exploitability-severity-model.md:1960-1962`, and `session-audit-2026-08-20.md:151-157` notes the
marker sits in an appendix a reader implementing the rank table never sees).

*The bar:* the `[VERIFY]` marker lives **in §3.3's body**, where an implementer reads it, not in an
appendix. The mapping may be used for internal scoring. **It may not appear in a client report or a
marketing claim until Docker's own documentation is cited.** Hard rule 2 applies.

**(b) The "8 of 11" retrospective scoreboard.** `exploitability-severity-model.md` §4.4 scores the
model at 8 of 11 exact against the prior engagement's corpus. Its own §4.5(2) and §5.6 bar it from client-facing
use, and §B(6) states the correct validation protocol.

*Why a sentence in a research document is not enough.* The audit's diagnosis
(`session-audit-2026-08-20.md:439-483`): the problem is **not** common authorship — the autopsy and
the model were written by two different research agents in the same session — it is a **fitted
vocabulary on a single 11-finding corpus**. Every rung that exists because the prior engagement had a mail catcher
(`env-secret-read`) is a free parameter fitted to the test set. Eleven findings, one engagement, one
stack, one topology, and a vocabulary designed **after seeing the answers**. A model with that many
degrees of freedom scoring 8/11 on its own fitting set carries essentially no information about
out-of-sample behaviour. What it *does* legitimately evidence is that the rule is mechanisable and
internally consistent — **a specification conformance test, not an accuracy measurement.**

And the denominator is worse than it looks: the false-negative check — *"none of the five findings
the autopsy adjudicated SOUND is suppressed"* — is measured against **five instances**. Five is not
enough to detect a suppression bias of any plausible size.

*The bar — mechanical, per `session-audit-2026-08-20.md:470-475` and §20.5:*

1. **A literal deny-list**, built the same way `VERIFICATION_CODES` is a literal set, in `report.py`
   and in any marketing-copy lint: the strings `8 of 11`, `8/11`, `eight of eleven`, and any
   `N of 11` / `N/11` pattern, plus any percentage derived from them. `report.py` **refuses to
   render** a document containing them.
2. **Freeze and tag `model_version` in git before the next engagement**, so *"we did not adjust it
   after seeing the answers"* is checkable from git history rather than asserted.
3. **The deny-list gets its own injected fault** (§9.3): emptying the frozenset must turn
   `tests.test_report` red. A bar that no test discriminates is a sentence in a different document.

**And the general §20.5 constraints, which bind everything derived from this design:** no accuracy
figure for the model itself; no cap phrased as reassurance (the required sentence is the derivation
one — *"Rated medium because it was observed in a development environment. The same issue in your
production system would be rated high"*; the cap is a statement about **where we looked**, never
about whether the client is safe); no probability language, because the bands are not likelihoods;
never *"comprehensive"*, *"complete"* or *"full coverage"* — with more force than before, because a
pipeline that only subtracts makes a short list and a short list invites exactly that adjective; and
never *"no findings"* where coverage records exist.

**Required in any report where this model is used:** a plain-language paragraph naming the two
questions it asks — *what must an attacker already have, and what environment did we see this in* —
and stating that findings the model rated down are **listed with their reasons rather than removed**.
A client who cannot see what was suppressed cannot audit the suppression, and P9 applies to
reductions that flatter our list length as much as to numbers that flatter our accuracy.

---

## 12. Open decisions for the operator

Each has a recommendation. None is a research question; all are choices someone has to make and
record, and leaving them unmade blocks the same work a research gap would.

| # | Decision | Recommendation | Why it cannot wait |
|---|---|---|---|
| **D-1** | **Environment cap values and bypass** (§6, P-1). Flat `low` + `applies_to_production` (autopsy E1), or graduated `high`/`medium`/`low` + `production_nexus` (severity model)? | **Graduated + `production_nexus`.** Four reasons at §6.2; the strongest is that a free-text "stated reason" absorbs any sentence an agent writes, and that `code_defect` is what stops the cap burying every whitebox finding | It is the number the spec must literally state, it differs by two bands, and it interacts with D-2: if scanner findings cannot declare `precondition`/`grants`, the cap becomes the **only** thing modulating their severity |
| **D-2** | **Scanner findings: hard ceiling at `low`?** (§5, P-2) | **Yes**, plus the 12-row static table. The ceiling is already implied by §4.5; stating it stops two mechanisms disagreeing later. Accept the product statement: *pinned scanner output is `low` until an agent verifies it* | Blocks RG-1's schema (`validate_record()` cannot require the fields until this is answered) and blocks RG-3 entirely |
| **D-3** | **Does `rg-verify` get the `Write` tool?** (§7.3, P-4) | **No, for now.** Mandate the path and schema; write via a `Bash` heredoc append; validate on read with file-level fail-closed. Grant `Write` only if the heredoc proves unreliable, and record the reason | Under hard rule 6 a tool grant to a high-risk agent needs a reason beyond convenience, and the premise that the grant was *necessary* was wrong |
| **D-4** | **Does `ENVIRONMENT_DISCREPANCY` ship blocking?** (§2, §4.2) | **Yes, but only on the four signals whose semantics were established** — self-signed cert (as flag-for-review), `pk_test_`/`sk_test_`, framework debug page, dev-tool fingerprint. `x-vercel-deployment-url` is **deleted**: it is a request header, unobservable from outside. `server: Vercel` is not a substitute. Everything else is contributes-only | A gate that fires on healthy input gets disabled, and a disabled gate is the E1 counterfactual undone |
| **D-5** | **May the reviewer ever raise a severity?** (§7.2) | **No.** Downward only; under-rating goes to `coverage_challenge`, which blocks phase completion. Enforced by the absence of `max` in `merge_review.py`, not by instruction | It is the difference between an additional filter and a parallel authority, and it is what makes the P1 compromise defensible |
| **D-6** | **Where does the Gate 1 environment refusal live** — `scope.parse()` or `gate_cli.cmd_approve()`? (§3.1) | **`cmd_approve()`.** `ScopeError` is DENY-by-contract and `scope.load()` is called by five scripts including `report.py`; a parse-time hard error blocks the report that would explain the refusal, and breaks eight test modules for no gain | It determines whether E1 is a contained change or a suite-wide one |
| **D-7** | **Freeze and git-tag `model_version` before the next engagement?** (§11.2) | **Yes.** Tag `rg-sev/1` before the next engagement. Without it, "we did not tune the model after seeing the answers" is an assertion rather than a checkable fact | Once the next engagement's findings exist, the freeze is no longer provable |
| **D-8** | **Adopt "one autopsy per two engagements" as cadence?** (§7.6) | **Yes.** It is the only thing that catches a systematically-wrong-downward reviewer, and it is a practice rather than a control — so it must be written into the cadence or it will be rediscovered the hard way | The residual it covers is not caught by anything mechanical in this document |
| **D-9** | **Do `.git/config` and source-map exposure stay at `info` until a rung exists?** (§5.4) | **Yes.** Do not invent a rung from one instance. Record `GRANT_AXIS_GAP`, take the extension path at three occurrences across two engagements | An invented rung is a fabricated severity; a recorded under-rating with a visible coverage record is recoverable |
| **D-10** | **Is `bucket_public`'s static `data: all` right?** (§5.2) | **Keep it, flag it.** Listing object *metadata* is not reading object *bodies*. It is the assignment most worth a reviewer challenge, and flagging it is better than tuning it before evidence exists | It is the only static assignment in the table that reaches the `high` band |

**Blocked on D-1 and D-2:** the schema is not implementable until both are answered. Everything in
§9.1 (release 1, coverage) is **not** blocked on either and should proceed regardless.
