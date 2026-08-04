---
title: Findings and verification
question: What counts as a finding, and who proves it?
sections: [10]
spec: RedGold design
status: draft
date: 2026-08-03
---

## 10. Findings and verification

### 10.1 Findings schema

```json
{
  "id": "F-007",
  "asset_id": "A-014",
  "asset": "https://api.acme.example/rest/v1/profiles",
  "title": "Anonymous read access to user profile table",
  "finding_class": "technical",          // technical | posture | governance | compliance
  "obligation_refs": ["au-privacy-act/app-11"],
  "data_classes": ["personal_information", "location"],
  "notifiable_assessment": "requires_legal_assessment",
  "status": "PROVEN",
  "verified": "replayed",
  "confidence": "high",
  "evidence_ptr": "evidence/F-007-anon-read.http",
  "severity": "high",
  "likelihood": "high",
  "real_world_impact": "Any visitor can enumerate all user emails and coordinates.",
  "tested_at_tier": 1,
  "gate_ref": "G-002",
  "playbook_ref": "backends/supabase@2.100-2.110#rls-anon-read",
  "standard_refs": ["ASVS-4.0.3-V4.1.3", "WSTG-ATHZ-02", "API1:2023"],
  "remediation": "Enable RLS on public.profiles and add an owner-scoped SELECT policy.",
  "cost_tier": "$",
  "cleanup_required": false,
  "discovered_by": "rg-webtest",
  "verified_by": "rg-verify",
  "created": "2026-08-06T11:20:00Z"
}
```

New versus the prior engagement: `verified`, `tested_at_tier` (the blast-radius tier of the *test
that produced this finding* — not an impact measure; §6's tiers classify actions, never
consequences), `gate_ref`, `playbook_ref`, `standard_refs`,
`cleanup_required`, `asset_id`. `gate_ref` lets a finding self-certify which approval authorised the
test that produced it — the prior engagement kept gate approvals only in `status.md` prose,
disconnected from the findings they covered.

### 10.2 `evidence_ptr` must resolve

In the prior engagement this was free-text prose (`"phase2_evidence/phase2_live_probes.md#1 (literal
w.version=...)"`) — a human citation that no script could check, which is partly why the validator
was never built. In RedGold it must resolve to an existing file, and for `file.md#anchor` form, to
an existing anchor. Raw HTTP evidence is captured as request/response pairs in
`evidence/<finding-id>-<slug>.http`, not paraphrased.

### 10.3 Verification levels

| Level | Meaning |
|---|---|
| `none` | Model asserted it. Cannot exceed `SPECULATED`, cannot exceed Low severity in a report. |
| `replayed` | `rg-verify` independently re-issued the request and observed the same result. |
| `executed` | The impact was mechanically demonstrated — payload actually fired, data actually returned, control actually bypassed. |
| `n/a` | **Only** for `finding_class: posture` or `governance`. There is no exploit to replay (§6.2). Requires a dated evidence pointer — a config export, screenshot, or interview note — and is subject to gates 2–5 of §10.4 but not gate 1 or 6. |

`rg-verify` does not read findings; it **re-runs** them:

- **XSS** → headless Chrome; confirm the JS actually executed (DOM mutation or dialog), not that the
  payload appears reflected in the body.
- **Access control / IDOR** → replay the identical request under a second auth context and diff.
- **Public bucket or table** → re-fetch and confirm the exact bytes.
- **Rate limiting** → re-run the capped `rate_probe.sh` and observe the absence of throttling.

**No `technical` finding above Low reaches a client report without `replayed` or `executed`.**
`posture` and `governance` findings may exceed Low with `verified: n/a`, because their severity
rests on an observed fact (MFA is off; there is no incident response plan) rather than on a
demonstrated exploit. `validate_findings.py` applies the severity rule by `finding_class` — without
that carve-out it would reject every legitimate posture finding on every engagement.

The measured justification: published false-positive rates for *autonomous* vulnerability detection
run **15.3–45.8% across six frontier models** (arXiv 2605.23243, 150 balanced samples). At those
rates an unverified finding is near a coin flip on the margin — which is why `rg-verify` re-executes
rather than re-reads, and why this rule has no exception for a confident-sounding agent. See §20.1.

Note the distinction a client will otherwise conflate: agents *triaging an existing scanner's output*
achieve far better rates (>92% baseline noise down to 6.3%). That is a different and much easier
task than independent detection, and the two numbers must never be quoted interchangeably.

### 10.4 The six validation gates

`rg-verify` runs a gate sequence adapted near-verbatim from `frendysanusi/claude-pentest-skills`,
whose framing is worth preserving exactly:

> You are a skeptical, adversarial quality gate. Assume **every finding is a false positive until
> proven otherwise.** You are not adversarial toward the tester — you are adversarial toward
> findings.

| # | Gate | PASS requires | FAIL when |
|---|---|---|---|
| 1 | Reproducible PoC | A complete HTTP request (method, URL, headers, body) that triggers it | It is described in words with no concrete request |
| 2 | HTTP evidence | Request **and** response captured; response demonstrates the issue | Either half missing or paraphrased |
| 3 | Impact verified | A concrete impact statement — "can read any user's email address" | Speculative — "may lead to data exposure" |
| 4 | In scope | Within `scope.yaml` and a CONFIRMED register row | Excluded asset. **No exceptions — reject unconditionally** |
| 5 | Real vulnerability | A demonstrated exploit path | Informational-only, best-practice, self-XSS, or theoretical |
| 6 | Client reproducible | A third party can reproduce with browser, curl or Burp | Needs a <5%-success race, undocumented session state, or custom tooling |

Verdict per finding: **VALIDATED / REJECTED / NEEDS-WORK**, with per-gate reasoning recorded.

### 10.5 Known false-positive patterns

Encoded as a check table so the same wrong call is not made twice, and so a secure default is never
sold to a client as a flaw:

| Pattern | Why it is not a finding |
|---|---|
| XSS that fires only in the tester's browser | Browser extensions or cached state may be responsible |
| SQL "errors" in normal application flow | Some apps intentionally surface error-like messages |
| SSRF reaching an internal IP but the response is blocked | The firewall blocked it — no exfiltration occurred |
| IDOR where the "other user's data" is public | Public profiles are not an access-control failure |
| CSRF on a form requiring re-authentication | Re-auth *is* a CSRF defence |
| Self-XSS requiring the victim to paste into their own console | Not exploitable against other users |
| Open redirect with no downstream impact | Informational by itself |
| Missing security headers with no exploit | Defence-in-depth, not a vulnerability |
| Reflected input that is HTML-encoded | The encoding is the control working |
| Time-based SQLi with inconsistent timing | Network latency mimics time-based responses |

This table lives in `playbooks/_generic/false-positives.md` and grows via `/rg:harvest`.

### 10.6 Confidence and coverage

Findings carry a three-value confidence — `confirmed` / `probable` / `unconfirmed` — orthogonal to
`status` and `verified`. Only `confirmed` findings appear in the main report body.

**Coverage gaps are a first-class report section, not a footnote.** Everything tested-and-clean,
everything de-scoped for time, and every `unconfirmed` finding is listed with a recommended next
action. A report that quietly omits what it did not test is a report that overstates its own
assurance, which is the fastest way for a solo contractor to lose a client's trust permanently.

---
