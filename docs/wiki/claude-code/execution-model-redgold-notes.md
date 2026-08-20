---
title: What Claude Code's execution model means for RedGold's controls
wiki_id: redgold-execution-model-notes
question: Given that hooks fire on tool calls and not on process creation, which RedGold controls still hold, and which claims must change?
subject: Claude Code / RedGold
status: partial
last_verified: 2026-08-20
verified_against: |
  claude-code/execution-model.md (same session, 2026-08-20);
  scripts/scope_guard.py as committed at c0a20bd, executed read-only 2026-08-20;
  docs/specs/rg2-containment.md §5, §9.3.1 as on disk 2026-08-20.
recheck_trigger: >
  before any client-facing wording about what RedGold's tooling prevents; before enabling the Bash
  sandbox; and when RG-2's gateway (layer 7) first produces real egress rows, since half the
  conclusions here are about what the workload-side ledger cannot see.
sources:
  - url: docs/specs/rg2-containment.md
    kind: primary
  - url: scripts/scope_guard.py
    kind: primary
related:
  - claude-code-execution-model
  - claude-code-hooks
---

# What the execution model means for RedGold's controls

Read [execution-model.md](execution-model.md) first. This page is only the consequences.

## 1. The one thing to carry away

RedGold's enforcement layer is `PreToolUse`/`PostToolUse` hooks on `Bash`. Those hooks see **the
request an LLM emitted**. They do not see processes. Every process below the first one — `bash -c`,
a Python script, a daemon, an MCP server, a hook's own command — comes into existence without any
`Bash` `PreToolUse` event.

This is not a bug to fix at the hook layer. It is `CLAUDE.md`'s "why containment is a network
problem", restated as an observed mechanism rather than an argument: the harness turns *strings*
into actions, so a control on strings binds exactly one action deep.

## 2. `scope_guard.py` — the concession in §9.3.1 is bigger than the example given

The module docstring concedes the write-then-execute case. Executed against the current file
(read-only, 2026-08-20), the concession is **broader** than the example implies:

- `echo 'curl …' > /tmp/a.sh && bash /tmp/a.sh` → **denied**. The spec's own example is caught,
  because `curl` is still in the string.
- `bash /tmp/a.sh` on its own → **allowed, and no ledger row written**. Same for `python3 /tmp/a.py`,
  `./a.out`, `make deploy`, `npm run start`.

The mechanism is `touches_network`: a token match against `NETWORK_TOOLS` plus a URL regex. A
command that merely *starts a program* trips neither, so `extract_hosts` returns an empty set and
`build_activity_row` returns `None`. **Splitting the write and the execution across two tool calls
defeats the guard where the single-command form does not.**

That is correct behaviour for a control at this layer, and the module already says so in the right
words — "defence-in-depth against sloppy scope drift. It is NOT a security boundary." Nothing here
argues for widening the parser. Denying every invocation of `make` would produce exactly design
judgement 2's disabled gate. **The correct response is that the guard's honest claim already says
this and must keep saying it.**

One wording refinement is warranted. The current claim reads:

> "The tooling mechanically refuses out-of-scope targets in the ordinary case, and refuses outright
> when it cannot determine what it is about to touch."

"Cannot determine what it is about to touch" implies the guard *knows* when it is blind. In the
`make deploy` case it does not: it classifies the call as having no network destination at all and
returns silently. Suggested amendment, offered rather than applied (specs and research documents are
out of this session's remit):

> "…and refuses outright when it can see that a command reaches the network but cannot determine
> where. It does not see, and makes no claim about, what a program started by a command goes on to
> do."

## 3. The ledger records the agent's requests, not the machine's traffic

RG-2 step 1 made `scope_guard.py` write a decision row per call. **A child process makes network
calls without producing a row.** The `bash /tmp/a.sh` case above is not merely unblocked — it is
*unlogged*, because `build_activity_row` returns `None` for an allow with no parsed target.

So `ledger/activity.jsonl` is a record of **what the agent asked the harness for**, and `rg-gw`'s
NFLOG→JSONL is the record of **what the machine actually sent**. They are different objects and the
difference is not noise:

| Event | Appears in `ledger/activity.jsonl`? | Appears in the gateway log? |
|---|---|---|
| `curl https://in-scope/` | Yes, `scope.allow` | Yes |
| `curl https://out-of-scope/` | Yes, `scope.deny` | No — never sent |
| `bash /tmp/a.sh`, script curls anywhere | **No row at all** | Yes |
| MCP server's own HTTP traffic | No | Yes |
| A detached daemon started an hour ago | No | Yes |

Rows 3–5 are what `rg2-containment.md` §5 means by a `corr_id` gap being "unattributed traffic". The
join is not a redundancy check between two logs of the same thing; **it is the only way the
workload-side ledger's blind spots become visible at all.**

`rg2-containment.md` already sites the authoritative log on the gateway and already states the
workload-side ledger is "forgeable by an escaped workload (§5.6)". This page adds the weaker,
more common case: the ledger is incomplete *without any escape and without any dishonesty* — an
agent doing ordinary work through a build script produces traffic the ledger never sees. A reader
must not mistake the workload-side ledger for a complete record, and no client-facing document
should describe it as one.

## 4. A control that is not installed

Observed 2026-08-20: **there is no `hooks/hooks.json` and no `hooks/` directory in this repository**,
`.claude/settings.json` and `.claude/settings.local.json` do not exist, and `~/.claude/settings.json`
declares no hooks. `scripts/scope_guard.py` is referenced in twenty-odd documents and is registered
as a hook in none of them.

Every conclusion on this page about what `scope_guard.py` allows or denies is therefore about **what
it would decide if it ran**. Right now it does not run on any tool call. This is design judgement 4
("a control nobody is forced to run is not a control") and design judgement 5 ("check the code, not
the document describing the code") arriving together, and it should be checked against `status.md`
rather than assumed to be a discovery — it may already be recorded as a known state of the MVP
build. Recording it here because a future agent reading this page must not infer from "the guard
denies X" that anything is currently being denied.

## 5. The split-agent credential requirement is not met by file permissions

RG-2's design has the inside agent not holding the operator's credentials. Observed: a direct child,
a grandchild, and a `setsid nohup` detached process all read `~/.claude/.credentials.json` (mode
`600`) and recovered the OAuth `accessToken` *and* `refreshToken` key structure. There is one uid;
Unix permissions cannot separate the agent from the harness's own credentials.

Consequences for the RG-2 build, in the order they matter:

1. **The separation has to be a machine or a uid, not a setting.** This is already RG-2's shape —
   the inside agent has "no principal on the filtering machine". This observation is the concrete
   reason that is the right shape.
2. `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB` scrubs *environment*; the token here is in a *file*. It is
   worth setting and it does not solve this.
3. `sandbox.credentials.files` with `"mode": "deny"` does cover the file, but only for sandboxed Bash
   commands, and only if the sandbox is enabled — it is not, on this machine.
4. `SSH_AUTH_SOCK` is inherited by every spawned process. Empty on this machine today. If the
   operator's agent ever holds a key while a contained session runs, any child process can
   authenticate as the operator to every host that key opens, and no file was read to do it.

## 6. Two harness features that deserve a decision before RG-2 provisioning

Neither is a defect; both are places where the harness can widen what runs, and RedGold should decide
deliberately rather than inherit the default.

- **`dangerouslyDisableSandbox`.** If the sandbox is enabled, the *model* may retry a
  sandbox-blocked command with the sandbox off. Setting `"allowUnsandboxedCommands": false` makes the
  parameter "completely ignored" `[SOURCE: cc-sandboxing]`. Given hard rule 6 — assume every agent is
  an insider threat — a model-actuated sandbox-off switch is exactly the mechanism the Anjali autopsy
  describes an agent using. **Strict sandbox mode should be the RedGold default.**
- **The shell snapshot.** Sourced from disk at the top of every Bash call, observed mode `664`,
  writable by any process the agent starts. Anything appended runs before the command a hook
  inspected, and a function defined there can shadow `curl` or `python3`. `[INFERRED]` — the sourcing
  and the mode were observed; writing to the file was not tested. If it holds, the provisioning
  template should make the snapshot directory unwritable by the workload uid, and
  `containment.selftest` should assert it — it is a cheap check and it closes a path no hook can see.

## 7. What does not change

- **Subagent hooks fire.** The spec's claim is confirmed verbatim, with `agent_id`/`agent_type` on
  stdin. Per-agent policy in a `PreToolUse` hook is buildable.
- **Skill `` !`cmd` `` injection runs through the Bash tool** and a deny rule aborts the invocation.
  That path is covered.
- **MCP tool calls raise `PreToolUse`** under `mcp__<server>__<tool>`. `scope_guard.py` already
  denies these as undeterminable, which remains right: MCP *server* processes are unhooked and
  session-lived, so the tool call is the only point of leverage that exists.
- **The architecture was already correct.** Nothing here argues for a new hook. It argues that the
  reason `CLAUDE.md` gives for putting enforcement on the network — rather than in the harness or the
  container — is now an observed fact about this machine, not only a design position.

## Related

- [Claude Code execution model](execution-model.md) — the evidence behind every claim on this page.
- [Claude Code hooks reference](hooks.md) · [RedGold hook facts](hooks-redgold-notes.md).
