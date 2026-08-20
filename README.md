# RedGold

RedGold is a Claude Code plugin for authorized web and API security auditing of startup products
and small-business compliance work. It scaffolds an engagement with a machine-enforced scope
boundary, runs a staged audit through a capped agent roster, and produces a client report built
only from findings that were independently re-executed on disk — not from the conversation that
produced them.

## Why this exists

Startups and solo founders now ship production software written largely by AI agents. That code
reaches real users — real logins, real payment rails, sometimes real location data — without ever
passing a security reviewer, not because anyone is negligent but because no consultancy can audit
that surface at founder speed or founder budget. RedGold is what I'm building to close that gap:
an agentic auditor with the same speed advantage as the code it's checking, but with its authority
to act kept narrower than its ability to reason, and that narrowing enforced by code rather than by
asking it nicely.

## State of the project

This is R&D, run by one person, not a product with customers. It has never been run end to end
against a live external target. The framework's own test suite is green and its adversarial-review
history is real (see below), but a green suite is evidence the controls behave in tests, not proof
they hold against a live one. The single most consequential gap: off-host egress filtering — the
actual network boundary described below — does not exist yet. Until it does, the honest claim is
**"out-of-scope targets are refused by tooling and logged,"** never **"cannot happen."**

`status.md` is the current, corrected state, including a plain list of what does not work yet. It
is not marketing copy and isn't written as one — read it before trusting any claim made here.

## Why containment is a network problem

An LLM is a text generator; it doesn't execute anything itself, so every command that runs, runs
because software around the model parsed a string it emitted and handed it to an interpreter.
Forking Claude Code to add enforcement means owning that fork forever, and a sandbox tight enough
to be a real boundary breaks the raw-socket, kernel-level tools a scanner needs — so the boundary
has to be the network: even an agent that fully compromises its own VM should still only be able to
send packets where a filter on a different machine permits.

## Layout

Two kinds of repository, kept permanently separate: this one (the plugin — commands, agents,
control scripts, tests, no client data ever) and one throwaway engagement repo per client,
scaffolded by `/rg:new` into `~/engagements/<client>-<yyyy-mm>/`. Within an engagement, an
orchestrator plans and dispatches; worker subagents can't spawn further subagents or see each
other's conversation state, only what's written to shared ledgers. Full detail:
`docs/specs/redgold/README.md` (16-file spec) or `docs/REDGOLD-BRIEFING.md` (single-file
condensation — read this first).

## Getting started

```sh
/plugin marketplace add ~/RedGold
/plugin install rg@redgold
```

or, for a one-session dev run: `claude --plugin-dir ~/RedGold`.

Then `/rg:new` to scaffold an engagement (it refuses without a signed authorization document
already on disk), and `/rg:scope`, `/rg:gate`, `/rg:report`, `/rg:close` from there. Each command
file in `commands/*.md` documents its own flags, refusals, and what it does and doesn't enforce —
that level of detail belongs there, not here.

## Testing

```sh
/usr/bin/python3 -m pytest -q
/usr/bin/python3 scripts/verify_controls.py
```

The second script breaks each control deliberately to prove the tests would notice it failing —
run it before trusting a green first one. Current counts, and what they do and don't prove, are in
`status.md`; they're not repeated here because that copy is exactly what went stale last time.

## Audit history

Eight adversarial review rounds are on record, most of them finding real defects the project's own
tests missed — including two shipped past a green suite in the same day they were found.
`playbooks/_generic/adversarial-framings.md` has the methodology; `status.md` has the full table.
The standing lesson: a framework's tests are written by whoever wrote the code, and inherit its
blind spots exactly.

## Where to look next

- `status.md` — what's true right now, corrected as of the last session
- `CLAUDE.md` — the rules this repo is built under
- `docs/REDGOLD-BRIEFING.md` — the whole design in one file
- `session.md` — the current working log
