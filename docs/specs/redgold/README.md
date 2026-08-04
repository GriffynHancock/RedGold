---
title: RedGold design specification — index
question: Which document answers the question I have?
spec: RedGold design
status: draft
date: 2026-08-03
---

# RedGold — Design Specification

**Date:** 2026-08-03
**Status:** Design, pending implementation
**Author:** Engagement operator + Claude (Opus)
**Supersedes:** the prior engagement's `FRAMEWORK.md` and `FRAMEWORK_BUILD_PLAN.md` (held in that
engagement's own directory)

---

## How to read this

Each file answers one question and is loadable on its own. Load the file whose question
matches yours; you should not need the whole set in context at once.

| # | Document | Answers |
|---|---|---|
| §1/2 | [Purpose and scope](00-purpose-and-scope.md) | What is RedGold for, why does the audit tier lead, and what does this spec cover? |
| §3 | [Design principles](01-principles.md) | What does RedGold believe, and what evidence holds each belief in place? |
| §4 | [Repository layout](02-repository-layout.md) | Where does everything live, and why are framework and client data separated? |
| §5 | [The scope model](03-scope-model.md) | How is authorisation expressed, how are assets attributed, and what may be touched? |
| §6 | [Engagement modes and blast-radius tiers](04-modes-and-tiers.md) | How far may an engagement go, and what makes an audit an audit? |
| §7 | [The three files and the ledgers](05-files-and-ledgers.md) | Which artifact answers which question, and what are the ledger schemas? |
| §8 | [Agent roster and model policy](06-agents.md) | Who does the work, on which model, and what may each agent touch? |
| §9 | [The enforcement layer](07-enforcement.md) | What is mechanically prevented, how, and what are the limits of that claim? |
| §10 | [Findings and verification](08-findings-and-verification.md) | What counts as a finding, and who proves it? |
| §11/12/13 | [Playbooks, entry point, and institutional memory](09-playbooks.md) | How does knowledge accumulate so the same mistake is never made twice? |
| §14 | [Subsystems B-E](10-subsystems-b-e.md) | How do recon, test depth, reporting and the defensive handoff plug into the core? |
| §15 | [Engagement governance](11-governance.md) | What must be true before this is pointed at a paying client's production system? |
| §16/17/18 | [Deliverables, build order, and risks](12-deliverables-and-build-order.md) | What does the client receive, in what order is this built, and what could go wrong? |
| §19 | [Sources](13-sources.md) | What is every claim in this spec grounded in? |
| §20 | [Calibration](14-calibration.md) | What is defensible to claim to a client, and what caveats must travel with it? |
| §21 | [Compliance and obligations](15-compliance-and-obligations.md) | What legal and framework obligations attach to this client's assets, and what does non-compliance cost them? |

## Reading paths

- **New to the project** — 00, then 01, then 04.
- **Implementing** — 02, 05, 06, 07, 08, then 12 for build order.
- **Preparing an engagement** — 03, 04, 11.
- **Questioning a claim** — 13.
- **Writing a report or quoting a client** — 14 first, always.
- **Assessing impact or compliance** — 15 (research still outstanding; every figure is marked [VERIFY]).
