---
title: Engagement governance
question: What must be true before this is pointed at a paying client's production system?
sections: [15]
spec: RedGold design
status: draft
date: 2026-08-03
---

## 15. Engagement governance

Controls that are not part of the pipeline but without which the pipeline should not be pointed at a
paying client's production system.

### 15.1 Authorization beyond the client's signature

The client can only authorise what the client controls. This segment runs on Supabase, Firebase,
Vercel and Netlify — **shared-tenant infrastructure the client does not own.** Under the Australian
Criminal Code Part 10.7 (s478.1, unauthorised access), authorisation must come from whoever actually
controls the asset, and a founder's signature does not bind their PaaS provider.

Before any engagement, `/rg:new` requires the operator to record, in `scope.yaml`:

- Each third-party platform in scope and whether its Acceptable Use Policy permits the testing being
  authorised (several require prior notification or prohibit automated testing outright).
- Whether provider notification was sent, and any reference number returned.
- An explicit acknowledgement where a platform's position is unresolved — in which case testing is
  confined to the client's own application layer, not the platform's.

This is a checklist, not legal advice, and it does not substitute for the operator obtaining proper
advice on the engagement contract.

### 15.2 Credential handling

`scope.yaml` points at credentials rather than containing them, but that alone is insufficient: a
command like `curl -H "Authorization: Bearer $TOKEN"` places the secret in `tool_input.command`,
which is visible to the transcript **before** `redact.py` (a `PostToolUse` hook) ever runs.

Therefore:

- Credentials live in a file outside both repos, `chmod 600`, referenced by path.
- Tools receive them via **environment variable or `--config`/netrc file**, never interpolated into
  a command string.
- `scope_guard.py` denies any command containing a credential-shaped literal, catching the mistake
  at the point it is made rather than redacting it afterwards.
- Client credentials are destroyed at engagement close, recorded in the closure checklist.

### 15.3 Inadvertent PII access

Testing an access-control flaw means, by definition, touching data we are not meant to see. The
prior engagement handled this well ad hoc — `HEAD` only, never fetching bodies of real users'
profile photos — but ad hoc discipline does not survive a tired operator.

Standing procedure: **prove the boundary, not the payload.** Establish that access is possible with
the smallest observation that demonstrates it (a status code, a content-length, a single redacted
field), then stop. Never enumerate. Never bulk-retrieve. Any real personal data incidentally
retrieved is recorded in `ledger/activity.jsonl`, minimised in `evidence/`, and flagged to the
client — an exposure discovered during testing may itself be an eligible data breach under the
Privacy Act 1988, and the client needs to know in time to meet their own obligations.

### 15.4 Critical findings mid-engagement

A finding of Critical severity, or any finding indicating **active or historic compromise**, stops
the engagement. The operator notifies the client directly within an agreed window (default: same
business day), before any further testing and well before the report. `status.md` carries the
notification state. The prior engagement needed exactly this and improvised it.

### 15.5 Evidence handling

`evidence/` may contain real personal data. It is encrypted at rest, never leaves the operator's
machine except in the agreed deliverable, and is **destroyed on a defined schedule** (default: 90
days after report delivery, or immediately on client request). Retention beyond that requires the
client's written instruction. The closure checklist records destruction.

### 15.6 Closure checklist

An engagement cannot be marked complete until: cleanup debt is empty; client credentials are
destroyed; evidence retention is set; the asset register is delivered; and `/rg:harvest` has run.
`cleanup_gate.py` enforces the first item; the rest are operator-attested in `ledger/gates.jsonl`.

### 15.7 Commercial and liability items — out of scope for the framework, tracked here

Not built into RedGold, but required before taking paid work, and listed so they are not forgotten:
professional indemnity and cyber liability cover; a written engagement contract with a liability cap
and an explicit authorisation clause; a pricing model for the engagement itself (the `$`/`$$`/`$$$`
tiers price the *client's remediation*, not the operator's time); a defined client communication
cadence; and a retest workflow for verifying remediation, which Tier 2/3 deliverables assume.

---
