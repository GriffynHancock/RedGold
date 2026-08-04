---
description: Write and approve the phase plan, or resolve a recorded deviation blocker. Operator-initiated only.
argument-hint: [plan | show | approve | blockers | resolve <id>]
disable-model-invocation: true
---

# /rg:gate — approval decisions

Backed by `scripts/gate_cli.py`. Do not simulate this command: do not approve a plan
conversationally, do not clear a blocker by saying it is cleared, and never record an approval the
operator did not give. Every decision below is appended to `ledger/gates.jsonl` with its
authorising clause, so the final report can state exactly when testing escalated and under whose
approval.

## Why this exists

`scripts/canary_check.py` permits a tier-2 write on one of two roads (§9.4.1): a canary proven
deleted, or the operation named in `ledger/plan.json` as client pre-approved. On a target where
anonymous callers cannot delete their own rows -- Supabase RLS configured correctly is the common
case -- the canary road dead-ends, and pre-approval is the only route to tier-2 testing at all.
This command is what produces `ledger/plan.json` and records the operator's approval of it.

## Commands

### `plan` — write the phase plan (Gate 1, not yet approved)

```
scripts/gate_cli.py plan --root ENGAGEMENT_DIR \
  --phase P3-webtest \
  --asset A-014 [--asset A-021 ...] \
  --max-tier 2 \
  --test-class authz-boundary [--test-class rate-limit ...] \
  --write-endpoint 'POST:/rest/v1/email_subscription:10' [...] \
  --live-confirm rate-limit \
  --expected-cleanup "delete by RedGold-TEST marker"
```

Writes `ledger/plan.json`. Refuses if:

- any `--asset` is not **CONFIRMED** in `assets/register.jsonl` -- promote it first with
  `/rg:scope promote <identifier> --confirm`;
- `--max-tier` exceeds the engagement ceiling declared in `scope.yaml`.

`--write-endpoint` syntax: `METHOD:/route/template[:operation][:max_writes]`. `route_template`
must match what `canary_check.py`'s `normalise_route()` would produce for the actual URL (path
parameters folded to `{id}`). `operation` is optional -- omit it to cover the whole route; for
GraphQL name the mutation explicitly. `max_writes` defaults to `1` if omitted. Examples:

- `POST:/rest/v1/email_subscription:10` -- up to 10 writes to that route, any operation
- `POST:/graphql:createComment:5` -- up to 5 `createComment` mutations specifically

### `show` — print the current plan and its approval state

```
scripts/gate_cli.py show --root ENGAGEMENT_DIR
```

Prints the plan JSON, then `APPROVED as G-00N`, `NOT APPROVED`, or `INVALID -- <reason>` (stale
because scope or plan changed since approval).

### `approve` — record operator approval (Gate 1)

```
scripts/gate_cli.py approve --root ENGAGEMENT_DIR --reason "authorising P3-webtest"
```

Appends a `gate.approve` row to `ledger/gates.jsonl` with a generated id (`G-001`, `G-002`, ...),
`plan_hash` (SHA-256 of the canonical plan JSON) and `scope_hash` (SHA-256 of `scope.yaml`'s
bytes). Refuses if no plan exists. **Editing the plan or amending scope.yaml after approval voids
it** (§9.7) -- `gate_cli.py show` and `gate_cli.py validate --gate-ref G-00N` will report it as
invalid, and `rate_probe.sh --gate-ref G-00N` will refuse to fire.

### `blockers` — list unresolved Gate 2 deviations

```
scripts/gate_cli.py blockers --root ENGAGEMENT_DIR
```

Lists unresolved rows from `ledger/blockers.jsonl` (indexed for use with `resolve`): a new asset
discovered mid-phase, a tier above what the plan authorises, an endpoint not named, an unexpected
write. `scope_guard.py`'s plan-checking steps (§9.3.2) are what raise these -- this command only
lists and resolves them.

### `resolve <index-or-id>` — record the operator's decision (Gate 2)

```
scripts/gate_cli.py resolve 1 --decision allow --reason "client confirmed by email 2026-08-06"
scripts/gate_cli.py resolve B-003 --decision deny --reason "out of scope for this engagement"
```

Appends a `gate.resolve` row to `ledger/gates.jsonl` and marks the blocker resolved. `--decision`
is `allow` or `deny`; `--reason` is required and goes straight into the audit trail.

## Worked example: authorising a write endpoint end to end, from a cold start

```sh
# 1. The asset must already be CONFIRMED (promoted, not just discovered).
scripts/scope_cli.py --root ENGAGEMENT_DIR show   # check assets/register.jsonl

# 2. Write the plan naming the write endpoint and its budget.
scripts/gate_cli.py plan --root ENGAGEMENT_DIR \
  --phase P3-webtest --asset A-014 --max-tier 2 \
  --test-class authz-boundary \
  --write-endpoint 'POST:/rest/v1/email_subscription:10' \
  --expected-cleanup "delete by RedGold-TEST marker"

# 3. Operator reviews it, then approves.
scripts/gate_cli.py approve --root ENGAGEMENT_DIR --reason "P3-webtest authorised"
#   -> Approved as G-001

# 4. canary_check.py now permits that write (no canary needed -- pre-approval carries it):
#    a POST to /rest/v1/email_subscription is allowed up to 10 times, then the budget is
#    exhausted and canary_check.py denies again until the plan is amended.

# 5. A bounded burst against it cites the gate:
scripts/rate_probe.sh --root ENGAGEMENT_DIR --gate-ref G-001 \
  --url https://api.acme.example/rest/v1/email_subscription --method POST \
  --data '{"email":"__MARKER__@redgold-test.invalid"}' --marker RedGold-TEST --max 5
```

If scope.yaml or the plan changes after step 3, `G-001` goes stale: `gate_cli.py show`,
`gate_cli.py validate --gate-ref G-001`, and `rate_probe.sh --gate-ref G-001` all refuse until
`approve` is re-run.

## The canary row schema (`ledger/cleanup.jsonl`)

Path (a) in §9.4.1 -- canary-proven, no pre-approval needed -- requires a row in
`ledger/cleanup.jsonl` with these keys: `purpose`, `state`, `method`, `route_template`,
`operation`. `purpose` must be the literal string `"canary"`. `state` must reach `"deleted"` --
`"pending"` (not yet confirmed removed) and `"orphaned"` (delete attempted and failed) do **not**
unblock the operation. Example row:

```json
{"purpose": "canary", "state": "deleted", "method": "POST", "route_template": "/rest/v1/email_subscription", "operation": "POST /rest/v1/email_subscription", "canary_id": "rg-canary-8f21", "created_ts": "2026-08-06T09:31:00Z", "deleted_ts": "2026-08-06T09:32:00Z"}
```

See `scripts/canary_check.py`'s module docstring for the full rule, including how `operation` is
derived for GraphQL endpoints.

## Acceptance test

`tests/test_gate_cli.py` -- covers refusal of an unconfirmed asset, `--max-tier` above ceiling,
`approve` with no plan, gate staleness after editing `scope.yaml` or the plan, `rate_probe.sh`
refusing an unknown or stale gate ref, and the end-to-end path: a plan is written, approved, and
`canary_check.py` then permits a write it previously denied.
