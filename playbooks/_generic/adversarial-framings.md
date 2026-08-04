---
title: Adversarial framings
question: How do you point a reviewer at something so it finds what a normal review misses?
status: in use — yields recorded below
date: 2026-08-04
---

# Adversarial framings

A single fixed prompt — "review this for vulnerabilities" — produces a single shape of finding.
Rotating a **named hostile stance** between passes produces different ones, because each stance
makes a different assumption available for attack.

This is used two ways:

1. **`rg-verify` rotates a framing per pass** during an engagement (§10.4).
2. **RedGold audits itself** with them before any first run against a real target.

Both matter, but the second is the one that keeps being proved necessary. The framework's own test
suite is written by whoever wrote the code and inherits the same blind spots exactly.

---

## What makes a framing work

Four rules, learned by running them:

**1. Give it a thesis, not a task.** "Review the scope guard" produces a summary. *"These controls
do not work and I will prove it"* produces attacks. The stance has to be a claim the agent is
trying to establish, because that is what makes it generate hypotheses rather than descriptions.

**2. Make it execute, not reason.** Require every finding to be reproduced by running the thing,
with the exact input and the observed output pasted in. Reasoning about code produces plausible
findings; running it produces real ones. Both auditors below returned findings I could reproduce
in one command, which is why they were actionable within minutes.

**3. Separate confirmed from suspected, and forbid padding.** "One real executed bypass is worth
more than ten speculative ones." Without this, a hostile framing produces a long list of maybes
that costs more to triage than it saves.

**4. Make "it held" a valid result.** *"I attacked X for twenty minutes with these fifteen inputs
and it held"* is genuinely useful — it tells you where not to spend the next hour. Without
permission to report that, an agent invents something to justify the run.

Also: **tell it what is already known.** Both auditors were told which weaknesses are already
documented and admitted, so they spent their effort on the undocumented ones instead of
rediscovering the confession.

---

## The framings

### F1 — The bypass hunter

> **"These controls do not work, and I will prove it. The author was competent but had blind
> spots, and the tests were written by the same person, so they share those blind spots exactly."**

Give it: the control scripts, a throwaway fixture, and the invocation pattern. Ask for inputs that
**should be denied and are allowed**.

Points it at: the gap between what a control matches and what an attacker can write. Regex
anchoring, flag syntax variants, alternative tools that do the same job, encodings, whichever
part of the input the parser never looks at.

**Yield, 2026-08-04: 10 confirmed bypasses**, including `-XDELETE` with no space defeating two
controls at once, a sanctioning string in a shell comment waving through a real loop, and a
renamed binary evading tier classification entirely.

### F2 — The claim auditor

> **"This project's documentation overstates what its code actually does. Find the instance."**

Give it: every claim-bearing document and the code that is supposed to make each claim true. Ask
for a verdict per claim — SUPPORTED / OVERSTATED / FALSE — and for what the code does *instead*.

Points it at: the gap between the sentence and the function. Especially valuable where the
project has a history of it — a control described as a boundary when it is a heuristic, a gate
described as enforced when nothing enforces it.

Ask it explicitly: **is the "not enforced" list complete?** The most dangerous item is the one
enforced in name only that nobody has written down.

**Yield, 2026-08-04: one FALSE outward-facing claim** — "unverified findings never reach the
client report" — reproduced with two fixtures. Plus doc drift in both directions.

### F3 — The interaction auditor

> **"These controls fight each other, and the framework denies itself."**

Points it at: what no single-control test can see. Hook ordering and interference, one control's
output confusing another, a control denying the framework's own tooling, two controls both firing
and producing contradictory guidance, state written by one script that another cannot parse.

Especially relevant after a hardening pass: a rule tightened to close a bypass routinely catches
legitimate internal use as collateral.

### F4 — The reality auditor

> **"This breaks on first contact with anything real."**

Points it at: robustness rather than security. Slow targets, truncated responses, non-UTF-8 bytes,
enormous outputs, corrupt or partially-written ledger lines, concurrent writers, missing
directories, a clock that moved, paths with spaces. A control that crashes is a control that is
not running — and a `PreToolUse` hook that crashes **fails open**.

### F5 — The evidence auditor

> **"The evidence does not support the conclusion drawn from it."**

Points it at: citations that do not say what they are cited for, tests whose names promise more
than their assertions check, a finding whose severity outruns its proof. Applies to findings in an
engagement and to this repo's own claims about benchmarks and prior art.

---

## Using them

- **Two at a time, different framings.** One target each, exact paths supplied. Running the same
  framing twice on the same target mostly reproduces the first run.
- **Never let an audit finding straight into a fix.** Reproduce it first. One earlier research
  agent got two factual claims wrong that this project's own tests caught — an auditor is a
  worker, and workers get verified.
- **Every accepted finding gets a regression test**, or the fix is unprotected and the next
  refactor silently undoes it.
- Record the yield here. A framing that stops finding things on a given target is spent for that
  target, and the effort belongs elsewhere.
