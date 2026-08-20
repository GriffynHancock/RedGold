---
title: Hypervisor licensing and RG-CONTAIN-1 sizing
date: 2026-08-20
status: draft
question: Is VMware Fusion licensed for RedGold's commercial use, and does RG-CONTAIN-1 fit in ~11 GB of freed resource on a 16 GB Apple Silicon Mac?
spec_refs:
  - "docs/specs/rg2-containment.md §0, §3, §4, §9"
  - "docs/research/containment-architecture.md §7, §8"
supersedes: nothing. Answers two questions rg2-containment.md §0 explicitly deferred.
---

# Hypervisor licensing and RG-CONTAIN-1 sizing

## Index

| § | Section |
|---|---|
| 0 | The two answers, up front |
| 1 | VMware Fusion licensing — primary sources and quoted terms |
| 2 | The one ambiguity, and what it does and does not threaten |
| 3 | Alternatives on Apple Silicon — Proxmox first, because it is the short answer |
| 4 | Alternatives evaluated against RG-CONTAIN-1's four requirements |
| 5 | Sizing — RAM |
| 6 | Sizing — disk, which is the resource that actually bites |
| 7 | Recommended allocation, and what degrades under load |
| 8 | What changes in RG-CONTAIN-1 |
| 9 | Open items marked `[VERIFY]` |

---

## 0. The two answers, up front

### Answer 1 — licensing: **the architecture stands. Fusion is free for commercial use.**

Broadcom made VMware Fusion Pro free for **commercial** use, not merely personal use, and says so in
its own current product documentation. The operative sentence, from the **VMware Fusion 26H1 Release
Notes (release date 14 May 2026, build 25388279)** — the current shipping release as of this
document's date:

> "VMware Fusion Pro is now free for commercial, educational, and personal use. You no longer require
> a license key."

There is therefore **no licensing reason to replace Fusion**, and no need to evaluate Proxmox — which,
separately, cannot run on this hardware at all (§3). The operator's instinct was right about the
*question* and, as it happens, wrong about the *era*: Fusion's commercial-use restriction was real
until Broadcom removed it, in two steps, in November 2024 and March 2025.

One thing that does **not** come with the free licence, and which is worth knowing before an
engagement goes wrong at 2am: **no vendor support**. Free users are explicitly not entitled to
Broadcom Global Support. For a solo operator whose containment boundary depends on hypervisor
behaviour, that is a real operational risk, though not a legal one.

### Answer 2 — sizing: **11 GB of free RAM is enough, but only on the replace-not-add plan, and only if ZAP is treated as a scheduled peak rather than a resident service.**

Concretely, on a 16 GB Mac:

| | Allocation | Notes |
|---|---|---|
| `rg-gw` | **768 MB** RAM, 1 vCPU, 8 GB disk | Comfortable for a router. 512 MB works; 768 MB stops swap being interesting |
| `rg-work` | **6 GB** RAM, 2–4 vCPU, 40 GB thin-provisioned disk | 6 GB is the number that makes ZAP survivable |
| Hypervisor overhead | **~0.5–0.8 GB** | Two VMs, Fusion's own process footprint |
| **Total virtualisation footprint** | **~7.3–7.6 GB** | Against ~11 GB offered |
| macOS host retains | **~8.4–8.7 GB** of the 16 GB | Adequate; not generous |

**This works only if `rg-work` replaces the existing 9.7 GiB Kali guest rather than joining it.**
`rg2-containment.md` §0 already concluded replace-not-add and deferred the numbers; the numbers
confirm it. Running the current Kali guest *and* both new VMs would need roughly 16 GB of guest RAM
alone on a 16 GB machine, which is not a tight fit, it is an impossible one.

**The resource the operator did not ask about is the one that will actually run out: disk.** See §6.
`rg-work`'s scanner toolchain, a linked-clone base image, per-engagement snapshots and an evidence
archive plausibly want 60–100 GB of disk. "11 GB free" is comfortably enough if it means RAM and
comfortably *not* enough if it means SSD.

---

## 1. VMware Fusion licensing — primary sources and quoted terms

Four Broadcom/VMware first-party sources, in date order. Each quote is verbatim; nothing here is
paraphrased into a more convenient shape.

### 1.1 The announcement — 11 November 2024

[VMware Cloud Foundation blog, "VMware Fusion and Workstation are Now Free for All Users",
published 11 Nov 2024](https://blogs.vmware.com/cloud-foundation/2024/11/11/vmware-fusion-and-workstation-are-now-free-for-all-users/):

> "available for free to everyone—commercial, educational, and personal users alike."

> "both VMware Fusion and VMware Workstation will transition away from the paid subscription model,
> meaning you can now utilize these tools without any cost."

> "The paid versions of these offerings – Workstation Pro and Fusion Pro – are no longer available
> for purchase."

> "The free version will include all the features you've come to rely on from the paid version."

### 1.2 The licensing KB — undated on the page

[Broadcom KB 368667, "Download and license VMware Desktop Hypervisor (Fusion Pro and Workstation
Pro)"](https://knowledge.broadcom.com/external/article/368667/download-and-license-vmware-desktop-hype.html):

> "VMware Desktop Hypervisor (VMware Fusion Pro & VMware Workstation Pro) is available free for
> Commercial, Educational, and Personal users."

> "No license key is required for the free version."

> "The Free Version for both Personal and Commercial Use is only available from versions 'Workstation
> Pro 17.5.2' and 'Fusion 13.5.2' and above."

**Version floor is load-bearing.** Below Fusion 13.5.2 there is no free commercial entitlement. The
operator must confirm the installed Fusion build is 13.5.2 or later — and in practice should be on the
current 26H1 line anyway. `[VERIFY]` the installed build on the operator's Mac (`vmware -v` or About
VMware Fusion); this document does not know it.

**Source-quality caveat:** this KB page renders with an "Updated On:" field that carries no timestamp,
so its currency cannot be established from the page itself. It is corroborated by §1.3 and §1.4, which
are dated.

### 1.3 The FAQ — document item no. dated Oct 2025

[VMware Fusion & Workstation (Desktop Hypervisor) Frequently Asked
Questions](https://www.vmware.com/docs/desktop-hypervisor-faqs) (PDF; footer item no.
`vmw-bc-faq-2p-intl-temp-uslet-word-2025Oct-25`, copyright 2025 Broadcom). This is the most explicit
of the four:

> "Q. What has changed with VMware Fusion and Workstation?
> A. As of March 2025, the current versions of VMware Fusion Pro and Workstation Pro are available at
> no charge for all use cases, including personal, educational, and commercial use. Users no longer
> need to purchase a license for these versions for any scenario."

> "Q. Is VMware Fusion and Workstation truly free for both commercial and personal use?
> A. Yes. As of March 2025, VMware Fusion Pro and Workstation Pro are available at no cost for all
> users — personal, educational, and commercial. No subscription or license key is required."

> "Q. Do I need a license key?
> A. No. The latest versions of VMware Fusion and Workstation now include the license automatically.
> There's no need to select a usage type or enter a key — just install and start using the software
> freely for all purposes."

> "Q. Is this a one-time promotion?
> A. No. This licensing update reflects a long-term strategic shift by Broadcom to broaden the reach
> and adoption of its desktop hypervisor solutions. At this time, Broadcom does not have plans of
> making future releases paid."

And, relevant to operations rather than law:

> "Q. Does the free version include official technical support?
> A. No. Users of the free version are not entitled to support from the Broadcom Global Support Team.
> Support is available only for customers with active, pre-existing contracts."

Also confirmed in the same FAQ, and relevant to §3:

> "VMware Fusion supports macOS, including both Intel-based and Apple Silicon (M1/M2/M3) systems."

> "Q. Is Apple Silicon fully supported in Fusion?
> A. Yes. Fusion for Apple Silicon supports many Linux distributions and Windows 11 for ARM. Note that
> not all x86 guest OS features are available due to differences in hardware architecture."

That last clause matters for a different reason: **Fusion on Apple Silicon cannot run x86_64 guests.**
`rg-gw` and `rg-work` must both be arm64 builds. The operator's existing Kali guest already is.

### 1.4 The current release notes — 14 May 2026

[VMware Fusion 26H1 Release Notes, release date 14 May 2026, build
25388279](https://techdocs.broadcom.com/us/en/vmware-cis/desktop-hypervisors/fusion-pro/26H1/release-notes/vmware-fusion-26h1-release-notes.html):

> "VMware Fusion Pro is now free for commercial, educational, and personal use. You no longer require
> a license key."

**This is the sentence to rely on**, because it is the most recent and it is attached to a specific,
dated, currently-shipping build. Three months old at the date of this document.

### 1.5 Is there a "personal use" tier the commercial user falls outside of?

**No — there is no longer a tier distinction.** Fusion **Player** (the old free-for-personal-use
edition) is gone:

> "Q. Are Workstation Player or Fusion Player still available for purchase?
> A. As of April 30, 2024, Workstation Player and Fusion Player reached End of Sale (EOS) and are no
> longer available for purchase or download. They have been replaced by the more powerful Pro
> editions, which are now free for all use cases."

So the historical structure the operator is remembering — *Player free for personal use, Pro paid for
commercial* — was real, and it was retired in two moves: Player EOS on 30 April 2024, and Pro made
free for everyone from 11 November 2024 / March 2025. **There is one edition now: Fusion Pro, free,
all use cases.**

---

## 2. The one ambiguity, and what it does and does not threaten

Calibrated honesty requires flagging this rather than presenting the answer as cleaner than it is.

**Ambiguity 1 — "personal-use license built in".** The same Oct-2025 FAQ that says "free ... for all
use cases, including ... commercial use" also contains this, in the Player-migration answer:

> "Workstation Pro and Fusion Pro installers, now by default, provide a free personal-use license
> built in."

That phrase, read alone, describes a *personal-use* grant. Read against the four other statements in
the same document and the same vendor's release notes, it is residual wording from the Player-era
mechanism (the installer's built-in key), not a restriction. **It is the only sentence in any primary
source that could be read as limiting commercial use, and it is contradicted three times in the same
PDF.** The reading that survives is: commercial use is permitted.

**Ambiguity 2, and the more serious one — `[VERIFY]` the EULA text itself.**

**I could not retrieve the operative End User License Agreement for VMware Fusion.** What was
retrieved is vendor *documentation about* the licence (blog, KB, FAQ, release notes) — authoritative
as to Broadcom's stated position, but not the contract. Specifically:

- Broadcom's `docs.broadcom.com/doc/12398250` "END USER LICENSE AGREEMENT" surfaced by search is the
  **EFOS EULA v2-3b (2 April 2020)** — Ethernet Fabric OS, an unrelated product. Not applicable.
- `broadcom.com/company/legal/licensing` ("License and Service Terms & Repository") returned a page
  header with no retrievable document list. **Unretrievable; not substituted with a secondary source.**
- The download flow presents "Terms and Conditions" as a click-through at download time (KB 368667:
  *"Please click on the term link(s) 'Terms and Conditions', then acknowledge you agree by selecting
  the checkbox before proceeding."*). That click-through, plus the in-installer EULA, is the actual
  contract, and it is behind an authenticated Broadcom portal.

`[VERIFY]` **Read the EULA presented in the Fusion installer / at download, and confirm two things:**
1. that it contains no clause restricting use to non-commercial or internal purposes; and
2. that it contains no "service bureau" / "use to provide services to third parties" restriction.

Point 2 is the one that is *specific to RedGold* and that none of the four documentation sources
addresses. RedGold does not resell or host Fusion — it runs client testing inside a VM on the
operator's own machine, which is ordinary commercial use, not service-bureau use. But that
distinction is a lawyer's distinction, and the repo's rule is that a legal fact is never asserted
from inference. **Until that clause is read, the honest claim is: "Broadcom's current product
documentation states Fusion Pro is free for commercial use; the EULA text has not been read."**

This is not a blocker. It is a five-minute task at next download, and the documentation position is
unambiguous enough that the architecture should not wait on it.

---

## 3. Alternatives on Apple Silicon — Proxmox first, because it is the short answer

### 3.1 Proxmox VE — **does not run on this hardware. Stop here.**

The operator named Proxmox, so it gets answered plainly and immediately rather than evaluated.

**Proxmox VE is a bare-metal, install-on-the-hardware hypervisor. It cannot be installed on an Apple
Silicon Mac, and even if it could, installing it would replace macOS.** Two independent reasons:

1. **Architecture.** [Proxmox VE System
   Requirements](https://pve.proxmox.com/wiki/System_Requirements) lists, verbatim:
   - `"CPU: 64-bit x86 (Intel 64 or AMD64)"` for evaluation, and for production
     `"Intel 64 or AMD64 with an Intel VT or AMD-V CPU flag"`.
   - ARM support exists but is scoped: `"64-bit ARM (arm64, aarch64) on the NVIDIA Grace Hopper and
     NVIDIA Vera platforms"`, and `"On other UEFI-based ARMv9-A or newer hardware, support is
     best-effort."`
   Apple Silicon is not on that list. It is not a UEFI/ACPI platform in the sense that entry
   contemplates, and Apple ships no supported path to boot a third-party OS as a hypervisor with the
   device support Proxmox needs.
2. **Topology.** Even on supported hardware, Proxmox is a *type-1* hypervisor that owns the machine.
   RedGold's control tier (`rg-setup`, this repo, the operator's daily work) runs on macOS
   (`rg2-containment.md` §3, Part 2). Replacing macOS with Proxmox does not relocate the control tier
   — it deletes it.

Its licensing (Proxmox VE is AGPLv3; the enterprise repository and support require a paid
subscription, the no-subscription repository does not) is **moot** and is not researched further.

Proxmox would only enter the picture as a *separate x86 box*, which is a different and much more
expensive architecture: a second physical machine, and `rg2-containment.md` §9.10 property 6
(solo-operator cost) rules it out.

### 3.2 The rest, on Apple Silicon

`[VERIFY]` markers below indicate claims not read from a primary vendor source during this pass.

| Option | Runs on Apple Silicon? | Licence for commercial use | Private/isolated segment (`rg-work` → only route is `rg-gw`) | Snapshot / linked clone |
|---|---|---|---|---|
| **VMware Fusion Pro** | **Yes** — vendor-confirmed, both Intel and Apple silicon Macs (§1.3). arm64 guests only | **Free**, incl. commercial (§1) | **Yes** — custom vmnet with NAT and DHCP disabled; the topology `rg2-containment.md` §4.3 already specifies | **Yes** — `vmrun snapshot` / `revertToSnapshot`, plus linked clones. §3.4's teardown path depends on this |
| **UTM (QEMU backend)** | Yes. Apache-2.0 | **Free**, no restriction | **Probably** — the QEMU config model carries a `host` network mode with a `hostNetUuid`, and an explicit `isIsolateFromHost` flag (UTM source, `Configuration/UTMQemuConfigurationNetwork.swift`). `[VERIFY]` that two VMs can be attached to the *same* host-only segment with no host route |
| **UTM (Apple Virtualization backend)** | Yes | Free | **No.** Decisive. UTM's own source enumerates exactly two modes: `case shared = "Shared"` and `case bridged = "Bridged"` (`Configuration/UTMAppleConfigurationNetwork.swift`). There is no host-only/internal mode. [utmapp/UTM#7480](https://github.com/utmapp/UTM/issues/7480) (opened 5 Nov 2025, still open) is the open request for it | No |
| **Parallels Desktop** | Yes | **Paid.** Commercial software, per-seat; Pro/Business are annual subscriptions ([Parallels pricing](https://www.parallels.com/products/desktop/buy/)). Permitted, but it costs money. `[VERIFY]` whether the Standard edition's EULA permits business use — Parallels' own KB does not state it plainly and the forum thread asking exactly this is not a primary source | Yes — host-only networking is a documented feature `[VERIFY]` | Yes — snapshots and linked clones `[VERIFY]` |
| **Lima / Colima** | Yes | Apache-2.0, free | **Poor fit.** Lima is a *single Linux VM for developer workflows*, driven from a YAML template; it is not a multi-VM network fabric. Default networking is user-mode (SLIRP); shared/host networking requires `socket_vmnet` as a privileged helper. Building a two-VM routed segment on it means fighting the tool's purpose | No first-class snapshot/revert workflow |
| **QEMU directly** | Yes, with HVF acceleration for arm64 guests | GPLv2, free | **Yes** — QEMU's socket/multicast and `-netdev` primitives can build any topology, including a segment with no host route | **Yes** — qcow2 internal snapshots and backing-file overlays (the native form of a linked clone) |
| **Apple Virtualization.framework** | Yes — it *is* the Apple Silicon virtualisation primitive | Free, part of macOS | **No, as shipped.** The framework's network device attachments are NAT and bridged. It has no internal/host-only segment, which is why UTM's Apple backend has none either. `[VERIFY]` against Apple's `VZNetworkDeviceAttachment` documentation before treating this as final | No snapshot API. Disposability would have to be done by copying disk images |

### 3.3 What this table says

Two things.

**First, Fusion is not merely acceptable — it is the only option in the list that satisfies all four
requirements with first-class, documented, scriptable support.** Snapshot/revert and linked clones are
not a convenience here; `rg2-containment.md` §3.4 makes `vmrun snapshot rg-work clean` step 4 of
handover and `revertToSnapshot clean` the teardown mechanism, and §9.10 property 5 (disposability) is
one of the six properties the whole design exists to satisfy. UTM has no exposed snapshot UI at all,
and the Apple backend has no snapshot support; Virtualization.framework has no snapshot API.

**Second, the one genuine fallback is UTM/QEMU, and it is a downgrade, not a substitute.** If Fusion
ever becomes unavailable — Broadcom reversing the licence, or dropping the product — the migration is
UTM with the **QEMU** backend (never the Apple backend, which cannot express the topology), accepting
that snapshot management moves to `qemu-img` on the command line and that the whole `vmrun`-based
teardown path in §3.4 must be rewritten. That is a day of work, not a redesign, and it is worth
writing down now so the decision is not made under time pressure later.

**Do not pay for Parallels.** It is licensable for commercial use, but it buys nothing Fusion does not
already provide free, and it introduces a recurring cost and a licence-compliance surface the free
option does not have.

---

## 5. Sizing — RAM

### 5.0 What "11 GB free" was assumed to mean

The operator said *"pull down everything on my machine to make it have about 11 GB free"*, which most
naturally reads as **freeing RAM by quitting applications on a 16 GB Mac**. That is the reading this
section costs. §6 costs the disk reading separately, because the two answers differ and the disk one
is worse.

### 5.1 `rg-gw` — a router, not a workstation

`rg-gw` runs nftables (in-kernel), Unbound, a CONNECT proxy, ulogd2, and chrony. Every one of those is
a small daemon; the only component with a memory appetite that scales with anything is Unbound's
cache, and that is a configured number.

**Documented floor.** Debian's own installation manual, Table 3.2 "Recommended Minimum System
Requirements" ([Debian installation guide, arm64,
§3.4](https://www.debian.org/releases/stable/arm64/ch03s04.en.html)):

| Install Type | RAM (minimum) | RAM (recommended) | Hard Drive |
|---|---|---|---|
| No desktop | 512 MB | 1 GB | 4 GB |
| With Desktop | 1 GB | 2 GB | 10 GB |

The same page notes that *"actual minimum memory requirements are a lot less than the numbers listed
in this table"*, with installation possible in as little as 245 MB with swap.

**Allocation: 768 MB.** Reasoning, stated so it can be argued with:

- 512 MB is Debian's documented no-desktop minimum and would work.
- The extra 256 MB is not for the daemons; it is so that **ulogd2's write path never contends with
  page cache under a heavy scan.** `rg-gw` is where the trustworthy log lives (`rg2-containment.md`
  §5.6 — *"the gateway-side log is trustworthy because it is written on a machine the workload has no
  principal on"*). A gateway that drops log records under load degrades the one artefact the whole
  reconciliation design rests on. 256 MB is a cheap insurance premium against that.
- Do **not** go above 1 GB. There is nothing to spend it on, and every MB here is a MB `rg-work`
  does not get.

**Alpine instead of Debian?** Alpine would run this in ~256 MB and is a smaller attack surface. It is
a reasonable choice and would save ~512 MB. It is not recommended here for a non-technical reason:
`ulogd2`, `unbound` and nftables tooling are better-trodden on Debian, and `rg-gw` is a component the
operator must be able to debug at 11pm. **Save the RAM elsewhere.** `[VERIFY]` Alpine's documented
minimums were not retrieved during this pass — the Alpine handbook page fetched did not contain them.

### 5.2 `rg-work` — where the RAM actually goes

Three documented requirements, from the three vendors that matter:

**Kali Linux** ([Kali installation
documentation](https://www.kali.org/docs/installation/hard-disk-install/)):
- bare/SSH-only, no desktop: *"as little as 128 MB of RAM (512 MB recommended)"*, *"2 GB of disk
  space"*
- default Xfce4 + `kali-linux-default`: *"at least 2 GB of RAM"*, *"20 GB of disk space"*
- and the sentence that sets the ceiling: when running resource-intensive applications such as Burp
  Suite, *"at least 8 GB of RAM"*, with more recommended for large web applications or concurrent
  programs.

**Claude Code** ([Claude Code advanced setup — system
requirements](https://code.claude.com/docs/en/setup)):
- *"**Hardware**: 4 GB+ RAM, x64 or ARM64 processor"*
- OS support includes *"Debian 10+"* and *"Alpine Linux 3.19+"*, so a Kali/Debian arm64 guest is
  supported.

**A correction to the brief's premise:** the task asked about "Node/Claude Code's footprint".
Claude Code no longer runs on Node at runtime. The setup docs state that the npm package *"downloads
a native binary that doesn't use your Node.js at runtime"* and *"The installed `claude` binary does
not itself invoke Node."* Node is not a resident cost in `rg-work` unless the *target's* toolchain
needs it. The documented 4 GB figure is a **whole-system** requirement, not a process RSS — it is a
floor on the guest, not an amount to add to a running total.

**OWASP ZAP** — and here the brief's hypothesis is right about the shape and the documentation is
disappointing about the number:
- ZAP requires *"a minimum of Java 17 to run"*
  ([ZAP FAQ](https://www.zaproxy.org/faq/what-versions-of-java-are-supported/)).
- **ZAP publishes no minimum or recommended RAM figure.** The
  [Options JVM screen](https://www.zaproxy.org/docs/desktop/ui/dialogs/options/jvm/) documents how to
  set `-Xmx` and gives `-Xmx256m, -Xmx512m, -Xmx1024m` as *examples*, not recommendations, and offers
  no guidance on how much ZAP should be given. `[VERIFY]` — **no ZAP RAM requirement was established
  from a primary source, because ZAP does not publish one.** Any number quoted for ZAP below is an
  engineering estimate and is labelled as such.

### 5.3 The `rg-work` budget

Headless is assumed throughout: `rg-work` is driven by Claude Code over a console, has no operator
sitting at a desktop, and ZAP runs in `-daemon` mode. That choice alone saves the ~1.5 GB delta
between Kali's no-desktop and Xfce4 figures, and it is the correct choice anyway — a GUI in `rg-work`
is a clipboard and a screenshot away from threat (f).

| Component | Estimate | Basis |
|---|---|---|
| Kali headless base + kernel + page cache | ~0.5 GB | Kali documents 512 MB recommended for bare install |
| Claude Code session + subprocesses | ~1.0–1.5 GB | Estimate. Vendor documents a 4 GB *system* floor, not a process figure |
| ZAP daemon, JVM heap | **~1.5–2.0 GB** | **Estimate — the driver.** No vendor figure exists (§5.2) |
| nuclei at moderate concurrency | ~0.5–1.0 GB | Estimate. Scales with `-c`/`-bs`; the template set is the fixed part |
| nmap, testssl, trufflehog, gitleaks | ~0.2–0.4 GB combined | Estimate. None is a memory hog; testssl is shell, nmap is C |
| Rootless container runtime overhead | ~0.1 GB | Estimate |
| **Peak, everything at once** | **~3.8–5.5 GB** | |

**Allocate 6 GB.** That satisfies Claude Code's documented 4 GB floor with room to spare, covers the
estimated peak with ~0.5–2 GB of headroom, and stays under Kali's *"at least 8 GB"* advice only
because RedGold runs ZAP headless rather than Burp with a GUI.

**4 GB is the hard floor and is not recommended.** At 4 GB, Claude Code's documented requirement is
met exactly, ZAP's heap and nuclei's concurrency have to be capped by hand, and the guest starts
swapping during the exact operation — a full active scan — where a stall looks like a target being
slow and produces a wrong finding. That is a `[VERIFY]`-class failure in the *findings*, not just in
performance, and RG-1's coverage register exists precisely so that a degraded scan is recorded rather
than inferred.

### 5.4 Host and hypervisor overhead

- **macOS host.** On a 16 GB Apple Silicon Mac, macOS plus the operator's control-tier work (a
  browser, an editor, `rg-setup`, this repo) wants meaningfully more than a token allowance. The
  ~8.4–8.7 GB left by the allocation in §0 is adequate. It is not generous, and the operator will
  notice memory compression if they also have thirty browser tabs open.
- **Per-VM hypervisor overhead.** Fusion's `vmware-vmx` process consumes memory beyond the guest's
  configured RAM for device emulation, graphics and virtual-machine metadata. Budgeted at
  **~0.5–0.8 GB combined for two VMs**. `[VERIFY]` — **no Broadcom-published figure for Fusion's
  per-VM overhead was retrieved.** This is an engineering allowance, not a vendor number, and if it is
  wrong it is wrong in a direction that costs the host, not the guests.
- **Apple Silicon caveat.** macOS uses memory compression and SSD swap aggressively, so the machine
  will not hard-fail at the boundary — it will get slow, and it will write to the SSD. That is a
  performance and SSD-wear cost rather than a crash, which makes over-allocation *tempting and
  quietly expensive*. Do not treat the absence of an out-of-memory kill as evidence the allocation
  fits.

### 5.5 Does the existing 9.7 GiB Kali guest keep running? **No. It is replaced.**

This is the question that decides everything else, and the arithmetic is not close.

| Plan | Guest RAM | Plus overhead | Left for macOS on a 16 GB machine |
|---|---|---|---|
| **Add** (keep current Kali + `rg-gw` + `rg-work`) | 9.7 + 0.75 + 6 = **16.45 GB** | ~17.2 GB | **Negative.** Impossible |
| **Replace** (`rg-gw` + `rg-work` only) | 0.75 + 6 = **6.75 GB** | ~7.3–7.6 GB | **~8.4–8.7 GB.** Works |

`rg2-containment.md` §0 concluded replace-not-add on judgement and deferred the numbers. **The numbers
confirm it, and they confirm it by a wide margin rather than a narrow one.** The add plan is not a
tight fit that could be squeezed; it exceeds the machine's entire physical RAM before macOS gets a
byte.

**Two consequences the spec should absorb:**

1. **The 9.7 GiB figure is a red herring, and freeing it is the whole answer.** The current Kali guest
   is over-allocated for what `rg-work` needs to do. Reclaiming it and re-spending 6 GB of it on
   `rg-work` plus 0.75 GB on `rg-gw` *leaves the operator ~3 GB better off than today.* The operator
   does not need to free 11 GB. They need to stop running the 9.7 GiB guest.
2. **§9.10 property 5 (disposability) survives.** `rg2-containment.md` §0 warned that if the operator
   ends up with one guest instead of two, disposability *"is the first thing to fall, and the honest
   claim in §10 loses a clause."* On the replace plan there are still two VMs — `rg-gw` and `rg-work`
   — and `rg-work` is a fresh linked clone per engagement. **The clause is kept. §10's honest sentence
   does not need to be weakened.** That is the most valuable single outcome of this sizing exercise.

---

## 6. Sizing — disk, which is the resource that actually bites

The operator said "free" without naming a resource. If they meant **SSD**, the answer changes from
*yes* to *no*.

| Item | Disk | Basis |
|---|---|---|
| `rg-gw` base | 8 GB thin | Debian documents 4 GB no-desktop; +4 GB for `egress.jsonl` growth |
| `rg-work` **base template** | 40 GB thin | Kali documents 20 GB for the default install; the scanner set (nuclei template corpus, ZAP + JRE, Go toolchain artefacts, wordlists) roughly doubles it |
| `rg-work` **linked clone**, per engagement | 5–15 GB grown | Estimate. A linked clone starts near zero and grows with every write the engagement makes |
| Snapshots | 1–10 GB each | The `clean` snapshot taken at §3.4 step 4 is cheap at creation and grows as the running clone diverges from it |
| Evidence archive | 1–20 GB per engagement | Lives on the **macOS control tier**, not in the guest (`rg2-containment.md` §3.3 pulls it out) — but it is still the same SSD |
| **Realistic working total** | **~65–100 GB** | |

**11 GB of free SSD is not enough — it is not enough for the `rg-work` base template alone.** Kali's
own documented 20 GB for a default install exceeds it before a single scanner is added.

**What this means practically:**

- If the operator's ~11 GB was RAM: proceed, §7's allocation stands.
- If it was disk: **the disk question must be solved before RG-CONTAIN-1 is built**, and the honest
  options are (a) free 80–100 GB on the internal SSD, or (b) put the VM bundles on external NVMe.
  Option (b) is cheap and works, with one caveat worth stating: **an external disk holding `rg-work`
  and its evidence is a client-data-bearing device** and inherits every handling obligation the
  engagement paperwork imposes — encrypted at rest, and it never leaves the operator's control.
- **Thin-provision everything and check actual consumption, not configured size.** A 40 GB thin disk
  costs what it uses. The numbers above are configured ceilings; steady-state consumption will be
  lower. But snapshots invert this: a long-lived snapshot on a busy clone can consume more than the
  base image, which is why §3.4's teardown is `revertToSnapshot` **and then discard**, not accumulate.

`[VERIFY]` the operator's actual free SSD, and which resource "11 GB" referred to. This document
cannot tell.

---

## 7. Recommended allocation, and what degrades under load

### 7.1 The allocation

| VM | RAM | vCPU | Disk | Network |
|---|---|---|---|---|
| `rg-gw` | **768 MB** | 1 | 8 GB thin | 2 NICs: one to the host's outbound path, one to the private vmnet |
| `rg-work` | **6 GB** | 2–4 | 40 GB thin (linked clone from template) | **Exactly 1 NIC**, on the private vmnet, NAT and DHCP disabled, only route = `rg-gw` (`rg2-containment.md` §4.3) |
| macOS host | retains ~8.4–8.7 GB | remainder | — | — |

**vCPU note.** `rg-work` gets 2–4 vCPU, not "as many as possible". Scanner concurrency is bounded by
the *scope* and by rate-limit courtesy to the client's production systems long before it is bounded
by cores, and over-provisioning vCPU on Apple Silicon steals scheduler time from macOS for no
throughput gain. `rg-gw` gets 1; it is forwarding packets for one host.

### 7.2 What degrades when the operator runs a heavy ZAP scan

Stated as failure modes, because "it gets slow" is not an actionable warning.

1. **First to degrade: `rg-work` responsiveness, not correctness.** ZAP's JVM expands its heap, nuclei
   is running concurrently, and Claude Code's session becomes laggy. Annoying; harmless.
2. **Second, and the one that matters: scan results change shape.** Under memory pressure the guest
   swaps, request timing becomes erratic, and timing-sensitive checks — anything measuring response
   latency, and any race-condition or timing-oracle test — produce results that reflect the *guest's*
   contention rather than the *target's* behaviour. **This is a finding-integrity failure, not a
   performance one.** It must be recorded in RG-1 §8.1's coverage register, exactly as §2.5 requires
   for capability-degraded scans. The rule generalises: *any degradation that changes what the
   scanner can observe is a coverage limitation and is written down, never inferred from absence.*
3. **Third: `rg-gw` log loss.** If the gateway is starved while `rg-work` generates tens of thousands
   of new connections, ulogd2 can drop NFLOG records. The reconciliation join (§5.5) then shows
   `(nothing) | allow` rows — `egress.unattributed` — which look like a security event and are
   actually a capacity event. **This is the false-positive class §5.5 warns will train the operator to
   ignore the tripwire**, and it is the reason `rg-gw` gets 768 MB rather than 512 MB.
4. **Fourth: the macOS host.** Memory compression and SSD swap. The operator notices; nothing breaks.

### 7.3 The three mitigations, in order of value

1. **Pin ZAP's heap explicitly: `-Xmx2g`, do not rely on JVM ergonomics.** ZAP publishes no
   recommended heap (§5.2), and the JVM's default maximum heap is derived from the *machine's*
   physical memory — which in a VM means the guest's RAM, and which will therefore change silently if
   the allocation is ever retuned. An explicit `-Xmx` makes the peak a known, versioned number instead
   of an emergent one. `[VERIFY]` the exact ergonomic default for the JRE shipped with ZAP on arm64
   before relying on any specific fraction; the point stands regardless of the fraction.
2. **Do not run ZAP and a high-concurrency nuclei sweep at the same time.** They are the two memory
   peaks and they do not need to be concurrent. Sequencing them is free and removes the top of the
   curve entirely.
3. **Cap nuclei concurrency in the playbook, not by hand at 11pm.** A concurrency figure recorded in
   the engagement playbook is a reproducible testing parameter; one typed under time pressure is an
   unrecorded variable in the findings.

---

## 8. What changes in RG-CONTAIN-1

**Nothing structural.** Both answers land on "the spec was right".

| `rg2-containment.md` section | Change |
|---|---|
| §0 — "refuses to decide" the RAM question | **Answer it.** Replace-not-add is confirmed with numbers (§5.5). §9.10 property 5 survives; §10's honest sentence keeps its clause |
| §3.4, §4.3 — Fusion `.vmx`, `vmrun`, custom vmnet | **Unchanged.** Fusion is licensed for commercial use (§1) and is the only Apple Silicon option with first-class snapshot + linked clone + isolated segment (§3.3) |
| §4.3 — guest architecture | **Add a note:** Fusion on Apple Silicon runs arm64 guests only. `rg-gw` must be a Debian arm64 image, not x86 |
| §9 — build order | **Add a precondition above everything:** confirm free SSD, not just RAM (§6). The build cannot start on 11 GB of disk |
| §11 — `[VERIFY]` list | **Add §9's items below** |
| New | **Record the fallback:** if Fusion becomes unavailable, migrate to UTM with the **QEMU** backend, never the Apple Virtualization backend, and rewrite §3.4's `vmrun` teardown against `qemu-img` (§3.3) |

One addition worth making to §10's honest limits, arising from §1.3: **the containment boundary now
depends on an unsupported product.** Free Fusion carries no vendor support entitlement. That is not a
legal problem and not a reason to change hypervisor — but it is an honest limit, and §10 is where
honest limits go.

---

## 9. Open items marked `[VERIFY]`

| # | Item | Why it matters | Cost to close |
|---|---|---|---|
| 1 | **The Fusion EULA text has not been read.** Confirm no non-commercial restriction and no service-bureau / "provide services to third parties" clause | Hard rule 1: no legal fact is asserted from inference. The documentation position is unambiguous; the contract is unread | 5 min at next download |
| 2 | Broadcom's `broadcom.com/company/legal/licensing` repository was **unretrievable** — returned a bare page header with no document list. Not substituted with a secondary source | It is the canonical index of the operative terms | 5 min in a browser |
| 3 | Installed Fusion build ≥ 13.5.2 (the free-commercial version floor, KB 368667). Ideally on the 26H1 line | Below the floor there is no free commercial entitlement | 30 s (`vmware -v`) |
| 4 | **ZAP publishes no RAM requirement.** All ZAP memory figures in §5.3 are engineering estimates | ZAP is the sizing driver and the one number with no vendor backing | Measure it: run a real scan with `-Xmx2g` and record peak RSS |
| 5 | Fusion per-VM hypervisor overhead — **no Broadcom figure retrieved.** §5.4's 0.5–0.8 GB is an allowance | Determines whether macOS gets 8.4 GB or less | Measure after first boot |
| 6 | **Which resource "11 GB free" referred to**, and the operator's actual free SSD | Changes the answer from yes to no (§6) | Ask; `df -h` |
| 7 | UTM QEMU backend: that two VMs can share one host-only segment with **no host route**. Inferred from UTM's source (`host` mode + `isolateFromHost`), not from documentation — `docs.getutm.app` returned HTTP 403 | Only matters if the Fusion fallback is ever exercised | 30 min, only if needed |
| 8 | Parallels Standard edition EULA: whether business use is permitted | Only matters if Parallels is ever considered. It should not be | Skip |
| 9 | `VZNetworkDeviceAttachment` — confirm Virtualization.framework offers no internal/isolated segment | Confirms why the UTM Apple backend is disqualified | 10 min, low value |
| 10 | Alpine's documented minimum RAM/disk — the handbook page fetched did not contain them | Only matters if `rg-gw` moves to Alpine to save ~512 MB | Skip unless RAM gets tight |

**Nothing in §0's two answers depends on items 7–10.** Items 1 and 6 are the two that could change a
conclusion: item 1 could in principle invalidate the licensing verdict (very unlikely, given four
concordant vendor sources), and item 6 could turn "yes, 11 GB is enough" into "no, and here is the
disk plan".
