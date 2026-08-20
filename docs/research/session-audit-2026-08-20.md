---
title: Adversarial audit of the 2026-08-20 research session — claim verification, document soundness, and research gaps
date: 2026-08-20
status: draft
question: Is the orchestrator's summary faithful to the six research documents, are those documents sound, what material research is still missing, and is there enough verified ground to write the RG-1 spec now?
---

# Session audit — 2026-08-20

Fifth adversarial round. Read-only against the repo and the six documents; the only file written is
this one. Where a claim could be checked against code, the Act, or the machine, it was checked
against the thing itself and not against what a document says about the thing.

**Verdict counts (Task 1, 23 claims):** SUPPORTED 16 · OVERSTATED 5 · CONTRADICTED 2 ·
UNSUPPORTED 0 · UNVERIFIABLE-CHEAPLY 0.

**Headline:** the documents are unusually good. The two contradictions are both in the orchestrator's
summary, one of them is also in a source document, and one of them is a live foot-gun for RG-3.
**RG-1 can be specced now**, with five caveats named in §4.

---

## 1. Task 1 — claim-by-claim verdicts

Claims 2, 3, 4 and 20 were checked against the code and the filesystem, not against the documents.
Claims 6, 7, 8, 9, 10 were checked against `~/Downloads/C2026C00227.docx` extracted with
`zipfile`. Claims 15, 16 were checked against nuclei's v3.11.1 source and NVD. Claim 18 was checked
against this machine.

### 1–4 · Autopsy and code

**1. An environment gate would have suppressed 7 of 11 bad findings — `SUPPORTED`.**
`docs/research/prior-engagement-autopsy.md:309` (FM-1 (ii): "F-101, F-103, F-107, F-046, F-048, F-058, F-060.
Seven of eleven reported findings, including the only critical and two of three highs") and
`:555` (E1 headline "**7 of 11 findings**"), with the mechanism split at `:576-578`: three by
severity cap, four by non-existence. Two things to hold on to and neither changes the verdict:
this is a counterfactual, never run; and four of the seven (F-046, F-058) are *also* claimed by E2,
so "E1 suppresses 7" and "E2 suppresses 2" are overlapping sets and must not be added.

**2. `baseline_scan.py` self-certifies, so `UNVERIFIED_ABOVE_LOW` could never fire on baseline
findings — `SUPPORTED`, verified in code.** `scripts/baseline_scan.py:233` writes
`"verified": "executed" if present else "none"`. The rule at `scripts/findings.py:274-280` fires
only when `severity in ABOVE_LOW and verified not in VERIFIED_STRONG`. Enumerating
`make_finding()`'s three exits: `present` → `verified: executed` (strong, rule cannot fire);
`absent` → `severity: info` (below Low, rule cannot fire); `applicable=False` → `verified: none` but
`severity: info` (below Low, rule cannot fire). The rule is structurally unreachable from this
producer. `docs/research/prior-engagement-autopsy.md:499` and `rg1-implementation-surface.md:213-217` both
describe this correctly.

**3. `agents/rg-verify.md` grants only `Bash, WebFetch, Read`, so the verifier structurally could
not record a verdict to disk — `CONTRADICTED`.** The tool list is right
(`agents/rg-verify.md:5`: `tools: Bash, WebFetch, Read`). The conclusion is wrong: **`Bash` is a
write path.** `echo … > findings/verification.json` works. The agent's own prompt assumes it:
`agents/rg-verify.md` instructs it to "write a blocker to `ledger/blockers.jsonl` and stop" and,
under HANDOFF, "write your output to disk". No hook restricts this — the repo has no
`hooks.json` and no `.claude/settings.json`, and `scope_guard.py` gates network calls, not writes.

The real defect is adjacent and worth stating correctly because E4 is specced against it: rg-verify
has **no `Write`/`Edit` tool, no schema, and no mandated output path**, so its verdicts land as
free prose (the prior engagement's `findings/verification.md`) that no script parses. The failure
is "structured verdicts are not required and nothing reads the unstructured ones", not "the agent
cannot write". Design E4 for the former; the latter would suggest the fix is a tool grant, and a
tool grant alone fixes nothing.

**4. `playbooks/_generic/false-positives.md` does not exist though the spec says the table lives
there — `SUPPORTED`, verified on disk.** `playbooks/_generic/` contains exactly one file,
`adversarial-framings.md`. A repo-wide `find -iname '*false-positive*'` returns nothing.
`docs/specs/redgold/08-findings-and-verification.md:129` says "This table lives in
`playbooks/_generic/false-positives.md` and grows via `/rg:harvest`." `agents/rg-verify.md` also
depends on it — its fourth rotating framing is "Check it against the false-positive table."
Two live references, zero file.

### 5–10 · Privacy Act

**5. The small business exemption is not repealed, not in a passed-but-not-commenced amendment, has
no commencement date, and is a commitment "agreed in principle" — `OVERSTATED`.** The negative half
is `[V]` and I confirmed it independently: `act.txt` line 1129 shows s 6D intact with the
$3,000,000 test, and the endnote at line 6932-6935 shows `s 6D … am No 197, 2012` and nothing after.
`privacy-act-feasibility.md:1353` grades it `[V]`.

The positive characterisation is not. `privacy-act-feasibility.md:1410` records that the
Attorney-General's Department page **timed out twice** and that "the 'agreed in principle,
28 September 2023, subject to further consultation' characterisation comes from search
summarisation"; `:249` self-grades confidence **Medium**; `:1354` grades it `[P]`. Under hard rule 1
that phrase is a legal fact obtained from a summariser, and the summariser in this same document
is on record inventing a section number. Say "not repealed, no date, no bill located" flatly;
attribute "agreed in principle" to an unread source until the page loads.

**6. Compilation No. 104, 4 June 2026, amendments to Act No. 75 2025; s 6D carries $3,000,000; no
amending Act to s 6D since 2012 — `SUPPORTED`, independently verified against the primary source.**
Every element checked out of the `.docx`: title page "Compilation No. 104" / "4 June 2026" /
"Act No. 75, 2025"; `6D(1)` "annual turnover for the previous financial year is $3,000,000 or less";
endnote `s 6D — ad No 155, 2000 — am No 197, 2012`.

**7. AML/CTF tranche 2 commenced 1 July 2026 and s 6E(1A) brings small-business reporting entities
into the Act for AML/CTF-related activities — `OVERSTATED`.** The s 6E(1A) half is exactly right and
I read it: `6E Small business operator treated as organisation … (1A) If a small business operator
is a reporting entity or an authorised agent of a reporting entity … this Act applies … in relation
to the activities carried on … for the purposes of, or in connection with, activities relating to
(a) the Anti-Money Laundering and Counter-Terrorism Financing Act 2006 … as if the small business
operator were an organisation.`

The **date** is not verified. `privacy-act-feasibility.md:1361` grades it `[P]` — "from OAIC
guidance via fetch summary only", not from the amending Act's commencement table — and `:319`
flags it in place. It is also the one fact the entire pivot rests on, so it is the one worth the
ten minutes. One structural nuance the summary loses: s 6E(1A)'s endnote is `am No 170, 2006`, i.e.
the Privacy Act mechanism has existed since 2006. Nothing changed in the Privacy Act on 1 July 2026;
what changed is the AML/CTF Act's definition of *reporting entity*. That matters, because it means
the commencement question must be answered against the AML/CTF amending Act, not this compilation.

**8. APP 1.7–1.9 (automated decision-making transparency) commence 10 December 2026 —
`SUPPORTED`, independently verified.** The compilation's amending-Act table records for the *Privacy
and Other Legislation Amendment Act 2024* (No. 128, 2024): "sch 1 (items 87–89): 10 Dec 2026
(s 2(1) item 7)", and the uncommenced-amendments line lists "sch 1 (item 89)" as underlined.
Consistent with the compiled Schedule 1 text, which ends APP 1 at clause 1.6 (`act.txt` line 5556).
Provisional: `privacy-act-feasibility.md:1360` marks the *operative text* of items 87–89 as not
read. The date is solid; what APP 1.7–1.9 actually require is not, and a product built on them
needs the text.

**9. APP triage is TECHNICAL 0 / HYBRID 9 / GOVERNANCE 3 / OUT OF SCOPE 1, and no APP is purely
technical — `SUPPORTED`.** `privacy-act-feasibility.md:383` and `:385`. Arithmetic checks: 0+9+3+1
= 13 APPs. The per-APP classifications at `:414, 445, 473, 507, 537, 572, 607, 646, 686, 717, 747…`
are individually reasoned with a technical surface and a governance surface each.

**10. No certification/accreditation/registered-assessor scheme; s 33C makes assessment the
Commissioner's power, so "certified" would be a false claim — `SUPPORTED`, with one boundary.**
s 33C verified in the Act: "Commissioner may conduct an assessment relating to the Australian
Privacy Principles etc." `privacy-act-feasibility.md:905-933` and `:1354` grade the scheme claim
`[V]`. The boundary: "would be a **false claim**" as a *factual* statement is sound (there is
nothing to be certified against). As a *legal* characterisation it leans on ACL s 29(1)(g)/(h),
which `privacy-act-feasibility.md:937` marks `[VERIFY — the exact text … was not retrieved; two
attempts …]`. Do not let the legal edge of that sentence into a marketing or contract document yet.

### 11–14, 21–23 · Severity model

**11. CVSS `PR:` is defined relative to the vulnerable system and cannot express a precondition held
on a different system — `SUPPORTED`.** `exploitability-severity-model.md:150-157`, which quotes v4's
`PR:H` as privileges "over the vulnerable system" and makes the sharper structural point: v4 has
Subsequent System metrics for downstream impact but **no antecedent-system metric** for an upstream
requirement. That is the load-bearing argument for the whole bespoke-ladder recommendation and it
holds.

**12. SSVC's documented fail-closed default is "if you cannot determine exposure, assume Open" —
`SUPPORTED`, with a form caution.** `exploitability-severity-model.md:22` and `:277-281`, sourced to
`certcc.github.io/SSVC` System Exposure 1.0.1, fetched 2026-08-20. Caution: the source document
renders the other System Exposure definitions inside quotation marks (`:259`) but renders *this*
one as an unquoted paraphrase ("Its guidance states that … they should assume exposure is Open").
The orchestrator's summary put quotation marks back around the paraphrase. Substantively fine;
do not print it as a quotation without re-fetching, because hard rule 2's neighbour applies.

**13. Mapping `docker` group membership to `host-root` (not `host-code-exec`) is correct —
`OVERSTATED`.** The reasoning at `exploitability-severity-model.md:406-411` is sound
(`docker run -v /:/host --privileged` is root in one documented step). But the document's own open
items say otherwise about its status: `:1960-1962` — "The claim is well established but **was not
fetched from Docker's own documentation in this session.** Cite the primary source before it appears
in a client report; hard rule 2 applies." The orchestrator dropped that qualification and rendered
the design choice as verified. It is a well-supported design choice with an unfetched citation.

**14. Applying the model, F-107 computes from `critical` to `info`, dominated by F-103 —
`SUPPORTED`, with the self-adjudication discount of §2.4.** `exploitability-severity-model.md:1037-1050`
walks it: `scope_change` empty, `DATA_RANK[tenant]=2 < DATA_RANK[all]=3`, same subject,
`CAPABILITY_RANK[tenant-user]=2 <= CAPABILITY_RANK[env-secret-read]=4` → dominated; brake 1 clears.
The derivation is mechanical and reproducible from the published rank tables, which is more than
most of the scoreboard rows can say. It is still the model author's own worked example against a
corpus the author read first.

**21. Strong deployment-state signals are conclusive-when-present and silent-when-absent, so a
classifier can conclude "dev" but never "prod" — `SUPPORTED`, but see the tension in §2.2.**
`exploitability-severity-model.md:760-765` states it flatly: "the classifier can confidently emit
`development`; it can never confidently emit `production`". Two problems live behind that sentence
and both are documented in §2.2 below: the attribution to `test-library-composition.md` §5 is wider
than what §5 actually says, and §3.6 of the same document defines a `prod-signal-present` verdict
that does conclude toward production from a conjunction.

**22. Sections 1–6 only subtract, so coverage counterweights must ship in the same release or
earlier — `SUPPORTED`.** `exploitability-severity-model.md:63-68` ("Nothing in sections 1–6
increases coverage, and section 7 is not optional … Ship section 7 in the same release as sections
2–4 or the programme makes a hollow engagement look cleaner") and `:1980` ("without them the whole
programme is a suppression engine"). "Or earlier" is if anything *more* faithful to the document's
own build order than "same release" — which is precisely why claim 23 is a problem.

**23. The recommended RG-1 implementation order is E2 → E1 → E3 → E5 → E4 → coverage counterweight —
`OVERSTATED`.** It is a verbatim-faithful reading of one document:
`rg1-implementation-surface.md:505-508`. It is presented as *the* recommendation when a second
document recommends a different one and nobody has reconciled them.
`exploitability-severity-model.md:1978-1988` gives the build order as: **(1)** §7.6 report freshness
+ §7.2 zero-zero rule — i.e. **coverage first, not last**; **(2)** `verified_by != discovered_by`
+ stop self-certifying (E3); **(3)** applicability filter (E2); **(4)** environment (E1);
**(5)** `review.jsonl` + `merge_review.py` (E4/E5 territory); **(6)** the ladder.

So the two documents disagree on two points that matter: whether coverage ships first or last, and
whether E3 precedes E2. The severity model's reason for putting coverage first is the strongest
argument in either document — "without them the whole programme is a suppression engine" — and it is
the one the summary inverted. See §3, gap 1.

### 15–17 · Test libraries

**15. Nuclei's `code` protocol executes commands on the scanning host, and CVE-2024-43405 is in that
root-cause class — `SUPPORTED`, CVE independently verified.** `test-library-composition.md:236-251`.
NVD's description of CVE-2024-43405, fetched this session: "a vulnerability in Nuclei's template
signature verification system could allow an attacker to bypass the signature check and **possibly
execute malicious code via custom code template**", versions 3.0.0 to <3.3.2. The document's causal
framing — that the bypass class exists *because* `code`-protocol templates can execute locally — is
correct on the primary text. One loose adjective: the document calls it "high-severity"; I could not
extract a clean base score from NVD's record in this session, so drop the adjective or source it.

**16. Nuclei's current pinning flags are `-t <dir>` and `-duc`; `-td`/`-templates-directory` do not
exist in the current CLI — `CONTRADICTED`, and this one is a live foot-gun.**

Checked against `cmd/nuclei/main.go` at tag `v3.11.1`:

```
:299   flagSet.BoolVarP(&options.TemplateDisplay, "template-display", "td", false,
                        "displays the templates content"),
:492   flagSet.CallbackVarP(disableUpdatesCallback, "disable-update-check", "duc",
                        "disable automatic nuclei/templates update check"),
```

`-t`/`-templates` and `-duc`/`-disable-update-check` are correct. But **`-td` exists in v3.11.1**.
It is the short form of `--template-display`, a **boolean**. Only `-templates-directory` is absent.
The consequence is worse than a wrong flag name: `nuclei -td /pinned/templates …` does not fail
loudly — it sets a boolean display flag to true and leaves `/pinned/templates` as an unconsumed
argument, so a wrapper written against the old guess would run against nuclei's *default* template
resolution while appearing to have pinned. That is exactly the silent-wrong-answer failure mode a
pinned test library exists to prevent.

`test-library-composition.md:55` carries the same error ("the prior doc's guess of
`-td`/`-templates-directory` was wrong; there is no such flag in the current CLI") and must be
corrected — see §5.

Separately confirmed against primary sources this session, both correct:
`projectdiscovery/nuclei` latest release `v3.11.1` (2026-08-08) and `nuclei-templates` latest tag
`v10.4.7` (2026-08-03), matching `test-library-composition.md:11`.

**17. nmap has no upstream digest-pinnable artifact, only a version string — `SUPPORTED`.**
`test-library-composition.md:201` and `:406-408`, which grades it `pin_strength: version_string`,
"WEAKEST pin in the set", and explicitly warns against implying parity with the digest-pinned tools.
The document is honest that its two direct fetches to `nmap.org/dist/` and `nmap.org/npsl/` failed
(`:120-122`, `:164`, `:650-655`) — but note the pinning conclusion does not depend on those fetches
(it depends on the absence of an nmap-published image, established from Docker Hub), whereas the
**NPSL licensing** conclusion at `:162-177` partly does. Do not carry the licensing conclusion
forward at the same confidence as the pinning one.

### 18–20 · Containment and enforcement

**18. The operator's machine is a VMware Fusion guest on Apple Silicon with no `/dev/kvm`, so
Kata/Firecracker/nested KVM are unavailable — `SUPPORTED`, independently verified on the machine.**
`systemd-detect-virt` → `vmware`; `/sys/class/dmi/id/product_name` → `VMware20,1`;
`sys_vendor` → `VMware, Inc.`; `/proc/cpuinfo` CPU implementer `0x61`; `ls /dev/kvm` → no such file.
Matches `containment-architecture.md:16-30` exactly. This is the strongest-evidenced claim in the
whole session and the correction it forces on spec §9.10 (`:708-714`) should be applied.

**19. A gateway *container* fails property 1 because the filtering principal would be a user in
group `sudo`; the gateway must therefore be a second VM — `OVERSTATED` on both halves.**
The sudo fact is real — `id` on this machine returns `…,27(sudo),…` — and
`containment-architecture.md:86-90` is correctly reasoned. Three corrections:

1. The failing principal in the document's table is "**rootless container run by `hiranya`**", and
   it fails because the workload can *become* `hiranya`, who is in `sudo`. "The filtering principal
   would be a user in group sudo" restates the conclusion as the premise.
2. The document's *second* row — root on the Kali guest, workload as a dedicated non-sudo user — is
   graded "**only via local privilege escalation**", i.e. §9.9's weak-boundary row. Not "fails".
   So a container-shaped gateway is weak, not automatically disqualified.
3. "Must therefore be a second VM" overstates the document's own conclusion.
   `containment-architecture.md:52-70` names macOS `pf` filtering the Fusion vmnet as the cheaper
   variant that "**still satisfies property 1**", worse on properties 3–5. A second VM is the
   recommendation; it is not the only property-1-satisfying option, and saying so removes the
   operator's fallback if RAM turns out not to be there (see §3, gap 6).

**20. `scripts/scope_guard.py` writes no ledger row on allow, making §9.9 reconciliation impossible
against current code — `SUPPORTED`, verified in code, and the true position is worse.**
`evaluate()` ends `return Decision.permit()` with no side effect
(`scripts/scope_guard.py:687`), and `emit()` is documented as
`"""Write the hook's response. Silent on allow, by design."""` with an early `return` on
`decision.allow` (`:76-79`). So no allow row.

**It writes no ledger row on deny either.** Denials go to `sys.stdout` as a `PreToolUse` JSON
response and, on the `--check-url` path, to `sys.stderr` (`:734-737`). No `open()`, no append, no
JSONL anywhere in the decision path. `docs/specs/redgold/07-enforcement.md:433` requires that "the
off-host egress log (§9.9) and `scope_guard`'s decisions must be **reconciled**". There is no
`scope_guard` decision log of any kind to reconcile against, in either direction. Anything the
spec says about reconciliation is currently a requirement on software that does not exist.

Related and worth surfacing: `scripts/scope_guard.py:672-676` already documents that §5.5's
rate-limiting, `purpose=attribution` logging, and evidence-discard requirements "belong to the
ledger work in later steps and are **NOT enforced here**. Until they are, do not describe
attribution probing as fully constrained." The code is more honest about this gap than the spec is.

## 2. Task 2 — audit of the documents themselves

General assessment first, because it is part of the finding: **these six documents are of markedly
higher discipline than the artifacts the four prior audit rounds were run against.** The privacy
document in particular does the thing this repo's hard rules ask for and almost nobody does — it
reports its own retrieval layer inventing `s 6D(1)(k)`, in its own source list
(`privacy-act-feasibility.md:1401`), against its own interest. My spot-checks below found no second
instance of that failure. The defects that follow are real but they are second-order.

### 2.1 Contradiction between documents — the three you asked about

**(a) Severity model vs test-library, on fuzzing and scanner output — not a contradiction, a
missing seam, and it is the most consequential finding in this section.**

`test-library-composition.md:253-266` excludes `flow`/DAST/fuzzing templates from the baseline
*and* from `rg-webtest`'s scripted layer, on P10 determinism and Tier-1 blast-radius grounds. The
severity model does not disagree with this. The severity model **does not mention it at all**:
`grep -in 'fuzz|nuclei|DAST|scanner output' exploitability-severity-model.md` returns **zero
matches**. The two documents do not conflict; they do not touch.

That is a problem, because the severity model makes `precondition` and `grants` required fields on
every technical finding above `low` (`:1265-1300`), and both are **agent declarations**. A pinned
nuclei or testssl.sh run emits records mechanically, with no agent in the loop to declare what an
attacker must already hold. So for every finding RG-3's pinned libraries produce, one of three
things must be true and no document says which:

- scanner-generated findings are capped at `low` by construction (defensible, and roughly what
  E3 + "stop self-certifying" already achieves — but then RG-3's pinned libraries can never produce
  an above-Low finding without a subsequent agent pass, which is a significant product statement);
- a static per-check mapping table supplies `precondition`/`grants` (cheap for `baseline_scan.py`'s
  12 checks; unbounded for nuclei's template corpus);
- an agent post-processes every scanner record (reintroduces exactly the judgement the pinned
  libraries were adopted to remove).

The severity model half-notices this at `:1849` — "`baseline_scan.py`'s `Check` tuple has a name, a
predicate and a hardcoded [severity]" — and does not follow it through. See §3, gap 2.

**(b) Containment doc vs the operator's stated requirement — no conflict; the doc satisfies it
literally.** The requirement was: agent in a container, behind a forward proxy, on a VM whose egress
is filtered by a separate machine. `containment-architecture.md:38-44` delivers exactly that
shape — `rg-work` VM, agent as non-sudo `redgold` in a rootless `--cap-drop=ALL` container,
CONNECT proxy on `rg-gw` (`:40`, `:402`), egress filtered by `root` on a different kernel on a
different VM. The only place the document pushes back on the operator is the *swarm* half
(`:75-105`), and the pushback is correct and well-argued. Note for the record that the document's
second-choice variant (macOS `pf`, `:52-70`) drops the separate-machine-for-filtering property from
"different VM" to "the host that already exists" — still a separate machine, still property 1, so
still inside the requirement.

**(c) Severity model's environment cap vs the autopsy's recommendation — a real, unreconciled
numeric conflict, and it is the single number the RG-1 spec has to state.**

| | non-production cap | bypass mechanism |
|---|---|---|
| `prior-engagement-autopsy.md:578-581` (E1) | technical findings capped at **`low`** for *any* `environment != production` | `applies_to_production: true` with a stated reason |
| `exploitability-severity-model.md:43-44, 673-674` | `staging` → **`high`**, `development` → **`medium`**, `ephemeral-preview` → **`low`** | `production_nexus`, five-value closed vocabulary, each requiring its own resolving evidence pointer |

These are different by up to two bands on the same finding, with different escape hatches and
different evidentiary burdens on the escape hatch. The severity model gives a reasoned defence of
the graduated version (`:673-674`, `:698`) and it is the better design — but it never states that it
is *overriding* the autopsy, and the orchestrator's summary carried E1 forward by its autopsy name
while carrying the cap forward by its severity-model values. Whoever writes the RG-1 spec must pick
explicitly and record why. This is a decision, not research; it costs one paragraph and it is
un-skippable.

### 2.2 Internal contradictions

**Severity model §3.5 vs §3.6 — the classifier "can never confidently emit `production`", except
where it can.** `:762-765` states the asymmetry flatly. `:773-775` then defines a
`prod-signal-present` classifier verdict, and `:847-853` defines the conjunction that earns it:
`reach: internet` **plus at least one** of a publicly-resolving CA-issued cert on a registered apex
domain, a live payment key prefix, non-synthetic PII in a response, or a production-shaped analytics
endpoint. That verdict is blocking against a declared `staging` — it is the row the document calls
"the case that matters most".

The document is *reconcilable*: §3.5 is about the classifier setting `environment`, §3.6 is about it
cross-checking a declaration. But it is not reconciled in the text, and the sentence at §3.5 is the
one that propagated into the orchestrator's summary as an absolute. Someone implementing from §3.5
alone would not build §3.6's conjunction. One clarifying sentence fixes it.

**Severity model's attribution to the composition doc is wider than the source.**
`:760-761` says "`test-library-composition.md` §5 **establishes** the constraint … the strong
signals are conclusive when present and silent when absent." What §5.7 actually says, of exactly
one signal (`test-library-composition.md:625-627`): the self-signed/localhost TLS cert is
"near-conclusive when present … silent (proves nothing) when absent." Signal 1 (platform preview
headers) is described as "the platform itself asserting the fact", signal 3 as "near-conclusive when
the branded form is seen", signal 5 as "a convention rather than an enforced fact". The general
principle is a reasonable *inference* across those, and it is probably right; it is not established
by the cited section. Restate it as the severity model's own derivation, not the composition doc's
finding.

**Autopsy — no internal contradictions found.** Its `[UNVERIFIED]` markers are placed where the
evidence stops, including at `:697-700` where the marker cuts against its own strongest false-negative
claim (whether the `id` the content API exposes is the `uuid` `/p/:uuid` consumes). That is the
discipline hard rule 5 asks for, applied against the author's own thesis.

### 2.3 Unsourced confident assertions

Checked systematically across version strings, CVE IDs, section numbers, capability claims and
numbers. Findings, worst first:

1. **`-td` (claim 16).** The only assertion in the six documents that is affirmatively wrong against
   a primary source, and it is a capability claim about a CLI the framework will shell out to.
   `test-library-composition.md:55`.
2. **`docker` group → `host-root` (claim 13).** Correctly self-flagged as unfetched at
   `exploitability-severity-model.md:1960-1962`; stated flatly in the body at `:406-411`. The body
   should carry the marker, not just the appendix — a reader who loads §2.3 to implement the rank
   table never sees §B.
3. **"High-severity" for CVE-2024-43405** (`test-library-composition.md:240`). Adjective not
   sourced; the CVE and its mechanism are.
4. **`s 6E(1A)` commencement date** (claim 7). Marked `[P]`; the marker is in the appendix table at
   `:1361` and a `[VERIFY]` note at `:319`, but §3.1's heading reads "**1 July 2026, already in
   force**" — a heading is where a reader stops.
5. **runc CVEs** `CVE-2025-31133`, `CVE-2025-52565`, `CVE-2025-52881`
   (`containment-architecture.md:105-111`). Three primary-source links given (runc GHSA, Sysdig,
   CNCF). Not independently re-fetched by me; sourcing is present and adequate on its face.
6. **`~768 MB` for `rg-gw`** (`containment-architecture.md:40`, `:672`). A sizing estimate with no
   stated basis. Harmless in itself, load-bearing for the RAM open item — see §3, gap 6.

**Version strings I re-verified against primary sources and which held:** nuclei `v3.11.1`,
nuclei-templates `v10.4.7`, Privacy Act Compilation No. 104 / 4 June 2026 / Act No. 75 2025,
s 6D `$3,000,000`, Act No. 128 2024 sch 1 items 87–89 commencing 10 Dec 2026. **No fabricated
numbers found.** Given that two prior audits caught citation errors, that is worth stating plainly.

### 2.4 `[VERIFY]` discipline, and the section-number spot-check

**Spot-check result: no second invented section number.** I extracted the compilation with
`zipfile`, stripped the WordprocessingML, and checked every Privacy Act section cited in
`privacy-act-feasibility.md` that appears more than once, plus every subsection-level citation:

| Cited | In the Act | Verdict |
|---|---|---|
| s 6D(1), (4), (5), (7), (8), (9) | 6D(1) turnover test; (4) "not a small business operator if…" (a)–(f); (5) private affairs; (7) disclosure compelled/consented; (8) collection with consent; (9) related bodies corporate | all correct |
| s 6DA(1) | "6DA What is the annual turnover of a business?" | correct |
| s 6E(1), (1A), (1B), (1C), (1D) | (1) regulations; (1A) reporting entity; (1B) protected action ballot agent; (1C) registered employee association; (1D) CDR accreditation | all correct, including the unusual ordering where (1A)–(1D) precede (1) in the printed text |
| s 6C(1) | `organisation` definition | correct |
| s 13K(1) | civil penalty provision, listing APP 1.3, 1.4, 2.1, 6.5, 7.2(c)/7.3(c), 7.3(d), 7.7(a), 7.7(b), 13.5 | correct, and the APP sub-clause list is correct item-for-item |
| s 26WE(1), s 26WH(2) | 26WH(2) is the 30-day assessment obligation | correct |
| s 33C | "Commissioner may conduct an assessment relating to the Australian Privacy Principles etc." | correct |
| s 14(1) | quoted in the doc's preamble re Schedule 1 | correct |

The one `29(1)` citation in the document is **ACL** s 29(1)(g)/(h), not Privacy Act s 29 (which has
no subsections in this compilation), and it is already marked `[VERIFY]` at `:937` with the failed
retrievals named. No confusion, no error.

**Markers that should exist and do not:** the two named in §2.3 items 2 and 4 — the `docker`
mapping in the severity model's body, and the "already in force" heading in the privacy doc's §3.1.
Both are cases where the marker exists somewhere in the document but not at the point a reader
would act on the claim. That is the specific failure this repo's summary-fidelity problem is made
of: the orchestrator read the headline, not the appendix, and so will the next implementer.

### 2.5 Retrospective self-adjudication — how much weight the 8/11 scoreboard bears

**Almost none as validation, and the document mostly says so — but its stated reason is wrong, and
the wrong reason understates the problem in one respect and overstates it in another.**

The caveat at `exploitability-severity-model.md:1244-1248` reads: "The scoreboard above is
retrospective and was written by **the same author as the model**." That is likely false as a
matter of fact — the autopsy and the severity model were produced by two different research agents
in this session. It is a *self-deprecating* error, which is the safe direction, and I would not
flag it except that the wrong diagnosis produces the wrong remedy.

The actual structure of the problem:

- **Not common authorship — common corpus and sequential exposure.** The severity model's author
  read the autopsy's verdicts and then designed a model that reproduces them. Every rung of the
  capability ladder that exists because the prior engagement had a mail catcher (`env-secret-read`, conceded at
  `:1252-1255`) is a free parameter fitted to the test set. Eleven findings, one engagement, one
  application stack, one deployment topology, and a vocabulary designed after seeing the answers.
  A model with that many degrees of freedom scoring 8/11 on its own fitting set carries essentially
  no information about out-of-sample behaviour. The document's own §4.5(3) is the honest version of
  this and it is stronger than §4.5(2).
- **What the scoreboard *does* legitimately evidence.** Internal consistency and mechanisability.
  W-2 (F-107) in particular is checkable by a reader from the published rank tables without
  adjudicating anything — the ranks are declared, the comparison is arithmetic, the answer follows.
  That is a real property and it is the property the model most needs: it shows the rule can be
  *implemented deterministically*, which is a different and lower claim than "it gets the right
  answer". Read the scoreboard as a specification conformance test, not an accuracy measurement.
- **Is the document's caveat sufficient?** As a *disclosure*, yes and more than most — §4.5 leads
  with "P9 applies to numbers that flatter us", `:1246` bars "8 of 11" from client-facing and
  marketing material, `:1437` repeats the bar, and §B(6) at `:1955-1959` states the correct
  validation protocol (freeze the model, run it against the *next* engagement before adjudication,
  compare). As a *control*, no: it is a sentence in a research document, and the failure mode this
  repo keeps hitting is that a number survives the document that qualified it. The bar needs to be
  mechanical. Concretely: `report.py` and any marketing copy should have a literal deny-list on the
  string, the same way `VERIFICATION_CODES` is a literal set — and the model version should be
  frozen and tagged *before* the next engagement so that "we did not adjust it after seeing the
  answers" is checkable from git rather than asserted.

One further weight-reduction the document does not name: **the scoreboard's denominator is
adjudicated by the autopsy, and the autopsy adjudicated five findings SOUND.** The claim "none of
the five findings the autopsy adjudicated SOUND is suppressed" (`:1233-1234`) is the most important
line in §4.4 — it is the false-negative check — and it is measured against five instances. Five is
not enough to detect a suppression bias of any plausible size. The coverage counterweight (§7) is
the real control for that risk, which is another reason its position in the build order is not a
detail.

## 3. Task 3 — ranked research gaps

Ranked by (probability the answer changes a design already being written) × (cost of finding out
late). Items marked **decision** are not research — they are a choice someone has to make and
record, and they are ranked here because leaving them unmade blocks the same work a research gap
would.

### Rank 1 — Which build order, and does coverage ship first or last? *(RG-1, decision)*

**Question.** `rg1-implementation-surface.md:505-508` says coverage counterweight **last**;
`exploitability-severity-model.md:1980` says the two cheapest coverage rules (§7.6 report freshness,
§7.2 zero-zero) ship **first**, "without them the whole programme is a suppression engine". Which?

**Why it blocks.** RG-1 is a programme whose sections 1–6 only subtract severity
(claim 22, `SUPPORTED`). If it ships in the summary's order, there is a window — potentially the
whole of RG-1 — in which the framework is strictly better at making findings disappear and no better
at noticing it produced nothing. The autopsy's worst single finding is an engagement that produced
**zero artifacts** (`prior-engagement-autopsy.md:22`), and nothing in E1–E5 addresses it. This is the exact
failure mode the repo's audit history is about, arriving through a summary that dropped a
qualification.

**Blocks:** RG-1 specifically, at the level of what ships in the first release.

**Cheap first step.** Reconcile by inspection, not research — the two orders are compatible.
§7.2 (a phase may not complete with zero findings *and* zero recorded negatives) and §7.6 are
described as "ten lines between them" and touch none of E1–E5's functions
(`rg1-implementation-surface.md:498-502` confirms no ordering constraint). Put them first, keep
`rg1-implementation-surface`'s E2→E1→E3→E5→E4 for the rest, and keep the §7.1/7.3/7.5 coverage
register after E1. That is a fifteen-minute edit to the plan and it removes the only structural
objection to the summary's order.

### Rank 2 — Who populates `precondition` and `grants` on scanner-generated findings? *(RG-1 schema; endangers RG-3)*

**Question.** The severity model requires `precondition` and `grants` on every technical finding
above `low` and both are agent declarations (`exploitability-severity-model.md:1265-1300`). Pinned
scanners emit records with no agent in the loop. Which of the three options in §2.1(a) is the design?

**Why it blocks.** It determines the schema RG-1 writes, whether `validate_record()` can require
these fields unconditionally or only for agent-authored findings, and whether RG-3's pinned
libraries can ever produce an above-Low finding on their own. Get it wrong in RG-1 and either every
scanner record fails validation, or the requirement is quietly optional and the whole dominance
mechanism becomes advisory. The severity model contains **zero** mentions of nuclei, fuzzing, DAST
or scanner output, so this seam has not been designed by anyone.

**Blocks:** RG-1 (schema and validator), and RG-3 cannot be specced against it until it is answered.

**Cheap first step.** Enumerate `baseline_scan.py`'s 12 `Check` tuples and write the
`precondition`/`grants` each would declare. My expectation is that the answer is near-uniform
(`precondition: {reach: internet, capability: none}`, `grants` varying over a handful of values),
which would make a static per-check table a ~12-row addition to the existing `Check` namedtuple and
settle the question for the baseline scanner in an afternoon. Nuclei's corpus is a separate and
much harder instance of the same question and belongs to RG-3 — but answering it for
`baseline_scan.py` tells you whether the static-table approach generalises at all.

### Rank 3 — What is the environment cap, and what is the bypass? *(RG-1, decision)*

**Question.** Autopsy E1: cap **`low`** for any non-production, bypass `applies_to_production: true`.
Severity model: `staging`→`high`, `development`→`medium`, `ephemeral-preview`→`low`, bypass
`production_nexus` from a five-value vocabulary with per-value evidence pointers. Which?

**Why it blocks.** It is the number the RG-1 spec must literally state, it differs by up to two
bands, and the two bypass mechanisms impose very different evidentiary burdens. It also interacts
with rank 2: if scanner findings cannot declare `precondition`/`grants`, the environment cap becomes
the *only* thing modulating their severity, which raises the stakes on getting it right.

**Blocks:** RG-1 specifically.

**Cheap first step.** Operator picks in one sitting. The severity model's graduated version is
better-argued (`:673-674`, `:698`: capping a live Resend key at `medium` because the laptop is a dev
box is the error the autopsy warns about) and carries the `production_nexus` machinery that makes
the bypass auditable. Recommend adopting it and recording explicitly that it supersedes E1's flat
`low`, so the next reader does not re-derive the conflict.

### Rank 4 — The `-td` collision, and whatever else the earlier survey guessed *(RG-3)*

**Question.** `test-library-composition.md:55` asserts `-td` does not exist. It does, as
`--template-display` (boolean). What else in the pinned-tool invocations came from the 2026-08-04
survey's guesses rather than from a `--help` dump?

**Why it endangers work.** A wrapper built on the stated flag set would silently run unpinned
(§1, claim 16). The whole value of a pinned test library is that the pin is verifiable; a pin that
silently does not apply is worse than no pin, because it is reported as applied.

**Blocks:** RG-3. Not RG-1.

**Cheap first step.** Run `nuclei -h`, `testssl.sh --help`, `nmap --help` inside the target
container image and diff the real flag surface against every flag string in
`test-library-composition.md` §1 and §4.2. Thirty minutes, mechanical, no agent needed — and per
CLAUDE.md's working preferences this is exactly the kind of retrieval that should not have been
delegated to a model in the first place. Correct `:55` first (see §5).

### Rank 5 — Vercel/Netlify preview-header semantics, before they gate Gate 1 *(RG-1)*

**Question.** `exploitability-severity-model.md:773` makes `nonprod-signal-present` against a
declared `production` a **blocking** `ENVIRONMENT_DISCREPANCY`, and the top-ranked signal is
`x-vercel-deployment-url` resolving to a `*.vercel.app` host
(`test-library-composition.md:519-537`). Is that header actually present only on preview
deployments, or is it present on production responses too?

**Why it blocks.** This is the one place where an unverified signal produces a *refusal*. If the
header is emitted on production responses as well (the composition doc says it "carries the
underlying deployment URL even when the request arrived on a custom domain" — which reads like it
is present on production traffic too), then every Vercel-hosted production engagement trips a
blocking violation at Gate 1. A gate that fires on healthy inputs gets disabled, and a disabled
gate is the E1 counterfactual undone. The composition doc's own §5.1 failure-mode note is about a
*different* case (deliberate preview-behind-production) and does not answer this one.

**Blocks:** RG-1 — specifically E1's discrepancy rule, not the `environment` field itself.

**Cheap first step.** `curl -sI` any known Vercel-hosted production site and look for the header.
Five minutes. If it is present on production, the signal must be narrowed to "header resolves to a
`*.vercel.app` host **and** the request Host is also `*.vercel.app`", or demoted from a blocking
verdict to a contributes-only signal.

### Rank 6 — Host RAM, and whether the three-VM topology fits *(RG-2)*

**Judgement: more severe than the containment doc's own ranking implies, and I have a partial
answer it did not have.** This Kali guest reports `9.7 GiB` total RAM. Whatever the Mac has, ~10 GB
of it is already committed to this guest. `containment-architecture.md:672-675` budgets `~768 MB`
standing for `rg-gw` plus `4–6 GB` for `rg-work` during an engagement. On a 16 GB Mac that is
10 + 0.75 + 5 ≈ 16 GB before macOS itself, which does not fit.

The important consequence is a design one, not an arithmetic one: **the answer is probably to
*replace* this Kali guest with `rg-work`, not to add `rg-work` alongside it.** The containment doc
frames the topology as additive (`:638`, `:672`) and never considers that the operator's existing
working environment and the disposable engagement VM might have to be the same slot. That changes
the provisioning story materially — `rg-work` being disposable means the operator's daily
environment cannot live in it.

**Blocks:** RG-2. Not RG-1.

**Cheap first step.** Ask the operator for the Mac's RAM — one question, no research. If it is
16 GB, re-open the topology section with the replace-not-add constraint, and re-rank the macOS `pf`
variant (`containment-architecture.md:52-70`), which needs no second VM at all and which claim 19
wrongly wrote out of the running.

### Rank 7 — What `open-vm-tools` exposes guest→host *(RG-2)*

**Judgement: correctly ranked by the containment doc as "the most likely hole in the design"
(`:688-691`), and cheaper to answer than the doc assumes.** I did the first ten minutes of it:
`open-vm-tools 2:12.5.0-2` (arm64) and `open-vm-tools-desktop` are installed, `vmware-toolbox-cmd`
and `vmtoolsd` are on PATH, and the command surface includes `gueststore` (guest-initiated fetch
from a host-side store) and `upgrade` (guest-initiated tools upgrade driven by the host). Both are
guest→host channels on their face. This is a live question, not a theoretical one.

**Why it blocks.** If the workload can drive host-side operations through the tools channel, the
`rg-work`→control-tier boundary that the entire three-tier design rests on is bypassable, and the
answer is not "add a firewall rule" — it is "strip open-vm-tools from the `rg-work` template", which
has knock-on effects on shared folders, clipboard, and time sync that the doc's §4 depends on.

**Blocks:** RG-2. Not RG-1.

**Cheap first step.** On this machine, right now: `vmware-toolbox-cmd help gueststore`,
`vmware-toolbox-cmd config get …`, and check whether `vmtoolsd` honours RPC from an unprivileged
user (`vmware-rpctool 'info-get guestinfo.x'` as a non-root, non-sudo user). Then read VMware's
own docs on `isolation.tools.*` config keys for disabling the channel from the `.vmx` side —
host-side disable is the control that survives a guest compromise, and it is the one the design
actually needs.

### Rank 8 — `scope_guard.py` writes no decision log at all *(RG-2, engineering)*

**Question.** None, really — the answer is known (claim 20). The gap is that spec
`07-enforcement.md:433` requires reconciliation between the off-host egress log and `scope_guard`'s
decisions, and `scope_guard` has no decision log on allow *or* deny. Every §9.9 reconciliation
statement is currently a requirement on non-existent software.

**Blocks:** RG-2. Cheap first step: append a JSONL row in `emit()` before the early return. This is
engineering, not research, and it should be a line item in RG-2's spec rather than an open question.
Flagged here because the summary presented it as a research finding about the documents when it is
a build task.

### Rank 9 — `s 6(1)` definitions and the four HTTP-403 legal items *(RG-5)*

**Judgement: correctly ranked by the privacy doc, and not urgent, because RG-5 is not next.**
`privacy-act-feasibility.md:1363` marks the `s 6(1)` definitions of *personal information*,
*sensitive information*, *APP entity* and *holds* as "**not read in this pass**; required before any
classifier or questionnaire is built" — which is the right gate and it is already stated. The four
403s (LPUL s 10, ACL s 18/s 29) are marked `[L]` — needs a lawyer — and the doc names #4, #15, #16
as "the three that block everything". Nothing here can be fixed by more research; #4 needs a
solicitor, #15 needs a broker.

One correction to the framing: the `s 6(1)` definitions are **not** a 403 problem. The compilation
is on disk and I read arbitrary sections out of it in seconds with `zipfile`. That item is thirty
minutes of reading whenever RG-5 starts, not a blocked retrieval.

**Blocks:** RG-5 only. Cheap first step: none needed now; do it at RG-5 kickoff.

### Rank 10 — `nmap.org/dist/` and `nmap.org/npsl/` fetch failures *(RG-3, low)*

**Judgement: lower severity than the composition doc's own carry-forward implies for pinning, and
slightly higher for licensing.** The pinning conclusion (claim 17) rests on the absence of an
nmap-published container image, established from Docker Hub, not from `nmap.org` — so the failed
fetches do not weaken it. The **NPSL** conclusion at `test-library-composition.md:162-177` does
partly rest on them, and licensing is the kind of claim that ends up in a client contract.

**Blocks:** nothing. Cheap first step: retry both URLs; they failed twice from one environment on
one day and there is no reason to believe the pages are gone.

### Is the deployment-state signal research adequate for a *required* `scope.yaml` key that refuses Gate 1?

Asked directly, so answered directly. **Yes for the key, no for the classifier, and the severity
model has already drawn that line correctly — with the one exception at rank 5.**

- **The required key itself** does not depend on the signal research at all. `environment:` is
  operator-declared; the refusal is for `absent` or `unknown`
  (`exploitability-severity-model.md:43`). Refusing to start until a human answers "is this
  production" needs no signal research to justify, and it is the single highest-value item in the
  autopsy. Ship it.
- **The classifier** is explicitly demoted to a cross-check that never sets the value
  (`:766-767`: "The classifier's output is therefore **never** the value of `environment`"). Six
  signals with self-documented failure modes are entirely adequate for that role.
- **The exception** is that one classifier verdict *blocks* (rank 5). A signal good enough to
  contribute to a cross-check is not automatically good enough to refuse a Gate. Either verify the
  Vercel header semantics before wiring the blocking path, or ship the blocking path only for the
  four signals whose semantics are unambiguous (self-signed cert, `pk_test_`/`sk_test_`,
  framework debug page, dev-tool service fingerprint — the last of which is what actually fires on
  the prior engagement, four times over, per `:798-800`).

## 4. Can RG-1 be specced now?

**Yes.** Nothing found in this audit is a research blocker for RG-1. The two `CONTRADICTED` claims
land on RG-3 (`-td`) and on E4's design rationale (`rg-verify`), and neither requires new research to
resolve — one is a thirty-minute `--help` diff, the other is a correction to a premise. The five
`OVERSTATED` claims are all cases of a qualification dropped in summarisation; every one of them has
its qualification sitting in the source document, already written.

I want to be explicit that I looked for a reason to say no and did not find one. The code checks
came back clean in the sense that matters — claims 2, 4 and 20 are all true of the actual repo, and
claim 3, the one that was wrong, was wrong in a direction that makes the situation *less* dire, not
more. The privacy document survived a systematic section-number audit against the primary source
with zero errors. The severity model's central structural argument (CVSS cannot express a
cross-system precondition) is correct on the v4 spec's own text. This is a session worth building on.

**The spec must treat these five as provisional and say so in the spec itself, not in a research
doc that the implementer will not read:**

1. **The environment cap values and the bypass mechanism** (§2.1(c), gap 3). Pick the severity
   model's graduated caps and `production_nexus`; record in the spec that this supersedes the
   autopsy's flat `low`/`applies_to_production`, so nobody re-litigates it from the autopsy.
2. **`precondition`/`grants` on scanner-generated findings** (§2.1(a), gap 2). The spec must state
   which of the three options it takes. Until it does, `validate_record()` cannot require the
   fields, and a requirement that is conditional-on-nothing is not a requirement.
3. **Build order, with the two coverage rules moved to the front** (§2.1, gap 1). §7.2's zero-zero
   rule and §7.6's report-freshness rule ship in release one, ahead of E2. Ten lines, no
   dependencies, and they are the only thing preventing RG-1 from being a pure suppression release.
4. **E4's premise.** `rg-verify` can already write to disk via `Bash` (claim 3). Spec E4 as
   "a required structured verdict at a mandated path, with a schema, and a merge that fails closed
   on a missing row" — not as "give the verifier a write capability". If the implementation grants
   `Write` it should be for schema-conformance reasons, not because writing is currently impossible.
5. **The `docker` → `host-root` rank and the "8 of 11" figure.** The first carries an unfetched
   citation (claim 13) and must not reach a client report until Docker's own docs are cited. The
   second must be barred mechanically, not by a sentence in a research doc (§2.5) — and the model
   version should be frozen in git before the next engagement so the freeze is checkable.

**One thing to do before the spec, because it is cheaper than doing it after:** rank 5's `curl -sI`
against a Vercel production site. Five minutes, and it determines whether E1's discrepancy rule
ships blocking or advisory. That is the only pre-spec item I would insist on.

**Not blockers, explicitly:** host RAM, `open-vm-tools`, `api.anthropic.com` CIDRs, the nmap.org
fetches, and every privacy item. All of them belong to RG-2, RG-3 or RG-5. None of them touches
RG-1's schema, validator, gate, or report path. Do not hold RG-1 for any of them.

---

## 5. Corrections that should be applied to source documents

Listed so they do not have to be re-derived. Each is a small edit, not a rewrite.

| # | File | Correction |
|---|---|---|
| 1 | `test-library-composition.md:55` | `-td` **does** exist in nuclei v3.11.1 as the short form of `--template-display` (boolean). Only `-templates-directory` is absent. Add the warning that `-td <dir>` fails silently rather than erroring. |
| 2 | `exploitability-severity-model.md:406-411` | Move the `[VERIFY]` from §B(3) into the body: the `docker`→`host-root` mapping is not primary-sourced. |
| 3 | `exploitability-severity-model.md:760-761` | Restate the conclusive/silent asymmetry as this document's derivation. `test-library-composition.md:625-627` states it of the TLS signal only. |
| 4 | `exploitability-severity-model.md:762-767` | Add one sentence reconciling §3.5's "can never confidently emit `production`" with §3.6's `prod-signal-present` conjunction. |
| 5 | `exploitability-severity-model.md:1244-1248` | The scoreboard's problem is a fitted vocabulary on a single 11-finding corpus, not common authorship (the autopsy and the model were written by different agents). §4.5(3) is the correct diagnosis; promote it. |
| 6 | `test-library-composition.md:240` | Drop or source the "high-severity" adjective on CVE-2024-43405. The CVE and its mechanism are correctly sourced. |
| 7 | `privacy-act-feasibility.md:276` | The §3.1 heading "1 July 2026, already in force" carries no marker while the date is `[P]` at `:1361`. Put the marker in the heading. Also note that s 6E(1A) has existed since Act No. 170, 2006 — the 2026 change is to the AML/CTF Act's *reporting entity* definition, so the commencement question must be answered against that Act. |
| 8 | `containment-architecture.md:672-675` | Add the constraint that this guest already holds ~9.7 GiB, so on a 16 GB Mac the topology is replace-not-add. |
| 9 | `docs/specs/redgold/08-findings-and-verification.md:129` and `agents/rg-verify.md` | Both reference `playbooks/_generic/false-positives.md`, which does not exist. Create it or remove both references. |
| 10 | `docs/specs/redgold/07-enforcement.md:433` | The reconciliation requirement has no `scope_guard` decision log to reconcile against, on allow **or** deny. Mark it as pending RG-2 rather than as a property of the system. |
