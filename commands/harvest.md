---
description: At engagement close, promote what was learned into the redacted cross-engagement playbook library. Operator-initiated only.
disable-model-invocation: true
---

# /rg:harvest — playbook promotion

**STATUS: NOT IMPLEMENTED (v0.1.0 skeleton). Build order step 11 — v2, not v1.**

Do not simulate this command. Do not copy engagement material into `playbooks/` by hand. Tell the
operator this command is not built yet and stop.

This command is the **only** sanctioned path by which anything crosses from an engagement into this
repo, and redaction is the whole point of it. Hand-copying is how one client's data ends up in
another client's engagement.

## What it will do (spec §11.5)

Runs at engagement close. Diffs what was learned against the existing playbooks and writes new
entries into the version-keyed playbook files under `playbooks/`, **redacted** — no client names,
hosts, keys, or endpoints.

Every entry carries the engagement date it came from, so dispatch can surface its age. A stale
entry is a seed hypothesis, never a conclusion.

## Acceptance test (step 11)

A lesson from a real prior engagement lands in the correct version-keyed playbook file, redacted.
