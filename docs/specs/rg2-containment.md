---
title: RG-2 — containment
date: 2026-08-20
status: draft
question: What must be built, in what order, so that "the agent's cooperation is not required" is a true statement about RedGold's egress — and what may honestly be said to a client at each stage of that build?
spec_refs:
  - "docs/specs/redgold/07-enforcement.md §9.8, §9.9, §9.10, §9.11"
  - "docs/specs/rg1-finding-integrity.md §6 (environment cap)"
research_refs:
  - "docs/research/containment-architecture.md"
  - "docs/research/session-audit-2026-08-20.md §18–20"
  - "docs/research/prior-engagement-autopsy.md"
supersedes: nothing. §9.10 remains the requirement; this is its answer.
---

# RG-2 — containment

## Index

| § | Section |
|---|---|
| 0 | What this document decides, and what it refuses to decide |
| 1 | The defence stack, layer by layer — boundary vs defence-in-depth |
| 2 | Shell and OS hardening — what survives a scanner workload |
| 3 | The three-part split, mechanically |
| 4 | `open-vm-tools` and the guest→host channel |
| 5 | The reconciliation tripwire |
| 6 | Honeypots — evaluated, and declined |
| 7 | Target-mode matrix |
| 8 | The "secure on my machine" problem |
| 9 | Build order and cost |
| 10 | Honest limits, and the sentence this earns |
| 11 | Open items marked `[VERIFY]` |

---

## 0. What this document decides, and what it refuses to decide

§9.9 settled the rule: **containment must be enforced outside the blast radius of the thing being
contained.** §9.10 left the implementation open and warned that getting it wrong produces isolation
theatre. `containment-architecture.md` answered §9.10 with `RG-CONTAIN-1` — a gateway VM, a
disposable work VM, a rootless container inside it. This document turns that recommendation into a
build, and it does three things the research document did not:

1. It grades every layer **boundary or defence-in-depth**, in §9.8's own vocabulary, and refuses to
   inflate any of them. Only one layer is a boundary. Two more are *boundary preconditions* — they
   are not the control, but if they fail the boundary is bypassed rather than merely weakened, and
   that is a distinct category §9.8's table does not have.
2. It states, for every layer, the **failure mode when the layer breaks legitimate work**. A control
   that breaks `ffuf` gets disabled by the operator at 11pm during an engagement and is then worth
   less than no control, because the operator believes it is still on. This is the same failure the
   `FRAMEWORK_SCRIPTS` allowlist in `scope_guard.py:136-148` already documents: *"A control that
   blocks the safe path pushes the operator toward the unsafe one."* Treat that comment as a design
   rule, not an anecdote.
3. It makes the reconciliation tripwire implementable against the code that exists today.

**What it refuses to decide.** The RAM question (`containment-architecture.md` §7, §8 item 1) is a
provisioning decision the operator must make, and it is upstream of everything here: on a 16 GB Mac
the three-VM topology is **replace-not-add**, so `rg-work` and the operator's daily working guest are
probably the same VM slot. This document specifies what `rg-work` must be; it does not pretend to
know whether the operator will have two guests or one. If it is one, §9's build order still holds but
the "disposable clone" property (§9.10 property 5) is the first thing to fall, and the honest claim in
§10 loses a clause. **That decision is a precondition of the build, not an implementation detail of
it.**

### One terminology correction, made once

The operator's earlier phrasing was "nginx in front". For *egress* chokepointing the correct
component is a **forward proxy** — specifically an HTTP `CONNECT` proxy — not a reverse proxy. nginx
sits in front of a service to control what reaches it; RedGold needs to control what leaves the
workload. The rest of this document says "CONNECT proxy" and means that. Nothing else in the
operator's specification changes.

---

## 1. The defence stack, layer by layer

The operator named six layers: model guardrails, Claude Code hooks, shell lockdown, OS hardening,
network control, VM configuration. All six are worth having. **One of them is the boundary.** §9.8's
table is the model for the honesty required here — it calls three of its four layers advisory,
heuristic and detection, and that is the correct proportion, not a pessimistic one.

A third grade is needed that §9.8 does not have. Layers 3 and 6 below are **boundary preconditions**:
they are not themselves the control, but their failure does not degrade the boundary, it *bypasses*
it. A guest→host RPC channel is not a weaker firewall; it is a route that never meets the firewall.
Mixing preconditions in with defence-in-depth is how a stack looks deeper than it is.

### 1.1 The table

| # | Layer | What it actually stops | What defeats it | Grade |
|---|---|---|---|---|
| 1 | **Model instruction** — CLAUDE.md, agent cards, `.claude/rules` | Nothing reliably. Shapes ordinary behaviour; sets the default | Any prompt injection; any goal-directed drift. *You cannot defend a prompt with a prompt* (§9.9) | **Advisory** |
| 2 | **Claude Code hooks** — `scope_guard.py` PreToolUse, `no_nesting.py`, canary/loop guards | Sloppy or unintentional drift, and it is genuinely good at that | Encoding, `$(...)`, write-then-execute, target files, redirects (§9.3.1 enumerates its own losses); `rm` on the script if the agent is privileged | **Heuristic**, becoming **Detection** once §5's ledger rows exist |
| 3 | **Shell and interpreter lockdown** — restricted shell, PATH control, `noexec` | Almost nothing against a Python interpreter the workload legitimately needs | `python3 -c`, any static binary the agent writes, `cp` to a writable exec mount | **Defence-in-depth (weak)** — see §2, where the recommendation is mostly *don't* |
| 4 | **OS hardening on `rg-work`** — non-sudo `redgold` user, root-owned hooks and `settings.json`, read-only plugin mount, `--cap-drop=ALL` rootless container | The agent editing its own controls (threat (b)) — the *likely, non-malicious* case, which is worth a lot | Local privilege escalation; a container escape (three runc CVEs in Nov 2025, see `containment-architecture.md:102-111`); the operator running something on request | **Defence-in-depth (strong)** — §9.9's "weak boundary" row, honestly labelled |
| 5 | **Network control** — nftables default-deny + allowlist-only resolver + CONNECT proxy on `rg-gw`, a *different VM* | **Every packet to an unauthorised destination**, regardless of how the command was constructed, encoded or hidden | Nothing the workload can reach. Residuals: the permitted API channel, shared-IP collateral, DNS rebinding — §10 | **BOUNDARY** |
| 6 | **VM and hypervisor configuration** — one NIC on a NAT-less/DHCP-less custom vmnet whose only route is `rg-gw`; `.vmx` `isolation.tools.*` and `guest_rpc.*` keys; no shared folders; no host credentials in the template | Nothing on its own. It is what makes layer 5 the *only* route out | A second NIC anyone adds "temporarily"; the guest→host RPC channel left live (§4); a Fusion hypervisor escape | **Boundary precondition** |
| 7 | **Off-workload logging and reconciliation** — NFLOG→JSONL on `rg-gw`, `rg-reconcile` on the control tier | Nothing. Proves what happened and catches layer-2 failures | Nothing, for the gateway-side log. The workload-side log is forgeable by an escaped workload (§5.6) | **Detection** |

**Layer 5 is the only row that supports a client claim.** Layers 1–4 make it less likely that layer 5
is ever tested; they do not substitute for it. Layer 7 is what converts a layer-2 failure from
invisible into an incident, which is why §9 puts it first despite it stopping nothing.

### 1.2 Why layer 6 is a precondition and not defence-in-depth

The distinction is operationally load-bearing, so state it once, sharply. If layer 4 fails, the agent
is root on `rg-work` and layer 5 still holds — that is exactly the argument for the gateway VM, and
`containment-architecture.md:183-185` is right to call a container escape a *containment-degradation*
event rather than a containment-failure event.

If layer 6 fails — a second NIC, a live `vmtoolsd` RPC path to the host, a writable shared folder —
then layer 5 is not weakened, it is **irrelevant for that path**, because the traffic never traverses
`rg-gw`. Preconditions therefore need *verification*, not just configuration: §4 specifies checks run
from inside the guest, and they belong in `verify_controls.py`, not in a setup checklist.

### 1.3 Maintenance cost and the "breaks legitimate work" failure mode

This column decides which layers actually survive a year. A control that is disabled during an
engagement and never re-enabled is worse than one that was never built, because the operator's mental
model still contains it — and the client-facing sentence in §10 is derived from that mental model.

| # | Maintenance cost | Failure mode when it blocks legitimate work | Verdict |
|---|---|---|---|
| 1 | Near zero. Prose edits | The agent argues with its own rules and wastes a turn. Harmless | Keep |
| 2 | **High and continuous.** Every new tool, flag and script is a potential false deny; the `FRAMEWORK_SCRIPTS` allowlist exists because a hardening pass denied RedGold's own sanctioned commands | **The dangerous one.** A deny on a legitimate scan pushes the operator toward `--dangerously-skip-permissions` or toward deleting the hook. This has already happened in this project's history in spirit — an agent rewrote its own text to get a write past `scope_guard.py` (`prior-engagement-autopsy.md`) | Keep, but never tighten it in place of layer 5. Every tightening must be paid for with a test |
| 3 | Moderate, and it fights the toolchain constantly | Scanner writes a wordlist to `/tmp`, `noexec` blocks a helper, `sqlmap` fails opaquely. Diagnosis cost is high because the error surfaces far from the cause | **Mostly decline.** §2 |
| 4 | Low once the template is built. Rebuild on Kali major upgrades | Low risk if scoped to *ownership* rather than *syscalls*: a non-sudo user and root-owned hooks do not break `ffuf`. Capability drops can break packet crafting — §2.5 | Keep, in the narrow form §2 specifies |
| 5 | **Moderate and per-engagement** — the ruleset is regenerated from `scope.yaml` each time, which is the point | Breaks *loudly and correctly*: an in-scope host whose IP changed mid-engagement stops resolving/connecting. This is the good failure. The bad one is a CDN with rotating anycast IPs where the allowlist goes stale hourly — see §7 and §10.5 | Keep. This is the product |
| 6 | Low. Template-time `.vmx` edits, verified at boot | Loses shared folders, clipboard and possibly guest time sync (§4.4). Time sync loss is not cosmetic: it desynchronises the ±5s reconciliation join (§5.5) | Keep, with NTP replacing tools time sync |
| 7 | Moderate. The `ulogd2` normaliser is the fiddliest piece in the build | Reconciliation false positives — an `egress.mismatch` that is really a clock skew or a coarse join — halt an engagement for nothing. Two of those and the operator stops trusting the tripwire | Keep, and tune the join before shipping the halt behaviour (§5.5) |

---

## 2. Shell and OS hardening — what survives a scanner workload

CLAUDE.md's own doctrine is the constraint: *"A sandbox tight enough to be a boundary breaks the
tools; one loose enough to run them is not a boundary."* The conclusion that follows is not "harden
less" but **harden along a different axis**. There are two kinds of OS hardening and they behave
completely differently under a pentest workload:

- **Ownership hardening** — who owns the controls, who may write them, who may become root. Cheap,
  durable, and it does not care what syscalls `nmap` makes. **Adopt all of it.**
- **Syscall/execution hardening** — seccomp, AppArmor, capability drops, `noexec`, restricted shells.
  Directly antagonistic to raw sockets, packet crafting, and tools that write and execute helpers.
  **Adopt almost none of it**, and be explicit about why.

The network is the boundary. OS hardening's job is to make threat (b) — the agent tidying away its
own obstacles — hard, and nothing more. Judged against that job, most of the classic list fails a
cost/benefit test.

### 2.1 Unprivileged user with no sudo — **ADOPT. Highest value item in this section.**

The agent runs as `redgold`, a user in no administrative group, with no `sudoers` entry and no
password. `hiranya` — in group `sudo` on this machine — must never be the agent's user; that single
fact is what disqualifies the container-only architectures in `containment-architecture.md:92`.

- **Survives a scanner workload?** Yes, with one exception: `nmap -sS`, `-sU`, `-O` and traceroute
  need `CAP_NET_RAW`. See §2.5 for the resolution — grant the capability to the binary, not sudo to
  the user.
- **What it buys:** the agent cannot `nft flush`, cannot edit root-owned hooks, cannot install a
  systemd unit, cannot read another user's files.
- **What it does not buy:** anything at all after a local privilege escalation. This is §9.9's
  explicit *weak boundary* row and must not be described as more.
- **Provisioning assertion, not a habit:** the `rg-work` template build must *assert* that `redgold`
  is in no group with administrative rights and that `sudo -n true` fails, and record the assertion
  in the provisioning ledger. A template property nobody checks decays.

### 2.2 Root-owned hook scripts and `settings.json` — **ADOPT. Cheapest real control in RG-2.**

`.claude/settings.json`, `scripts/`, `.claude/rules/` and the RedGold plugin are owned by `root`,
mode `0755`/`0644`, mounted `:ro` into the container. The engagement directory (`findings/`,
`evidence/`, `ledger/`) is writable by `redgold`; nothing else is.

- **Survives a scanner workload?** Yes, completely. No scanner writes to the plugin.
- **What it stops:** the single most likely non-malicious failure — an agent hitting a `scope_guard`
  deny and "fixing" the obstacle. `prior-engagement-autopsy.md` records the behaviour already occurring.
- **What defeats it:** privilege escalation, and *the operator being asked to run something*. That
  second one is real and procedural: any agent request to modify a file under `scripts/` or
  `.claude/` is an incident to be logged, not a chore to be completed.
- **Consequence worth stating:** with hooks read-only, a hook that is *broken* cannot be fixed from
  inside. That is the correct trade — a broken hook should halt the engagement and go back to the
  control tier, which is exactly the §4.7 amendment round trip.

### 2.3 Restricted shell (`rbash`, `lshell`, PATH jails) — **DO NOT ADOPT.**

Say this plainly rather than listing it for completeness: **a restricted shell is security theatre in
this specific environment, and it will cost engagement time.**

The workload legitimately runs `python3`, `node`, `ruby` and `perl` — they are RedGold's own tooling
substrate, `scope_guard.py` is written in one of them, and half the scanner ecosystem shells out. Any
one of those is a full escape from a restricted shell in a single line. Meanwhile `rbash` reliably
breaks ordinary things: `cd`, `PATH` assignment, output redirection, `command -p`. The result is a
layer that stops nobody and generates a steady stream of "why did that fail" incidents, each of which
tempts the operator to loosen something that matters.

The one shell-adjacent measure worth taking is not restriction but **observation**: ensure every
interactive and non-interactive shell inherits the environment that makes the CONNECT proxy mandatory
(`http_proxy`, `https_proxy`, `no_proxy`) — and then *do not rely on it*, because the agent can unset
it. It exists so that well-behaved tools are logged, not so that badly-behaved ones are stopped;
default-deny on `rg-gw` is what stops them. Grade: **hygiene**, not a control.

### 2.4 `noexec` mounts — **DO NOT ADOPT beyond one narrow case.**

`noexec` on `/tmp`, `/var/tmp` and `/dev/shm` is standard CIS-style advice and it is wrong here.
Scanner toolchains write and execute from temp directories routinely — nuclei template helpers, Go
binaries extracted at runtime, `sqlmap`'s tamper scripts, anything installed via `pipx`/`npx` during
an engagement. Diagnosis is expensive because the failure surfaces as an opaque exec error inside a
tool the operator did not write.

The narrow case that is worth it: mount the **inbound share** (`scope.yaml`, `plan.json`, playbooks,
`provision.json`) `ro,noexec,nosuid,nodev`. That mount should never contain an executable —
`containment-architecture.md:344` already says the inbound direction carries no executable the
control tier did not author — so `noexec` there costs nothing and enforces the intent. Everything
else stays exec.

### 2.5 Capability drops — **ADOPT `--cap-drop=ALL` plus targeted file capabilities.**

`--cap-drop=ALL` and `--security-opt=no-new-privileges` on the workload container are correct and
cheap, with one caveat the research document raises and does not resolve: they break `nmap -sS`,
`hping3`, `arping` and anything on `AF_PACKET`, all of which need `CAP_NET_RAW`.

Three ways out, in order of preference:

1. **Do not need it.** RedGold's actual profile is HTTP/API testing over TCP. `nmap -sT` (connect
   scan) works with no capability at all and is what a scoped web engagement should be running
   anyway — a SYN scan of a client's production host is a tier decision, not a default.
   `containment-architecture.md:283` makes the same observation about gVisor and is right.
2. **Grant the capability to the binary, not the user:** `setcap cap_net_raw+ep /usr/bin/nmap` at
   template build time, container started with `--cap-add=NET_RAW` only when the engagement's ruleset
   records that it needs it. This keeps the *user* unprivileged, which is the property §2.1 is
   actually protecting.
3. **Never `--cap-add=NET_ADMIN`.** This is the line. `NET_ADMIN` lets the workload reconfigure its
   own network namespace, which is §9.10 property 2 by name. Anthropic's own devcontainer grants it
   (`containment-architecture.md:120-127`); it is a productivity guardrail and honest about being one,
   and RedGold must not copy it.

**Failure mode to anticipate:** capability drops fail *silently and confusingly* — `nmap` falls back
to a connect scan and prints a warning nobody reads, and the finding corpus quietly changes shape.
Any capability-dependent tool that degrades must be recorded in the coverage register (RG-1 §8.1) as
a coverage limitation, not left to be inferred from absence.

### 2.6 seccomp and AppArmor profiles — **DO NOT ADOPT a custom profile. Keep the default.**

Keep the container runtime's *default* seccomp profile — it is well-tested against ordinary
workloads and blocks the obviously exotic. **Do not write a bespoke one.** A custom seccomp or
AppArmor profile for a pentest toolchain is a permanent maintenance liability: every new tool, every
tool update, and every Go runtime change can trip it, and the failure presents as `EPERM` from deep
inside a binary the operator does not maintain. The benefit — narrowing kernel attack surface against
a container escape — is real but is already handled at the layer that matters: **the escape is
survivable because the boundary is on another machine.** Spending days on a profile to reduce the
probability of an event whose consequence is already bounded is the wrong trade for a solo operator
(§9.10 property 6).

gVisor (`--runtime=runsc`) is the same argument with better economics *if* the toolchain survives it,
and `containment-architecture.md:284` correctly marks that `[VERIFY]`. Treat it as optional, after
the boundary works, never as a substitute for it.

### 2.7 Summary — what to build

| Measure | Verdict | Reason |
|---|---|---|
| Non-sudo `redgold` user, asserted at provisioning | **Adopt** | Highest value; survives everything |
| Root-owned hooks, `scripts/`, `settings.json`, plugin `:ro` | **Adopt** | Stops the likely, non-malicious failure |
| `--cap-drop=ALL` + `no-new-privileges` | **Adopt** | Cheap; degrades one scan mode, handled by §2.5 |
| `setcap` on specific binaries when the scope needs raw sockets | **Adopt, per engagement** | Keeps the user unprivileged |
| `ro,noexec,nosuid,nodev` on the inbound share only | **Adopt** | Free; enforces a stated invariant |
| Proxy env vars in every shell profile | **Adopt as hygiene** | Logging, not enforcement. Do not claim otherwise |
| `CAP_NET_ADMIN` | **Never** | §9.10 property 2 |
| Restricted shell | **Decline** | Defeated by `python3 -c`; breaks real work |
| `noexec` on `/tmp` and friends | **Decline** | Breaks scanners; expensive to diagnose |
| Custom seccomp/AppArmor profile | **Decline** | Maintenance liability; the escape is already survivable |
| gVisor `runsc` | **Optional, later** | `[VERIFY]` toolchain first; never the boundary |

---

## 3. The three-part split, mechanically

CLAUDE.md names three systems with different trust properties. RG-2 concerns the second and third;
the first (this repo) is out of scope for containment and must stay that way — hard rule 3.

| | Tier | Principal | Runs | Trust |
|---|---|---|---|---|
| Part 1 | Framework dev | operator | this repo, macOS or a working guest | Trusted. **No client data, no targets, ever.** |
| Part 2 | Deployment & scoping — `rg-setup` | operator's macOS account | macOS host | Trusted. Host access. Never touches a target |
| Part 3 | Auditing & pentesting — `rg-webtest`, `rg-surface`, `rg-codeaudit`, `rg-verify` | `redgold`, non-sudo, in a `--cap-drop=ALL` container | `rg-work` VM | **Untrusted.** No host access, no principal on `rg-gw` |

### 3.1 The setup agent — what it does and what it must never do

`rg-setup` runs on the control tier with ordinary operator privileges. Its seven duties are as
`containment-architecture.md` §4.1 sets them out, and one placement decision in that list deserves
promotion to a rule because it is easy to get wrong under time pressure:

**`rg-recon` runs on the control tier, outside containment.** Asset discovery needs broad DNS and
broad web access — exactly what the contained tier must not have. This is not a compromise of the
model, it *is* the model: only `CONFIRMED` assets are testable and promotion is a human decision
(`scope_cli.py` already refuses promotion on one signal, on a bare IP, or outside the boundary).
**Recon outside, testing inside.**

Two prohibitions on `rg-setup`, both of which re-cross the boundary by hand if violated:

1. **It must never read raw outbound content in a session that holds tools.** See §3.3.
2. **It must never hold a live push channel into `rg-work` after handover.** Handover is a state
   transition, not a connection (§3.4).

### 3.2 Inbound (control → workload) — the easy direction

**Carries:** `scope.yaml`, `plan.json`, playbooks, the RedGold plugin, `provision.json`
(`engagement_id`, `scope_hash`, `ruleset_hash`, `resolution_ptr`, `window`).

**Constrained by:** read-only at the hypervisor, not inside. Bake it into the linked clone before
first boot where possible, so there is no live channel at all; otherwise a Fusion shared folder
marked read-only, mounted `ro,noexec,nosuid,nodev` (§2.4). Note the interaction with §4: if
`isolation.tools.hgfs.disable` is set to strip the guest→host channel, shared folders are gone and
bake-before-boot becomes the only option. **That is the right answer anyway** — a channel that does
not exist cannot be abused in either direction.

`session_start.py` inside asserts `scope_hash(provision.json) == sha256(mounted scope.yaml)` and
refuses to work on mismatch. **This is a consistency check, not a control** — it runs inside, so an
adversarial workload can defeat it. Say so in the code comment, in the style `scope_guard.py` already
uses for its own limits.

**Trust: high.** This is the only high-trust direction. It must carry no executable the control tier
did not author.

### 3.3 Outbound (workload → control) — the residual, addressed concretely

**Carries:** `findings/*.json`, `evidence/*`, `ledger/*.jsonl`, `requests/amend-*.json`.

**Every byte is attacker-influenced.** §9.9 names this as the residual and states plainly that no
network control prevents it. What follows is not a fix — it is a set of constraints that keep the
attacker's text from ever reaching a component that can act on it. The design principle:

> **Outbound content is only ever read by programs that do not follow instructions, or by a human who
> knows they are reading attacker-influenced text.** There is no third reader.

Seven rules, in the order they run:

1. **Manifest first.** The workload writes `handback.json`: SHA-256 per file, file count, byte count,
   `engagement_id`, `scope_hash`, `ruleset_hash`. The control tier verifies before opening anything
   else. A mismatch is an incident, not a retry. (The manifest is written by the workload and is
   therefore forgeable — it detects transfer corruption and casual tampering, not a determined
   escapee. Its value is that it makes the *honest* failure loud.)
2. **Transfer by plain directory pull.** `vmrun copyFileFromGuest` or a host-side read of the share.
   **Never git.** A git handover hands the control tier commit content, `.gitattributes` filters and
   hook files — an executable channel wearing a version-control costume. Commit on the control tier,
   after validation, if history is wanted.
3. **Structural validation is a program.** `validate_findings.py` plus a JSON-schema check, run as
   plain Python. Programs do not follow instructions embedded in their input. This is the single most
   important rule in the section.
4. **Sanitise before any human or model sees it.** Strip ANSI escapes and C0/C1 control characters;
   normalise Unicode (NFKC) and reject or flag confusable/bidi-control sequences; truncate absurd
   field lengths. Evidence files that must retain raw bytes (`.http`, `.pcap`) are stored raw and
   **rendered only as hex or as escaped text**, never pasted into a terminal or a model context in
   their original form.
5. **No agentic session on the control tier reads raw outbound content while holding tools.** If a
   model must summarise findings, it runs with no tools, no network, and its output is treated as
   equally untrusted — it has now read the payload.
6. **Report rendering stays deterministic.** `report.py` builds the deliverable from validated records
   through a fixed template. Do not put a model between the finding and the client document. This
   also protects the *client*: a prompt-injection payload embedded in a finding body must not reach
   the client's PDF as live text — §6.3 revisits this.
7. **Amendment requests are data.** `requests/amend-*.json` is parsed by a schema validator, rendered
   as inert text, and decided by a human against `scope_cli.py`'s existing two-signal rule. The
   agent's argument for why a host is in scope is *evidence to be checked*, never a reason to widen
   a ruleset automatically. The ruleset can never be widened from inside — that property is what the
   round trip buys.

**Stated plainly:** this direction is *contained*, not *trusted*. If the operator reads a finding that
says "run this cleanup query as `service_role`" and does it, the architecture did not fail — it was
never in that path. That is threat (f), it is the highest-severity residual in the system, and the
only mitigations are procedural: the standing rule that no command in a finding body is executed
without independent reconstruction, and the existing rule that unverified above-Low findings never
reach the client body.

### 3.4 Handover, mechanically

Not a socket, not an RPC, not a git remote. A filesystem drop plus a VM state transition:

1. Control tier writes `inbound/` and pushes the ruleset to `rg-gw` **from the host**, never from
   `rg-work`.
2. `nft -f /etc/nftables.conf` on `rg-gw` — atomic; a failed ruleset leaves the previous one intact.
3. Control tier writes `provision.json` (hashes and window).
4. `vmrun snapshot rg-work clean`.
5. `vmrun start rg-work`. **Boot is the handover event.** There is no live control channel afterwards.
6. Teardown: pull evidence, run `rg-reconcile`, `revertToSnapshot clean`, revoke the API key.

### 3.5 Where the Anthropic API credential lives

**Inside. The workload can read it. There is no way around this.** Claude Code needs the credential in
the process that makes the requests; proxy-side injection only moves the secret to a place the
workload can still cause to be used. Do not design around this; design *for* it.

What follows, as requirements:

- **A dedicated Console workspace and a dedicated API key per engagement**, with a workspace spend
  limit and rate limits, revoked at engagement close alongside `revertToSnapshot`. Anthropic supports
  per-workspace spend and rate limits; they are configured in the Console UI with no Admin API
  endpoint, so budget a couple of minutes of manual work per engagement.
  ([Workspaces](https://platform.claude.com/docs/en/manage-claude/workspaces),
  [Rate limits](https://platform.claude.com/docs/en/api/rate-limits))
- **Never place in `rg-work`:** a long-lived org-admin key, cloud credentials, the operator's SSH
  keys, the operator's git credentials, or any other client's engagement data. The template is built
  without them and **provisioning asserts their absence** — a grep of the image for key-shaped
  strings at template build time, recorded in the ledger.
- **The blast radius, stated:** an injected agent can spend tokens up to the cap, and can encode data
  into its own model requests or into text the operator reads. That is threat (d) and it is
  unstoppable; it is bounded, not prevented.
- **Client-supplied credentials share the fate.** If the client provides a `cleanup_credential`
  (§9.4.1), it lives inside and is compromised in the same event as the API key. **This must be in
  the engagement paperwork**, in the client's own words, before they hand anything over: *any
  credential supplied to the testing environment should be treated as disclosed at engagement end and
  rotated.* That sentence is cheap to write and expensive to omit.
- **Permit the channel without creating a tunnel.** Deny all direct egress from `rg-work`; force the
  API channel through the CONNECT proxy on `rg-gw` with a **hostname allowlist** — `api.anthropic.com`
  plus the minimum Claude Code telemetry endpoints — and **no TLS interception** (interception would
  write the operator's API key into a proxy log, which is strictly worse). Log
  `(ts, CONNECT hostname, bytes up, bytes down, duration)`. That is a channel: one hostname, one
  method, every byte counted. It does not stop steganography inside legitimate model traffic, and
  nothing does. Anthropic publishes fixed egress/ingress IP ranges and states they will not change
  without notice ([IP addresses](https://platform.claude.com/docs/en/api/ip-addresses)), but
  `[VERIFY]` whether `api.anthropic.com` resolves inside them in practice before writing any
  IP-based rule — the CONNECT-proxy design is deliberately independent of that answer.

---

## 4. `open-vm-tools` and the guest→host channel

`containment-architecture.md` §8 ranks this the most likely hole in the design and the first thing to
test. That ranking is correct, and one part of it has now been resolved against vendor documentation
in a direction that makes it worse, not better.

### 4.1 The channel is present, and by default it is reachable by an unprivileged user

This guest carries `open-vm-tools 2:12.5.0-2` (arm64) and `open-vm-tools-desktop`, with
`vmware-toolbox-cmd` and `vmtoolsd` on `PATH` and a command surface including `gueststore` (a
guest-initiated fetch from a host-side store) and `upgrade` (a guest-initiated tools upgrade driven
from the host side). Both are guest→host channels on their face.

The narrower question — *can a non-sudo user drive them?* — is answered by Broadcom's own KBs:

- Access to GuestInfo variables is gated by the `.vmx` keys `guest_rpc.rpci.auth.cmd.info-get` and
  `guest_rpc.rpci.auth.cmd.info-set`. **The documented default is `FALSE`**, i.e. *not* restricted;
  setting them `TRUE` makes `vmware-rpctool` / `rpctool.exe` and `vmtoolsd --cmd` return "Permission
  denied" for regular (non-admin/non-root) users, while root remains unaffected.
  ([KB 377294](https://knowledge.broadcom.com/external/article/377294/accessing-or-modifying-a-guestinfo-vari.html),
  [KB 377267](https://knowledge.broadcom.com/external/article/377267/modifying-a-cloudinit-guestinfo-variable.html))
- `vmware-rpctool` and `vmtoolsd --cmd` are documented as behaving *differently* for regular users —
  open-vm-tools identifies privileged callers by their use of privileged source ports (<1024), which
  the guest denies to non-privileged users; `vmtoolsd --cmd` is the path regular users can use.
  ([open-vm-tools issue #690](https://github.com/vmware/open-vm-tools/issues/690))

**So the answer to the research document's open item is: yes, by default, an unprivileged guest user
can drive at least the GuestInfo RPC surface, and the restriction is a host-side `.vmx` key that is
off unless you set it.** This is a `redgold`-reachable guest→host interface that does not traverse
`rg-gw`. Under §1.2 that makes it a **boundary-precondition failure**, not a defence-in-depth gap.

`[VERIFY]` What is *not* established from vendor documentation, and must be tested rather than
assumed: whether `gueststore` and `upgrade` specifically are reachable by a non-root user, and
whether any `guest_rpc.rpci.auth.cmd.*` key exists for commands other than `info-get`/`info-set`. Do
not write a client-facing claim that depends on either.

### 4.2 Removing the package is necessary and not sufficient

Uninstalling `open-vm-tools` removes the *convenient* interface. It does not remove the *transport*.
The backdoor is an architectural interface between guest and hypervisor, and open-vm-tools carries
architecture-specific backdoor implementations including an aarch64 one
([`backdoorGcc64_arm64.c`](https://github.com/vmware/open-vm-tools/blob/master/open-vm-tools/lib/backdoor/backdoorGcc64_arm64.c));
on ARM the tools implement an emulation of the x86 backdoor I/O space rather than the x86 port
mechanism itself. Any program the agent writes can in principle re-implement it — and a pentest
workload is unusually well equipped to do so.

`[VERIFY]` **Whether the aarch64 backdoor transport is reachable from unprivileged userspace (EL0) on
Fusion/Apple Silicon.** The claim that the backdoor is usable from unprivileged mode appears in
VMware patent text, not in vendor product documentation, and patent text is not a product-behaviour
source. Treat the answer as *probably yes* for planning purposes and *unestablished* for any claim.

**The consequence for the build:** package removal is hygiene; **the `.vmx` keys are the control**,
because they are set on the host side, outside the guest's blast radius — which is §9.9's rule
applied to a non-network channel.

### 4.3 What to set — the `rg-work` `.vmx`

Set on the host, in the template, before first boot. Verified key names and effects from Broadcom's
VMware Tools security-configuration documentation
([Security considerations to configure VMware Tools](https://techdocs.broadcom.com/us/en/vmware-cis/vsphere/tools/12-3-0/vmware-tools-administration-12-3-0/configuring-vmware-tools-components/using-vmware-tools-configuration-file/security-considerations-to-configure-vmware-tools.html))
and Workstation/Fusion guest-isolation documentation.

| Key | Value | Effect | Source status |
|---|---|---|---|
| `guest_rpc.rpci.auth.cmd.info-get` | `TRUE` | Non-root guest users get "Permission denied" reading GuestInfo | **Verified** (KB 377294) |
| `guest_rpc.rpci.auth.cmd.info-set` | `TRUE` | Same for writing GuestInfo | **Verified** (KB 377267) |
| `isolation.tools.hgfs.disable` | `TRUE` | Disables Shared Folders (HGFS); overrides `sharedFolder*.enabled` | Verified |
| `isolation.tools.copy.disable` | `TRUE` | Disables copy to guest clipboard | Verified |
| `isolation.tools.paste.disable` | `TRUE` | Disables paste from host clipboard | Verified |
| `isolation.tools.dnd.disable` | `TRUE` | Disables drag-and-drop both directions | Verified |
| `isolation.tools.diskShrink.disable` | `TRUE` | Blocks guest-initiated disk shrink | Verified |
| `isolation.tools.diskWiper.disable` | `TRUE` | Blocks guest-initiated disk wipe | Verified |
| `isolation.tools.vixMessage.disable` | `TRUE` | Blocks VIX API automation messages | Verified |
| `isolation.tools.getCreds.disable` | `TRUE` | Prevents guest retrieval of credentials | Verified |
| `isolation.tools.hgfsServerSet.disable` | `TRUE` | Disables the tools-side shared-folder server | Verified |
| `isolation.device.connectable.disable` | `TRUE` | Prevents guest connecting/disconnecting devices | Verified |
| `isolation.device.edit.disable` | `TRUE` | Prevents guest modifying device settings | Verified |
| `tools.setInfo.sizeLimit` | `1048576` | Caps how much the guest can write into the config file | Verified |
| `tools.guestlib.enableHostInfo` | `FALSE` | Blocks host performance metrics reaching the guest | Verified |

`[VERIFY]` **that VMware Fusion on Apple Silicon honours each of these keys.** Every source above is
written for ESXi/vSphere and Workstation. Fusion shares the `.vmx` format and the guest-isolation UI
exposes a subset of them, but "documented for vSphere" is not "verified on Fusion 13/14 aarch64".
Test each key by attempting the operation from inside the guest as `redgold` (§4.5) rather than
trusting the table. **Any key that cannot be shown to work must be treated as not set.**

Also set, and equally important because they are the *network* preconditions:

- exactly **one** virtual NIC, on a custom vmnet with Fusion's NAT and DHCP **disabled**, whose only
  gateway is `rg-gw`;
- no second adapter of any kind, including host-only, "for debugging";
- no USB passthrough, no serial port, no printer redirection.

### 4.4 What is lost, and the replacements

- **Shared folders** — gone. Inbound is baked into the clone before boot (§3.2); outbound is
  `vmrun copyFileFromGuest` from the host. Both are better shapes anyway.
- **Clipboard and drag-and-drop** — gone. Nobody should be pasting attacker-influenced text out of
  the workload by hand; that is threat (f) with a keyboard shortcut.
- **Guest time sync** — likely gone with the tools daemon. **Replace it**: run `chrony`/`systemd-timesyncd`
  against `rg-gw` (which itself may sync upstream), and permit `udp/123` to `rg-gw` only in the
  ruleset. This is not cosmetic — §5.5's reconciliation join uses a ±5 s window, and an unsynchronised
  workload clock manufactures both false mismatches and false clean runs.
- **Graceful shutdown from the host, and heartbeat/health reporting** — degraded. Acceptable: the
  teardown path is `revertToSnapshot`, not a graceful shutdown.

### 4.5 Verifying from inside the guest that the channel is gone

Configuration that is never verified decays, and this is a precondition, so verification must be
mechanical. Ship these as a `verify_containment.py` check set that runs **inside `rg-work` as
`redgold`** at session start and writes its results to the ledger as `containment.selftest` rows.
Each check is written so that **the pass condition is a failure to reach the host.**

| # | Check, run as `redgold` | Pass condition |
|---|---|---|
| 1 | `command -v vmtoolsd vmware-toolbox-cmd vmware-rpctool` | all absent |
| 2 | `systemctl is-active vmtoolsd open-vm-tools` | inactive/not-found |
| 3 | `lsmod \| grep -E 'vmw_(balloon\|vsock\|vmci\|pvscsi)'`, and `ls /dev/vsock /dev/vmci` | modules absent or blacklisted; device nodes absent |
| 4 | `vmtoolsd --cmd 'info-get guestinfo.ip'` (if the binary was reinstated by a package) | non-zero exit / "Permission denied" |
| 5 | `mount \| grep -i vmhgfs`, `ls /mnt/hgfs` | no HGFS mount |
| 6 | `ip -o link` | exactly one non-loopback interface |
| 7 | `ip route` | exactly one default route, next hop = `rg-gw` |
| 8 | Connect to a known-bad IP:port | fails at the socket, and a matching `egress.block` appears on `rg-gw` |
| 9 | `dig $(uuidgen).invalid-canary.example` | NXDOMAIN from `rg-gw`'s Unbound; no upstream query |
| 10 | `sudo -n true`; `id -nG` | fails; no administrative groups |

Checks 1–5 are the guest→host channel. **Check 8 is the only one that proves the boundary**, and it
must assert the *gateway-side* observation, not merely the local failure — a local failure can be
manufactured by anything. Wire that assertion into `verify_controls.py` alongside the existing
fault-injection tests, and treat a missing gateway-side record as a failure even when the connection
failed locally.

`[VERIFY]` the vmci/vsock module and device names on aarch64 Debian/Kali before hard-coding check 3;
blacklisting them may also disable functionality Fusion needs for other purposes.

---

## 5. The reconciliation tripwire

§9.9: *"A block that `scope_guard.py` had allowed means either the parser is wrong or the agent was
manipulated. Both are incidents."* §9.11 already flags that this is a requirement on software that
does not exist. This section makes it exist.

### 5.0 The gap, precisely, against current code

`scope_guard.py` writes **no ledger row at all** — not on allow, and not on deny.

- `evaluate()` ends `return Decision.permit()` with no side effect (`scripts/scope_guard.py:687`).
- `emit()` is documented `"""Write the hook's response. Silent on allow, by design."""` and returns
  early when `decision.allow` (`:76-79`).
- Denials go to `sys.stdout` as a `PreToolUse` JSON response and, on the `--check-url` path, to
  `sys.stderr` (`:734-737`). There is no `open()`, no append, and no JSONL anywhere in the decision
  path.

There is therefore nothing to reconcile *in either direction*. The deny side is arguably the more
embarrassing omission: a denial is an event with a security meaning, and today it survives only as
terminal text in a session transcript.

**Fix the guard before building the firewall.** This is §9's build-order argument and it is the
cheapest high-value item in RG-2.

### 5.1 The guard-side row — `ledger/activity.jsonl`

Aligned to §9.11's envelope, with two additions that §9.11 must adopt repo-wide now while it is still
cheap. Emitted on **both** allow and deny.

```jsonc
{
  "ts": "2026-08-20T11:20:00.123Z",
  "engagement_id": "acme-2026-08",
  "event_type": "scope.allow",              // or "scope.deny"
  "actor": {"agent": "rg-webtest", "model": "sonnet", "session": "<session_id>"},
  "target": {
    "asset_id": "A-014",
    "host": "api.acme.example",
    "port": 443,
    "resolved_ips": ["203.0.113.10"],       // ADDITION 1 — from ledger/resolution.jsonl
    "operation": "Bash: curl -s https://api.acme.example/v1/health"
  },
  "decision": "allow",                       // or "deny"
  "reason": "CONFIRMED in-scope; tier 1 <= ceiling 2",
  "tier": 1,
  "gate_ref": "G-002",
  "scope_hash": "sha256:...",
  "ruleset_hash": "sha256:...",              // from provision.json — proves which filter was live
  "corr_id": "01J8ZK...",                    // ADDITION 2 — ULID minted per decision
  "severity": "info"                         // "high" on deny
}
```

**Addition 1 — `target.resolved_ips`.** Without it there is no join key at all, because the firewall
only ever sees addresses. It **must be read from `ledger/resolution.jsonl`** — the resolution record
produced on the control tier at provisioning — and **never from a live lookup inside the guest**, for
two reasons: a resolver inside the workload can be poisoned by the target, and a lookup inside is
itself egress. If a host has no resolution record, stamp `resolved_ips: []` and set
`reason_code: "unresolved"`; do not guess.

**Addition 2 — `corr_id`.** A ULID minted by the guard. It turns a fuzzy time-window join into an
exact one wherever the value can be carried forward (§5.5).

**Also emit** `event_type: "scope.undeterminable"` as a distinct value rather than folding it into
`scope.deny`. §9.3.1's undeterminable-target denial is the parser admitting it lost, and its rate over
time is the single best metric for whether layer 2 is degrading. Burying it inside `scope.deny` makes
that invisible.

### 5.2 Implementation notes — the gotcha that will break this

Writing the row is ten lines. There is one non-obvious constraint and one ordering constraint:

1. **The allow row must not become an allow *decision*.** `emit()` returns silently on allow *by
   design*, because emitting an explicit `permissionDecision: "allow"` would auto-approve the call and
   suppress the operator's own permission prompt. The ledger append must therefore happen **outside**
   `emit()` — do not add a write inside the allow branch and then be tempted to "make it symmetrical"
   by emitting a decision too. Recommended shape: a `record(decision, context)` call in `main()`,
   between `evaluate()` and `emit()`, and in `check_url()` before its return.
2. **Failure to log must not fail open, and must not fail the tool call either.** `main()` is already
   wrapped so an unhandled exception denies rather than permits (`:741-755`) — correct, keep it. But a
   ledger write failing (disk full, read-only mount) must not turn every tool call into a deny mid-
   engagement. Rule: **wrap the append in its own try/except; on failure, write a `ledger.write_fail`
   marker to stderr and continue with the original decision** — then have `rg-reconcile` treat *any*
   gap in `corr_id` monotonicity as an unattributed-traffic condition. Losing rows is survivable
   because the gateway log is the trustworthy one; deadlocking the engagement is not.
3. **Use the existing helper shape.** `append_ledger(root, name, row)` already exists identically in
   `scope_cli.py:89-93` and `gate_cli.py:81-85`. It is now needed in a third place; move it to a
   shared module rather than copying it a third time, and give it an `O_APPEND` single-`write()`
   append so concurrent agents do not interleave partial lines.
4. **`check_url()` must log too.** `rate_probe.sh` calls the guard through this path; if it does not
   log, RedGold's own sanctioned burst path is invisible to reconciliation and shows up as
   unattributed traffic — a false positive that will train the operator to ignore the alarm.

### 5.3 Also close the §5.5 attribution gap while you are in there

`scope_guard.py:672-676` already documents that §5.5's rate-limiting, `purpose=attribution` logging
and evidence-discard requirements are **NOT enforced**. The logging third of that is now free: an
attribution probe against an unconfirmed in-scope host emits its row with
`reason_code: "attribution_probe"` and `purpose: "attribution"`. That does not enforce anything, but
it makes the unenforced carve-out *visible in the ledger* instead of only in a code comment, and it is
a prerequisite for ever rate-limiting it.

### 5.4 The gateway-side log — `egress.jsonl` on `rg-gw`

nftables `log ... group N` sends matched packets to NFLOG; `ulogd2` consumes the group and writes
JSON ([nftables wiki — Logging traffic](https://wiki.nftables.org/wiki-nftables/index.php/Logging_traffic),
[Netfilter logging framework](https://home.regit.org/2014/02/nftables-and-netfilter-logging-framework/)).
A thin normaliser on `rg-gw` maps ulogd JSON into the §9.11 envelope:

```jsonc
{
  "ts": "2026-08-20T11:20:00.140Z",
  "engagement_id": "acme-2026-08",
  "event_type": "egress.block",            // or "egress.allow" (ct state new only)
  "actor": {"agent": null, "source_ip": "10.77.0.20"},
  "target": {"host": null, "ip": "198.51.100.5", "port": 443, "proto": "tcp"},
  "decision": "deny",
  "reason": "nft:default-deny:chain=egress",
  "ruleset_hash": "sha256:...",
  "severity": "high"
}
```

Three requirements on this side:

- **Log allows as well as blocks**, on `ct state new` only, so per-flow volume stays sane. Without
  allow rows you cannot detect "the guard allowed something the firewall never saw" — which §5.5 rates
  the *more* alarming outcome.
- **The CONNECT proxy emits its own rows** with the requested hostname, which is the only place a
  hostname exists on the gateway side. `event_type: "egress.proxy"`, fields
  `(ts, host, method, bytes_up, bytes_down, duration_ms, corr_id?)`.
- **Unbound emits query rows** — QNAME, QTYPE, response code — into the same envelope as
  `event_type: "dns.query"`. A burst of NXDOMAIN for long random labels is threat (e) happening in
  front of you.

### 5.5 The join

**Primary key:** `(engagement_id, dst_ip, dst_port, |Δt| ≤ 5 s)`.
**Promote to exact** wherever `corr_id` can be carried: for proxy-mediated HTTP the workload emits it
as a request header which the proxy logs and **strips before forwarding** — a header that reaches the
client's server is an information leak, so the strip is mandatory, not tidy.

Hostname is unavailable on the nftables side; IP is unavailable on the guard side unless stamped from
the resolution ledger. That is why `resolved_ips` is not optional.

| Guard | Gateway | Meaning | Action |
|---|---|---|---|
| allow | allow | Normal | none |
| deny | (nothing) | Guard worked, no packet left | none — but count it; the rate is a health metric |
| deny | **allow** | The guard denied and traffic went anyway: a tool bypassing the hooked path, or a background process started earlier | `egress.mismatch`, **high**. Investigate the process |
| **allow** | **block** | **§9.9's named incident** — the parser was wrong, or the agent was manipulated | `egress.mismatch`, **high**. **Halt.** Human review. Write a regression test from the payload |
| (nothing) | **block** | Traffic the guard never evaluated at all — write-then-execute, redirect, background job | `egress.mismatch`, **high**, plus: identify the process. **The more alarming row** |
| (nothing) | allow | Egress the guard never saw but the filter permitted — e.g. a redirect landing on an in-scope IP | `egress.unattributed`, **medium**. Review |

**Tuning before the halt behaviour ships.** The ±5 s window plus a shared IP will produce joins that
are wrong in both directions. Run reconciliation in **report-only mode for the first two
engagements**, measure the false-positive rate, and only then enable the halt. A tripwire the operator
has learned to dismiss is worse than no tripwire — the same argument §2 makes about disabled controls.

### 5.6 Where it runs, and what it can honestly detect

**On the control tier, over pulled copies of both logs.** Not on `rg-gw` — keep the gateway minimal
and single-purpose — and obviously not on `rg-work`. `rg-reconcile` is plain Python with no model in
the loop, run (a) every 60 s during an engagement and (b) as a **mandatory gate at engagement close**,
alongside `cleanup_gate.py`. An unresolved `high` blocks engagement close exactly as outstanding
cleanup debt does.

One caveat that belongs in the code comments, in `scope_guard.py`'s own style:

> A workload that has escaped its container can forge `ledger/activity.jsonl`, because it writes it.
> The workload-side log is **evidence, not proof.** The gateway-side log is trustworthy because it is
> written on a machine the workload has no principal on. Reconciliation detects an honest parser
> failure reliably and a dishonest workload only imperfectly.

That asymmetry is acceptable, because in the dishonest case the **filter** is the control and the log
is only the narrative.

---

## 6. Honeypots — evaluated, and declined in the proposed form

The operator's idea, offered as "just an idea": *"a few out-of-scope honeypots could be set up so
that even if the agent does start escaping it might dig into those instead."*

**Verdict: do not build out-of-scope honeypot services. Build one canary artefact instead (§6.5).**
The reasoning, honestly, because the idea is not silly — it is the right instinct aimed at a problem
this architecture has already solved.

### 6.1 It is detection, not containment — and detection is the layer already saturated

A honeypot's value is the probability that an escape attempt touches it rather than something real.
In `RG-CONTAIN-1`, **every** packet to a non-allowlisted destination is already dropped and logged on
a machine the workload cannot reach, and **every** DNS query for a non-allowlisted name already
returns NXDOMAIN and is already logged. The detection probability for network-shaped escape attempts
is not "improved by a honeypot" — it is already 1, by construction, for the entire out-of-scope
address space.

A honeypot can only add value where detection is currently *below* 1. So the honest question is: what
are the agent's actual escape paths, and which of them does a honeypot cover?

| Escape path | Current detection | Would a honeypot help? |
|---|---|---|
| Connect to an out-of-scope host | 1.0 — `egress.block` | **No.** Already caught, and a honeypot would make it an `egress.allow` — *worse*, because the alarm becomes quieter |
| DNS exfil to an attacker domain | 1.0 — NXDOMAIN + `dns.query` | **No** |
| Container escape to `rg-work` root | ~0 locally, but bounded — the boundary still holds | Marginally. Requires a *host-local* decoy, not a network one |
| Guest→host RPC (§4) | 0 until §4.5's checks exist | **No** — build the checks; that is the answer |
| Editing its own hooks/controls | Low (file ownership stops it; nothing alarms) | **Yes, cheaply** — see §6.5 |
| Tunnelling through the API channel | ~0, and unstoppable | **No** |
| Manipulating the operator via findings | 0 mechanically | **No** |

The two rows where detection is genuinely weak are answered by a static canary artefact and by §4's
self-test — neither of which is a honeypot service.

### 6.2 The findings-corpus pollution risk is real, and it is the decisive objection

Ask the question the deliverable forces: **is there any scenario where an agent reports a honeypot as
a client finding?** Yes, and it is not exotic — it is the *expected* behaviour of a system working as
designed:

1. A honeypot exists to look like an attractive, weakly-defended service.
2. RedGold's agents exist to find attractive, weakly-defended services and write them up.
3. `rg-webtest` finds an unauthenticated admin panel on `10.77.0.99`, verifies it (it is deliberately
   verifiable), and writes `F-0xx: unauthenticated administrative interface`, `severity: high`.
4. Nothing downstream reliably rejects it. `scope_guard.py` would have denied *contacting* it — but
   the honeypot only functions if it is reachable, so either it is out-of-scope-and-unreachable (in
   which case it is inert and pointless) or it is reachable (in which case it is inside the allowlist
   and looks like a client asset).

That is the trap: **a honeypot must be reachable to work, and anything reachable is inside the
containment boundary and therefore looks in-scope to everything downstream.** RG-1's applicability
filter and the asset-register join would catch most instances — a finding whose `asset_id` resolves
to nothing in `assets/register.jsonl` should never reach a report — but "most" is the wrong standard
for a class of error whose failure mode is *inventing a critical vulnerability in the client's
infrastructure that does not exist.* That is a P9 calibrated-honesty violation shipped to a paying
client, and it is exactly the failure mode `prior-engagement-autopsy.md` documents RedGold already being prone
to.

Against a benefit of approximately zero (§6.1), any nonzero probability of this loses.

### 6.3 Second-order cost: it corrupts the evidence corpus and the metrics

Even when a honeypot finding is caught before the report, it is now in `findings/`, in the coverage
register, in the ledger, and in whatever corpus is later used to measure RedGold's own false-positive
rate. Deliberately seeding false positives into a system whose central design problem is finding
integrity is working against RG-1 from inside.

### 6.4 Maintenance cost, stated

A honeypot is a service. It needs a host, a config, patching (an unpatched decoy is a real foothold —
it runs on `rg-work`'s network, next to the gateway), a log path, an alerting rule, and a place in the
provisioning script. Call it half a day to build and a recurring tax forever, spent on the one layer
that is already saturated. §9.10 property 6 — *cheap enough for a solo operator* — is a hard
requirement, and this fails it on its own even before §6.2.

### 6.5 What to build instead — one canary artefact, ~30 minutes

Keep the operator's instinct, drop the service. Seed the `rg-work` template with a small number of
**inert canary artefacts**: a plausible-looking but entirely fictitious credential and hostname, in
plausible places (`~/.aws/credentials`, a `.env`, a shell history entry), where:

- the hostname appears in **no** `scope.yaml`, ever, and is registered nowhere;
- the credential is valid for nothing;
- `rg-gw` holds a **specific, named rule** matching that hostname and that credential string, logging
  `event_type: "canary.trip"`, `severity: "critical"`;
- Unbound answers the canary name with a static sinkhole address rather than NXDOMAIN, so a trip is
  distinguishable from ordinary noise.

Properties that make this the right shape:

- **Zero false positives by construction.** Nothing legitimate ever touches it. Compare §5.5's join,
  which needs tuning; this needs none.
- **It cannot enter the findings corpus**, because it is part of *RedGold's environment*, not part of
  the target. No agent scanning the client's asset will encounter it as a discovery.
- **It covers the one genuinely weak row in §6.1** — an agent going through the workload's own
  filesystem for credentials and destinations, which is precisely the behaviour that precedes both
  threat (b) and a post-escape pivot.
- **It costs nothing to maintain.** It is two files and one nft rule in the template.

Record it in the engagement paperwork as part of the testing environment, so it can never be mistaken
for client infrastructure by a future reader of the ledger.

---

## 7. Target-mode matrix

Whitebox → a repo or a dev environment. Blackbox → a dev environment or a live site under heavy
controls. The four combinations differ in what egress must be permitted, what the ruleset contains,
and what `scope.yaml` must record — and they differ *more* than they look, because two of them involve
no network target at all.

| | **Whitebox / repo** | **Whitebox / dev env** | **Blackbox / dev env** | **Blackbox / live site** |
|---|---|---|---|---|
| **Primary agent** | `rg-codeaudit` | `rg-codeaudit` + `rg-webtest` | `rg-surface` + `rg-webtest` | `rg-surface` + `rg-webtest` + `rg-verify` |
| **Containment must permit** | **Nothing outbound but the API channel.** The repo is baked into the clone | API channel + the dev host's IPs on scoped ports | API channel + dev host IPs + DNS for the dev hostnames | API channel + production IPs on scoped ports + DNS + strict rate discipline |
| **Egress ruleset** | Default-deny with **no target rule at all**. This is the cheapest, safest mode and it should be the default for a first engagement | Target rule for a small, stable, private IP set. Usually static, often RFC1918 | As whitebox/dev, plus tolerance for hostnames the client adds mid-engagement (§4.7 round trip) | Target rule over **public, possibly CDN-fronted, possibly rotating** IPs. Re-resolve on a schedule and log every change |
| **Ceiling (§6 tiers)** | n/a — no network actions | Up to tier 3 is defensible on a dev box the client can restore | Tier 2 default; tier 3 only with named authorisation | **Tier 1 default.** Tier 2 requires explicit written approval; tier 3 requires approval plus a window plus a named client contact reachable during it |
| **What `scope.yaml` must record** | `asset_type: SOURCE_CODE`, commit SHA, and that no live system was contacted | Dev host identifiers, `environment: development`, and how dev differs from prod (§8) | Same, plus how the dev instance was provisioned and by whom | `environment: production`, testing window, rate limits, blast-radius constraints, cleanup credential handling (§3.5), and a named contact |
| **Dominant risk** | Secrets in the repo entering `rg-work` and then the corpus | Findings that do not hold in production (§8) | Attribution error — testing something the client does not own | **Harm to a live system**, which containment does *not* address at all (§10.3) |
| **RG-1 environment cap** | `code_defect` nexus applies by default — the environment of a source-code finding is the code, not the box | Cap applies; `production_nexus` needed to lift | Cap applies | No cap; findings stand at full severity |

### 7.1 The two rules that fall out of the matrix

1. **Whitebox/repo is the mode to build first and to prefer.** It needs no target rule, has no blast
   radius, and exercises the whole pipeline. `containment-architecture.md`'s end-to-end validation
   step should be done in this mode before any live traffic is contemplated.
2. **Blackbox/live is the only mode where containment is doing load-bearing work at client-facing
   risk** — and it is also the mode where the allowlist is coarsest, because production is where CDNs
   and shared hosting live. §10.4 is the honest statement about that; do not let the strength of the
   architecture in the other three modes be quoted about this one.

### 7.2 What changes in the ruleset when the mode changes

The generator (`nftables.conf` from `scope.yaml`) must key on `mode` and `environment`, not just on
the asset list, and must **refuse** to emit two combinations:

- a `SOURCE_CODE`-only scope that nonetheless carries target IP rules — that is a scope error, and
  silently permitting it defeats mode 1's whole benefit;
- `environment: production` with a ceiling above the scope's recorded ceiling, or with no testing
  window — production without a window is not an engagement, it is an incident waiting for a
  timestamp.

Both refusals belong in the generator on the control tier, where the workload cannot argue with them.

---

## 8. The "secure on my machine" problem

The operator:

> *"Some red teaming against the live version is important, because otherwise there's an 'it's secure
> on my machine' problem — maybe it really is hardened on dev, but on deployment there's something
> that causes a side-channel leak, or its configs subtly change when deployed, or behaviour changes."*

This is correct and it is a **methodological constraint on the product**, not a containment
preference. It has to be stated here because containment is what makes production testing possible or
impossible.

### 8.1 The collision with RG-1's environment cap

RG-1's environment cap (`rg1-finding-integrity.md` §6 — note: §6, not §2) discounts non-production
findings: graduated caps of `staging → high`, `development → medium`, `ephemeral-preview → low`,
liftable only by a `production_nexus` from a five-value closed vocabulary with a resolving evidence
pointer. That rule is right, and RG-2 does not touch it.

Put the two together and a conclusion falls out that neither document states on its own:

> **An engagement that tested only non-production cannot speak to production. That belongs in the
> report headline, not in a footnote.**

The cap already handles it *per finding*. What is missing is the *per engagement* statement. A client
reading a report of `medium` findings will conclude their production system is moderately healthy;
the truthful conclusion is that their production system was **not assessed**. Those are different
claims and only one of them is supported.

**Requirement (RG-1 interaction, to be reflected there):** `report.py` emits, in the report's first
section and in the executive summary, one of three sentences derived mechanically from
`environment_at_test` across the coverage register — never written by an agent:

- *"This assessment tested your production systems."*
- *"This assessment tested a non-production environment (`development`). Findings are rated for the
  environment tested. **Nothing in this report is evidence about your production systems**, including
  the absence of findings."*
- *"This assessment tested production for [asset list] and non-production for [asset list]. The
  distinction is carried on every finding."*

The second sentence is the one that costs a sale and is therefore the one most at risk of erosion.
It is also the one that makes the third-party attestation worth anything.

### 8.2 What containment must support for limited production testing

Production testing is not a containment relaxation; it is a **narrower** configuration with more
recording. Specifically:

1. **A production-mode ruleset is narrower, not wider.** Exact resolved IPs and exact ports, no
   wildcard entries, no apex-wide recursion. Where §4.5's optional Unbound `stub-zone` variant would
   be used for a wildcard host, it must be recorded as a named engagement deviation with the
   operator's approval.
2. **A hard testing window, enforced in two places.** `scope_guard.py` already denies outside the
   authorization window and the testing window (`:600-618`). RG-2 adds the second enforcement: the
   ruleset carries the window, and `rg-gw` drops target traffic outside it via an nft time match or a
   scheduled ruleset swap from the control tier. **Layer 2 alone is not enough for a production
   window** — that is the whole thesis of §9.9 applied to time instead of destination.
   `[VERIFY]` nftables time-based matching support in the packaged version before relying on the
   in-kernel form; the scheduled-swap fallback needs no special support and is preferred if uncertain.
3. **Rate discipline as a first-class ruleset property**, not agent politeness. Per-destination
   connection-rate limiting on `rg-gw` bounds the tier-2/3 blast radius even when the agent's own loop
   guard fails — and the agent's loop guard is in-guest, i.e. heuristic.
4. **A live named contact and an abort path.** Reverting `rg-work` to snapshot terminates every
   session instantly and is the abort button. It should be documented to the client as such, with a
   phone number that reaches the operator.
5. **Cleanup obligations recorded before, not after.** Any tier-2 write against production carries a
   canary row (§9.4.1) and an unresolved canary blocks engagement close.

### 8.3 What the scope record must carry about dev-vs-prod divergence

The "secure on my machine" problem is a *divergence* problem, so the divergence must be recorded as
data at scoping time — while the client is available and cooperative — not reconstructed at report
time. Add to `scope.yaml` a `parity` block, filled from the scoping questionnaire (Part 2 of RedGold),
and **carry it onto every finding** produced in a non-production environment:

```yaml
parity:
  tested_environment: development
  production_exists: true
  divergences:                       # client-asserted; each becomes a stated limitation
    - area: tls_termination          # CDN/WAF in front of prod, absent on dev
      differs: true
      note: "Cloudflare WAF in front of production; dev is origin-direct"
    - area: authn_provider
      differs: false
    - area: env_config               # secrets, feature flags, debug modes
      differs: true
    - area: data                     # synthetic vs real
      differs: true
    - area: infrastructure           # single container vs autoscaled
      differs: true
  divergence_source: client_questionnaire   # never agent-inferred
  attested_by: "<name>, <role>, <date>"
```

Three properties this must have:

- **Client-asserted, attributed and dated.** RedGold does not get to guess whether prod matches dev;
  guessing is exactly the fabrication hard rule 1 exists to prevent. `divergence_source` may be
  `client_questionnaire` or `operator_observed` — **never** `agent_inferred`.
- **Each `differs: true` becomes a stated limitation in the report**, mechanically. A WAF in front of
  production is the canonical case: it can hide a real finding *and* it can be the finding, and either
  way a dev-only test cannot tell you which.
- **A divergence in `tls_termination`, `env_config` or `infrastructure` blocks the "no findings"
  conclusion outright.** With those differing, "we found nothing" is not a supportable sentence about
  production under any severity model.

### 8.4 The honest position, in one line

Non-production testing finds real defects cheaply and safely; it cannot establish a production
security posture. RG-2 makes limited production testing *survivable* by narrowing and recording it.
Neither document lets an engagement quietly upgrade the environment it tested into the environment the
client cares about.

---

## 9. Build order and cost

Property 6 of §9.10 — *cheap enough for a solo operator to run per engagement* — is a hard
requirement. A containment design that costs 20 minutes of setup per engagement gets skipped on the
engagement where it mattered.

### 9.1 Sequence, by risk reduced ÷ effort

**Step 0 — decide the RAM/topology question. Before any code.** On a 16 GB Mac the topology is
replace-not-add (`containment-architecture.md:676-690`): the working guest already holds ~9.7 GiB
standing. Either `rg-work` replaces the daily working guest, or the fallback (macOS `pf` filtering the
Fusion vmnet — which still satisfies property 1, at a cost on properties 3–5) is taken. Building
`rg-gw` before answering this risks building a VM that cannot be run. `[VERIFY] total RAM on the Mac`.

| Order | Item | Effort | Risk reduced | Why here |
|---|---|---|---|---|
| 1 | `scope_guard.py` emits `scope.allow` / `scope.deny` / `scope.undeterminable` rows, with `resolved_ips`, `corr_id`, and the `check_url()` path covered (§5.1–5.3) | 2–3 h | Detection only — but it is the **prerequisite for everything downstream**, and it makes denials survive the session | Cheapest real improvement in the list; useful standalone; already specified |
| 2 | `.vmx` `isolation.tools.*` + `guest_rpc.*` keys, `open-vm-tools` stripped, `verify_containment.py` checks 1–7, 9, 10 (§4) | 3–4 h | **Closes a boundary-precondition hole that is live today** (§4.1) | Highest risk-per-hour in the build. A hole that bypasses the boundary outranks work that strengthens it |
| 3 | `rg-gw` VM: custom vmnet, nftables default-deny, static Unbound, routing (§1 layer 5) | 4–6 h | **The boundary.** Everything §10 permits saying depends on this | The product. Longer than steps 1–2 but it is what is being bought |
| 4 | `nftables.conf` + `unbound.conf` generators from `scope.yaml`, with §7.2's two refusals + tests | 5–7 h | Makes step 3 per-engagement rather than hand-maintained | Without it step 3 decays into a static ruleset nobody regenerates |
| 5 | CONNECT proxy with hostname allowlist, no TLS interception, logging (§3.5) | 2–3 h | Makes the API channel a channel and not a tunnel; gives the only hostname-bearing gateway log | Needed before the reconciler can do exact joins |
| 6 | `ulogd2` NFLOG → §9.11 envelope normaliser (§5.4) | 3–4 h | Gateway-side trustworthy log | **The fiddliest piece.** Do not schedule it optimistically |
| 7 | `rg-reconcile` + tests + fault injection in `verify_controls.py`, report-only mode first (§5.5–5.6) | 4–6 h | Converts layer-2 failures from invisible to incidents | Needs 1 and 6 |
| 8 | `rg-work` template: non-sudo `redgold`, root-owned hooks, rootless container, credential-absence assertion, canary artefacts (§2, §6.5) | 4–5 h | Threat (b); post-escape detection | Independent of 3–7; can be done in parallel |
| 9 | `rg-provision` / `rg-teardown` around `vmrun`; per-engagement Console workspace runbook | 3–4 h | Makes the 3–4 minute per-engagement number real | Property 6 lives or dies here |
| 10 | End-to-end validation in whitebox/repo mode against a host the operator owns (§7.1) | 3–4 h | Proves the whole chain, including check 8 | Last, and non-negotiable before any client claim |
| 11 | *Optional, later:* gVisor `runsc` after `[VERIFY]`ing the toolchain | 2–4 h | Reduces escape probability; changes no claim | Never before 1–10 |

### 9.2 Where this disagrees with the research document

`containment-architecture.md` §7 lists the `scope.allow` emission and the reconciler as "useful on
their own and the cheapest real improvement", which is right, but places the `.vmx`/`open-vm-tools`
work in an appendix of `[VERIFY]` items. **Promote it to step 2.** The reasoning is §1.2: a live
guest→host channel is not a weaker boundary, it is a route that never meets the boundary — and §4.1
now shows the restriction is off by default, so this is a present-tense hole rather than a research
question. Four hours spent there outranks four hours spent anywhere else in the list except the
gateway itself.

One partial disagreement with the ordering logic more generally: putting the reconciler's *ledger
rows* first is correct, but **do not build `rg-reconcile` itself before the gateway exists** — there
is nothing to reconcile against, and a reconciler validated only against synthetic data will be
wrong in exactly the ways §5.5 warns about. Steps 1 and 2 first; then 3; then the rest.

### 9.3 Cost — validated and revised

**One-time: the research document's 4–5 focused days is optimistic. Plan 6–8.** The estimate is
sound for the items it lists and the per-item numbers are believable; what it omits is:

- the `.vmx`/`open-vm-tools` work and its verification harness (step 2, 3–4 h);
- the mode-aware generator refusals in §7.2 and the `parity` block in §8.3 (~3 h);
- the two report-only reconciliation engagements before the halt behaviour is trusted (§5.5) — not
  build hours, but calendar time before the claim in §10 can be made;
- the topology re-plan implied by step 0, which is the most likely thing to add a day.

Total ≈ 40–55 hours. That is 6–8 focused days, and anyone quoting fewer has not written the ulogd
normaliser.

**Per engagement: 3–4 minutes is roughly right in steady state, but not at first.**

| Step | Steady state | First 2–3 engagements |
|---|---|---|
| `vmrun clone` (linked) | ~20 s | ~20 s |
| Resolve, generate, push ruleset, `nft -f` | ~10 s | ~10 s + investigating what the ruleset broke |
| Boot, stage inbound, snapshot `clean` | ~60 s | ~60 s |
| Console workspace + key + spend cap (UI, no Admin API) | ~2 min manual | ~2 min manual |
| `verify_containment.py` self-test (§4.5) | ~15 s | ~15 s |
| **Total setup** | **≈ 4 min, ~2 human** | **≈ 15–30 min, most of it human** |
| Mid-engagement amendment | <1 min machine + operator decision | same |
| Teardown: pull, reconcile, revert, revoke key | ~2 min | ~5 min |

The steady-state number satisfies property 6 comfortably. The **honest** number to plan around is the
first-engagements column, because that is when the operator decides whether the system is worth
keeping. The `[VERIFY]` items in §11 are the main things that turn a 4-minute setup into a 30-minute
one.

**Standing cost.** VMware Fusion Pro has been free for commercial, educational and personal use since
November 2024, with no license key required
([VMware announcement](https://blogs.vmware.com/cloud-foundation/2024/11/11/vmware-fusion-and-workstation-are-now-free-for-all-users/),
[Broadcom KB 368667](https://knowledge.broadcom.com/external/article/368667/download-and-license-vmware-desktop-hype.html));
free users get documentation and community support only. RAM: `~768 MB` for `rg-gw` is a round-number
estimate with no stated basis — `[VERIFY]` by building it. Disk ~40 GB for the template; linked clones
add little. Cognitive cost: one `vmrun` command and one habit — **never run the agent on the
workstation VM.**

---

## 10. Honest limits, and the sentence this earns

Written to match `status.md`'s "NOT enforced" section and §9.3.1: state what is not true first.

### 10.1 What RG-2 does not stop

1. **Exfiltration through the model API.** The control plane must stay open. Data can be encoded into
   model requests or into text the operator reads. Bounded by a per-engagement key and spend cap; not
   prevented. Do not claim otherwise.
2. **Social engineering of the operator through findings and reports.** §3.3 reduces the surface; it
   cannot close it, because a deliverable exists to be read and acted on. This is the highest-severity
   residual in the system and it is procedural, not architectural.
3. **Harm to an in-scope target.** Containment governs *destinations*, not blast radius at a permitted
   destination. Deleting client data, exhausting a rate limit, corrupting a production record — all
   fully reachable inside the allowlist. The ceiling, canary and loop controls remain in-guest
   heuristics. **The firewall does nothing for this class**, and this is the class a client is most
   likely to assume it covers.
4. **Shared-hosting collateral.** An allowlist entry is an IP. Cloudflare, Vercel, Fly and Supabase
   put many tenants behind one address, so the allowlist is coarser than the scope. Host-header
   restriction at the proxy narrows plain HTTP; it does nothing for tunnelled TLS.
5. **DNS rebinding and post-resolution IP change.** Rules are built from IPs resolved at provision
   time. A target controlling its own DNS can aim RedGold at an address that was allowlisted when
   resolved. Re-resolve on a schedule and log every change; the residual stands.
6. **A VMware hypervisor escape.** Rated low, but it is now the single assumption the whole
   architecture rests on. It replaces "the agent must not escape a container" with "the agent must not
   escape a VM" — a much better bet, and still a bet.
7. **Anything at all if the operator runs the workload on their own workstation.** The entire argument
   depends on `rg-work` being a disposable clone. `hiranya` is in group `sudo`; running the agent
   there defeats the design regardless of what nftables says. Given §9's step 0, **this is the most
   likely way the system fails in practice** — not by being defeated, but by not being used.
8. **`scope_guard.py` is not improved by any of this.** It remains a heuristic (§9.3.1) and its
   client-facing description does not change. What changes is that its failures are now caught by a
   layer beneath it rather than being the last word.
9. **The guest→host channel is a `[VERIFY]` until §4.5's checks pass on the actual template.** Until
   then, treat the boundary as unproven for non-network escape paths.

### 10.2 The claim today — unchanged

Until `rg-gw` is enforcing, the permitted sentence remains exactly what §9.9 sets:

> **"Out-of-scope targets are refused by tooling and logged."**

Never *"cannot happen."* And note that even this sentence is **currently ahead of the code on one
word**: nothing is logged today (§5.0). Until step 1 of §9.1 lands, the accurate sentence is *"refused
by tooling"* — the "and logged" clause is earned by a two-to-three-hour change and should be made
true rather than dropped.

### 10.3 What upgrade this earns, and the preconditions

**Preconditions — all of them, verified for the specific engagement being described:**

1. `rg-gw` is enforcing, with a ruleset generated from that engagement's `scope.yaml`.
2. `rg-work` is a disposable clone with exactly one NIC and no route except through `rg-gw` — §4.5
   checks 6, 7 and 8 pass, with check 8 confirmed on the *gateway-side* log.
3. The agent runs as a non-sudo user in a `--cap-drop=ALL` container with root-owned controls.
4. §4's `.vmx` keys are set and checks 1–5 pass.
5. `scope_guard.py` emits allow and deny rows, and `rg-reconcile` has run **clean on at least one real
   engagement** — with the halt behaviour enabled, not report-only.

**The sentence the operator may then say, in full:**

> "Network traffic from the testing environment is filtered by a firewall running on a separate
> machine that the testing environment has no account or access path to. Traffic to destinations
> outside your authorised scope is dropped there — whatever command the agent runs, and however it is
> constructed. The agent's cooperation is not required. Every blocked destination is logged outside
> the testing environment and reconciled against the agent's own decisions at engagement close. Two
> limits you should know: the agent's connection to its model provider necessarily stays open, and
> where your systems share an IP address with other tenants the filter is coarser than your scope.
> This bounds what can be reached; it is not a proof of impossibility."

Every clause is defensible sentence by sentence, and each maps to something verifiable: clause 1 to
precondition 2, clause 2 to precondition 1, clause 4 to precondition 5, and the two stated limits to
§10.1 items 1 and 4.

**What may still not be said, even then:**

- *"The agent cannot reach anything out of scope."* — §10.1 items 4, 5 and 6.
- *"Your data cannot leave."* — §10.1 item 1.
- *"Nothing can go wrong on your production system."* — §10.1 item 3, which is the most likely
  misreading of the permitted sentence and should be pre-empted in the same breath.
- Anything at all about production posture from a non-production engagement — §8.1.
- **The permitted sentence while the gateway is a container on the same kernel.** That would be the
  exact overstatement §9.3.1 says is worse than having no control at all.

### 10.4 The intermediate claim, for the period between steps

Because the build is sequenced, there is a real window where more is true than §10.2 says and less
than §10.3 permits. One intermediate sentence is available once steps 1, 2 and 8 are done but the
gateway is not:

> "Out-of-scope targets are refused by tooling, every allow and deny decision is written to an
> immutable-append log, and the testing environment is a disposable VM with no shared folders,
> no host clipboard and no guest-to-host management channel."

That is true, checkable, and materially weaker than §10.3 — it claims *refusal and recording*, not
*enforcement outside the blast radius*. Use it, and do not let it drift toward the stronger one.

---

## 11. Open items marked `[VERIFY]`

Ordered by how much each would change this document.

1. **Total RAM on the Mac host** — decides whether the three-VM topology is feasible at all
   (§9 step 0). Assume replace-not-add until answered.
2. **Whether VMware Fusion on Apple Silicon honours each `.vmx` key in §4.3.** Sources are
   vSphere/Workstation documentation. Test by attempting each operation from inside the guest as
   `redgold`. Any key not demonstrated is treated as not set.
3. **Whether `gueststore` and `upgrade` RPCs are reachable by a non-root guest user**, and whether
   `guest_rpc.rpci.auth.cmd.*` keys exist beyond `info-get`/`info-set`. The `info-get`/`info-set`
   default (`FALSE`, i.e. unrestricted) is **verified**; the rest is not.
4. **Whether the aarch64 backdoor transport is reachable from unprivileged userspace (EL0)** on
   Fusion/Apple Silicon. Sourced today only from patent text, which is not a product-behaviour source.
5. **Whether `api.anthropic.com` resolves inside the published `160.79.104.0/23` range or to
   Cloudflare anycast.** The published CIDRs are primary-sourced; the anycast claim is community
   reporting. The CONNECT-proxy design is deliberately independent of the answer.
6. **nftables time-based matching in the packaged version** (§8.2 item 2). Prefer the scheduled
   ruleset swap if unresolved.
7. **The RedGold toolchain under gVisor `runsc`** with `--net-raw=false` (`ffuf`, `nuclei`, `sqlmap`,
   `httpx`). Determines whether step 11 is a free win or a regression.
8. **`pf` on macOS filtering Fusion vmnet traffic pre-NAT** — needed only if the no-gateway-VM
   fallback is taken. Community-sourced today.
9. **`~768 MB` sizing for `rg-gw`** — a round number with no stated basis. Verify by building.
10. **vmci/vsock module and device names on aarch64 Debian/Kali** before hard-coding §4.5 check 3.
11. **The OCSF class most appropriate for security-testing activity** — outstanding from §9.11 and
    unchanged here. Field names in §5.1 should be re-checked against it before they spread further.

---

## Sources

- [Broadcom KB 377294 — accessing a GuestInfo variable from the guest OS fails with "Permission denied"](https://knowledge.broadcom.com/external/article/377294/accessing-or-modifying-a-guestinfo-vari.html)
- [Broadcom KB 377267 — modifying a cloud-init GuestInfo variable from the guest OS fails](https://knowledge.broadcom.com/external/article/377267/modifying-a-cloudinit-guestinfo-variable.html)
- [Broadcom TechDocs — Security considerations to configure VMware Tools](https://techdocs.broadcom.com/us/en/vmware-cis/vsphere/tools/12-3-0/vmware-tools-administration-12-3-0/configuring-vmware-tools-components/using-vmware-tools-configuration-file/security-considerations-to-configure-vmware-tools.html)
- [Broadcom TechDocs — Configuring guest isolation options for a virtual machine (Workstation Pro 17)](https://techdocs.broadcom.com/us/en/vmware-cis/desktop-hypervisors/workstation-pro/17-0/using-vmware-workstation-pro/configuring-virtual-machine-option-settings/configuring-guest-isolation-options-for-a-virtual-machine.html)
- [vmware/open-vm-tools issue #690 — vmware-rpctool permission denied, privileged-port identification](https://github.com/vmware/open-vm-tools/issues/690)
- [vmware/open-vm-tools — `lib/backdoor/backdoorGcc64_arm64.c`](https://github.com/vmware/open-vm-tools/blob/master/open-vm-tools/lib/backdoor/backdoorGcc64_arm64.c)
- [Anthropic — IP addresses](https://platform.claude.com/docs/en/api/ip-addresses)
- [Anthropic — Workspaces](https://platform.claude.com/docs/en/manage-claude/workspaces)
- [Anthropic — Rate limits](https://platform.claude.com/docs/en/api/rate-limits)
- [nftables wiki — Logging traffic](https://wiki.nftables.org/wiki-nftables/index.php/Logging_traffic)
- [Netfilter logging framework and nftables (Regit)](https://home.regit.org/2014/02/nftables-and-netfilter-logging-framework/)
- [VMware — Fusion and Workstation now free for all users](https://blogs.vmware.com/cloud-foundation/2024/11/11/vmware-fusion-and-workstation-are-now-free-for-all-users/)
- [Broadcom KB 368667 — download and license VMware Desktop Hypervisor](https://knowledge.broadcom.com/external/article/368667/download-and-license-vmware-desktop-hype.html)

Local code references are to this repo at the time of writing: `scripts/scope_guard.py:76-79`,
`:136-148`, `:600-618`, `:672-676`, `:687`, `:734-755`; `scripts/scope_cli.py:89-93`;
`scripts/gate_cli.py:81-85`. Environment facts about this host are carried from
`docs/research/containment-architecture.md` §0 and were verified there on 2026-08-20.
