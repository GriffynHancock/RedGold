---
title: RedGold — adversarial rearrangement (a proposal, not the current design)
wiki_id: architecture-proposed
question: If every decision in RedGold is assumed wrong until proven otherwise, which ones survive, which fail, and what rearrangement minimises risk?
subject: RedGold architecture
status: partial
last_verified: 2026-08-20
verified_against: docs/wiki/architecture/current.md at the same commit; primary sources cited inline
recheck_trigger: this document is an argument, not a record. Re-run the attack after any of its proposals is adopted, and after any commit that changes what current.md §6 says.
sources:
  - url: docs/wiki/architecture/current.md
    kind: primary
  - url: docs/specs/rg2-containment.md
    kind: primary
  - url: docs/specs/rg1-finding-integrity.md
    kind: primary
related:
  - architecture-current
---

# Adversarial rearrangement — **a proposal**

> **Read this line before anything else.** Nothing in this document describes RedGold. Nothing in
> it has been adopted or decided. It is an argument written to be attacked in turn. The
> description of RedGold is [current.md](current.md).

## 0. Method, and its failure mode

The standard applied, literally: **every decision is wrong until proven otherwise mechanically,
through strict logic, or by a high-authority primary source.** For each decision below: *what would
have to be true for this to be right*, then *whether it holds*.

**The failure mode of this method is deference**, and the second failure mode is its opposite — a
proposal that changes everything is exactly as suspect as one that changes nothing. So §2 is the
list of decisions that **survive**, and it is deliberately first and deliberately long. A design
audited on 2026-08-20 by four adversarial rounds and 21 fixed defects should mostly survive; if it
did not, either the rounds were theatre or this attack is.

Nine decisions are attacked. **Five survive, three fail, one survives on different grounds than
the ones given for it.**

---

## 1. What the attack is aimed at

Not at whether the controls are correct. RG-1, RG-2 and RG-3 are unusually rigorous about their own
limits, and the four audit rounds found real defects. The attack is aimed at the **shape**: whether
the pieces are cut at the right joints, and whether anything exists because of the order it was
built in rather than because it is right.

The evidence base for the attack is `current.md` §6 — nineteen controls whose declared input is
unproduced, produced later, or overwritten before the read. That is not nineteen unrelated bugs.
**It is one missing artifact, nineteen times.**

---

## 2. Decisions that survive the attack

### 2.1 The boundary is the network — **survives, and it is the strongest argument in the repo**

*What must be true:* (a) the harness cannot be modified without owning a fork forever; (b) a
sandbox tight enough to be a boundary breaks scanner tooling; (c) a filter on a different machine
constrains a fully-compromised workload.

(a) is stated by Anthropic's own documentation about hooks vs CLAUDE.md
`[SOURCE: docs/REDGOLD-BRIEFING.md §2.4, quoting the Claude Code docs verbatim]` and by the fact
that Claude Code is a closed binary. (b) is argued concretely in `rg2-containment.md` §2 with
per-measure reasoning — `noexec` breaks nuclei helpers, `rbash` is defeated by `python3 -c`, a
custom seccomp profile fails as `EPERM` inside a binary nobody maintains. (c) is definitional.

All three hold. **Do not rearrange this.** The one thing worth adding is that the argument is
currently *load-bearing for a component that does not exist*, so its rhetorical strength is
unearned in practice — see §4.3.

### 2.2 The containment build order — **survives**

`rg2-containment.md` §9.1 orders: ledger rows → `.vmx`/`open-vm-tools` → gateway → generators →
proxy → ulogd → reconciler → template → provisioning → end-to-end. Attacked on the obvious ground
(*why is the boundary third and not first?*) it holds: step 2 closes a **boundary-precondition**
hole that is live today, and §1.2's distinction — a precondition failure *bypasses* the boundary
rather than weakening it — is strict logic, not preference. A gateway built before the guest→host
RPC channel is closed is a gateway with a documented route around it.

The one correction §4 proposes is not to the order but to what precedes step 1.

### 2.3 `rg-lead` in the main session — **survives**

*What must be true:* subagents cannot nest, and the failure is silent. The nesting constraint is
corroborated from a second project's post-mortem (*"silently collapsed: delegation failed open, no
specialized executor ever ran"*) `[SOURCE: docs/specs/redgold/06-agents.md §8.0]`. The
consequence — a pipeline reporting success while doing nothing — is the worst available failure for
a security tool. `rg-lead` also holds no `Bash` and no `WebFetch`, which makes "the orchestrator
drifted into first-hand verification" structurally impossible rather than discouraged.

Holds. `no_nesting.py`'s wiring is broken (`current.md` D-8), which is an implementation defect,
not a reason to revisit the decision.

### 2.4 Plan-time approval rather than per-action approval — **survives**

*What must be true:* constant prompting trains reflexive approval, and never asking produces the
Strix posture. Both counter-examples are named and quoted
`[SOURCE: docs/REDGOLD-BRIEFING.md §15]`. The claim that judgement is worth most when deciding
*what will be done* is strict logic about where information is highest.

Holds — but note it is currently a **decision without a gate**: `current.md` D-14 shows no action
in the engagement carries a `gate_ref`, so plan-time approval is a recorded intention rather than a
precondition of anything except a `rate_probe.sh` burst. The decision survives; its implementation
is one field short of being real.

### 2.5 Two repositories, permanently separate — **survives**

*What must be true:* client data must never enter the framework repo, and the framework repo is
public. Both are stated facts, and the second makes the first unusually consequential. The layout
is forced by a second constraint that is primary-sourced: plugin-shipped agents cannot set `hooks`
`[SOURCE: docs/wiki/claude-code/hooks.md §4, quoting plugins-reference verbatim]`, so `/rg:new`
must write the engagement's `settings.json`.

Holds. One under-stated consequence belongs in the design rather than in a footnote: **the
enforcement layer is regenerated per engagement by a script the workload can read**, and its
integrity depends entirely on `rg2-containment.md` §2.2's root-ownership control, which is unbuilt.
That is the correct place for the risk to sit, but it should be named in `status.md`.

### 2.6 The fail-closed direction rule — **survives, and it is the design's best-composing idea**

*"'Fail closed' names a direction, not a value, and the direction is always the one that does not
reduce what the client is told"* (RG-1 §3.4). `current.md` §8.7 records six independent
implementations by different agents, none of which points the wrong way. This is the only place in
the audit where composition worked without coordination, and the reason is instructive: **the rule
is stated as a direction rather than as a value**, so it survives being re-derived. Every rule in
§4's proposals is written the same way for that reason.

---

## 3. Decisions that fail the attack

### 3.1 The five sub-projects are a dispatch artifact, not a decomposition — **fails**

*What would have to be true:* the five carve at joints where artifacts are separable, so each can
be specified and shipped without editing another's files.

It does not hold, and the evidence is mechanical:

| Sub-project | Files it must edit to land |
|---|---|
| RG-1 | `findings.py`, `report.py`, `gate_cli.py`, `scope.py`, `baseline_scan.py` |
| RG-2 (containment) | `scope_guard.py`, **plus a `parity` block in `scope.py`** (§8.3) |
| RG-2 (rate control) | a new `scan_run.py`, **plus `scope.yaml` keys** (§4) |
| RG-3 | new `profiles/`, **plus `findings.py`'s scanner ceiling**, which it inherits from RG-1 and which is unbuilt |
| RG-4 | **`scope.py`'s `authority`/`platforms` blocks — named as "the smallest blocking item" (D-3)** |

**Four of five need edits to two files owned by a fifth**, and the fifth's own §9.2 records that
three of its five items did not land. Two documents share the number RG-2 and have no artifact in
common. A decomposition designed at the seams would not have that shape; a set of research
dispatches, each given its own topic on one day, would have exactly that shape.

The joint the work actually has is not topical. It is **schema versus everything else**.

> **Proposal R1 (see §4.1): extract RG-0 — the record schema, the scope schema, the ledger
> envelopes, and the producer/consumer contract — as a sub-project the other four consume.**

### 3.2 The roster cap is right; the reason given for it is wrong — **fails on its stated grounds**

*What would have to be true:* the cap exists because *"flooding Claude with options makes automatic
delegation less reliable"* `[SOURCE: docs/specs/redgold/06-agents.md §8]`.

That argument is about **automatic delegation by description-matching**. RedGold does not use it:
§8.0 of the same document states *"the **command layer** dispatches workers"*, and §8.4 describes
the `description` field as the router. Both cannot be true. If dispatch is by command, the number
of agents is irrelevant to routing reliability and the cited justification does not apply.

The cap is still defensible on a ground the document does not give: **each agent is a maintained
artifact** — a card, a tool grant, a memory policy, a CI check in `validate_agents.py` — and seven
is what a solo operator can keep in step. That is a maintenance argument, and it is the one that
should be written down, because it predicts different things: it says *do not add an eighth without
retiring one*, and it says nothing about descriptions.

Two membership questions follow from applying the corrected reason:

- **`rg-surface` and `rg-webtest` have identical tool grants and no mechanism distinguishing
  them.** The distinction is a phase discipline (fingerprint before exploit) that nothing enforces,
  plus one instruction to run `baseline_scan.py` first — which is a command, not an agent. Two
  maintained artifacts for one enforceable behaviour.
- **`rg-verify` cannot perform its role as specified** (`current.md` §8.1). This is *not* an
  argument for removing it; P2 requires it. It is an argument that the roster question is
  **downstream of RG-1 E4**, not upstream, and that debating the roster before `review.jsonl`
  exists is debating a shape with a hole in it.

### 3.3 The questionnaire as a Claude skill — **fails; the medium is doing almost none of the work**

*What would have to be true, all four:*

1. **The client has Claude and will run a skill in it.** No evidence anywhere in the repo. The
   target client is *"non-technical founders"*; RG-4 assumes without discussion that they operate a
   Claude session on their own machine against their own documents. `[VERIFY]` — this is an
   adoption assumption sitting on the critical path of every engagement, and it is unpriced.
2. **A conversational agent extracts better answers than a form.** Plausible, and RG-4's best
   content is evidence *against* the medium mattering: A3's spend-and-access phrasing, C2's
   warning-inside-the-question, B7's "have you told the people who'd notice", the layer-3 read-back.
   **Every one is a property of the question, not of the model asking it.** A static form carries
   all of them.
3. **Document-reading is load-bearing.** This is the one thing only a model can do — and RG-4
   itself closes it off. §2.2 layer 2: `rg4_ingest.py` *"refuses a bundle in which … any answer's
   provenance is `document` alone."* §2.4: document hashes are *"not evidence of what the file
   says."* §3.3: nothing derived from a document alone may land in `in_scope`. **By the design's own
   rules, no document may produce any field that matters.** The skill reads documents in order to
   ask better questions — real, and small.
4. **Non-enforceability is acceptable.** RG-4 §10 concedes it directly: *"It is a prompt. A user
   who wants a different bundle can get one."*

Three of four are weak or self-refuted. And the mechanical part of RG-4 — `rg4_ingest.py`, the
`scope.py` schema blocks, and the engagement-document template — is **identical either way**.

> **Proposal R4 (§4.4): ship the form and the ingester; make the skill an optional accelerator over
> them, not the delivery mechanism.**

### 3.4 The compliance track shares scoring machinery it must not share — **fails**

*What would have to be true:* a compliance gap and an exploited defect are the same kind of claim,
scoreable on the same axes.

They are not, and the code already shows it. `finding_class: compliance` is in `FINDING_CLASSES`
and in neither carve-out, so today (`current.md` D-18):

- it is capped through the **exploit** column of the environment table — an obligation gap becomes
  `medium` because it was observed on a dev box, which is incoherent: the obligation attaches to
  the organisation, not to the host;
- `verified: "n/a"` — its only honest value — raises blocking `NA_NOT_PERMITTED`.

**Every compliance finding is currently unrepresentable**, and the vocabulary shipped ahead of the
machinery.

What survives: **shared storage, shared validation of shape, shared report assembly, shared
evidence discipline.** RG-1's own argument for one implementation of the cap — *"two independent
cap implementations would be two things to keep in step"* — is correct and applies here too.

What must not be shared: **the severity model.** And one thing must be added before any compliance
content moves at all — `report.py` claims to strip `[VERIFY]` content and contains no such check
(`current.md` D-19). Subsystem F is entirely `[VERIFY]`; sharing a report path with it while that
claim is a docstring is how hard rule 1 gets broken by a component that says it enforces it.

---

## 4. The rearrangement

Ordered by risk reduced ÷ cost. Each states: **the risk it reduces · what it costs · what it
breaks · how it would be verified.**

### 4.1 R1 — RG-0: a dataflow contract, and field ownership

**The proposal, in two parts.**

*Part A — the contract.* `current.md` §3–§4 becomes a maintained artifact: an ordered lifecycle and
a per-field table of producer, lifecycle point, mutators and readers. Machine-checkable, and
checked: `verify_controls.py` gains a pass that, for every validator code, asserts at least one
fixture record produced by a **declared producer** — not hand-written by the test — triggers it.

*Part B — field ownership, stated as a direction.* Split every schema field into
**producer-writable** and **derived**. `severity_derivation`, `environment_at_test`, and the
`production_nexus` `code_defect` default are derived; `severity`, `verified`, `evidence_ptr`,
`created` are producer-writable. **A record in which a producer supplied a derived field is
refused.** This is the S1 lesson (*"a security decision must not read from a mutable,
producer-supplied field"*) generalised from one field to a rule.

**Risk reduced.** All nineteen defects in `current.md` §6 are one missing artifact. Part A makes
the class detectable; Part B makes the specific sub-class that produced S1, D-5, D-6 and D-7
unrepresentable. It also removes the reason those four fixes failed to generalise: today a fix is
verified against the path that produced the bug report and no other, because nobody knows what the
other paths are.

**Cost.** Part A: the table already exists (`current.md` §4); making it authoritative and adding the
`verify_controls.py` pass is perhaps a day. Part B: a constant, a check in `validate_record`, and
one injected fault.

**What it breaks.** Part B breaks the `SubagentStop` path for any record where an agent legitimately
carries a prior derivation — which is exactly the case `apply_environment_cap`'s
carry-forward logic handles today, and that logic would have to move behind the derived-field
check rather than in front of it. This is the highest-risk part of the proposal and must be
designed against a real corpus, not asserted.

**Verification.** The pass exists and is red before the fix. Then: delete any producer from the
contract and assert a control that reads its field is reported as unreachable. **A control with no
declared producer for one of its inputs is a build failure**, in the same way an agent card granting
`Bash` without the scope-guard marker is already a build failure
`[SOURCE: docs/REDGOLD-BRIEFING.md §7.1, the CI invariant]`.

### 4.2 R2 — the agent output contract, before any further control

**The proposal.** `06-agents.md` §8.7 already requires it: *"every worker card carries an explicit
Output Contract section specifying the exact JSON it must return."* No card has one
(`current.md` §2.1c). Write them, from `findings.py`, and add a CI check in `validate_agents.py`
that every card granting `Write` (or `Bash`, which is a write path — RG-1 §7.3) declares the
contract, and that every field the contract names exists in `FINDING_CLASSES`/`REQUIRED_FIELDS`.

**Risk reduced.** This is the single highest-leverage item in the list, because roughly twenty
built, tested, fault-injected controls currently validate a record shape **no agent has ever been
told to produce**. It closes D-1 outright (`created` gets a producer, so `REPORT_STALE` stops
firing on 100% of real engagements), gives `phase` a producer (D-2), and is a precondition of E3
and E4 having any meaning.

**Cost.** Small — six card sections and one CI check. It is *not* a mechanism: an agent card is an
instruction, per CLAUDE.md design judgement 4, and this proposal must be recorded as raising
compliance rather than enforcing it. **The mechanical half is D-15**: if `agent_type` really is on
`SubagentStop` stdin, `validate_findings.py` can stamp `discovered_by` and `created` itself,
converting the two most load-bearing fields from instruction to mechanism. **`[VERIFY]` that first
— two documents in this repo contradict each other on it and neither has been checked against a
running hook.**

**What it breaks.** Nothing in the current suite. It will make `/rg:close` start refusing for the
*right* reasons on corpora that previously passed by accident.

**Verification.** Run a worker end-to-end against a scratch target, take the record it writes
unedited, and run `validate_findings.py` over it. **If a fresh agent-written record does not pass,
the contract is wrong, not the agent.** No fixture may be hand-authored for this test.

### 4.3 R3 — stop the deterministic baseline fabricating criticals, before the next engagement

**The proposal.** Two changes, both already specified and neither built:

1. `baseline_scan.make_finding` stops writing `"verified": "executed"` (RG-1 §4.5's paired change).
2. `Check` gains `grant_evidence`, and a check whose `detect` reads only `probe.status` is pinned
   to the info band, enforced by an assertion over `CHECKS` at **import time** (RG-1 §5.3).

**Risk reduced.** `current.md` D-10 and D-11 compose into the design's worst live failure: against a
single-page application that returns `200` for unknown paths — the modal shape for exactly this
client segment — the baseline emits a **critical** and two **highs**, self-certified
`verified: executed`, `confidence: confirmed`, with resolving evidence, which pass every gate in
`validate_record` and every branch of `report.classify` and land in **What we found**. That is the
Wavestone failure (*"fabricated a critical … with a proof-of-exploit that did not work"*)
reproduced by the component built to prevent it, and it is the fastest way for a solo contractor to
lose a client permanently.

This is listed third only because R1 and R2 change the shape of the system. **On a schedule, it goes
first**, and it is the one item on this page that should block the next engagement.

**Cost.** Two small changes, both already designed. RG-1 §9.2 gives the injected faults verbatim.

**What it breaks.** `tests/test_baseline_scan.py` asserts `verified == "executed"` on
`present=True`. RG-1 §9.2 names this and says those assertions become `"none"`. It also, correctly,
parks every above-Low baseline hit at `low` — which is a **product statement** (D-2 in RG-1's
numbering: *pinned scanner output is `low` until an agent verifies it*) and needs the operator's
sign-off, not an engineer's.

**Verification.** Point `baseline_scan.py --target` at a local SPA that serves `200` for every path.
Today it produces a critical. After the change it must produce three info-band records and no
critical. **Drive the real code against a real 200-for-everything origin; do not assert it in a
fixture.**

### 4.4 R4 — de-risk RG-4 by shipping the form, not the skill

**The proposal.** Build, in order: (1) the engagement-document template and the static
questionnaire, carrying RG-4 §3's exact question phrasings; (2) `scope.py`'s `authority` and
`platforms` blocks (RG-4 D-3, *"the smallest blocking item"*), plus `parity` (RG-2 §8.3), plus
`environment_established`/`environment_source` (RG-1 §3.1); (3) `rg4_ingest.py`. The `rg-scoping`
skill becomes an optional accelerator over the same bundle format.

**Risk reduced.** Removes an unpriced adoption assumption (client-has-Claude) from the critical path
of every engagement. More importantly it unblocks step (2), which **four of five sub-projects need**
(§3.1) — and step (2) has a defect waiting for it: `scope_cli.py amend` rewrites `scope.yaml` from
`Scope.to_dict()`, so **the first amendment after `parity` lands deletes the client's signed
attestation of dev/prod divergence** (`current.md` D-12). Fix `to_dict()` completeness — or make
`amend` an in-place edit rather than a re-serialisation — in the same commit as the first new block.

**Cost.** Roughly the same total work, differently ordered. The skill is not discarded; it is
demoted from mechanism to convenience, which is what RG-4 §10 already says it is.

**What it breaks.** Nothing built. It changes RG-4's framing from *"a fourth system with the weakest
trust properties"* to *"a document, plus an ingester that is the actual control"* — which is a more
honest description of what RG-4 §10 concludes.

**Verification.** Round-trip: take a filled form, run `rg4_ingest.py`, run `/rg:new`, and assert the
resulting `scope.yaml` is byte-identical to one produced from the bundle the skill emits for the
same answers. Then amend the boundary and assert **no key is lost** — the D-12 regression.

### 4.5 R5 — three smaller rearrangements, stated without ceremony

| # | Change | Risk reduced | Cost | Breaks |
|---|---|---|---|---|
| R5a | Add `compliance` to `NO_EXPLOIT_CLASSES` (or give the cap table a third column) and make `report.py` refuse to render a document containing `[VERIFY]`, with the RG-1 §11.2 deny-list and its injected fault | D-18 + D-19. The second is the only mechanical guard on hard rule 1 | Two functions, two faults | Nothing; both are additive |
| R5b | Fix the four wiring defects: `no_nesting` matcher (D-8), `redact` matcher (D-9), `not_attempted` in the two remaining readers (D-3), and a finding-id allocator (D-13) | Four inert or actively harmful controls, one of which silently drops a real finding from a client document | Under a day | The id allocator changes `baseline_scan`'s numbering; evidence filenames move once |
| R5c | Merge `rg-surface` into `rg-webtest`, or give the two a mechanically enforced distinction | One fewer maintained artifact, or one real control instead of a prose phase boundary | Small either way | Routing descriptions; `validate_agents.py` |

R5b is listed last and is the cheapest thing on the page. **Do it first anyway** — it is under a day
and it converts four things that read as coverage into four things that are.

---

## 5. What this proposal deliberately does not change

Named because a proposal that changes everything is as suspect as one that changes nothing.

- **The containment topology and its build order.** §2.1, §2.2. The gateway VM, the three-VM split,
  the `.vmx` keys, the decision to decline restricted shells and custom seccomp profiles, the
  refusal to build honeypots — all of it survives, and the reasoning in `rg2-containment.md` §§1–2
  and §6 is the best-argued material in the repo. The only change §4 makes near it is that R5b's
  wiring fixes and R1's contract are prerequisites for step 7's reconciler being meaningful, which
  RG-2 §9.2 half-anticipates.
- **The scope model.** Three artifacts, two-signal attribution, IP never counting alone, the
  untouchable candidate queue, the tier-0/1 carve-out that stops the invariant deadlocking. Each is
  primary-sourced or forced by a stated deadlock. The one gap — `load_register` folding away the
  port (`current.md` §6.1) — is an implementation defect.
- **The mode/tier model.** `posture`/`audit`/`redteam` is close to a label for an integer ceiling,
  and was attacked on that ground. It survives because the modes are also the **commercial product
  tiers**, and collapsing them to a number would lose the thing the client is buying. Noted rather
  than changed.
- **Plan-time approval, the nesting resolution, the two-repo split, the fail-closed direction
  rule.** §2.3–§2.6.
- **`baseline_scan.py` existing at all.** P10's argument — *judgement decides where to look next; it
  never decides whether to check the obvious* — is sound and evidenced. R3 changes what it may
  claim, not whether it runs.

### 5.1 One thing attacked and left open

**Is `baseline_scan.py`'s checklist fitted to n=1?** Three of its nine checks are shaped by one
engagement's stack: `/ghost/api/admin/site/`, `/actuator/env`, and `/storage/v1/object/list/public`
— which is literally the Supabase Storage API path, presented as a fingerprint-free check. CLAUDE.md
design judgement 1 forbids designing from n=1, and the spec applied that judgement to the *playbook*
tier while the *unconditional* tier kept the fitted paths.

This is not proposed as a change, because the counter-argument is real and unresolved: a
fingerprint-free checklist has to guess paths from somewhere, and §2.2's market evidence says
Supabase and Firebase *are* where this client base lives. **Recorded as an open question with a
decision rule attached: if the second engagement's stack shares none of these three paths, the
checklist is fitted and must be re-derived — not extended.**

---

## 6. Residuals this proposal does not touch

Stated in the style of `status.md`'s NOT-enforced section, because a proposal that lists only its
wins is doing the thing P9 forbids.

1. **Operator manipulation through findings.** `rg2-containment.md` §10.1 item 2 calls it the
   highest-severity residual in the system and says it is procedural, not architectural. Nothing in
   §4 touches it.
2. **Harm at a permitted destination.** The firewall does nothing for it; the rate-control document
   addresses it and is unbuilt.
3. **A systematically-wrong-downward reviewer.** RG-1 §7.6's honest residual. Caught only by an
   outside autopsy, which is a practice and not a control.
4. **The whole severity model is unvalidated.** No out-of-sample measurement of any rule exists, and
   the `8 of 11` retrospective score is barred from client-facing use for good reasons.
5. **Every conclusion this document leans on is one agent's analysis** and has not itself been
   audited. Several such conclusions were overturned on 2026-08-20, including a prescribed defect
   fix that was wrong.
6. **The `[VERIFY]` items in §3.3 and §4.2 are the two that would change this document most.** If
   the client-has-Claude assumption holds after all, R4 shrinks to a sequencing note. If
   `agent_type` is on `SubagentStop` stdin, R2's mechanical half exists and R2 gets substantially
   stronger. Neither has been checked.
