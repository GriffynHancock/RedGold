---
description: Show the engagement boundary, promote a discovered asset to CONFIRMED, or amend the boundary in writing. Operator-initiated only.
argument-hint: show | add-candidate <host> | promote <host> | amend
disable-model-invocation: true
---

# /rg:scope — the authorization boundary

```sh
RG=/usr/bin/python3\ "${CLAUDE_PLUGIN_ROOT}/scripts/scope_cli.py"\ --root\ .

# what is authorised, what is confirmed, what is waiting
$RG show

# record something recon found
$RG add-candidate api.acme.example \
    --discovery-method "crt.sh CT log" \
    --signal 'TLS_SAN:api.acme.example@crt.sh' \
    --signal 'CONTENT_FP:matches prod bundle hash@httpx'

# make it testable above tier 1
$RG promote api.acme.example --confirm

# change what was authorised
$RG amend --add 'WILDCARD:*.other.example' --reason "signed amendment 2026-08-05"
```

## Why promotion is a command and not an edit

Promotion is the moment an asset becomes testable above tier 1. Hand-editing `register.jsonl`
would make "never promote on a single signal" a rule someone has to remember — and this project's
audit history is a list of rules that were prose.

| Refusal | Reason |
|---|---|
| One attribution signal class | Two independent classes required, or explicit `CLIENT_CONFIRMED` (§5.2). Two observations of the *same* class is still one class. |
| A signal whose value is a bare IP | Shared edge IPs (Cloudflare, Vercel, Netlify) cover every tenant at that address — and that is where this client base lives. There is deliberately **no IP signal class**, so the rule is enforced by the vocabulary, not by memory. |
| Asset outside the boundary, or explicitly excluded | Promotion never widens scope. Amend first, in writing. |
| No `--confirm` | Operator sign-off is required even when the signals qualify. |
| An amendment that does not parse | The boundary is round-tripped through the parser before it is written. |

An amendment records a `scope.amend` row in `ledger/gates.jsonl` and **voids every gate approval
derived from the previous scope** — an amended scope cannot silently inherit an older
authorisation (§9.7).

## The attribution carve-out

An unconfirmed asset inside the boundary is still reachable at **tier 0–1 only**, as an attribution
probe (§5.5) — otherwise nothing could ever be confirmed, because the signals that confirm an asset
can only be obtained by contacting it. Tier 2 and above stays denied until promotion.

**Not yet enforced:** §5.5 additionally requires attribution probes to be rate-limited, logged with
`purpose: attribution`, and to have anything they observe discarded as evidence. Those three are
not implemented, so do not describe attribution probing as fully constrained.
