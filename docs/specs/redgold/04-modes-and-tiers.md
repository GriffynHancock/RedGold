---
title: Engagement modes and blast-radius tiers
question: How far may an engagement go, and what makes an audit an audit?
sections: [6]
spec: RedGold design
status: draft
date: 2026-08-03
---

## 6. Engagement modes and blast-radius tiers

The prior engagement hardcoded "tier 3 always blocked," calibrated to one client's demo window. RedGold makes
the ceiling a per-engagement declaration, enforced mechanically.

**The dividing line is not read versus write.** An earlier draft made that mistake and it produced
an incoherent product: rate limiting is among the most basic controls any audit is expected to
check, and you cannot check it without sending writes. A client handed an "audit" that skipped rate
limiting has not been audited.

The real line is **reversible, conspicuous and bounded** versus **irreversible, sustained or
exploitative**.

| Tier | Name | Contains |
|---|---|---|
| **0** | Passive | OSINT, CT logs, passive DNS, archive, public docs. Never touches the target. |
| **1** | Safe active reads | Normal-user-equivalent reads: page loads, unauthenticated GETs, bundle fetch, TLS/header inspection, read-only API calls under supplied credentials. |
| **2** | Bounded reversible writes | Rate-limit probing via `rate_probe.sh`, form and signup submission, non-destructive fuzzing, and **only those** authz/BOLA tests that genuinely require a write. Most IDOR/BOLA testing is read-only replay-and-diff and stays at tier 1 (§9.4). **Every write is conspicuous test data (§6.1) and canary-gated (§9.4).** |
| **3** | Irreversible, sustained or exploitative | Exploitation of confirmed vulnerabilities, sustained load, chained compromise, anything that cannot be trivially undone or that fires real-world side effects. |

**Modes** set the default ceiling; `ceiling:` in `scope.yaml` may lower it but never raise it.

- `posture` → ceiling 1, plus the governance review (§6.2). The **cheap trial**: tells a founder
  where they stand without touching anything that writes. Designed to be sold as a fixed-price
  first engagement that earns the full audit.
- `audit` → ceiling 2. **The main product**, black-box and/or white-box. Includes rate limiting,
  access-control boundaries, and everything else a founder would reasonably expect an audit to have
  looked at.
- `redteam` → ceiling 3. Requires written authorization naming exploitation, a named emergency
  contact, and **strongly prefers a non-production target**. Tier-3 actions require operator
  presence at the time of execution.

Every action carries a tier. `scope_guard.py` denies anything above the declared ceiling regardless
of what any agent concludes.

### 6.1 Conspicuous test data

Canary-gating (§9.4) proves *we* can delete what we wrote. It does not help when deletion fails for
a reason nobody predicted — which is exactly what happened on the prior engagement, where an ownership check
refused the anonymous creator's own delete and left 15 rows behind.

So every write is also made **unmistakably identifiable and trivially removable by the owner**:

- Every writable text field carries the marker `RedGold-TEST-<engagement_id>-<seq>`.
- Email addresses use a dedicated, operator-controlled domain, never a plausible-looking fake.
- Names, notes and free-text use obviously synthetic values — never anything that could be mistaken
  for a real user's data at a glance.
- Timestamps and sequence numbers make the write set enumerable.

The point: if cleanup fails, the client can find and remove every artifact with a single `LIKE
'RedGold-TEST-%'` query, and can tell at a glance that no real user data was involved. Residue
becomes an inconvenience rather than an incident.

**Every engagement ships a cleanup appendix** listing exactly what was written, where, when, and the
query to remove it — whether or not cleanup succeeded. Generated from `ledger/cleanup.jsonl`.

**Where conspicuousness fails, and what happens instead.** The marker only works in free-text
fields, so four cases need handling rather than assuming:

| Case | Handling |
|---|---|
| Non-text fields — foreign keys, enums, booleans, uploads | No marker is possible. The write is identified in `cleanup.jsonl` by primary key and timestamp instead, and the cleanup appendix lists those explicitly. Uploads use a fixed, published test image. |
| Email deliverability checks (MX/SMTP verification) reject the test domain | The operator-controlled domain must have real MX records. Listed as an engagement prerequisite in §15 and checked by `/rg:new`, not discovered mid-test. |
| A WAF or anti-abuse rule pattern-matches the marker itself | Produces a false "blocked" that reads as a working control. Any tier-2 test that returns blocked is re-run once with an unmarked but still synthetic value to distinguish signature matching from a real control. The result is recorded either way. |
| Third-party fan-out — webhooks, CRM syncs, analytics, notification emails | Outside the operator's cleanup rights entirely. This is the §5 invisible-asset problem reappearing for cleanup. Any endpoint with known or suspected fan-out is tier 3, not tier 2, regardless of reversibility in the primary database. |

### 6.2 An audit is a posture assessment, not just a test run

A cybersecurity audit for a startup spans "there is no whitelist on this firewall" through to "you
are not budgeting for security governance." Confining findings to what a packet can prove would omit
most of what the client actually needs to hear.

Findings therefore carry a **`finding_class`**:

| Class | Established by | Examples |
|---|---|---|
| `technical` | Evidence from testing, verified per §10.3 | Anon-readable table, missing rate limit, IDOR |
| `posture` | Observed configuration and available metadata | No MFA on the Supabase dashboard, single shared admin account, public preview deployments, no dependency update process, secrets in the repo history |
| `governance` | Structured interview and document review | No incident response plan, no named security owner, no backup restoration ever tested, no vendor review, no security line in the budget |
| `compliance` | Gap against a named obligation, no exploit attached (§21) | No privacy policy, no collection notice, no breach response plan, no record of consent, offshore storage undisclosed |

`posture` and `governance` findings still require evidence — a screenshot, a config export, a dated
interview note — but they do not require verification in the §10.3 sense, because there is no
exploit to replay. They are marked `verified: n/a` and carry their own evidence pointer.

This is what makes the `posture` mode saleable on its own: it needs no tier-2 action, yet it answers
the question a founder is actually asking, which is *"how bad is it, and what do I do first?"*

---
