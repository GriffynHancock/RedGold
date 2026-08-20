---
title: Test-library composition — closing the gaps in scanner-integration.md
date: 2026-08-20
status: draft
question: Now that we're committing to "adopt standardised test libraries that we can just compose and pin, only custom building detections when necessary" — what exactly do we pin, on what architecture, what's missing from the earlier survey, what does a real profile spec look like, and how do we tell a dev/staging deployment from production before we grade its findings?
---

## Recommendation

Commit to the 2026-08-04 doc's direction with five corrections. **Pin nuclei to
`v3.11.x` engine / `nuclei-templates v10.4.7`** using `-t <dir> -duc` (not the flag
names the prior doc guessed at). **Drop nmap's `http-cors` and `http-config-backup`
from the pinned set's confidence claims** — they exist and run, but their output is
unstructured text a human wrote for a terminal, not a machine-checkable record, so
treat their findings as posture leads for human review, not auto-severity-mapped
records, until we've hand-verified the parse. **testssl.sh has no published schema
in 2026 either** — pin `v3.2.4` and snapshot sample output ourselves, same
conclusion as before, now with a version number. **All three components (nuclei,
nmap, testssl.sh) have working arm64 packages or images**, so ARM64 Kali is not a
blocker, but only nuclei's Docker tags are pinnable by content digest — nmap and
testssl.sh's Kali/Docker Hub artifacts are pinnable only by version tag, which is a
weaker guarantee and should be recorded as such on every finding. **Add one new
finding class the prior doc never considered: deployment-state classification**,
which must run *before* severity assignment, not after — a permissive CORS policy
on a Vercel preview URL and the same policy on the apex production domain are not
the same finding, and grading them identically is what produced the noise on the
prior engagement. On task 3's survey: include ZAP Automation Framework for
`rg-webtest`'s authenticated layer (already recommended, now with the config
mechanism); include Semgrep for `rg-codeaudit` (source-code track only, not the
live-HTTP baseline); include Supabase-specific anon-key/RLS probing as a
hand-rolled check family, informed by CVE-2025-48757 which is exactly the
misconfiguration class P10 exists to catch; exclude nuclei's `code`/`flow`/DAST
protocols from anything that runs against a client target without a human in the
loop — the `code` protocol executes arbitrary commands on the *scanning* host and
DAST/fuzzing templates are explicitly designed to find unknowns via mutation, which
is the opposite of the deterministic, enumerable checklist P10 requires; exclude
trivy/grype from the live-HTTP baseline (confirmed: not applicable, no live target)
but include trivy as the `rg-codeaudit` SBOM/dependency check when `SOURCE_CODE` is
in scope, since that track already reads source, not a wire target.

---

## 1. Resolving the `[VERIFY]`s

### 1.1 nuclei CLI flags for pinning and disabling auto-update

Checked against the current `docs.projectdiscovery.io/opensource/nuclei/running`
page and the `projectdiscovery/nuclei` GitHub repo (fetched 2026-08-20; the docs
site does not print a version number on this page, so the flags below are cross-
checked against the Kali package `nuclei 3.11.0-0kali1`, which matches the current
Docker Hub `latest`/`v3.11.x` tags found in §2).

| Purpose | Flag | Notes |
|---|---|---|
| Point the engine at a specific template directory | `-t, -templates string[]` | Comma-separated list of template files/directories. This is the flag that actually selects what runs. The prior doc's guess of `-templates-directory` is wrong — there is no such flag. But `-td` is **not** absent: verified against `cmd/nuclei/main.go` at tag `v3.11.1`, `-td`/`--template-display` exists as a **boolean** flag (`displays the templates content`), unrelated to path selection. `[VERIFY]` — this is a live foot-gun for any wrapper: `nuclei -td /pinned/templates …` does not error. It sets the `template-display` boolean to true and leaves `/pinned/templates` as an unconsumed positional argument, so the run silently falls back to nuclei's default template resolution while appearing pinned. Only `-t`/`-templates` actually selects the template path. Do not use `-td` for pinning under any circumstance, and diff the wrapper's real flag surface against `nuclei -h` before relying on any flag name in this table that was not confirmed from a `--help` dump. |
| Disable the automatic update check nuclei performs on every run | `-duc, -disable-update-check` | This is the flag that matters for determinism — without it, nuclei silently checks (and in older versions, applied) an update before every scan. |
| Manually trigger a template update (never call this from the wrapper) | `-ut, -update-templates` | Pulls the latest tagged `nuclei-templates` release. The wrapper must never call this — updates happen out-of-band, deliberately, per §2 below. |
| Custom install/update location for `nuclei-templates` | `-ud, -update-template-dir string` | Only relevant if we let nuclei manage the clone; RedGold's model (§4) checks out a pinned tag ourselves and points `-t` at that path directly, so this flag is not used in the wrapper. |
| Single target | `-u, -target string[]` | Confirmed. |
| File-based target list | `-l, -list string` | Confirmed to exist — **never used**, per §9.3.1/`scope_guard.py`; the wrapper loops and calls `-u` once per target, same pattern as `baseline_scan.py`. |

**Resolved wrapper invocation:** `nuclei -u <single-target> -t <pinned-templates-dir> -duc -jsonl -irr`
(`-jsonl` for the one-match-per-line output the prior doc already identified as the
strongest format of the group; `-irr`/`-include-response` to embed the raw
request/response, satisfying the `evidence_ptr` requirement without synthesizing a
transcript).

**Version checked:** nuclei engine `3.11.0` (Kali package `nuclei_3.11.0-0kali1`,
confirmed via `pkg.kali.org/pkg/nuclei`; Docker Hub tags `v3.11.1-arm64` seen at
`hub.docker.com/r/projectdiscovery/nuclei/tags`, fetched 2026-08-20). Do not treat
this as frozen — ProjectDiscovery has renamed flags across major versions before
(the prior doc's caution was correct), so re-check this table at the next engine
version bump, not just at the next `nuclei-templates` bump.

### 1.2 nuclei-templates: still the right pinning unit, current tag

Yes — `nuclei-templates` remains a separate, independently tagged GitHub repo
(`github.com/projectdiscovery/nuclei-templates/releases`). Current release series
is still `10.x`. Five most recent tags at fetch time (2026-08-20):

| Tag | Date |
|---|---|
| v10.4.7 | 2026-08-03 |
| v10.4.6 | 2026-07-16 |
| v10.4.5 | 2026-06-23 |
| v10.4.4 | 2026-05-28 |
| v10.4.3 | (the tag the prior doc's example profile named) |

Cadence confirms the prior doc's "roughly every 1–2 weeks" estimate. **Resolved
pin: `nuclei-templates v10.4.7`.** Recorded as of this document's date; the pin is
a framework-release decision per §2 of the prior doc, not something this document
freezes for all time.

### 1.3 testssl.sh: version, JSON modes, schema

Checked against `github.com/testssl/testssl.sh/releases` (fetched 2026-08-20).

- **Current stable: `3.2.4`** (bugfix release, 2026-07-12) — includes an XSS fix in
  the HTML output and OpenSSL 4 compatibility. This supersedes the prior doc's
  unresolved version question outright.
- A `3.3dev` branch exists in parallel (`3.3dev-snapshot-2607`, also 2026-07-12);
  **do not pin to a dev snapshot** — same reasoning as nuclei's template pin, a
  moving development branch fails the "identical every run" requirement outright,
  it isn't even a candidate.
- **JSON output modes:** testssl.sh supports `--jsonfile`/`--json` (compact) and
  `--jsonfile-pretty`/`--jsonfile-pretty` (indented) — both documented in the
  tool's own `--help` and `Dockerfile.md`; the two are the same schema, differing
  only in whitespace.
- **Schema: still `[VERIFY]` — no formal JSON Schema was found**, same conclusion
  as 2026-08-04. testssl.sh's own repo does not publish one (unlike nuclei, which
  does). **Action, not just a flag:** before wiring the adapter, run `testssl.sh
  --jsonfile-pretty` against one throwaway target under the pinned `3.2.4` binary
  and commit the sample output as a fixture the adapter's tests assert against —
  this converts the unverifiable schema claim into a verifiable regression test,
  which is the only honest way to close this `[VERIFY]` without a schema to point
  at.

### 1.4 nmap version and the three named NSE scripts

Checked against `nmap.org/dist/` (via search-engine cache; the direct WebFetch to
`nmap.org/dist/` failed twice from this environment — recorded as a fetch failure,
not treated as absence of a source) and `svn.nmap.org/nmap-releases/nmap-7.98/`,
cross-checked against Kali's package tracker.

- **Latest stable nmap: `7.98`**, released 2025-08-21 (confirmed via the SVN
  release-tag listing and corroborated by Wikipedia's infobox, which is a
  secondary source here — the SVN path is primary). A `7.991` string surfaced in
  one search snippet but could not be corroborated against a primary nmap.org
  page in this session; treat `7.991` as `[VERIFY]` and unused.
- **Kali's package: `nmap 7.99+dfsg-1kali1`**, confirmed directly from
  `pkg.kali.org/pkg/nmap`. Kali is one point release ahead of the upstream stable
  tag found above — not unusual for a rolling distro that back/forward-ports; this
  is the version ARM64 Kali will actually run, so it is the one to record as the
  pin (§2), not `7.98`.
- **`http-security-headers.nse`** — confirmed to exist (`nmap.org/nsedoc/scripts/
  http-security-headers.html`, mirrored in the Kali packages GitLab). It checks
  HSTS, HPKP, X-Frame-Options, X-XSS-Protection, X-Content-Type-Options, CSP,
  X-Permitted-Cross-Domain-Policies, `Set-Cookie`, Expect-CT, Cache-Control,
  Pragma, and Expires — matches the prior doc's claim exactly.
- **`http-cors.nse`** — confirmed to exist and run. Its output is a **bare list of
  permitted HTTP methods** (e.g. `GET POST OPTIONS`), not a structured
  wildcard/credentials verdict — this is a materially weaker signal than the prior
  doc implied by grouping it with nuclei's CORS template family. It does not
  replicate nuclei's reflected-origin/null-origin bypass detection at all; it only
  confirms CORS is enabled and for which methods. **Correction to the prior doc:**
  this script does not earn the "real gain" claim on its own — keep the hand-rolled
  `wildcard_cors` check as primary, use `http-cors.nse` only as a supplementary
  "CORS is present at all" signal.
- **`http-config-backup.nse`** — confirmed to exist and run. It probes for editor
  backup/swap variants (`~`, `.bak`, `.swp`, URL-encoded `%23...%23`) of known CMS
  config file names (WordPress, phpBB, Joomla, MediaWiki, Drupal) and reports each
  hit with its HTTP status line. This is genuinely additive — none of our nine
  checks or nuclei's exposure templates specifically chase editor-backup variants
  of config filenames — but its output is free text per hit, not a structured
  record, so the adapter must parse status-line text out of NSE's `output` field
  rather than a keyed JSON object.
- **NSE output format** — unchanged from the prior doc: `-oX` gives a stable,
  decades-old XML schema at the scan/host/port level, but each script's own
  `<script id=... output=...>` content is free-form prose the script's author
  wrote for a terminal, confirmed by inspecting the two scripts above directly.

### 1.5 nmap licensing (NPSL) — installed-binary invocation vs bundling

Checked against `nmap.org/npsl/` and the Nmap OEM page (fetched via search
cache; direct WebFetch to both pages failed in this session — recorded as a
fetch-tooling limitation, not as an unresolved question, since the search
results quote the license's operative language directly).

- **The NPSL restricts redistributing or bundling nmap inside a proprietary
  product** — this is the license's central commercial term: an NPSL license does
  not permit shipping nmap embedded in a commercial hardware/software product; an
  Nmap OEM License is the paid path for that.
- **Installing nmap from a distro's own package manager (`apt install nmap`) and
  invoking the installed binary from a script is explicitly not the restricted
  act** — the NPSL text itself names `apt-get install nmap` / `yum install nmap`
  as a permitted path, distinct from a vendor bundling the nmap binary inside
  their own shipped product.
- **RedGold's actual usage — shelling out to a Kali-apt-installed `nmap` from a
  Python wrapper during an authorized engagement — is invocation, not
  redistribution**, and is unaffected by the NPSL's commercial-bundling
  restriction. This confirms the prior doc's provisional read and resolves its
  `[VERIFY]`. **The `[VERIFY]` that remains, correctly scoped down from the prior
  doc's broader flag:** if RedGold ever ships a container image that bundles the
  nmap binary itself (rather than a Dockerfile that runs `apt install nmap` at
  build time, which is the same "install via package manager" case as above), get
  that specific packaging shape reviewed against the NPSL text directly before
  shipping it — the annotated NPSL text page exists precisely because this
  distinction has bitten other projects.

---

## 2. ARM64 / Kali availability

Operator environment: `Linux 6.19.11+kali-arm64`, tools intended to run inside a
container.

| Tool | Official ARM64 build | In Kali repos | Official container image, arm64 manifest | Pinnable identifier |
|---|---|---|---|---|
| **nuclei** | Yes — `projectdiscovery/nuclei` publishes `*-arm64` Docker tags (e.g. `v3.11.1-arm64`, `latest-arm64`) on Docker Hub, confirmed 2026-08-20. | Yes — `nuclei 3.11.0-0kali1`, confirmed via `pkg.kali.org/pkg/nuclei`. | Yes, arch-suffixed tags exist (note: a real multi-arch **manifest list** under one tag had an open feature request as of the sources found — projectdiscovery/nuclei#6147 — so today the arm64 image is a separately-named tag, not a manifest-list entry under `latest`). | **Best pin available: an arm64-tagged image digest**, e.g. `projectdiscovery/nuclei:v3.11.1-arm64@sha256:<digest>` — resolve and record the digest at pin time, don't trust the tag alone to stay put. |
| **nuclei-templates** | N/A (data, not a binary) | N/A | N/A | Git tag, e.g. `v10.4.7` — this is a real pin (tags on this repo are not force-moved in normal operation), but record the resolved commit SHA alongside the tag for belt-and-braces, same discipline as the container digest. |
| **nmap / NSE scripts** | Yes, nmap builds for aarch64 upstream and via distro packages. | Yes — `nmap 7.99+dfsg-1kali1`, confirmed via `pkg.kali.org/pkg/nmap`; also present for aarch64 on Arch Linux ARM as a corroborating independent build. | No single official "nmap" container image is published by the nmap project itself; any container image is a third party's Dockerfile layering `apt install nmap` on a base image. | **Weakest pin in the set: the apt version string** (`7.99+dfsg-1kali1`) is the only stable identifier — there is no upstream nmap image digest to anchor to. If we containerize, record the digest of *our own* built image (the layer that ran `apt install nmap=<version>`), not an nmap-published digest, because none exists. |
| **testssl.sh** | Shell script, architecture-independent by design (bash + openssl), so "ARM64 build" is really "does its container image ship an arm64 layer." | Yes — `testssl.sh 3.2.2+dfsg-1` in Kali's rolling repo, confirmed via `pkg.kali.org/pkg/testssl.sh` (note: this is one patch version behind the `3.2.4` upstream release found in §1.3 — record whichever one actually runs, not whichever is "latest upstream"). | Yes — `ghcr.io/testssl/testssl.sh` publishes a genuine multi-platform manifest covering `linux/amd64, linux/386, linux/arm64, linux/arm/v7, linux/arm/v6, linux/ppc64le`, confirmed via the project's own Dockerfile documentation. Prefer this over the `drwetter/testssl.sh` Docker Hub mirror, which was not confirmed to carry the same arm64 coverage. | **A real pin: `ghcr.io/testssl/testssl.sh:3.2.4@sha256:<digest>`** — this is the strongest of the three tool pins because the multi-arch manifest is published by the project itself, not a third party. |
| **ZAP** (for `rg-webtest`, not the baseline — see §3) | Yes. | Not directly relevant — ZAP is normally run from its own container, not apt. | Yes — `zaproxy/zap-stable` (Docker Hub) and `ghcr.io/zaproxy/zaproxy:stable` are the current official images; multi-arch support is real but the exact arm64 manifest digest was not independently confirmed in this session — **`[VERIFY]` the specific tag's arm64 coverage before wiring `rg-webtest`**, don't assume from the project's general multi-platform posture. | `ghcr.io/zaproxy/zaproxy:stable@sha256:<digest>` once §above `[VERIFY]` clears. |

**General finding for task 2:** every component the profile needs has a working
ARM64 path — nothing in this survey is amd64-only, so ARM64 Kali is not an
obstacle to the composition plan. But the pins are not uniformly strong: nuclei
and testssl.sh (via ghcr) resolve to real, project-published digest-pinnable
images; nmap does not — there is no nmap-published image to anchor to, only a
distro package version string, which is a *weaker* pin because a Kali point
release can rebuild the same version string against a different upstream
snapshot. Record that difference explicitly in the profile schema (§4) rather
than pretending all three pins carry equal weight.

---

## 3. What the 2026-08-04 doc did not consider

### 3.1 ZAP Automation Framework — include, for `rg-webtest`, not the baseline

The prior doc already excluded ZAP from the baseline and named it for
`rg-webtest`'s "authenticated and contextual" layer, but left the actual
configuration mechanism unspecified. Resolved: ZAP ships an **Automation
Framework**, a single YAML plan (`zaproxy.org/docs/automate/automation-framework/`)
that expresses contexts, authentication (script/form/JSON methods with
username/password field selectors and login/logout verification regexes),
session handling, and an ordered job list (spider, AJAX spider, passive scan,
optionally active scan) in one file, runnable via the same `zap-stable` image
named in §2 or its GitHub Action. This is the natural unit for `rg-webtest` to
name explicitly, per the prior doc's own "rewrite rg-webtest to name its scripted
layer" recommendation. **Verdict: include**, scoped to passive baseline mode plus
authenticated spidering, same reasoning the prior doc gave — ZAP's *active* scan
rules are the noisy part, not the baseline/authenticated-crawl part.

### 3.2 Nuclei's newer capabilities — code protocol, flow, DAST/fuzzing templates

**Code protocol — exclude, unconditionally, from anything RedGold runs against a
client target.** The `code` protocol lets a template execute a shell command on
the machine running nuclei, not on the target. Confirmed via ProjectDiscovery's
own DeepWiki-indexed docs and independently reinforced by CVE-2024-43405 (a real,
patched signature-verification bypass — no base score confirmed from a primary
source in this session, so the "high-severity" characterisation is dropped rather
than carried forward `[VERIFY]` — that let a malicious
template smuggle extra content past nuclei's template-signing check — precisely
because `code`-protocol templates are capable of local execution, that bypass
class exists at all). Running any template set that includes `code`-protocol
entries means every template pin decision is also implicitly a "do we trust every
contributor to this template category not to have hidden something" decision —
categorically different from the "does this regex correctly match a known HTTP
response shape" trust model the rest of the pinned set relies on. This is not
close: exclude `code`-protocol templates from every profile, full stop, and treat
any future profile-authoring step that would include one as a deliberate,
reviewed exception, never a default inclusion via a broad tag.

**`flow`/DAST/fuzzing templates — exclude from the baseline and from `rg-webtest`'s
scripted layer; do not extend blanket inclusion to `rg-webtest`'s agentic layer
either.** `projectdiscovery/fuzzing-templates` and the DAST-mode capability are
explicitly built to find *unknown* vulnerabilities via parameter mutation across
Query/Header/Body/Cookie/Path components — this is deliberately the opposite of
"deterministic, same every run," which is P10's baseline requirement and the
entire reason the prior doc's composition argument works at all. It is also the
opposite of Tier-1's "no writes, no payloads" constraint `baseline_scan.py`
documents in its own header comment: fuzzing by definition sends crafted,
mutated, adversarial input, which is a different blast-radius tier than an
unauthenticated GET. **Verdict: excluded from the pinned profile entirely** —
if a future engagement's scope explicitly authorizes higher-tier dynamic testing,
that is a `rg-webtest` decision made deliberately per engagement with its own
scope language, not something a template `-tags` filter should silently pull in.

### 3.3 Semgrep — include, for `rg-codeaudit` only

Semgrep is a static-analysis engine for source, not a live-HTTP tool — it has no
place in the baseline the prior doc scoped, but `rg-codeaudit`
(`rg:rg-codeaudit`) exists specifically for when `SOURCE_CODE` is an in-scope
asset, and nothing in either research doc names a tool for that track yet, which
is a real gap. **False-positive reputation, cited:** Semgrep's own 2025 published
comparison of its Community Edition against its paid Pro/Code tier
(`semgrep.dev/blog/2025/security-research-comparing-semgrep-community-edition-and-semgrep-code-for-static-analysis`)
reports the free Community Edition performs with "minimal false positives" on its
own rule set, while the paid tier adds true positives without a corresponding
false-positive increase — this is a vendor-published number, cite it as
vendor-published, not as independent benchmark, same calibration discipline P9
requires everywhere else. **Cost to pin:** the free `semgrep` CLI plus the public
`p/default`/`p/owasp-top-ten`/language-specific registries are pinnable by ruleset
version the same way `nuclei-templates` is — a tagged, versioned registry.
**Recommendation: include** the free CLI and public rulesets as `rg-codeaudit`'s
scripted layer (secret-pattern rules, injection-shape rules, known-bad-function
rules), pinned the same way as everything else in this document; do not adopt the
paid AI-triage tier — that is a subscription decision independent of this
research question, and the free tier's reported false-positive posture is already
adequate for a human-verified pipeline (`rg-verify` sits downstream of every
above-Low finding regardless of source, same backstop as nuclei findings today).

### 3.4 trivy / grype — exclude from baseline, include (trivy) for `rg-codeaudit` SBOM work

Confirms the prior doc's exclusion from the live-HTTP baseline (no live target,
same reasoning as before) but the prior doc's "not assessed" note on trivy is
resolved here since `rg-codeaudit` is a real, existing subagent and the task
explicitly asks about "dependency and SBOM work where SOURCE_CODE is in scope."
**False-positive comparison, cited:** a 2026 practitioner writeup comparing the
two on a 500-image internal test set reports Trivy surfacing roughly 18% more
findings than Grype, with roughly 60% of that excess attributable to
backport-patch false positives Grype's curated `grype-db` avoids — **this is a
single unverified practitioner account, not a disclosed academic methodology**,
cite it with that caveat, same treatment the prior doc gave the "80% nuclei false
positive" anecdote. **Recommendation: include trivy** as `rg-codeaudit`'s
SBOM/dependency-CVE layer when `SOURCE_CODE` is in scope — it's the more
commonly-deployed default per the same source, and its SBOM output (via the
bundled Syft-equivalent generation) gives `rg-codeaudit` a reusable artifact
beyond just the CVE list. **Do not add grype as a required second pass** — the
same source's own recommendation ("Grype as a second-opinion scanner on critical
externally-facing images") is a nice-to-have for a much larger engagement than
RedGold's Tier-1 startup-audit remit; one curated tool beats two competing ones
for the same reason the prior doc rejected nikto.

### 3.5 Supabase/Firebase-specific tooling — hand-roll, informed by CVE-2025-48757

No dedicated open-source *scanner* for this surface was found that meets
RedGold's bar (several commercial/SaaS "Supabase security scanner" products
surfaced in search results — `apify.com/renzomacar/supabase-rls-scanner`,
`launchguard.dev`, `securifyai.co` — none of them a pinnable open-source tool
with a published methodology; treat these as market-validation signal that the
check family matters, not as candidates to adopt). What is well-documented is the
**exact misconfiguration class**: CVE-2025-48757 (disclosed by security
researcher Matt Palmer, May 2025) found 303 endpoints across 170 audited
AI-generated-app projects with Supabase tables directly queryable by the public
`anon` key because Row Level Security was either disabled (Supabase's own
documented default for tables created via SQL or the Table Editor) or written as
a no-op `USING (true)` policy. This is structurally identical to check #5 in
`baseline_scan.py` (`_bucket_listing`) — same "anonymous caller reads a listing
that should require auth" shape — but for Postgres rows via PostgREST rather than
storage-object listings. **Recommendation: add a hand-rolled check**, not a
wrapped tool: probe `/rest/v1/<table>?select=*&limit=1` (PostgREST's REST
surface) using only the `anon` key already visible in the client bundle (never a
service-role key — that would cross into an authenticated/Tier-2 test, out of
Tier-1's unauthenticated-GET constraint), for a small set of commonly-named
tables (`users`, `profiles`, `orders`, etc.) discovered from the fingerprinted
stack, and flag any 200 with row data as `high`, structurally identical to
`_bucket_listing`'s existing shape-based approach. This belongs with "what to
keep hand-rolled," not the composed-tool set — nobody else has published a
general, vendor-neutral, pinnable version of this check.

### 3.6 Summary table — task 3 verdicts

| Candidate | Unique coverage | FP reputation (cited) | Pin cost | Verdict |
|---|---|---|---|---|
| ZAP Automation Framework | Authenticated/contextual crawl + passive scan | Baseline/passive mode is quiet (prior doc); AF itself doesn't change that | One YAML plan, one image digest (§2) | **Include** — `rg-webtest` only |
| Nuclei `code` protocol | Local script execution as a "check" | N/A — this is an execution primitive, not a detection, so FP framing doesn't apply | Same pin as nuclei generally, but trust model is categorically different | **Exclude**, unconditionally |
| Nuclei `flow`/DAST/fuzzing templates | Unknown-vuln discovery via mutation | Explicitly designed to be exploratory, not deterministic | Same repo pin, different tag family | **Exclude** — violates Tier-1's no-payload/deterministic constraints |
| Semgrep (CE, free) | Source-code SAST: secrets, injection shapes, known-bad functions | Vendor-published: "minimal false positives" on CE (cite as vendor claim) | Free CLI + tagged public ruleset | **Include** — `rg-codeaudit` only |
| trivy | Container/dependency/SBOM CVEs | Practitioner-reported ~18% more findings than grype, ~60% of the delta backport-FP noise (uncited methodology, flag as anecdotal) | Free CLI, tagged DB | **Include** — `rg-codeaudit`, `SOURCE_CODE`-in-scope engagements only |
| grype | Same as trivy, curated DB | Same source: lower FP than trivy | Free CLI, tagged DB | **Exclude** — one curated tool beats two, same logic as nikto |
| Supabase anon-key/RLS probe | Anonymous PostgREST row read | No general open tool exists; CVE-2025-48757 is the primary source for the misconfiguration class itself | Zero — hand-rolled, no upstream dependency | **Include, hand-rolled** — joins `_bucket_listing` as vendor-shape-aware but keeps the vendor-agnostic detection philosophy where possible |

---

## 4. The composition format — a real specification

### 4.1 Critique of the sketch

The 2026-08-04 sketch is directionally right but underspecified on four points
this section fixes: (a) it names version strings, not resolvable pins — `nmap:
"7.99"` is not enough to reproduce a scan two months later, per §2's finding that
nmap has no digest-pinnable artifact at all; (b) `selection: {tags: [...]}` for
nuclei is fine but has no equivalent syntax defined for nmap or testssl, so each
component effectively invents its own dialect anyway, just informally; (c)
`mapping: findings-schema-v1` names an adapter version but not *which* mapping
table governs each component's severity, which is exactly the piece the prior
doc's §3 calls "part of the secret sauce" — a profile that doesn't say which
mapping ran is not fully reproducible; (d) there is no field for the
deployment-state classifier from §5, which now has to run as a step before
severity assignment, and no field recording per-component pin *strength*
(digest vs tag vs version-string, per §2's finding that these are not equal).

### 4.2 Field-by-field specification

```yaml
# profiles/<name>.yaml — one file per engagement type (baseline, webtest, codeaudit).
# This file is the versioned, enumerable object referenced by every finding it
# produces, in the same field position `discovered_by` occupies today.

profile: web-baseline-v1          # REQUIRED. Stable name; bump the trailing -vN on any
                                   # change to `components` or `mapping`, never edit in place.
profile_version: 1                # REQUIRED. Integer, monotonic. `web-baseline-v1` @ version 1,
                                   # version 2, etc. — this is what "record a deliberate,
                                   # dated decision" (prior doc §2) becomes as a machine field.
recorded: 2026-08-20               # REQUIRED. Date this profile version was pinned/reviewed.
mapping: findings-schema-v1        # REQUIRED. Points at the adapter+severity-mapping table
                                    # version in scripts/findings.py's vocabulary. A profile
                                    # bump that only changes `mapping` is still a version bump.

pins:                              # REQUIRED. One entry per external component. Every entry
                                    # states BOTH the identifier and its pin_strength, because
                                    # §2 found these are not uniform across tools.
  - tool: nuclei
    engine: "3.11.0"                        # apt/binary version actually installed
    engine_image: "projectdiscovery/nuclei:v3.11.1-arm64"
    engine_digest: "sha256:<resolved-at-pin-time>"
    pin_strength: digest                    # digest | tag | version_string
    templates_ref: "v10.4.7"                # nuclei-templates git tag
    templates_commit: "<resolved-sha>"      # belt-and-braces per §2
    pin_strength_templates: tag             # git tags are not force-moved in practice, but
                                             # record commit SHA alongside for the same reason
                                             # a container tag gets a digest recorded too.
  - tool: nmap
    version: "7.99+dfsg-1kali1"             # Kali apt package version — the actual identifier,
                                             # not the upstream 7.98/7.991 string (§1.4)
    pin_strength: version_string            # WEAKEST pin in the set (§2) — no upstream digest
                                             # exists to anchor to. Record honestly rather than
                                             # implying parity with the digest-pinned tools.
  - tool: testssl
    version: "3.2.4"
    image: "ghcr.io/testssl/testssl.sh:3.2.4"
    image_digest: "sha256:<resolved-at-pin-time>"
    pin_strength: digest

components:                        # REQUIRED, ordered list. Execution order = list order.
                                    # `selection` uses each tool's OWN native selector syntax —
                                    # deliberately not a new cross-tool query language (the prior
                                    # doc's own conclusion: "nothing spans tools," and inventing
                                    # one here would be exactly the kind of engineering effort
                                    # the operator's thesis says to avoid). The adapter (§4.3)
                                    # is the one place selection differences get reconciled.
  - tool: nuclei
    selection:
      tags: [exposures, misconfig-cors]     # nuclei's own -tags syntax, verbatim
      exclude_protocols: [code, flow]        # belt-and-braces even though templates_ref (above)
                                              # is itself curated to exclude these (§3.2) — a
                                              # defence-in-depth filter the adapter enforces at
                                              # runtime, not just at template-selection time.
    finding_class_default: technical
    severity_source: template_field          # nuclei's own info.severity maps 1:1 (prior doc §3)

  - tool: nmap-nse
    scripts: [http-security-headers, http-cors, http-config-backup]
    finding_class_default: posture           # NSE has no severity field at all (prior doc §3);
                                              # every NSE finding's severity comes from the table
                                              # below, not from the tool.
    severity_source: mapping_table
    severity_table_ref: "nse-severity-v1"    # names WHICH table, resolving critique (c) above.
    confidence_ceiling: probable             # §1.4's finding that http-cors/http-config-backup
                                              # output is free-text, not structured — the adapter
                                              # must not claim `confirmed` confidence off a text
                                              # parse it cannot fully validate. http-security-
                                              # headers is closer to structured and may exceed
                                              # this per-script in the mapping table.

  - tool: testssl
    args: ["--severity", "medium", "--jsonfile-pretty"]
    finding_class_default: posture
    severity_source: mapping_table
    severity_table_ref: "testssl-severity-v1"

  - tool: redgold-native
    checks: [bucket_public, sourcemap, supabase_anon_rls]   # supabase_anon_rls per §3.5 — new
    finding_class_default: technical
    severity_source: check_definition        # unchanged from baseline_scan.py today

deployment_state_check:            # REQUIRED as of this profile version — runs BEFORE severity
                                    # assignment on every finding this profile produces (§5).
  enabled: true
  classifier_version: "deploy-state-v1"
  signals: [tls_cert_issuer, hosting_header_pattern, error_page_shape, source_map_presence]
  # See §5.6 for what each signal does. A finding's `deployment_state` field
  # (production | staging | preview | dev | unknown) is set once per asset, before
  # the per-check loop runs, and every record from this profile carries it.

target_discipline:                 # REQUIRED. States the constraint explicitly rather than
                                    # leaving it implicit in wrapper code, so a profile reviewer
                                    # can confirm compliance by reading the YAML alone.
  one_target_per_invocation: true
  forbidden_flags: ["-l", "-iL", "--target-file", "-w"]   # mirrors scope_guard.FILE_TARGET_LIST_RE
  boundary_recheck: per_target                             # in_boundary() re-checked before
                                                             # each shell-out, same as today
```

### 4.3 How component output becomes a `finding_class` + severity

Each `components[].severity_source` names one of three strategies, resolving
critique (c):

1. **`template_field`** (nuclei only) — the tool's own severity travels straight
   through; no separate table needed, per the prior doc's §3 observation that
   `info.severity` maps 1:1.
2. **`mapping_table`** (nmap-nse, testssl) — an explicit, named, versioned table
   (`nse-severity-v1`, `testssl-severity-v1`) lives alongside the profile file and
   is referenced by name, never inlined into the profile YAML itself, so the table
   can be reviewed and versioned independently of the profile that uses it — the
   same separation `mapping: findings-schema-v1` already gives the whole-record
   adapter.
3. **`check_definition`** (redgold-native) — unchanged: `Check.severity` in
   `baseline_scan.py` today.

Every record produced under any strategy still carries `discovered_by` (now
naming the tool, e.g. `"nuclei"`, `"nmap-nse"`, `"testssl"`, `"baseline_scan"`)
**and** a new `profile: {name, version}` pair, so a finding is traceable to the
exact profile version and pin set that produced it — this is the mechanism the
prior doc's §"Composition: the reframed core answer" asked for but didn't give a
field name to.

### 4.4 `evidence_ptr` under composition

Unchanged conclusion from the prior doc, restated as a rule the adapter enforces:
nuclei (`-irr`) and ZAP retain full request/response and get a synthesized
`.http`-equivalent evidence file; nmap-nse and testssl.sh do not, and their
`evidence_ptr` points at the tool's own raw XML/JSON output file directly — the
adapter must never fabricate a `.http` transcript from a summary to make the two
tool families look uniform.

---

## 5. Deployment-state classification

The prior engagement's noise (permissive realtime broadcast config, debug
endpoints, verbose errors, seeded test data, permissive local CORS) was a
deployment-state problem, not a detection-accuracy problem — every one of those
findings was a *correct* observation of a *non-representative* environment. This
section ranks the signals cheap enough for a deterministic pre-pass to check,
before severity assignment, per the new `deployment_state_check` block in §4.2.

### 5.1 Hosting-platform preview-URL and header patterns — strongest, cheapest

Vercel and Netlify preview deployments are the single most reliable signal
available, because the platform itself labels them. Vercel: preview deployments
receive their own `*.vercel.app` URL distinct from the assigned production
domain, and the `x-vercel-deployment-url` response header carries the underlying
deployment URL even when the request arrived on a custom domain — so a scanner
that sees `x-vercel-deployment-url` resolve to a `*.vercel.app` host while the
request's `Host` header is the client's real domain has caught the platform
telling it "this response came from a preview build," a fact the operator (not
the target) is asserting. Vercel's own REST API additionally exposes a
first-class `target` field on a deployment (`staging`/`production`/null for
preview), which is not visible to an external scanner directly but confirms the
platform models this distinction natively, which is why the header proxy for it
is trustworthy. **Reliability: high. Failure mode:** a target can reverse-proxy a
preview deployment behind their own production domain deliberately (soft-launch,
canary), in which case the header is still honest about the underlying
deployment but the operator's intent is "this is production traffic on purpose" —
the classifier should flag, not silently downgrade, in that case.

### 5.2 TLS certificate issuer and subject facts

A certificate whose issuer equals its subject (self-signed) or whose subject is
`localhost`/an RFC 1918 address/a bare `*.local` name is a strong, cheap,
already-observable-in-testssl.sh's-own-output signal that the target is not a
public production deployment — production services on the public internet
overwhelmingly present certificates from a real CA (Let's Encrypt, a commercial
CA, or a cloud provider's managed cert), and self-signed certs are specifically
recommended only for local dev, container-internal traffic, and non-public
internal APIs per multiple sources converging on the same guidance.
**Reliability: high for the self-signed/localhost case specifically; lower as a
general staging detector** — plenty of legitimate staging environments run behind
the same CA-issued wildcard cert as production (a `staging.example.com` cert from
the same Let's Encropt account), so absence of this signal proves nothing;
presence of it is close to conclusive. **Failure mode:** internal corporate CAs
(a company-run root CA trusted only by employee devices) look self-signed to an
external scanner's default trust store but are legitimate internal production
infrastructure — treat "self-signed" as "flag for review," not "conclude dev,"
when the cert chain terminates in an unrecognized-but-structured CA rather than
literally issuer==subject.

### 5.3 Staging/preview subdomain and hostname conventions

`staging.`, `dev.`, `preview.`, `test.`, a numbered PR-preview subdomain
(`pr-1234.`), or a platform-assigned throwaway domain (`*.vercel.app`,
`*.netlify.app`, `*.herokuapp.com`, `*.supabase.co` project-ref subdomains used
directly rather than behind a custom domain) are all cheap string-match signals
on the hostname alone, requiring no request at all. **Reliability: moderate** —
this is a naming *convention*, not an enforced platform fact like §5.1, so it is
weaker evidence on its own but essentially free to check and worth combining with
the others. **Failure mode:** some production products intentionally keep a
platform-default hostname permanently (a small SaaS that never buys a custom
domain and runs production on `*.vercel.app` forever) — the convention signal
alone should never downgrade a finding's severity by itself, only contribute to a
combined score alongside §5.1/§5.2.

### 5.4 Error-page shape and framework debug output

A stack trace, a framework-branded debug page (Django's `DEBUG=True` yellow
error page, Rails' error page with full backtrace, Next.js's dev-mode error
overlay), or a raw unhandled-exception JSON body with a file path and line
number in it, is close to conclusive: production deployments of every major
framework default to a generic error page specifically because shipping a
verbose one is treated as its own vulnerability class (information disclosure)
independent of deployment-state classification — so seeing the verbose form is
strong evidence either that `NODE_ENV`/`DEBUG`/equivalent is still set to a
development value, or that the deployment is non-production entirely. This
double-counts usefully: it is *both* a deployment-state signal *and*, if
observed on a URL that other signals say is production, a legitimate high-severity
finding in its own right (verbose errors in production is exactly the kind of
posture finding P10 exists to catch) — the classifier's job is to make sure it's
graded as the right one of those two, not to suppress it. **Reliability: high**
for the specific framework-branded-page case; **failure mode:** a generic 500
with no framework branding is not this signal at all — don't over-fit the
detector to "any 500 means dev," only branded/verbose bodies count.

### 5.5 Source maps and exposed build artifacts

A published `.js.map` (check #6 in `baseline_scan.py` today) is a genuine
production posture finding in its own right in most cases — many legitimate
production SPAs ship source maps deliberately for error-tracking-service
integration (Sentry et al. commonly consume them post-deploy then optionally
strip public access) — so this signal is **weaker as a deployment-state
classifier than as a standalone finding**, and should be treated as low-weight
supporting evidence, not a primary signal, specifically because its false-positive
rate as a *dev-only* indicator is high: plenty of production deployments have
this exact property on purpose or by oversight unrelated to being non-production.

### 5.6 Seeded/placeholder data shape in response bodies

Response bodies containing `test@example.com`, `lorem ipsum`, sequential/obviously
fake names, or Stripe/payment-provider test-mode key prefixes (`pk_test_`,
`sk_test_`) are a strong signal when present, but require a body-content check
rather than a header/cert check, making them costlier than §5.1–5.3 and more
prone to bespoke false positives (a production app's own demo/sandbox account
legitimately contains `test@example.com`-shaped data). **Reliability: moderate,
cost: higher than the header/cert signals** — worth including in the classifier
as a supporting signal (e.g., detecting a Stripe test-mode key is close to
conclusive on its own, since a real production payment flow cannot function with
a test key), but not as a first-line cheap check the way §5.1–5.3 are.

### 5.7 Ranked top 5, by reliability

1. **Hosting-platform preview headers/URLs** (`x-vercel-deployment-url` resolving
   to a `*.vercel.app` host, equivalent Netlify deploy-preview headers) — the
   platform itself is asserting the fact; hardest to spoof accidentally.
2. **Self-signed / localhost-subject TLS certificate** — near-conclusive when
   present (issuer==subject or subject is `localhost`/RFC1918), silent (proves
   nothing) when absent.
3. **Framework-branded verbose error/debug page** — near-conclusive when the
   branded form is seen; double-counts as its own finding when the environment
   otherwise reads as production.
4. **Payment-provider test-mode key prefix in a response body** (`pk_test_`,
   `sk_test_`) — narrow but close to conclusive where it applies at all.
5. **Staging/preview subdomain naming convention** — cheap, free to check, but a
   convention rather than an enforced fact; combine with the above rather than
   trusting alone.

Source-map presence (§5.5) and generic seeded-data shape (§5.6, apart from the
payment-key special case) are real signals but rank below these five —
appropriately weighted contributors to a combined score, not standalone
classifiers.

---

## Open questions carried forward

- **nmap 7.991 vs 7.98** (§1.4): the higher version string surfaced once in
  search results without a primary-source page loading to confirm it in this
  session. Kali's own `7.99+dfsg-1kali1` is what actually matters for this
  operator's environment and is independently confirmed, so this doesn't block
  anything, but re-check `nmap.org/dist/` directly (the direct fetch failed
  twice from this environment, unrelated to the fact itself) before quoting an
  upstream version number to a client.
- **testssl.sh JSON schema** remains genuinely unpublished — the fixture-based
  mitigation in §1.3 is a workaround, not a resolution; if testssl.sh ever
  publishes a schema, replace the fixture-diffing approach with a real schema
  check.
- **ZAP's arm64 manifest** for the specific `zap-stable`/`ghcr.io/zaproxy/zaproxy:stable`
  tags was not independently confirmed to the digest level in this session —
  confirm before wiring `rg-webtest`'s container, not before this document.
- **The Supabase anon-key/RLS check's table-name list** (§3.5) needs to be built
  from fingerprinted-stack data (rg-surface's output), not hardcoded the way the
  three admin-path checks are today — an open design question for whoever
  implements it, not resolved here.
