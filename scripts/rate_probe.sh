#!/usr/bin/env bash
# rate_probe.sh -- the only sanctioned way to send a bounded burst (spec §9.4).
#
# The bug this script exists to make impossible: a hand-rolled loop authorised for 10 requests
# sent 20, because it counted its own ITERATIONS while the loop body dispatched two requests per
# pass. So the rule here is absolute -- the counter increments immediately before exactly one
# dispatch, and nothing else in this script sends a request.
#
# Guarantees:
#   * counts dispatched requests, never iterations
#   * hard cap enforced in-script, and the cap can never exceed scope.yaml's burst limit
#   * stops at the first 429 or Retry-After
#   * refuses concurrency -- requests are strictly sequential
#   * logs its plan to ledger/activity.jsonl BEFORE the first request, not after the last
#   * refuses to run without a Gate-1 reference
#
# Logging before firing is deliberate. Logging afterwards permits recording only the attempts that
# worked, which quietly corrupts both the coverage claim and the evidence trail.

set -euo pipefail

PYTHON="${RG_PYTHON:-/usr/bin/python3}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

url=""
method="GET"
data=""
requested_max=""
gate_ref=""
root="."
marker=""

usage() {
  cat >&2 <<'EOF'
Usage: rate_probe.sh --url URL --gate-ref G-NNN [options]

  --url URL           target (must be in scope and CONFIRMED)
  --gate-ref G-NNN    the Gate-1 approval authorising this burst   [required]
  --max N             request ceiling for this burst (may lower scope.yaml's cap, never raise it)
  --method M          HTTP method (default GET)
  --data BODY         request body; implies a write
  --marker TEXT       conspicuous test-data marker to include in the body
  --root DIR          engagement directory (default .)

Sends at most N requests, strictly sequentially, stopping at the first 429 or Retry-After.
EOF
  exit 2
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --url)       url="$2"; shift 2 ;;
    --method)    method="$2"; shift 2 ;;
    --data)      data="$2"; shift 2 ;;
    --max)       requested_max="$2"; shift 2 ;;
    --gate-ref)  gate_ref="$2"; shift 2 ;;
    --marker)    marker="$2"; shift 2 ;;
    --root)      root="$2"; shift 2 ;;
    -h|--help)   usage ;;
    *) echo "REFUSED: unknown argument '$1'" >&2; exit 2 ;;
  esac
done

[[ -n "$url" ]] || { echo "REFUSED: --url is required" >&2; exit 2; }

# A burst with no approval behind it is exactly the thing that went wrong before.
if [[ -z "$gate_ref" ]]; then
  echo "REFUSED: --gate-ref is required. A bounded burst must cite the Gate-1 approval that" >&2
  echo "         authorised it. Approve a plan via /rg:gate first." >&2
  exit 2
fi

if [[ ! -f "$root/scope.yaml" ]]; then
  echo "REFUSED: no scope.yaml in $root -- run this inside an engagement directory." >&2
  exit 2
fi

# The scope cap is the authority. --max may lower it and can never raise it.
scope_cap="$("$PYTHON" - "$root" <<'PY'
import sys
sys.path.insert(0, __import__("os").environ.get("RG_SCRIPTS", ""))
from pathlib import Path
sys.path.insert(0, str(Path(sys.argv[0]).resolve().parent))
PY
)" 2>/dev/null || true

scope_cap="$(RG_SCRIPTS="$SCRIPT_DIR" "$PYTHON" -c "
import sys
sys.path.insert(0, '$SCRIPT_DIR')
import scope
try:
    b = scope.load('$root/scope.yaml')
    print(b.constraints.max_requests_per_burst or 10)
except Exception as exc:
    print('ERR:' + str(exc))
")"

if [[ "$scope_cap" == ERR:* ]]; then
  echo "REFUSED: could not read the burst cap from scope.yaml (${scope_cap#ERR:})" >&2
  exit 2
fi

cap="$scope_cap"
if [[ -n "$requested_max" ]]; then
  if ! [[ "$requested_max" =~ ^[0-9]+$ ]] || [[ "$requested_max" -lt 1 ]]; then
    echo "REFUSED: --max must be a positive integer" >&2
    exit 2
  fi
  if [[ "$requested_max" -gt "$scope_cap" ]]; then
    echo "REFUSED: --max $requested_max exceeds scope.yaml's cap of $scope_cap." >&2
    echo "         A burst ceiling may be lowered here, never raised. Amend the scope in" >&2
    echo "         writing via /rg:scope if the client authorised more." >&2
    exit 2
  fi
  cap="$requested_max"
fi

# --- the boundary check this script MUST do for itself ------------------------------------
# scope_guard.py lets RedGold's own scripts past its parser, on the explicit grounds that each
# enforces the boundary itself. That is only true if this runs. Without it, the sanctioned burst
# path would be the one way to reach an out-of-scope host with no check at all.
tier=1
if [[ -n "$data" || "$method" != "GET" ]]; then tier=2; fi

if ! "$PYTHON" "$SCRIPT_DIR/scope_guard.py" --check-url "$url" --root "$root" --tier "$tier"; then
  echo "REFUSED: rate_probe will not fire at a destination outside the authorization boundary." >&2
  exit 3
fi

# The gate reference must actually be an approved, current authorisation -- not just any string.
# gate_cli.py's check_gate() checks existence, approval, and that plan_hash/scope_hash still
# match the files on disk (an amended scope or edited plan voids the approval, §9.7). Checked
# last, immediately before anything is logged or fired, but still before either happens.
if ! gate_error="$("$PYTHON" "$SCRIPT_DIR/gate_cli.py" --root "$root" validate --gate-ref "$gate_ref" 2>&1 >/dev/null)"; then
  echo "$gate_error" >&2
  exit 2
fi

timestamp() { date -u +%Y-%m-%dT%H:%M:%SZ; }

mkdir -p "$root/ledger"
activity="$root/ledger/activity.jsonl"

# --- log the plan BEFORE firing anything ----------------------------------------------------
"$PYTHON" -c "
import json, sys
print(json.dumps({
  'ts': sys.argv[1], 'event_type': 'rate_probe.plan', 'decision': 'allow',
  'gate_ref': sys.argv[2], 'tier': 2 if sys.argv[4] not in ('GET','HEAD') else 1,
  'target': {'host': sys.argv[3], 'operation': sys.argv[4] + ' ' + sys.argv[3]},
  'reason': 'bounded burst, cap ' + sys.argv[5] + ', sequential, stop at first 429/Retry-After',
}))" "$(timestamp)" "$gate_ref" "$url" "$method" "$cap" >> "$activity"

echo "rate_probe: up to $cap sequential requests to $method $url (gate $gate_ref)"

sent=0
stopped_reason="cap reached"
declare -a codes=()

body_file="$(mktemp)"
head_file="$(mktemp)"
trap 'rm -f "$body_file" "$head_file"' EXIT

while [[ "$sent" -lt "$cap" ]]; do
  # THE INVARIANT: increment, then dispatch exactly once. Nothing else here sends a request.
  sent=$((sent + 1))

  payload="$data"
  if [[ -n "$marker" && -n "$data" ]]; then
    payload="${data//__MARKER__/${marker}-${sent}}"
  fi

  if [[ -n "$payload" ]]; then
    code="$(curl -sS -o "$body_file" -D "$head_file" -w '%{http_code}' \
              -X "$method" --data "$payload" \
              -H 'Content-Type: application/json' \
              -H 'User-Agent: RedGold-rate-probe/1.0 (authorized security assessment)' \
              --max-time 15 "$url" || echo "000")"
  else
    code="$(curl -sS -o "$body_file" -D "$head_file" -w '%{http_code}' \
              -X "$method" \
              -H 'User-Agent: RedGold-rate-probe/1.0 (authorized security assessment)' \
              --max-time 15 "$url" || echo "000")"
  fi

  codes+=("$code")
  echo "  [$sent/$cap] HTTP $code"

  if [[ "$code" == "429" ]]; then
    stopped_reason="429 received"
    break
  fi
  if grep -qi '^retry-after:' "$head_file"; then
    stopped_reason="Retry-After header received"
    break
  fi
  if [[ "$code" == "000" ]]; then
    stopped_reason="transport failure"
    break
  fi
done

throttled="false"
[[ "$stopped_reason" != "cap reached" ]] && throttled="true"

"$PYTHON" -c "
import json, sys
print(json.dumps({
  'ts': sys.argv[1], 'event_type': 'rate_probe.result', 'decision': 'allow',
  'gate_ref': sys.argv[2],
  'target': {'host': sys.argv[3], 'operation': sys.argv[4] + ' ' + sys.argv[3]},
  'reason': sys.argv[5],
  'requests_dispatched': int(sys.argv[6]), 'cap': int(sys.argv[7]),
  'throttled': sys.argv[8] == 'true',
  'status_codes': sys.argv[9].split(','),
}))" "$(timestamp)" "$gate_ref" "$url" "$method" "$stopped_reason" "$sent" "$cap" \
     "$throttled" "$(IFS=,; echo "${codes[*]}")" >> "$activity"

echo "rate_probe: dispatched $sent request(s) of a $cap cap -- $stopped_reason"
if [[ "$throttled" == "true" ]]; then
  echo "rate_probe: throttling observed. Rate limiting appears to be present on this endpoint."
else
  echo "rate_probe: no throttling observed across $sent requests."
fi
