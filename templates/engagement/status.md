# status.md — {{ENGAGEMENT_ID}}

*What is true right now.* Present tense only. History goes in `session.md`.

## Phase

| Phase | State |
|---|---|
| Scope agreed (Gate 0) | **done** — `scope.yaml` written {{SCAFFOLD_DATE}} |
| Test plan approved (Gate 1) | **not started** |
| Recon | not started |
| Surface map | not started |
| Active testing | not started |
| Verification | not started |
| Report | not started |

## Boundary

| | |
|---|---|
| Mode | `{{MODE}}`, ceiling {{CEILING}} |
| Window | {{WINDOW_START}} to {{WINDOW_END}} |
| In scope | {{IN_SCOPE_SUMMARY}} |
| Out of scope | {{OUT_OF_SCOPE_SUMMARY}} |

## Assets

| | Count |
|---|---|
| CONFIRMED (`assets/register.jsonl`) | 0 |
| CANDIDATE (`assets/candidates.jsonl`) | 0 |

No asset is testable above tier 1 until it is CONFIRMED by two independent attribution signals.

## Findings

None yet.

## Cleanup debt

None yet. Every write lands in `ledger/cleanup.jsonl` as `pending`, `deleted` or `orphaned`.
The engagement does not close with anything left `pending`.

## Open blockers

None.
