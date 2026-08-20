#!/usr/bin/env python3
"""canary_check.py -- PreToolUse hook. Write authorisation (spec §9.4, §9.4.1).

Build order step 7.

THE INCIDENT THIS IS
--------------------
A prior engagement left **15 undeletable `email_subscription` rows and 6 orphaned note rows in a
live client database**, still outstanding as action items at handoff, because the automation could
create test data faster than it could guarantee removing it. An ownership check refused the
anonymous creator's own delete.

THE RULE
--------
*Create a canary -> prove the delete path works -> only then proceed.*

But a canary alone dead-ends on this framework's core client segment. Row-level security is
routinely and **correctly** configured so an anonymous user cannot delete rows they inserted --
which is exactly the incident above. If a passing canary were the only route to a write, then
tier-2 testing that §6 says an audit *must* include would be permanently unreachable on the most
common target stack.

So a write proceeds if **either** holds:

  (a) **Canary-proven** -- a canary write to this operation was created and verified deleted.
  (b) **Client pre-approved** -- the client approved writes to this operation class in the plan,
      accepting in advance that residue may need manual removal. Conspicuous test data (§6.1)
      makes that residue trivially identifiable, and the cleanup appendix hands them the query.

It denies only when **neither** holds: an unapproved write to an operation with no proven delete
path. That is still the original failure, and it stays blocked.

What must never happen is a write proceeding on an agent's judgement that cleanup will probably
work. Both paths route through a decision recorded *before* the fact -- (a) through evidence,
(b) through the plan.

THE CANARY ROW SCHEMA (`ledger/cleanup.jsonl`)
-----------------------------------------------
`canary_proven()` below reads this file looking for a canary row that reached `state: deleted`.
The required keys are `purpose`, `state`, `method`, `route_template`, `operation` -- match
`{method, route_template, operation}` exactly against the write you are trying to authorise, or
it will not be found. Extra keys (`created_ts`, `deleted_ts`, `canary_id`, `note`, ...) are
welcome and ignored by this check, but the five required ones are load-bearing.

`purpose` must be the literal string `"canary"` for a proving row (any other value, or its
absence, means the row cannot authorise anything -- see `writes_already_made()`, which counts
*non*-canary rows against a plan's `max_writes` budget, except those whose `state` positively
records that the request was never dispatched).

`state` must reach `"deleted"`. `"pending"` (write made, delete not yet attempted or not yet
confirmed) and `"orphaned"` (delete attempted and failed -- what `cleanup_gate.py` blocks session
end on) do **not** unblock further writes to that operation. Only a row that has actually reached
`deleted` counts as proof the delete path works.

Copy-pasteable example -- append this as one line to `ledger/cleanup.jsonl`:

```json
{"purpose": "canary", "state": "deleted", "method": "POST", "route_template": "/rest/v1/email_subscription", "operation": "POST /rest/v1/email_subscription", "canary_id": "rg-canary-8f21", "created_ts": "2026-08-06T09:31:00Z", "deleted_ts": "2026-08-06T09:32:00Z"}
```

Note `operation` for a plain REST route is conventionally `"{METHOD} {route_template}"`, matching
what `resolve_operation()` below produces automatically for non-GraphQL routes. For a GraphQL
endpoint, `operation` is the mutation name (e.g. `"deleteAccount"`), never the shared `/graphql`
route alone.

OPERATION IDENTITY
------------------
A canary is keyed by `{method, route_template, operation}`, never by literal URL. `route_template`
normalises path parameters, and `operation` carries the logical mutation name where one URL serves
many: a GraphQL endpoint is one route but `createComment` and `deleteAccount` are different
operations, and a canary proven for one must never unblock the other. Anything that cannot be
resolved to a distinct operation is denied rather than guessed at.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import scope_guard  # noqa: E402

WRITE_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

# States that mean "this row was logged before an attempt that never left the machine" -- the
# guard refused it, and that refusal is itself recorded. Anything else, including an absent,
# empty or unrecognised state, counts as a write that may have been made. See
# `writes_already_made()` for why the ambiguity resolves that way.
NEVER_DISPATCHED_STATES = frozenset({"denied_not_sent"})

# Path segments that are identifiers rather than route structure.
_UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_NUMERIC = re.compile(r"^\d+$")
# An opaque identifier contains a digit. Without that requirement a long all-alphabetic
# segment like `deleteallaccounts` normalised to `{id}`, collapsing distinct operations onto
# one canary key -- so a canary proven for a harmless route unblocked a dangerous one.
_OPAQUE_ID = re.compile(r"^(?=[0-9a-z_-]*\d)[0-9a-z_-]{16,}$", re.I)

_GRAPHQL_OP = re.compile(r"\b(?:mutation|query)\s+(\w+)")

# scope_guard.URL_RE deliberately captures only the authority -- it answers "what host will this
# reach". This control needs the path, so it matches the whole URL.
FULL_URL_RE = re.compile(r"https?://[^\s'\"|;>)]+", re.IGNORECASE)


class Undeterminable(Exception):
    """The operation cannot be identified. Deny rather than guess."""


def normalise_route(path: str) -> str:
    """`/api/users/1f2e.../comments/42` -> `/api/users/{id}/comments/{id}`."""
    segments = []
    for segment in path.split("/"):
        if not segment:
            segments.append(segment)
            continue
        if _UUID.match(segment) or _NUMERIC.match(segment) or _OPAQUE_ID.match(segment):
            segments.append("{id}")
        else:
            segments.append(segment)
    return "/".join(segments) or "/"


def extract_method(command: str) -> str:
    # `-XDELETE` with no space is valid curl and was missed by a `\s+` pattern -- which
    # bypassed write authorisation AND tier classification in one stroke.
    match = re.search(r"-X\s*([A-Za-z]+)|--request[\s=]*([A-Za-z]+)", command)
    if match:
        return (match.group(1) or match.group(2)).upper()
    # -T / --upload-file is a PUT in everything but name.
    if re.search(r"(?:^|\s)(?:-T|--upload-file)\b", command):
        return "PUT"
    if re.search(r"(?:^|\s)(?:-d|--data|--data-raw|--data-binary|--form|-F)\b", command):
        return "POST"
    return "GET"


def extract_body(command: str) -> str:
    match = re.search(r"(?:-d|--data|--data-raw|--data-binary)[\s=]+('([^']*)'|\"([^\"]*)\"|(\S+))",
                      command)
    if not match:
        return ""
    return match.group(2) or match.group(3) or match.group(4) or ""


def resolve_operation(url_path: str, body: str, method: str) -> str:
    """The logical mutation name. Raises Undeterminable when one URL could serve many."""
    route = normalise_route(url_path)

    if "graphql" in route.lower():
        # One route, many operations. Guessing here would let a canary proven for a harmless
        # mutation unblock an account deletion.
        if body:
            try:
                payload = json.loads(body)
                if isinstance(payload, dict):
                    named = payload.get("operationName")
                    if isinstance(named, str) and named:
                        return named
                    query = payload.get("query")
                    if isinstance(query, str):
                        found = _GRAPHQL_OP.search(query)
                        if found:
                            return found.group(1)
            except (json.JSONDecodeError, ValueError):
                found = _GRAPHQL_OP.search(body)
                if found:
                    return found.group(1)
        raise Undeterminable(
            "this is a GraphQL endpoint and the operation name could not be determined. One "
            "route serves many mutations, so a canary proven for one must not unblock another."
        )

    return f"{method} {route}"


def canary_key(method: str, route: str, operation: str) -> str:
    return f"{method} {route}#{operation}"


def read_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                rows.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return rows


def canary_proven(root: Path, method: str, route: str, operation: str) -> bool:
    """(a) a canary for THIS operation was created and verified deleted."""
    for row in read_jsonl(root / "ledger" / "cleanup.jsonl"):
        if row.get("purpose") != "canary":
            continue
        if row.get("state") != "deleted":
            continue
        if (str(row.get("method", "")).upper() == method
                and row.get("route_template") == route
                and row.get("operation") == operation):
            return True
    return False


def writes_already_made(root: Path, method: str, route: str, operation: str) -> tuple[int, int]:
    """`(dispatched, logged_but_never_dispatched)` for this operation.

    A cleanup row is written **before** the write is attempted (engagement rule 5: the audit
    trail must exist before the action). So a row also exists for a write that was then refused
    and never sent -- and counting those as spent budget let a *denied* attempt consume the very
    quota it was denied by. That is B-003: two refused attempts exhausted a budget of two while
    zero requests had ever reached the target.

    The correction is deliberately asymmetric, because the two errors are not equally bad.
    Under-counting means more writes reach a client's live data than they authorised -- the
    incident this whole module exists for. Over-counting only blocks a test, loudly, with a
    message the operator can act on. So ambiguity fails CLOSED: a row counts as dispatched
    unless its `state` **positively** says the request never left. A crashed, timed-out or
    killed worker leaves a row whose outcome was never written back; that row still counts,
    which is exactly what we want.

    `NEVER_DISPATCHED_STATES` is therefore an allow-list of states that mean "the guard itself
    refused this before dispatch", not a deny-list of states that mean "made". Only `state` is
    consulted -- never the free-text `outcome`/`note` prose, which is unstructured and not a
    control surface. Extending this set is a deliberate decision, never a convenience.
    """
    dispatched = 0
    undispatched = 0
    for row in read_jsonl(root / "ledger" / "cleanup.jsonl"):
        if row.get("purpose") == "canary":
            continue
        if (str(row.get("method", "")).upper() == method
                and row.get("route_template") == route
                and row.get("operation") == operation):
            if str(row.get("state", "")).strip().lower() in NEVER_DISPATCHED_STATES:
                undispatched += 1
            else:
                dispatched += 1
    return dispatched, undispatched


def plan_preapproval(root: Path, method: str, route: str, operation: str) -> tuple[bool, str]:
    """(b) the client pre-approved writes to this operation class, and budget remains."""
    plan_path = root / "ledger" / "plan.json"
    if not plan_path.is_file():
        return False, "no approved plan (ledger/plan.json) exists"
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return False, f"plan could not be read: {exc}"

    for entry in plan.get("write_endpoints") or []:
        if not isinstance(entry, dict):
            continue
        if str(entry.get("method", "")).upper() != method:
            continue
        if entry.get("route_template") != route:
            continue
        # An entry may pin an operation; if it does not, it covers the route.
        if entry.get("operation") and entry.get("operation") != operation:
            continue
        max_writes = entry.get("max_writes")
        if not isinstance(max_writes, int) or max_writes < 1:
            return False, (f"plan entry for {method} {route} has no usable max_writes budget")
        made, undispatched = writes_already_made(root, method, route, operation)
        if made >= max_writes:
            reason = (f"the plan's write budget for {method} {route} is exhausted "
                      f"({made} of {max_writes} dispatched)")
            if undispatched:
                # B-003: do not let the next operator read a pile of logged rows as spent
                # budget. Say which rows actually cost something and which did not.
                reason += (f"; a further {undispatched} row(s) are logged but never dispatched "
                           f"(state in {sorted(NEVER_DISPATCHED_STATES)}) and do not consume "
                           "budget")
            reason += (". Only rows positively marked as never dispatched are exonerated -- a "
                       "row with a missing or unrecognised state counts as a write made.")
            return False, reason
        return True, ""
    return False, f"the approved plan does not name {method} {route} as a write endpoint"


def emit_deny(reason: str) -> None:
    json.dump({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }, sys.stdout)
    sys.stdout.write("\n")


def evaluate(payload: dict, root: Path) -> tuple[bool, str]:
    tool_name = payload.get("tool_name")
    tool_input = payload.get("tool_input") or {}

    if tool_name == "WebFetch":
        return True, ""          # WebFetch issues GETs; it cannot mutate.
    if tool_name != "Bash":
        return True, ""

    command = tool_input.get("command")
    if not isinstance(command, str) or not command.strip():
        return True, ""
    match = FULL_URL_RE.search(command)
    if not match:
        return True, ""

    method = extract_method(command)
    body = extract_body(command)
    # A GraphQL mutation is a write whatever verb carries it. Sending one by GET was a clean
    # bypass of write authorisation.
    if method not in WRITE_METHODS:
        if "graphql" in match.group(0).lower() and re.search(r"\bmutation\b", command, re.I):
            method = "POST"
        else:
            return True, ""

    after_scheme = match.group(0).split("://", 1)[1]
    path = "/" + after_scheme.split("/", 1)[1] if "/" in after_scheme else "/"
    path = path.split("?")[0].split("#")[0]
    route = normalise_route(path)

    try:
        operation = resolve_operation(path, body or command, method)
    except Undeterminable as exc:
        return False, (
            f"DENIED (operation not identifiable): {exc} Name the operation explicitly, or raise "
            "a deviation via /rg:gate."
        )

    if canary_proven(root, method, route, operation):
        return True, ""

    approved, why_not = plan_preapproval(root, method, route, operation)
    if approved:
        return True, ""

    return False, (
        f"DENIED (no write authorisation): {method} {route} (operation '{operation}') has neither "
        "a canary proven deleted nor client pre-approval.\n\n"
        f"  canary : no cleanup.jsonl row shows a canary for this operation verified deleted\n"
        f"  plan   : {why_not}\n\n"
        "A prior engagement left 15 undeletable rows in a live client database because writes ran "
        "faster than cleanup could be guaranteed. Either (a) write one canary and verify you can "
        "delete it, recording purpose=canary and state=deleted in ledger/cleanup.jsonl, or (b) "
        "get the client to pre-approve this operation class in the plan, accepting that residue "
        "may need manual removal.\n\n"
        "Note for the report either way: an application whose own operators cannot delete test "
        "data has a data-lifecycle problem. That is a posture finding in its own right."
    )


def main() -> int:
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise ValueError("hook payload is not a JSON object")
        root = Path(scope_guard.find_engagement_root(payload))
        allow, reason = evaluate(payload, root)
    except Exception as exc:  # noqa: BLE001 -- a crashed PreToolUse hook fails OPEN
        emit_deny(
            f"DENIED (canary_check could not evaluate this call): {type(exc).__name__}: {exc}. "
            "A control that cannot evaluate must not permit."
        )
        return 0

    if not allow:
        emit_deny(reason)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
