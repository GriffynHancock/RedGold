---
title: Design principles
question: What does RedGold believe, and what evidence holds each belief in place?
sections: [3]
spec: RedGold design
status: draft
date: 2026-08-03
---

## 3. Design principles

Each principle is held because of specific evidence, not taste. Sources in §19.

**P1 — Enforcement is mechanical, never advisory.**
Claude Code's own documentation states that CLAUDE.md content is injected as a user message and
that *"Claude treats them as context, not enforced configuration. To block an action regardless of
what Claude decides, use a PreToolUse hook instead."* Three documented incidents (PocketOS deleting
a Railway production volume, Replit deleting a live production DB during a code freeze, McKinsey's
Lilli platform reaching full production read/write in two hours) share one root cause: the only
barrier between the agent and an irreversible action was prose in a prompt. Mechanical checks are a
strictly better floor than prose — but they are a floor, not a proof (§9.3.1). RedGold's ROE lives in
exit codes.

**P2 — A finding is not a finding until something other than the model has verified it.**
Every system with independently checkable results puts a non-LLM gate between claim and report:
XBOW executes the XSS payload in a headless browser and confirms the JS actually fired; OpenAI's
Aardvark re-exploits in an isolated sandbox; CVE-Bench runs an evaluation server checking for a real
dropped file or changed DB row; Strix requires a working PoC. None trust self-report.

**P3 — Seed hypotheses beat open-ended hunting.**
Google's Project Naptime took CyberSecEval2 Buffer Overflow from 0.05 → 1.00 largely by framing the
task as *variant analysis* — "here is a known bug pattern, find its cousins" — rather than "find
bugs." CVE-Bench's failure taxonomy shows **"insufficient exploration" accounting for 37.5–80% of
failures** under open-ended framing. The playbook library exists to supply seed hypotheses.

**P4 — Audit between steps; do not fan out and vote.**
The mechanism is the defensible part: agentic errors are *systematic*. One early wrong action locks
the trajectory into confidently-wrong output that every voter reproduces, so averaging across voters
cannot correct what they all got wrong the same way. Hierarchical delegation, by contrast, beat flat
ReAct 13% vs 2.5% on CVE-Bench, and CVE-Bench names *insufficient exploration* — a planning failure,
not a sampling failure — as the dominant bottleneck for every agent tested.

*Sourcing note:* earlier drafts asserted self-consistency yields "+0–2pp on agentic tasks." **No
cyber-specific study supports that figure and it has been removed.** The nearest real evidence is
domain-general — "Soft Self-Consistency Improves Language Model Agents" (arXiv 2402.13212, ACL 2024)
finds plain majority-vote self-consistency gives only marginal gains on long-horizon agentic tasks
in WebShop, ALFWorld and bash synthesis. Say that, and stop there.

Correctness comes from per-step verification, not ensemble averaging.

**P5 — Retrieval on demand, not context stuffing.**
Vulnhuntr traces call chains by requesting specific functions as needed rather than dumping the
repo. In the "Sifting the Noise" study, an oracle baseline given the same files but no iteration
scored 36.4%, versus 96% with iterative retrieval. It is the iteration that works, not the volume.

**P6 — One fact, one home.**
The prior engagement's `status.md` reached 430 lines doing five jobs and grew a duplicate finding ID. Every
artifact answers exactly one question.

**P7 — Capability grows faster than complexity.**
New knowledge lands as playbook entries, not new agents. The roster is capped; the library is not.

**P8 — The operator approves each escalation, not each engagement.**
The instructive contrast is Strix (32k stars), whose system prompt instructs its agents to *"NOT ask
for permission or confirmation — you already have complete testing authorization"* and that *"Real
vulnerabilities take TIME — expect to need 2000+ steps minimum. NEVER give up early."* That is a
coherent design for unattended, high-volume bug-bounty work against programs that have pre-consented
to it. It is the wrong design for a named client's production system. RedGold's counter-model comes
from `pentest-ai-agents`' exploit-chainer: *"The operator approves each move. Never auto-chain
without consent."* Approval is granted at pivot granularity, not once at engagement start.

Note also that a runtime toggle defeats this: CAI's guardrails can be disabled wholesale with
`CAI_GUARDRAILS=false`. RedGold has no equivalent switch — enforcement lives in the artifact and is
checked at build time.

**P9 — Calibrated honesty is a feature.**
Published FP rates from vendors almost never disclose methodology. Client-facing claims are set
against academic benchmark bands (§1.1), not marketing numbers. Under-claiming wins the second
engagement.

**P10 — A deterministic baseline runs before any agentic exploration, and cannot be skipped.**
The most instructive published failure of an agentic pentest is not a missed subtlety. In an
independent evaluation (Wavestone/RiskInsight, 2026), the agent **fabricated a critical JWT
algorithm-confusion finding with a proof-of-exploit that did not work**, while **missing an exposed
admin interface protected by default credentials** — described as "a vulnerability no human
pentester would overlook." The same evaluation records "tunnel vision": prolonged fixation on one
irrelevant path at the expense of coverage.

Agentic judgement decides *where to look next*. It must never decide *whether to check the obvious*.
So a fixed, scripted baseline runs on every engagement regardless of what any agent concludes is
interesting: default credentials, exposed admin routes, public buckets and tables, directory
listing, source maps, `.env` and `.git` exposure, wildcard CORS on authenticated routes, missing
authentication on discovered endpoints, preview-deployment reachability, TLS and header posture.
Deterministic, checklist-driven, results recorded whether positive or negative.

Implemented as `scripts/baseline_scan.py`, owned by `rg-surface`, run at the start of every
engagement's active phase. It is **not** playbook-dispatched — §11.5's startup default checks are
fingerprint-triggered and therefore conditional, which is the opposite of what this principle
requires. The baseline runs before any fingerprint is known and regardless of what one turns out to
be; the playbook checks are additive on top of it. Both write findings through the normal schema,
distinguished by `discovered_by`.

**P11 — Repeatability is the product; the run is not.**
The same evaluation found that **two agentic runs against the same target produce substantially
different findings**. A deliverable that cannot be reproduced is not an assurance artifact.

RedGold's answer is that reproducibility lives in the *method*, not the model: the deterministic
baseline (P10) is identical every time; playbook checks are enumerated and versioned; every finding
carries a replayable request; and coverage is reported explicitly, including what was not examined.
Two RedGold engagements against the same target should agree on the baseline and the playbook
checks, and may legitimately differ only in what exploratory work surfaced — which the report says
plainly.

This is also the honest answer when a client asks *"could I just run this myself?"* The tool is
non-deterministic; the method is not. The method is what they are paying for.

---
