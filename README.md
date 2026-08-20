# RedGold

RedGold is a Claude Code plugin for authorized web and API security auditing of startup products
and small-business compliance work. It scaffolds an engagement with a machine-enforced scope
boundary, runs a staged audit through a capped agent roster, and produces a client report built
only from findings that were independently re-executed on disk — not from the conversation that
produced them.

## Why this exists

Two reasons, and the second is the one I actually find interesting.

**There is about to be a lot of demand and not much supply.** The Australian government has agreed
in principle to remove the small business exemption from the Privacy Act. No commencement date has
been legislated yet — so this is a stated direction, not a deadline — but if it lands, a large
population of businesses acquires obligations they have never had to meet, with no in-house
capability to meet them. Meanwhile founders ship production software written largely by AI agents:
real logins, real payment rails, sometimes real location data, reaching real users without ever
passing a security reviewer. Not negligence — no consultancy audits that surface at founder speed
or founder budget.

**And I want to know where the bounds of LLM risk actually are.** An agentic pentester is a
deliberately awkward case: you are handing a text generator offensive tooling and pointing it at
someone else's system. So it is a good place to find out what can genuinely be controlled, what
cannot be, and what that leaves LLMs useful for. The answers so far have been more specific than
"be careful" — a hook cannot see a child process; a control can be perfectly written and still
never fire; the only enforcement that survives a compromised agent is a filter on a machine the
agent has no account on. Those are findings about the technique, not about this project.

So this is as much an AI-safety experiment as a security tool, and it produces one either way. The
design rule underneath it: keep the agent's authority to act narrower than its ability to reason,
and enforce that narrowing in code rather than by asking nicely.

## State of the project

This is R&D, run by one person, not a product with customers. It has never been run end to end
against a live external target. The framework's own test suite is green and its adversarial-review
history is real (see below), but a green suite is evidence the controls behave in tests, not proof
they hold against a live one. The single most consequential gap: off-host egress filtering — the
actual network boundary described below — does not exist yet. Until it does, the honest claim is
**"out-of-scope targets are refused by tooling and logged,"** never **"cannot happen."**

The project keeps an internal record of exactly what is and is not enforced, and it is longer than
this README. It is not published: it names specific unfixed gaps in a framework meant to be pointed
at other people's systems, which is a map worth keeping to ourselves. Treat any capability claim
here as needing that check.

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
run it before trusting a green first one. Counts are deliberately not quoted here: a number copied
into a README is a number that goes stale, which is exactly what happened to the last one.

## Audit history

Eight adversarial review rounds are on record, most of them finding real defects the project's own
tests missed — including two shipped past a green suite in the same day they were found.
`playbooks/_generic/adversarial-framings.md` has the methodology.
The standing lesson: a framework's tests are written by whoever wrote the code, and inherit its
blind spots exactly.

## Where to look next

- `CLAUDE.md` — the rules this repo is built under, and the design judgements behind them
- `docs/REDGOLD-BRIEFING.md` — the whole design in one file
- `session.md` — the current working log
