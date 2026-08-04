---
title: Structured tool interface instead of shell parsing
question: Can the scope guard stop parsing arbitrary Bash, and what would that actually buy?
status: DEFERRED — research direction, not scheduled. Raised 2026-08-04 by external review.
date: 2026-08-04
---

# Structured tool interface instead of shell parsing

## The criticism

An outside review put it directly: the framework's heaviest technical dependency is parsing
arbitrary Bash to decide whether a command is safe, and that is an unbounded problem. The
regression list bears it out — `-XDELETE` with no space, `--request=DELETE`, `psql "host=… port=…"`,
punycode hosts, `$VAR` expansion, `$(…)` substitution, wrapper scripts. Each was found by an
adversary, each took a fix, and there is no reason to think the list is finished.

The proposed alternative: stop emitting shell. Have the agent emit a typed request —

```json
{"tool": "http_request", "host": "api.example.com", "method": "POST", "path": "/users"}
```

— and let the framework construct the underlying call itself. Scope checking becomes a field
comparison. No regexes, no quoting, no injection.

## Assessment

**Directionally right, and worth building. But it is not the answer to "how do we make shell
parsing safe", because there isn't one.**

### What the criticism gets right

- **An AST does not close the gap.** Parsing `curl "$URL"` into a syntax tree tells you a
  substitution exists; it does not tell you what it evaluates to. Upgrading regexes to a real
  parser improves precision and buys nothing on indirection.
- **Deny-on-uncertainty is the correct posture**, and is what the guard already does.
- **The edge-case list has no end**, and every case is found by someone. The ones nobody finds are
  the ones that matter, which is an argument for shrinking the parser's surface even though it
  cannot be eliminated.

### What it misses

1. **A structured tool is not a boundary while `Bash` exists.** "No shell injection" holds only if
   the shell is gone. An agent that finds the typed interface restrictive simply uses Bash instead.
   Adding `http_request` alongside `Bash` improves the common case and moves no boundary.

2. **Removing Bash costs real capability.** nmap, nuclei, sqlmap, testssl, ffuf — none of these fit
   behind a typed HTTP request. `scanner-integration.md` argues for invoking *more* external
   tooling, not less. So the typed interface can own the ordinary-request surface and cannot own
   the tool surface.

3. **The framework already concluded the parser is not the boundary.** §9.3.1 states plainly that
   `scope_guard.py` is defence-in-depth and cannot be a security boundary; §9.9 states the real
   boundary must be egress filtering enforced *outside* the machine the agent controls, because a
   control the agent can reach is not a control. A typed interface does not change either finding.
   It reduces how much work the heuristic layer has to do — which is worth having, and is a
   different claim.

### The argument the criticism did not make, which is the strongest one

The spec currently **denies MCP tool calls** on the grounds that "each server defines its own
schema; there is no canonical target field" (§9.3.1). That reasoning inverts for a server we write
ourselves. If RedGold ships its own MCP server, we define the schema, and the destination arrives
as a typed field rather than something recovered from a string.

**The case the guard currently treats as its worst becomes its best.** That is a stronger argument
for the direction than anything about regex fragility, and it points at a concrete mechanism rather
than a wish.

## The shape this should take

Three layers, not one choice:

| Layer | Mechanism | Handles | Strength |
|---|---|---|---|
| 1 | Typed tool interface (RedGold MCP server) | The common case: ordinary HTTP requests | Unambiguous by construction |
| 2 | Shell, narrowed to vetted wrappers | Real tooling — scanners, probes | Heuristic, deny-on-uncertainty |
| 3 | Off-host egress filtering (§9.9) | Everything, regardless of how it was expressed | The only real boundary |

`rate_probe.sh` is already a layer-2 wrapper: the agent does not hand-roll a burst, it calls a
script that owns the counter, the cap and the stop condition. The typed interface generalises that
pattern to the ordinary case, and the parser's remaining job shrinks to "did this command try to
leave the sanctioned paths".

## Why this is deferred, not scheduled

- It changes the agent-facing contract, so it should be designed against evidence from a real
  engagement rather than a hypothesis. The framework has not yet run against a live target.
- Layer 3 is the boundary and does not exist. Building layer 1 first would improve the story while
  leaving the actual gap open — and would make the framework *sound* safer than it is, which is the
  failure mode this project keeps finding in itself.
- The immediate cost of the parser is bounded and visible: it is a list of regressions with tests
  against them, not an open wound.

**Order, if this is taken up:** off-host egress (§9.10 research) first, because it is the boundary.
Typed interface second, because it shrinks the heuristic layer and makes the MCP denial rule
obsolete in the one case we control. AST-based shell parsing last, or never — it is the option that
costs the most and moves the least.

## Open questions `[VERIFY]`

- Can a plugin-shipped MCP server enforce scope server-side, or does enforcement still have to live
  in the engagement's `settings.json` hooks? Plugin agents cannot declare `mcpServers`, so the
  wiring path needs checking.
- Does denying `Bash` to a worker while granting a typed tool measurably reduce capability on a
  real engagement, or does the tool surface cover more than expected?
- What does the typed interface do about a tool that needs a file-based target list — the case the
  guard denies today?
