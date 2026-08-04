---
title: Calibration — what agentic testing can and cannot do
question: What is defensible to claim to a client, and what caveats must travel with it?
spec: RedGold design
sections: [20]
status: draft
date: 2026-08-04
---

## 20. Calibration

P9 says calibrated honesty is a feature. This is the file that makes it operable. Everything here
comes from benchmarks with disclosed methodology; vendor self-reported numbers are excluded on
principle. **The calibration paragraph in §14.4 is required in every client report.**

### 20.1 The calibration table

| Task type | Best published rate | Source | Caveat |
|---|---|---|---|
| **Blind web/API vuln discovery** (no CVE given) | **4–14%** ground-truth coverage; CVE-Bench zero-day ~10% success@5 | arXiv 2605.23243 (5 production-style apps, 118 ground-truth vulns, 20+ CWE families); CVE-Bench arXiv 2503.17332 | Closest task to a real engagement. Only 5 target apps — thin sample |
| **Detecting a real bug-bounty vulnerability** | **5.0–12.5%** | BountyBench arXiv 2505.15216 Table 1 | 40 real codebases, real payouts, 3 attempts/task |
| **CVE reproduction** (description given) | 10% zero-day, **12.5%** one-day | CVE-Bench §4.2 | Success = one of 8 defined attacks actually landing |
| **Exploit development** (vuln pre-identified) | **32.5–57.5%** top agents; 17.5–67.5% all | BountyBench Table 1 | Vulnerability is *handed to* the agent — not discovery |
| **Patching a known vulnerability** | **87.5–90%** top agents | BountyBench Table 1 | Consistently the strongest task for every agent tested |
| **CTF, guided, many attempts** | o3 89% high-school / 59% professional (pass@12); Cybench ~100% pass@30 | OpenAI o3 system card; Anthropic system card | Best-of-N, not first-try. Labs state these are **saturated** and no longer track capability |
| **CTF, unguided, single attempt** | **55%** (Claude 4.5 Sonnet) | Cybench | >40pp below the same model's pass@30. This is the decision-relevant figure |
| **Chained exploitation vs active defences** | **0 of 7 frontier models** succeeded in any scenario | PACEbench arXiv 2510.11688 | 32 challenges — small, but unambiguous |
| **Security knowledge (recall)** | 70–89% | CAIBench arXiv 2510.24317 | Knowledge ≠ execution — that gap is the paper's central finding |
| **Multi-step attack & defence** | 20–40% | CAIBench | Execution band overall 20–50% |
| **False positives — autonomous detection** | **15.3–45.8% FPR** across 6 frontier models | arXiv 2605.23243 Table 2 (150 balanced samples) | Every frontier model tested was double-digit |
| **False positives — triaging existing SAST output** | >92% → **6.3%** | arXiv 2601.22952, OWASP Benchmark | **A different, easier task.** Never quote as "agents' false positive rate" |

### 20.2 What this means for the design

Each row below is a design consequence, not an observation.

- **Detection at 5–12.5% is why playbooks exist.** Seed hypotheses (P3) attack the exact failure
  mode — CVE-Bench names *insufficient exploration* as the dominant bottleneck, at up to 80% of
  failures for the best agent tested.
- **Detection FPR of 15–46% is why verification is mechanical (P2).** At those rates an unverified
  finding is close to a coin flip on the margin. This single row justifies `rg-verify` re-executing
  rather than re-reading.
- **The 40+ point gap between pass@30 and single-attempt** is why a finding must be *reproducible*
  (validation gate 1, §10.4), not merely observed once.
- **0/7 against active defences** is why RedGold does not sell red-teaming as its main product and
  why `redteam` mode carries the heaviest authorisation requirements for the least reliable output.
- **Patching at 87.5–90%** is why the north star points at remediation and the defensive handoff.

### 20.3 The gap nobody has measured

**No benchmark measures open-ended web/API penetration testing** — recon through business-logic
abuse through chaining to client-reportable findings, with a human baseline. CVE-Bench always aims
at a known CVE in a known app. VulnLLM-R is closest in spirit but spans five applications. AutoPT
and AutoPenBench claim OWASP coverage but their figures could not be verified from primary sources
and must not be quoted.

So the honest position on the task RedGold actually performs is: **there is no benchmark number, and
anyone quoting one is extrapolating.** RedGold's own acceptance tests (§17) are the nearest thing to
an internal measure, and they measure reproduction of a known engagement, not discovery.

### 20.4 Required client paragraph

Reproduced in every report, adjusted only for engagement mode:

> Automated and agentic security testing is strong at some tasks and weak at others, and it is worth
> being precise about which. Where a vulnerability is already identified, current systems patch it
> correctly around 87–90% of the time, and that is the basis for the remediation work in this
> report. Discovery is much weaker: against real codebases, the best measured detection rates are
> between 5% and 12.5%, and against production-style web applications, blind discovery covers
> roughly 4–14% of known issues. Published false-positive rates for autonomous detection run from
> 15% to 46%, which is why every finding here was independently re-verified before inclusion, and
> why findings that could not be verified are labelled rather than omitted.
>
> Two further caveats. Most published figures report the best of many attempts rather than
> first-try reliability, and where both are measured the gap is 20–45 percentage points. And no
> public benchmark measures open-ended web application testing of the kind performed here, so any
> precise "coverage" figure — from us or anyone else — is an extrapolation.
>
> This report is therefore a prioritised map of what was found, not a proof of what is absent. The
> coverage section states exactly what was and was not examined.

### 20.5 Things never to say

- Any single "we find X% of vulnerabilities" figure. Scope the claim to the task type or omit it.
- "Zero false positives." No credible methodology supports it from anyone.
- Any saturated pass@30-style benchmark number as evidence of capability — the labs publishing them
  say they no longer track capability.
- "Comprehensive", "complete", or "full coverage" about any testing performed.
- Vendor marketing figures, including favourable ones. P9 applies to numbers that help us too.

### 20.6 The market context — why none of this is optional

Calibration is not only an ethical position. As of 2026 it is a commercial precondition, because
the receiving end of AI-generated security findings has publicly rebelled:

| Programme | What happened |
|---|---|
| **curl** | Bug bounty **terminated** (ends 2026-01-31). 20 submissions in early 2026, **zero valid**. Maintainer: *"the never-ending slop submissions take a serious mental toll to manage."* |
| **Internet Bug Bounty** | New submissions **paused** 2026-03-27 after 14 years and $1.5M+ paid. HackerOne: the "balance between findings and remediation capacity in open source has substantively shifted." |
| **Bugcrowd** | Triage queues **+334% in three weeks**. 30-day suspension after 10 consecutive AI-attributed invalid reports; permanent bans for farming. Coined *"sloptimism"*: reports that "look legitimate... but collapse under inspection." |
| **Nextcloud** | Paid bounty suspended 2026-04-22 — "unable to find ways to responsibly handle the massive increase of low quality reports." |
| **Node.js** | 30+ reports in a month against a historical 2–3/week, "remarkably similar, strongly suggesting... the same or similar LLM/tooling." New researchers locked out via a Signal 1.0+ requirement. |
| **Apple** | Submission caps, 30-day cooldowns, 180-day pauses. A legitimate research team was **rate-limited out of reporting a real bug** by AI volume. |
| **HackerOne** | Leaderboard restructured to separate AI collectives from individual researchers. |

Three consequences for how RedGold is sold and built:

1. **Never lead with the tooling.** "AI-powered" now reads as a warning label to anyone technical.
   Lead with verified findings and judgement. This is a positioning rule, recorded in `NORTH_STAR.md`.
2. **A short proven list beats a long speculative one — and the difference is not stylistic.**
   Volume exceeding the client's capacity to remediate is what broke the bug bounty ecosystem.
   Ruthless prioritisation is a deliverable feature, not an admission of limited coverage.
3. **Even the strongest vendor concedes the core point.** XBOW's own engineering writing states that
   LLMs are "trained to please, so their findings are not always reliable and need to be validated,"
   and that general-purpose agents "cannot reliably execute long, multi-stage attack sequences."
   Independent analysis puts XBOW's cross-programme report validity near **1 in 3**. Google's own
   position on Big Sleep is that it "excels at variant analysis, not broad exploratory hunting," and
   that a target-specific fuzzer would likely be at least as effective.

The strategic read: the field's credibility problem is RedGold's opportunity. Verified-only output,
explicit coverage, and calibrated language are exactly what the market has been trained to want and
is not being offered.
