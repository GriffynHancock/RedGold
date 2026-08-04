---
title: Scanner integration — composing the baseline from open-source components
date: 2026-08-04
status: draft
question: Should the nine-check baseline be hand-rolled, wrapped, or composed from open-source scanners plus proprietary checks — and how?
---

## Recommendation

**Compose, don't choose.** Define a versioned **scan profile** — one YAML file per engagement type —
that lists specific nuclei template IDs, specific nmap NSE scripts, one testssl.sh invocation, and
our own hand-rolled checks, each producing a schema-conformant finding through one shared adapter.
Do this first: keep all nine current checks (they are cheap, fast, and already schema-correct),
add nuclei running **only** `http/exposures/*` and `http/misconfiguration/cors*` templates pinned to
a recorded `nuclei-templates` release tag, and add `testssl.sh` for TLS posture (a real gap today).
Do not add ZAP, nikto, or trivy to the baseline — they are useful in `rg-webtest`, not here. One
target per invocation (never `-l`), so `scope_guard.py` needs no change. The client-reusable half of
the deliverable is the open-source template/script list; the paying half is verification, evidence
capture, boundary enforcement, and the checks we author ourselves.

## 1. Coverage — what already exists, per check

| # | Our check | Tool that already does it | Specific unit | Better? |
|---|---|---|---|---|
| 1 | `.env` exposed | nuclei | `http/exposures/configs/env-file-disclosure.yaml` (and several vendor-specific `.env` templates) | Same detection logic (regex on body), no meaningful gain. Ours is fine. |
| 2 | `.git/config` exposed | nuclei | `http/exposures/configs/git-config.yaml` (checks for `[core]`) | Identical technique to ours. Nuclei's template set also covers `.git/HEAD`, `.git/logs/HEAD`, and dumping the whole repo via `git-dumper`-style templates — **that's more than ours**, but the extra is post-detection exploitation, arguably out of Tier-1 scope. |
| 3 | Directory listing | nuclei (`http/exposures/configs/apache-status.yaml` style + generic `directory-listing.yaml`), also nikto | Both regex on `Index of /` — same technique. | No gain. |
| 4 | Admin route reachable | nuclei has thousands of vendor-specific `exposed-panels/*` templates (Grafana, phpMyAdmin, Jenkins, pgAdmin, Kubernetes dashboard, etc.) | e.g. `http/exposed-panels/grafana-login-panel.yaml` | **Real gain.** Our check only knows `/admin`, `/ghost/api/admin/site/`, `/actuator/env` — three hardcoded paths. Nuclei's panel-exposure set is in the thousands and fingerprint-aware. This is the strongest coverage argument for wrapping. |
| 5 | Object storage listing | Nothing hand-tuned for this shape (Supabase/S3/GCS listing JSON) exists as a single generic nuclei template; there are vendor-specific S3-bucket-open templates (`http/exposures/configs/s3-detect.yaml`, `cloud/aws-*`) but they check ACL/bucket-name patterns, not our shape-based JSON-body heuristic. | — | Keep hand-rolled. Nobody else does the vendor-agnostic version we need. |
| 6 | Source map published | nuclei `http/exposures/configs/js-source-map.yaml`-style templates exist but are inconsistent across the template set (several duplicate/overlapping ones) | — | Marginal gain; our check is simpler and already correct. |
| 7 | Wildcard CORS + credentials | nmap NSE `http-cors`, nuclei `http/misconfiguration/cors-misconfig.yaml` (multiple variants: reflected-origin, null-origin, wildcard+credentials) | `http-cors.nse`; nuclei CORS template family | **Real gain** — nuclei's CORS template family tests reflected-origin and null-origin bypasses in addition to the literal wildcard case we check. Ours only catches the blunt `Access-Control-Allow-Origin: *` + `credentials: true` combination, missing the more common "reflects any Origin" misconfiguration. |
| 8 | Missing security headers | nmap NSE `http-security-headers.nse`; nuclei has header-check templates too | `http-security-headers.nse` checks HSTS, CSP, X-Frame-Options, X-Content-Type-Options, X-XSS-Protection, Expect-CT, cache headers | Roughly equivalent coverage; NSE's list is longer (adds X-Frame-Options, Expect-CT, cache-control) than our three headers. Modest gain, cheap to add. |
| 9 | (implicit) TLS/cert posture | **Not covered by us at all today**, despite P10 explicitly naming "TLS and header posture" as in-baseline scope. | testssl.sh | **Genuine gap**, not a wrapping question — this is missing entirely. testssl.sh (GPLv2, `github.com/testssl/testssl.sh`) checks protocol versions, cipher suites, cert chain/expiry, known TLS CVEs (Heartbleed, ROBOT, etc.), HSTS preload status. Nothing hand-rolled does this well; it is genuinely well-trodden, mechanical, deterministic-per-cert ground. |

**What these tools cover that we don't, beyond the nine:** TLS/cipher posture (above), a much larger
panel/admin-product fingerprint library, known-CVE detection for identifiable software versions
(nuclei's `cves/` tree, tens of thousands of templates), default-credential checks for named
products, and DNS/subdomain-takeover style checks (out of baseline scope, belongs in recon). The
panel-exposure and CVE trees are worth the most — they are exactly the class of "vulnerability no
human pentester would overlook" that P10 cites as the failure mode we're defending against, and
hand-maintaining a vendor-fingerprint library ourselves is not a good use of engineering time.

## 2. The determinism problem (the crux)

**Nuclei supports pinning cleanly.** The `nuclei-templates` repo is a separate, tagged, versioned
GitHub repository (currently on a `10.x` release series, e.g. `v10.4.2`/`v10.4.3` in April 2026,
released roughly every 1–2 weeks per the ProjectDiscovery blog's monthly template-changelog posts).
Standard practice for reproducible scanning is exactly what P10 needs: clone/checkout a specific
tag or commit, point `nuclei -update-templates=false -td <pinned-path>` at it, and record the tag in
the finding. [VERIFY: exact current flag names — `-update-templates`, `-td`/`-templates-directory` —
against the installed nuclei version before wiring this up; ProjectDiscovery has renamed CLI flags
across major versions before.]

**What changes between releases, in practice:** overwhelmingly, new CVE templates and vendor
fingerprint additions, plus bug fixes to existing templates' match logic (the April 2026 changelog
example: moved template locations, fixed CVE-ID mismatches, corrected CPE formats). This means two
things for P10:

- A **pinned template set** does not change between runs — this reconciles cleanly with "identical
  every run." The nuclei *binary* itself is a much smaller determinism risk than the template set;
  pin both, but the template set is the one that moves weekly.
- A pinned set will occasionally **miss** a template fix that would have caught something (a
  template that had a bug at pin-time, fixed later). That's an acceptable, honestly-disclosable
  trade — the same trade every static ruleset makes, and it's exactly the trade P11 already asks us
  to make explicit ("coverage is reported explicitly, including what was not examined").

**Conclusion on the crux: yes, reconcilable, and it's the standard fix, not a novel one.** Record
`{tool: nuclei, engine_version, template_repo_commit_or_tag}` on every nuclei-sourced finding. Bump
the pin deliberately and record the bump as a method-version change, the same way we'd version a
playbook (P11 already treats playbook checks as "enumerated and versioned" — nuclei templates slot
into the identical model, they're just externally authored). Roll the pin per **framework release**,
not per engagement, so two client engagements run inside the same pin window agree exactly, and a
version bump is a deliberate, dated decision — not something that happens because a Tuesday auto-
update landed mid-engagement.

## 3. Output and mapping

| Tool | Machine format | Format stability | Notes |
|---|---|---|---|
| nuclei | JSONL via `-jsonl`/`-j` (one JSON object per line, one per match) | Reasonably stable; a formal JSON Schema is published at `nuclei-jsonschema.json` in the repo, which is unusual rigor for this space and makes drift detectable. `-irr`/`-include-response` embeds the raw request/response in the record. | Best of the group for our purposes — request/response can be captured natively per match. |
| nmap (NSE) | XML via `-oX` | Very stable — nmap's XML schema has been stable for well over a decade; scripts add `<script>` elements with `id`/`output` but no strict per-script schema, so NSE output is semi-structured (parseable, but each script's own text is free-form). | Response bodies are not captured — NSE scripts summarize, they don't retain the raw exchange. |
| testssl.sh | Flat JSON + "JSON-pretty" | [VERIFY] — no formal schema published; field names have shifted across major versions per changelogs. | No raw request/response equivalent (TLS handshake, not HTTP) — evidence would have to be the tool's own structured record, not a `.http` file. |
| ZAP baseline | JSON via `-J`, or the newer Automation Framework's structured report | Backed by a documented Alert model (name, risk, confidence, evidence snippet, `messageId` referencing the HAR-like session) | Best request/response fidelity of the group other than nuclei — ZAP retains the full HTTP session and an alert can reference it. |

**Where mapping loses what we currently guarantee:** our schema requires `evidence_ptr` to resolve
to a **file on disk** — a literal `.http` transcript, checked by `resolve_evidence()` in
`scripts/findings.py`. Nuclei (with `-irr`) and ZAP both retain enough to reconstruct that file
faithfully; nmap NSE and testssl.sh do not retain a raw request/response at all, only a rendered
summary. For those two, `evidence_ptr` would have to point at the tool's own JSON/XML fragment
rather than a synthesized `.http` file — which is honest (it's the real machine output) but is a
different evidentiary object than what `baseline_scan.py` writes today, and the adapter must not
silently synthesize a fake `.http` file from a summary to make it *look* like the others. Write the
adapter so nmap/testssl findings carry `evidence_ptr` pointing at the raw XML/JSON output file, not
a fabricated transcript.

`finding_class`/`status`/`verified`/`severity` need an explicit per-tool mapping table (nuclei's
`info.severity` maps directly to ours; NSE has no severity field at all — every NSE-sourced finding
needs its severity assigned by the mapping table we author, same as our own `Check.severity` today).
This mapping table is itself part of the secret sauce (see §3 of the reframe below).

## 4. The scope_guard file-target problem

`scripts/scope_guard.py`'s `FILE_TARGET_LIST_RE` denies `-iL`, `-l`/`--input-file`,
`--target-file`, `-w` — any flag that hands the target list to the tool via a file the guard never
opens (`# Target lists live in files this hook never opens (§9.3.1)`). Nuclei accepts single-target
input via `-u <url>` (or `-target`, depending on version) with no file involved; nmap accepts a bare
hostname argument. **Resolution: one target per invocation, driven by our own loop, exactly the
pattern `baseline_scan.py` already uses today** (`for base in bases: ... fetch(url)`) — the composed-
scan wrapper does the same thing: iterate `confirmed_targets()`, and for each, shell out to
`nuclei -u <single-target>`, `nmap <single-host>`, `testssl.sh <single-host>` individually. This is
strictly the right answer, not just the scope_guard-compatible one: it's what other authorized-scan
setups do too — CI/CD nuclei integrations and bug-bounty tooling both favor per-target or small-batch
invocation specifically because it keeps rate limiting, resumability, and per-target evidence capture
tractable; a single `-l targets.txt` run against a mixed engagement makes it hard to attribute a
timeout or a rate-limit response to the right asset. No change to `scope_guard.py` is needed — the
integration constraint should live in the wrapper, exactly as the file's own comment anticipates
(`FRAMEWORK_SCRIPTS` already documents this pattern: each listed script "enforces the boundary
itself, in code"). Add the new wrapper script to `FRAMEWORK_SCRIPTS` once it exists and re-checks
`in_boundary()` per target before each shell-out, same as `baseline_scan.py` does.

## 5. False positives and the verification cost

Search results converge on the same practical finding: **nuclei run unscoped and unfiltered is
noisy** — one practitioner account puts unfiltered, unscoped nuclei runs at "80% false positives,"
and multiple bug-bounty guides describe nuclei's proper role as "a triage and replication layer, not
a substitute for human validation," requiring manual confirmation before any result is reported.
[VERIFY: no rigorous, methodologically-disclosed false-positive-rate study for nuclei specifically
was found — the 80% figure is anecdotal, not benchmarked, and should not be cited to a client.] Nikto
has the same reputation, documented in its own issue tracker (#532, #728) as a known, unresolved
problem, worse on esoteric server configurations. ZAP's active-scan rules (not the passive baseline)
are the noisiest of the group; the *baseline* scan specifically (passive-only, spider + passive
rules, no active attack) is comparatively quiet — which is exactly why "ZAP baseline" and not full
ZAP active scan is the right unit to consider at all.

**Does this interact with "no unverified finding above Low reaches a client"?** Directly, and
favorably if scoped correctly. `findings.py`'s `UNVERIFIED_ABOVE_LOW` rule already forces every
above-Low technical finding through `rg-verify` regardless of source. The real risk isn't that the
gate lets a false positive through — it can't, by construction — it's **volume**: if the composed
profile includes broad CVE/panel template sets, `rg-verify`'s workload scales with however many
above-Low hits the scan produces, and a noisy profile could make verification the bottleneck. The
mitigation is at the profile-authoring stage, not the gate: keep the pinned template *set* narrow and
curated (exposures + misconfiguration + a short, deliberately chosen CVE list relevant to fingerprinted
software — not "run all 12,000+ templates"). This is a argument for careful profile composition, not
an argument against wrapping.

## 6. Licensing

| Tool | License | Commercial-use flags |
|---|---|---|
| nuclei (engine) | MIT | None. No usage caps, no attribution requirement beyond standard MIT notice retention. |
| nuclei-templates | MIT | Same — free to use, modify, redistribute, including in a client-facing profile file, provided the MIT notice is retained if templates are redistributed verbatim. |
| nmap / NSE | nmap has its own license (a modified GPL-compatible "Nmap Public Source License") | [VERIFY] — nmap's license has historically had commercial-redistribution caveats (it restricts bundling nmap itself inside a commercial product without a separate agreement in some historical versions); using it as an installed tool invoked via CLI in our own engagements is not "redistribution" and should be unaffected, but if RedGold ever ships nmap *bundled* with the product this needs a real read of the current NPSL text, not this summary. |
| testssl.sh | GPLv2 | GPLv2 requires that if testssl.sh's *source* is modified and distributed, the modifications are shared under GPLv2 too — running it unmodified as an external tool from our wrapper does not trigger this. No restriction on using its output commercially. |
| ZAP (zaproxy) | Apache 2.0 | Permissive, attribution via standard NOTICE retention only. No restriction on commercial/paid engagement use — this is explicitly the design intent (ZAP is Checkmarx-stewarded, positioned for commercial CI/CD use). |
| nikto | GPLv3 (as of 2.6) | Same posture as testssl.sh: running it unmodified imposes no obligation on our own code; redistributing a modified nikto would require sharing changes. |
| trivy | Apache 2.0 | Permissive, but see §"what to keep hand-rolled" — trivy scans containers/IaC/SBOMs, not live HTTP endpoints, so it is largely out of scope for this baseline; flag only if RedGold later adds a container/registry-access-authorized track. |

**None of these licenses restrict paid consulting use.** The one live risk is nmap's NPSL if RedGold
ever bundles/redistributes the binary rather than invoking an installed copy — `[VERIFY]` before any
future packaging decision, not before this integration.

## 7. rg-webtest — what should it drive?

`rg-webtest.md` today is pure prose with no tooling named. Given the composition model above, the
defensible split is:

- **Scripted tool passes** (deterministic, same as baseline): the composed profile's nuclei/NSE/
  testssl runs already happened in `baseline_scan.py`'s successor — `rg-webtest` should **not**
  re-run them. Its own scripted layer is the *authenticated* and *contextual* equivalent: ZAP
  baseline run against session-authenticated routes discovered by recon (ZAP's baseline mode is
  explicitly designed to be safe against production, passive-only), plus targeted nuclei runs scoped
  to `-tags` matching the fingerprinted stack once recon has identified it (P10's "playbook checks
  are additive on top of it" language already anticipates exactly this: fingerprint-triggered,
  conditional, not baseline).
- **Agentic judgement**: business-logic abuse, auth/authz boundary testing across roles (IDOR,
  privilege escalation), multi-step chained exploitation, anything requiring semantic understanding
  of what an endpoint *means* rather than what it matches syntactically. This is exactly the territory
  no scanner template can cover and where P3's "seed hypotheses beat open-ended hunting" principle
  earns its keep — the agent should be seeded with recon findings and playbook entries, not turned
  loose.

**The line:** if a check can be expressed as "does this HTTP response match pattern X," it belongs in
a scanned/templated pass, scripted, deterministic, and outside `rg-webtest`'s agentic loop entirely.
If it requires deciding *what a legitimate response should have been* given business context, it's
agentic. `rg-webtest` should be rewritten to name its scripted layer explicitly (which tool, which
tag-set, pinned to the same profile file) rather than leaving "dynamic testing" undifferentiated
prose — that gap is real and independent of the baseline-composition question.

## Composition: the reframed core answer

**1. Unit of composition.** No existing tool defines this format — nuclei has `-tags`/`-id`
filtering and a config-file allowlist, ZAP has its Automation Framework YAML, but nothing spans
tools. Define `profiles/<name>.yaml` ourselves:

```yaml
profile: web-baseline-v1
pinned:
  nuclei_engine: v3.11.0
  nuclei_templates_ref: v10.4.3          # nuclei-templates release tag
  nmap: "7.99"
  testssl: "3.2.1"                       # [VERIFY exact pin format testssl uses]
components:
  - tool: nuclei
    selection: {tags: [exposures, misconfig-cors]}   # never "all"
  - tool: nmap-nse
    scripts: [http-security-headers, http-cors, http-config-backup]
  - tool: testssl
    args: [--severity, medium]
  - tool: redgold-native
    checks: [bucket_public, sourcemap]    # the ones nothing else covers well
mapping: findings-schema-v1               # which adapter/severity table applies
```

Each engagement's `findings/baseline.json` records which profile + pin ran, same field placement as
`discovered_by` today. This *is* the versioned, enumerable object P11 already asks playbooks to be —
templates and NSE scripts just become externally-authored playbook entries with the same versioning
discipline, not a special case.

**2. Client reuse.** A profile expressed purely as `{tool, selection}` references into MIT/Apache/GPL
tools the client can install themselves is fully reusable without our code — that's the retainer
hook the operator wants, and it costs us nothing licensing-wise (§6). For it to degrade gracefully,
the profile file itself must be shareable (it's just YAML naming public template IDs/NSE scripts) and
the adapter/mapping code that turns raw tool output into schema-conformant findings should be the
one piece we don't hand over — a client re-running the profile gets nuclei/nmap/testssl's native
output, not our findings schema, unless they're a retained client with access to the mapping layer.

**3. Where the secret sauce sits.** The operator's working answer — boundary enforcement,
verification discipline, evidence format, target-specific checks from prior engagements — holds up,
with one addition: **the composition and pinning decision itself is sauce.** Which template tags to
include, which to deliberately exclude (broad CVE sweeps, noisy active-scan rules), and when to bump
a pin are judgment calls built from engagement experience; the profile YAML is shareable, but knowing
*which* profile to run against *which* stack, and how to keep it quiet enough that verification stays
cheap (§5), is exactly the kind of operational knowledge that doesn't commoditize just because the
ingredients are open source. The four items the operator named are necessary but not sufficient —
add profile curation itself as a fifth.

**4. Determinism under composition.** See §2 above — pin every component's version, not just
nuclei's, and record the whole set as one profile version per finding. Composition makes this
*harder* mechanically (more moving pins) but not conceptually different: it's still "record the
method version, treat a change as a deliberate release."

## What to keep hand-rolled

- **Object storage listing detection** (`_bucket_listing`) — no tool covers the vendor-agnostic
  shape-based heuristic; this is genuinely novel and cheap to maintain.
- **Source map detection** — trivial, already correct, wrapping buys nothing.
- **The finding-record shaping and evidence-writing** (`make_finding`, `write_evidence`) — this is
  the schema adapter itself; every tool's raw output still funnels through this, wrapped or not.
- **Negative-result recording** — no scanner in this list records "checked, absent" as a first-class
  output the way P10/P11 require; that discipline is ours regardless of what produces the positive
  check.
- **The three hardcoded admin-path checks** (`/admin`, `/ghost/api/admin/site/`,
  `/actuator/env`) can be *retired* in favor of nuclei's panel-exposure set, but the CORS
  double-check and header list should stay as a cheap always-on fallback even after NSE/nuclei are
  added — belt-and-braces costs one extra HTTP request per target and needs no pin to stay correct.

## Risks and open questions

- **[VERIFY]** Exact current nuclei CLI flags for template-directory pinning (`-td`,
  `-templates-directory`, or similar) — confirm against whatever version gets installed before
  wiring the wrapper; ProjectDiscovery has a history of flag churn across major versions.
- **[VERIFY]** testssl.sh JSON schema stability — no formal schema found; field names may have
  shifted across the 3.x series. Pin the binary version and snapshot a sample output before trusting
  the mapping.
- **[VERIFY]** nmap's license (NPSL) implications if RedGold ever bundles nmap rather than invoking
  an already-installed copy — not a blocker for CLI invocation, but flag before any packaging
  decision.
- **Open question**: whether the 80%-false-positive figure for unscoped nuclei (found anecdotally,
  not in a disclosed methodology) is representative of a properly-scoped, tag-filtered run — the
  profile-composition model in this doc is a bet that scoping the template set down fixes most of
  it, but that bet is untested against a real target set. Worth a small pilot (run the proposed
  `web-baseline-v1` profile against 3–5 already-engaged targets and count `rg-verify` overturns)
  before committing it to every engagement.
- **Open question**: whether nikto belongs anywhere in the composed profile at all. Nothing in this
  research found a check nikto performs that nuclei's exposures/misconfiguration templates or our
  own hand-rolled checks don't already cover better, and its false-positive reputation is worse than
  nuclei's. Current recommendation: leave it out.
- **Not assessed**: trivy is a container/SBOM/IaC scanner, not a live-HTTP scanner — it does not fit
  this baseline's remit at all (no live target it scans). It's relevant only if RedGold later takes
  on engagements with authorized registry/repo access, which is a different authorization model
  entirely.
