---
title: Agent orchestration lessons from the reference-repo operator
source: github.com/the-operator/reference-repo, read 2026-08-04
status: research note — extracted for RedGold framework design, not a client deliverable
---

This note distills engineering/orchestration lessons from a private repo (`reference-repo`, a
forked open-source CMS product build) where the operator ran a Claude Code multi-agent orchestration
system for several weeks. Product/business content (client identity, pricing, feature specifics,
security findings about the product itself) is deliberately excluded — only the *mechanics of
running the agent system* are extracted, per the framework-repo rule against client/business data.

21 files were requested; 21 were fetched successfully; **zero 404s**. Full list in §4.

---

## §1 The skills-in-subagents lesson

**Verdict up front: not found as stated.** I could not locate a document in this repo that
narrates a discrete incident of "skills failed to propagate into subagents, here's what broke,
here's the fix." I searched every fetched file for "skill" (case-insensitive) and read the
surrounding context on each hit; there is no retrospective entry, dated postmortem, or "learned
the hard way" note about skills specifically not being inherited or copied into subagents. If the
operator's memory is of a concrete failure-and-fix, it is not written down in these 21 files — it
may live in a session that predates the earliest docs here, in a memory file this task didn't
fetch, or the memory may be conflating skills with the (very well-documented) fact that
**conversation state, STATUS.md, and ledgers** don't propagate to subagents (see below).

What **is** verbatim and grounded in these files, and is the closest real thing to what the
operator may be recalling:

**1. A standing, dated recommendation that skills do NOT auto-share across agent cards, and that
the fix (native `skills:` frontmatter) had not yet been adopted.** From
`docs/product/agents/README.md` (2026-06-21 audit):

> "De-duplicate the landmine block (repeated in implementer + fixer) into the `fork-dev`
> skill, loaded via `skills:` — single source."

And from `docs/product/agents/CARD-AUDIT-2026-06-21.md` (Gap 6, "MINOR: leverage native features the
cards reinvent in prose"):

> "`skills:` can preload `fork-dev` into implementer/fixer so the landmines load as a skill
> rather than being re-pasted into every card. (sub-agents doc, frontmatter table)"

Mechanism implied: at the time of this audit, the five agent "cards" (`orchestrator.md`,
`implementer.md`, `reviewer.md`, `fixer.md`, `auditor.md`) were **prose docs, not loadable
`.claude/agents/*.md` subagent definitions** — confirmed elsewhere in the same audit: "The five
files live in `core/docs/product/agents/` and are role documentation, NOT `.claude/agents/*.md`
files (verified: no `.claude/agents/` in the project)." Because there was no frontmatter, there
was no `skills:` field to load a shared skill into a subagent — so a "landmine" list (DB gotchas,
test-framework quirks, migration ESLint rules) had to be **hand-copied into both `implementer.md`
and `fixer.md`,** and the audit calls this out as a drift risk. This is a design gap the operator
was warned about and (per this audit) had not yet fixed — not a "we tried skills and they silently
didn't load" failure.

**2. The broader, explicitly-stated inheritance boundary — CLAUDE.md yes, everything else no.**
This is well documented and is likely adjacent to what's being remembered. From
`docs/product/backups/CLAUDE.md` ("Before spawning a subagent (Checkpoint-out)"):

> "Subagents DO auto-receive this CLAUDE.md (project instructions load into every spawn) but
> inherit NOTHING else — no conversation, no STATUS.md, no memory, no ledgers. So briefs must
> restate STATE (the task, decisions, file paths, carries) but need NOT restate RULES already in
> this file (fork discipline, test commands, repo layout) — don't bloat briefs re-teaching the
> rulebook. EXCEPTION: an agent working in an isolated WORKTREE cwd may not resolve this file —
> worktree briefs stay fully self-contained. [[worktree-superpowers-gitignored]]"

And from `docs/product/agents/implementer.md`:

> "Model: **sonnet** (the floor for prose/plan-driven work; haiku only for trivial single-file
> mechanical edits). Inherits NOTHING — the dispatch must be self-contained."

Note the tag `[[worktree-superpowers-gitignored]]` on the CLAUDE.md quote — its name strongly
suggests a **worktree-specific** failure: something under `.superpowers/` (gitignored scratch/
ledger state, per the workspace map: "`.superpowers/sdd/` ledgers … (gitignored)") does not carry
into a freshly created git worktree, so an agent spawned into an isolated worktree cwd cannot
resolve CLAUDE.md (and by extension, presumably, anything that lives beside it) the normal way and
must get a fully self-contained brief instead. This is the one place in these files where
something *skill/rule-adjacent* is documented as failing to propagate into a subagent under a
specific condition (worktree isolation) — but the file itself was not fetched (this task's list
didn't include whatever `worktree-superpowers-gitignored` points to), so the mechanism can't be
confirmed beyond this one inline note.

**3. In the base open-source project's own instructions, skills are explicitly NOT ambient — they are
loaded by name/path on demand.** From `CLAUDE.md`/`AGENTS.md` (repo root, symlinked/identical):

> "When the user asks you to create a commit or draft a commit message, load and follow the
> `commit` skill from `.agents/skills/commit`."

This confirms the project's working assumption throughout: a skill is not something an agent
"has" by default — it is invoked by explicit instruction referencing its path. That's consistent
with (but does not prove) a "skills don't get inherited automatically" lesson.

**Plain conclusion:** the specific claim — "the operator hit a concrete bug/incident where skills
silently failed to propagate into subagents" — is **not supported** by these 21 files. What is
supported, with verbatim citations, is (a) a standing architectural gap where shared "landmine"
content had to be hand-duplicated across cards because the cards weren't yet frontmatter-based
subagent definitions with a `skills:` field, and (b) a strongly and repeatedly stated rule that
subagents inherit CLAUDE.md but nothing else (conversation, STATUS.md, memory, ledgers) unless the
brief restates it — with one flagged worktree-specific exception whose underlying incident this
task could not read. If this lesson matters to your framework, I'd suggest either re-asking the
operator for the specific session it happened in, or fetching whatever
`[[worktree-superpowers-gitignored]]` points to (likely a `.remember/` or auto-memory entry, not
in this repo's tracked docs).

---

## §2 Lessons by theme

### Context/state management

**Claim: reading a large "current state" file in full at every session start is a documented cause
of model degradation, not just a theoretical risk.**
> "CLAUDE.md resume step 1 instructs the fresh orchestrator to 'Read STATUS.md in full.' So every
> session begins by ingesting 1,652 lines that … Burn a large fraction of the context window before
> any work starts — the exact precondition for the degradation already observed."
— `docs/product/orchestration-audit-2026-07-02.md`
Implication for a security-auditing framework: any "read the full findings log on resume" pattern
is a latent context-poisoning bug. Cap state files hard and split current-truth from history.

**Claim: state fragmented across multiple overlapping stores (a hand-maintained status file, a
roadmap file, per-feature ledgers, and two separate auto-memory systems) drifts and duplicates.**
> "CLAUDE.md declares STATUS the single source of truth, but the two memory systems write parallel
> histories that can and do drift, and spend tokens re-injecting redundant summaries every
> session."
— `docs/product/orchestration-audit-2026-07-02.md`, Finding 3
Implication: declare exactly one current-state authority and one detail-ledger; treat any
auto-memory/plugin memory as disposable and advisory, never authoritative — the fix applied here
was to explicitly say so in the rulebook (`docs/product/backups/CLAUDE.md`: "`.remember/` plugin
files and auto-memory are disposable/advisory and MAY lag or contradict — never treat them as
project state").

**Claim: operator-level settings (a terse/compressed output style) actively fight the orchestrator's
core job of writing precise subagent briefs.**
> "Caveman mode ('drop articles/filler/hedging, fragments OK') directly fights the orchestrator's
> single most important work product: precise, fully self-contained subagent briefs. … An
> under-specified brief to a cold Opus agent is the most expensive failure mode in the whole system
> (a wasted high-tier run + a review cycle to catch the divergence)."
— `docs/product/orchestration-audit-2026-07-02.md`, Finding 4
Implication: verbosity/compression settings that are fine for a human-facing chat session can be
actively harmful for the specific artifact an orchestrator produces (dispatch briefs). Worth an
explicit carve-out in any framework that supports output-style toggles.

### Cost / model tiering

**Claim: a risk-based tiering rule collapses to "everything is the expensive model" in practice
once nearly every task touches a flagged risk category.**
> "The tiering rule marks security / DB-schema / architecture as Opus for both implementer and
> reviewer, plus 'when in doubt, Opus.' For a product handling sensitive user data, nearly every task touches one
> of those, so in practice almost everything runs Opus×2. That is defensible for correctness and is
> also exactly the cost the operator is feeling."
— `docs/product/orchestration-audit-2026-07-02.md`, Finding 5
Implication for a security-auditing framework: a similar "escalate to the strongest model whenever
security-adjacent" instinct will over-trigger for a tool whose whole job is security. The
documented fix was decoupling implementer tier from reviewer tier (cheap implementer behind an
expensive reviewer gate) and reserving double-audits (pre-build + post-build) for genuinely
high-risk work only — not blanket escalation.

**Claim: middle-manager ("build-lead") agents hit a token cost wall that flat orchestrator→leaf
dispatch avoids.**
> "PLAN T0–T8 (per-task Opus LEAF pipeline — build-leads shelved, ~292k birth-cost wall
> [[subagent-instruction-token-budget]]; lean self-contained briefs)"
— `docs/product/backups/STATUS.md`
> "build-lead birth-cost wall (~292k): middle-manager agents can't birth with headroom → drive
> per-task with single-purpose LEAF agents (implementer+reviewer)."
— same file
Implication: a deep orchestration hierarchy (orchestrator → build-lead → implementer → reviewer)
adds a real, measured token tax per layer before any work happens. If a framework plans more than
one management layer, budget for this explicitly rather than assuming layering is free.

### Silent vs. loud failure

**Claim: background subagents can have their final result misrouted if the parent that spawned
them has already stopped.**
> "Run your reviewer/implementer subagents FOREGROUND (blocking), not background. A background
> child that finishes after you stop gets its verdict misrouted to the main conversation while you
> sit 'waiting' forever (observed 2026-07-04). Background is for YOU (the caller runs you in
> background); your own children block."
— `docs/product/backups/orchestrator-agent.md`
Implication: background dispatch is not a free performance win — a synchronous verdict a parent
agent needs to act on should be foreground, and background is reserved for the top of the chain
only. This is a genuinely load-bearing operational rule, not a style preference.

**Claim: automated verification (unit + integration tests, code review, and an independent
security audit, ALL green) can still certify a broken product.**
> "GREEN TESTS/AUDITS ≠ A WORKING PRODUCT (learned the hard way 2026-07-14). A form-editing UI
> passed every unit/integration test + security audit + code review + green build and was still
> broken in 6 places in the real browser (type-drift: admin code hydrating against imagined server
> shapes, mocked tests validating the wrong fixtures; + reachability: a working page nothing in the
> nav linked to)."
— `docs/product/backups/CLAUDE.md`, "Definition of done"
Implication: this is the single most concrete "agents claiming work was done when it was not"
finding in the corpus, and it's not about an agent lying — every individual gate passed honestly.
The failure mode was that no gate exercised the *actual end-to-end interactive surface*; each gate
verified a piece in isolation (mocked components, unit assertions, static code review). The fix
adopted was a mandatory "UI-journey gate" for any interactive/HIGH-risk feature, run against real
server response shapes, not admin-side type definitions:
> "For any user-facing feature with an interactive flow (create/edit/save/multi-step) or
> money/authz/PII surface, 'done' now REQUIRES a passing UI journey."
For a security-auditing framework this generalizes directly: an audit that only inspects
code/config/tests in isolation, no matter how many layers of review, can still miss the thing that
only shows up when the actual live surface is exercised end to end.

### Testing / done-signal discipline

**Claim: raw test-pass counts were being used (and are unreliable) as the completion signal.**
> "STATUS repeatedly cites raw counts as the completion signal ('410 tests ✓', '27 tests', '36
> feature tests'). Counts are not coverage: the review history shows near-vacuous tests caught only
> by reviewer/advisor … and some suites were not executed at all."
— `docs/product/orchestration-audit-2026-07-02.md`, Finding 9
Fix codified into the rulebook:
> "Every new test must be shown RED before green (or the reviewer explicitly confirms it
> discriminates); a raw pass count is not evidence of coverage. If a suite genuinely cannot run in
> the sandbox … mark it UNVERIFIED in STATUS — do not fold it into the green count."
— `docs/product/backups/CLAUDE.md`
Implication: for a security tool, "N checks ran, N passed" is exactly the wrong headline metric
unless each check is shown to actually discriminate (fail when the thing it's testing for is
present). Fault-injection ("revert the fix, confirm the check fails, restore, confirm it passes")
is the concrete technique used here (`docs/product/agents/fixer.md`).

**Claim: reviewer/auditor read-only status was "honor system," not enforced, before the cards were
converted to real frontmatter subagent definitions — and the official Claude Code behavior for an
unset `tools` field is to grant everything.**
> "'Read-only on the working tree' (reviewer/auditor) and 'applies a bounded set' (fixer) are
> intentions, not constraints. The docs are explicit: 'If you omit tools, you're implicitly
> granting access to all available tools.'"
— `docs/product/agents/CARD-AUDIT-2026-06-21.md`, Gap 2
Implication, directly relevant to a security-framework design: any agent role you intend to be
read-only/write-denied (a reviewer, an auditor) must set `tools`/`disallowedTools` explicitly in
its frontmatter. An omitted field is not a safe default — it's "everything." Similarly for model
pinning: "an omitted `model` inherits the (expensive) session model" — pin it, don't rely on the
caller remembering to pass it.

### Persona rotation / independent verification as a design pattern

**Claim: rotating a distinct skeptical persona per review pass caught real defects that a single
static reviewer prompt would plausibly have missed.**
> "Audit/review subagents get a distinct skeptical framing each time to cover blind spots: 'be
> rigorous, flag aggressively,' 'trust nothing, run it yourself,' name a specific risk for them to
> chase … Re-invoke reviewers until they find no major flaws."
— `docs/product/agents/orchestrator.md`
> "The persona rotation + an independent opus auditor each caught real defects this session (a
> `next()`-isn't-a-404 leak, a vacuous filter stub, latent-RED tests outside the feature path, an
> out-of-sync patch ledger)."
— `docs/product/agents/README.md`
Implication: directly applicable to a security-auditing framework's own review loop — a single
fixed "review this for vulnerabilities" prompt is weaker than rotating named-risk skeptical
personas ("trust nothing," "chase the auth bypass specifically," etc.) across passes.

**Claim: an independent auditor that re-runs the full test suite itself (not the feature-scoped
subset) caught failures the orchestrator's own scoped runs missed twice.**
> "The orchestrator's own test runs were twice green OVER latent failures (schema-integrity hash,
> exporter coverage) because they were scoped to the feature's paths. An independent auditor that
> re-runs the broad suites and reads the code is the backstop."
— `docs/product/agents/auditor.md`
Implication: scoping verification to "the files this task touched" is a real, repeated source of
false-green results; an independent full-suite pass is the documented mitigation, not a redundant
nice-to-have.

### Parallelism and shared state hazards

**Claim: two agents committing to the same working tree race via the shared git index even when
their file sets are disjoint.**
> "Two agents that both COMMIT must not share one working tree — even with disjoint files.
> Disjoint files is NOT enough: the git INDEX/staging area is shared tree state, so two concurrent
> `git commit`s race and one sweeps the other's staged files into its commit (observed 2026-07-02:
> a docs agent's staged spec+plan landed inside a code agent's commit)."
— `docs/product/backups/CLAUDE.md`
Implication: "different files = safe to parallelize" is a false assumption for any git-committing
parallel agents; only isolated worktrees or strict sequencing are safe for writers. Read-only
parallel agents share a tree fine.

**Claim: the `isolation: worktree` Agent-tool parameter can silently fail depending on the
session's working directory relative to the actual repo root.**
> "The Agent `isolation: worktree` param fails here because the session CWD is the PROJECT ROOT
> `/Users/<user>/<project>`, which is NOT a git repo (the repo root is a nested subdirectory). To isolate
> a writer, have the agent create its own worktree with an explicit `git -C
> /Users/<user>/<project>/core worktree add <path> <branch>` … or sequence the writers in the main tree
> instead."
— `docs/product/backups/CLAUDE.md`
Implication: a framework wrapping the Agent tool's `isolation: worktree` needs to verify the CWD
is actually the git root before relying on it — a mismatch fails without necessarily surfacing
loudly.

### Agent card / frontmatter gotchas

- An omitted `tools:` field grants ALL tools — reviewer/auditor roles intended to be read-only
  must set `tools:` or `disallowedTools:` explicitly (`CARD-AUDIT-2026-06-21.md`, Gap 2).
- An omitted `model:` field inherits the (often expensive) session model rather than failing safe
  to a cheap default — pin per-card (`CARD-AUDIT-2026-06-21.md`, Gap 3).
- Auto-delegation depends entirely on a well-written `description:` field, plus the community
  convention of "Use PROACTIVELY" phrasing for agents meant to fire automatically — absent this,
  dispatch stays fully manual (`CARD-AUDIT-2026-06-21.md`, Gap 4).
- Each subagent role in this system used a different status/return vocabulary (implementer: 4
  states, fixer: 2, reviewer: Approved/Needs-fixes, auditor: CLEAN/ISSUES) — flagged as a gap the
  orchestrator has to special-case per role rather than parsing one contract
  (`CARD-AUDIT-2026-06-21.md`, Gap 5). This was a standing recommendation, not confirmed fixed in
  these files.

---

## §3 Things that contradict or complicate my current design

Flagging these adversarially, as requested — some are internal contradictions in the source
material itself, which is useful information in its own right (the operator's own rules drifted).

1. **Direct contradiction on whether a crashed/background agent can be resumed via `SendMessage`.**
   `docs/product/agents/orchestrator.md` (2026-06-21) states flatly: "`SendMessage` to resume a
   crashed agent is NOT available in this harness; re-dispatch fresh after checking what landed on
   disk." But `docs/product/backups/STATUS.md` (2026-07-17, later) states: "Resume any
   API-error-killed agent via SendMessage (context intact). [[build-lead-child-misroute]]" These
   are the same repo, ~a month apart, and directly disagree on a capability. Either the harness
   gained this capability over that month, or one of the two notes is simply wrong. If your
   framework's design depends on whether a killed/crashed agent's context is recoverable via
   `SendMessage`, don't take either claim at face value — verify against the current harness
   behavior directly.

2. **Green verification at every layer still missed a broken product** — this is worth treating as
   a first-class design constraint, not a footnote, for an audit framework. If RedGold's design
   assumes "static analysis + automated checks + a review pass = sufficient audit coverage," the
   `reference-repo` UI-breakage incident is a concrete counterexample: unit tests, integration
   tests, a full security audit, and code review all passed while the real interactive surface was
   broken in six distinct ways, because every gate exercised a mocked or isolated view rather than
   the live end-to-end path. A black-box security audit framework is arguably *better positioned*
   than this to catch that class of gap (since it's supposed to interact with the live system
   already) — but it's worth explicitly confirming the framework's design doesn't quietly regress
   to "review the code/config and trust it" for any surface.

3. **Background dispatch is not a free win — a synchronous consumer can lose the verdict.** If
   RedGold's orchestration pattern uses background agents anywhere a caller needs the result to
   make its next decision (which, for a security audit chain — recon → exploit → verify — is most
   of it), the documented failure ("a background child that finishes after you stop gets its
   verdict misrouted to the main conversation") is directly applicable. Foreground/blocking should
   probably be the default for any step whose output gates the next step.

4. **Layered orchestration (orchestrator → mid-manager → leaf) has a measured, nontrivial token
   cost per layer** (~292k tokens cited as a "birth-cost wall" for a middle-manager agent before it
   could even start doing useful work). If RedGold's architecture plans more than a flat
   orchestrator→specialist-agent structure, this is worth budgeting for explicitly rather than
   assuming hierarchy is cheap.

5. **"Escalate to the strongest model whenever [risk category]" reliably collapses to "always
   escalate" once the risk category is broad.** For `reference-repo` the trigger was "money/authz/
   schema"; for a security-auditing tool the equivalent trigger ("anything security-relevant") is
   close to *all* of the work, by definition. The documented fix — decoupling implementer tier from
   reviewer tier, and reserving double-audits for genuinely high-blast-radius work — is probably
   necessary for RedGold too, or cost will follow the same trajectory this operator hit.

6. **Two committers sharing a tree race even with disjoint files**, and **`isolation: worktree` can
   silently fail** depending on session CWD vs. actual repo root. Both are concrete gotchas worth a
   preflight check if RedGold parallelizes any git-writing agents.

7. **Auto-memory/plugin-memory systems are explicitly called out as untrustworthy for project
   state** ("disposable and may lag or contradict — never treat them as project state"). If
   RedGold leans on a persistent-memory mechanism (its own MEMORY.md-style system, per the user's
   own memory notes) for cross-session audit state, this is a direct warning against trusting that
   memory as ground truth rather than as an advisory index pointing at ground truth (files,
   commits, ledgers).

---

## §4 Files read / files that 404'd

All 21 requested files were fetched successfully via
`gh api "repos/the-operator/reference-repo/contents/<path>?ref=<branch>"`. **No 404s.**

| # | Path | Result |
|---|------|--------|
| 1 | `docs/product/orchestration-audit-2026-07-02.md` | OK, 281 lines |
| 2 | `docs/product/agents/README.md` | OK, 23 lines |
| 3 | `docs/product/agents/CARD-AUDIT-2026-06-21.md` | OK, 169 lines |
| 4 | `docs/product/agents/orchestrator.md` | OK, 46 lines |
| 5 | `docs/product/friction-log.md` | OK, 36 lines |
| 6 | `docs/product/claude-md-changeover.md` | OK, 90 lines |
| 7 | `CLAUDE.md` (repo root) | OK, 287 lines — this is the base project's own generic monorepo `AGENTS.md`/`CLAUDE.md`, NOT the product orchestrator rulebook (that file lives outside the git repo at the project root per the docs; the tracked equivalent is `docs/product/backups/CLAUDE.md`, item 16 below) |
| 8 | `AGENTS.md` (repo root) | OK, 287 lines — identical content to #7 |
| 9 | `CONTEXT-MAP.md` (repo root) | OK, 9 lines — minimal, one context stub (Portal) |
| 10 | `docs/product/agents/auditor.md` | OK, 22 lines |
| 11 | `docs/product/agents/implementer.md` | OK, 27 lines |
| 12 | `docs/product/agents/reviewer.md` | OK, 28 lines |
| 13 | `docs/product/agents/fixer.md` | OK, 20 lines |
| 14 | `docs/product/backups/orchestrator-agent.md` | OK, 158 lines |
| 15 | `docs/product/backups/feature-workflow-SKILL.md` | OK, 161 lines |
| 16 | `docs/product/backups/CLAUDE.md` | OK, 295 lines — the actual orchestrator rulebook (backup copy of the live, un-tracked project-root file) |
| 17 | `docs/product/backups/STATUS.md` | OK, 112 lines — live project-state snapshot, redacted per the repo's own backup convention |
| 18 | `docs/product/blindspot-sweep-2026-07-13.md` | OK, 401 lines — mostly product-specific security findings, excluded from this report per the framework's no-business-data rule; only its methodology (6 parallel read-only investigators across 12 lenses) is orchestration-relevant and noted in passing above |
| 19 | `.github/agents/agentic-workflows.agent.md` | OK, 155 lines — generic `gh-aw` (GitHub Agentic Workflows) dispatcher doc, unrelated to this orchestration system specifically |
| 20 | `.agents/skills/add-api-endpoint/SKILL.md` | OK, 16 lines — frontmatter is minimal: just `name` and `description`, no other fields observed |
| 21 | `docs/product/archive-prototype-superpowers/legacy-misc/legacy-learnings.md` | OK, 136 lines — unrelated legacy/infra bugs from a scrapped earlier prototype, not orchestration-relevant |
