---
title: Claude Code hooks reference
wiki_id: claude-code-hooks
question: For a given hook event, what triggers it, how often does it fire, does exit code 2 block anything, and what does the event receive/return?
subject: Claude Code
status: partial
last_verified: 2026-08-20
verified_against: https://code.claude.com/docs/en/hooks, fetched 2026-08-20; https://code.claude.com/docs/en/plugins-reference, fetched 2026-08-20
recheck_trigger: before relying on this page to design a new enforcement hook, or if code.claude.com/docs/en/hooks 404s or its event list/section headers change
sources:
  - url: https://code.claude.com/docs/en/hooks
    kind: primary
  - url: https://code.claude.com/docs/en/plugins-reference
    kind: primary
related:
  - redgold-hooks-facts
---

# Claude Code hooks reference

Claude Code exposes 31 hook events `[SOURCE: cc-hooks-docs]`. Every one is scoped to a turn, a tool
call, a tool batch, a subagent, a task, a worktree, or a session — **none is scoped to anything
larger than a session** (see `redgold-hooks-facts.md` for why that matters for RedGold
specifically). Exit code 2 blocks the triggering action only on events documented below as
"blocks"; on every other event, exit 2 either shows stderr to the user/model without stopping
anything, or is ignored outright. Getting an event's row wrong in this table is exactly the mistake
that cost effort in the 2026-08-20 session (`docs/specs/rg1-finding-integrity.md` §9.1a).

**Caveat on this page's sourcing method:** the event-by-event detail below was retrieved by fetching
`code.claude.com/docs/en/hooks` and having it summarized/quoted back, not by a human reading the
raw HTML. Table cells are `[SOURCE]`-tagged because the URL and date are real and the content
matches multiple independent fetches, but if a specific row is load-bearing for an irreversible
design decision, re-fetch the doc and check the exact wording yourself before relying on it — flag
any discrepancy found by adding a `[VERIFY]` note inline and downgrading this page's `status`.

## 1. Quick-reference table — every event

| Event | Fires when | Cadence | Blocks on exit 2? | Exit-2 / non-blocking effect |
|---|---|---|---|---|
| `ConfigChange` | A config file changes mid-session | Per change | Yes | Blocks the config change from taking effect (except `policy_settings`) `[SOURCE: cc-hooks-docs]` |
| `CwdChanged` | Working directory changes (e.g. `cd`) | Per change | No | Shows stderr to user only `[SOURCE: cc-hooks-docs]` |
| `DirectoryAdded` | A dir is added mid-session (`/add-dir`, SDK `register_repo_root`) | Per add | No | Stderr to debug log; directory is already added `[SOURCE: cc-hooks-docs]` |
| `Elicitation` | An MCP server requests user input mid-tool-call | Per elicitation | Yes | Denies the elicitation `[SOURCE: cc-hooks-docs]` |
| `ElicitationResult` | After user responds to an elicitation, before it's sent back | Per elicitation | Yes | Blocks the response (action becomes decline) `[SOURCE: cc-hooks-docs]` |
| `FileChanged` | A watched file changes on disk | Per change | No | Shows stderr to user only `[SOURCE: cc-hooks-docs]` |
| `InstructionsLoaded` | A CLAUDE.md / `.claude/rules/*.md` loads into context | Per load (session start + lazy loads) | No | Exit code is ignored `[SOURCE: cc-hooks-docs]` |
| `MessageDisplay` | While assistant text streams to the display | Per message | No | Original text is displayed regardless `[SOURCE: cc-hooks-docs]` |
| `Notification` | Claude Code sends any notification | Per notification | No | Output/exit ignored except `terminalSequence` `[SOURCE: cc-hooks-docs]` |
| `PermissionDenied` | Auto mode denies a tool call | Per denial | No | Exit code/stderr ignored (denial already happened); JSON `hookSpecificOutput.retry: true` can offer the model a retry, ignored for no-verdict denials `[SOURCE: cc-hooks-docs]` |
| `PermissionRequest` | A tool call needs a permission decision | Per request | **No — exit 2 not honored** | Deny via the JSON `hookSpecificOutput.decision` field (`allow`/`deny`/`escalate`), not exit code `[SOURCE: cc-hooks-docs]` |
| `PostCompact` | After context compaction completes | Per compaction | No | Shows stderr to user only `[SOURCE: cc-hooks-docs]` |
| `PostToolBatch` | After a full parallel tool-call batch resolves, before next model call | Per batch | Yes | Stops the agentic loop before the next model call `[SOURCE: cc-hooks-docs]` |
| `PostToolUse` | After a tool call succeeds | Per tool call | No | Shows stderr to Claude; the tool already ran `[SOURCE: cc-hooks-docs]` |
| `PostToolUseFailure` | After a tool call fails | Per tool call | No | Shows stderr to Claude; the tool already failed `[SOURCE: cc-hooks-docs]` |
| `PreCompact` | Before context compaction | Per compaction | Yes | Blocks compaction `[SOURCE: cc-hooks-docs]` |
| `PreToolUse` | Before a tool call executes (skips `EndConversation`) | Per tool call | Yes | Blocks the tool call `[SOURCE: cc-hooks-docs]` |
| `SessionEnd` | A session terminates | Once per session | **No — cannot block at all** | Shows stderr to user only; shares a 1.5s budget across all `SessionEnd` hooks `[SOURCE: cc-hooks-docs]` |
| `SessionStart` | A session begins or resumes | Once per session | No | Shows stderr to user only; stdout is added as context Claude can see `[SOURCE: cc-hooks-docs]` |
| `Setup` | Claude Code starts with `--init-only`, or `--init`/`--maintenance` in `-p` mode | Once per setup | No | Shows stderr to user only `[SOURCE: cc-hooks-docs]` |
| `Stop` | Claude finishes responding | **Once per turn** | Yes | Prevents Claude from stopping, continues the conversation `[SOURCE: cc-hooks-docs]` |
| `StopFailure` | The turn ends due to an API error | Once per turn | No | Output/exit ignored except `terminalSequence` `[SOURCE: cc-hooks-docs]` |
| `SubagentStart` | A subagent is spawned | Per spawn | No | Shows stderr to user only (in the subagent's own transcript) `[SOURCE: cc-hooks-docs]` |
| `SubagentStop` | A subagent finishes | Per subagent | Yes | Prevents the subagent from stopping `[SOURCE: cc-hooks-docs]` |
| `TaskCompleted` | A task is being marked completed | Per task | Yes | Prevents the task from being marked completed `[SOURCE: cc-hooks-docs]` |
| `TaskCreated` | A task is being created (`TaskCreate`) | Per task | Yes | Rolls back the task creation `[SOURCE: cc-hooks-docs]` |
| `TeammateIdle` | An agent-team teammate is about to go idle | Per teammate | Yes | Prevents the teammate going idle; it keeps working `[SOURCE: cc-hooks-docs]` |
| `UserPromptExpansion` | A user-typed command expands into a prompt | Once per turn | Yes | Blocks the expansion before it reaches Claude `[SOURCE: cc-hooks-docs]` |
| `UserPromptSubmit` | A prompt is submitted, before Claude processes it | Once per turn | Yes | Blocks prompt processing and erases the prompt; stdout added as context; default timeout lowered to 30s `[SOURCE: cc-hooks-docs]` |
| `WorktreeCreate` | A worktree is created (`--worktree`, `isolation: "worktree"`, background session) | Per worktree | **Yes — any non-zero exit**, not just 2 | Fails worktree creation on any non-zero exit `[SOURCE: cc-hooks-docs]` |
| `WorktreeRemove` | A worktree is removed | Per worktree | No | Failures logged in debug mode only `[SOURCE: cc-hooks-docs]` |

The two facts that were load-bearing in the 2026-08-20 session, called out explicitly: **`Stop`
fires once per turn (not once per task, not once per engagement) and exit 2 makes it *continue the
conversation*** — the actuator is the model, not a human. **`SessionEnd` cannot block at all** —
its exit 2 only shows stderr to the user; the docs group it among events "that already happened or
can't be prevented" `[SOURCE: cc-hooks-docs]`.

## 2. Stdin — common fields on every event

```json
{
  "session_id": "string",
  "prompt_id": "UUID",
  "transcript_path": "/path/to/transcript.jsonl",
  "cwd": "/current/working/directory",
  "permission_mode": "default|plan|acceptEdits|auto|dontAsk|bypassPermissions",
  "effort": { "level": "low|medium|high|xhigh|max" },
  "hook_event_name": "EventName",
  "agent_id": "string (subagent-scoped events only)",
  "agent_type": "string (subagent-scoped events only)"
}
```
`[SOURCE: cc-hooks-docs]`. Each event adds fields specific to what it fired for — e.g. `PreToolUse`
adds `tool_name`, `tool_input`, `tool_use_id`; `Stop`/`SubagentStop` add `last_assistant_message`
(the full assistant text of the turn — the documented way to get final turn text without reading
the transcript file) `[SOURCE: cc-hooks-docs]`.

## 3. JSON output schema

```json
{
  "continue": true,
  "stopReason": "string (when continue: false)",
  "suppressOutput": false,
  "systemMessage": "string shown to Claude",
  "additionalContext": "string added to Claude's context",
  "terminalSequence": "string for terminal notifications",
  "decision": "event-specific — e.g. allow|deny|escalate for PermissionRequest",
  "reason": "string explanation",
  "hookSpecificOutput": {
    "hookEventName": "EventName",
    "permissionDecision": "allow|deny|escalate",
    "permissionDecisionReason": "string",
    "retry": true,
    "updatedInput": {}
  }
}
```
`[SOURCE: cc-hooks-docs]`. Decision-field routing differs by event, not universal:

- `PreToolUse`, `PostToolUse`, `PostToolUseFailure` → `hookSpecificOutput.permissionDecision` /
  `permissionDecisionReason`.
- `PermissionRequest` → `hookSpecificOutput.decision` (note: `decision`, not `permissionDecision`)
  — and this is the *only* way to deny on this event, since exit code 2 is not honored here.
- `PermissionDenied` → `hookSpecificOutput.retry: true` offers the model a retry; ignored when the
  classifier produced no verdict.
- Universal fields (`continue`, `systemMessage`, `additionalContext`, `terminalSequence`) work
  across most events regardless of the event-specific decision field.

**Exit code precedence** `[SOURCE: cc-hooks-docs]`: exit 2 blocks even if the JSON body says
`"allow"` — exit code wins. Claude Code still reads valid JSON output even on exit 2 (e.g. for
`systemMessage`/`reason`). Exit codes other than 0/2 are honored like exit 0 if stdout is valid JSON
matching the schema, otherwise treated as a non-blocking error — except `WorktreeCreate`, where
**any** non-zero exit fails worktree creation.

## 4. Where hooks can be configured

| Location | Scope | Shareable | Notes |
|---|---|---|---|
| `~/.claude/settings.json` | All projects | No | Local machine only |
| `.claude/settings.json` | Single project | Yes | Committable |
| `.claude/settings.local.json` | Single project | No | Gitignored by Claude Code |
| Managed policy settings | Org-wide | Yes | Admin-controlled; `allowManagedHooksOnly` restricts to these |
| Plugin `hooks/hooks.json` | While plugin enabled | Yes | Bundled with the plugin |
| Skill frontmatter | Rest of session after skill invoked | Yes | Follows workspace trust rules |
| Subagent frontmatter | While that subagent runs | Yes | Only after workspace trust accepted for that agent file's folder |

`[SOURCE: cc-hooks-docs]`. Cloud sessions (Claude Code on the web) do not read
`~/.claude/settings.json` — hooks there come from repo settings and org-managed settings only
`[SOURCE: cc-hooks-docs]`.

### Plugin-shipped agents cannot set `hooks`, `mcpServers`, or `permissionMode`

Confirmed against `code.claude.com/docs/en/plugins-reference`, fetched 2026-08-20:

> "Plugin agents support `name`, `description`, `model`, `effort`, `maxTurns`, `tools`,
> `disallowedTools`, `skills`, `memory`, `background`, and `isolation` frontmatter fields... For
> security reasons, `hooks`, `mcpServers`, and `permissionMode` are not supported for
> plugin-shipped agents." `[SOURCE: cc-plugins-reference]`

What happens if a plugin agent's frontmatter includes these fields anyway — silently dropped,
warned, or a hard validation error — **is not stated in the fetched documentation**
`[VERIFY]`. This repo's working assumption (RedGold ships agents as a plugin, per
`docs/specs/redgold/02-repository-layout.md`'s `agents/` directory) should be that these fields are
inert if present, not that they error loudly — but that assumption itself is `[INFERRED]`, not
confirmed, and should be checked directly (e.g. by adding one of these fields to a RedGold agent
definition in a scratch branch and observing behavior) before anything depends on it.

## 5. Matchers and the `if:` prefilter

Two independent filters compose: a **matcher** (which tool/event-source, e.g. `"Bash"`,
`"Edit|Write"`, `"mcp__memory__.*"`) and an **`if:` field** on an individual handler, which uses
permission-rule syntax to check the tool name *and arguments together* — e.g. `if: "Bash(git *)"`
runs only when a Bash subcommand matches `git *`; `if: "Edit(*.ts)"` only for TypeScript files
`[SOURCE: cc-hooks-docs]`.

**Matcher pattern rules** `[SOURCE: cc-hooks-docs]`: a pattern using only letters, digits, `_`, `-`,
spaces, `,`, `|` is matched as an exact/alternation match; anything else is treated as an
unanchored JavaScript regex (`RegExp.prototype.test`). `FileChanged` and `StopFailure` use a
narrower exact-match charset (letters, digits, `_`, `|` only) — hyphens/spaces/commas push those two
onto the regex path. MCP tools match as `mcp__<server>__<tool>`; matching every tool from a server
requires the explicit `.*` (`mcp__memory__.*`), and plugin-bundled servers are scoped as
`mcp__plugin_<plugin-name>_<server>__<tool>`.

**The `$(...)` / backtick caveat**, quoted verbatim from the official doc, fetched 2026-08-20:

> "For Bash patterns, whether your hook command runs depends on the shape of the pattern and the
> Bash command Claude is invoking. Leading `VAR=value` assignments are stripped before matching."

The doc's own worked table:

| `if` pattern | Bash command | Hook runs? | Why |
|---|---|---|---|
| `Bash(git *)` | `FOO=bar git push` | yes | leading assignments stripped; `git push` matches |
| `Bash(git *)` | `npm test && git push` | yes | each subcommand checked; `git push` matches |
| `Bash(rm *)` | `echo $(rm -rf /)` | yes | commands inside `$()`/backticks are checked; `rm -rf /` matches |
| `Bash(rm *)` | `echo $(date)` | no | no subcommand matches `rm *` |
| `Bash(git push *)` | `echo $(date)` | **yes** | patterns that specify more than the bare command name run the hook anyway on `$()`, backticks, or `$VAR` |

`[SOURCE: cc-hooks-docs]`. The caveat, stated precisely rather than as "unreliable" in the abstract:
a pattern that is just a command name (`Bash(git *)`) checks substituted subcommands correctly, but
a pattern **more specific than the bare command** (`Bash(git push *)`) runs the hook regardless of
what's actually inside a `$()`/backtick/`$VAR` substitution — i.e. it over-fires inside
substitution rather than under-firing. Combined with the documented fail-open behavior — quoted
verbatim: "the filter also fails open, running your hook regardless of pattern, when the Bash
command can't be parsed... because the `if` filter is best-effort, use the permission system rather
than a hook to enforce a hard allow or deny" `[SOURCE: cc-hooks-docs]` — the operative rule is:
**`if:` is a prefilter for reducing noise, never a security boundary.** Anything that must actually
block a class of command belongs in the permission system or a `PreToolUse` hook that inspects the
parsed command itself, not in an `if:` string.

## Related

- [RedGold-specific hook facts](hooks-redgold-notes.md) — what this means for engagement close and
  for `Stop`-hook designs specifically, with the finding-integrity spec's reasoning.
