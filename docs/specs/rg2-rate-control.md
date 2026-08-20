---
title: RG-2 — request-volume control for tools that loop internally
date: 2026-08-20
status: draft
question: What actually bounds the volume of traffic RedGold sends at a client, where does that bound live, and which parts of it are boundaries rather than hopes?
---

# RG-2 — request-volume control

## Index

| § | Question |
|---|---|
| 1 | What is actually being protected, and why "rate" is the wrong noun |
| 2 | The five candidate control points, graded |
| 3 | The recommended design — `scan_run.py`, the wrapper requirement, and the wall-clock account |
| 4 | Where the number comes from: RG-4 E2 → `scope.yaml` → every control point |
| 5 | Honest limits — what stays unenforceable, and the sentence this earns |

## The gap this document answers

`scripts/no_handrolled_loops.py` denies a Bash command that combines an iteration construct with a
request tool. It exists because of a real incident (`07-enforcement.md` §9.4): an agent hand-rolled a
rate-limit probe authorised for **ten** requests and sent **twenty**, because the loop counted its own
iterations while the body dispatched two requests per pass.

`rg3-test-libraries.md` §5.5 records that this control **cannot see a scanner**:

> `nuclei -u <one-url> -dast …` trips none of those patterns, and correctly so: there is no shell
> loop. The fan-out happens inside a Go binary the hook cannot see.

`nuclei -u https://target -t /pinned/templates` is one command line with no iteration syntax that
issues on the order of 1,500 requests. The control encoding one of RedGold's two founding incidents
is structurally blind to the entire class of tooling RG-3 exists to adopt. The same document records
a second admission (§5.4): the fuzz request budget is **a post-hoc detection, not a control**, because
nuclei has no total-request flag and the real ceiling is `rate × wall_clock`.

This document takes both admissions as given and asks where the control actually belongs.

---

## 1. The real requirement

**Rate is a proxy, and a bad one.** Ten requests per second against a Vercel-fronted marketing site is
nothing; ten requests per second against a Supabase free-tier project with a synchronous export
endpoint is an outage. Counting requests is easy, which is why the framework counts them. It is not
what anyone is trying to protect.

Three things are actually being protected, and they fail in different ways:

1. **The client's service, for its real users.** The harm is availability and cost: a slowed site, a
   tripped WAF that locks out genuine customers, an exhausted database connection pool, a metered
   API bill, a paged on-call engineer at 2am. This is `rg2-containment.md` §10.1 item 3 — *harm at a
   permitted destination* — the class the firewall explicitly does nothing about.
2. **The authorisation actually holding.** A client agreed to "a burst of rapid requests" (RG-4 E2),
   not to an unbounded one. Traffic beyond what was agreed is traffic outside the authorisation, and
   `07-enforcement.md` §9.3.1 states the consequence plainly: under the Australian Criminal Code Part
   10.7 (s478.1) **the operator's own exposure turns on authorisation scope actually holding.** An
   overrun is not a courtesy failure. It is the same category of event as touching an out-of-scope
   host, arriving through a different door.
3. **The engagement's own results.** Concurrency and volume make the target's rate limiting a
   variable in every other finding (RG-3 §2.5). A scan that trips the target's own throttling
   produces a result about RedGold's traffic, not about the client's application.

**The requirement, in one sentence:**

> No engagement may place more load on a client's system than the client agreed in writing to absorb,
> and every request RedGold sends must be attributable to an approved plan, bounded before it is sent,
> and stoppable while it is in flight.

Four properties fall out of that sentence, and they are the criteria the rest of this document grades
against:

| Property | Why it is separate |
|---|---|
| **Bounded before firing** | A number computed after the run is a report, not a control. `rate_probe.sh` logs its plan *before* the first request for exactly this reason |
| **Attributable** | A count with no gate reference and no ledger row cannot be shown to a client or defended afterwards |
| **Stoppable in flight** | A 20-minute scan that the operator cannot halt is 20 minutes of committed load. This is the property the wall-clock timeout buys, and the only one a post-hoc assertion cannot |
| **Derived from consent** | A cap RedGold picked for itself is a self-imposed courtesy, not an authorisation limit. §4 |

**What this requirement does *not* say.** It does not say "few requests". A rate-limit test that sends
too few requests to trigger a limiter has failed to test the control the client is paying for
(`04-modes-and-tiers.md` §6: *"a client handed an 'audit' that skipped rate limiting has not been
audited"*). The constraint is a **ceiling with provenance**, not minimisation.

**And one thing the requirement exposes immediately:** request *count* is not the load variable.
A single request to `/api/export?all=true` can cost the target more than 1,500 fuzz requests. Nothing
in this document bounds that, and §5 says so rather than letting the count stand in for the harm.

---

## 2. The candidate control points, graded

Grades use `rg2-containment.md` §1's vocabulary, unchanged: **Advisory**, **Heuristic**,
**Defence-in-depth** (weak/strong), **Boundary precondition**, **BOUNDARY**, **Detection**. The
discipline of that table is that only one row is allowed to be a boundary, and inflating any other row
is the failure it exists to prevent.

### 2.0 The table

| # | Control point | What it actually stops | What defeats it | Grade |
|---|---|---|---|---|
| A | `no_handrolled_loops.py` — shell-syntax hook | Improvised bursts written in bash: `for`, `while`, `xargs`, brace expansion, `curl [1-20]`, `-Z`, `-K`, backgrounding, >3 URLs on a line. This is the 20-vs-10 incident and it is genuinely stopped | Any binary that loops internally — nuclei, ffuf, nmap, ZAP, testssl. The fan-out is inside a process the hook cannot see | **Heuristic** |
| B | Wrapper allowlist — tier-2 tools must go through `scan_run.py` | The ordinary case completely: one place owns the rate flags, the gate ref, the budget, the pre-flight log and the process timeout | Invoking the binary directly, which is caught only by the same string parser §9.3.1 already calls a heuristic (`n=nuclei; $n …`, a copied binary, `python3 -c`) | **Defence-in-depth (strong)** |
| C | Per-tool native rate flags — `nuclei -rl`, `nmap --max-rate`, ZAP's rate limiter | The actual load, in practice. These are the only mechanism that determines what the tool really sends | Cooperative by construction: correct invocation is the whole guarantee. A flag that silently no-ops (§1.5's `-td` case) leaves a run that *looks* capped in the command line, the log and the report | **Defence-in-depth (cooperative)** |
| D | The gateway — nftables/proxy on `rg-gw` | **Connection rate and byte volume to a destination**, enforced by a principal the workload cannot become | Nothing the workload can reach — *for what it measures*. But it cannot measure requests at all (§2.4) | **BOUNDARY**, for connections and bytes only |
| E | Post-hoc ledger detection with halt | Nothing in flight. Makes an overrun undeniable, halts the session, and blocks engagement close | Latency — the requests are already sent. And a workload that has escaped forges its own ledger (`rg2-containment.md` §5.6) | **Detection** |

**Read the D row carefully.** It is a boundary, and it is a boundary over the wrong variable. That
gap is the central finding of this document and §2.4 works it out.

### 2.1 A — the existing shell-syntax hook

**What it still catches, and this is not nothing.** The founding incident was an agent writing a loop
in bash. That remains the most likely way an overrun happens, because it is what an agent reaches for
when no tool is to hand: a quick `for i in {1..20}` to check whether an endpoint throttles. The hook's
pattern list is broader than "loop keywords" — brace expansion, curl URL globbing, `-Z/--parallel`,
`-K/--config`, `-i/--input-file`, `-r/--recursive`, and a bare `MAX_URLS_PER_COMMAND = 3` fan-out
check — and each of those is a way to issue N requests from one line without a loop keyword. Deleting
this hook would be a regression.

**What it structurally cannot catch.** The hook inspects a shell string. `nuclei`, `ffuf`, `nmap`,
`zap.sh` and `testssl.sh` iterate inside their own process. There is no syntax to match, and there is
no version of this hook that can match one — the information is not in the string. Adding scanner
names to `LOOP_PATTERNS` would deny scanning outright, which is not a control, it is a ban.

**A false-positive worth fixing while the file is open.** `LOOP_PATTERNS` denies
`(?:^|\s)(?:-i|--input-file)\b` as "a wget input file" and `(?:^|\s)(?:-r|--recursive|-m|--mirror)\b`
as "recursive mirroring". `curl -i https://in.scope/health` is *include response headers* — one of the
most common commands in this entire product — and `curl -r 0-1023` is a byte range. Both are denied
today with a message about hand-rolled request loops. This is precisely `rg2-containment.md` §1.3's
named failure mode: *a deny on legitimate work pushes the operator toward deleting the hook.* The
Verified by calling `no_handrolled_loops.evaluate()` directly this session: `curl -i
https://in.scope/health` → denied, `curl -r 0-1023 https://in.scope/f` → denied, and
`nuclei -u https://t -rl 5 -c 1` → allowed. The hook denies the two safe commands and permits the
1,500-request one. The `-i`/`-r` patterns must be narrowed to the tools that give them that meaning (`wget -i`, `wget -r`)
rather than matched globally. **Fix this in the same change as anything else in §3, and pay for it
with a test.**

**Grade: Heuristic.** Unchanged by anything in this document, and still worth having.

### 2.2 B — the wrapper allowlist

RG-3 §5.5's proposal: generalise `SANCTIONED` from the single `rate_probe.sh` regex to a table of
vetted wrappers, and require that any invocation naming a tier-2 network tool goes through one.

**This is the right shape, and the argument for it is exactly `rate_probe.sh`'s.** A wrapper is the
only place where the budget can be *known before the run*: it is where the profile is read, the scope
cap is applied, the gate reference is validated, the plan row is written, the flags are asserted and
the process timeout is set. None of those can live in a hook, because a hook sees a string and has no
process to supervise.

**What stops the agent invoking the binary directly?** Mechanically: a new deny rule in
`no_handrolled_loops.py` — a command naming a member of `TIER2_TOOLS ∪ TIER3_TOOLS` (plus the scanners
RG-3 pins that are not in those sets today: `testssl`, `zap.sh`, `zap-cli`) is denied unless it matches
a sanctioned wrapper invocation.

**Is that enforceable? No — and the honest description matters here.** It rests on the same
token-matching that §9.3.1 disclaims:

| Bypass | Caught by |
|---|---|
| `n=nuclei; $n -u https://t` | `scope_guard.py`'s `INDIRECTION_RE` → **denied** as undeterminable |
| `echo 'nuclei …' > /tmp/s.sh && bash /tmp/s.sh` | `SCRIPT_EXEC_RE` → **denied** as undeterminable |
| `python3 -c "subprocess.run(['nuclei',…])"` | `INLINE_CODE_RE` → **denied** as undeterminable |
| `cp $(command -v nuclei) /tmp/x && /tmp/x -u …` | The `$(…)` denies the first half; a two-turn version with the copy done earlier is **not caught** |
| `/opt/rg/bin/nucl''ei -u …`, or any renamed binary | **Not caught.** The token is not `nuclei` |
| A tool RedGold has never heard of | **Not caught.** The list is an enumeration |

The composite of the two hooks is meaningfully stronger than either alone — three of six rows are
denied by machinery that already exists — but the last three rows are real and the grade must reflect
them. This is **defence-in-depth (strong)**: it converts "an agent can trivially outrun the budget" into
"an agent must deliberately evade two hooks to outrun the budget", and it does not convert it into
"cannot".

**The trap that comes with it.** Adding `scan_run.py` to `scope_guard.FRAMEWORK_SCRIPTS` makes
`extract_hosts()` return an empty set for that command line — the parser stops looking. The comment in
`scope_guard.py` is explicit that this is safe *only* because each listed script "enforces the boundary
itself, in code". `rate_probe.sh` does (it calls `scope_guard.py --check-url` before it fires).
**`scan_run.py` must do the same, per target, or the wrapper requirement becomes the bypass** — the one
sanctioned path to a scanner would be the one path with no boundary check at all.

### 2.3 C — per-tool native rate flags

Verified against the pinned versions, this session. Everything below is either sourced or marked.

| Tool | Mechanism | Verified | Honest limit |
|---|---|---|---|
| **nuclei** | `-rl, -rate-limit int` (**default 150**), `-rld, -rate-limit-duration` (default `1s`), `-c, -concurrency` (default 25), `-bs, -bulk-size` (default 25), `-timeout int` (default 10), `-mhe, -max-host-error` (default 30), `-duc`, `-dast`, `-per-host-rate-limit` | Flag names, arity and defaults read from the `v3.11.1` README usage dump this session | **The defaults are the danger.** An unflagged `nuclei -u` runs at up to 150 rps with 25 parallel templates. There is still **no total-request flag** — RG-3 §5.4 stands. `-rlm/-rate-limit-minute` is marked DEPRECATED in that same dump; do not build on it. Semantics of `-per-host-rate-limit` relative to `-rl` are `[VERIFY]` — one target per invocation makes the distinction moot, which is why §3 keeps that rule |
| **nmap** | `--max-rate`, `--min-rate` (packets/second), `--scan-delay`, `--max-retries`, `--host-timeout`, `-T0`–`-T5` | Read from the nmap reference guide (`man-performance`) this session | **`--max-rate` and `--min-rate` are global across the scan, not per host**, and the reference guide states they affect port scanning and host discovery — **not NSE**. RedGold's baseline profile uses NSE scripts (`http-security-headers`, `http-cors`, `http-config-backup`). **The rate flag does not bound the traffic RedGold actually cares about here.** NSE load is bounded by script count × targets and by `--script-timeout` `[VERIFY: exact spelling and whether it is per-script or per-host at 7.99]` |
| **testssl.sh** | `--mode serial` (default), `--parallel`, `MAX_PARALLEL` (env, default 20), `--connect-timeout`, `--openssl-timeout`, `MAX_WAIT_TEST` (default 1200) | Read from the 3.2 branch `testssl.1.md` this session | **There is no request-rate or connection-rate option at all.** Parallelism and timeouts only. testssl is bounded *by construction* — it runs a fixed test list against one host — which is a real bound but not a configurable one. The wrapper's lever is serial mode, one host per invocation, and the wall clock |
| **ZAP** | Network add-on **Rate Limit**: rules with `requestsPerSecond` and `groupBy: rule\|host`, applied to all HTTP/HTTPS traffic through ZAP | Documented at `zaproxy.org/docs/desktop/addons/network/options/ratelimit/`; exact API parameter spellings `[VERIFY]` against the pinned ZAP version before use | **The best of the four**, because ZAP is a proxy and the limit applies to everything it emits, spider and active scan alike. It is still cooperative: it must be configured before the scan starts, from the wrapper, not from the desktop UI |
| **trufflehog / gitleaks** | n/a | RG-3 §6.2 | Local filesystem scanners. They generate **no target traffic** unless trufflehog's live verification is enabled, which is a network action against a third party and defaults OFF. Not in this regime; the wrapper asserts the verification flag rather than assuming it `[VERIFY: exact flag spelling at 3.97.0]` |

**What guarantees correct invocation? Nothing, today.** That is the whole content of the grade. And
RG-3 §1.5 has already shown the specific way this fails silently: `-td` is a *boolean* display flag, so
a pinning flag that reads correctly does nothing and the run proceeds against a different corpus while
looking pinned in the command line, the log and the report.

**A rate flag can fail the same way, and the consequence is worse.** A mis-pinned corpus produces the
wrong findings; a no-op rate flag produces a client outage while the ledger records `rate_limit: 5`.
So the design consequence is direct: **`verify_pins.py` V1 — the flag-surface-and-arity assertion —
must cover the rate, concurrency and timeout flags specifically, and a scan whose rate flags fail V1
must refuse to start**, not warn. V1 was described in RG-3 as "a nicety that happens to catch this
specific bug". For the flags that carry the load ceiling it is not a nicety.

### 2.4 D — the gateway

`rg2-containment.md` §1.1 layer 5 is the only boundary in the stack: nftables default-deny plus a
CONNECT proxy on `rg-gw`, a separate VM the workload has no principal on. If a rate ceiling can live
there, it is enforced by a principal the workload cannot become — the same argument that makes egress
filtering the only real scope control.

**It can, partially. Here is exactly how much.**

**What nftables can enforce.** Named dynamic sets (meters) support `limit rate over` with a
concatenated key, e.g. `meter scanrate { ip daddr . tcp dport limit rate over 20/second } drop`, keyed
per destination, evaluated on `ct state new`
([nftables wiki — Meters](https://wiki.nftables.org/wiki-nftables/index.php/Meters),
[Rate limiting matchings](https://wiki.nftables.org/wiki-nftables/index.php/Rate_limiting_matchings)).
`limit rate … bytes/second` and `quota` give a byte ceiling and a cumulative byte budget.
`[VERIFY]` that the packaged nftables on the `rg-gw` build supports dynamic-set meters with a
concatenated key — this is the same class of open item as `rg2-containment.md` §11 item 6.

**What it therefore measures: new connections per second, and bytes. Not requests.** HTTP keep-alive
and HTTP/2 multiplexing put many requests on one connection, and nuclei reuses connections. A tool
issuing 1,500 requests down a handful of connections is, at the packet filter, a handful of
`ct state new` events. **A connection-rate limit does not bound a runaway scanner.**

**And the proxy cannot close the gap.** `rg2-containment.md` §3.5 mandates the CONNECT proxy with
**no TLS interception** — and that decision is correct for a stronger reason than convenience:
interception would write the operator's API key into a proxy log. But a CONNECT proxy without
interception sees one `CONNECT host:443` and a byte count. It cannot count HTTP requests inside the
tunnel. Squid's delay pools do not help either: they limit **bandwidth in bytes per second, not
request rate** ([Squid — DelayPools](https://wiki.squid-cache.org/Features/DelayPools)).

> **Request-rate enforcement outside the workload is unavailable by construction, unless the design
> accepts TLS interception. It should not.** This is the load-bearing finding of §2. The gateway is a
> boundary over connections, bytes and time — and those are useful — but the variable the fuzz budget
> is written in cannot be enforced there at all.

**What it costs, and what it breaks.** The rule is generated per engagement from `scope.yaml`
alongside the destination rules that already have to be generated (`rg2-containment.md` §9 step 4), so
the marginal cost is a few lines in an existing generator. What it breaks is subtler and is the reason
this must be designed carefully rather than turned on:

- **Dropping over-rate packets corrupts the finding.** A tool that meets a drop sees connect timeouts
  and retries, and RedGold's own gateway then looks exactly like the client's rate limiter. The single
  most likely outcome of a badly-set gateway limit is a **false "rate limiting is present" finding** —
  a fabricated result about the very control this framework exists to test.
- **A legitimate slow scan and a runaway are distinguished by rate, not by duration.** A profile at
  5 rps and a runaway at 150 rps differ by 30×, so a threshold set well above the profile separates
  them cleanly. What the gateway *cannot* distinguish is a long legitimate scan from a long runaway —
  duration is bounded by the wrapper and by the testing window, not here.

**Therefore the gateway's rate rule is a runaway threshold, never the operating point.** Set it at a
declared multiple of the engagement's authorised rate (§4 proposes 4×), log every hit at
`event_type: "egress.ratelimit"` in the §9.11 envelope, and **treat any run that touches it as an
invalid run** — its findings are quarantined, not reported — because from inside the guest a gateway
drop is indistinguishable from the target throttling. That rule is what keeps a safety control from
becoming a source of fabricated findings.

**Grade: BOUNDARY** for connection rate, byte volume and time-of-day, all of which are real. **Not a
control at all** for request rate.

### 2.5 E — post-hoc detection from the ledger

RG-3 §5.4's `FUZZ_BUDGET_EXCEEDED` generalises: every wrapper run writes `scan.plan` before firing and
`scan.result` after, the result carries the actual dispatched count read from the tool's own evidence
store, and a run over its declared budget raises a blocker.

**What it buys, and it is more than it sounds.** It makes an overrun *undeniable* — the same thing
`rate_probe.sh`'s log-before-firing rule buys, applied to a tool that counts for itself. It gives the
report a real number instead of an estimate. It feeds the per-engagement account in §3.4. And a halt on
detection stops the *next* scan, which in a multi-phase engagement is most of them.

**What it does not buy.** The 1,500 requests are already sent. And the workload writes this ledger, so
an escaped or manipulated workload can forge it (`rg2-containment.md` §5.6). It is evidence, not proof.

**Grade: Detection.** Which is exactly what RG-3 §5.4 already called it, and that honesty should
survive this document rather than being upgraded by proximity to the other layers.

---

## 3. The recommended design

**Adopt RG-3 §5.5's wrapper proposal, with three additions it does not make**: the wrapper must carry
its own boundary check (§2.2), the rate flags must be verified at runtime rather than declared (§2.3),
and the wall-clock problem must be solved with a per-engagement account rather than a per-run timeout
(§3.4). The gateway rule is built as a runaway threshold (§2.4), not as the control.

The shape is `rate_probe.sh`'s, generalised. That script's guarantees are the specification:

> counts dispatched requests, never iterations · a hard cap that can never exceed `scope.yaml`'s ·
> stops at the first `429`/`Retry-After` · refuses concurrency · logs its plan **before** the first
> request · refuses to run without a Gate-1 reference

Four of those six transfer directly. Two cannot, and saying which is the difference between a design
and a wish: **a wrapper around a tool that loops internally cannot count dispatched requests in-band,
and cannot stop at the first `429`.** The tool decides both. What the wrapper can do is *declare* the
ceiling, *enforce* the time, *assert* the flags, and *count afterwards*.

### 3.1 `scripts/scan_run.py` — the one sanctioned path

One invocation form for every tier-2/3 network tool RG-3 pins:

```
scan_run.py --profile web-baseline-v1 --gate-ref G-003 --target https://api.acme.example \
            [--root DIR] [--max-seconds N] [--rate N]
```

Ordered responsibilities. The order is load-bearing — everything that can refuse, refuses before
anything is logged, and everything is logged before anything is sent.

| # | Step | Rule |
|---|---|---|
| 1 | **Gate reference** | `gate_cli.py validate --gate-ref` must pass: approved, current, `plan_hash`/`scope_hash` still matching. Same rule and same code path as `rate_probe.sh`. No gate, no scan |
| 2 | **Profile load** | Budgets from `profiles/<name>.yaml` §2.5. A profile that names no `budgets` block is a refusal, not a default |
| 3 | **Effective ceiling** | `rate = min(profile.rate_limit_per_second, scope.constraints.rate.requests_per_second)`; `concurrency = min(profile, scope, 1 unless the profile explicitly raises it)`; `max_seconds = min(profile.wall_clock_seconds, seconds remaining in the testing window, remaining engagement account §3.4)`. `--rate`/`--max-seconds` **may lower and can never raise** — `rate_probe.sh`'s rule, verbatim |
| 4 | **Boundary check, per target** | `scope_guard.check_url(root, target, tier)`. **Mandatory**, because step 8 puts this script in `FRAMEWORK_SCRIPTS` and the parser will stop looking at the command line (§2.2). One target per invocation; `target_discipline.forbidden_flags` (RG-3 §2.6) is enforced by the wrapper refusing to pass a target-list flag at all |
| 5 | **Flag-surface assertion** | `verify_pins.py` V1 over **the rate, concurrency and timeout flags specifically**, plus V2/V3. A rate flag that has changed arity, been renamed or become boolean fails here and the scan refuses to start (§2.3) |
| 6 | **Plan row, before firing** | `scan.plan` to `ledger/activity.jsonl`: gate ref, profile + version, target, tier, effective rate, concurrency, `max_seconds`, **the derived arithmetic ceiling `rate × max_seconds`**, and the declared `requests_per_target`. Both numbers, because they differ and §5 requires the report to state the loose one |
| 7 | **Run under a process timeout** | `SIGTERM` at `max_seconds`, `SIGKILL` at `max_seconds + 10`. The kill is the only hard bound in the guest, and it is the property that makes a scan *stoppable* |
| 8 | **Count afterwards** | Read the actual dispatched-request count from the tool's own store — nuclei `-srd`, ZAP's history, nmap's XML — and write `scan.result`: actual, declared, elapsed, exit reason (`completed` \| `timeout` \| `killed` \| `refused`). Over budget → `SCAN_BUDGET_EXCEEDED` blocker. No count available → `reason_code: "uncounted"`, never a guess |
| 9 | **Debit the account** | §3.4 |

`SANCTIONED` in `no_handrolled_loops.py` becomes a table — `rate_probe.sh`, `scan_run.py`, and nothing
else without a test — and a new deny fires when a `TIER2_TOOLS ∪ TIER3_TOOLS ∪ SCANNER_TOOLS` token
appears outside a sanctioned invocation. The deny message must name the exact `scan_run.py` line that
would have been correct. `scope_guard.py`'s own comment is the reason: *"A control that blocks the safe
path pushes the operator toward the unsafe one."*

### 3.2 Per-tool invocation — and why none of the six break

The test of this design is RG-3's pinned set. A control that makes scanning unusable gets disabled,
which is worse than none.

| Tool | What the wrapper sets | Does it break anything? |
|---|---|---|
| **nuclei** | `-rl <effective>` `-rld 1s` `-c 1` `-bs 1` `-timeout <n>` `-mhe <profile>` `-duc`, plus RG-3's selection/exclusion flags and `-srd <dir>` for the count | No. RG-3 §2.5 already specifies `-c 1 -bs 1` for determinism. The wrapper's contribution is that `-rl` is now `min(profile, scope)` instead of the **150/s default** |
| **nmap** | `--max-rate <effective>` `-T2` `--host-timeout` `--script-timeout` `[VERIFY]`, one host per invocation | No — but §2.3 stands: `--max-rate` does not bound NSE traffic. NSE load is bounded here by *script count and one target*, and the profile must say so rather than implying the rate flag covers it |
| **testssl.sh** | `--mode serial`, `MAX_PARALLEL=1`, `--connect-timeout`/`--openssl-timeout`, one host per invocation, wall clock from the wrapper | No. There is no rate option to set; the bound is the fixed test list and the timeout. Recorded in the profile as `rate_control: none_available`, not left blank |
| **ZAP** | Network add-on Rate Limit rule with `requestsPerSecond = effective`, `groupBy: host`, configured via the API **before** the spider or active scan starts `[VERIFY exact API parameter spellings against the pinned version]` | No, and this is the tool the design fits best: the limit is applied by ZAP's own proxy to everything it emits |
| **trufflehog** | Verification explicitly disabled `[VERIFY flag spelling at 3.97.0]` | No. Local scanner; RG-3 §6.2 already defaults verification off. It is in the wrapper only so the assertion is machine-checked rather than assumed |
| **gitleaks** | — | No. Local, no network |

Two rules that keep this from decaying:

1. **`rate_control: none_available` is a required, explicit profile value.** A tool with no rate flag
   must say so in the profile, so a reviewer can tell "bounded by construction" from "nobody wired it
   up". A blank field reads as coverage.
2. **One target per invocation, always.** It is already RG-3 §2.6's `one_target_per_invocation`, and it
   is what makes per-host and global rate semantics equivalent — which is why the unresolved
   `-per-host-rate-limit` semantics in §2.3 do not matter here.

### 3.3 The gateway rule

Generated with the destination rules, from the same `scope.yaml` block:

```
# emitted by the ruleset generator on the control tier, per engagement
meter rg_scanrate { ip daddr . tcp dport limit rate over <4 × authorised_rps>/second } \
    log group 2 prefix "rg-ratelimit " drop
```

Three properties, and each is a constraint rather than a nicety:

- **It is a runaway threshold, not the operating point** (§2.4). At 4× the authorised rate it is never
  reached by a correctly-invoked scan, so reaching it is always an anomaly.
- **Every hit is logged on the gateway** as `event_type: "egress.ratelimit"` in the §9.11 envelope and
  joined by `rg-reconcile` exactly like `egress.block`. Guard-side `scan.plan` says 5 rps; gateway-side
  says 20/s exceeded; that pair is an incident with the same standing as an `egress.mismatch`.
- **Any run that touches it is quarantined, not reported.** From inside the guest a gateway drop looks
  like target throttling, so the run's rate-limiting findings are unsound by construction.

Add a byte `quota` per engagement in the same ruleset if the client's constraint is bandwidth or a
metered egress bill. That is the one part of this whole design that is enforced outside the blast
radius **and** measured in the unit the client actually cares about.

### 3.4 The wall-clock problem, and what happens when a scan needs to run long

RG-3 §5.4 is right that the only real in-band ceiling is `rate × wall_clock`. That leaves the obvious
question: what bounds the wall clock, and what happens when a legitimate scan needs more of it?

**Three bounds, in order, and none of them is "a bigger timeout".**

1. **Per invocation** — `profile.wall_clock_seconds`, enforced by the wrapper's `SIGTERM`/`SIGKILL`.
   Hard, in-guest, and the only thing that makes a running scan stoppable.
2. **Per engagement — the request account.** A cumulative budget in `scope.yaml` (§4), debited by every
   `scan.result` and every `rate_probe` run, held in `ledger/activity.jsonl` and summed by the wrapper
   before each run. **This is the number that comes from the client**, and it is what a per-run timeout
   cannot give you: ten well-behaved 900-second scans are still ten times the load of one.
3. **The testing window.** `scope_guard.py` evaluates `constraints.testing_window` per *tool call* — so
   a scan started at 16:55 inside a `09:00-17:00` window keeps running until 17:10 with nothing
   checking. The wrapper closes that: `max_seconds` is clamped to the seconds remaining in the window,
   and a run refuses to start if fewer than a floor (say 120 s) remain. At the gateway, prefer a
   **scheduled ruleset swap** at window close over nftables time-based matching, which
   `rg2-containment.md` §11 item 6 already lists as `[VERIFY]`.

**When a scan legitimately needs to run long** — a large surface, a slow target, a 5 rps ceiling that
makes 1,500 requests take five minutes at best and much longer at worst — the answer is **not** a
raised timeout. It is:

- **Split it.** N bounded invocations against a partitioned input set, each debiting the account. The
  input set is already a committed artifact (`surface.jsonl`, RG-3 §5.4 bound 1), so partitioning it is
  mechanical and each partition is independently reproducible.
- **Resume, do not extend.** A `timeout` exit is a normal outcome, not a failure. `scan.result` records
  `exit: timeout` with the partition covered, and the coverage section of the report says which
  partition was not reached — RG-1's `not_attempted` discipline, applied to time.
- **Exhausting the account is a Gate 2 deviation, not a retry.** The agent halts and the operator
  either amends the budget *with the client* or stops. A budget that an agent can extend by asking
  itself is not a budget.

The cost is real and should be stated: an engagement with a small authorised rate and a large surface
will not finish, and the report will say so in the coverage section. That is the correct outcome. The
alternative — quietly running until done — is the 20-vs-10 incident with a longer time base.

---

## 4. The authorisation link — from the client's answer to every control point

A cap RedGold picked for itself is a courtesy. A cap the client agreed to is an authorisation limit,
and §1 item 2 is why the difference is legal rather than aesthetic.

### 4.1 The problem with E2 as it stands

RG-4 §3.5 E2 is:

> "Is it acceptable for us to send a burst of rapid requests to check that your system limits them?
> This is how we test whether someone can brute-force your login. It may set off alerts, and on a
> small server it may slow the site for a minute."

It is a good question and it produces `permit.rate_testing: true|false`. **A boolean cannot become a
number honestly.** Deriving "5 requests per second" from "yes" and then telling a client they
authorised 5 rps would be fabricating an authorisation — the same category of error as hard rule 1.

Two options were considered. **Asking the client for a number directly is rejected** for RG-4 §3.5's
own stated reason: a client who types "20" has not consented to anything, because they were not told
what 20 does to them. That is the "what blast-radius tier do you authorise?" mistake in different
units.

### 4.2 E2a — a consequence question, asked only when E2 is yes

| # | Field | R/O | Question |
|---|---|---|---|
| E2a | `rate.capacity_band` | R when E2 = yes | "How much extra traffic can your site take without anyone noticing? Pick the closest: **(a)** it's a small server, or we honestly don't know — go gently; **(b)** it's behind Cloudflare, Vercel or similar and handles normal traffic without trouble; **(c)** we've load-tested it and can give you the figure we know it holds; **(d)** this is a dev or staging copy that nobody real uses — go as hard as you need." |

The bands map to **RedGold defaults**, and the engagement document states the resulting numbers back
to the client in plain units so the countersignature is a signature on the numbers:

> "We will send no more than **N requests per second**, no more than **one at a time**, for no longer
> than **T minutes** in any single run, and no more than **B requests in total** across the whole
> engagement."

| Band | `requests_per_second` | `concurrency` | `max_scan_seconds` | `engagement_request_budget` |
|---|---|---|---|---|
| (a) small / unknown | 2 | 1 | 600 | 5,000 |
| (b) CDN-fronted, healthy | 5 | 1 | 900 | 20,000 |
| (c) client-supplied figure | `min(client figure, 20)` | 1 | 900 | 20,000 |
| (d) dev/staging copy | 20 | 1 | 1800 | 100,000 |

**These four rows are RedGold's engineering judgement, not measurements, and the format must say so.**
They are starting values chosen to be conservative; there is no measured basis for them and none is
claimed. Band (c) is capped because a client's load-test figure describes their *capacity*, not their
*consent to have it consumed*, and because a figure remembered in a questionnaire is not a figure
RedGold may treat as a ceiling. Band (d) still has a ceiling: RG-2 §7's matrix permits more against a
dev copy, not everything.

Two refusals belong in `rg4_ingest.py` and in `scope.parse()`:

- `rate` present with `permit.rate_testing: false` → contradiction, routed to RG-4 §7.2 rather than
  resolved by the skill.
- `rate` present with no `source`/`derived_by` → refuse. A number with no provenance is exactly the
  kind of authorisation this document exists to make real.

### 4.3 Where the number lives

`scope.py` already has `Constraints.max_requests_per_burst` (a positive integer, validated, defaulting
to None, used by `rate_probe.sh` as its hard cap). Extend `constraints` rather than inventing a second
home, so there is one authority:

```yaml
constraints:
  no_destructive: true
  testing_window: "weekdays 09:00-17:00 AEST"
  max_requests_per_burst: 10          # UNCHANGED MEANING — rate_probe.sh's per-burst cap
  rate:
    requests_per_second: 5
    concurrency: 1
    max_scan_seconds: 900
    engagement_request_budget: 20000
    source: "RG-4 E2a band (b) — client-declared capacity band"
    derived_by: "rg4/1 defaults table, docs/specs/rg2-rate-control.md §4.2"
```

`max_requests_per_burst` keeps its current meaning and its current consumer. The new block governs
tools that loop internally. They are different questions — "how many requests in one deliberate probe"
versus "how fast and for how long may a scanner run" — and collapsing them would silently change
`rate_probe.sh`'s cap.

`scope.parse()` validation, matching the existing style: positive integers only, `bool` rejected
explicitly (it is an `int` subclass, and `requests_per_second: true` is a mistake, not a rate),
`source` and `derived_by` both required when the block is present.

### 4.4 How it reaches every control point

| Consumer | How it reads the number | Direction it may move it |
|---|---|---|
| `rate_probe.sh` | `constraints.max_requests_per_burst` (already), plus `rate.requests_per_second` as an inter-request delay | `--max` may lower, never raise (already enforced) |
| `scan_run.py` | `min(profile budget, scope rate block)` at step 3 | `--rate`/`--max-seconds` may lower, never raise |
| `no_handrolled_loops.py` | **Reads no number.** It needs only the wrapper table | n/a |
| The nftables generator (control tier) | `4 × rate.requests_per_second` as the runaway threshold; `engagement_request_budget` informs the byte `quota` if one is set | Generated outside the guest; the workload cannot argue with it |
| `report.py` methodology | The authorised numbers, the derived `rate × wall_clock` ceiling, **and the actual counts** from `scan.result` | Reporting only |
| `verify_controls.py` | Asserts the same number appears at every consumer above | A cap living in four files drifts; this is the test that catches it |

The last row is not optional. `rate_probe.sh` already demonstrates the failure it prevents: the burst
cap is authoritative only because one script reads it and refuses to exceed it. Four readers with no
cross-check is four caps.

---

## 5. Honest limits

Written in the order `rg2-containment.md` §10 uses: what is not true, first.

1. **Nothing in this design is a boundary over request rate. Nothing can be.** §2.4 is the finding:
   the gateway enforces connection rate, byte volume and time-of-day; the variable the fuzz budget is
   written in is invisible outside the TLS tunnel, and RG-2 correctly refuses TLS interception. **Even
   after RG-2 ships in full, request-volume control remains in-guest and cooperative.** This is the
   one control class in the framework that gets no boundary upgrade, and it should be stated in those
   words rather than allowed to inherit the gateway's credibility by adjacency.

2. **Until RG-2 step 3 ships, this is detection plus cooperation, and that is all.** The permitted
   sentence today:

   > "Request volume is bounded by RedGold's tooling before each run, and the actual number of
   > requests sent is recorded and reported. The bound depends on the tooling being used as intended;
   > it is not enforced outside the testing environment."

   Not *"cannot exceed"*. Not *"capped"* without the second clause.

3. **`rate × wall_clock` remains the honest ceiling, and it is loose.** At 5 rps and 900 seconds the
   arithmetic ceiling is 4,500 requests where the declared budget is 1,500 — a factor of three. Both
   numbers go in the plan row and both go in the report. RG-3 §5.4 called the budget a detection; that
   is unchanged here, and the wrapper does not upgrade it by owning it.

4. **The wrapper requirement rests on a parser §9.3.1 already disclaims.** A renamed binary, a
   previously-copied binary, or a tool nobody enumerated walks past both hooks. §2.2's table lists the
   bypasses that are caught and the ones that are not; the ones that are not are not hypothetical.

5. **A no-op flag is the failure mode most likely to actually happen.** RG-3 §1.5's `-td` case is not
   an anecdote about one flag; it is the class. V1 flag-surface verification over the rate flags
   reduces it and does not eliminate it — V1 checks that a flag exists with the expected arity, not
   that the engine honours it. The only assertion that closes the loop is the post-run count, which is
   §2.5's detection, arriving after the traffic.

6. **Request count is a poor proxy for load, and nothing here fixes that.** One request to an
   unindexed export endpoint can cost the target more than 1,500 fuzz requests. A rate ceiling does
   nothing about an accidental denial of service through a single expensive query, and no counter
   RedGold can build would see it coming. The mitigations are the ones already in the framework —
   tier ceilings, the plan, the named emergency contact — and they are procedural.

7. **Harm at a permitted destination is outside containment entirely.** `rg2-containment.md` §10.1
   item 3 says so, and this document is that class in full. A client who hears "a firewall on a
   separate machine" and concludes their production database is safe from an overrun has misread it,
   and §10.3's guidance to pre-empt that misreading *in the same breath* applies here word for word.

8. **The client's number is declared capacity, not measured capacity.** For bands (a) and (b) it is
   RedGold's default wearing the client's consent. That is better than an undeclared default and worse
   than a measurement, and the engagement document should carry the numbers plainly enough that a
   client who knows their system can push back on them.

9. **A gateway rate limit can manufacture a finding.** §3.3's quarantine rule is a mitigation, not a
   guarantee: it depends on the reconciler seeing the `egress.ratelimit` row and on the operator
   acting on it. Until `rg-reconcile` has run clean on a real engagement (`rg2-containment.md` §10.3
   precondition 5), treat the gateway rate rule as report-only, exactly as §5.5 requires of the halt
   behaviour.

10. **The `-i`/`-r` false positives in `no_handrolled_loops.py` (§2.1) are live today.** A control that
    denies `curl -i` is a control the operator learns to route around, and every hour it stays that way
    is an hour the whole hook is worth less than the file suggests.

### What may be said to a client, once §3 is built

> "Before each scan we write down the rate, the concurrency and the time limit we will run under,
> and where those numbers come from in your authorisation. Every scan runs under a hard time limit
> and is stopped when it expires. Afterwards we count what was actually sent and report it against
> what we said. If a run exceeds its budget, the engagement stops and you hear about it."

Every clause maps to a mechanism in §3: the plan row, the `SIGKILL`, the post-run count, the blocker.
None of it claims enforcement outside the workload, because there is none to claim.

---

## Sources

- nuclei `v3.11.1` usage output — rate, concurrency, bulk-size, timeout and update flags with defaults
  ([README at the tag](https://raw.githubusercontent.com/projectdiscovery/nuclei/v3.11.1/README.md))
- nmap reference guide — timing and performance options; `--max-rate`/`--min-rate` are global and
  affect port scanning and host discovery ([man-performance](https://nmap.org/book/man-performance.html))
- testssl.sh 3.2 manual — no rate or connection-rate option; `--mode serial`, `MAX_PARALLEL`, timeout
  variables ([testssl.1.md](https://raw.githubusercontent.com/testssl/testssl.sh/3.2/doc/testssl.1.md))
- ZAP Network add-on — Rate Limit options, `requestsPerSecond`, `groupBy: rule|host`
  ([zaproxy.org](https://www.zaproxy.org/docs/desktop/addons/network/options/ratelimit/))
- nftables wiki — [Meters](https://wiki.nftables.org/wiki-nftables/index.php/Meters),
  [Rate limiting matchings](https://wiki.nftables.org/wiki-nftables/index.php/Rate_limiting_matchings)
- Squid — [DelayPools](https://wiki.squid-cache.org/Features/DelayPools) (bandwidth, not request rate)

Repo references at the time of writing: `scripts/no_handrolled_loops.py`, `scripts/rate_probe.sh`,
`scripts/scope_guard.py` (`FRAMEWORK_SCRIPTS`, `TIER2_TOOLS`, `check_url`), `scripts/scope.py`
(`Constraints`, `_parse_constraints`); `docs/specs/redgold/07-enforcement.md` §9.3.1, §9.4;
`docs/specs/redgold/04-modes-and-tiers.md` §6; `docs/specs/rg3-test-libraries.md` §1.5, §2.5, §2.6,
§5.4, §5.5; `docs/specs/rg2-containment.md` §1.1, §1.3, §3.5, §5.4, §7, §10;
`docs/specs/rg4-scoping-questionnaire.md` §3.5, §6.4, §7.2.
