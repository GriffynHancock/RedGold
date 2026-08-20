---
title: Strategic review — does the composition make sense, and what is nobody looking at
date: 2026-08-20
status: draft
question: Not "does the architecture work" but "does this composition cohere at all, where do the five sub-projects disagree about their shared nouns, what is nobody looking at, and does the business thesis survive the finding that the Privacy Act small-business deadline was never legislated?"
---

# Strategic review

Independent, bird's-eye. Read-only except this file. I reviewed `NORTH_STAR.md`, `CLAUDE.md`,
`status.md`, `README.md`, the briefing, the spec index, all five sub-project specs, the six named
research documents, and the two gitignored legal documents. I also measured the tree rather than
reading its self-description, per design judgement 5.

**Standing caveat.** Market facts, competitor capabilities and prices in §3 and §4 are marked with
their evidentiary strength. Anything from a vendor-comparison blog rather than the vendor's own
page is marked `[VERIFY]` and is directional only. I am not a lawyer and take no position beyond
what `privacy-act-feasibility.md` establishes.

---

## The three findings that matter most

### Finding 1 — RedGold has built a severity-grading system for findings it has almost no ability to produce

Measured against `HEAD`, not against any document:

| What exists | Size |
|---|---|
| Prose (specs + research, incl. the two gitignored files) | **23,947 lines** |
| Python | **7,576 lines** |
| Tests | **6,688 lines** |
| Agent cards, commands, skills, playbooks | 1,122 lines |
| **Playbooks in `playbooks/`** | **1 file — `_generic/adversarial-framings.md`. Zero test playbooks.** |
| **Actual detections the tool can perform** | **12 hard-coded checks in `baseline_scan.py`** — `/.env`, `/.git/config`, directory listing, `/admin`, `/ghost/api/admin/site/`, `/actuator/env`, a Supabase public-bucket path, `/static/js/main.js.map`, wildcard CORS, and three response headers |
| `obligations/`, `profiles/`, `evals/` | **Do not exist.** Specced in the briefing (§13.5), RG-3 §2, §9. |

That is roughly **2,000 lines of prose per detection check**. `findings.py` (947 lines, the
severity pipeline) plus `report.py` (576) plus RG-1's 1,697-line spec exist to correctly grade,
cap, dominate, review, and calibrate the output of nine hard-coded URL fetches.

This is not a criticism of the grading work, which is the best-reasoned thing in the repository and
is a direct, evidenced response to a real corpus of eleven bad findings. It is an observation about
**proportion**. RG-1 was designed against the prior engagement's findings — that is n=1 by the
project's own design judgement 1 — and the response to eleven bad findings has been a mechanism
capable of governing a thousand. Meanwhile the thing that produces findings at all is a fixed list
of nine paths, one of which (`/ghost/api/admin/site/`) is a hard-coded artifact of the single prior
engagement, and one of which (`/static/js/main.js.map`) will match approximately no modern build.

**The compounding question in the brief has a measurable answer.** Since 2026-08-04 the project has
added ~16,000 lines of documentation and **zero new detection capability**. RG-3 is the document
that would change this — pinned nuclei, testssl, ZAP, gitleaks, semgrep — and it is the one
sub-project explicitly gated behind RG-1 (RG-3 §10.1) and behind a real engagement (`status.md`
"Next steps" item 3). The ordering has the causality backwards: the severity model is being
finished against a corpus that only exists once the scanners run.

### Finding 2 — the composition does not cohere, in four places, and three of the four were created today by agents that could not read each other

Details in §1. In short: **environment divergence is modelled twice, incompatibly**
(`parity` block in `scope.yaml` vs `environment-delta.yaml`, 5 dimensions vs 12, boolean vs
tri-state, at scoping time vs after signature — and RG-4 explicitly rejects the design RG-2
assumes). **Rate authorisation depends on a questionnaire field that does not exist** (`scan_run.py`
requires `constraints.rate`; RG-4's E-block has no E2a and neither worked example emits the block).
**The scope model has silently become four artifacts, not three** (RG-3 adds `assets/surface.jsonl`,
which RG-1's coverage register and RG-4's scope record do not know about). And **the compliance
direction introduces a fourth parallel vocabulary for "a claim with evidence"** — `EVIDENCED` /
`GAP` / `CANNOT DETERMINE` — alongside `PROVEN`/`SPECULATED`, the `verified` enum and the
`confidence` enum, with a fifth `finding_class` bolted on.

None of these is fatal. All are cheap to fix now and expensive to fix after code exists. The reason
they are worth naming is structural: **~30 agents wrote ~16,000 lines in one day against
non-overlapping evidence, and nothing in the process reconciles their outputs.** The disagreements
are not carelessness; they are the predictable output of that process, and they will recur at the
same rate on the next such day unless something reconciles.

### Finding 3 — the client is the least-designed object in the project

There is a `report.py` that renders a plausible client document, and it is genuinely good: plain
headings ("What we found", "What you own that is exposed to the internet", "What we checked and did
not find", "Test data we created", "Limits of this assessment"), and it mechanically refuses to put
an unverified above-Low finding in the body. Credit where due — that is the client experience, and
it exists.

Everything else about the client does not. Across 23,947 lines of prose there is **no price, no
duration, no capacity model, no sales motion, no contract, no insurance position, and no
description of the second engagement**. The briefing's §13 deliverable table has four tiers and no
prices. The one commercial artifact anywhere in the corpus is a table in a gitignored legal
feasibility document (`privacy-act-feasibility.md` §7.2), and it prices the *compliance* product,
not the pentest. §12 of the briefing lists "engagement pricing model" under "Not built, but
required before paid work" and nothing has moved it since 2026-08-04.

The consequence is sharper than "we should do some pricing". **Every engineering decision in RG-2
and RG-3 has a cost per engagement, and none of them can be evaluated because there is no revenue
per engagement to weigh them against.** RG-2's containment build is 4–5 focused days plus a
possible $600–900 of hardware plus a topology that `containment-architecture.md` §7 concedes may
not fit in the operator's RAM. Is that worth it? Unanswerable today. If an engagement is worth
A$6,000 and the operator can run one a fortnight, it is obviously worth it. If the first three
engagements are favours, it is capital destruction. **The project has priced its controls in days
and its risks in defects, and has never priced anything in dollars.**

---

## 1. Does the composition cohere?

**Partly.** The vertical coherence is genuinely strong and I want to say so before the criticism:
RG-3 §4.2's dissolution of the `grants` problem — a scanner record held at RG-1's `low` ceiling
never crosses the threshold at which `grants` is required, so the unbounded-table problem is never
reached — is a real piece of composition, found by one document reading another's rules and
noticing they already compose. RG-2's §8.1 discovery that the environment cap plus production
testing implies a *per-engagement* headline sentence neither document states alone is another.
Those are the kind of finding this review was commissioned to look for, and two of them already
exist in the corpus. The specs are not written in ignorance of each other. They are written in
ignorance of each other's **same-day revisions**.

Assessed on the six shared nouns.

### 1.1 `environment` — **disagreement, material**

`environment` itself is consistent: one closed five-value vocabulary, defined in RG-1 §3.1,
consumed correctly by RG-4 Block D (which asks it in plain words and preserves `unknown` as a
sayable answer), and respected by RG-2 §8.1. That part is good work.

**The divergence between environments is modelled twice and the two models are incompatible.**

| | RG-2 §8.3 | RG-4 §8.3 |
|---|---|---|
| Artifact | a `parity:` block **inside `scope.yaml`** | **`environment-delta.yaml`**, a separate file |
| Dimensions | 5 (`tls_termination`, `authn_provider`, `env_config`, `data`, `infrastructure`) | 12 (`edge`, `rate_limiting`, `tls_and_certs`, `auth_provider`, `data`, `secrets`, `outbound_fanout`, `payment`, `build_and_debug`, `datastore`, `shared_components`, `access_control`) |
| Value type | `differs: true\|false` (boolean) | `same \| differs \| unknown` (tri-state, `unknown` costed as `differs`) |
| Source | *"filled from the scoping questionnaire (Part 2 of RedGold)"* | **explicitly rejects that**: "Rejected alternative: a fifth block of `rg-scoping`… Its respondent is different… its timing is different" |
| When | scoping time, client-declared | **after signature**, with the operator present and a named platform engineer |
| Downstream rule | a divergence in three named areas **blocks the "no findings" conclusion** | every `differs`/`unknown` becomes a report coverage line; three specific rows become **findings**; `unknown` raises non-blocking `ENV_DELTA_UNESTABLISHED` |

RG-2 names a mechanism it expects RG-4 to supply, and RG-4 — same date, same status — considered
that exact mechanism and rejected it with reasons. RG-4's design is the better one (the tri-state,
the twelve dimensions, the named human, the post-signature timing, and the "three of these rows are
findings, not context" rule are all improvements). But RG-2's `parity` block carries one rule RG-4
does not: **a divergence in TLS termination, environment config or infrastructure makes "we found
nothing" an unsupportable sentence about production.** That rule should survive the merge, and
today it lives only in the document that is about to be superseded.

**Recommendation:** delete `parity` from RG-2 §8.3, point it at `environment-delta.yaml`, and
migrate the no-findings block rule into RG-4 §8.4 as a fourth mechanical consequence.

### 1.2 `engagement` — **disagreement, and it is a lifecycle one**

Three documents assume three different engagement lifecycles.

- **RG-1 §9.1a** establishes that there is *no Claude Code lifecycle event for engagement close*,
  that `/rg:close` narrows "forgot a check" to "skipped a documented step", and that three hard
  refusals apply (stale deliverable, empty corpus, no completed phase).
- **RG-4 §9.3** extends close into a nine-item hard/soft preflight with `--override <item> --reason`.
  That is a good design, but it adds five new soft items sourced from artifacts (`environment-delta`,
  `scope-facts`, credential attestation, evidence retention, harvest) that **do not exist**, and it
  makes `/rg:harvest` an item on the checklist — a command `README.md` states is not built.
- **RG-2 §3.4 / §8.2** adds a *containment* lifecycle on top: provision, snapshot, handover,
  revert-to-snapshot as the abort button, teardown with `rg-reconcile`, key revocation. None of
  those steps appears in `/rg:close`'s completeness set, and one of them — reverting `rg-work` to
  snapshot — **destroys the machine the ledgers are on** unless evidence was pulled first. That
  ordering dependency is stated in RG-2 §3.4 step 6 and nowhere in RG-1 or RG-4.

An engagement is currently a directory (RG-1), a bundle-plus-directory (RG-4), and a VM pair with a
gateway ruleset (RG-2). Nothing owns the composite lifecycle. This is the disagreement most likely
to produce a real incident, because the failure mode is *losing an engagement's evidence at
teardown* and there is no test that would catch it.

### 1.3 `asset` — **disagreement, quiet and structural**

The briefing §5 is emphatic: **"three artifacts, three rules"** — `scope.yaml`,
`assets/register.jsonl`, `assets/candidates.jsonl`. RG-3 §5.7.2 adds a fourth,
`assets/surface.jsonl`, and does so with a good argument (a path is not a host; the register keys on
`(identifier, port)` and a path is unrepresentable). RG-3's authorisation analysis of it is careful
and correct — discovery is not attribution, and `scope_guard.py` needs no change.

The composition cost is elsewhere and RG-3 does not see it:

1. **Coverage now has two keys.** RG-1 §8.3's asset-coverage assertions and §8.2's zero-zero rule
   are keyed on assets. RG-3 §5.7.4 adds `SURFACE_UNDISPOSED` blocking `gate_cli.py complete
   --phase` on a *surface* row. A phase can now be complete under RG-1's rule and incomplete under
   RG-3's, and the code that ships today implements only the first.
2. **RG-4's `scope-record.yaml` has no surface concept**, so the client-side artifact that defines
   what may be touched cannot express the object RG-3 makes phase completion depend on.
3. **RG-3 §5.7.5 writes "`COVERAGE_EMPTY_PHASE` candidate" about a fuzz *run*.** A run is not a
   phase. RG-2's rate-control document introduces `run_id`, `scan.plan` and `scan.result` as a third
   unit of work alongside phase and engagement. Three units of work, three coverage rules, one
   `gate_cli.py complete --phase`.

### 1.4 `finding` — **coherent on the technical path; a fourth vocabulary is arriving on the compliance path**

On the technical side this is the strongest composition in the corpus. RG-3 §3.5 assigns
`discovered_by` the tool name, observes that `verified_by` is therefore absent, and lets RG-1 §4.5's
existing demotion rule impose the scanner ceiling *without a new rule*. That is exactly how
sub-projects should compose, and it should be held up as the standard.

The problem is on the compliance side. A "claim supported by evidence" is currently expressed by:

- `status`: `PROVEN` | `SPECULATED`
- `verified`: `none` | `replayed` | `executed` | `n/a`
- `confidence`: `confirmed` | `probable` | `unconfirmed`
- `precondition.established_by`: `demonstrated` | `scope-declared` | `client-declared` | `asserted` | `unestablished`
- and now, from `privacy-act-feasibility.md` §6.3: `EVIDENCED` | `GAP` | `CANNOT DETERMINE`, in a
  separate `assessments.jsonl`, with its own reason codes and its own close-time validator.

The privacy document says, correctly, *"Same rule, different domain. One mechanism, not two."* It
then specifies two. Five overlapping enums for one concept is how the prior engagement's severity
vocabulary got fitted to eleven findings — design judgement 1, applied to epistemics rather than to
playbooks. **Before Subsystem F is built, collapse these.** My read is that `status` and
`confidence` are the redundant pair and `established_by` is the one carrying real information.

### 1.5 `phase` — **underspecified rather than contradictory**

The briefing §4.3 gives workers Recon → Experiment → Test → Verify. RG-1 §8.2 makes a phase the
unit of coverage. The built `gate_cli.py` has `plan`/`approve`/`complete --phase`/`close`. RG-3 and
RG-2 add runs beneath phases. Nobody has written down what the phase list actually is for an
engagement, whether it is fixed or per-plan, or how a `posture`-mode engagement's phases differ from
an `audit`-mode one. This is small and cheap to fix, and it is the kind of gap that only shows up
when something tries to enumerate phases — which is precisely what `report.py`'s coverage section
does.

### 1.6 `evidence` — **one real collision, from the sovereignty document**

`data-sovereignty.md` §3.5 lands a distinction nothing else in the corpus makes: `11-governance.md`
§15.5 controls the *durable* evidence archive (encryption, 90-day destruction) and controls nothing
about the *transient* copy that crosses into model context — and on the document's reading of APP 8,
duration is irrelevant, so the transient copy is the cross-border event and the archive is not.

That composes badly with two things written the same day:

- **RG-4 §1.2** states, as a settled decision, *"Explicitly permitted to cross Anthropic's servers:
  everything"* — and records that decision in a spec the client never sees. `data-sovereignty.md`
  §4.2 item 4 calls the absence of that sentence from the client-facing skill *"the misleading-conduct
  exposure"*. Two specs, one day, opposite conclusions about the same disclosure.
- **RG-3 §3.4** introduces `evidence_mode: tool_output`, pointing `evidence_ptr` at a raw nmap XML or
  ZAP JSON. Those artifacts are unredacted by construction — `redact.py` operates on tool output in
  the transcript, not on files a tool wrote itself — and RG-3 §6.5 works out the redaction collision
  only for the *secrets* mode, not for `tool_output`.

### 1.7 Summary

| Noun | Verdict |
|---|---|
| `environment` | value vocabulary coherent; **divergence modelled twice, incompatibly** |
| `engagement` | **three lifecycles, no owner**; teardown can destroy evidence |
| `asset` | **fourth artifact added silently**; coverage now has two keys, work has three units |
| `finding` | technical path composes well; **compliance path adds a fifth epistemic vocabulary** |
| `phase` | underspecified — no canonical list |
| `evidence` | **transient vs durable copy collision**, plus an unredacted `tool_output` mode |

The operator's expectation was "at least two". It is four, and one of them (evidence at teardown)
has a data-loss failure mode.

---
## 2. The blind spots

Ordered by what they cost, not by how interesting they are.

### BS-1 — Nobody is designing the thing that gets sold

The framework knows a great deal about what must be *true* of a deliverable and almost nothing about
what it *is*. Concretely, none of the following is answered anywhere in 23,947 lines:

- **What does an engagement cost, and how long does it take?** No price, no day estimate, no
  capacity model. Directionally, Australian web-app pentests are quoted at roughly **A$4,000–10,000**
  for a small application `[VERIFY — vendor marketing blogs only; no quote obtained]`. That number
  is the denominator for every build-vs-skip decision in RG-2 and RG-3 and it has never been written
  down.
- **Why would they buy it twice?** NORTH_STAR's answer is the guardrail pack — *"the client's own
  coding agents leave with guardrails, checks, and regression tests"*, explicitly named as "the
  moat" and "the part nobody else is selling yet". **It does not exist.** `playbooks/` contains one
  file about how to run adversarial reviews of RedGold itself. There is no guardrail pack template,
  no client-side CLAUDE.md, no client hook set, no regression-suite generator, and no spec for any
  of them beyond three lines in briefing §13. The single stated differentiator has zero artifacts.
- **What does the client do on day one?** RG-4 answers this and its answer has a hole: `rg-scoping`
  *"runs in the client's own Claude, on the client's own machine"*. For a funded startup founder
  that is plausible. For the segment NORTH_STAR calls "the real market" — a conveyancing practice, a
  small retailer — the buyer does not have Claude, will not install it, and cannot be walked through
  a skill invocation. **The scoping design assumes the buyer is technical, and the business thesis
  says the buyer is not.** That is a straight contradiction between RG-4 §1.1 and NORTH_STAR's
  segment table, and it is the single most consequential unexamined assumption in the corpus.
- **What happens between engagements?** Briefing §13 tier 3 says "retainer + drift monitoring". No
  design, no cost, no trigger. `privacy-act-feasibility.md` §7.3 independently identifies the best
  recurring product in the whole corpus — a **breach-readiness retainer** priced against the s 26WH
  30-day assessment clock — and notes, accurately, that *"this is the best product in this document
  that nobody asked about."* It is still nobody's.

### BS-2 — The operator is a single point of failure and nothing is designed around it

Asked directly: what happens if the operator is unavailable for two weeks mid-engagement?

- The signed authorisation names them personally; there is no substitute tester provision.
- RG-2 §8.2 item 4 requires *"a live named contact and an abort path… with a phone number that
  reaches the operator"* for production testing. One phone, one person.
- The abort button is `revertToSnapshot` on the operator's laptop, reachable only by the operator.
- Evidence lives in `~/engagements/` on one machine. `engineering-infrastructure.md` §1 documents
  that even the *test results* are "a sentence an operator typed after running a command on a
  machine nobody else has". There is no stated backup, no encrypted offsite copy, no key escrow.
- There is no CI, so nothing but the operator can establish whether the tree is green — a fact that
  document already proves by finding `status.md` stale within hours.

The client-facing consequence is the one that matters commercially: a client under a real deadline
(an AUSTRAC enrolment, a due-diligence questionnaire) cannot buy from a supplier with no continuity
story, and enterprise-adjacent buyers will ask. The mitigation is not "hire someone". It is
**documented, testable handover**: encrypted offsite evidence backup, a written continuity clause in
the engagement contract, and CI so that "the suite is green" is a fact about a commit rather than a
memory. All three are cheap.

### BS-3 — Concentration risk on Claude Code is total, and the risk is capability change, not shutdown

The whole enforcement design is shaped around one closed binary the operator cannot fork. CLAUDE.md
states this and treats it as a settled constraint. It is a settled constraint; it is not a
quantified risk, and the corpus has already recorded two instances of the risk materialising
without noticing that they were instances of the same thing:

1. **Plugin-shipped agents cannot set `hooks`, `mcpServers` or `permissionMode` — silently ignored**
   (briefing §4.1). The entire two-repo layout, and `/rg:new` writing the engagement's
   `.claude/settings.json`, exists to route around that behaviour.
2. **Subagents cannot nest, and the failure is silent** (briefing §4.2). The whole "rg-lead runs in
   the main session, the command layer dispatches workers" architecture exists to route around that.
3. **There is no lifecycle event for engagement close** (RG-1 §9.1a). `/rg:close` exists because the
   harness has no hook that fires at the right moment, and `status.md` caveat 6 concedes the residual.

That is three load-bearing architectural decisions determined by undocumented or inconvenient
harness behaviour. Each is a decision that silently becomes wrong if the behaviour changes — and
two of the three failure modes are *silent* by the corpus's own description. **Nothing tests any of
them.** `verify_controls.py` injects faults into RedGold's code; nothing injects a harness change.

The proportionate response is not to abandon Claude Code — the reasoning for using it is sound and
the alternatives are worse. It is one small thing: **a harness-assumption register** listing every
behaviour RedGold depends on, with a runnable probe for each, run at session start. Perhaps six
entries. Without it, the first upgrade that changes hook dispatch turns the enforcement layer into
decoration and nothing announces it. This is exactly design judgement 8 ("verify external state
before asserting it") applied to the one external system the project cannot audit.

### BS-4 — Build-vs-buy was never asked, and the answer is not obviously "build"

Nowhere in the corpus is there a competitive assessment. What I could verify:

| Product | Position | Evidence |
|---|---|---|
| **Burp Suite DAST** (ex-Enterprise) | Quote-only since 2025; no published rate card. Aggregators put it at roughly US$6k–200k+/yr `[VERIFY — comparison blogs only]` | portswigger.net publishes no price |
| **Intruder** | Published tiers from **US$119/mo** (Essential), $239 (Cloud), $399 (Pro), plus per-target fees `[VERIFY — G2/SaaSWorthy, not the vendor page]` | This is the one that matters: it is *self-serve, published-price, SMB-shaped* |
| **XBOW** | **Pricing is quote-only**; the page says "Pricing is scoped to your environment… usage-based". The $4,000/$8,000 tiers circulating in comparison blogs are **not on xbow.com** | Verified directly against xbow.com/pricing, 2026-08-20 |
| **Horizon3 NodeZero** | No public pricing; median contract reported near US$18.6k/yr `[VERIFY — comparison blog only]` | — |
| **PrivacyScore / ComplianceKit** | Free 3-minute Australian Privacy Act assessment; **A$49 generated policy** | `privacy-act-feasibility.md` §7.1 — the operator's own research already found this |
| **Australian privacy consultancies** | ~$200–350/hr; readiness assessment $5k–25k `[VERIFY — directional]` | same |

Two conclusions the corpus has not drawn.

**First: the pentest market's floor is not empty.** Intruder is self-serve, published-price and aimed
at exactly this buyer. RedGold is not competing with XBOW (enterprise, quote-only, and per the
briefing's own §2.3 evidence, actively damaging its own category's reputation). It is competing with
a $119/month scanner the founder can buy with a credit card on a Tuesday. Against that, RedGold's
honest differentiators are **(a)** a human who verified each finding, **(b)** business-logic and
domain judgement, **(c)** the guardrail pack, and **(d)** — newly available and genuinely rare —
*"your data is processed in Sydney"* (`data-sovereignty.md` §4.1, costs an afternoon of Bedrock
configuration). Note that **(a), (b) and (d) are not the framework.** They are the operator, the
contract and a config file. Only (c) is a product, and (c) does not exist.

**Second: the strongest build-vs-buy answer is not about the scanner at all.** What RedGold uniquely
composes is *scanner output + a verification discipline + a legal-impact layer + a client-agent
handoff*, sold by one accountable person in Australia. No product on that list sells that bundle.
But every component except the verification discipline is currently unbuilt or bought, which means
**the moat is a bundle nobody has assembled yet, not a technology nobody has.** That is a fine
position — it is just a very different one from "we are building a better agentic pentester", and
the roadmap is currently written as if it were the latter.

### BS-5 — Time-to-first-revenue is not being tracked, and the trend is negative

The repository is 16 days old and has produced work on three of them. Today alone added ~21,300
lines, ~16,000 of it prose. Across all 16 days: **zero live external targets, zero paying clients,
zero invoices, and no artifact that describes how any of those would happen.**

The compounding test in the brief is answerable. Ask of each of today's outputs: *does this get
closer to a paid engagement?*

| Work | Moves toward revenue? |
|---|---|
| `privacy-act-feasibility.md` | **Yes, strongly.** It killed a false premise before it reached marketing, found two real dated hooks, priced four segments, and named the three blockers (#4, #15, #16). This is the highest-ROI document in the repo. |
| `data-sovereignty.md` | **Yes.** It converted a perceived architectural blocker into a config change and found a genuine differentiator. |
| `prior-engagement-autopsy.md` | **Yes.** Real corpus, real failure taxonomy, correctly identifies the cheapest high-yield gates. |
| `engineering-infrastructure.md` / `test-suite-review` / `rg1-code-review` | **Indirectly.** They are honest and they found real defects. They also all concern a tool with 12 detections. |
| RG-1 §7 adversarial reviewer, §4.3 domination, §4.7 scoring | **No.** Sophistication far ahead of the corpus it grades. |
| RG-2 containment, lab topology, hypervisor licensing/sizing | **No, and negatively.** ~2,000 lines and a 4–5 day build for a boundary whose necessity is asserted, not evidenced. See BS-6. |
| RG-3 | **Yes, if built.** It is the only document that increases what the tool can find. |
| RG-4 | **Yes, if built**, with the technical-buyer contradiction in BS-1 resolved first. |

The pattern is clear: **the research is compounding toward revenue and the specification is
compounding away from it.** The research consistently kills bad premises and finds cheap wins. The
specification consistently deepens machinery for hypothetical volume.

### BS-6 — The containment programme's necessity is asserted, not evidenced, and it is the biggest single spend

This is the unwelcome one. CLAUDE.md's containment argument is logically sound and I do not dispute
any step of it. What is missing is a **frequency estimate**. `containment-architecture.md` §2 ranks
prompt injection from a scanned target as *"most likely, by a wide margin"* — an ordering, with no
base rate, and the corpus contains no instance of it. The two agent-misbehaviour incidents that *are*
evidenced are both from the prior engagement and both are in-guest problems that in-guest controls
address: the 20-vs-10 request overrun (`no_handrolled_loops.py`, built) and the agent rewording its
own output to pass `scope_guard.py` (autopsy §D.2 — and note the off-host gateway would not have
stopped that either, since the write was to local disk).

Set against that: 4–5 focused days, a possible $600–900 hardware spend, ~2,000 lines of spec across
three documents, and a topology that `containment-architecture.md` §7 concedes probably **does not
fit in the operator's RAM** and forces `rg-work` and the daily workstation VM to become the same
machine — described there as *"the most likely practical obstacle to adoption"*.

The correct response is not to abandon containment. It is to notice that RG-2 itself already ranks
its own items and that **the top of that ranking is nearly free**: §2.1 non-sudo user, §2.2
root-owned hooks and `settings.json` ("the cheapest real control in RG-2"), §2.5 `--cap-drop=ALL`,
and §4 removing the `open-vm-tools` guest→host channel. Those are hours, not days, and they remove
the *agent edits its own controls* class outright. The gateway VM, the ruleset generator, the ulogd
normaliser and `rg-reconcile` are the expensive four-fifths, and they buy a boundary against a threat
with no observed instance and no client currently asking for it.

**The honest framing: containment is a prerequisite for the engagement RedGold has not yet sold, and
the cheap 20% of it is a prerequisite for the one it is about to.**

### BS-7 — The framework's controls are measured against themselves, never against a target

`verify_controls.py` breaks controls and asserts the suite goes red. Excellent, and rare. But
`test-suite-review-2026-08-20.md` establishes the ceiling on what that proves: **68% fine-grained
mutation score, with survivors clustered exactly on band boundaries, closed-vocabulary membership
and fail-closed defaults** — and the two weakest files (`no_handrolled_loops.py` at 25%,
`redact.py` at 55%) are *the two the framework most often describes as working*. The briefing §18
names the real acceptance test — *"re-run the prior engagement end-to-end under RedGold — same
findings, with resolvable evidence, no ROE violations, no cleanup debt"* — and it has never been
run. That is the only test in the corpus that measures the product rather than its scaffolding, and
it needs no client, no authorisation and no new code. It is sitting there unrun.

### BS-8 — Public repository, unfinished security tool, calibration claims

`status.md` correctly identifies the disclosure constraints of a public repo. Nobody has assessed
the *reputational* asymmetry. `github.com/GriffynHancock/RedGold` publishes, in the operator's own
words, a tool with an enforcement layer that is "defence-in-depth, not a security boundary", a list
of six things that are not enforced, and a test suite the project's own review scores at 68%. That
honesty is the product's differentiator and I would not dilute it. But a prospective client who
Googles the supplier finds a repository whose README's most prominent section is "What is NOT
enforced" — and a competitor asked to comment will read it aloud. The mitigation is not less
honesty; it is that **the public repo needs a client-facing front page** that leads with what the
service is, not with the framework's internal caveats. Right now the README is written for a
reviewer, and reviewers are not the audience arriving from a sales conversation.

---
## 3. The strategy question — does the thesis survive?

### 3.1 What the deadline finding actually killed

It killed a **timing** claim, not the thesis. NORTH_STAR's argument was never *"the law is
changing"*; it was *"small businesses hold personal data, have no compliance capability, and cannot
talk about risk without impact."* That is unchanged and correct. What the exemption finding removed
is the **forcing function** — the reason a small retailer would buy *this quarter* rather than never.

That loss is bigger than it looks, because a forcing function is what makes a cold outbound sale to
a non-technical small business possible at all. Without a deadline, the pitch reverts to selling
insurance against an abstraction to a buyer with no budget line for it. The operator's own research
says as much in §7.4's fairest statement of the case against, which I endorse: the market is
*"already served at the low end by free tools and at the high end by lawyers and consultants with
credentials the operator does not have."*

But `privacy-act-feasibility.md` also does the work of finding what replaced it, and the replacements
are better-qualified than the thing they replace:

- **AML/CTF tranche 2** — reporting entities since **31 March 2026**, core obligations since
  **1 July 2026**, AUSTRAC enrolment due **29 July 2026**, all verified against the amending Act's
  own commencement table. The population is nine nameable professions, all of which have fee income,
  an insurer, and an existing compliance habit. **The enrolment date is in the past**, which is a
  sharper opener than a future deadline: a missed enrolment is a present problem.
- **APP 1.7–1.9 automated-decision-making transparency, 10 December 2026** — verified verbatim,
  backed by an infringement notice via s 13K(1), applies to every existing APP entity, and triggers
  on any "computer program" that makes or substantially contributes to a decision about a person.
  **This lands squarely on AI-built products**, which is precisely the segment RedGold's technical
  work already serves. It is the single best-aligned commercial hook in the corpus and it is
  111 days away as of today.

### 3.2 Verdict on the thesis

**The thesis survives with one segment deleted and one re-ranked.**

- **Delete: cold outbound to non-technical small retailers.** The floor is A$49 and automated
  (PrivacyScore), the honest answer for most of them is "the Act does not apply to you", and RG-4's
  own design assumes a buyer who can run Claude — which this buyer cannot. This segment was the
  "real market" in NORTH_STAR and, on the operator's own research, it is the weakest of the four.
- **Promote: the compliance *layer* on technical work.** `privacy-act-feasibility.md` §7.2's last
  row is the commercially decisive one — **+A$1,500–3,000 attached to an audit already being done,
  because discovery is shared.** Same buyer, same engagement, same pipeline, marginal cost near
  zero, and no new go-to-market motion. §7.5 item 1 ("add obligation references to existing pentest
  findings") is cheap, legally safe and immediately valuable.
- **Promote: the ADM readiness check, timed to 10 December 2026.** Sold to the startup base that
  already exists, on a verified statutory obligation, about the exact thing those clients build.
- **Hold: the AML/CTF cohort**, but only behind the three gates the research names — a lawyer on
  unqualified practice (#4), a broker on PI cover (#15), and an engagement contract (#16). Those
  are weeks of elapsed calendar time, not days of work, and they should be *started now* precisely
  because they are elapsed-time-bound. Starting them costs an email.

### 3.3 Is agentic pentesting the right wedge?

**As the wedge, no. As the delivery mechanism, yes.** The distinction is the whole answer.

The evidence in the corpus argues against agentic pentesting as a *positioning*: briefing §2.1 puts
blind web-app discovery coverage at 4–14% and detection at 5–12.5%; §2.3 documents an entire market
turning against AI-sourced findings; §2.5 records an independent evaluation of an agentic pentester
fabricating a critical JWT finding and missing an admin panel with default credentials. NORTH_STAR
§"Positioning" already reaches the right conclusion — *"AI found it" now reads as a warning label* —
and RedGold's own hard rules exist to be defensible in exactly that climate.

So the wedge is not "an AI pentester". It is **"a named Australian security consultant who verifies
every finding, tells you what the law makes of it, and leaves your coding agents with guardrails —
and whose data never leaves Sydney."** Agentic tooling is how one person delivers that at a price a
founder pays. That is precisely NORTH_STAR's own "never lead with the tooling" rule, and the
roadmap has drifted away from it: four of the five sub-projects are about the tooling.

The compliance direction is more defensible and less technically risky — the research is right about
that — but it is also **more legally risky** (§5.2 unqualified practice, which pentesting does not
have) and it has a $49 floor. The correct read is not "pivot to compliance". It is:
**pentest is the wedge, compliance is the multiplier, and the compliance work should never be sold
standalone until a lawyer has cleared it.** That is exactly §7.5's sequencing, and the strategic
contribution of this review is simply to say that §7.5 should be *the roadmap*, not a section in a
gitignored document.

### 3.4 What I would do differently with the same skills and the same 16 days

Stated plainly, since it was asked. Roughly: days 1–2 on the same autopsy, because it is the
foundation of everything and it is excellent. Day 3 on `baseline_scan.py` plus **pinned nuclei with
a `low` ceiling** — RG-3's core insight is one page long and does not need 1,692 lines to state.
Days 4–5 building **one guardrail pack** for one stack, because it is the stated moat and it is the
only deliverable a client cannot get elsewhere. Day 6 writing a price list, a one-page scope
template and a contract skeleton. Days 7–10 running the framework against **the operator's own
property** end to end — the briefing §18 acceptance test — and fixing what breaks. Days 11–16
selling: three founders, free or near-free, in exchange for a written testimonial and permission to
generalise the playbook.

The severity model, the containment architecture and the questionnaire spec are all *better* than
what that plan would have produced. They are also all downstream of an engagement that has not
happened, and the plan above would have produced one.

---

## 4. What to stop doing

Specific, and deliberately unwelcome.

1. **Stop specifying ahead of implementation.** The corpus is now ~24,000 lines of prose against
   7,576 lines of code, and CLAUDE.md's own design judgement 6 says *"a spec that runs far ahead of
   code accumulates confident mistakes"* — a judgement recorded on the same day the gap tripled.
   **Impose a hard ratio**: no new sub-project spec until the previous one has shipped a release.
   RG-2, RG-3 and RG-4 are all specced and none is started; RG-1 is the only one with code and it
   shipped two critical defects.

2. **Stop the containment programme above its cheap 20%.** Build RG-2 §2.1, §2.2, §2.5 and §4 —
   non-sudo user, root-owned hooks and settings, capability drops, remove `open-vm-tools`. Hours,
   not days, and they close the *agent edits its own controls* class. **Stop** the gateway VM,
   the nftables generator, the ulogd normaliser, `rg-reconcile`, the mini-PC lab and the TLS-bump
   split until a client's scope requires it. That is ~2,000 lines of spec and 4–5 build days
   against a threat with zero observed instances and a topology that may not fit in RAM.

3. **Stop deepening RG-1.** Releases 1 and 2 shipped. The adversarial reviewer (§7), the domination
   ladder (§4.3), the exploitability delta (§4.7), the eight-rank capability vocabulary and the
   `production_nexus` five-value bypass are a grading system for a corpus of eleven findings from
   one engagement — n=1, by the project's own first design judgement. The two *un*built RG-1 items
   worth having are the ones the autopsy ranked cheapest and highest-yield (E1 environment gate,
   already shipped; E2 applicability filter). The rest should wait for a second corpus.

4. **Stop adding tests to the existing suite.** `test-suite-review-2026-08-20.md` establishes that
   the suite is at 68% fine-grained mutation score with survivors concentrated on exactly the
   boundaries that matter, and that 564→605 tests did not prevent two critical defects. Adding a
   606th test of the same kind buys nothing. If test effort is spent at all, spend it on the ~40
   named surviving mutations and on `no_handrolled_loops.py` (25%) and `redact.py` (55%).

5. **Stop treating the public repo as the shopfront.** It is a reviewer's document. Either give it
   a client-facing front section or accept that prospects should never be pointed at it.

6. **Stop launching ~30 agents in a day.** Four disagreements, all cheap to prevent and none
   detectable by any control in the repository, came out of one such day. The working preference in
   CLAUDE.md already says "one or two research agents at a time"; today's session violated the
   project's own written practice, and this review exists because of it. If a fan-out of that size
   happens again, **budget a reconciliation pass as part of it**, not as a separate engagement
   afterwards.

**What to keep, explicitly, because a critic who only subtracts is also useless.** The four
adversarial review rounds and `verify_controls.py`'s `breaks` field are the best engineering
practice in this repository and neither came from a tool. The `status.md` "NOT enforced" section is
worth more than any control it disclaims. `privacy-act-feasibility.md` and `data-sovereignty.md` are
the two highest-value documents produced to date and both paid for themselves within hours by
killing a false premise and dissolving a perceived blocker. The autopsy's failure taxonomy is real
knowledge derived from real evidence. And the calibration discipline — the refusal to state a
benchmark without a primary source, the `[VERIFY]` convention, the willingness to write "the
deadline does not exist" in the file that depended on it — is, on the evidence of §2.3 of the
briefing, the single most commercially valuable asset the project has.

---

## 5. The one thing

> **Run a complete engagement, end to end, against a target the operator owns — this week, before
> any further specification — and price it.**

Not a client. Not a live external target. The operator's own property, under the full pipeline:
`/rg:new` with a real authorisation document on disk, `/rg:scope` promotion with two signals,
`/rg:gate plan` and `approve`, `baseline_scan.py`, findings written with resolvable evidence,
`validate_findings.py`, `/rg:report`, `/rg:close`. Then write down the wall-clock hours it took and
what that implies about a price.

**The evidence for this being the one thing, in order of weight:**

1. **The project's own build plan already names it and it has never been run.** Briefing §18:
   *"Overall acceptance: re-run the prior engagement end-to-end under RedGold — same findings, with
   resolvable evidence, no ROE violations, no cleanup debt."* It requires no client, no
   authorisation from anyone else, no containment build and no new code.
2. **CLAUDE.md design judgement 6 predicts what it will find**: *"Nearly every real defect found on
   2026-08-20 came from an agent trying to build something and discovering it could not — not from
   anyone reading for errors."* Four of the four composition disagreements in §1 are the kind an
   end-to-end run surfaces immediately and no amount of reading surfaces reliably.
3. **It is the only action that resolves all three lead findings at once.** It converts the
   detection deficit from an argument into a measurement (Finding 1); it forces the sub-projects to
   agree because one pipeline has to actually run (Finding 2); and it produces the first honest
   duration number the project has ever had, which is the missing denominator for every
   build-vs-skip decision (Finding 3).
4. **Every previously-run version of this exercise paid off immediately.** The autopsy — one
   backward-looking pass over one real engagement — generated RG-1 in its entirety. A forward pass
   over a real engagement is cheaper and will generate more.
5. **`status.md`'s own next-steps list already implies it** and has been blocked for 16 days on a
   fact the operator has not supplied ("once the operator supplies the facts §15.1 requires"). An
   operator-owned target removes that block entirely, today.

The second thing, if there is capacity for two: **send the three legal/insurance questions
(`privacy-act-feasibility.md` §8 items #4, #15, #16, plus #14B on Criminal Code Part 10.7) to a
lawyer and a broker this week.** They gate all paid work, they are elapsed-time-bound rather than
effort-bound, and starting them costs one email each. Every week they are not started is a week
added to time-to-first-invoice regardless of how much gets built.

---

## Appendix — evidentiary status of external claims in this review

| Claim | Status |
|---|---|
| Repository line counts, file inventory, detection-check count, commit dates | **Measured** against `HEAD`, 2026-08-20 |
| XBOW publishes no prices; page says "scoped to your environment" | **Verified** — xbow.com/pricing, read 2026-08-20 |
| Burp Suite DAST is quote-only; no rate card on portswigger.net | **Verified** by absence; dollar range is `[VERIFY]` |
| Intruder tiers US$119/$239/$399 per month plus per-target fees | `[VERIFY]` — G2/SaaSWorthy/comparison blogs, not the vendor pricing page |
| NodeZero median contract ≈ US$18.6k/yr | `[VERIFY]` — single comparison blog |
| Australian web-app pentest ≈ A$4,000–10,000 small app | `[VERIFY]` — Australian vendor marketing pages only; no quote obtained. Directional |
| PrivacyScore free assessment + A$49 policy; consultancy $200–350/hr; readiness $5k–25k | Reproduced from `privacy-act-feasibility.md` §7.1, which marks the pricing `[VERIFY]` |
| AML/CTF dates (31 Mar / 1 Jul / 29 Jul 2026); APP 1.7–1.9 on 10 Dec 2026; s 6D intact | Verified **in `privacy-act-feasibility.md` §8** against primary sources; not re-verified here |
| Bedrock `au.` Australia inference profile; Claude Code Bedrock support | Verified **in `data-sovereignty.md` §2** against vendor docs; not re-verified here |
| Benchmark figures (4–14% coverage, 5–12.5% detection, 15–46% FPR) | Cited in briefing §2.1 to arXiv identifiers; not re-verified here |

No document needed for this review failed to retrieve, so nothing has been appended to
`/home/hiranya/REDGOLD-NEEDS-FROM-YOU.md`.

**Sources consulted for the competitive section:**
[xbow.com/pricing](https://xbow.com/pricing) ·
[codeant.ai Burp Suite pricing](https://codeant.ai/blogs/burp-suite-pricing) ·
[G2 Intruder pricing](https://www.g2.com/products/intruder/pricing) ·
[SaaSWorthy Intruder](https://www.saasworthy.com/product/intruder) ·
[codeant.ai NodeZero pricing](https://codeant.ai/blogs/nodezero-pricing) ·
[Intrix — pentest cost Australia](https://intrix.com.au/blog/how-much-does-a-penetration-test-cost-in-australia/) ·
[Penvasecurity — pentest cost](https://penvasecurity.com.au/penetration-testing-cost/)
