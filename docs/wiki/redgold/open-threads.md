---
title: Open threads — what is next, and what must not be lost
question: If I am a cold agent starting a session, what should I be working on and what is already decided?
status: draft
date: 2026-08-20
last_verified: 2026-08-20
---

# Open threads

Written at the close of 2026-08-20 so it survives to the next session. **Read `facts.md` first** —
it holds the findings; this holds the work.

Ordering is deliberate. Items are ordered by *what unblocks the most*, not by interest.

---

## 0. The standing constraint

**No target is authorised by default, and a chat message is not an authorisation record.**
An engagement begins when an authorisation document exists on disk and `/rg:new` has run.
The self-authorization for the operator's own target **expired 2026-08-18** and must be renewed
before anything runs against it — a short edit to a document the operator owns, but it happens
first.

---

## 1. Blocks the next engagement — do these before running anything

| # | Item | Why now |
|---|---|---|
| 1 | **Stop `baseline_scan` self-certifying `verified: "executed"`; pin status-only checks to `info`.** Both are specified (RG-1 §4.5, §5.3); neither is built. | Without this, an engagement against an SPA that 200s everything produces a **fabricated critical in the client report**. Any run before this fix teaches the wrong lesson. |
| 2 | **Give `created` a producer, or stop `REPORT_STALE` depending on it.** | The first agent-authored finding permanently blocks `/rg:close` today. |
| 3 | **Run one complete engagement end-to-end against an owned target, and record the hours.** | Briefing §18's acceptance test, written down and never run. Produces the first duration number — the missing denominator under every build-or-skip decision in RG-2 and RG-3. Judgement 6 predicts it finds what reading cannot. |

---

## 2. The engagement knowledge that does not exist yet

The operator's observation, and it is correct: **a red-team agent currently has no idea what to do,
how, or in what order.** There is no tool list, no methodology reference, no ordering. This is a
larger gap than any control defect, because a control only matters once work is being done.

Needed, roughly in dependency order:

- **A tool inventory.** Which tools, pinned how, for which phase. Note the operator's steer: Kali's
  packaging is often not the best available version, and there are better-maintained alternatives
  worth evaluating rather than defaulting — e.g. Go-based port scanners, and `smap`, which answers
  from Shodan rather than touching the target at all. **The operator holds a Shodan key**, which
  makes passive reconnaissance possible without a packet reaching the client. That is worth a lot
  under both the rate-control and the tort analyses.
- **Explicit rejection recorded:** BlackArch has tools Kali lacks, but pulling AUR packages into a
  sensitive client engagement is an unacceptable supply-chain risk. Not "later" — decided against.
- **Methodology references, retrieved and pinned**: MITRE ATT&CK, NIST (800-115 and the CSF),
  OWASP WSTG and ASVS. Today's severity work established that **ATT&CK is being stretched** when
  used as a precondition ladder — it describes post-compromise behaviour and collapses pre-auth web
  flaws into T1190 — so retrieve it for what it is good for and do not reuse the earlier framing.
- **Per-tool operating guidance**: ZAP in particular has none. What mode, against what, with what
  authentication, producing what artifact.
- **Phase ordering**: what runs first, what gates what, what a worker agent is handed.

None of this is speculative design — it is the difference between an agent that works and one that
improvises. Do it before adding another control.

---

## 3. Hardening the harness itself

Follows directly from `../claude-code/execution-model.md`. The findings there are not academic:
the shell snapshot is writable by the agent's own uid and is sourced before every command, and the
OAuth token sits in a file readable by any child process.

- Run Claude Code as a **hardened, non-sudo user** with its own environment.
- The contained agent must **not share a uid** with the credential holder.
- Root-own hook scripts and `settings.json`; make the shell snapshot not agent-writable.
- Consider enabling the Bash sandbox — it is the only mechanism that covers **child** processes —
  with `allowUnsandboxedCommands: false`, and measure what it breaks against the scanner workload
  before committing. `[VERIFY]`

---

## 4. Decisions waiting on the operator

| Decision | State |
|---|---|
| Mini-PC lab vs laptop VMs | Recommendation is laptop-first with named triggers to buy; the strongest trigger is two concurrent engagements. |
| Documents to retrieve | `~/REDGOLD-NEEDS-FROM-YOU.md`, headed by the **Criminal Code** (the actually-criminal question), then LPUL from a government host, then the TFN and Medicare algorithms. |
| Lawyer and broker | Four legal items and one insurance item. Elapsed-time-bound, not effort-bound — one email each starts them. |
| ~25 spec decisions (D-3…D-17) | Each carries a recommendation. Collected at the end of each sub-project spec. |

---

## 5. Deliberately not being done

Recorded so nobody re-opens them by accident:

- **No new sub-project specs** until an existing one ships a release. The 2026-08-20 session
  produced ~15,000 lines of research against 7,576 lines of code; the composition disagreed in four
  places and 19 controls could not fire. More specification was not the missing ingredient.
- **Containment above its cheap 20%** — build the non-sudo user, root-owned hooks, cap-drop and
  `open-vm-tools` removal; hold the gateway VM, the ulogd normaliser and `rg-reconcile`.
- **Deepening the severity model** — an eight-rank capability ladder fitted to eleven findings from
  one engagement is design-from-n=1 by the repo's own judgement 1.
- **More tests of the existing kind.** The suite scores 68% on fine-grained mutation with survivors
  on the boundaries that matter. Adding ±1 faults to `verify_controls.py` is worth more than
  another hundred tests.

---

## 6. Framing worth keeping

This is **R&D, not product development.** The work of the last sessions has been discovering hard
blocks in the architecture — several of them imposed by the harness rather than by design choices.
That is a legitimate phase and the strategic review's revenue-focused criticism should be read
against it rather than as a verdict. It should also not become permanent: the review's central
point stands that nothing has been sold and nothing has run against a real target.

## See also

- `facts.md` — the distilled findings, which is the page to read first
- `../architecture/current.md` and `proposed.md`
- `../../../status.md` — authoritative for what is built and what is not
