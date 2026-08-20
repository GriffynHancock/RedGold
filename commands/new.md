---
description: Scaffold a new RedGold engagement directory with its scope boundary and enforcement layer. Operator-initiated only.
argument-hint: <client-slug> <yyyy-mm>
disable-model-invocation: true
---

# /rg:new — engagement scaffolder

Scaffolds `~/engagements/<client>-<yyyy-mm>/` with its authorization boundary, its three-file
contract, its ledgers, and an `.claude/settings.json` that wires `scope_guard.py` as a `PreToolUse`
hook against a **pinned, verified** interpreter.

## How to run it

Gather the authorization facts from the operator **by asking**. Do not infer them, do not default
them, and do not proceed with a placeholder. §15.1 requires all of: who authorized the test, what
they are entitled to authorize, where the signed document is, the engagement window, and — for
`redteam` only — a named emergency contact.

Then run the scaffolder:

```sh
/usr/bin/python3 "${CLAUDE_PLUGIN_ROOT}/scripts/new_engagement.py" \
  --client acme --date 2026-08 \
  --client-name "Acme Pty Ltd" --client-contact founder@acme.example \
  --auth-document ~/authorization/acme-signed-roe-2026-08-01.pdf \
  --signed-by "Jane Founder" --signed-date 2026-08-01 \
  --window-start 2026-08-05 --window-end 2026-08-19 \
  --mode audit --ceiling 2 \
  --environment production \
  --in-scope 'WILDCARD:*.acme.example' \
  --in-scope 'SUPABASE_PROJECT:abcdefghijklmnop' \
  --out-of-scope 'URL:https://blog.acme.example|third-party WordPress' \
  --crown-jewel "user geolocation" \
  --burst-cap 10
```

`--environment` is **required** and has no default: `production`, `staging`, `development`,
`ephemeral-preview` or `unknown`. Ask the client which environment these assets are; do not infer
it from a hostname. `unknown` is an honest thing to record and Gate 1 refuses to approve a plan on
it — an engagement that never established this reported a development stack on the operator's own
laptop as the client's production system, which produced seven bad findings including the only
critical. Every finding inherits the value, and severity is capped against it (RG-1 §6).

`--in-scope` is repeatable and takes `TYPE:pattern`. `--out-of-scope` additionally accepts
`TYPE:pattern|note`. Run with `--help` for the full flag set.

**White-box vs black-box is a scope question, not a mode question.** Add a `SOURCE_CODE` entry for
a white-box engagement. Note that a `SOURCE_CODE` entry names a repository, not a network
destination — it authorises reading the code, never sending requests to the host it is published on.

## What it refuses, and why

| Refusal | Reason |
|---|---|
| Authorization document does not exist on disk | No target is touched without a signed scope. Checked before the directory exists. |
| Interpreter is relative, or cannot import PyYAML | A hook that dies on import does not deny — a crashed `PreToolUse` hook **fails open**. The interpreter is tested by actually importing yaml through it before being pinned. |
| The boundary does not parse | The document is round-tripped through the parser before anything is written. |
| `ceiling` exceeds the mode's default | A declared ceiling may lower a mode's default, never raise it (§6). |
| `redteam` without a named emergency contact | §6. |
| No `--environment` | Required, no default. A fresh engagement must not be born missing the key Gate 1 demands. |
| The engagement directory already exists | It may hold evidence and ledger history. `--force` only if you are certain. |

A refused scaffold leaves nothing behind.

## What is wired, and what is not

Wired, on `PreToolUse` unless noted: `scope_guard.py` (scope, ports, ceiling, window),
`no_handrolled_loops.py`, `canary_check.py`, `no_nesting.py`, `redact.py` (`PostToolUse`),
and `validate_findings.py` (`SubagentStop`).

**Not wired, because not built:** plan/deviation checking (Gate 2), `session_start.py`,
`cleanup_gate.py`. Only hooks whose scripts exist are wired — a hook pointing at a missing script
errors, and an erroring hook is not a denying hook. Do not describe the unbuilt three as enforced.
