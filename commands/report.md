---
description: Generate the client deliverable from validated findings on disk. Operator-initiated only.
argument-hint: [--tier 0|1]
disable-model-invocation: true
---

# /rg:report — client deliverable

```sh
/usr/bin/python3 "${CLAUDE_PLUGIN_ROOT}/scripts/regen_status.py" --root .
/usr/bin/python3 "${CLAUDE_PLUGIN_ROOT}/scripts/report.py" --root . --tier 1
```

Writes `deliverables/report-tier<N>.md`.

Regenerate `status.md` first. It is a projection of the ledgers, and a stale one means the report
and the status file disagree in front of the client.

## Tiers

| Tier | Client receives |
|---|---|
| 0 | Asset register + severity-ordered findings |
| 1 | Tier 0 + hardening guidance + prioritised next steps |
| 2 | Tier 1 + regression suite + guardrail pack — **not built** |

## What it refuses to print

The report is generated from findings on disk and nothing else. It never sees the conversation
that produced a claim, so it cannot be talked into including one.

| Excluded | Why |
|---|---|
| A technical finding above Low that was not independently re-executed | Published false-positive rates for autonomous vulnerability detection run 15.3–45.8% across six frontier models. On the margin an unverified finding is close to a coin flip, and the client cannot tell which by reading it. It moves to **Open questions**. |
| A finding whose `evidence_ptr` does not resolve | Demoted, then excluded — not printed with a caveat. |
| A finding whose `evidence_ptr` is prose rather than a pointer | A citation no script can check is not evidence a client can audit. |
| Anything not `confidence: confirmed` | Only confirmed findings appear in the body. |
| A rollup's constituent findings | Counted once. Naive concatenation inflates the count, which flatters us. |
| Anything marked `[VERIFY]` | Never reaches a client. |

A **posture** or **governance** finding may exceed Low with `verified: n/a` — its severity rests on
an observed fact (MFA is off; there is no incident response plan), not a demonstrated exploit.

## What it always includes

- **What we checked and did not find.** Every negative result, listed. A report that lists only
  what broke tells the client nothing about whether the rest holds.
- **Open questions**, with a recommended next action each — reported as open rather than dressed
  up as findings.
- **The asset register.** For a founder who does not know that clicking a dashboard spawned a
  public bucket, "here is everything you actually own" often lands harder than the findings.
- **Test data we created**, with the exact removal query — whether or not cleanup succeeded.
- **Limits**, including that scope enforcement is defence in depth rather than a guarantee, and
  that a finding we did not make is not a vulnerability that does not exist.
