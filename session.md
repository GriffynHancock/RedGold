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
406 tests (18 skipped), 21/21 fault injection, both exit 0. Pushed private.

**Four adversarial audit rounds found 21 real defects the self-written suite missed** — including
one that put an unverified finding into a client report, a shell injection in the scaffolder, and
two introduced *while fixing the previous round*. Framings and their yields:
`playbooks/_generic/adversarial-framings.md`. Treat that ratio as the standing estimate of what
self-review catches on its own.

**The framework has never run against a live target.** Everything green is evidence the controls
behave in tests, which is not the same claim.

---

## Session 005 — not started

**Objective: the opensesh engagement.** See `status.md` — the target is **not yet authorised in the
framework's terms**. The operator has stated approval exists; the scope facts, and the
authorization document `/rg:new` requires on disk, do not. Ask for them first.

Deferred research, in the order it should be taken up if it is:
1. `docs/specs/redgold/07-enforcement.md` §9.10 — off-host egress containment. This is the only
   real boundary and it does not exist.
2. `docs/research/structured-tool-interface.md` — typed tool interface instead of shell parsing.
   Raised by outside review 2026-08-04; shrinks the heuristic layer, does not replace the boundary.
3. `docs/research/scanner-integration.md` — compose scan profiles from pinned open-source
   components plus our own checks. Deliberately deferred until a real engagement shows which gaps
   actually bite.
