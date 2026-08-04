# CLAUDE.md — RedGold framework repo

Rules for working **on RedGold itself**. Engagement rules live in each engagement's own CLAUDE.md.

## What this repo is
RedGold: a Claude Code plugin for authorized web/API security auditing of startup products and
small-business compliance. Business thesis: `/home/hiranya/NORTH_STAR.md`.

## Read first
- `docs/REDGOLD-BRIEFING.md` — single-file condensation. Read this before the spec.
- `docs/specs/redgold/README.md` — index of the 16-file spec. Load only the file whose question
  matches yours.
- `status.md` — current state. `session.md` — last handoff.

## Authorisation state — check `status.md` for the current table
No target is authorised by default. As of the last update: **prior-engagement live = NOT authorised**
(artifacts only); **Anjali = gated** pending snapshot. `status.md` is authoritative; this line is a
reminder that the answer is never "probably fine".

## Hard rules
1. **Never fabricate a legal fact.** Everything in §21 (Subsystem F) is marked `[VERIFY]` and
   unconfirmed. Nothing marked `[VERIFY]` reaches a client or a marketing claim.
2. **Never fabricate a benchmark number.** Cite the primary source or omit it. Two audits caught
   citation errors; do not add more.
3. **Client data never enters this repo.** Engagements live in `~/engagements/<client>-<yyyy-mm>/`.
4. **No target is touched without a signed scope.** Authorized work only.
5. **Calibrated honesty applies to us too** — including numbers that flatter us (P9).

## Working preferences
- One or two research agents at a time, one target each, exact paths supplied. Broad orienting pass
  first, then narrow passes against what it found.
- Use APIs/curl for mechanical retrieval, not agents (`api.github.com/repos/O/R/git/trees/main?recursive=1`).
- Split documents before they grow. Frontmatter + index on everything.
- Opus for reasoning/synthesis/sensitive analysis. Sonnet for legwork.
- Be a thinker, not a tinkerer. Planning sessions are a good outcome.

## Current phase
Spec complete for Subsystems A–F. **Next: MVP implementation** — see `status.md`.
