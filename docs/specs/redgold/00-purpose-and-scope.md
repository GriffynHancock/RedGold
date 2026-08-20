---
title: Purpose and scope
question: What is RedGold for, why does the audit tier lead, and what does this spec cover?
sections: [1, 2]
spec: RedGold design
status: draft
date: 2026-08-03
---

## 1. Purpose

RedGold is a Claude Code plugin for professional, authorized web and API security auditing of
startup products — the class of application increasingly written by AI coding agents for
non-technical founders.

The operating thesis is in `~/NORTH_STAR.md`. In one line: move from *"I can help you
check out your webapp"* to *"pay me to fix your product's security, and to arm your agents to keep
it secure."*

The framework must let the operator point at a product and say:

> "This client is trying to protect XYZ. For white-box, here is a file of credentials and source
> access. For black-box, here are a few URLs to start from. Let's start."

### 1.1 Why the audit tier is the default

**BountyBench** (arXiv 2505.15216, 40 real bug bounties across 25 real codebases with real payouts,
3 attempts per task) measures the same agents across three separate tasks. The per-agent rows —
*not* a cross-agent range, which an earlier draft of this spec wrongly presented as one system's
scores:

| Agent | Detect | Exploit | Patch |
|---|---|---|---|
| Claude Code | **5.0%** | 57.5% | 87.5% |
| o3-high (Codex CLI) | **12.5%** | 47.5% | 90.0% |
| o4-mini (Codex CLI) | **5.0%** | 32.5% | 90.0% |

The shape is consistent across every agent tested, and it is the single most important fact about
this business:

> **Agents find 5–12.5% of real vulnerabilities. Given one, they exploit 32.5–57.5%. Asked to fix a
> known one, they succeed 87.5–90%.**

Corroborating evidence points the same way. **CAIBench** finds models scoring 70–89% on security
*knowledge* but 20–50% on *execution*, and 20–40% on multi-step attack-and-defence specifically.
**CVE-Bench** puts end-to-end exploitation at ~10% (zero-day) and 12.5% (one-day). Blind discovery
against production-style web apps lands at roughly **4–14% ground-truth coverage**. **PACEbench**
found **0 of 7 frontier models** bypassed active defences in any scenario.

Three consequences, and the whole product follows from them:

1. **Discovery is the weak half, so it must be augmented, not trusted.** Playbooks supplying seed
   hypotheses (P3) and a human operator directing exploration are not nice-to-haves — CVE-Bench
   names "insufficient exploration" as the dominant failure mode for every agent tested.
2. **Remediation is the strong half, and it is also the half worth more.** "Pay me to fix it and
   keep it fixed" is both the higher-margin offer and the one the technology actually supports.
3. **Never sell discovery coverage as a percentage.** See §20 for the defensible client language.

Combined with the commercial reality that a founder needs an audit *before* anyone funds a red
team, the default engagement is an **audit**. Red-team ceilings exist but are the exception.

### 1.2 Market validation

This client segment fails in a documented, repeatable way — which is what makes a playbook library
viable rather than speculative:

- **RedHunt Labs Project Resonance Wave 15**: ~130,000 published vibe-coded sites scanned;
  **~1 in 5 leaking secrets**; 16,000+ exposed Firebase credentials, 3,000+ Supabase.
- **CVE-2025-48757** (Lovable/Supabase): of 1,645 generated apps, **170 had fully public
  databases**. A smaller independent follow-up (manual audit, n=50) reported roughly **85% with RLS
  missing on at least one table** — a small sample, cited as directional only.
- **Tea app (July 2025)**: unauthenticated Firebase Storage bucket exposed 72,000 images including
  13,000 ID verification selfies; a separate authz bug then exposed 1.1M private messages.

Anon-readable tables with full-precision geolocation is a recurring headline finding across
engagements against this product class, not a lucky hit.

---

## 2. Scope of this specification

RedGold decomposes into five subsystems. This document specifies **all five**, with **Subsystem A
in build detail** and B–E at interface level. B–E each get their own spec before implementation.

| | Subsystem | Status in this spec |
|---|---|---|
| **A** | **Engagement core** — scaffolder, scope contract, enforcement, evidence store, findings schema, agent roster, phase pipeline, white/black-box entry | **Build detail** |
| **B** | Recon & asset cataloguing — OSINT, discovery, attribution | Interface + methodology outline |
| **C** | Web/API test depth — WSTG/ASVS dynamic testing, static analysis | Interface + methodology outline |
| **D** | Reporting — client deliverables, severity, remediation, cost | Interface + template outline |
| **E** | Defensive handoff — guardrail pack, regression suite, retainer/monitoring | Interface + outline |
| **G** | **Containment & isolation** — provable egress boundary outside the agent's blast radius (§9.10) | **Research required. Not designed** |
| **F** | **Compliance & obligations** — obligation register, data classification, gap assessment, policy artifacts (§21) | **Spec only. Research outstanding, not built** |

A is the spine: B–F all plug into its scope contract, evidence store, findings schema, and hooks.

**F is promoted to a subsystem** because it has its own research programme, its own deliverables
(gap assessment, policy artifacts), and plausibly its own agent. It may become the larger business —
see §21.3. It is **specced but deliberately not built**: the legal backbone requires verified
research, and nothing in it may reach a client while marked `[VERIFY]`.

---
