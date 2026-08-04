---
title: Playbooks, entry point, and institutional memory
question: How does knowledge accumulate so the same mistake is never made twice?
sections: [11, 12, 13]
spec: RedGold design
status: draft
date: 2026-08-03
---

## 11. The playbook library — the skill factory

The differentiator. Not a flat "what worked" list, but knowledge indexed by *what you were facing*:
"Supabase around 2.108 behind Vercel" retrieves the accumulated playbook for exactly that stack.

### 11.1 Why skills are the right container

Claude Code loads skills progressively: only `name` and `description` cost tokens at session start;
the body loads on invocation and persists for the session; **bundled reference files and check
scripts cost zero tokens until explicitly read.** A large library is therefore free until used.

### 11.2 Dispatch, not a flat list

Anthropic's documentation states the `description` field lets Claude choose among "potentially 100+
available Skills," so there is **no documented hard ceiling** — the earlier "~20 entries" figure was
practitioner folklore and has been removed. The argument for dispatch does not depend on it:
selection reliability at library scale is simply unproven, and dispatch removes the question
entirely while keeping per-session cost flat. So playbooks
are **dispatched**: a single `playbook-dispatch` skill reads `playbooks/index.yaml`, matches the
fingerprint produced by `rg-surface`, and loads only the matching playbooks.

The library can grow to hundreds of entries while per-session context cost stays flat. This is the
mechanism by which **capability grows faster than complexity**.

```yaml
# playbooks/index.yaml
- id: backends/supabase
  fingerprint:
    any_of:
      - {signal: http_header, key: "server", match: "supabase"}
      - {signal: js_bundle,   match: "supabase.co"}
      - {signal: dns_cname,   match: "*.supabase.co"}
  specializes: _generic/backend-authz
  versions: ["<2.100", "2.100-2.110", ">2.110"]
```

### 11.3 Playbook structure

```
playbooks/backends/supabase/
  PLAYBOOK.md            # seed hypotheses, secure defaults, check index
  checks/*.yaml          # individual checks mapped to ASVS/WSTG/API-Top-10
  versions/2.100-2.110.md  # what has been tried against this version band, and what happened
  remediation/*.md       # fix snippets, cost-tiered
  handoff/               # guardrail-pack fragment for subsystem E
  evals/evals.json       # trigger evals (§11.6)
```

Every playbook holds:

- **Fingerprint signature** — how to detect this technology
- **Seed hypotheses** — the Naptime variant-analysis framing (P3). Not "look for bugs" but "in this
  stack, X is commonly wrong; go check X." This is where the 20x lives.
- **Known secure defaults** — so a default is never reported as a flaw. The prior engagement
  correctly credited Supabase RLS for blocking 9/9 privilege-escalation attempts; that judgement
  must be encoded, not re-derived.
- **Checks** mapped to a recognised standard so remediations cite a bar the client can verify
- **Remediation snippets** with cost tiers (`$` config, `$$` patch, `$$$` re-architecture)
- **Handoff fragment** feeding the client guardrail pack

### 11.4 The generic tier

`_generic/` holds technology-independent methodology that specific playbooks **specialize**:
auth-model mapping, authz-boundary probing, IDOR/BOLA, BFLA, rate limiting, secrets handling,
transport security.

This fixes the flaw seen in the prior engagement where `supabase-audit` was simultaneously the flagship skill and the
*only* implementation of backend auditing — a design that silently assumed every future target
would be Supabase. Supabase becomes one specialization among Firebase, generic REST, GraphQL and
whatever comes next.

### 11.5 Startup default checks

Because the failure modes of this client segment are documented and repeatable (§1.2), these run by
default on every engagement rather than being optional extras:

RLS / security-rules enabled on any discovered Supabase or Firebase project · `anon` versus
`service_role` key differentiation · public storage bucket check · wildcard CORS on authenticated
routes · exposed source maps · secret scanning across any accessible repo (gitleaks for breadth,
trufflehog to verify liveness) · **Vercel/Netlify preview deployment discoverability** — public by
default unless Deployment Protection is explicitly enabled, and routinely wired to production
databases · no-auth serverless endpoints · admin routes shipped in the client bundle · committed
`.env`.

### 11.6 Evals

Every playbook skill ships with `evals/evals.json` containing at least three **should-trigger** and
three **should-not-trigger** prompts, following Anthropic's own skill-authoring methodology: build
evals first, baseline without the skill, then write the minimum instructions that close the gap.
This is the quality control that stops the library degrading into a pile of never-invoked files.

### 11.7 The harvest loop

`/rg:harvest` runs at engagement close. It diffs what was learned against the existing playbooks and
promotes lessons into the correct version-keyed file, **redacted**, with a pointer back to the
engagement. Because the framework and engagement repos are separate (§4), redaction is a deliberate
step rather than an accident waiting to happen.

Promotion targets are chosen by the triage rule in §13.

---

## 12. `using-redgold` — the entry-point skill

Modelled on `superpowers:using-superpowers`. Loaded at the start of any engagement session, it
establishes how to operate before anything else happens:

1. **Refuse to act without a scope.** If `scope.yaml` is absent or its authorization window has
   expired, stop and tell the operator. No exceptions.
2. **Announce the mode and ceiling** at the top of every session, read from `scope.yaml`.
3. **Read the previous handoff block** from the archived session log.
4. **Route to the right agent.** A decision table mapping operator intent → agent → phase.
5. **State the file contract** — which of the three files a given piece of information belongs in.
6. **State the evidence rule** — no claim without a resolvable evidence pointer; PROVEN requires
   verification.
7. **State the escalation rule** — what to do when a mistake happens (§13).

It is deliberately short and deliberately loud. Its job is to make the rules the first thing in
context, not to teach methodology — that lives in playbooks.

---

## 13. Institutional memory: never make the same mistake twice

A triage rule, applied at the moment a mistake is noticed. It is written into `using-redgold` and
into every engagement's `CLAUDE.md`.

| The mistake is… | Fix belongs in | Guarantee |
|---|---|---|
| A checkable precondition on a tool call (wrong host, destructive command, missing approval, unbounded loop) | **A hook** | Mechanical. Cannot be forgotten. |
| A recurring judgement or context gap | A `CLAUDE.md` / `.claude/rules/` entry — **promoted to a hook on second recurrence** | Probabilistic |
| A multi-step procedure executed incompletely | A **skill with an explicit checklist** the model copies and ticks off | Probabilistic, measurably better than prose |
| Output-shape drift (malformed finding, missing field) | A **validation script** wired to `SubagentStop` | Mechanical |
| Target-specific tribal knowledge | Agent `memory: project` | Advisory only |
| Cross-engagement technology knowledge | **A playbook entry**, via `/rg:harvest` | Advisory, but retrieved by fingerprint |

The rule that matters: **the second occurrence of any mistake escalates it one level toward
mechanical enforcement.** A repeated mistake is a missing hook, not a careless agent.

Path-scoped `.claude/rules/` files (with `paths:` frontmatter) hold methodology that should load
only when working in a matching area — for example GraphQL rules that activate only when handling
GraphQL artifacts — keeping `CLAUDE.md` under its line cap.

---
