---
title: Lab topology, Kali packaging, selective TLS interception, and log aggregation
date: 2026-08-20
status: draft
question: Can RedGold keep Kali without keeping the Kali VM; is a mini-PC lab better than laptop VMs; does splitting target traffic from the API channel make external request-rate limiting a real boundary; and how do logs actually leave the contained environment?
spec_refs:
  - "docs/specs/rg2-containment.md §1.1, §3.5, §4.3, §5.4, §5.6"
  - "docs/specs/rg2-rate-control.md §2.4, §5.1"
  - "docs/specs/redgold/07-enforcement.md §9.9, §9.10, §9.11"
research_refs:
  - "docs/research/hypervisor-licensing-and-sizing.md §5, §6"
supersedes: nothing. Amends rg2-rate-control.md §2.4 — see §3.6.
---

# Lab topology, Kali packaging, selective TLS interception, and log aggregation

## Index

| § | Section |
|---|---|
| 0 | The four answers, up front |
| 1 | Kali in a container — the operator keeps Kali, loses only the VM |
| 2 | Mini PCs versus laptop VMs, against §9.10's six properties |
| 3 | Selective TLS interception — the split `rg2-rate-control.md` §2.4 missed |
| 4 | Log aggregation — the honest answer, and the forwarding design |
| 5 | Open items marked `[VERIFY]` |

---

## 0. The four answers, up front

**1. Kali containers exist, are official, are arm64, and are updated weekly. Use `kalilinux/kali-rolling` + `kali-linux-headless`.** Kali publishes five images under its own Docker Hub organisation, all multi-arch including `linux/arm64`, all pushed on the same weekly cycle (verified: every one of the five was last pushed 2026-08-16T04:2x, §1.1). Do **not** build a custom Debian-plus-selected-packages image; the operator's instinct that maintaining a custom Linux is hard is correct, and the official image removes the reason to.

The reframe that matters more than the image choice: **the operator is not losing Kali, they are losing a VM.** The 9.7 GiB Kali guest is a *delivery mechanism* for Kali's tooling. A Kali container inside `rg-work` delivers the same tooling. `rg2-containment.md` already puts a rootless container inside `rg-work`; the only open question was what goes in it, and the answer is "official Kali". "Replacing the Kali VM defeats the purpose" is true if the purpose is the VM and false if the purpose is the tools.

**2. Start on laptop VMs. Buy mini PCs when the second concurrent engagement happens, not before.** The mini-PC lab is genuinely better on four of §9.10's six properties and it is the right end state — but it fails property 6 (cheap enough for a solo operator to actually use) *today*, not on money (roughly $600–900 buys a workable two-box lab, §2.3) but on **elapsed time before the first engagement can run**. The laptop plan needs one Fusion template; the hardware plan needs a firewall box, a switch, an OS install, a provisioning path, and a reimaging story, and none of that produces a client deliverable. The honest sequencing is: build the topology on Fusion where iteration is cheap, and port it to hardware once it is stable and the constraint is concurrency rather than correctness.

**3. Yes. Selective TLS interception makes external request-rate limiting a real boundary — and `rg2-rate-control.md` §2.4 is wrong in its general form.** The operator's instinct is right and the spec conflated two flows with completely different sensitivity. Intercepting the *target* channel is standard pentest practice and leaks nothing RedGold is keeping from itself; the *Anthropic API* channel stays a plain `CONNECT` tunnel and is never bumped. Both mitmproxy (`allow_hosts` / `ignore_hosts`) and Squid (`ssl_bump peek` then `splice`/`bump` on an `ssl::server_name` ACL) implement exactly this split, verified from their own documentation (§3.2). This converts "permanently unenforceable" into a boundary **for HTTP request rate against bumped destinations**, which is the majority of RedGold's actual traffic.

It is not free, and the price is not certificate handling — that is easy. **The price is that every finding about the target's TLS is now a finding about the proxy's TLS**, so `testssl.sh`, certificate-validity checks, cipher-suite findings and HSTS observations must be routed around the bump or they will produce fabricated results (§3.4). That carve-out is manageable because it is a small, enumerable set of tools, and it must be a *register*, not a habit.

**4. We pray. There is no aggregation today, and the operator's suspicion is exactly right.** Ledgers are JSONL files inside the engagement directory on the machine that generates them; `scope_guard.py` began emitting decision rows at `c0a20bd`, four commits ago; §9.11 says in as many words *"Emit the envelope; ship no forwarder."* Nothing leaves any VM except by the manual `vmrun copyFileFromGuest` pull at teardown (`rg2-containment.md` §3.4 step 6).

The design in §4 is **pull, never push**, and it rests on a distinction the forwarding question usually elides: **there are two logs with opposite trust properties, and only one of them needs a forwarder at all.** The gateway log is trustworthy and the gateway is not the untrusted side — shipping it is ordinary telemetry. The workload log is attacker-influenced text written by the thing being contained, and it is *evidence, not proof*; it should be pulled on the same path and under the same rules as findings (`rg2-containment.md` §3.3), because it is the same class of object. A forwarder pushing from `rg-work` to the coordinator would be a *new outbound channel from the untrusted side*, invented for the convenience of telemetry, and it would be the second-worst thing in the architecture after the API channel.

---

## 1. Kali in a container — the operator keeps Kali, loses only the VM

### 1.0 Restating the objection precisely

> *"If you can't fit everything unless the Kali VM is down, doesn't that defeat the purpose? I guess
> we can use a stripped down Linux and put Kali tools on it, but then we are also maintaining our own
> custom Linux container which seems hard."*

Two claims are bundled here and they separate cleanly.

The first — *"turn off your workstation to run an engagement" is a bad answer* — is correct as
stated and is not what `hypervisor-licensing-and-sizing.md` §5.5 actually concluded. That section's
arithmetic says the **9.7 GiB allocation** cannot coexist with `rg-work`. It does not say Kali cannot.
The guest is over-allocated for what it does: `rg-work` at 6 GB runs the same toolchain with 3.7 GiB
to spare, and the operator ends up *better off in RAM than today*.

The second — *maintaining a custom Linux is hard* — is also correct, and is the reason the third
option below is rejected. But it only bites if a custom image is necessary, and it is not.

### 1.1 What Kali actually publishes — verified

Kali's own container documentation
([Official Kali Linux Docker Images](https://www.kali.org/docs/containers/official-kalilinux-docker-images/)):

> "Kali provides official Kali Docker images that are updated once a week on Docker Hub."

> "All the images below do not come with the 'default' metapackage. You will need to
> `apt update && apt -y install kali-linux-headless`."

The Docker Hub `kalilinux` organisation contains exactly five repositories, and their manifests were
read from the Docker Hub v2 API on 2026-08-20:

| Repository | Purpose (Kali's words) | arm64 manifest | arm64 compressed size | Last pushed | Pulls |
|---|---|---|---|---|---|
| `kalilinux/kali-rolling` | "the main image that you should likely use" | **yes** | **52,628,510 B (~50.2 MiB)** | 2026-08-16T04:22:28Z | 9,075,721 |
| `kalilinux/kali-last-release` | tracks the last versioned release | **yes** | 52,212,322 B (~49.8 MiB) | 2026-08-16T04:22:02Z | 449,043 |
| `kalilinux/kali-dev` | dev repository, for developers | **yes** | 52,615,081 B (~50.2 MiB) | 2026-08-16T04:21:10Z | 78,170 |
| `kalilinux/kali-bleeding-edge` | bleeding-edge repository | not read this pass | — | 2026-08-16T04:20:24Z | 175,466 |
| `kalilinux/kali-experimental` | experimental repository | not read this pass | — | 2026-08-16T04:19:53Z | 43,182 |

Each of the three manifests read carries four architectures — `amd64`, `arm64`, `386` and `arm`
(32-bit) — all marked `active`. **`linux/arm64` is available and is not an afterthought**, which is
the load-bearing fact for Apple Silicon, where Fusion runs arm64 guests only
(`hypervisor-licensing-and-sizing.md` §1.3).

Three observations that are worth more than the numbers:

1. **All five repositories were pushed within 2 minutes 36 seconds of each other**, four days before
   this document's date. That is a single automated pipeline on a weekly trigger, not five images
   maintained by five people at five cadences. It corroborates the documented "once a week" claim with
   independent evidence rather than repeating it.
2. **The publisher is the Kali project itself**, from its own documentation, pointing at its own
   Docker Hub organisation. This is not a third party repackaging Kali, which is the failure mode the
   operator was right to worry about.
3. **~50 MiB compressed is a base, not a toolkit.** The image is a bootstrapped Kali root filesystem
   with the Kali apt repository configured and *no tools*. The tools arrive from `apt`, which is what
   makes the next section the real decision.

### 1.2 The metapackage structure — and one number that is not what it looks like

From Kali's metapackage documentation
([Kali Metapackages](https://www.kali.org/docs/general-use/metapackages/)) and the `kali-meta` source
package page ([kali-meta](https://www.kali.org/tools/kali-meta/)):

| Metapackage | Kali's description |
|---|---|
| `kali-linux-core` | "Base Kali Linux System – core items that are always included" |
| `kali-linux-headless` | "Default install that doesn't require GUI" |
| `kali-linux-default` | the tools on the default desktop images |
| `kali-tools-web` | "Designed doing web applications attacks" |
| `kali-tools-information-gathering` | "Used for Open Source Intelligence (OSINT) & information gathering" |
| `kali-tools-vulnerability` | vulnerability assessment tools |

**A trap worth naming.** The `kali-meta` page lists `kali-linux-headless` with an **"Installed size:
13 KB"**. That is the metapackage — a control file and a dependency list — **not the closure**.
`kali-linux-headless` pulls on the order of 150+ packages including `metasploit-framework`, which
alone is large. `[VERIFY]` **the actual on-disk closure of `kali-linux-headless` on arm64; Kali
publishes no figure for it and none was found this pass.** Do not put "13 KB" in a sizing table; it
would be a fabricated benchmark number in the exact sense hard rule 2 prohibits, arrived at by quoting
a real number that answers a different question.

### 1.3 The three ways to get Kali tools into `rg-work`, compared

| | **A. Official `kali-rolling` + `kali-linux-headless`** | **B. Official `kali-rolling` + named `kali-tools-*` only** | **C. Debian base + Kali repo + hand-picked packages** |
|---|---|---|---|
| Base provenance | Kali project, weekly | Kali project, weekly | Debian, plus a third-party apt source RedGold configures |
| Tool selection | Kali's, curated by Kali | Kali's group curation, subset chosen by RedGold | RedGold's, package by package |
| Image size | Largest — includes wireless, password-cracking, forensics tools RedGold does not use | Middle | Smallest |
| Who owns "does this tool work" | Kali | Kali | **RedGold**, for every interaction between Debian's libraries and Kali's builds |
| Maintenance on upgrade | `docker pull`; the pipeline already tested it | `docker pull` + confirm the group still contains what the playbook names | **Every Kali package upgrade is an unowned integration test.** Mixing suites is a documented way to break a Debian system |
| Reproducibility | Tag is `latest`-only; pin by digest | Same | Same, plus a second suite to pin |
| Failure mode | Bloat | A group is renamed or re-scoped and a tool silently disappears | Dependency conflict at 11pm mid-engagement, in a component nobody upstream supports |

**C is the option the operator was dreading, and they were right to dread it.** The specific hazard is
not "it's a lot of work" — it is that mixing Debian and Kali suites creates a system whose failures
are *nobody's*. Kali is itself a Debian derivative with its own versions of shared libraries; a
Debian base with the Kali repo bolted on is a configuration neither project tests. When
`sqlmap` breaks against a Python version Kali did not ship it with, there is no upstream to ask.

**Recommendation: A, with B as a deliberate later optimisation and only if disk actually bites.**

Reasoning, stated so it can be argued with:

- **The maintenance burden of A is `docker pull` and a digest pin.** That is the whole thing. Every
  other option adds a curation task that recurs on every upgrade, forever, and recurs *silently* —
  the failure is a missing tool, and a missing tool in a scan looks like a clean result. That is a
  finding-integrity failure (RG-1 §8.1's coverage register exists for exactly this), not a
  convenience failure, which is what raises it above a taste question.
- **Design judgement 1 (do not design from n=1) cuts toward A.** B requires knowing now which tool
  groups RedGold needs across all future engagements. RedGold has one engagement of history. Choosing
  the narrow set today is fitting the image to the first target's shape.
- **Design judgement 4 (a control nobody is forced to run is not a control) applies to curation.** B's
  saving depends on someone re-auditing the group contents each upgrade. Nobody will.
- **A's cost is disk, and disk is the resource `hypervisor-licensing-and-sizing.md` §6 says actually
  bites.** This is the real tension. It is resolved by *moving where the bulk lives*, not by shrinking
  it: see §1.4.

### 1.4 What this does to the sizing arithmetic — the part that answers the objection

The container changes the shape of `rg-work`, and the change is in the operator's favour on both
resources.

**`rg-work` becomes a thin host.** Its VM disk carries Debian arm64 (Debian documents 4 GB for a
no-desktop install), a rootless container runtime, and the image store. The scanner toolchain lives
*in the image*, not in the guest filesystem. Three consequences:

1. **The base template shrinks and the per-engagement clone shrinks more.** The 40 GB `rg-work`
   template in `hypervisor-licensing-and-sizing.md` §6 was sized as "Kali default install plus
   scanners installed into the guest". With the toolchain in a pulled image, the template is a small
   Debian plus an image cache, and each engagement's linked clone diverges only by what the
   engagement writes. `[VERIFY]` the real closure size before restating a number (§1.2).
2. **Reprovisioning stops being a VM operation.** A corrupted toolchain is `docker rm` and a re-pull,
   not a `revertToSnapshot`. The snapshot path remains for the *engagement*, which is what §9.10
   property 5 is about.
3. **`--cap-drop=ALL` and the read-only plugin mount, which `rg2-containment.md` §2 already
   specifies, now apply to a supported image rather than a hand-built one.** The hardening posture is
   unchanged; only the thing being hardened is now maintained by someone else.

**RAM does not change, and it was never the container's problem.** The container shares the guest
kernel and the guest's RAM. `rg-work` still wants 6 GB, and the reason the existing guest must stop
running is still that 9.7 + 6 + 0.75 exceeds 16 GB. **What the container changes is what the operator
loses when it stops: nothing they were using.** Kali's tools remain available, one `docker run` away,
in a supported image, in the environment where the work is actually authorised to happen.

That is the direct answer to "doesn't that defeat the purpose". The purpose was the tools. The tools
survive. The 9.7 GiB VM was the packaging.

### 1.5 One honest limit on the container answer

A container is not a substitute for the VM boundary and must not be described as one.
`rg2-containment.md` §1.1 grades the rootless container **defence-in-depth (strong)**, and three runc
CVEs in November 2025 are already on the record there. Using an official Kali image improves *supply
chain and maintenance*; it changes nothing about isolation. The boundary is still `rg-gw`, on a
different machine, and the container escape is still survivable only because of that.

Pin by digest, not by `latest`. Kali ships one moving tag per repository (the API returns `latest`,
`amd64` and `i386` as the only tags on `kali-rolling`), so a digest pin recorded in `provision.json`
is the only way an engagement can state *which* toolchain produced its findings. An engagement that
cannot name its toolchain version cannot be reproduced, and RG-1's whole posture depends on findings
being reconstructible.

---

## 2. Mini PCs versus laptop VMs, against §9.10's six properties

> *"I might buy a couple of mini PCs to run in a home lab, so each mini PC can be its own engagement
> behind a firewall and being logged."*

This is not a variation on the laptop plan. It is a different architecture with different failure
modes, and it deserves to be graded rather than praised. The short version: **it is better on the
properties that describe the boundary, worse on the property that describes whether the boundary ever
gets built, and it unlocks one thing the laptop cannot buy at any price — concurrency.**

### 2.1 The six properties, graded side by side

§9.10's required properties, in its own priority order.

| # | Property | Laptop VMs (`RG-CONTAIN-1` on Fusion) | Mini-PC lab | Winner |
|---|---|---|---|---|
| 1 | Egress filtering enforced by a principal the workload cannot become | `rg-gw` is a separate VM on the same hypervisor. Strong — but the hypervisor is a shared component, and a Fusion escape reaches both | A separate **physical** box with its own CPU, kernel and NIC. There is no shared hypervisor to escape. The workload's packets reach the filter over a wire | **Mini PC**, and by more than a little. This is the property the whole design exists for |
| 2 | Workload cannot reconfigure its own network namespace | Same in both: no sudo, no `CAP_NET_ADMIN` | Same, plus: the physical uplink is a cable into a port on a box the workload has no account on | Tie, edge to mini PC |
| 3 | Rules derived from `scope.yaml`, regenerated per engagement, from outside | `nft -f` pushed from the macOS host | `nft -f` pushed to the firewall box over its management interface | **Tie** — identical mechanism, and that is the point: the generator does not care |
| 4 | Full egress logging outside the workload, reconcilable | ulogd2 on `rg-gw`; log lives on the same SSD as the guest that produced the traffic | ulogd2 on the firewall box; log lives on hardware the work box cannot address | **Mini PC.** §4's whole trust argument gets easier |
| 5 | Snapshot/restore — the environment is disposable | **`vmrun revertToSnapshot`, seconds, scriptable, already in the spec** | Reimaging a physical machine is minutes-to-tens-of-minutes and needs a mechanism that does not exist yet (PXE, an image-restore partition, or a hypervisor *on* the mini PC) | **Laptop, decisively.** See §2.4 |
| 6 | Cheap enough for a solo operator to run per engagement | Zero marginal cost. Fusion is free (`hypervisor-licensing-and-sizing.md` §1) | ~$600–900 capital (§2.3), plus power, space, and a build project | **Laptop today.** The money is not the problem; the build is |

**Read the table honestly and it does not say "mini PCs win".** It says the mini-PC lab is better at
being a boundary and worse at being disposable — and disposability is property 5, not property 7. A
lab that cannot cheaply return `rg-work` to a known-clean state has traded a strong property for a
stronger one and *lost* on net, because a contaminated environment carried into the next engagement is
a client-data-handling failure as well as a security one.

### 2.2 The resolution: put a hypervisor on the mini PC, and property 5 comes back

The obvious fix is the right one, and it is what makes the mini-PC plan actually viable rather than
merely appealing. **An x86-64 mini PC restores every option Apple Silicon removed.**
`hypervisor-licensing-and-sizing.md` §3.1 disqualified Proxmox on two grounds — architecture
(`"CPU: 64-bit x86 (Intel 64 or AMD64)"`, per [Proxmox VE System
Requirements](https://pve.proxmox.com/wiki/System_Requirements)) and topology (a type-1 hypervisor
owns the machine, and on the laptop that machine is the control tier). **On a dedicated mini PC both
objections evaporate.** Proxmox owning the box is exactly what you want when the box's only job is to
host engagements, and the control tier stays on the operator's Mac where it belongs.

That gives the mini-PC plan:

- **Property 5 back**, in a stronger form than Fusion offers: Proxmox linked clones and snapshots,
  plus templates, plus scripted `qm clone` / `qm rollback`.
- **KVM instead of Fusion**, i.e. a hypervisor with a supported open-source lineage rather than a free
  binary with no support entitlement (`hypervisor-licensing-and-sizing.md` §8's honest limit).
- **Firecracker and Kata as real options**, not just names in §9.10's table. Both are x86-64-first.
  They are *not* recommended for RedGold's toolchain — a scanner workload wants a general-purpose
  guest, and `rg2-containment.md` §2.6 already argues that spending days narrowing kernel surface is
  the wrong trade when the escape is already survivable — but the option existing is worth recording.

**So the honest comparison is not "laptop VMs vs mini PCs". It is "Fusion on the laptop" vs "Proxmox
on a dedicated box".** Framed that way the mini-PC plan wins properties 1, 2, 4 and 5, ties on 3, and
loses only 6.

### 2.3 Cost, realistically

Verified vendor prices, read 2026-08-20. Everything here is a list price from the manufacturer's own
store; street prices vary and the operator should confirm before buying.

| Role | Candidate | Verified price | Source |
|---|---|---|---|
| Firewall / gateway (`rg-gw` in hardware) | Protectli Vault Pro VP2420 — "Intel Celeron® J6412 Quad Core at 2 GHz", "4 Intel® 2.5 Gigabit Ethernet NIC ports", fanless, AES-NI | **€339,00** | [eu.protectli.com VP2420](https://eu.protectli.com/product/vp2420/) |
| Engagement host | Minisforum MS-A1 (barebone, no CPU/RAM/SSD) | **$235.00** | [minisforum.com](https://www.minisforum.com/collections/mini-pc) |
| Engagement host | Minisforum MS-A2, 64 GB RAM + 1 TB SSD, complete | **$575.90** | same |
| Engagement host | Minisforum MS-R1, 32 GB RAM + 1 TB SSD | **$503.90** | same |

Two notes on the sourcing, because the repo's rule is that a benchmark or price is cited or omitted:

- Protectli's own store notes the **VP2420 has been replaced by the VP2420e** (identical but without
  the eMMC module) and that the VP2420 is now large-volume only. The €339 figure is real and current
  on the EU store page as read; `[VERIFY]` the VP2420e's price and availability in the operator's
  region before ordering.
- **Beelink pricing was searched and deliberately not quoted.** The figures returned came from resale
  listings and review sites, not the manufacturer, and ranged $380–$525 for nominally the same
  machine. That is not a price, it is a rumour. If Beelink is being considered, read their store.

**A realistic first build: one engagement host and one gateway, ~$600–900 all-in** depending on
whether the gateway is a purpose-built fanless appliance (€339, silent, 4 NICs, no fan to fail) or a
second cheap mini PC with a USB-Ethernet adapter (cheaper, noisier, one more moving part). The
second engagement host is another ~$250–600 and is the purchase that actually buys concurrency.

**What the money does not buy, and this is the real cost:** the build. A firewall OS install, a
Proxmox install, network cabling, a management VLAN or a second interface, a provisioning path that
pushes rulesets from the Mac to the gateway box, and a reimaging story. Call it a weekend if
everything works and considerably more if it does not, and none of it produces a client deliverable.

### 2.4 Power, noise, space, and teardown

- **Power.** These are 15–65 W-class devices. Running two continuously is a rounding error on a
  domestic bill; that is not the constraint. `[VERIFY]` actual TDP figures against the specific SKUs
  if the operator wants a number — none was read this pass.
- **Noise and space.** The Protectli is explicitly fanless — *"The Vault is fanless so it has no moving
  parts"* — which matters if the lab shares a room with the operator. Mini PCs with fans are audible
  under a sustained scan. Two boxes plus a switch is a shelf, not a rack.
- **Reimaging.** With Proxmox on the box, teardown is `qm rollback` to a clean snapshot and is
  equivalent to the Fusion path. **Without a hypervisor on the box it is the plan's weakest point**
  and must be solved before the first engagement, not after: bare-metal reimaging needs PXE or a
  restore partition, and "I reinstalled it by hand" is not a disposability property, it is a chore
  that will be skipped once.
- **Engagement teardown, mechanically**, on the hardware plan: pull evidence and logs to the Mac
  (§4), `qm rollback` the engagement VM to `clean`, flush the engagement's ruleset from the gateway
  and reload the default-deny base, revoke the API key. That is the same six-step shape as
  `rg2-containment.md` §3.4 with `vmrun` swapped for `qm` — which is itself an argument that the two
  plans are the same architecture on different metal, and porting is not a redesign.

### 2.5 Verdict — laptop first, and the trigger for moving

**Recommendation: build `RG-CONTAIN-1` on Fusion now. Move to hardware when a specific trigger fires,
not on a date.**

The case for starting on the laptop is not that it is better. It is that:

1. **The topology is the deliverable, and it is identical on both.** Default-deny nftables from a
   generated ruleset, an allowlist resolver, a CONNECT proxy, ulogd2 into the §9.11 envelope, a
   disposable work environment. Every one of those is built once and runs on either substrate. Getting
   them *right* is the hard part, and iterating on a laptop VM is minutes per cycle against tens of
   minutes on hardware.
2. **Design judgement 6 applies directly** — *implementation finds what review misses*. The fastest
   path to discovering what is wrong with this architecture is running it, and Fusion is the fastest
   path to running it. Buying hardware first converts an unknown design into an unknown design with
   cables.
3. **Property 6 is a hard requirement, not a preference.** `rg2-containment.md` §6.4 already killed
   the honeypot proposal on property 6 alone. The same standard has to apply to a purchase the
   operator wants to make, or it is not a standard.

**The triggers that say "buy now":**

| Trigger | Why it is the right moment |
|---|---|
| **Two engagements need to run concurrently** | The laptop cannot do this at all. 16 GB does not hold two `rg-work` guests, and mixing two clients' data in one guest is a paperwork violation before it is a security one. This is the strongest trigger and it is a *business* signal, not a technical one |
| **An engagement needs an x86-64 guest** | Fusion on Apple Silicon runs arm64 guests only (`hypervisor-licensing-and-sizing.md` §1.3). A client's own container image, an x86 binary, an appliance VM — any of these ends the laptop plan for that engagement |
| **A client asks where their data lives, and "my laptop" is the true answer** | Dedicated hardware in a locked room is a materially better answer, and at some point it becomes a sales requirement rather than an engineering preference |
| **Free SSD stays under ~100 GB** | `hypervisor-licensing-and-sizing.md` §6 flags disk as the resource that actually bites. A mini PC with a 1 TB SSD solves it more permanently than an external NVMe |

**And one anti-trigger, stated so it is not mistaken for caution:** do not buy hardware because the
laptop plan feels cramped. Cramped is survivable. The purchase is justified by concurrency, by
architecture mismatch, or by a client, and by nothing else.

---

## 3. Selective TLS interception — the split `rg2-rate-control.md` §2.4 missed

> *"About not being able to rate limit, isn't that why we put the high risk agent behind something
> like nginx so that we can rate limit it externally?"*

**The operator is right, the spec is wrong in its general form, and the error is identifiable.** This
section states the error, verifies the mechanism, prices it honestly, and proposes the amendment.

### 3.1 The error, precisely

`rg2-rate-control.md` §2.4 reasons in three steps:

1. nftables sees connections, not requests. **Correct, and unaffected by anything below.**
2. A CONNECT proxy without TLS interception sees `CONNECT host:443` and a byte count. **Correct.**
3. Therefore *"Request-rate enforcement outside the workload is unavailable by construction, unless
   the design accepts TLS interception. It should not."*

**Step 3 smuggles in a quantifier.** The reason interception "should not" be accepted is imported
from `rg2-containment.md` §3.5, and that reason is specific and narrow:

> "**no TLS interception** (interception would write the operator's API key into a proxy log, which
> is strictly worse)"

That objection is entirely about **one destination** — `api.anthropic.com`. It is a decisive objection
*for that flow*. §2.4 then applies it to *all* flows, and in doing so treats "TLS interception" as a
single global setting. It is not. It is a per-destination policy decision, and every intercepting
proxy in the pentest ecosystem implements it as one.

**The two flows leaving `rg-work` have opposite sensitivity, and they should never have been governed
by one rule:**

| | **Anthropic API channel** | **Target channel** |
|---|---|---|
| Destinations | `api.anthropic.com` + Claude Code telemetry — a fixed, tiny, RedGold-controlled allowlist | The engagement's in-scope hosts, from `scope.yaml` |
| Contains | The operator's API key in an `x-api-key` header, on every request | The client's application traffic, which RedGold is **authorised in writing** to inspect |
| Secret from RedGold? | **Yes.** Logging it is the harm | **No.** Reading it is the job. Burp, ZAP and mitmproxy exist to do exactly this |
| Volume | Bounded by the model loop | Unbounded — this is the flow the fuzz budget is written about |
| Must be counted? | No. Bytes and duration suffice | **Yes. This is the entire requirement** |

The flow that needs counting is the flow that is safe to intercept. The flow that is unsafe to
intercept does not need counting. **The conflict §2.4 identified does not exist.**

### 3.2 The mechanism, verified

Both candidate proxies implement per-destination interception policy as a first-class feature.

**mitmproxy** — from its own options documentation
([Options](https://docs.mitmproxy.org/stable/concepts/options/)):

> `ignore_hosts`: "Ignore host and forward all traffic without processing it. In transparent mode, it
> is recommended to use an IP address (range), not the hostname. In regular mode, only SSL traffic is
> ignored and the hostname should be used. The supplied value is interpreted as a regular expression
> and matched on the ip or the hostname."

> `allow_hosts`: "Opposite of --ignore-hosts."

That is the split, expressed in one option. `--ignore-hosts '^api\.anthropic\.com$'` (or, safer,
`--allow-hosts` enumerating the scope) yields: API traffic tunnelled untouched, target traffic bumped.

**Squid** — from the SslBump feature documentation
([SslBump Peek and Splice](https://wiki.squid-cache.org/Features/SslPeekAndSplice),
[ssl_bump directive](https://www.squid-cache.org/Doc/config/ssl_bump/)). Squid's model is a
three-step state machine with `peek`/`stare` as non-final actions and `bump`/`splice`/`terminate` as
final ones; `ssl::server_name` ACLs may match on the CONNECT URI, the TLS client SNI, or the server
certificate subject. The idiom is: `peek` at step 1 to learn the SNI, then `splice` the named
exceptions and `bump` the rest.

**Which to use.** mitmproxy, for three reasons: the per-request programmability is the thing RedGold
actually needs (§3.3), the addon API is Python — the same language as `scope_guard.py` and the ledger
helpers, so the envelope emitter is shared code — and Squid's ssl_bump configuration is notoriously
easy to get subtly wrong. Squid's advantage is maturity as a forward proxy under load; that is not
RedGold's binding constraint at 5 requests per second.

**Why this makes the count real.** Once bumped, the proxy sees individual HTTP requests — including
requests multiplexed onto one connection over HTTP/2 and requests reusing a keep-alive connection,
which is precisely what §2.4 correctly said the packet filter cannot see. mitmproxy's addon model
gives a `request` hook per request ([Addon overview](https://docs.mitmproxy.org/stable/addons/overview/)),
so a ~40-line addon can maintain a token bucket per `(engagement_id, host)`, emit an `egress.request`
row in the §9.11 envelope, and — critically — **it runs on `rg-gw`, a machine the workload has no
principal on.** That satisfies §9.10 property 1 for request rate, which nothing in RedGold currently
does.

### 3.3 What it costs — certificate handling is the easy part

**The CA.** mitmproxy generates its own CA on first run
([Certificates](https://docs.mitmproxy.org/stable/concepts/certificates/)):

> "The first time mitmproxy is run, it creates the keys for a certificate authority (CA) in the config
> directory (`~/.mitmproxy` by default)."

> "For security reasons, the mitmproxy CA is generated uniquely on the first start and is not shared
> between mitmproxy installations on different devices."

Three requirements follow, and they are template-build tasks, not per-engagement work:

1. **The CA is generated on `rg-gw` and its private key never leaves `rg-gw`.** Only
   `mitmproxy-ca-cert.pem` — the certificate, not the key — is installed into the `rg-work` template
   and into the Kali container image (`/usr/local/share/ca-certificates/`, then
   `update-ca-certificates`).
2. **The workload gets a trust anchor it does not control.** This is a genuine, if small, addition to
   the workload's attack surface *against itself*: a compromised `rg-gw` could impersonate any site to
   `rg-work`. Since `rg-gw` already decides whether any packet leaves at all, this adds no capability
   an adversary at that position lacked.
3. **`[VERIFY]` that the Go-based tools honour the system trust store on Kali arm64.** `nuclei`,
   `httpx`, `ffuf` and `subfinder` are Go binaries; Go's `crypto/x509` reads the platform trust store
   on Linux, but that was **not read from a primary source this pass**, and the failure mode —
   every HTTPS request failing verification, or worse, a tool silently falling back to
   `InsecureSkipVerify` and reporting nothing — is exactly the kind of silent degradation
   `rg2-containment.md` §2.5 warns about. Test it before relying on it; record the result in the
   coverage register either way.

**Certificate pinning.** mitmproxy's own documentation is blunt:

> "Some applications employ Certificate Pinning to prevent man-in-the-middle attacks. This means that
> **mitmproxy's** certificates will not be accepted by these applications without modifying them."

For RedGold this is largely a non-issue in the *tooling* — scanners do not pin — and a real issue in
one place: if the engagement's scope includes a mobile or desktop client that pins, that client cannot
be driven through the bump. The escape hatch is the same `ignore_hosts` mechanism, and the cost is
that traffic then falls back to being uncountable. **Record it as a coverage limitation, do not work
around it silently.**

**Non-HTTP and non-proxied traffic.** This is where the honest accounting lives:

| Tool / traffic | Goes through the proxy? | Countable? | Consequence |
|---|---|---|---|
| `curl`, `httpx`, `ffuf`, `nuclei`, ZAP, `sqlmap` over HTTP(S) | Yes, via `http_proxy`/`https_proxy` | **Yes** | The main win. This is most of RedGold's traffic |
| `nmap` (any scan type) | **No.** nmap speaks raw TCP/IP; it is not an HTTP client and does not use an HTTP proxy | No | Unchanged from today. nftables still governs it as connections. nmap's request volume was never the fuzz-budget problem |
| `testssl.sh` | Optionally — it documents `--proxy` and *"does ANY check via the specified proxy"*, but also that *"Authentication to the proxy is not supported, also no HTTPS or SOCKS proxy"* and that OCSP revocation checking *"is not supported by OpenSSL via proxy"* ([testssl.1.md](https://raw.githubusercontent.com/testssl/testssl.sh/3.2/doc/testssl.1.md)) | Irrelevant | **Must be spliced, not bumped.** §3.4 |
| HTTP/3 / QUIC | **No.** mitmproxy's own docs: *"QUIC is a UDP-based protocol, which means regular proxying via HTTP CONNECT only supports TCP"* ([mitmproxy 11](https://www.mitmproxy.org/posts/releases/mitmproxy-11/)) | No | Moot in practice: `rg-gw`'s default-deny drops `udp/443` anyway, which forces targets to TCP fallback. Worth stating because a target that is HTTP/3-only would be untestable |
| DNS | No — Unbound handles it | n/a | Already logged (`rg2-containment.md` §5.4) |

### 3.4 The decisive cost, and it is not the one anyone expects

**Every TLS-layer observation made through a bumped connection describes `rg-gw`, not the target.**

This is not a performance caveat. It is a finding-integrity failure of exactly the class RG-1 exists
to prevent, and it is worse than the honeypot problem `rg2-containment.md` §6.2 rejected — because a
honeypot produces a finding about a machine that is not the client's, whereas a bumped `testssl` run
produces a finding *about the client's host* that is *entirely false*, sourced from RedGold's own
proxy configuration.

Concretely, run through a bump, RedGold would report:

- the **proxy's** cipher suites and TLS versions as the target's;
- the **proxy's** certificate chain — self-signed by a private CA — as the target's, which would
  present as a critical certificate-validation finding on every engagement;
- **no** OCSP stapling, **no** certificate transparency, **no** HSTS preload behaviour that the target
  actually has;
- a wrong answer to every question `testssl.sh` exists to ask.

**Mitigation, and it must be structural rather than procedural:** the bump policy is generated from
`scope.yaml` alongside the nftables ruleset, and it carries an explicit **splice register** —
destinations and tools whose traffic is tunnelled rather than bumped. Two entries are permanent
(`api.anthropic.com`; any pinning client in scope) and one is tool-shaped: **`testssl.sh` and any
other TLS-property tool must run against a spliced path.** The cleanest implementation is a second
proxy listener on `rg-gw` that splices everything, reachable only by the wrapper that invokes those
tools, with its usage logged as a named exception.

And the rule that makes the register honest: **a spliced destination is an uncountable destination,
and every splice is a coverage limitation recorded in RG-1 §8.1's register** — never inferred from
absence. That is the same rule §2.5 of `rg2-containment.md` applies to capability-degraded scans, and
it generalises correctly here.

### 3.5 Verdict

**Selective TLS interception converts request-rate control from "permanently unenforceable" into a
real boundary, for the majority of RedGold's traffic, at a cost that is enumerable and manageable.**

The honest grading, in §1.1's vocabulary:

| Flow | Grade for request-rate control |
|---|---|
| HTTP(S) to bumped in-scope destinations | **BOUNDARY.** Counted and enforced on `rg-gw` by a principal the workload cannot become |
| HTTP(S) to spliced destinations (pinning clients, TLS-property tools) | **Cooperative only** — unchanged from today, and enumerated in the splice register |
| Raw-socket tools (`nmap`, packet crafting) | **Not applicable.** Governed as connections by nftables, as before |
| Anthropic API channel | **Deliberately unbumped.** Bytes and duration only, as `rg2-containment.md` §3.5 requires |

Two residuals that must not be lost in the upgrade:

1. **The workload can unset `http_proxy`.** `rg2-containment.md` §2.3 already grades the proxy
   environment variables as *hygiene, not a control*, and that is unchanged. What makes the bump a
   boundary rather than a suggestion is that **nftables must deny direct `tcp/443` egress from
   `rg-work` to everything except `rg-gw`'s proxy port.** Without that rule the whole of §3 is
   advisory. This is the single most important implementation note in the section.
2. **`rg2-rate-control.md` §5.6 still stands and is untouched by this.** Request count is a poor proxy
   for load; one expensive query can outweigh 1,500 fuzz requests. A boundary over request rate is not
   a boundary over harm.

### 3.6 The amendment to `rg2-rate-control.md`

Proposed, for the operator to accept or reject:

| Section | Change |
|---|---|
| **§2.4**, the block quote beginning *"Request-rate enforcement outside the workload is unavailable by construction"* | **Rewrite.** It is true only for unbumped flows. Replace with: *"Request-rate enforcement outside the workload requires TLS interception, and interception is a per-destination policy, not a global setting. The Anthropic API channel is never bumped — that objection is decisive for that flow. In-scope target destinations may be bumped, and RedGold is authorised in writing to inspect that traffic. Request rate is therefore enforceable at the gateway for bumped destinations and cooperative everywhere else."* |
| **§2.4**, grade line | Currently *"**Not a control at all** for request rate."* Becomes: **BOUNDARY** for request rate to bumped destinations; **not a control** for spliced destinations and raw-socket tools |
| **§2.0** table, row D | Add a row splitting the gateway into "gateway, unbumped" and "gateway, bumped" |
| **§5.1** honest limit | Currently *"Nothing in this design is a boundary over request rate. Nothing can be."* **This becomes false and must be replaced**, not softened. New form: *"Request rate is a boundary for bumped destinations and cooperative for the rest. The splice register names every exception, and every entry in it is a coverage limitation."* |
| **§5, new limit** | Add: *"A bumped connection's TLS properties are the proxy's, not the target's. Any finding about certificates, cipher suites, protocol versions or HSTS must come from a spliced path, or it is fabricated."* |
| **"What may be said to a client"** | May now add one clause: *"For most traffic, the request rate is enforced by a filter outside the testing environment, not only by the testing tools."* Do not overstate it — name the exceptions if asked |

**One caution before any of this is written into the spec.** `rg2-rate-control.md` §5.9 already warns
that a gateway rate limit *can manufacture a finding*, because from inside the guest a gateway drop is
indistinguishable from the target throttling. **A bumped proxy makes this worse, not better**, because
the proxy can return a synthetic `429` that looks even more like the target's. The rule stands and
hardens: any run that touches the gateway limit is an **invalid run**, its findings quarantined, and
the limit ships **report-only** until `rg-reconcile` has run clean on a real engagement.

---

## 4. Log aggregation — the honest answer, and the forwarding design

> *"Speaking of logging, do we actually aggregate logs of what is done? Or do we just pray? Wouldn't
> we need a forwarder to get things out of the VM to our coordinator box?"*

### 4.1 The straight answer: we pray. Here is exactly what exists

**Aggregation: none. Forwarding: none. Retention outside the machine that wrote it: none.**

What does exist, read from the code rather than from the documents describing it (design judgement 5):

| Artefact | Written by | Where it lives | Leaves the machine? |
|---|---|---|---|
| `ledger/activity.jsonl` | `scope_guard.py:record_decision()` — **new at `c0a20bd`, four commits ago** | Engagement directory, in the guest | No |
| `ledger/gates.jsonl` | `gate_cli.py:append_ledger()` | Engagement directory | No |
| `ledger/blockers.jsonl`, `ledger/cleanup.jsonl` | `findings.py`, `cleanup_gate.py` | Engagement directory | No |
| `ledger/resolution.jsonl` | control tier at provisioning | Written outside, mounted in | Inbound only |
| `egress.jsonl` on `rg-gw` | **specified in `rg2-containment.md` §5.4; not built** | `rg-gw` | n/a |

And §9.11 says it in as many words:

> "**Not built for v1.** Emit the envelope; ship no forwarder. A forwarder against a stable schema is
> an afternoon."

So: the envelope was decided, the emitters are landing, and the transport was consciously deferred.
That is a defensible sequence — it is exactly the "decide the schema now, build the pipe later"
argument — but the operator is right that the current state is *files on a box, and hope*. Worth
noting that `record_decision()` is already written to survive the transport being unreliable: a ledger
write failure prints `ledger.write_fail` to stderr and **does not block the tool call**, on the stated
reasoning that *"rg-reconcile will see the corr_id gap and treat the traffic as unattributed."* That
is the right failure posture and it presumes a reconciler that does not yet exist.

### 4.2 The distinction the question needs: two logs, opposite trust

`rg2-containment.md` §5.6 already states the asymmetry, and it is the whole design:

> "A workload that has escaped its container can forge `ledger/activity.jsonl`, because it writes it.
> The workload-side log is **evidence, not proof.** The gateway-side log is trustworthy because it is
> written on a machine the workload has no principal on."

That sentence answers the operator's implicit question — *what is the value of workload-side logs at
all?* — and the answer is more interesting than "not much":

**The workload log's value is that it is the only place intent lives.** The gateway sees
`10.77.0.20 → 198.51.100.5:443, 1,432 bytes`. It cannot know which agent, which asset, which tier,
which gate reference, or what the operation was. `activity.jsonl` carries all of that, and
`scope_guard.py` deliberately stamps `resolved_ips` from `ledger/resolution.jsonl` — *never* from a
live lookup — precisely so the two can be joined.

So the honest framing is not "trusted vs untrusted logs". It is:

| | Gateway log (`egress.jsonl`) | Workload log (`activity.jsonl`) |
|---|---|---|
| Written on | `rg-gw` — no workload principal | `rg-work` — the workload writes it |
| Forgeable by an escaped workload | **No** | **Yes** |
| Knows *what happened* | Yes, at the packet level | Only what the guard was told |
| Knows *why, and by whom* | No | **Yes — uniquely** |
| Value class | **Proof** | **Evidence, and the only narrative** |
| Trust on arrival at the coordinator | Telemetry | **Attacker-influenced text** |

**The consequence for forwarding: they are not the same kind of object and must not travel the same
way.** Treating `activity.jsonl` as telemetry — parsing it into a dashboard, feeding it to a model,
alerting on its `reason` field — is handing attacker-influenced strings to a system that acts on them.
`rg2-containment.md` §3.3 already wrote the rules for this class of object; the workload log is
covered by them and nobody noticed, because it looks like a log rather than a finding.

### 4.3 Push versus pull — pull, and the reason is not preference

**A push forwarder from `rg-work` is a new outbound channel from the untrusted side, created for
convenience.** It would need a permitted destination in the nftables ruleset, a live network path to
the coordinator, and a listener on the coordinator that parses whatever the workload sends. That is a
channel with the coordinator as the *server*, initiated by the *untrusted* party — the exact inversion
of every other trust relationship in the architecture. `rg2-containment.md` §3.1 already forbids the
mirror image of this (`rg-setup` "must never hold a live push channel into `rg-work` after handover")
and the reasoning transfers unchanged.

**Pull, and the direction of every arrow stays right:**

| | Push (workload initiates) | Pull (coordinator initiates) |
|---|---|---|
| Who opens the connection | The untrusted party | The trusted party |
| New egress allowlist entry needed | **Yes** — a permanent hole in the default-deny ruleset | **No.** Nothing new leaves |
| Coordinator's exposure | Runs a listener that parses untrusted input, continuously | Reads a file when it chooses to |
| Availability if the workload is compromised | The workload can just stop pushing, silently | The coordinator notices the pull failed, or that the file stopped growing |
| Buffering | Workload-side; lost on `revertToSnapshot` | Coordinator holds what it pulled |
| Mechanism already in the spec | none | **Yes** — `vmrun copyFileFromGuest`, `rg2-containment.md` §3.4 step 6 |

**And the pull mechanism should not be a network protocol at all where it does not have to be.** On
the laptop plan the coordinator is the hypervisor host, so `vmrun copyFileFromGuest` reads the file
through the hypervisor with no guest network involvement and no listener anywhere. That is strictly
better than SSH, because it needs no credential in either direction and no port open on `rg-work`.
Note the interaction with `rg2-containment.md` §4.3: if `isolation.tools.*` keys strip the guest→host
channel and `open-vm-tools` is removed, **`copyFileFromGuest` may stop working**. `[VERIFY]` whether
`vmrun` file operations survive the §4.3 hardening on Fusion/Apple Silicon — this is a real
dependency between two parts of the spec and it is not currently written down anywhere. If it does
not survive, the fallback is a read-only-to-the-guest second virtual disk, or an SSH pull from the
host to the guest, in that order of preference.

On the mini-PC plan the coordinator is a different machine, so the pull is over the network: the
coordinator opens an SSH connection *into* `rg-work` and reads. The workload holds no credential for
the coordinator, and a compromised workload can serve poisoned bytes but cannot reach out.

### 4.4 What is shipped, at what cadence, in what volume

Two streams with different urgency, and conflating them is why "aggregation" sounds harder than it is.

**Stream 1 — gateway log, continuous, trustworthy, small.** `rg-gw` writes `egress.jsonl` from
ulogd2, the CONNECT/bump proxy, and Unbound. The coordinator pulls it every 60 s — the same cadence
`rg2-containment.md` §5.6 already specifies for `rg-reconcile`. Volume: one row per new connection,
per DNS query, and (with §3's bump) **one row per HTTP request**. At an authorised 5 rps that is
~18,000 request rows an hour; at a few hundred bytes each, tens of megabytes per engagement-day.
That is nothing to store and it is well within what a naive `tail`-and-copy handles. It is *not*
nothing to write on a starved gateway — `hypervisor-licensing-and-sizing.md` §7.2 item 3 already
identifies ulogd2 log loss under load as the mechanism that manufactures false
`egress.unattributed` rows, and §3's per-request rows multiply that volume by an order of magnitude.
**That is a new argument for the gateway's RAM allowance, and possibly for raising it above 768 MB
once the bump lands.**

**Stream 2 — workload ledgers, on the same 60 s cadence, untrusted.** `activity.jsonl`,
`gates.jsonl`, `blockers.jsonl`. Volume is trivial — one row per tool call with a network
destination. These are pulled into a **quarantine directory** on the coordinator, not into the
reconciler's input directory, until they have been through the §4.6 pipeline.

**Cadence choice, stated so it can be argued with:** 60 s, not real-time. Real-time streaming buys
nothing here — nobody is watching a dashboard, the reconciler runs on a timer anyway, and a streaming
transport is a persistent connection, which is the thing §4.3 is trying not to build. The cost of 60 s
is that the last minute before a `revertToSnapshot` can be lost from the workload side; the gateway
side is unaffected, and the gateway side is the one that matters.

### 4.5 Tamper-evidence, and what it is honestly worth

**On the workload side, cryptographic tamper-evidence buys almost nothing, and it is important to say
so rather than build a hash chain that reads as a control.**

Any scheme the workload runs — a hash chain, an HMAC, a signature — uses a key the workload holds. An
escaped workload holds the key and can rewrite the entire chain consistently. This is design
judgement 2's second test applied to a transform: *name any state at which this fires.* It fires on
transport corruption and on an unsophisticated tamper. It does not fire on the threat model it looks
like it addresses.

What *does* work, in descending order of value:

1. **Ship early and often.** A row the coordinator already holds cannot be retroactively edited by the
   workload. **The 60 s pull is itself the tamper-evidence mechanism**, and it is the strongest one
   available, because it moves the artefact outside the blast radius rather than trying to protect it
   inside. This is §9.9's rule — *enforce outside the blast radius of the thing being contained* —
   applied to logs instead of packets.
2. **Append-only from the coordinator's side.** The coordinator writes each pull into a
   content-addressed, immutable per-pull file (`pulls/<engagement>/<ts>-<sha256>.jsonl`) and never
   mutates a prior one. A workload that shortens or rewrites its ledger produces a *divergence between
   consecutive pulls*, which is detectable and is a `high` incident. This is worth building; it is
   ~20 lines and it detects exactly the behaviour a hash chain claims to.
3. **`corr_id` monotonicity.** Already anticipated in `scope_guard.py`'s `ledger.write_fail` handler:
   a gap in the ULID sequence means rows are missing, whether from a disk error or a deletion. The
   reconciler treats a gap as unattributed traffic and does not need to know which.
4. **The gateway log as the authority.** When the two disagree, the gateway wins. Always, and without
   a tiebreak procedure — a tiebreak procedure is where the workload's version gets to argue.

**On the gateway side, tamper-evidence is not needed for the threat model in scope.** `rg-gw` is
outside the workload's reach by construction; if it is not, the boundary has already failed and the
log is the least of it. Ordinary file integrity and the coordinator's immutable pull archive are
sufficient.

### 4.6 What the coordinator does with them

Four programs, no model, in a fixed order. The design principle is `rg2-containment.md` §3.3's,
restated for logs:

> Log content from the workload is only ever read by programs that do not follow instructions, or by
> a human who knows they are reading attacker-influenced text. There is no third reader.

1. **Ingest.** Write the pull to the immutable archive (§4.5 item 2). Verify it is a strict extension
   of the previous pull; a non-extension is an incident, not a retry.
2. **Validate.** Schema-check every row against the §9.11 envelope. A malformed row is quarantined,
   not "best-effort parsed" — lenient parsing of untrusted input is how a payload reaches a consumer.
3. **Sanitise.** Strip ANSI and C0/C1 controls, NFKC-normalise, flag bidi and confusables, truncate
   absurd field lengths — `rg2-containment.md` §3.3 rule 4, applied to `reason` and `operation`,
   which are free-text fields the workload controls. **`target.operation` contains the literal command
   line**, which means it contains whatever the agent was induced to type. Nobody should ever paste it
   into a terminal, and a renderer must escape it.
4. **Reconcile.** `rg-reconcile` joins gateway and workload rows on
   `(engagement_id, dst_ip, dst_port, |Δt| ≤ 5 s)`, promoted to exact where `corr_id` carries
   (`rg2-containment.md` §5.5). Report-only for the first two engagements; the halt behaviour ships
   after the false-positive rate is measured.

**Storage and retention.** Per-engagement directories on the coordinator, under the same handling
obligations as evidence — this is client data, it names client hosts and IPs, and
`hypervisor-licensing-and-sizing.md` §6 already notes that a disk holding engagement artefacts
inherits every obligation in the paperwork. Retention follows the engagement's retention clause, not
a default.

**No SIEM for v1, and §9.11's intent is preserved rather than pre-empted.** The envelope is already
committed; the coordinator's archive is already JSONL in that envelope. Forwarding to Splunk, Sentinel
or an OCSF lake later is a mapping file plus an output plugin, which is what §9.11 said it should be.
Building a SIEM integration now would be building the interface before the data exists — and RedGold
has zero engagements' worth of real events to design it against, which is design judgement 1 exactly.

### 4.7 The forwarding design, in one place

| | |
|---|---|
| **Direction** | **Pull only.** The coordinator initiates every transfer. No listener on the coordinator, no permitted egress destination added for telemetry |
| **Mechanism (laptop plan)** | `vmrun copyFileFromGuest` for `rg-work`; host-side read for `rg-gw`. No guest networking involved. `[VERIFY]` survives §4.3's `isolation.tools.*` hardening |
| **Mechanism (mini-PC plan)** | Coordinator-initiated SSH pull into each box. Workload holds no coordinator credential |
| **Cadence** | 60 s during an engagement; a final pull at teardown **before** `revertToSnapshot` |
| **Streams** | Gateway (`egress.jsonl`: nftables via ulogd2, proxy request rows, Unbound queries) — trustworthy. Workload (`activity.jsonl`, `gates.jsonl`, `blockers.jsonl`) — attacker-influenced |
| **Landing** | Immutable, content-addressed per-pull files. Workload stream lands in quarantine until validated |
| **Tamper-evidence** | Frequency of the pull, plus prefix-extension checking across consecutive pulls, plus `corr_id` monotonicity. **No workload-side hash chain** — the workload holds the key |
| **Consumers** | `rg-reconcile` and a schema validator. Never a model with tools. Never a terminal paste |
| **Authority on conflict** | The gateway log, without a tiebreak |
| **Onward forwarding** | None in v1. §9.11's envelope keeps a SIEM output a mapping file |

**What this design does not claim.** It does not make workload logs trustworthy — nothing can. It does
not guarantee completeness: a workload that never calls `scope_guard.py` produces no row, which is
precisely the `(nothing) | block` case `rg2-containment.md` §5.5 rates the more alarming outcome, and
it is detected by the *gateway* log, not by anything on this page. And it does not detect a workload
that is compromised for the whole engagement and has forged its ledger consistently from the first
row — against that, the workload log has no value at all, and the gateway log has all of it.

---

## 5. Open items marked `[VERIFY]`

| # | Item | Why it matters | Cost to close |
|---|---|---|---|
| 1 | **On-disk closure of `kali-linux-headless` on arm64.** Kali's page lists "Installed size: 13 KB" for the metapackage, which is not the closure, and no closure figure is published | It is the input to `rg-work`'s disk sizing, and disk is the resource that bites (`hypervisor-licensing-and-sizing.md` §6) | 10 min: `docker run --rm --platform linux/arm64 kalilinux/kali-rolling` and install it |
| 2 | **Do the Go-based tools (`nuclei`, `httpx`, `ffuf`) honour the system trust store on Kali arm64 after `update-ca-certificates`?** | If not, §3's bump breaks every HTTPS scan, or worse, degrades silently to no verification | 20 min against a bumped test target |
| 3 | **Does `vmrun copyFileFromGuest` survive `rg2-containment.md` §4.3's `isolation.tools.*` hardening and `open-vm-tools` removal?** | §4's entire pull mechanism on the laptop plan depends on it, and no other part of the spec notices the dependency | 30 min, once the template exists |
| 4 | **`rg-gw` RAM at 768 MB with per-request proxy logging.** `hypervisor-licensing-and-sizing.md` §5.1 sized it for connection-rate ulogd2 volume, not for one row per HTTP request | ulogd2/proxy log loss manufactures false `egress.unattributed` rows — the false-positive class that trains the operator to ignore the tripwire | Measure during the first real scan |
| 5 | **mitmproxy's throughput and stability at RedGold's concurrency on arm64.** No figure read this pass | If the proxy is the bottleneck, scan timings become the proxy's, which is a finding-integrity issue, not a performance one | Measure |
| 6 | **Protectli VP2420e price and availability**; the VP2420's €339 is current on the EU store but the model is superseded | Only affects the hardware plan's cost line | 5 min |
| 7 | **Mini-PC TDP / power figures** for whichever SKU is chosen; none read this pass | Minor. Affects the "runs continuously" claim | 5 min at purchase |
| 8 | **`kalilinux/kali-bleeding-edge` and `kali-experimental` arm64 manifests** were not read | Irrelevant to the recommendation — neither should be used for engagement work | Skip |

**Items 2 and 3 are the two that can invalidate a conclusion here.** Item 2 could make §3's bump
impractical for the Go toolchain, which is most of RedGold's scanning; item 3 could force a redesign
of §4's transport. Items 1 and 4 change numbers, not decisions.
