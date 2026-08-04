---
title: The enforcement layer
question: What is mechanically prevented, how, and what are the limits of that claim?
sections: [9]
spec: RedGold design
status: draft
date: 2026-08-03
---

## 9. The enforcement layer

### 9.1 Where it lives — and why it cannot live in the plugin

**Plugin-shipped agents cannot set `hooks`, `mcpServers`, or `permissionMode`; those fields are
silently ignored for security.** Enforcement therefore cannot ride along in RedGold's agent cards.

Instead, `/rg:new` writes the engagement's `.claude/settings.json`, wiring hooks that point at
scripts inside the installed plugin via `${CLAUDE_PLUGIN_ROOT}`. The payoff is that **hooks fire for
subagent tool calls unconditionally**, carrying `agent_id` and `agent_type` on stdin. A
project-level hook therefore binds every RedGold agent, and a subagent cannot remove it — it can
only add its own on top.

A CI check in the RedGold repo fails the build if any Bash-capable agent ships without scope-guard
wiring. The mechanism is lifted from `0xSteph/pentest-ai-agents`' `validate.yml`: parse each agent
card's YAML frontmatter, and **if `tools:` grants Bash, require a fixed marker string** proving the
scope block is present — otherwise emit a GitHub error annotation and fail. The same job validates
that every agent card has `name`, `description`, `tools` and `model`, and shellchecks every script.

The lesson is that the invariant *"any agent that can run commands carries the safety block"* is
machine-checkable at PR time. Convention would not survive a tired operator adding an agent at
11pm.

### 9.2 Hook inventory

| # | Event | Matcher | Script | Encoded lesson |
|---|---|---|---|---|
| 1 | `PreToolUse` | `Bash\|WebFetch\|mcp__.*` | `scope_guard.py` | Prose scope enforcement has a body count |
| 2 | `PreToolUse` | `Bash` (`if: Bash(*)`) | `no_handrolled_loops.py` | The 20-vs-10 request overrun |
| 3 | `PreToolUse` | `Bash\|WebFetch` | `canary_check.py` | 15 undeletable rows left in a client's live DB |
| 4 | `PostToolUse` | `Bash\|WebFetch\|mcp__.*` | `redact.py` | Secrets must not enter the transcript |
| 5 | `SubagentStop` | `*` | `validate_findings.py` | The validator that was never built |
| 6 | `SessionStart` | — | `session_start.py` | Context loss across compaction |
| 7 | `Stop` | — | `cleanup_gate.py` | Engagement closed with outstanding cleanup debt |

### 9.3 Hook 1 — `scope_guard.py`

The core control. On every network-capable tool call it:

1. Reads `scope.yaml` and `assets/register.jsonl`.
2. Extracts the target host from `tool_input.command` (Bash) or `tool_input.url` (WebFetch), or the
   server-defined target field (MCP).
3. **Decodes base64/base32 in the command** before matching, to catch obfuscated targets.
4. Denies if the host matches any `out_of_scope` entry.
5. Denies if the host is not a `CONFIRMED` register row mapping to an `in_scope` entry.
6. Classifies the command's blast-radius tier and denies if it exceeds `ceiling`.
7. Denies if outside `constraints.testing_window`.
8. **Fails closed**: if the host cannot be determined, it denies.

#### 9.3.1 What this control does and does not do — read before quoting it to a client

`scope_guard.py` is **defence-in-depth against sloppy scope drift. It is not a security boundary.**

Extracting "what network destination will this command reach" from an arbitrary shell string is not
a solved parsing problem — Bash is Turing-complete, and the target can be absent from the string
entirely:

| Evasion | Why the guard misses it |
|---|---|
| `H=$(echo target); curl https://$H` | No literal host in the command |
| `echo 'curl https://x' > /tmp/a.sh && bash /tmp/a.sh` | The inspected call is `bash /tmp/a.sh` |
| `nuclei -l targets.txt`, `nmap -iL hosts.txt` | Targets live in a file the hook never opens |
| `curl --resolve`, `--connect-to`, `/etc/hosts`, a proxy | The literal name is disconnected from the IP contacted |
| A 302 redirect | The destination is chosen by the *target*, after the check |
| Hex, ROT13, URL-encoding, `python3 -c` | Decoding base64/base32 while ignoring every other encoding is whack-a-mole |
| Arbitrary MCP servers | Each has its own schema; there is no canonical "target field" |

The fail-closed rule in step 8 is the honest admission of this: a check that must deny on
uncertainty is a heuristic, not a boundary.

**The claim RedGold makes to a client is therefore precise:**

> "The tooling mechanically refuses out-of-scope targets in the ordinary case, and refuses outright
> when it cannot determine what it is about to touch. It is one layer among several — alongside a
> signed scope, a capped ceiling, per-escalation approval, and an audit log — not a guarantee that
> the agent is incapable of reaching anything else."

Overstating this would be worse than having no control. A client asking *"how do you guarantee the
agent can't touch our other systems"* deserves the true answer, and under the Australian Criminal
Code Part 10.7 (s478.1, unauthorised access) the operator's own exposure turns on authorization
scope actually holding — a control marketed as absolute that isn't is a liability, not an asset.

**Consequences for the design:** commands with variable indirection, file-based target lists, or
calls to MCP servers without a registered target-field mapping are **denied**, not guessed at. That
is a deliberate friction cost, accepted because the alternative is false confidence.

Denial uses the documented JSON path on exit 0, so the model receives a structured, actionable
reason rather than a raw stderr string:

```json
{
  "hookSpecificOutput": {
    "hookEventName": "PreToolUse",
    "permissionDecision": "deny",
    "permissionDecisionReason": "Host 'api.other.example' is not a CONFIRMED in-scope asset. It appears in assets/candidates.jsonl with attribution_confidence=LOW. Promote it via /rg:scope with client confirmation before testing."
  }
}
```

An `if: "Bash(curl *)"`-style prefilter list (curl, wget, nc, nmap, ffuf, gobuster, nuclei, sqlmap,
httpx, subfinder, amass) keeps the script off the hot path for non-network Bash calls. The prefilter
is an optimisation only; the real check is always done in the script body, because `if` patterns
match unreliably inside `$(...)` substitution.

#### 9.3.2 Checking against the approved plan

Steps 1–8 above enforce *scope*. They do not enforce *the plan*, and an earlier draft claimed Gate 2
("deviation stops and asks") was enforcement when nothing enforced it — a new in-scope asset
discovered mid-phase would have sailed straight through. That is the precise failure P1 exists to
prevent, reproduced inside RedGold's own flagship gate.

So `scope_guard.py` additionally loads `ledger/plan.json` (§7.6) and, for any action at tier ≥ 1:

9.  **Asset named?** The target must appear in the current phase's `assets` list. A CONFIRMED,
    in-scope, under-ceiling asset that the plan does not name is a **deviation → deny**.
10. **Test class authorised?** The action's class must appear in the phase's `test_classes`.
11. **Write endpoint named and under budget?** A write must match a `write_endpoints` entry by
    method and route template, and `ledger/cleanup.jsonl` must show fewer than `max_writes` writes
    already made against it.
12. **Live confirmation pending?** If the class appears in `live_confirm`, deny with a reason
    instructing the agent to raise a `decision` blocker.
13. **Plan still valid?** `plan_hash` and `scope_hash` must match the approved gate record. An
    edited plan or amended scope voids the approval until re-approved.

Denials at steps 9–12 carry `deviation` in the reason so the agent knows to record a blocker rather
than retry. **Deviation is now a denied tool call, not a request that the agent may decline to
make.**

The cost is real: the plan must be specific enough to be checkable, which means Gate 1 takes longer
and mid-engagement re-planning is a genuine interruption. That is the intended trade — a plan vague
enough to never trigger a deviation is a plan that authorises nothing.

### 9.4 Hooks 2 and 3 — the two prior-engagement incidents, as exit codes

**`no_handrolled_loops.py`** denies any Bash command combining an iteration construct
(`for`, `while`, `xargs -P`, `seq |`, `repeat`) with a request tool. Bounded bursts must go through
`scripts/rate_probe.sh`, which owns its own counter, stops at the first `429`/`Retry-After`, refuses
concurrency, and logs the plan to `ledger/activity.jsonl` before firing. In the prior engagement an
agent hand-rolled a loop that issued **20 requests against a ≤10 authorized cap**; the fix was
written into a design document *after* the fact and never enforced.

**`canary_check.py`** denies any state-mutating request unless `ledger/cleanup.jsonl` already
records, for that endpoint, a canary write that was subsequently **verified deleted**. The rule is
*create canary → prove the delete path works → only then proceed*. The prior engagement left 15
undeletable rows in one table and 6 orphaned rows in another, in a live client database, still
outstanding as action items at handoff, because the automation could create test data faster than
it could guarantee removing it.

Every write is appended to `ledger/cleanup.jsonl` with state `pending | deleted | orphaned`.

**Operation identity.** A canary is keyed by `{method, route_template, operation}` — not by literal
URL. `route_template` normalises path parameters (`/users/{id}/comments`), and `operation` carries
the logical mutation name where one URL serves many: a GraphQL endpoint is one route but
`createComment` and `deleteAccount` are different operations, and a canary proven for one must never
unblock the other. Anything RedGold cannot resolve to a distinct operation is denied.

#### 9.4.1 Write authorisation — canary, pre-approval, or neither

A canary alone dead-ends on this framework's core client segment. Supabase RLS is routinely and
*correctly* configured so an anonymous user cannot delete rows they inserted — which is exactly the
prior-engagement incident. If a passing canary were the only route to a write, tier-2 testing that §6 says
an audit *must* include would be permanently unreachable on the most common target stack.

So a write proceeds if **either** condition holds:

**(a) Canary-proven.** A canary write to this operation was created and verified deleted through
some available path. The strongest case: cleanup is demonstrated, not assumed.

**(b) Client pre-approved.** The client has approved writes to this operation class in
`ledger/plan.json`, accepting in advance that residue may need manual removal. This is a normal
thing for a client to agree to, because §6.1's conspicuous test data makes the residue trivially
identifiable and removable, and the cleanup appendix hands them the exact query.

`canary_check.py` denies only when **neither** holds — an unapproved write to an operation with no
proven delete path. That is still the prior-engagement failure, and it stays blocked.

**A cleanup credential is a nice-to-have, not a prerequisite.** Where the client can supply one — a
service-role key, an admin session, or a standing offer to run a deletion — record it in
`scope.yaml` under `cleanup_credential`; it upgrades path (b) to path (a) and removes the residue
question entirely. Where they cannot, the engagement proceeds under pre-approval and the report says
what was left behind.

What must never happen is the write going ahead on an agent's judgement that cleanup will probably
work. Both paths route through a human decision recorded before the fact — the canary through
evidence, pre-approval through the plan.

One observation worth carrying into the report either way: an application whose own operators cannot
delete test data has a data-lifecycle problem. That is a `posture` finding in its own right.

### 9.5 Hook 4 — output redaction

`redact.py` runs on `PostToolUse` and rewrites tool output through `hookSpecificOutput.
updatedToolOutput` before the model sees it, stripping credential-shaped strings (JWTs, API key
prefixes, `service_role` keys, bearer tokens, private keys). This limits blast radius if a response
body contains secrets and keeps them out of the transcript on disk.

### 9.6 Hook 5 — findings validation

`validate_findings.py` runs on `SubagentStop`. **Exit 2 on `SubagentStop` prevents the subagent from
stopping — it does not restart it.** The script must therefore emit, on stderr, a specific and
actionable correction instruction ("record F-007 is missing evidence_ptr; capture the request/
response to evidence/F-007-*.http, then finish"), because the agent continues from where it is
rather than re-running the phase. A naive "invalid, try again" message risks an agent that thrashes
against the same broken output instead of correcting it, so the script also tracks attempts per
subagent and escalates to a `kind: validation` row in `ledger/blockers.jsonl` after two failed corrections.

It blocks stopping if any findings
record: fails schema; carries an `evidence_ptr` that does not resolve to an existing file and
anchor; is `finding_class: technical` and labelled `PROVEN` without a `verified` level of `replayed`
or `executed`; is `technical` and rated above Low without verification; or carries
`verified: n/a` without being `posture` or `governance` (§10.3).

Unresolvable evidence auto-demotes the record to `SPECULATED`.

**Acceptance test:** the validator must run cleanly against the prior engagement's five existing `phase*.json`
files and correctly flag the known gaps in them. That is the honest way to prove it is not vaporware
a second time.

### 9.7 Gates

Two failure modes bracket this design. An agent that never asks is the Strix/HexStrike posture that
gets people hurt. An agent that asks before every escalation trains the operator to approve
reflexively, which is the same thing with extra steps and a worse audit trail.

The resolution is **approval at plan time, not at action time** — the operator's judgement is worth
most when deciding *what will be done*, and worth least when rubber-stamping the ninety-third
in-plan request. This is also how a human engagement actually runs: you agree the test plan, then
the tester tests.

**Gate 0 — Scope agreement (planning).** Before anything, operator and `rg-lead` work through scope
together: what the client signed, what the crown jewels are, what the register shows, what is
explicitly excluded, what the ceiling is. Output: a committed `scope.yaml`. This is the conversation
where operator attention genuinely pays.

**Gate 1 — Test plan approval.** `rg-lead` emits a plan naming, per phase: the assets to be touched,
the maximum tier, the classes of test, the endpoints expected to receive writes, and the expected
cleanup. The operator approves once. **Execution within the approved plan proceeds without further
prompting.** Recorded in `ledger/gates.jsonl` with `scope_hash` and a `plan_hash`.

**Gate 2 — Deviation.** Anything outside the approved plan stops and asks: a new asset, a higher
tier, an endpoint not named, an unexpected write. The agent appends a `kind: deviation` row to
`ledger/blockers.jsonl` and halts rather than improvising. This is where the friction belongs, because a deviation is
information — either the plan was wrong or the target is not what we thought.

**Gate 3 — Per-action, tier 3 only.** `redteam` mode. Operator present, emergency contact named,
each action approved individually. Unreachable in `posture` and `audit` because `scope_guard.py`
denies on ceiling.

A stale plan expires: if `scope.yaml` changes, `scope_hash` no longer matches and every gate
approval derived from it is void until re-approved. An amended scope cannot silently inherit an
older authorisation.

---

### 9.8 Egress containment — the layer that makes the claim true

**Motivating case.** Anthropic reviewed prior cybersecurity evaluations and found instances where an
agent was inadvertently given real internet access and **did not stop when it realised**. The
question that follows — *"even if it submitted those commands, is there any way they could run?"* —
cannot be answered by §9.3. A command parser loses to a motivated model: hex encoding, `$(...)`,
write-then-execute, a file of targets, a redirect. §9.3.1 says so plainly.

The answer is not a smarter parser. It is that **the agent's behaviour must stop being the control.**

#### The stack

| Layer | Mechanism | Stops | Strength |
|---|---|---|---|
| 1 | Model instruction (CLAUDE.md, agent cards) | Nothing reliably | Advisory |
| 2 | `scope_guard.py` PreToolUse hook | Sloppy or unintentional drift | Heuristic |
| 3 | **Host egress allowlist** | **Every packet to an unauthorised destination** | **Boundary** |
| 4 | Proxy + audit log | Nothing — but proves what happened | Detection |

**Layer 3 is the only one that supports the claim.** Default-deny egress on the engagement VM;
allow only (a) resolved IPs for CONFIRMED in-scope assets, (b) the Anthropic API endpoint, (c) an
explicit tooling allowlist. All HTTP forced through a local logging proxy. DNS restricted to a
controlled resolver so name resolution cannot be used as an exfiltration or discovery channel.

Implementation is host-level (`nftables`/`iptables` + resolver config + proxy), regenerated from
`scope.yaml` by `/rg:new`, and **outside the agent's write access** — an agent that can edit its own
firewall has no firewall.

#### What this does and does not prove `[HONEST LIMITS]`

**Does:** an out-of-scope destination is unreachable regardless of how the command was constructed,
encoded, or hidden. Obfuscation becomes irrelevant, because the parser is no longer the control
point. A redirect to an out-of-scope host fails at the socket.

**Does not:** the control plane must remain open — the agent's own API channel is permitted egress
by necessity, and a sufficiently determined agent could in principle tunnel through a permitted
channel. Scope-resolved IPs on shared infrastructure (Cloudflare, Vercel) cover other tenants at the
same address, so the allowlist is coarser than the scope. It is containment, not proof of
impossibility.

**Defensible claim — only if §9.9 holds:** *"Traffic to destinations outside the authorised scope is
blocked outside the machine the agent controls. The agent's cooperation is not required."* Stated of
a host firewall the agent can edit, this claim is false (§9.9). That is a materially stronger statement than anything §9.3 supports, and it is the one worth
making to a client.

#### Consequence for the roster

Layer 3 outranks layer 2. Where they disagree, the firewall wins and the disagreement is itself a
finding about RedGold — logged, because a `scope_guard` allow that the firewall then blocked means
the parser is wrong.

---

### 9.9 The trust boundary must be a machine boundary

**The hole.** §9.8 as first written put the egress control on the same host the agent has Bash on.
An agent with sudo can `nft flush ruleset`, rewrite `/etc/resolv.conf`, unset proxy variables, edit
`.claude/settings.json` to remove the hooks, or delete `scope_guard.py`. Every layer in §9.8's stack
then sits *inside* the blast radius of the thing it is meant to contain. **A control the agent can
edit is not a control.**

**The attack chain that makes this urgent.** A target serving crafted content — a prompt-injection
honeypot, which any adversary expecting to be scanned might deploy — reaches an agent that holds its
own keys:

1. Worker fetches an attacker-controlled HTTP response.
2. The response contains instructions.
3. The agent has privileges over its own controls.
4. The agent disables them.

§8.5's untrusted-data clause is an *instruction*, and instructions are precisely what injection
subverts. **You cannot defend a prompt with a prompt.** It mitigates accidents; it does nothing
against a deliberate adversary.

**The rule.** *Containment must be enforced outside the blast radius of the thing being contained.*

| Where the control lives | Defeated by | Verdict |
|---|---|---|
| Agent's prompt | Injection | Not a control |
| Hook script on the agent's host, agent-writable | `rm` | Not a control |
| Host firewall, agent has sudo | `nft flush` | Not a control |
| Host firewall, agent unprivileged, rules root-owned | Privilege escalation; operator social-engineered into running something | Weak boundary |
| **Filter on a different machine — hypervisor, gateway VM, or host OS outside the guest** | **Nothing the agent can reach** | **Real boundary** |

**Required architecture:** the engagement VM's egress is filtered **outside the guest** — macOS `pf`
on the host controlling the VM's NAT, a dedicated gateway VM, or the router. The agent has no
principal on that machine and no path to one. Inside the guest, the agent additionally runs as an
unprivileged user with no sudo, and hook scripts plus `settings.json` are root-owned and not
agent-writable — defence in depth, not the boundary itself.

**Tripwire.** The off-host filter logs every blocked destination. A block that `scope_guard.py`
had *allowed* means either the parser is wrong or the agent was manipulated. Both are incidents.
Reconciling the two logs is a standing check, not an optional one.

**Residual, stated plainly.** The API channel must remain open, so an injected agent could still
exfiltrate by writing data into text the operator reads. No network control prevents that; only
operator review does. Containment bounds the damage — it does not eliminate the class.

**Consequence for the demo and for client claims:** until off-host filtering exists, the honest
statement is *"scope violations are refused by tooling and logged"* — not *"cannot happen."*

---

### 9.10 Containment architecture — RESEARCH REQUIRED (candidate Subsystem G)

§9.9 states the requirement but not the implementation. Getting it wrong produces isolation theatre,
so this is a research item, not a design decision to be made from intuition.

**Required properties**, in priority order:

1. Egress filtering enforced by a principal the workload cannot become.
2. The workload cannot reconfigure its own network namespace (no `CAP_NET_ADMIN`, no sudo).
3. Filter rules derived from `scope.yaml` and regenerated per engagement, from outside.
4. Full egress logging outside the workload, reconcilable against `scope_guard` decisions (§9.9).
5. Snapshot/restore, so a compromised engagement environment is disposable.
6. Cheap enough for a solo operator to run per engagement.

**Caution against the obvious answer.** Containers share a kernel; Docker alone is a weaker
isolation boundary than a VM, and *Swarm is orchestration, not isolation*. A container that can be
escaped or that holds `CAP_NET_ADMIN` provides no boundary at all. Candidate architectures to
evaluate rather than assume:

| Option | Boundary | Notes |
|---|---|---|
| Kali VM + macOS `pf` on the host controlling NAT | Hypervisor | Cheapest for the current setup; host is already outside the guest |
| Kali VM + dedicated gateway VM | Two VMs | Filter has its own OS the workload cannot reach |
| Container workload + gateway sidecar, no `CAP_NET_ADMIN` | Namespace | Weaker; kernel shared with the filter |
| gVisor / Kata / Firecracker microVM | Stronger kernel isolation | More moving parts |

**Research questions:** which option actually satisfies property 1 under a realistic escape attempt;
what the failure modes of each are; how rules are generated and pushed from outside; how the
Anthropic API channel is permitted without becoming a general tunnel; whether DNS can be constrained
without breaking legitimate resolution of in-scope hosts; and what this costs to stand up per
engagement.

**Until this research lands and is implemented, the claim is "refused and logged", never "cannot
happen" (§9.9).**

---

### 9.11 Event envelope and SIEM forwarding — decide now, build later

Every ledger file (§7.5) is already JSONL. Committing now to a **common event envelope** makes
forwarding a configuration change later rather than a rewrite; deciding it after the fact means
re-emitting history. The cost today is naming fields consistently. The cost later is a migration.

```jsonc
{
  "ts": "2026-08-06T11:20:00Z",
  "engagement_id": "acme-2026-08",
  "event_type": "scope.deny | write.canary | gate.approve | finding.create | egress.block | …",
  "actor": {"agent": "rg-webtest", "model": "sonnet", "session": "…"},
  "target": {"asset_id": "A-014", "host": "…", "operation": "POST /rest/v1/…"},
  "decision": "allow | deny | escalate",
  "reason": "…",
  "tier": 2,
  "gate_ref": "G-002",
  "evidence_ptr": "evidence/F-007-anon-read.http",
  "severity": "info | low | … "
}
```

**Align field names to OCSF** (Open Cybersecurity Schema Framework) where a mapping exists, so a
forwarder to Splunk, Sentinel, Elastic or an OCSF-native lake is a mapping file rather than a
translation layer. `[VERIFY]` the current OCSF class most appropriate for security-testing activity
before fixing the names.

**Why it belongs in the spec now, unbuilt:**

- The off-host egress log (§9.9) and `scope_guard`'s decisions must be **reconciled**. Two logs in
  one schema makes that a query; two logs in two schemas makes it a project.
- The defensive handoff (Subsystem E) already promises drift monitoring. A client who receives
  RedGold's guardrail pack should be able to forward *its* events to whatever they already run.
- It is the natural upgrade path from one-off engagement to retainer: the same envelope that records
  an audit records ongoing monitoring.

**Not built for v1.** Emit the envelope; ship no forwarder. A forwarder against a stable schema is
an afternoon.

---
