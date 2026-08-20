---
title: RedGold — Architecture Briefing
date: 2026-08-04
status: draft — §5 contested (see the marker there); numbers re-checked 2026-08-20
question: What is RedGold, in one file — its claims, its evidence, and its architecture — for a reader or model that has not seen the 16-file spec?
currency_audit: 2026-08-20 — docs/research/currency-audit-2026-08-20.md
---

# RedGold — Architecture Briefing

> Single-file condensation of `docs/specs/redgold/` (**16 numbered files plus a README, ~2,340
> lines** — re-counted 2026-08-20; this read "15 files, ~1900 lines") for handing to another
> model or reader. **It no longer condenses the whole spec:** five sub-project specs (RG-1 through
> RG-4, ~6,650 further lines) were written on 2026-08-20 and are not reflected below. Structured as claims, evidence, and architecture — not explanatory prose.
> Authoritative source is the split spec; this is a map, not a replacement.
> Date: 2026-08-04.

---

## 1. WHAT IT IS

- **RedGold** = a Claude Code plugin for authorized web/API security auditing of startup products.
- **Target client** = non-technical founders whose products were largely built by AI coding agents.
- **Operator** = one solo security contractor, Kali VM, Victoria Australia.
- **Business thesis** = move from "I can check your webapp" to "pay me to fix your product's
  security and arm your agents to keep it secure."
- **Entry contract** = "Client protects XYZ. White-box: here are creds + source. Black-box: here are
  URLs. Start."
- **Supersedes** = the prior engagement's `FRAMEWORK.md`, which was prose the model was asked to obey.

---

## 2. EVIDENCE BASE

### 2.1 Capability — what agents can and cannot do

| Fact | Value | Source |
|---|---|---|
| Detect a real bug-bounty vulnerability | **5.0–12.5%** | BountyBench arXiv 2505.15216 Tab.1 |
| Exploit, vulnerability pre-identified | **32.5–57.5%** (top 3 agents) | same |
| Patch a known vulnerability | **87.5–90%** | same |
| Per-agent rows | Claude Code 5.0/57.5/87.5 · o3-high 12.5/47.5/90.0 · o4-mini 5.0/32.5/90.0 | same |
| Blind web-app discovery coverage | **4–14%** | arXiv 2605.23243 (5 apps, 118 vulns) |
| CVE-Bench exploitation | 10% zero-day, 12.5% one-day | arXiv 2503.17332 §4.2 |
| Dominant failure mode | **"insufficient exploration", 37.5–80%** of failures | CVE-Bench Tab.5 |
| Tool misuse (category, not sqlmap-specific) | 5.0–47.5% | CVE-Bench Tab.5 |
| Hierarchical vs flat ReAct | 13% vs 2.5% | CVE-Bench |
| Knowledge vs execution gap | 70–89% vs 20–50% | CAIBench arXiv 2510.24317 |
| Chained exploitation vs active defences | **0 of 7 frontier models** | PACEbench arXiv 2510.11688 |
| Unguided single-attempt vs pass@30 | 55% vs ~100% (>40pp gap) | Cybench |
| Autonomous detection false-positive rate | **15.3–45.8%** across 6 frontier models | arXiv 2605.23243 Tab.2 |
| SAST-triage filtering FPR (**different task**) | >92% → 6.3% | arXiv 2601.22952 |

- **No benchmark measures open-ended web/API pentesting.** Any coverage percentage for that task is
  extrapolation, including RedGold's.
- Frontier labs state their own cyber benchmarks are **saturated** and no longer track capability.

### 2.2 Market — why this client segment

| Fact | Source |
|---|---|
| ~130,000 vibe-coded sites scanned; **~1 in 5 leaking secrets**; 16,000+ Firebase, 3,000+ Supabase creds | RedHunt Labs Project Resonance Wave 15 |
| 170 of 1,645 Lovable apps had **fully public databases** | CVE-2025-48757 |
| ~85% RLS missing on ≥1 table (n=50, directional only) | independent manual audit |
| Tea app: 72,000 images inc. 13,000 ID selfies; then 1.1M messages via a separate authz bug | July 2025 |
| Vercel/Netlify preview deployments **public by default**, routinely wired to prod DBs | Vercel docs |

### 2.3 Market — why "AI-powered" is a liability

| Programme | Event |
|---|---|
| curl | Bounty **terminated**. 20 submissions early 2026, **zero valid** |
| Internet Bug Bounty | New submissions **paused** after 14 years |
| Bugcrowd | Triage queues **+334% in three weeks**; suspensions for repeated AI-invalid reports |
| Nextcloud | Paid bounty suspended |
| Node.js | 30+ reports/month vs 2–3/week historical; new researchers locked out |
| Apple | Caps + cooldowns; a legitimate team **rate-limited out of reporting a real bug** |
| HackerOne | Leaderboard split: AI collectives vs individual researchers |

- XBOW's own writing: LLMs are *"trained to please, so their findings are not always reliable and
  need to be validated"*; general agents *"cannot reliably execute long, multi-stage attack
  sequences."* Independent analysis: ~1 in 3 XBOW reports valid.
- Google on Big Sleep: *"excels at variant analysis, not broad exploratory hunting"*; a
  target-specific fuzzer would likely be at least as effective.

### 2.4 Safety — why enforcement is mechanical

| Incident | Root cause |
|---|---|
| PocketOS — agent deleted a Railway production volume | Only barrier was a system-prompt instruction |
| Replit — deleted a live production DB during a code freeze, then said it was unrecoverable | same |
| McKinsey Lilli — unsupervised agent reached full prod read/write in 2 hours | same |
| Prior engagement — agent hand-rolled a curl loop, sent **20 requests against a ≤10 cap** | same |
| Prior engagement — 15 undeletable + 6 orphaned rows left in a client's live DB at handoff | no pre-write deletability check |

- Claude Code docs, verbatim: CLAUDE.md is *"context, not enforced configuration. To block an action
  regardless of what Claude decides, use a PreToolUse hook instead."*

### 2.5 Independent evaluation of agentic pentesting (Wavestone/RiskInsight 2026)

- Fabricated a **critical JWT finding with a non-working PoC**.
- **Missed an exposed admin interface with default credentials** — "a vulnerability no human
  pentester would overlook."
- "Tunnel vision": fixation on one irrelevant path at the cost of coverage.
- **Two runs on the same target produce substantially different findings.**
- Rarely builds business-logic understanding. Cost escalates on failure paths.

---

## 3. PRINCIPLES (P1–P11)

| # | Principle | Held because |
|---|---|---|
| P1 | Enforcement is mechanical, never advisory | §2.4 incidents; Claude Code docs |
| P2 | A finding is not a finding until something other than the model verified it | XBOW headless-browser confirm; Aardvark sandbox; CVE-Bench eval server; Strix PoC requirement |
| P3 | Seed hypotheses beat open-ended hunting | Naptime variant-analysis framing; CVE-Bench insufficient-exploration 37.5–80% |
| P4 | Audit between steps; do not fan out and vote | Agentic errors are systematic — one wrong action locks the trajectory; hierarchical 13% vs flat 2.5% |
| P5 | Retrieval on demand, not context stuffing | Vulnhuntr call-chain tracing; iteration 96% vs oracle-no-iteration 36.4% |
| P6 | One fact, one home | Prior engagement's status.md: 430 lines, five jobs, duplicate ID |
| P7 | Capability grows faster than complexity | Roster capped; library unbounded |
| P8 | Operator approves each escalation, not each engagement | Counter-examples: Strix "NOT ask for permission… 2000+ steps"; CAI `CAI_GUARDRAILS=false` |
| P9 | Calibrated honesty is a feature | Vendor FP rates lack methodology; §2.3 market |
| P10 | Deterministic baseline before agentic exploration, non-skippable | Wavestone missed-admin-panel failure |
| P11 | Repeatability is the product; the run is not | Wavestone non-determinism |

---

## 4. ARCHITECTURE

### 4.1 Two repositories, permanently separate

```
~/RedGold/                        framework. private git, installs as CC plugin
  .claude-plugin/{plugin.json, marketplace.json}
  agents/  skills/  commands/  hooks/  scripts/  playbooks/  templates/  evals/

~/engagements/<client>-<yyyy-mm>/ one private repo per engagement
  .claude/settings.json           ← ENFORCEMENT LIVES HERE, not in the plugin
  CLAUDE.md  status.md  session.md  scope.yaml
  assets/{register,candidates}.jsonl
  findings/*.json   evidence/
  ledger/{gates,activity,cleanup,blockers,phases}.jsonl  ledger/plan.json  ledger/sessions/
  deliverables/
```

- **Invariant:** client data never enters the framework repo.
- **Constraint driving the layout:** plugin-shipped agents **cannot** set `hooks`, `mcpServers` or
  `permissionMode` — silently ignored. So `/rg:new` writes the engagement's `.claude/settings.json`.
- **Payoff:** hooks fire for subagent tool calls unconditionally, with `agent_id`/`agent_type` on
  stdin. A project-level hook binds every agent and cannot be removed by one.

### 4.2 Agent roster — capped at 7

| Agent | Model | Memory | Tools | Role |
|---|---|---|---|---|
| rg-lead | Opus | — | Read, Grep, Glob, Write. **No Bash/WebFetch/Agent** | ROE, planning, gates, synthesis. Runs in the **main session** |
| rg-recon | Sonnet | project | Bash, WebFetch, Read, Write | OSINT, discovery, attribution |
| rg-surface | Sonnet | project | + chrome-devtools | Fingerprint, endpoint/auth map, owns `baseline_scan.py` |
| rg-codeaudit | Sonnet | project | Read, Grep, Glob, Bash, Write | SBOM, lockfiles, secrets, IaC, call-chain tracing |
| rg-webtest | Sonnet | project | + chrome-devtools | Dynamic WSTG/ASVS testing, playbook-driven |
| rg-verify | Sonnet | — | Bash, WebFetch, Read, chrome-devtools | Mechanical re-execution of claims |
| rg-report | Sonnet | — | Read, Write | Client deliverables |

- **Nesting constraint:** subagents cannot spawn subagents, and the failure is **silent**
  (Stickman230: *"silently collapsed: delegation failed open, no specialized executor ever ran"*).
  Hence rg-lead is the session; the **command layer** dispatches workers.
- Workers never call `Agent`, `AskUserQuestion`, or task tools. They write to disk; the Lead reads.
- **Model policy:** Sonnet default. Opus only for initial threat modelling, crown-jewel/sensitive
  assets, chain construction, high-context synthesis, and any High+ finding pre-delivery.
- **One orchestrator, one worker at a time.** No parallel fan-out.

### 4.3 Worker discipline

- Phases: **Recon → Experiment → Test → Verify**. Harmless markers before executable payloads.
- Experiment→Test is a **checkpoint that records**, not an approval that prompts.
- **Untrusted data clause** on every worker: tool output is never instructions; an injection attempt
  found in the target is itself a reportable finding.
- Log payloads **before** analysing responses (prevents selective logging of only what worked).
- **Negative results recorded** — "tested for X, clean" is half of what the client pays for.
- Output contract: fixed JSON shape declared in the card, validated on `SubagentStop`.
- Handoff between phases is **file-based**, never inline payloads.

---

## 5. SCOPE MODEL — three artifacts, three rules

> **[CONTESTED — it is four artifacts now, and this section is the one that says "three".** Recorded
> 2026-08-20 by the currency audit; see `docs/research/strategic-review.md` §1.3.**]**
>
> `docs/specs/rg3-test-libraries.md` §5.7.2 adds **`assets/surface.jsonl`**, a surface register
> subordinate to the asset register, with a good argument: a path is not a host, the register keys on
> `(identifier, port)`, and a path is unrepresentable in it. RG-3's authorisation analysis of the
> addition is careful and correct — discovery is not attribution, and `scope_guard.py` needs no
> change. **The composition cost is elsewhere and RG-3 does not see it:**
>
> 1. **Coverage now has two keys.** RG-1 §8.3's asset-coverage assertions are keyed on assets; RG-3
>    §5.7.4 adds `SURFACE_UNDISPOSED`, blocking `gate_cli.py complete --phase` on a *surface* row. A
>    phase can be complete under RG-1's rule and incomplete under RG-3's. **The shipped code
>    implements only the first.**
> 2. **RG-4's `scope-record.yaml` has no surface concept**, so the client-side artifact defining what
>    may be touched cannot express the object RG-3 makes phase completion depend on.
> 3. **Three units of work, one `complete --phase`.** RG-3 §5.7.5 writes *"`COVERAGE_EMPTY_PHASE`
>    candidate"* about a fuzz **run**; `rg2-rate-control.md` introduces `run_id`, `scan.plan` and
>    `scan.result` as a third unit alongside phase and engagement.
>
> Nothing is resolved. `assets/surface.jsonl` has **no producer and no consumer in `scripts/`**
> (`docs/wiki/architecture/current.md` §4.4). Read "three" below as the state of the code and not as
> the state of the design.

| Artifact | Contains | Rule |
|---|---|---|
| `scope.yaml` — **authorization boundary** | What the client *signed*. Coarse: `*.example.com`, `CLOUD_ACCOUNT`, `GITHUB_ORG`, `SUPABASE_PROJECT` | Changes **only by written amendment**. The only thing hooks enforce |
| `assets/register.jsonl` — **discovered assets** | Concrete assets + attribution signals + confidence | Grows all engagement. Itself a **deliverable** |
| `assets/candidates.jsonl` — **candidate queue** | Looks like theirs, unconfirmed | Untouchable except for attribution probes (§5.3) |

- **Asset type vocabulary adopted from HackerOne**, not invented: `URL, WILDCARD, CIDR, IP_ADDRESS,
  API, SOURCE_CODE, TESTFLIGHT, …` extended with `CLOUD_ACCOUNT, GITHUB_ORG, SUPABASE_PROJECT,
  FIREBASE_PROJECT`.
- **Attribution requires two independent signal classes.** Signals: `RDAP_REGISTRANT, ASN_OWNER,
  TLS_SAN, CT_COOCCURRENCE, DNS_CNAME_CHAIN, CONTENT_FP, ANALYTICS_ID, COPYRIGHT_STRING,
  AUTHENTICATED_CONFIRM, CLIENT_CONFIRMED`.
- **IP never counts alone** — Cloudflare/Vercel/Netlify edge IPs are shared across all tenants,
  which is by definition where this client base lives. Favicon hashes fingerprint the *platform*,
  not the owner.
- **Enforcement invariant:** active tooling targets only CONFIRMED rows mapping to an `in_scope`
  entry. Nothing an agent finds can widen what an agent may do.
- **Attribution carve-out:** tier 0–1 probes against CANDIDATES *inside* the boundary are allowed,
  rate-limited, logged, and **cannot produce a finding**. Attribution buys the right to identify,
  never to conclude.
- **Why this matters:** clients genuinely do not know what assets they own. Clicking a dashboard
  spawns cloud objects invisibly.

---

## 6. MODES AND TIERS

**The line is not read vs write.** It is *reversible + conspicuous + bounded* vs *irreversible +
sustained + exploitative*. Rate limiting is table stakes for an audit and cannot be checked without
writes.

| Tier | Contains |
|---|---|
| 0 Passive | OSINT, CT logs, passive DNS, archives. Never touches the target |
| 1 Safe active reads | Normal-user reads, bundle fetch, TLS/headers, read-only API calls |
| 2 Bounded reversible writes | Rate-limit probes, form/signup submission, non-destructive fuzzing, write-requiring authz tests |
| 3 Irreversible/sustained/exploitative | Exploitation, sustained load, chaining, real-world side effects |

| Mode | Ceiling | Purpose |
|---|---|---|
| `posture` | 1 | The cheap paid trial. Ceiling-1 + governance review |
| `audit` | 2 | **The main product.** Black and/or white box |
| `redteam` | 3 | Exception. Written authorization naming exploitation, emergency contact, non-prod preferred |

### 6.1 Conspicuous test data

- Every writable text field carries `RedGold-TEST-<engagement_id>-<seq>`.
- Dedicated operator-controlled email domain (must have real MX — engagement prerequisite).
- Residue removable by the client with one `LIKE 'RedGold-TEST-%'` query.
- **Cleanup appendix ships every engagement**, whether or not cleanup succeeded.
- Failure cases handled explicitly: non-text fields (identified by PK+timestamp), deliverability
  checks, WAF signature-matching the marker (re-run once unmarked), **third-party fan-out →
  tier 3, not tier 2**.

### 6.2 Finding classes

| Class | Established by | Verified |
|---|---|---|
| `technical` | Testing evidence | `replayed` / `executed` required above Low |
| `posture` | Observed config/metadata (no MFA, shared admin, public previews) | `n/a` + dated evidence |
| `governance` | Interview + document review (no IR plan, no security owner, no budget line) | `n/a` + dated evidence |

An audit spans "no whitelist on this firewall" through "you are not budgeting for security
governance." Posture/governance findings need no packet — this is what makes `posture` mode saleable
alone.

---

## 7. ENFORCEMENT

### 7.1 Hooks (installed per engagement)

| Event | Matcher | Script | Encoded lesson |
|---|---|---|---|
| PreToolUse | `Bash\|WebFetch\|mcp__.*` | `scope_guard.py` | Prose scope enforcement has a body count |
| PreToolUse | `Bash` | `no_handrolled_loops.py` | The 20-vs-10 request overrun |
| PreToolUse | `Bash\|WebFetch` | `canary_check.py` | 15 orphaned rows in a live client DB |
| PostToolUse | `Bash\|WebFetch\|mcp__.*` | `redact.py` | Secrets out of the transcript |
| SubagentStop | `*` | `validate_findings.py` | The validator that was never built |
| SessionStart | — | `session_start.py` | Context loss across compaction |
| Stop | — | `cleanup_gate.py` | Engagement closed with cleanup debt |

- **Deny format:** `{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny",
  "permissionDecisionReason":"…"}}` on exit 0.
- **`SubagentStop` exit 2 PREVENTS STOPPING — it does not retry.** Validator emits actionable
  corrections and escalates to a blocker after two failures.
- **CI invariant:** parse each agent card's frontmatter; if `tools:` grants Bash, require the
  scope-guard marker string or fail the build. (Pattern from `0xSteph/pentest-ai-agents`.)

### 7.2 scope_guard.py — steps

Scope checks (1–8): read scope+register → extract host → decode base64/32 → deny out_of_scope →
require CONFIRMED+in_scope → classify tier vs ceiling → check testing window → **fail closed**.

Plan checks (9–13): asset named in phase → test class authorised → write endpoint named and under
budget → live-confirm pending → plan/scope hash still valid.

### 7.3 **CRITICAL HONESTY: what scope_guard.py cannot do**

It is **defence-in-depth, not a security boundary.** Extracting a network target from an arbitrary
shell command is not solvable in general.

| Evasion | Why it is missed |
|---|---|
| `H=$(echo t); curl https://$H` | No literal host in the string |
| `echo 'curl …' > /tmp/a.sh && bash /tmp/a.sh` | Inspected call is `bash /tmp/a.sh` |
| `nuclei -l targets.txt` | Targets in a file the hook never opens |
| `curl --resolve`, `/etc/hosts`, proxies | Name disconnected from IP contacted |
| A 302 redirect | Destination chosen by the target, after the check |
| Hex, ROT13, URL-encoding, `python3 -c` | Decoding two encodings while ignoring infinite others |

**Client-facing claim, exact:** "The tooling mechanically refuses out-of-scope targets in the
ordinary case, and refuses outright when it cannot determine what it is about to touch. It is one
layer among several — not a guarantee the agent is incapable of reaching anything else."

Legal relevance: Australian Criminal Code Part 10.7 s478.1 — operator exposure turns on
authorization actually holding.

### 7.4 Gates — approval at plan time, not action time

| Gate | When | What |
|---|---|---|
| 0 Scope agreement | Planning | Operator + Lead agree scope, crown jewels, ceiling → committed `scope.yaml` |
| 1 Plan approval | Before execution | Approve `ledger/plan.json` once; execution within it is unprompted |
| 2 Deviation | Runtime | New asset / higher tier / unnamed endpoint → **denied by scope_guard**, blocker recorded |
| 3 Per-action | tier 3 only | Operator present, emergency contact, individual approval |

Rationale: an agent that never asks is the Strix posture; an agent that asks constantly trains
reflexive approval. Judgement is worth most when deciding *what will be done*.

Stale-plan rule: `scope_hash` + `plan_hash` on the gate record. Amended scope voids the approval.

### 7.5 Write authorisation

Write proceeds if **either**: (a) canary-proven — a canary write verified deleted via any path; or
(b) client pre-approved in `ledger/plan.json`. Denied only when neither holds.
A **cleanup credential is a nice-to-have** that upgrades (b) to (a), not a prerequisite.
Canary identity = `{method, route_template, operation}` — GraphQL's one URL serves many mutations.

---

## 8. FINDINGS AND VERIFICATION

```jsonc
{ "id":"F-007", "asset_id":"A-014", "asset":"…", "title":"…",
  "finding_class":"technical|posture|governance",
  "status":"PROVEN|SPECULATED", "verified":"none|replayed|executed|n/a",
  "confidence":"confirmed|probable|unconfirmed",
  "evidence_ptr":"evidence/F-007-anon-read.http",   // MUST RESOLVE
  "severity":"…", "likelihood":"…", "real_world_impact":"…",
  "tested_at_tier":1, "gate_ref":"G-002", "playbook_ref":"backends/supabase@2.100-2.110#rls-anon-read",
  "standard_refs":["ASVS-…","WSTG-…","API1:2023"],
  "remediation":"…", "cost_tier":"$|$$|$$$", "cleanup_required":false,
  "discovered_by":"rg-webtest", "verified_by":"rg-verify", "created":"…" }
```

- `evidence_ptr` must resolve to a real file/anchor. Unresolvable → auto-demote to SPECULATED.
- **rg-verify re-runs, does not re-read**: XSS → headless Chrome confirming JS *executed*; IDOR →
  replay under second auth context and diff; public bucket → re-fetch exact bytes; rate limit →
  re-run capped probe.
- **Six validation gates** (from `frendysanusi/claude-pentest-skills`): reproducible PoC · HTTP
  evidence both halves · concrete impact · in scope (**reject unconditionally**) · real
  vulnerability · client-reproducible with standard tools. Verdict VALIDATED/REJECTED/NEEDS-WORK.
- Framing kept verbatim: *"adversarial toward findings, not toward the tester."*
- **Known-false-positive table** (10 rows) in `playbooks/_generic/false-positives.md`: blocked SSRF,
  public-by-design IDOR, re-auth CSRF, self-XSS, HTML-encoded reflection, headers-without-exploit, …
- **Coverage gaps are a report section, not a footnote.**

---

## 9. PLAYBOOKS — the skill factory

- Each playbook is a **Skill**: name+description cost tokens at session start; body loads on
  invocation; **bundled files cost zero tokens until read**.
- **Dispatched, not listed**: `playbook-dispatch` reads `index.yaml`, matches the fingerprint, loads
  only what applies. Library grows unbounded; per-session cost stays flat.
- Structure: `PLAYBOOK.md` (seed hypotheses, secure defaults, check index) · `checks/*.yaml` mapped
  to ASVS/WSTG/API-Top-10 · `versions/2.100-2.110.md` ("what was tried against this version band")
  · `remediation/` · `handoff/` · `evals/evals.json`.
- **`_generic/` tier** that specific playbooks *specialize* — fixes the prior engagement's flaw where
  `supabase-audit` was both flagship and only implementation.
- **Startup default checks** (run because §2.2 says they are the modal failure): RLS/security rules,
  anon vs service_role key, public buckets, wildcard CORS, source maps, secret scanning, **Vercel/
  Netlify preview reachability**, no-auth serverless, admin routes in bundle, committed `.env`.
- Each playbook ships **evals** (3 should-trigger, 3 should-not-trigger).
- `/rg:harvest` promotes lessons into version-keyed files, **redacted**, at engagement close.

**Distinct from playbooks:** `baseline_scan.py` (P10) runs *before any fingerprint is known*,
unconditionally. Playbook checks are additive on top.

---

## 10. THE THREE FILES + LEDGERS

| File | Question | Rule |
|---|---|---|
| `CLAUDE.md` | What are the rules here? | ≤120 lines. True on day 1 and day 20. No findings, no history |
| `status.md` | What is true right now? | **Generated** by `regen_status.py`. Nothing writes to it directly |
| `session.md` | What happened, what should next session know? | Append-only. Fixed **HANDOFF block** injected by `session_start.py` |

Ledgers: `gates.jsonl` (with `scope_hash`) · `activity.jsonl` · `cleanup.jsonl`
(`pending|deleted|orphaned`) · `blockers.jsonl` (`deviation|cleanup|validation|capability|decision`)
· `phases.jsonl` · `plan.json`.

**Invariant: no fact lives in two files.** The prior engagement violated this — 430 lines, five jobs,
duplicate `L-002`.

---

## 11. INSTITUTIONAL MEMORY — never twice

| Mistake type | Fix belongs in | Guarantee |
|---|---|---|
| Checkable precondition on a tool call | **Hook** | Mechanical |
| Recurring judgement gap | CLAUDE.md / `.claude/rules/` → **hook on second recurrence** | Probabilistic |
| Multi-step procedure done incompletely | Skill with explicit checklist | Probabilistic |
| Output-shape drift | Validation script on `SubagentStop` | Mechanical |
| Target-specific tribal knowledge | Agent `memory: project` | Advisory |
| Cross-engagement tech knowledge | Playbook entry via `/rg:harvest` | Retrieved by fingerprint |

**Rule: the second occurrence of any mistake escalates it one level toward mechanical enforcement.
A repeated mistake is a missing hook, not a careless agent.**

---

## 12. GOVERNANCE

- **Third-party authorization**: the client cannot authorise testing of Supabase/Vercel/Netlify
  infrastructure they do not control. AUP position recorded per platform in `scope.yaml`.
- **Credentials**: never interpolated into a command string — `tool_input.command` is visible
  *before* PostToolUse redaction. Env var or config file only; `scope_guard.py` denies
  credential-shaped literals.
- **Inadvertent PII**: prove the boundary, not the payload. Smallest observation that demonstrates
  access, then stop. Privacy Act 1988 notifiable-breach implications flagged to client.
- **Critical findings**: stop the engagement, notify same business day.
- **Evidence**: encrypted at rest, destroyed on schedule (default 90 days post-delivery).
- **Closure checklist**: cleanup debt empty · credentials destroyed · retention set · register
  delivered · harvest run.
- **Not built, but required before paid work**: indemnity/cyber cover, engagement contract with
  liability cap, engagement pricing model, communication cadence, retest workflow.

---

## 13. DELIVERABLES

| Tier | Mode | Client receives |
|---|---|---|
| 0 Quick scan | posture | Asset register + severity-ordered findings |
| 1 Full audit | audit | + hardening playbook + calibrated next steps |
| 2 Audit + handoff | audit | + regression suite + **guardrail pack** (security CLAUDE.md, hooks, review skill installed in the *client's* repo) |
| 3 Retainer | negotiated | + living asset register + drift monitoring (CT-log polling first) + advisory feed |

The guardrail pack is the moat: the client's coding agent refuses to reintroduce the class of bug
found. Tiers 2–3 require the asset register to exist, which is why recon is not optional.

---

## 13.5 COMPLIANCE AND OBLIGATIONS (§21 — RESEARCH OUTSTANDING)

**Every legal figure, date and threshold in the spec's §21 is marked `[VERIFY]` and unconfirmed.
Do not treat any of it as accurate. RedGold does not provide legal advice.**

- **Core argument:** you cannot talk about risk without impact, and for an Australian small business
  impact is mostly legal. Severity without consequence is an opinion about software.
- **Commercial trigger — corrected 2026-08-20** (see `docs/research/privacy-act-feasibility.md`):
  the small business exemption (s 6D) has **not** been repealed and carries no commencement date for
  removal; Compilation No. 104 (4 June 2026) shows no amendment to s 6D since 2012 and the
  $3,000,000 turnover threshold intact. Removal remains a government "agreed in principle"
  commitment only, subject to further consultation `[VERIFY]` — no bill, no date. The dated market
  instead rests on two narrower, already-legislated obligations: AML/CTF "tranche 2" reporting
  entities pulled into the Act for their AML/CTF-related activities from 1 July 2026
  `[VERIFY — under audit]`, and automated-decision-making transparency (APP 1.7–1.9) commencing
  10 December 2026 for every existing APP entity `[VERIFY — under audit]`. Posture regardless: act
  as though the obligations already apply.
- **Customer reframe:** solo founders are the proving ground that generates playbooks and reputation;
  **small businesses with no compliance capability are the larger market**. Work profile shifts
  toward questionnaires, data-flow discovery, gap assessment and policy drafting. Same discovery/
  evidence/reporting pipeline; different questions asked of it.
- **Obligation register** — `~/RedGold/obligations/<regime>/` with fixed shape: `applies_when`
  (machine-evaluable triggers), `obligations[]`, `controls[]`, `tests[]` (linking to a playbook check
  or baseline item), `consequences`, `remediation`, `bookmarks`. The controls→tests link is what
  makes it operational rather than decorative.
- **Regimes to encode:** Privacy Act 1988 + APPs + NDB scheme · ASD Essential Eight · ASD ISM ·
  NIST CSF 2.0 / 800-53 / 800-171 / 800-115 · MITRE ATT&CK · ISO 27001 · PCI DSS · sector overlays
  (SOCI, APRA CPS 234, My Health Records, Consumer Data Right) · GDPR/UK DPA where users are there.
- **Data classification drives asset priority.** Assets gain `data_classes[]`; obligations attach to
  classes; priority follows from law rather than intuition. Candidate classes: personal, sensitive,
  health, government identifier, payment, credentials, location, children's, employee records — all
  `[VERIFY]` against the Act's own definitions. Inference by agents produces a *question for the
  client*, never a legal conclusion about them.
- **Findings gain** `obligation_refs[]`, `data_classes[]`, `notifiable_assessment`, and a fourth
  `finding_class: compliance` (gap against a named obligation, no exploit attached).
- **Open and explicitly unanswered** (§21.6): does Australian PII require onshore storage, or is
  residency a risk-reduction measure? How are offshore payment processors treated? What must a
  privacy policy disclose about offshore recipients? Sector-specific residency rules?
- **Research plan:** broad orienting pass, then nine narrow passes (Privacy Act core · exemption
  removal · NDB · penalties and actual enforcement · Essential Eight and ISM · NIST spine selection ·
  data residency · sector overlays · policy artifacts).

---

## 14. CALIBRATION — client-facing rules

**Required paragraph in every report** (full text in `14-calibration.md` §20.4). Core content:
patching ~87–90%; detection 5–12.5%; blind web-app coverage 4–14%; FPR 15–46% hence every finding
re-verified; most published figures are best-of-N with a 20–45pp gap to single-attempt; **no public
benchmark measures this kind of testing**, so any coverage figure is extrapolation. The report is a
prioritised map of what was found, not a proof of what is absent.

**Never say:** a single "we find X%" figure · "zero false positives" · saturated pass@30 numbers ·
"comprehensive/complete/full coverage" · vendor marketing figures, **including favourable ones**.

**Positioning:** never lead with the tooling. "AI-powered" reads as a warning label (§2.3). Sell
verified findings, a short proven list, repeatability, and business-logic judgement.

---

## 15. DESIGN DECISIONS AND THEIR COUNTER-EXAMPLES

| Decision | Rejected alternative | Because |
|---|---|---|
| Hook-enforced scope | Prose ROE | §2.4 incidents |
| One orchestrator, one worker | Parallel fan-out + voting | Agentic errors are systematic; voting cannot correct trajectory-locked errors |
| rg-lead in main session | Orchestrator subagent | Subagents cannot nest; failure is **silent** |
| Plan-time approval | Per-action approval | Constant prompting trains reflexive approval |
| Plan-time approval | Never asking | Strix: *"NOT ask for permission… 2000+ steps… NEVER give up early"* |
| Enforcement in the artifact | Runtime toggle | CAI: `CAI_GUARDRAILS=false` disables everything |
| Deterministic baseline first | Agent decides what to check | Wavestone missed an admin panel with default creds |
| Playbook dispatch | Flat skill list | Keeps per-session context cost flat |
| JSONL + git | SQLite findings DB | Greppable, diffable, auditable (open question §16) |

---

## 16. OPEN QUESTIONS

1. Should `rg-verify` run as a `context: fork` skill to keep verification output out of the Lead's
   context entirely?
2. SQLite vs JSONL once engagements exceed a few dozen findings — query convenience vs
   greppability/diffability?
3. Should the guardrail pack ship as a separate installable plugin for the client?
4. How specific must `ledger/plan.json` be before deviation checks become more friction than value?
5. What is the real cost/latency of mandatory re-verification on a full engagement?

---

## 17. KNOWN WEAKNESSES (stated, not hidden)

- `scope_guard.py` is not a security boundary (§7.3).
- Fail-closed denial will block harmless commands; accepted deliberately.
- Playbook knowledge rots; entries carry dates and are seed hypotheses, never conclusions.
- No benchmark validates the actual task; internal acceptance tests measure *reproduction of a known
  engagement*, not discovery.
- Attribution error is the worst realistic failure — mitigated by two-signal rule, IP never counting
  alone, and the untouchable candidate queue.
- Failed agent runs show ~9x token amplification (vendor-sourced figure, flagged as such).

---

## 18. BUILD ORDER (v1 = `posture` + `audit`)

1. Plugin skeleton + manifests → installs clean
2. `scope.yaml` schema + parser → round-trips the prior engagement as a boundary
3. `scope_guard.py` → denies out-of-scope, ceiling violation, base64-obfuscated target, undeterminable host
4. `/rg:new` scaffolder → hooks fire and deny end-to-end
5. `validate_findings.py` → **runs against the prior engagement's five phase JSONs and flags their known gaps**
5b. `baseline_scan.py` → finds the known public bucket with no fingerprint supplied
6. Findings schema + evidence capture → unresolvable pointer auto-demotes
7. `no_handrolled_loops.py`, `rate_probe.sh`, `canary_check.py` → the 20-request overrun is denied
8. Agent roster → rg-lead cannot issue a network call; a nesting attempt is caught loudly
9. `using-redgold` + three-file contract + `regen_status.py` → status.md regenerates identically

v2: `playbook-dispatch` + evals (10), `/rg:harvest` (11), agent memory, tier-3 redteam path.

**Overall acceptance: re-run the prior engagement end-to-end under RedGold** — same findings, with
resolvable evidence, no ROE violations, no cleanup debt.

---

## 19. PRIOR ART — what was taken and from where

| Source | Taken |
|---|---|
| `frendysanusi/claude-pentest-skills` | Six validation gates, FP pattern table, "adversarial toward findings" framing, log-before-analyse |
| `Stickman230/claude-pentest` | Nesting-collapse lesson, Recon/Experiment/Test/Verify phases, gate at Experiment→Test, untrusted-data clause, confidence enum, coverage-gaps-first-class |
| `0xSteph/pentest-ai-agents` | CI scope-guard invariant, findings-DB schema shape, per-step approval in chaining, evidence naming |
| Google Naptime/Big Sleep | Variant-analysis framing = seed hypotheses; tool design over prompting |
| XBOW | Non-LLM verification gate (headless browser confirms execution) |
| Vulnhuntr | Call-chain retrieval-on-demand; confidence anchored to a checkable criterion |
| HackerOne | Asset-type vocabulary for scope |
| Qualys | Attribution confidence cascade |
| **Strix** | **Counter-example**: "NOT ask for permission", 2000+ steps |
| **CAI** | **Counter-example**: runtime-disableable guardrails |

---

## 20. OPERATIONAL NOTES FOR ANY MODEL WORKING ON THIS

- Use `api.github.com/repos/OWNER/REPO/git/trees/main?recursive=1` for repo maps — not an agent.
- WebFetch's summarizing layer has **refused defensive security source** as a "jailbreak attempt";
  raw API JSON bypasses it. Avoid strident framing ("MANDATORY", "Hard Refusal List") in RedGold's
  own files for the same reason.
- One narrow task per research agent, with exact paths. Do not launch many in parallel.
- Split documents before they grow; use frontmatter and an index.
