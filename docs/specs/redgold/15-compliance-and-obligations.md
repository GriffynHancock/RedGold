---
title: Compliance, obligations, and impact
question: What legal and framework obligations attach to this client's assets, and what does non-compliance cost them?
sections: [21]
spec: RedGold design
status: draft — RESEARCH REQUIRED, see §21.8
date: 2026-08-04
---

## 21. Compliance, obligations, and impact — **Subsystem F**

> **Status warning.** This document is a *structure*, not a legal reference. Every specific
> obligation, threshold, penalty figure and commencement date below is marked `[VERIFY]` and must be
> confirmed against primary sources before it reaches a client deliverable. Fabricated legal detail
> would be worse here than anywhere else in the spec. See §21.8 for the research plan.
>
> **RedGold does not provide legal advice.** It maps technical findings to obligations a client
> should raise with their own adviser, and it says so in every deliverable.

### 21.1 Why this is the spine, not an appendix

An earlier draft of this spec could describe *what is broken* but not *what it costs*. That is a
report a founder cannot act on, because severity without consequence is just an opinion about
software.

Three things follow from taking obligations seriously:

1. **Impact becomes concrete.** "Anonymous read access to the profiles table" is a technical fact.
   "This is personal information under the Privacy Act, held without adequate security, which is an
   APP 11 obligation, and an exposure of it is likely a notifiable data breach" is an impact
   statement a founder can take to their board or their lawyer.
2. **Asset priority stops being guesswork.** Which assets matter most is not a matter of taste —
   it is determined by what obligations attach to the data they hold. Crown jewels are identified
   by law before they are identified by intuition.
3. **Blind spots get named.** A control framework is a checklist of things people forget. Without
   one, coverage is whatever the operator happened to think of; with one, coverage is measured
   against a published bar and the gaps are visible.

### 21.2 The commercial trigger `[VERIFY]`

**Corrected 2026-08-20** (see `docs/research/privacy-act-feasibility.md`): the **Privacy Act small
business exemption** (s 6D) has **not** been repealed and carries no commencement date for removal.
Compilation No. 104 (4 June 2026) shows no amendment to s 6D since 2012, and the $3,000,000 annual
turnover threshold is intact. Removal remains a government "agreed in principle" commitment only,
subject to further consultation `[VERIFY]` — no bill, no date. The "late 2026" figure previously
stated here does not hold and should not be repeated.

The dated market instead rests on two narrower, already-legislated obligations, both `[VERIFY —
under audit]`: AML/CTF "tranche 2" reporting entities (real estate professionals, dealers in
precious metals/stones, lawyers, conveyancers, accountants, trust and company service providers)
reportedly pulled into the Act for their AML/CTF-related activities from 1 July 2026 via s 6E(1A);
and automated-decision-making transparency (APP 1.7–1.9) reportedly commencing 10 December 2026 for
every existing APP entity. These are better-qualified, better-dated hooks than the exemption ever
was, but neither is yet confirmed to the standard this repo requires before a client or marketing
document may state it as fact.

**RedGold's posture regardless of the date: act as though the obligations already apply.** They
represent baseline practice that any business holding personal information should already meet, and
a client hardened early is a client not scrambling later.

### 21.3 Customer reframe

| | Segment | What they buy | Work profile |
|---|---|---|---|
| **Proving ground** | Solo founders / vibe-coded startups | Technical audit | Web/API testing, asset discovery. Generates the playbooks and proves the tooling |
| **The real market** | Small businesses with no compliance capability | *Getting above the line* | Questionnaires, asset and data-flow discovery, gap assessment against a named bar, remediation plan, policy drafting |

The second segment is larger, less technically exciting, and more valuable — and the two are not
separate products. A small business with a customer-account section on its website has exactly the
same unanswered questions as a startup: *where is this data, who can reach it, what happens if it
leaks.* The technical machinery built for segment one is what makes segment two affordable, because
the discovery, evidence and reporting pipeline is identical. Only the questions asked of it change.

This is also why the **asset register** (§5.2) and **`posture`/`governance` finding classes** (§6.2)
matter more than they first appeared: for segment two they are not supporting artifacts, they are
the deliverable.

### 21.4 The obligation register

A machine-readable corpus in the framework repo — the "cheat sheet in your back pocket", made
queryable so it is applied consistently rather than remembered selectively.

```
~/RedGold/obligations/
  index.yaml                    # which regimes apply, and the triggers that make them apply
  au-privacy-act/
    REGIME.md                   # scope, who it binds, commencement, regulator
    principles/app-01..app-13.md
    breach-notification.md      # NDB scheme
    penalties.md                # [VERIFY] all figures
    controls.yaml               # obligation -> technical control -> how RedGold tests it
  asd-essential-eight/
  asd-ism/
  nist-csf-2.0/
  nist-800-53/  nist-800-171/  nist-800-115/
  mitre-attack/
  iso-27001/
  pci-dss/
  sector/{soci-act, apra-cps-234, my-health-records, consumer-data-right}/
  intl/{gdpr, uk-dpa}/          # applies when the client has users in those jurisdictions
```

Each regime folder answers, in a fixed shape:

| Field | Content |
|---|---|
| `applies_when` | Machine-evaluable triggers — turnover, sector, data classes held, user jurisdictions, contracts |
| `obligations[]` | Each with an id, plain-language statement, and the primary-source citation |
| `controls[]` | The technical control that discharges each obligation |
| `tests[]` | How RedGold checks that control — links to a playbook check or a baseline item |
| `consequences` | Penalty exposure, regulator, notification duty and timeframe. **All `[VERIFY]`** |
| `remediation` | What fixing it looks like, with cost tier |
| `bookmarks` | Direct links to the authoritative text and to the regulator's own guidance |

**The `controls`→`tests` link is what makes this operational rather than decorative.** It means a
technical finding can be reported with its obligation, and a compliance gap can be reported with the
test that would have caught it.

### 21.5 Data classification drives asset priority

Assets in the register (§5.2) gain a `data_classes[]` field. Obligations attach to data classes;
priority follows.

Candidate classes `[VERIFY against the Privacy Act's own definitions]`:

| Class | Notes |
|---|---|
| `personal_information` | The Act's central definition — broader than most founders assume |
| `sensitive_information` | Health, biometric, racial/ethnic origin, religious beliefs, sexual orientation, criminal record, union membership. Higher obligations |
| `health_information` | Additional state-based regimes may apply |
| `government_identifier` | Tax file numbers, licence and passport numbers — specific handling rules |
| `payment_data` | PCI DSS scope; usually reduced by using a hosted gateway |
| `credentials` | Password hashes, tokens, API keys |
| `location` | Precision matters — a recurring finding class is full-precision coordinates |
| `childrens_data` | Heightened expectations `[VERIFY current position]` |
| `employee_records` | Historically treated differently `[VERIFY — this may be changing]` |

`rg-recon` and `rg-surface` infer candidate classes from schema names, API responses and form
fields; the client confirms them in the co-discovery interview. **Inference is never authoritative
for a legal conclusion** — it produces a question for the client, not an answer about them.

### 21.6 Data residency and cross-border disclosure `[VERIFY]`

The operator's open questions, recorded here as the research brief rather than answered
speculatively:

- Does storing Australian personal information offshore require anything beyond the cross-border
  disclosure obligation, and what does that obligation actually require of a small business?
- Is "put the bucket in the Sydney region" a genuine requirement, a risk-reduction measure, or
  neither?
- How is a payment processor with offshore infrastructure treated versus self-hosted storage?
- What must a client disclose in their privacy policy about offshore storage and recipients?
- Do any sectors (health, government-adjacent, financial) impose stricter residency rules?

**Not to be answered from memory.** These are the sort of questions where a confident wrong answer
does real damage to a client, and they are explicitly assigned to research in §21.8.

### 21.7 Obligation-aware findings and reporting

Findings gain:

```jsonc
{
  "obligation_refs": ["au-privacy-act/app-11", "asd-essential-eight/patch-applications"],
  "data_classes": ["personal_information", "location"],
  "notifiable_assessment": "likely | unlikely | requires_legal_assessment | n/a"
}
```

- `finding_class` gains a fourth value: **`compliance`** — a gap against a named obligation with no
  technical exploit attached (no privacy policy; no breach response plan; no record of consent).
  Verified `n/a`, evidenced by document or interview, same as `governance`.
- Every report gains an **obligations section**: which regimes apply and why, gaps against each,
  and what each gap exposes the client to.
- Impact statements pair technical and legal consequence in one sentence.
- **Standing disclaimer in every deliverable:** this is a technical assessment mapped to obligations
  for prioritisation; it is not legal advice; the client should confirm their position with a
  qualified adviser. `[VERIFY]` — whether the operator needs any registration or insurance to
  provide compliance-adjacent services in Victoria.

### 21.8 Research plan — broad, then narrow

Run per the broad-then-narrow pattern: one orienting pass, then targeted passes against what it
finds. **No figure or date from this document reaches a client until its `[VERIFY]` is cleared.**

**Stage 1 — orienting (one agent).** Map the Australian compliance landscape for a small business
holding customer data: which instruments apply, which regulators, where the authoritative texts
live, what the small-business exemption change actually is and when it commences, and what the
obvious sub-questions turn out to be. Output is a map with primary-source URLs, not answers.

**Stage 2 — narrow passes, one per agent, each given exact documents by stage 1:**

1. **Privacy Act core** — the APPs most relevant to a web application (security, collection, use and
   disclosure, access and correction, cross-border), in plain language, with the primary text.
2. **Small business exemption removal** — instrument, commencement, threshold, transition, and
   exactly which obligations bite on day one.
3. **Notifiable Data Breaches** — the assessment test, timeframes, what must be notified, and worked
   examples from OAIC determinations.
4. **Penalties and enforcement** — current maximums, how they scale, what regulators have actually
   done to small entities rather than what the maximum permits.
5. **ASD Essential Eight and the ISM** — the maturity model, which controls are realistic for a
   small business, and how to express a gap assessment.
6. **NIST CSF 2.0 / 800-53 / 800-171 / 800-115** — which is the right spine for a small Australian
   business, and free primary sources.
7. **Data residency and cross-border disclosure** — answering §21.6's questions specifically.
8. **Sector overlays** — health, financial, critical infrastructure, Consumer Data Right: what
   triggers them and what changes.
9. **Policy artifacts** — what a compliant privacy policy, collection notice and breach response
   plan must contain, and whether producing them is something the operator can offer.

Every stage-2 output lands as an `obligations/<regime>/` folder in the structure of §21.4, with
`[VERIFY]` cleared only where a primary source was actually read.

---
