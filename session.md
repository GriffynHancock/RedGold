# session.md

Append-only working log. Current sessions only — archive to `docs/sessions/` when the file grows
past roughly 150 lines, and keep this one short.

**`status.md` is authoritative for phase and authorisation state and overrides anything here.**

Archived: `docs/sessions/2026-08-03-04-sessions-001-004.md` — design through v1 build complete
(sessions 001–004, 505 lines). Read it only if you need the reasoning behind a specific decision;
the conclusions that still matter are in `status.md`, `CLAUDE.md`, and the spec.

---

## Where v1 landed (2026-08-04)

Build order §17.2 steps 1–9 complete, plus `/rg:scope`, `/rg:gate` and `/rg:report`.
406 tests (18 skipped), 21/21 fault injection, both exit 0. Pushed to
`github.com/GriffynHancock/RedGold`, which is a **public** repository — an earlier note here said
"pushed private" and was wrong. Everything committed to this repo is world-readable; target
identifiers and engagement detail must be anonymised before they land here.

**Four adversarial audit rounds found 21 real defects the self-written suite missed** — including
one that put an unverified finding into a client report, a shell injection in the scaffolder, and
two introduced *while fixing the previous round*. Framings and their yields:
`playbooks/_generic/adversarial-framings.md`. Treat that ratio as the standing estimate of what
self-review catches on its own.

**The framework has never run against a live target.** Everything green is evidence the controls
behave in tests, which is not the same claim.

---

## Session 005 — 2026-08-20. Ran, and did not do what this heading said.

**This section said "not started" until 2026-08-20 and was wrong for the length of a very large
day.** The engagement did not happen. Roughly 30 agents ran instead.

**What shipped as code.** RG-1 Releases 1 and 2 and RG-2 step 1 (`scope_guard` decision logging),
all in `acbc165`. Suite 406 → 605 (18 skipped, 141 subtests); fault injection 21 → 60. Both green
at `de109fa`.

**What shipped as prose.** Five sub-project specs (RG-1 finding integrity, RG-2 containment, RG-2
rate control, RG-3 test libraries, RG-4 scoping questionnaire), an internal wiki, and ~11 research
documents. The tree is now ~24,100 lines of specs-plus-research against 7,576 lines of Python.

**What the day's four adversarial rounds found** — the full table is in `status.md`:

- **Claim audit** (`session-audit-2026-08-20.md`): 23 claims, 2 contradicted. One of them overturned
  a claim in a source document — `rg-verify` "cannot write even if told to" is false, because
  `Bash` is a write path.
- **RG-1 code review** (`rg1-code-review-2026-08-20.md`): **12 defects, 2 critical**, in code that
  had just shipped green at 540 tests and 33/33 faults. S1–S11 fixed; **S12 not** — it is the
  missing `phase` producer, filed low-and-unproven and since proven.
- **Test-suite mutation study** (`test-suite-review-2026-08-20.md`): **68%** fine-grained mutation
  score, 40 survivors, clustered on band boundaries and fail-closed defaults.
- **Architecture walk** (`docs/wiki/architecture/current.md`): **19 wired controls that cannot fire**,
  13 of them new. Nine are now disclaimed in `status.md`. The one that matters most is
  `REPORT_STALE`, which reads a `created` field only `baseline_scan.py` writes — so the first
  agent-authored finding permanently blocks `/rg:close`.

**The lesson the day cost most to learn.** Every round after the first found defects the previous
round's fixes had introduced or failed to generalise, because **each fix was verified against the
path that produced the bug report and against no other path** (architecture §6.2). The absence of a
dataflow contract — nothing states which component writes which field at which lifecycle point — is
the single finding underneath all nineteen.

**And the process cost.** `docs/research/strategic-review.md` §4 item 6 records that a fan-out of
~30 agents produced four composition disagreements between sub-projects, none detectable by any
control in the repo, and that CLAUDE.md's own working preference already says "one or two research
agents at a time". `status.md` went stale twice in the same day and was corrected twice; a currency
audit (`docs/research/currency-audit-2026-08-20.md`) then ran over the whole tree and corrected it a
third time. **Budget a reconciliation pass as part of any fan-out of that size, not after it.**

## Session 006 — not started

**Objective: still the next engagement, and it is still blocked on the same fact it was blocked on
16 days ago.** See `status.md` — no target is authorised in the framework's terms. The operator has
stated approval exists; the scope facts, and the authorization document `/rg:new` requires on disk,
do not. Ask for them first.

**The competing proposal, unresolved.** `strategic-review.md` §5 argues the one thing to do is run
the briefing §18 acceptance test — a complete engagement end to end against a target *the operator
owns* — which needs no client, no third-party authorisation, no containment build and no new code,
and which would unblock the queue below today. That has never been run. No decision is recorded
either way; both readings are live.

Deferred research, in the order it should be taken up if it is:
1. `docs/specs/redgold/07-enforcement.md` §9.10 — off-host egress containment. This is the only
   real boundary and it does not exist. `strategic-review.md` §4 item 2 dissents: build RG-2 §2.1,
   §2.2, §2.5 and §4 (hours, not days) and stop above that until a client's scope requires it.
2. `docs/research/structured-tool-interface.md` — typed tool interface instead of shell parsing.
   Raised by outside review 2026-08-04; shrinks the heuristic layer, does not replace the boundary.
3. `docs/research/scanner-integration.md` — compose scan profiles from pinned open-source
   components plus our own checks. Deliberately deferred until a real engagement shows which gaps
   actually bite. **Superseded in detail by `docs/specs/rg3-test-libraries.md`**, which corrects
   that document's `-td` pinning error; read RG-3 §1.5 first.
