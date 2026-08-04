---
title: Subsystems B-E
question: How do recon, test depth, reporting and the defensive handoff plug into the core?
sections: [14]
spec: RedGold design
status: draft
date: 2026-08-03
---

## 14. Subsystems B–E (interface level)

Each gets its own spec before implementation. Defined here only far enough to fix their interfaces
against Subsystem A.

### 14.1 B — Recon and asset cataloguing

**Owner:** `rg-recon`. **Writes:** `assets/register.jsonl`, `assets/candidates.jsonl`.
**Reads:** `scope.yaml`.

Pipeline: **seed → expand → attribute → confirm → monitor**, the standard EASM lifecycle.

- *Seed* from `scope.yaml` boundary entries.
- *Expand*: CT logs (crt.sh), passive DNS, subfinder/amass, permutation via alterx from *observed*
  naming conventions, `httpx` triage, dangling-CNAME takeover checks, cloud bucket enumeration,
  CSP/SPF/DMARC third-party inference, JS bundle indexing, preview-deployment discovery.
- *Attribute*: score signals per §5.2; two independent classes required for CONFIRMED.
- *White-box additive*: with read-only cloud credentials, native inventory (AWS Resource Explorer /
  Config, GCP Cloud Asset Inventory, Azure Resource Graph, Prowler, ScoutSuite, steampipe) becomes
  **ground truth and outranks inference-based attribution**.
- The **co-discovery interview** is a first-class Phase 0 step, not an afterthought: present the
  draft register back to the founder for confirmation before anything active runs.

Deliverable in its own right: the asset register (§5.2).

### 14.2 C — Web/API test depth

**Owner:** `rg-webtest` (dynamic), `rg-codeaudit` (static). **Writes:** `findings/*.json`,
`evidence/`. **Reads:** register, playbooks.

Dynamic depth anchored on OWASP WSTG and API Top 10 2023: BOLA, BFLA, broken auth, JWT handling,
SSRF including cloud metadata, GraphQL introspection and depth/batching abuse, race conditions,
business-logic testing.

Static analysis is a **first-class phase**, absent entirely from the prior engagement: SBOM generation (syft for
breadth, cdxgen for SaaSBOM and reachability), lockfile dependency inventory against real
manifests rather than versions inferred from bundles, secret scanning, IaC review, and Vulnhuntr-style
**call-chain tracing** — request specific functions on demand rather than stuffing the repo (P5).

Tooling is curated where raw shell output is noisy, stateful, or easy to misparse into a false
positive, and left as plain Bash where it is already atomic. Note that CVE-Bench attributed **5–47%
of agent failures to "Tool Misuse" as a category** (5.0–47.5% across agent/setting conditions; the
figure is not sqlmap-specific, though sqlmap features in the qualitative discussion) — powerful
tools need usage guardrails, not just
availability.

### 14.3 D — Reporting

**Owner:** `rg-report`. **Reads:** `findings/*.json`, register, `ledger/`. **Writes:**
`deliverables/`.

Non-technical by default: severity-ordered findings, each with plain-language impact, remediation,
and cost tier. Positives credited explicitly where secure defaults reduced risk. A standing
**calibrated-expectations** section stating what agentic testing does and does not establish, with
the benchmark bands from §1.1 rather than vendor marketing numbers. ATT&CK/NIST vocabulary appears
only in the technical handoff annex, never in the client body.

### 14.4 E — Defensive handoff

**Owner:** `rg-report` + playbook `handoff/` fragments. **Writes:** `deliverables/handoff/`.

Four products, selected by service tier (§16):

1. **Guardrail pack** — a security `CLAUDE.md`, `PreToolUse` hooks, and a review skill installed
   into the *client's* repo, so their coding agent refuses to reintroduce the class of bug found
   (a new public bucket, a table added without RLS). The moat: this is the piece nobody else sells.
2. **Regression suite** — each fixed finding becomes an executable test that fails if it returns.
3. **Hardening playbook** — written remediation guidance with config snippets and priorities.
4. **Retainer / monitoring** — scheduled re-discovery against the asset register with diff-based
   alerting. CT-log polling is the highest-signal, lowest-false-positive drift signal and is the
   first thing to implement. A later addition is a CVE/advisory feed filtered by the client's actual
   SBOM and asset register, delivered on a schedule.

The last two require the asset register to exist, which is why B is not optional.

---
