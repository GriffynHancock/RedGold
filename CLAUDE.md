# CLAUDE.md — RedGold framework repo

Rules for working **on RedGold itself**. Engagement rules live in each engagement's own CLAUDE.md.

## What this repo is
RedGold: a Claude Code plugin for authorized web/API security auditing of startup products and
small-business compliance. Business thesis: `~/NORTH_STAR.md`.

## Why containment is a network problem
An LLM is a text generator. It does not execute anything. Every command that runs, runs because
conventional software around the model parsed a string it emitted — JSON, XML, a tool-call block —
and handed it to an interpreter. The model's output is only ever a request; the harness is what
turns it into an action.

Three consequences follow:

1. **Modifying the harness is not on the table.** Claude Code is a closed, fast-moving binary.
   Forking it to add enforcement means owning that maintenance forever.
2. **Locking down the container is brittle.** RedGold's tools are scanners — raw sockets, packet
   crafting, kernel-dependent syscalls. A sandbox tight enough to be a boundary breaks the tools;
   one loose enough to run them is not a boundary.
3. **So the boundary is the network.** Even if the agent fully compromises its own VM — finds a
   0-day, gets root, rewrites every hook and deletes every script — it can still only send packets
   to destinations that a filter on a different machine permits.

This is why enforcement effort goes to egress control and not to sandboxing the process.

## The three parts of RedGold
RedGold is three systems with different trust properties, and conflating them is a design error:

1. **Framework development and testing** — this repo. No client data, no targets.
2. **Deployment and scoping** — the setup agent. Runs *outside* containment, on the operator's
   machine, with host access. Takes the signed scope and the scoping questionnaire, resolves
   in-scope hosts, generates the network ruleset, provisions the contained environment, hands over.
3. **Auditing and pentesting** — the high-risk agents. Run *inside* containment. No host access and
   no principal on the filtering machine. Everything they produce crosses a boundary to reach the
   operator, and that outbound direction carries prompt-injection payloads, so it is reviewed, not
   trusted.

## Read first
- `docs/wiki/redgold/facts.md` — **the findings that cost a session to learn, distilled to one
  page.** Read before opening any research document; there are 15,000+ lines of them and the part
  that matters is short. `docs/wiki/redgold/open-threads.md` says what is next.
- `docs/REDGOLD-BRIEFING.md` — single-file condensation. Read this before the spec.
- `docs/specs/redgold/README.md` — index of the 16-file spec. Load only the file whose question
  matches yours.
- `status.md` — current state. `session.md` — last handoff.

## Authorisation state — check `status.md` for the current table
No target is authorised by default. As of the last update: **prior-engagement live = NOT authorised**
(artifacts only); **prior-engagement target = gated** pending snapshot. `status.md` is
authoritative; this line is a reminder that the answer is never "probably fine".

## Hard rules
1. **Never fabricate a legal fact.** Everything in §21 (Subsystem F) is marked `[VERIFY]` and
   unconfirmed. Nothing marked `[VERIFY]` reaches a client or a marketing claim.
2. **Never fabricate a benchmark number.** Cite the primary source or omit it. Two audits caught
   citation errors; do not add more.
3. **Client data never enters this repo.** Engagements live in `~/engagements/<client>-<yyyy-mm>/`.
3a. **This repo is PUBLIC** (`github.com/GriffynHancock/RedGold`). Neither client nor *operator*
   identifiers reach it: no target hostname, tailnet, IP, container or database name, target repo
   URL, absolute home path, or prospective client name. Past engagements are "the prior engagement"
   (`ENGAGEMENT-A` blackbox, `ENGAGEMENT-B` whitebox). An unremediated vulnerability in our own
   systems is written as methodology, never as a finding against an identifiable host; the
   unredacted version stays in the engagement folder. Anonymise the *identifiers*, not the
   *findings* — the technical substance is what makes the analysis worth publishing.
4. **No target is touched without a signed scope.** Authorized work only.
5. **Calibrated honesty applies to us too** — including numbers that flatter us (P9).
6. **Assume every agent is an insider threat.** Not because the model is malicious, but because two
   ordinary things produce identical behaviour: prompt injection from a target that expects to be
   scanned, and an agent going off the rails on its own. Both are already evidenced here — an agent
   rewrote its own text to get a write past `scope_guard.py` (`docs/research/prior-engagement-autopsy.md`).
   Design for the case where the agent's cooperation is not merely absent but adversarial.

## Working preferences
- One or two research agents at a time, one target each, exact paths supplied. Broad orienting pass
  first, then narrow passes against what it found.
- Use APIs/curl for mechanical retrieval, not agents (`api.github.com/repos/O/R/git/trees/main?recursive=1`).
- Split documents before they grow. Frontmatter + index on everything.
- Opus for reasoning/synthesis/sensitive analysis. Sonnet for legwork.
- Be a thinker, not a tinkerer. Planning sessions are a good outcome.

## Design judgements
Learned the hard way. Stated generally on purpose — each was discovered in one instance and the
instance is not the lesson.

1. **Do not design from n=1.** A single target teaches you its own shape, not the general one. The
   spec once centred a Supabase playbook because the first audit used Supabase; the severity
   vocabulary was fitted to one engagement's eleven findings. Both look like knowledge and are
   really overfitting. When a design's evidence is one example, say so in the design, and prefer a
   mechanism that degrades gracefully on the second example over one tuned to the first.
2. **Site a control later than the earliest moment its input can exist.** Two tests, not one: *name
   a healthy state at which this fires* catches a gate placed too early (it fires on everything);
   *name any state at which this fires* catches one placed before its input exists (it fires on
   nothing). A gate that never fires is worse than a wrong one, because it reads as coverage.
3. **Distinguish a refusal from a transform.** A refusal that fires on healthy input gets disabled.
   A transform that applies to every record may be entirely correct. Do not apply the disabled-gate
   test to something that blocks no work.
4. **A control nobody is forced to run is not a control.** If it depends on being remembered, it
   will be forgotten. Where no mechanism can bind it, say so plainly and record the residual rather
   than describing it as enforced.
5. **Check the code, not the document describing the code.** Specs drift, and a document repeating
   a wrong claim is how a defect survives review. Several controls here were described as built
   while the file they named did not exist.
6. **Implementation finds what review misses.** Nearly every real defect found on 2026-08-20 came
   from an agent trying to build something and discovering it could not — not from anyone reading
   for errors. Keep implementation close behind specification; a spec that runs far ahead of code
   accumulates confident mistakes.
7. **Test count is not discrimination.** Every new control needs a matching injected fault in
   `scripts/verify_controls.py`, and a mutation that nothing catches means the control is untested
   whatever the number says. Never tune a fault until it passes.
8. **Verify remote and external state before asserting it.** Comparing against a stale
   remote-tracking ref, or a tool's flag as remembered rather than read, produces confident wrong
   answers. `nuclei -td <dir>` looks like pinning and silently is not.

## Current phase
Spec complete for Subsystems A–F. **Next: MVP implementation** — see `status.md`.
