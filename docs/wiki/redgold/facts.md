---
title: Hard-won facts — the things that cost a session to learn
question: What did we establish the expensive way, and where is the full reasoning?
status: draft
date: 2026-08-20
last_verified: 2026-08-20
---

# Hard-won facts

**Read this before opening any research document.** On 2026-08-20 a single session produced
**15,131 lines** across 18 research files. The findings that matter are a page. This is the page.

Each entry: the fact, why it bites, and where the reasoning lives. If an entry and its source
document disagree, **the source document wins and this page is stale** — fix it.

Provenance markers follow `../README.md`: `[SOURCE: x]` verified from a primary source,
`[VERIFY]` unconfirmed, `[INFERRED]` reasoned but untested.

---

## 1. The harness will not enforce anything for you

| Fact | Why it bites |
|---|---|
| **Hooks fire on tool calls, not syscalls.** A child process of a Bash command is entirely unhooked. `[SOURCE: docs + observation]` | Every control is bypassed by one level of indirection. See `claude-code/execution-model.md`. |
| **The shell snapshot is sourced before every Bash call and is writable by the agent's own uid.** `[SOURCE: observed, mode 664, same uid]` | Append `curl() { … }` and the hook inspects a string that is genuinely in scope, allows it, logs an allow row — and something else runs. **This defeats the parser without obfuscating anything.** Worse class than the base64 evasions §9.3.1 concedes. |
| **The OAuth token is a 600 file under the same uid**, read successfully from a direct child, a grandchild, and a detached process. `[SOURCE: observed]` | `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB` scrubs the *environment*; the token is in a *file*. The contained agent must run as a different uid. Not a preference — a requirement. |
| **One process per Bash call, a direct child of `claude`.** cwd persists because it is written to a file and replayed as a spawn parameter. `[SOURCE: docs + observed PIDs]` | There is no session to hold state in, so nothing can be "remembered" between calls except through disk. |
| **`Stop` fires once per turn. `SessionEnd` cannot block. There is no engagement-close event.** `[SOURCE: hooks docs]` | An engagement is not an object the harness models. `/rg:close` is a command, not a gate, and an operator who skips it is stopped by nothing. |
| **`updatedToolOutput` is absent from the published hooks reference**; it appears in the CHANGELOG at v2.1.121 as "previously MCP-only". Installed here: 2.1.212. `[SOURCE: CHANGELOG]` | `redact.py` depends on it. It works today and would have been a **silent no-op** weeks ago. Needs a `SessionStart` self-test or the control can stop existing without saying so. |
| **Plugin-shipped agents cannot set `hooks`, `mcpServers` or `permissionMode`** — silently ignored. `[SOURCE: plugins reference]` | Why enforcement is written into each engagement's `.claude/settings.json` by `/rg:new`, and why the framework repo has no `.claude/`. That absence is correct, not a bug. |

Full detail: `claude-code/execution-model.md`, `claude-code/hooks.md`, and their `-redgold-notes` companions.

---

## 2. Our own controls, honestly

| Fact | Why it bites |
|---|---|
| **19 controls cannot fire.** They read fields nothing produces, or produce too late, or that something overwrites first. `[SOURCE: architecture/current.md]` | **All 19 are invisible to all 60 injected faults** — mutating a control that cannot fire changes no test outcome. Fault injection is structurally blind to a dead control. |
| **`_admin_reachable` is `return probe.status == 200`, and `baseline_scan` self-certifies `verified: "executed"`.** | Against an SPA that 200s everything — the modal shape for this client segment — this puts a **fabricated critical in the client report, past every gate.** That is the Wavestone failure P10 exists to prevent, reproduced by the component built to prevent it. |
| **`REPORT_STALE` reads `created`; only `baseline_scan` writes it.** | The first agent-authored finding **permanently blocks `/rg:close`**. Fires on 100%. |
| **`scope_guard` returns `set()` for `bash /tmp/a.sh`, `python3 x.py`, `make deploy`, `npm run start`** — allowed, and no ledger row. `[SOURCE: ran extract_hosts]` | §9.3.1's documented example is the case that *works*. Splitting write and execute across two tool calls defeats it. |
| **`no_nesting.py` guards 4 of the 12 nesting tools it knows about** — exact alternation matcher. `SendMessage` is unguarded, and its own comment says it had to be added. | |
| **`scope_cli.py amend` rewrites `scope.yaml` from `to_dict()`**, destroying unmodelled keys. | The first amendment after RG-2's `parity` block lands deletes the client's signed dev/prod attestation. |
| **68% fine-grained mutation score.** `MAX_URLS_PER_COMMAND` can be 2, 3 or 4, and `>` can become `>=`, with a green suite. | The suite establishes *that* a control fires, almost never *where its edge is*. All 12 faults added on 2026-08-20 are gross mutations. |
| **gitleaks and trufflehog have a 0% hit rate on the only leak this repo has ever had.** | A client name is not a credential and matches no rule. Both checks that would have caught it are ~40-line project-specific scripts. |

The generative defect: **RedGold has no dataflow contract.** Specs say what to check; nothing records
who writes each field, when, and who reads it. Fix is `architecture/proposed.md` R1.

---

## 3. Law — verified, and each one changes a decision

| Fact | Why it bites |
|---|---|
| **The small business exemption was never legislated away.** `s 6D` in force, $3,000,000 threshold, no amendment since 2012. `[SOURCE: Compilation 104, 4 June 2026]` | The "market with a deadline" thesis had no deadline. Corrected in `~/NORTH_STAR.md`. |
| **AML/CTF tranche 2: 31 Mar 2026** (reporting-entity status, so the Privacy Act hook), **1 Jul** (obligations), **29 Jul** (enrolment). `[SOURCE: Act No. 110 2024 as made]` | The real dated hook. A missed enrolment is a sales opener. |
| **APP 1.7–1.9 (automated decision-making) commence 10 Dec 2026.** `[SOURCE: Act No. 128 2024, sch 1 items 87–89]` | Dated, infringement-notice-backed, lands on AI-built products. |
| **18 U.S.C. § 2713**: a provider must disclose data in its *"possession, custody, or control, regardless of whether … located within or outside of the United States."* `[SOURCE: statute]` | The hinge is a **corporate test** and the clause disclaims location. **"Inference runs in Sydney" is sayable. "Your data is sovereign" is not.** Encryption cannot rescue it — the model must see plaintext. |
| **Local inference on owned hardware defeats the jurisdictional half** (no provider = nothing to compel) **and only that half.** Supply chain remains. `[INFERRED]` | Sovereignty has two axes; owning hardware moves one. |
| **The Schedule 2 tort is civil, not criminal**, needs all five elements (intent/recklessness, seriousness, and a balancing test naming crime prevention), and **only an individual can sue**. `[SOURCE: Compilation 104 Sch 2]` | Red teaming is not illegal. But **there is no cl 8 defence for acting under contract with the data holder** — a signed scope helps on the elements, never as a defence. The criminal question is Criminal Code Part 10.7, which turns on *unauthorised*. |
| **No certification scheme exists** — `s 33C` makes "privacy assessment" the Commissioner's own power. `[SOURCE: Compilation 104]` | "Certified" would be false. Even "privacy assessment" is best avoided. |
| **LPUL s 11 engages on marketing copy alone**, independently of delivery. `[VERIFY — non-government host]` | Answer this before a website exists, not before a client does. |
| **Trade/professional association membership *is* sensitive information; biometric is conditional on purpose; location is *not* sensitive but *is* personal.** `[SOURCE: s 6(1)]` | Three facts an automated classifier gets wrong. "Is this sensitive?" and "is this dangerous?" are different questions. |
| **The IHI is the only refusal-grade identifier** — 16 digits, prefix `800360`, Luhn. A bare 9-digit number passes the TFN mod-11 check **~1 in 11**. `[SOURCE: HL7 AU Base]` | A context-free TFN detector fires on ~9% of every 9-digit ID and gets disabled in a week. TFN and Medicare algorithms could not be primary-sourced — Presidio's cites Wikipedia. |

Full reasoning: `docs/research/privacy-act-feasibility.md`, `data-sovereignty.md`,
`sovereignty-and-pre-ingestion-controls.md` (all three **gitignored** — on disk, not published).

---

## 4. Tooling — each of these was a trap

| Fact | Why it bites |
|---|---|
| **`nuclei -td <dir>` does not pin templates.** `-td` is a **boolean** `template-display` flag at v3.11.1. Correct pinning is `-t <dir>` plus `-duc`. `[SOURCE: cmd/nuclei/main.go]` | It does not error. It runs against default template resolution **while appearing pinned**. The canonical example of judgement 8. |
| **Nuclei's `code` protocol executes on the scanning host, not the target.** `[SOURCE: CVE-2024-43405 class]` | An agent-reachable code-exec primitive in a template file. Exclude mechanically, not by note. |
| **Nuclei's default rate is 150 rps; `nmap --max-rate` does not bound NSE; `testssl` has no rate option at all.** | The request budget is post-hoc detection, not a control. |
| **`no_handrolled_loops.py` cannot see a scanner.** One command line, ~1,500 requests, no shell loop. | The control encoding the 20-vs-10 overrun incident is defeated by the entire tooling class RG-3 adopts. |
| **Selective TLS interception makes external rate limiting a real boundary.** The no-interception rule was destination-specific (it would log the API key) and had been applied universally. `[SOURCE: mitmproxy `ignore_hosts`, Squid `ssl::server_name`]` | The flow that needs counting is the flow that is safe to bump. **Price:** every TLS observation through a bump describes the proxy — fabricating a cert-validation finding about the client's real host. Needs a splice register. |
| **VMware Fusion is free for commercial use** since Nov 2024 / Mar 2025, no licence key. `[SOURCE: Fusion 26H1 release notes]` | No vendor support entitlement, though. **Proxmox cannot run on Apple Silicon** — x86-64 only. |
| **Bedrock has an Australian geo with an Opus-class model** (`au.anthropic.claude-opus-4-8` → `ap-southeast-2`/`4` only). But `AWS_REGION=ap-southeast-2` **alone derives the `apac.` prefix** and routes to Tokyo/Seoul/Mumbai/Singapore. `[SOURCE: AWS + Anthropic docs]` | Pin the full `au.` model ID **and** an IAM condition. Judgement 8 again: a setting that looks like pinning and silently is not. |
| **Official Kali container images carry active `linux/arm64` manifests**, ~50 MiB, weekly cadence. `[SOURCE: Docker Hub v2 API]` | The 9.7 GiB guest is packaging for the tools. A container inside `rg-work` gives the same tools and leaves ~3 GB more RAM. |

---

## 5. What has never been done

- **RedGold has never run against a live external target.** Every green number describes behaviour in tests.
- **Off-host egress filtering does not exist.** The only real boundary. Permitted claim: *"out-of-scope targets are refused by tooling and logged"* — never *"cannot happen."*
- **The briefing's own §18 acceptance test has never been run.** An end-to-end engagement against an owned target, with the hours recorded, is the cheapest thing that would resolve the most open questions.
- **No engagement playbook exists.** `playbooks/` holds one file, and it is about reviewing RedGold itself.

---

## See also

- `open-threads.md` — what is next and why
- `../architecture/current.md` — what exists; `../architecture/proposed.md` — what should replace it
- `../../research/strategic-review.md` — the blind spots, including this project's own conduct
- `../../../CLAUDE.md` — the eight design judgements, which are the compressed version of *how* to work here
