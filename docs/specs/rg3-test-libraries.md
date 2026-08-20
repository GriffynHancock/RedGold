---
title: RG-3 — composed test libraries, controlled fuzzing, and playbook dispatch
date: 2026-08-20
status: draft
question: How does RedGold compose and pin standardised test libraries instead of hand-rolling detections — including a fuzzer that is controlled rather than blocked and whose discoveries reach the asset register — without hand-annotating thousands of templates, and without the framework staying a Supabase tool?
---

# RG-3 — composed test libraries

Sub-project RG-3. Consumes `docs/specs/rg1-finding-integrity.md` (schema, scanner ceiling, validator
codes) and `docs/research/test-library-composition.md` (pinned composition, 2026-08-20), which in
turn corrects `docs/research/scanner-integration.md` (2026-08-04).

**RG-1 §5.6 explicitly did not settle nuclei's corpus and deferred it here. §5 of this document is
that answer.** RG-1's `low` ceiling on scanner output (decision D-2) is inherited unconditionally
and is never relaxed by anything below.

## Index

| § | Contains |
|---|---|
| 0 | What this settles, and where it disagrees with prior work |
| 1 | Pins: where they live, how they are recorded, how they are *verified* |
| 2 | The profile format — full specification and worked example |
| 3 | Output → `finding_class`, severity, and profile stamping |
| 4 | The scanner ceiling and the `grants` problem |
| 5 | Controlled fuzzing |
| 6 | Secret scanning: gitleaks + trufflehog |
| 7 | Generalising off Supabase — the backend-agnostic check families |
| 8 | Playbook dispatch, reopened |
| 9 | The false-positive budget, and how it becomes evidence |
| 10 | Build order and dependencies on RG-1 |
| 11 | What this does NOT do |
| 12 | Open decisions for the operator |

---

## 0. What this settles, and where it disagrees with prior work

### 0.1 The five decisions

1. **A profile is a pinned, versioned, reviewable object** whose pins are *heterogeneous by nature*
   and say so per component (§1, §2). Uniform-looking pins across tools with genuinely different
   anchoring strength are a lie the format must not be able to tell.
2. **Every scanner-sourced finding sits at `low`.** Not by policy bolted on afterwards, but because
   RG-1 §4.5 already caps anything without an independent `verified_by`, and because §4 below shows
   the alternative — per-template `grants` — is unbuildable. The escape is a *different producer*
   (`rg-verify` reading a response), never a bigger table.
3. **Fuzzing runs, bounded by its input set rather than by an in-band request counter**, and its
   discoveries are first-class artifacts written to a new `assets/surface.jsonl` (§5). The operator's
   point is the load-bearing one: a fuzzer that finds an undocumented endpoint has done asset
   discovery, and today that result is thrown away.
4. **Secret scanning runs both gitleaks and trufflehog, with trufflehog's live verification OFF by
   default** (§6). Verification is an unauthenticated network action against a *third party who is
   not the client*, and no signed scope covers Stripe.
5. **Playbook dispatch is built from the start, with `_generic/` as the primary implementation
   surface and the no-match path as the primary path** (§8). The deferral argument was not wrong
   about the risk; it was wrong about which artifact carries it.

### 0.2 Where this disagrees

| # | Prior position | Source | This document |
|---|---|---|---|
| D-a | `severity_source: template_field` — nuclei's `info.severity` maps 1:1 | `test-library-composition.md` §4.2 / `scanner-integration.md` §3 | **Rejected.** Under RG-1 severity is derived from `grants` + `precondition` + environment, none of which a template knows. At `nuclei-templates v10.4.7`, 1,830 templates self-declare `critical` and 2,928 `high` (`TEMPLATES-STATS.md` at that tag). Template severity is recorded as a non-computed claim and used only to *order the verification queue* (§4.4) |
| D-b | Wrapper invocation `nuclei … -irr` | `test-library-composition.md` §1.1 | **Corrected.** At `v3.11.1` the help dump reads `-irr, -include-rr -omit-raw … [DEPRECATED use -omit-raw] (default true)`. Request/response inclusion is already the default; the live flag is the *negative* `-or/-omit-raw`. Passing a deprecated flag to get a default is a pin that decays silently. Evidence capture uses `-sresp -srd <dir>` instead (§3.4) |
| D-c | DAST/fuzzing templates excluded entirely | `test-library-composition.md` §3.2 | **Overruled by the operator, and the overrule is right** — but only for the `dast/` family. The `code/` protocol exclusion stands unchanged and unconditionally (§5.1); those are two different arguments that the prior doc bundled into one verdict |
| D-d | `projectdiscovery/fuzzing-templates` is the fuzzing corpus | `test-library-composition.md` §3.2 | **Wrong pin unit.** That repo's newest tag is `v0.0.4`. The fuzzing corpus ships *inside* `nuclei-templates` at `dast/` — 251 `.yaml` files at tag `v10.4.7`, of which the corpus's own stats count 249 as templates. One pin covers both the deterministic and the fuzzing corpus (§5.2) |
| D-e | Dispatch deferred to v2; "solves a problem that does not exist at n=1" | `12-deliverables-and-build-order.md` §17.1 | **Reopened by the operator.** §8.4 concedes what the argument got right and names the two mitigations that make early dispatch safe |

### 0.3 The rule this document is written under

Hard rule 2. Every version string, flag spelling, count and licence below was read from a
version-tagged primary source in this session, or is marked `[VERIFY]`. The "roughly 80% of unscoped
nuclei output is noise" figure that circulates in the prior research **is not quoted here, is not
quotable to a client, and is not a design input** (§9). The only false-positive number RedGold may
ever state is one it measured itself, with its denominator, and that number does not exist yet.

---

## 1. Pins — where they live, how they bump, how they are verified

### 1.1 Pins are a framework-release fact, not an engagement fact

An engagement selects a *profile*; it never selects a version. If an engagement could bump a pin,
two engagements run a week apart would be incomparable and neither would be reproducible from the
report. So:

| Artifact | Path | Contents | Changed by |
|---|---|---|---|
| The pin lock | `profiles/pins.lock.yaml` | Every external component, its resolved identifier, its `pin_strength`, and the date it was resolved | A deliberate, reviewed commit on the framework repo. Never by an engagement, never by a script, never by a tool's own updater |
| The profile | `profiles/<name>.yaml` | Selection, mapping, budgets, ceilings. References `pins.lock.yaml` by `pins_ref` | Same |
| The bump record | `profiles/CHANGELOG.md` | One entry per bump: what moved, from what to what, why, and what re-ran | Same commit as the lock change |
| The resolved corpus | `profiles/<name>.resolved.json` | The concrete template-id list a selection expanded to at pin time, and its count | Generated by `scripts/resolve_profile.py`, committed |

`profiles/` does not exist in the repo today. Neither does `pins.lock.yaml`. This is a new directory.

**Automatic update is disabled everywhere, by flag and by network.** `nuclei` gets `-duc`; the
wrapper never calls `-ut/-update-templates`; trivy's and trufflehog's DB/detector refresh paths are
pinned or disabled per §6.3. A tool that can update itself mid-engagement has no pin, only a
comment.

### 1.2 Pin strength is not uniform, and the format must say so

Five strengths, ordered. `pins.lock.yaml` requires the field on every entry; there is no default.

| `pin_strength` | Means | Components that can achieve it |
|---|---|---|
| `image_digest` | A content-addressed manifest published by the project itself | nuclei (`projectdiscovery/nuclei:v3.11.1-arm64@sha256:…`), testssl.sh (`ghcr.io/testssl/testssl.sh:3.2.4@sha256:…`) |
| `file_digest` | A sha256 over a release artifact the project published and signed or checksummed | gitleaks `gitleaks_8.30.1_linux_arm64.tar.gz`, trufflehog `trufflehog_3.97.0_linux_arm64.tar.gz` — both present in the tagged releases, both accompanied by checksum files |
| `git_commit` | A tag *plus* the commit SHA it resolved to at pin time | `nuclei-templates v10.4.7` → `83234ce456da3e90dda86dfbc5e605e64a846df3` (resolved from the GitHub refs API, 2026-08-20) |
| `version_string` | A distro package version and nothing else | **nmap.** There is no nmap-published image or upstream digest to anchor to. `7.99+dfsg-1kali1` is the whole pin |
| `local_build_digest` | The digest of an image *we* built, whose Dockerfile ran `apt install <pkg>=<version>` | The only way to give nmap a content anchor, and it anchors *our* build, not nmap's |

**The honest consequence, which must appear on any finding sourced from a `version_string` component
and in the report's methodology section:** a Kali point release can rebuild the same version string
against a different upstream snapshot. `nmap 7.99+dfsg-1kali1` today and `nmap 7.99+dfsg-1kali1` in
six months are not provably the same bytes. Every other component in the set is provably the same
bytes. Recording both under one word — "pinned" — is the kind of flattening P9 forbids.

Every finding therefore carries `pin_strength` for the component that produced it (§3.5), and
`report.py` renders the weakest pin_strength in the profile in the methodology section rather than
the strongest.

### 1.3 A bump is an event with a record

A pin bump is the only thing that changes what a profile does, so it is the only thing that needs a
record. One `CHANGELOG.md` entry per bump, four required fields:

```
entry:       2026-09-03 — web-baseline-v1 profile_version 1 → 2
component:   nuclei-templates
from:        v10.4.7 @ 83234ce456da3e90dda86dfbc5e605e64a846df3
to:          v10.4.8 @ <sha>
why:         scheduled cadence bump; upstream added N templates under selected selectors
resolved:    template count 412 → 431; 3 template-ids retired per §9.3, listed
re-ran:      fixtures/ regenerated; tests/test_profile_resolution.py green
```

`profile_version` is a monotonic integer and bumps on **any** change to `pins_ref`, `components`,
`mapping`, or a budget. It never bumps on a comment. A profile is never edited in place at the same
version.

### 1.4 Reproducing an old scan from an old report

The report states, and this is the whole reproducibility claim:

> `profile: web-baseline-v1`, `profile_version: 4`, `pins_ref: pins.lock.yaml@<git-sha>`.

From those three facts a reader checks out the framework repo at `<git-sha>`, reads
`profiles/web-baseline-v1.yaml` at `profile_version: 4`, and re-resolves every component from
`pins.lock.yaml`. Four of the five components resolve to identical bytes. nmap does not, and §1.2
says so on the same page.

What this claim explicitly does **not** cover: the target. A re-run in six months sends the same
requests to a system that has changed. §5.6 states the fuzzing-specific version of this honestly;
the general form is that RedGold can make its *inputs* reproducible and can never make its *outputs*
reproducible.

### 1.5 Pins must be verified at runtime, not declared — the `-td` case

The foot-gun, restated because it is the reason this subsection exists. At `nuclei v3.11.1`, `-td`
is the boolean short form of `--template-display`. So:

```
nuclei -u https://target -td /opt/rg/templates/v10.4.7 -duc -jsonl
```

does **not** error. It sets a display boolean and leaves the path as an unconsumed argument, and
the run proceeds against nuclei's *default* template resolution — whatever is in the user's
`~/.local/nuclei-templates`, possibly auto-updated, possibly a different corpus entirely. The run
looks pinned in the command line, in the logs, and in the report. It is not.

**The general principle: a pin that is asserted by a flag string is not a pin. A pin is a property
of the process that actually ran, and it must be read back out of that process.**

`scripts/verify_pins.py` runs before the first request of every scan phase and refuses on any
failure. Five assertions, each of which would have caught the `-td` case:

| # | Assertion | How |
|---|---|---|
| V1 | **The flag surface is what we think it is.** Every flag the wrapper intends to pass appears in `nuclei -h` output with the expected arity | Parse `-h`, compare to the wrapper's declared flag table. A flag that has become boolean, been renamed, or been deprecated fails here. This is the `-td` catch, and it catches it *before* a scan rather than after a report |
| V2 | **The binary is the pinned one.** `nuclei -version` (and equivalents) matches `pins.lock.yaml`; where the component is an image, the running image's digest matches | — |
| V3 | **The template directory is the pinned one, by content.** Hash the resolved template tree and compare to `profiles/<name>.resolved.json`'s recorded tree hash. Not "the path we passed exists" — the *tree we ran against* | A directory hash over the selected files. Cheap, and it is the only assertion that survives a flag rename we did not anticipate |
| V4 | **The corpus that ran is the corpus we resolved.** Post-run, the set of distinct `template-id` values in the JSONL output is a subset of `resolved.json`'s id list. A template-id outside the list means the pin did not hold, whatever V1–V3 said | Post-condition, not pre-condition. This is the backstop for the failure mode where the pre-checks pass and the engine still resolves elsewhere |
| V5 | **Auto-update did not run.** No network call to an update endpoint appears in the run; `-duc` present; the template tree's mtimes and hash are unchanged after the run | The hash comparison from V3, re-run after |

V3 and V4 are the ones that matter. V1 is a nicety that happens to catch this specific bug; V3/V4
catch the class. **Ship V3 and V4 first.** A framework that only implements V1 has learned the
incident and not the lesson.

`PIN_UNVERIFIED` is a blocking violation at Gate 1 approval of any phase whose plan names a profile,
and at phase completion if V4 fails. It is not advisory: an unverified pin makes every determinism
statement in the report false, and a false determinism statement is worse than an absent one.

---

## 2. The profile format

### 2.1 Four constraints the format must satisfy

1. **No new query language.** Each tool already has a selector syntax its own maintainers document
   and test. Inventing a cross-tool selector means writing and maintaining a translator, which is
   exactly the engineering the "compose, don't build" thesis exists to avoid. **`selection` is
   per-component and is that component's native syntax, verbatim**, and the profile says which
   dialect each block is in. The price is that a profile reader must know four small dialects; the
   alternative price is a translator that silently mis-selects, which is the §1.5 failure again.
2. **Selection must resolve to a concrete list.** Native syntax is expressive, which means a
   one-line selector can silently grow by 400 templates at the next pin bump. So selection is
   *expanded at pin time* into `profiles/<name>.resolved.json` and the expansion is committed. The
   profile declares `max_templates`; resolution that exceeds it fails the build. This is the
   mechanism §9 depends on.
3. **Pins are referenced, not inlined.** `pins_ref` names `pins.lock.yaml`; the profile does not
   restate digests. One lock file, many profiles, no drift between them.
4. **Every mapping is named and versioned.** A profile that does not say *which* severity table
   governed a component is not reproducible even if every byte of every tool is.

### 2.2 Field-by-field

Top level. R = required, O = optional.

| Field | R/O | Type | Meaning and rules |
|---|---|---|---|
| `profile` | R | str | Stable name, e.g. `web-baseline-v1`. Trailing `-vN` is part of the *name* and changes only on a redesign, not on a pin bump |
| `profile_version` | R | int | Monotonic. Bumps on any change to `pins_ref`, `components`, `mapping`, `ceiling`, or any budget. Never edited in place |
| `recorded` | R | date | Date this version was pinned and reviewed |
| `pins_ref` | R | str | `pins.lock.yaml` (path relative to `profiles/`). Resolved against the framework repo commit named in the report |
| `mapping` | R | str | Adapter + record-mapping version in `scripts/findings.py`'s vocabulary, e.g. `findings-schema-v1` |
| `ceiling` | R | str | The severity ceiling every finding this profile produces is capped at. **Must be `low`** for any profile containing a non-`redgold-native` component — RG-1 D-2, inherited unconditionally. Present as an explicit field so that a future relaxation is a visible diff and not an emergent behaviour |
| `tested_at_tier` | R | int | The scope tier this profile requires. Stamped onto every finding. A profile may not run under a scope whose ceiling is lower |
| `target_discipline` | R | object | §2.6 |
| `components` | R | list | Ordered. Execution order = list order. §2.3 |
| `deployment_state_check` | R | object | Runs before severity assignment. Inherits `test-library-composition.md` §5's classifier, narrowed by RG-1 §2.4 — the four blocking signals only, `x-vercel-deployment-url` deleted |
| `budgets` | R | object | §2.5. Required even when every value is `null`, so "no budget" is a written decision |
| `fuzzing` | O | object | Absent means the profile does not fuzz. §5.3 |
| `max_templates` | R when any component resolves a corpus | int | Resolution failing this is a build failure, not a warning |
| `notes` | O | str | Free text. Nothing computes on it |

### 2.3 `components[]`

| Field | R/O | Meaning |
|---|---|---|
| `tool` | R | One of a closed set: `nuclei`, `nmap-nse`, `testssl`, `zap-af`, `semgrep`, `trivy`, `gitleaks`, `trufflehog`, `redgold-native`. Adding a value is a framework change with a new adapter |
| `selection` | R | **Native syntax for this tool.** The shape is per-tool and validated by that tool's adapter, not by a generic schema |
| `selection_dialect` | R | Names the dialect and its version, e.g. `nuclei-flags/3.11`, `nse-script-names/7.99`, `gitleaks-toml/8.30`. Makes the "we did not invent a language" decision auditable and gives a rename something to fail against |
| `exclude` | O | Native exclusions. Applied *after* selection, always. Defence in depth even where the pinned corpus already excludes |
| `finding_class_default` | R | `technical` / `posture` / `governance` / `compliance` |
| `severity_source` | R | `mapping_table` \| `check_definition` \| `ceiling_only`. **`template_field` is not a legal value** — see §4.4 |
| `severity_table_ref` | R when `severity_source: mapping_table` | Names a versioned table file alongside the profile, never inlined |
| `confidence_ceiling` | R | `confirmed` \| `probable` \| `unconfirmed`. The strongest confidence this component's output may claim. Free-text parses (`http-cors`, `http-config-backup`) may not exceed `probable` |
| `grants_selector_map` | O | §4.3. Maps *selectors* — not templates — to a `grants` floor |
| `evidence_mode` | R | `native_transcript` (tool retains request/response: nuclei, ZAP) \| `tool_output` (evidence_ptr points at the tool's own XML/JSON: nmap, testssl) \| `redacted_excerpt` (§6.5: secret scanners). **The adapter may never synthesize a `.http` transcript from a summary** |
| `enabled` | O, default `true` | A component switched off stays in the file with `enabled: false`, so the profile shows what was considered and declined |

### 2.4 Selection without a query language, per tool

| Tool | `selection_dialect` | Shape | Resolves to |
|---|---|---|---|
| `nuclei` | `nuclei-flags/3.11` | `{tags: [...], template_paths: [...], exclude_tags: [...], exclude_protocols: [...], exclude_severity: [...]}` — the arguments to `-tags`, `-t`, `-etags`, `-et`, `-es` | A concrete template-id list, by running the pinned engine with `-tl` (template list) against the pinned tree at resolve time |
| `nmap-nse` | `nse-script-names/7.99` | `{scripts: [...]}` — the argument to `--script` | The literal script list; there is nothing to expand |
| `testssl` | `testssl-args/3.2` | `{args: [...]}` — verbatim argv | Itself |
| `zap-af` | `zap-af/1` | `{plan: "zap/<name>.yaml"}` — a path to a ZAP Automation Framework plan file, committed | The plan file's own digest |
| `semgrep` | `semgrep-registry/1` | `{configs: ["p/owasp-top-ten", ...]}` | The resolved rule ids at the pinned registry version |
| `gitleaks` | `gitleaks-toml/8.30` | `{config: "secrets/gitleaks.toml"}` — a committed config, never the built-in default | The rule ids in that config |
| `trufflehog` | `trufflehog-flags/3.97` | `{detectors: [...] \| "all", verification: false}` | The detector list |
| `redgold-native` | `rg-checks/1` | `{checks: [...]}` — keys from `baseline_scan.CHECKS` | Itself |

Two rules hold across all dialects:

- **No file-based target list, in any dialect.** `scope_guard.FILE_TARGET_LIST_RE` denies `-l`,
  `-iL`, `--target-file`, `-w` and `--input-file`. Every component is invoked **once per target**,
  by a wrapper that loops in Python and re-checks `in_boundary()` before each shell-out — the same
  pattern `baseline_scan.py` already uses. A dialect whose only multi-target mode is a file list
  simply does not get a multi-target mode.
- **A selector that resolves to zero items is a build failure**, not an empty scan. A typo'd tag is
  otherwise indistinguishable from a clean result, and RG-1 §8.2's whole argument is that "found
  nothing" and "did not look" must be mechanically distinguishable at every level.

### 2.5 `budgets`

```yaml
budgets:
  requests_per_target: 2000        # asserted post-hoc, see §5.4 — not enforced in-band
  rate_limit_per_second: 10        # nuclei -rl; lowered further by scope.yaml, never raised
  wall_clock_seconds: 900          # enforced by the wrapper's process timeout
  concurrency: 1                   # nuclei -c 1 -bs 1. Determinism first; also keeps the
                                   # target's own rate limiting from becoming a variable
  max_host_errors: 30              # nuclei -mhe default; recorded because it changes what ran
```

Two of these need saying out loud. **`rate_limit_per_second` is a ceiling, not a setting**: the
effective value is `min(profile, scope.yaml burst policy)` and the wrapper computes it, so widening
the profile can never widen an engagement. **`requests_per_target` is observed, not enforced** —
§5.4 explains why, and calls it a detection rather than a control, because that is what it is.

### 2.6 `target_discipline`

Unchanged in intent from `test-library-composition.md` §4.2, restated so a reviewer can confirm
compliance from the YAML alone:

```yaml
target_discipline:
  one_target_per_invocation: true
  forbidden_flags: ["-l", "--list", "-iL", "--target-file", "-w", "-i", "--input-file"]
  boundary_recheck: per_target
  allowed_methods: [GET, HEAD, OPTIONS]     # anything else requires the write path (§5.5)
```

### 2.7 Complete worked example

Two files. Both are complete, not fragments.

```yaml
# profiles/pins.lock.yaml
lock_version: 1
recorded: 2026-08-20
components:

  - tool: nuclei
    kind: engine
    image: "projectdiscovery/nuclei:v3.11.1-arm64"
    image_digest: "sha256:<resolved-at-pin-time>"      # [VERIFY] not resolved in this session
    engine_version: "3.11.1"
    pin_strength: image_digest
    notes: >
      Kali also ships nuclei 3.11.0-0kali1. If the container path is unavailable the apt
      binary is the fallback and its pin_strength drops to version_string — record which
      one actually ran, per §1.2.

  - tool: nuclei-templates
    kind: corpus
    git_ref: "v10.4.7"
    git_commit: "83234ce456da3e90dda86dfbc5e605e64a846df3"
    pin_strength: git_commit
    tree_hash: "<sha256 of the resolved subtree>"       # written by resolve_profile.py

  - tool: nmap
    kind: binary
    version: "7.99+dfsg-1kali1"
    pin_strength: version_string
    weakest_in_profile: true          # rendered in the report's methodology section

  - tool: testssl
    kind: image
    image: "ghcr.io/testssl/testssl.sh:3.2.4"
    image_digest: "sha256:<resolved-at-pin-time>"       # [VERIFY]
    pin_strength: image_digest

  - tool: gitleaks
    kind: binary
    version: "8.30.1"
    artifact: "gitleaks_8.30.1_linux_arm64.tar.gz"
    file_digest: "sha256:<from the release checksums file>"   # [VERIFY]
    pin_strength: file_digest
    licence: "MIT"

  - tool: trufflehog
    kind: binary
    version: "3.97.0"
    artifact: "trufflehog_3.97.0_linux_arm64.tar.gz"
    file_digest: "sha256:<from the release checksums file>"   # [VERIFY]
    pin_strength: file_digest
    licence: "AGPL-3.0"
    licence_note: >
      Invoked as a separate process, unmodified, not offered as a network service.
      [VERIFY] before any packaging shape that bundles or hosts it.
```

```yaml
# profiles/web-baseline-v1.yaml
profile: web-baseline-v1
profile_version: 1
recorded: 2026-08-20
pins_ref: pins.lock.yaml
mapping: findings-schema-v1
ceiling: low
tested_at_tier: 1
max_templates: 450

target_discipline:
  one_target_per_invocation: true
  forbidden_flags: ["-l", "--list", "-iL", "--target-file", "-w", "-i", "--input-file"]
  boundary_recheck: per_target
  allowed_methods: [GET, HEAD, OPTIONS]

budgets:
  requests_per_target: 2000
  rate_limit_per_second: 10
  wall_clock_seconds: 900
  concurrency: 1
  max_host_errors: 30

deployment_state_check:
  enabled: true
  classifier_version: "deploy-state-v1"
  blocking_signals: [self_signed_or_local_cert, payment_test_key_prefix,
                     framework_debug_page, dev_tool_fingerprint]
  contributes_only: [hostname_convention, vercel_app_host, ephemeral_storage_path,
                     source_map_present, server_header_vercel]
  # x-vercel-deployment-url is deliberately absent: RG-1 §2.3 established it is a REQUEST
  # header, unobservable from outside the deployment. It is not a weak signal; it is a
  # signal RedGold cannot see, and leaving it in would read as coverage.

components:

  - tool: redgold-native
    selection_dialect: rg-checks/1
    selection:
      checks: [env_exposed, git_exposed, dir_listing, admin_open, ghost_admin_open,
               actuator_open, bucket_public, sourcemap, wildcard_cors,
               header_strict_transport_security, header_content_security_policy,
               header_x_content_type_options]
    finding_class_default: technical
    severity_source: check_definition
    confidence_ceiling: confirmed
    evidence_mode: native_transcript
    # Runs FIRST and unconditionally: P10 requires the baseline to run before any
    # fingerprint is known. Nothing below may be a precondition for it.

  - tool: nuclei
    selection_dialect: nuclei-flags/3.11
    selection:
      template_paths: ["http/exposures", "http/misconfiguration"]
      tags: [exposure, misconfig]
    exclude:
      exclude_protocols: [code, flow, headless, javascript, network]
      exclude_tags: [dos, bruteforce, intrusive, oast, fuzz]
      exclude_severity: []
      exclude_template_ids: []          # §9.3 retirement list; empty at version 1
    finding_class_default: technical
    severity_source: ceiling_only
    confidence_ceiling: probable
    evidence_mode: native_transcript
    grants_selector_map: grants/nuclei-selectors-v1.yaml
    # exclude_protocols carries `code` unconditionally. At v10.4.7 the corpus ships 289
    # code-protocol templates (TEMPLATES-STATS.md at that tag), and a code-protocol
    # template executes a command on the SCANNING host. That is a different trust model
    # from "does this regex match a response shape", and it is not negotiable per profile.

  - tool: nmap-nse
    selection_dialect: nse-script-names/7.99
    selection:
      scripts: [http-security-headers, http-cors, http-config-backup]
    finding_class_default: posture
    severity_source: mapping_table
    severity_table_ref: "severity/nse-severity-v1.yaml"
    confidence_ceiling: probable
    evidence_mode: tool_output
    # probable, not confirmed: NSE's per-script `output` is free text a human wrote for a
    # terminal. http-cors emits a bare method list, not a wildcard/credentials verdict, so
    # the hand-rolled wildcard_cors check above stays primary and this is supplementary.

  - tool: testssl
    selection_dialect: testssl-args/3.2
    selection:
      args: ["--severity", "medium", "--jsonfile-pretty"]
    finding_class_default: posture
    severity_source: mapping_table
    severity_table_ref: "severity/testssl-severity-v1.yaml"
    confidence_ceiling: probable
    evidence_mode: tool_output
    # No published JSON schema upstream. The adapter asserts against a committed fixture
    # captured from the pinned 3.2.4 binary; that fixture IS the schema until one exists.

fuzzing:
  enabled: false        # see profiles/web-fuzz-v1.yaml; the baseline does not fuzz
```

The baseline profile deliberately does **not** fuzz. Fuzzing is a separate profile with a separate
tier and its own gate approval (§5), because bundling it into the baseline would make P10's
"the baseline runs on every engagement regardless" claim carry a payload-sending component.

---

## 3. Output → `finding_class`, severity, and the profile stamp

### 3.1 Three severity strategies, and the one that was deleted

| `severity_source` | Applies to | Behaviour |
|---|---|---|
| `check_definition` | `redgold-native` | Unchanged: `Check.severity`, then RG-1's pipeline |
| `mapping_table` | `nmap-nse`, `testssl`, `zap-af`, `semgrep`, `trivy` | A named, versioned table maps a tool-specific outcome key to a severity, then RG-1's pipeline caps it |
| `ceiling_only` | `nuclei`, `gitleaks`, `trufflehog` | Severity is `profile.ceiling` — `low` — for every record, full stop. The tool's own severity claim is recorded as data (§3.3) and computed on by nothing |
| ~~`template_field`~~ | — | **Deleted.** §4.4 |

### 3.2 `finding_class` assignment

`finding_class_default` on the component, with exactly one override path: a
`severity_table_ref` row may set `finding_class` per outcome key, because one NSE script can produce
both a posture observation and a technical one. No agent assigns `finding_class` for scanner output;
it is a property of the profile, resolvable before the scan runs.

The classes matter because RG-1 §5.5 exempts `posture` and `governance` from the
`precondition`/`grants` machinery entirely. Putting testssl and `http-security-headers` output in
`posture` is not a filing convenience: it is what keeps the ladder from rejecting findings that
have no exploit to have a precondition for.

### 3.3 The scanner's own severity claim, as data

Every `ceiling_only` record carries:

```json
"scanner_claim": {
  "tool": "nuclei",
  "template_id": "apache-config-file",
  "claimed_severity": "medium",
  "claimed_tags": ["exposure", "config"],
  "selector": "http/exposures"
}
```

`scanner_claim` follows the precedent RG-1 set for `attack_refs`: **recorded for interchange, never
computed on.** Its one sanctioned use is ordering the verification queue (§4.4) — which is a
scheduling decision, not a disclosure, so being wrong about it costs time and not truth.

### 3.4 `evidence_ptr` by `evidence_mode`

| Mode | Evidence file | Rule |
|---|---|---|
| `native_transcript` | `evidence/F-NNN-<slug>.http` | nuclei writes real request/response via `-sresp -srd <dir>`; the adapter copies the pair for the matched result. **Not** `-irr`: at `v3.11.1` that flag is deprecated and already defaults to true, so passing it is a no-op that will one day become a parse error |
| `tool_output` | `evidence/raw/<tool>-<asset>.{xml,json}` | Points at the tool's own artifact, unedited. The adapter never fabricates a `.http` transcript from a summary to make tool families look uniform |
| `redacted_excerpt` | `evidence/secrets/<fingerprint>.txt` | §6.5. Contains file, line span, detector, value *prefix and length only* — never the value |

### 3.5 The profile stamp on every finding

New additive fields on the finding record. All are facts about the run, none is a judgement, and
none is written by an agent:

```json
"profile": {
  "name": "web-baseline-v1",
  "version": 1,
  "pins_ref_commit": "<framework repo git sha>",
  "component": "nuclei",
  "pin_strength": "image_digest",
  "corpus_pin": "nuclei-templates@v10.4.7+83234ce4",
  "resolved_corpus_hash": "<tree hash asserted by verify_pins V3>",
  "run_id": "R-2026-08-20-0003"
}
```

`discovered_by` keeps its existing meaning and takes the tool name (`"nuclei"`, `"nmap-nse"`,
`"testssl"`, `"gitleaks"`, `"trufflehog"`, `"baseline_scan"`). RG-1 §4.5 then does its work without
modification: `verified_by` is absent on all of these, so every one is demoted to `low` — which is
§4's ceiling arriving through a rule that already exists rather than a new one.

`PROFILE_UNSTAMPED` (blocking): a record whose `discovered_by` names a composed tool and which
carries no `profile` object. Without it a corpus is unattributable to a pin set, and §9's
per-profile-version measurement has no key to group by.

---

## 4. The scanner ceiling and the `grants` problem

RG-1 §5.6 left this open in as many words: the static-table approach works for 12 hand-written
checks and "a per-template `grants` table is not maintainable and inventing one from template
metadata is exactly the fabrication hard rule 2 forbids."

### 4.1 The size of the thing, measured

From `TEMPLATES-STATS.md` committed at `nuclei-templates v10.4.7` (the corpus's own generated
statistics, read at that tag):

| By directory | Count | | By declared severity | Count |
|---|---|---|---|---|
| `http` | 11,038 | | `info` | 5,053 |
| `cloud` | 663 | | `high` | 2,928 |
| `file` | 447 | | `medium` | 2,811 |
| `code` | 289 | | `critical` | 1,830 |
| `network` | 280 | | `low` | 504 |
| `dast` | 249 | | `unknown` | 58 |
| `workflows` | 207 | | | |
| `javascript` | 125 | | | |
| `ssl` / `dns` / `headless` | 38 / 31 / 24 | | | |

Roughly 13,200 templates, of which 4,758 self-declare `high` or `critical`. Hand-annotating a
`grants` object per template is not a large job; it is not a job. At a generous minute apiece it is
several months of work that expires at the next fortnightly corpus bump.

**So the design must not require it, and this section's claim is that it does not require it at
all — because RG-1 already made `grants` unnecessary for exactly this class of record.**

### 4.2 The dissolution

RG-1 §3.3 requires `grants` on `technical` findings **above `low`**. RG-1 D-2 caps scanner output at
`low`. These two facts compose:

> **A record held at the ceiling never crosses the threshold at which `grants` is required.
> `GRANTS_UNDECLARED` does not fire, because it only fires above `low`. The unbounded-table problem
> is not solved; it is never reached.**

That is the whole answer to "what carries `grants` for a template nobody has read": **nothing does,
and nothing needs to, for as long as the record sits at the ceiling.** The moment a record needs to
exceed the ceiling, something has read it — and that something is a different producer, not a bigger
table.

This is not a loophole being exploited. It is the intended shape of RG-1 §5.3's rule that "the escape
is not a bypass, it is a different producer", generalised from three status-only checks to an
arbitrary corpus. The cost is precisely the product statement RG-1 §10.8 already asks the operator
to sign: *pinned scanner output is `low` until an agent verifies it.*

### 4.3 Three tiers of `grants`, and what each costs

Tier 0 covers everything. Tiers 1 and 2 exist so the ceiling is a floor to climb from rather than a
permanent cap.

| Tier | Who declares | Granularity | Count to maintain | What it may do |
|---|---|---|---|---|
| **0 — none** | nobody | every template | 0 | Record sits at `ceiling`. `precondition` is the uniform scanner precondition of RG-1 §5.2 (`capability: none`, `data: none`, `established_by: demonstrated`), which is true of every unauthenticated GET and is not a judgement call. `grants` absent |
| **1 — per selector** | the profile author | the ~6–10 selectors in `components[].selection` | one per selector | Supplies a `grants` **floor** for chain-graph edges (`chain_scan.py`, RG-1 §8.4) and orders the verification queue. **May never raise severity.** A floor that could raise severity is a per-template table wearing a disguise |
| **2 — per record** | `rg-verify`, having read the response | one finding | as many as are verified | The only path above the ceiling. `verified_by != discovered_by`, so RG-1 §4.5 stops demoting, and the record can exceed `low` on its merits |

**Tier 1 is the whole trick, and it is worth stating why it is legitimate.** `grants` at tier 1 is
not a claim about a template. It is a claim about the *selector the profile author deliberately
chose*, e.g.:

```yaml
# profiles/grants/nuclei-selectors-v1.yaml
version: 1
selectors:
  - selector: "http/exposures"
    grants_floor: {capability: none, data: none}
    discloses: config
    rationale: >
      Every template under this path matches a file or endpoint that should not be public.
      What it grants depends entirely on the file's contents, which the selector cannot know,
      so the floor is the bottom of both axes. This row exists to give chain_scan an edge and
      to say out loud that we did not read 400 templates.
  - selector: "http/misconfiguration"
    grants_floor: {capability: none, data: none}
    discloses: null
    rationale: >
      Same reasoning. Some templates in this tree would justify more; we have not read them,
      and the honest floor for an unread template is the bottom.
unmatched_selector_policy: ceiling_only
```

Every floor in that file is the bottom of both axes, and that is the *correct* value — not a
placeholder. An unread detection grants nothing we can evidence, and RG-1 §3.4's rule is that
`grants` has no safe default precisely because guessing high fabricates and guessing low suppresses.
Here neither happens: the floor does not set severity (the ceiling does), so a bottom floor
suppresses nothing.

A template that fires and matches no annotated selector gets `unmatched_selector_policy:
ceiling_only`, which is tier 0 — the default, not an error. There is no state in which the corpus
growing produces a validation failure, which is the property that makes this survive a fortnightly
upstream bump.

### 4.4 Can a template's own `info.severity` ever be trusted?

**Not as severity. Yes as a selector and as a queue ordering.**

The argument, in three parts:

1. **It answers a different question.** RG-1 derives severity from `grants` band, exploitability
   delta over `precondition` and `reach`, an environment cap, and a domination check. A template
   author knows none of those. `info.severity` is a claim about a vulnerability *class in the
   abstract*, on someone else's asset, in an unknown environment. Piping it into the `severity` field
   is a category error before it is an accuracy problem.
2. **The distribution says it is not calibrated for us.** 1,830 `critical` and 2,928 `high` in one
   corpus, contributed by hundreds of authors across years under no severity rubric this project has
   read. Even if every one is defensible on its own terms, the terms are not RG-1's.
3. **The one thing it is good for is triage order.** A `ceiling_only` corpus of, say, 40 findings
   all sitting at `low` gives `rg-verify` no ordering. `scanner_claim.claimed_severity` is a
   perfectly reasonable cheap prior for *which to verify first*, and being wrong about the order
   costs a scheduling inefficiency, never a disclosure.

Two sanctioned uses, both pre-scan and both selection rather than grading:

- `exclude_severity: [info]` as a **selection** filter (nuclei `-es`), to shrink the corpus.
- `claimed_severity` as the sort key of the verification queue.

`SEVERITY_FROM_TEMPLATE` (blocking): a record whose `severity` differs from the profile's `ceiling`
and whose `verified_by` is absent. This is the mechanical form of the deletion — it makes the
tempting implementation (read `info.severity`, write `severity`) fail a test rather than ship.

### 4.5 What this costs, stated plainly

`.git/config` exposure lands at `low`. A nuclei template that correctly identifies an unauthenticated
admin panel lands at `low`. A template that identifies a live RCE — which the corpus contains — lands
at `low` until a human or `rg-verify` re-executes it.

That is a significant under-rating and it is deliberate. Three things make it survivable, and if any
of the three is not built, the ceiling becomes a suppression engine:

1. **The record still exists, in the report, with its evidence.** RG-1's rule is that suppression
   caps and never deletes.
2. **The verification queue is ordered and its length is a reported number.** A profile producing 200
   ceiling-capped findings that nobody verifies is a visible failure, not a quiet one.
3. **§9's promotion path exists.** A template that is validated repeatedly earns a hand-written
   tier-2 grants row at the next pin bump. The ceiling is where a detection starts, not where it
   is sentenced to stay.

---

## 5. Controlled fuzzing

The prior research excluded fuzzing outright on determinism and blast-radius grounds
(`test-library-composition.md` §3.2). The operator overruled: *control it, do not block it, and make
sure what it finds is logged, because it might discover unknown assets or webpages.*

**The overrule is correct, and the prior document's mistake was bundling two different arguments
under one verdict.** "Executes a command on the scanning host" (`code` protocol) and "sends mutated
input to the target" (`dast`) are not the same risk and do not deserve the same answer. The first is
a trust-model problem with no mitigation short of exclusion. The second is a blast-radius problem,
and blast radius is what this framework already knows how to bound.

### 5.1 What stays excluded, unconditionally

The `code` protocol. 289 templates at `v10.4.7`. A `code`-protocol template executes a shell command
on the machine running nuclei, so including the family means every pin decision is also a decision
to trust every contributor to that family not to have hidden something — categorically different
from "does this matcher match a response shape". `exclude_protocols: [code]` appears in every
profile in this document and is not a per-profile choice. Nothing in the operator's direction touches
this.

### 5.2 The corpus, and its pin

The fuzzing corpus is `dast/` **inside `nuclei-templates`**, not the separate
`projectdiscovery/fuzzing-templates` repo (newest tag `v0.0.4`). At `v10.4.7` the `dast/` tree holds
251 `.yaml` files across `dast/vulnerabilities`, `dast/cves` and `dast/ai`; the corpus's own stats
count 249 as templates. One `git_commit` pin covers the deterministic and the fuzzing corpus
together, which removes an entire second pin-drift surface.

Two facts about the corpus that shape the control:

- **`dast/vulnerabilities/sqli/time-based-sqli.yaml` is in the corpus's own `.nuclei-ignore` file**,
  alongside the default-ignored tags `dos`, `local`, `fuzz`, `bruteforce`, `txt-service`. Upstream
  has already decided that template is too noisy or too heavy for a default run. RedGold honours the
  ignore list and adds to it; it never overrides it.
- **DAST templates do not run without `-dast`.** The `fuzz` tag is default-ignored, so enabling
  fuzzing is an explicit, greppable act in the wrapper, not something a tag filter can pull in by
  accident. That is a useful property and the profile format should not paper over it.

### 5.3 The `fuzzing` block

```yaml
# profiles/web-fuzz-v1.yaml — excerpt. Full profile inherits §2.7's structure.
profile: web-fuzz-v1
profile_version: 1
ceiling: low
tested_at_tier: 2

fuzzing:
  enabled: true
  gate_ref_required: true            # refuses to run without a Gate-1 approval reference
  corpus: "nuclei-templates@v10.4.7:dast/vulnerabilities"
  engine_flags:                      # nuclei v3.11.1 spellings, verified against the tagged help
    dast: true                       # -dast
    fuzz_aggression: low             # -fa low   (low|medium|high; low is the engine default)
    fuzz_param_frequency: 10         # -fuzz-param-frequency (engine default)
    fuzzing_type: replace            # -ft replace (replace|prefix|postfix|infix)
    fuzzing_mode: single             # -fm single (single|multiple) — one component per request
    display_fuzz_points: true        # -dfp, so the log records WHERE it fuzzed, not just what
    project: false                   # -project MUST be off: it dedups requests across runs,
                                     #   which makes run 2 differ from run 1 (§5.6)
  scope:
    in_scope_regex: []               # -cs, generated from the boundary; never hand-written
    out_of_scope_regex:              # -cos, always includes the destructive-path deny list
      - "(?i)/(logout|signout|delete|remove|destroy|purge|reset|unsubscribe)"
      - "(?i)/(admin|internal)/.*(delete|drop|truncate)"
  input_set:
    source: "surface.jsonl"          # the URLs rg-surface mapped; NOT a crawl
    max_urls: 40
    max_params_per_url: 12
  budgets:
    requests_per_target: 1500
    rate_limit_per_second: 5
    wall_clock_seconds: 1200
    concurrency: 1
  methods: [GET, HEAD, OPTIONS]      # POST and above require §5.5
  wordlists: []                      # empty for nuclei-dast; see §5.4 if a wordlist is added
```

### 5.4 How the search space is actually bounded

Six bounds, in decreasing order of how much work they do. The ordering matters, because the first
one does most of the work and is the one that gets forgotten.

**1. The input set — the real bound.** nuclei's DAST mode fuzzes the URLs it is *given*; it does not
crawl and does not recurse. So the search space is

> (URLs supplied) × (fuzzable components per URL) × (payloads in the pinned templates)

and the first term is an artifact RedGold controls completely: it is `surface.jsonl`, produced by
`rg-surface`, capped at `max_urls`. **This is what separates controlled fuzzing from a directory
brute-forcer, and it is the reason this is safe to enable at all.** A profile that pointed the fuzzer
at a crawler's live output would have none of this property; the input set must be a *committed,
countable list* before the run starts.

**2. Payload set — pinned, not generated.** DAST payloads live in the pinned template files. There is
no random generation and no external wordlist in the nuclei-dast path, so the payload term of the
product is a constant of the pin. `[VERIFY]`: that the engine does not add engine-side payload
mutation on top of template payloads at `-fa low` — establish by capturing `-srd` output from two
runs against a fixture and diffing (§5.6), not by reading documentation.

**3. Scope regexes.** `-cs`/`-fuzz-scope` is generated from the engagement boundary by the wrapper —
never hand-written into the profile, because a hand-written regex is a second, un-reconciled copy of
the boundary and the two will disagree. `-cos`/`-fuzz-out-scope` carries the destructive-path deny
list unconditionally.

**4. Rate.** `-rl` at `min(profile, scope.yaml)`, `-c 1`, `-bs 1`. Sequential and slow is a
determinism decision as much as a courtesy one: concurrency makes the target's own rate limiting a
variable in the result.

**5. Methods.** `GET`/`HEAD`/`OPTIONS` only at tier 2. Anything that writes goes through §5.5.

**6. The request budget — a detection, not a control, and this must be said plainly.** nuclei has no
total-request cap flag. `-mhe` bounds errors, `-rl` bounds rate, `timeout` bounds wall clock; none of
them bounds requests. So:

- the profile declares `requests_per_target`;
- the wrapper enforces `wall_clock_seconds` with a process timeout, which bounds requests
  *indirectly* at `rate_limit × wall_clock` — a real ceiling, just a loose one;
- after the run, the wrapper counts the actual dispatched requests from the `-srd` store and asserts
  against the declared budget, raising `FUZZ_BUDGET_EXCEEDED`;
- the count, the declared budget and the elapsed time are written to `ledger/activity.jsonl` **and
  into the finding records and the report's methodology section.**

**`FUZZ_BUDGET_EXCEEDED` is a post-hoc detection. It does not stop the requests; it makes an overrun
impossible to not notice.** That is a weaker guarantee than `rate_probe.sh` gives, and it is stated
as weaker rather than described as a cap. The honest ceiling is the product of the rate limit and the
wall clock, and that is the number the report states.

If a profile ever adds an external wordlist (an ffuf-style content-discovery component — `ffuf` is
already in `scope_guard.TIER2_TOOLS`), the wordlist is pinned by sha256 **and its line count is
recorded**, because line count is the term that multiplies the request budget and a wordlist swap
that keeps the filename is otherwise invisible.

### 5.5 Compatibility with `no_handrolled_loops.py` and the tier ceiling

**The honest position first: `no_handrolled_loops.py` does not bound nuclei and cannot.** It is a
`PreToolUse` hook that pattern-matches *shell syntax* — `for`, `while`, `xargs`, brace expansion,
`curl -Z`, more than three URLs on a command line. `nuclei -u <one-url> -dast …` trips none of those
patterns, and correctly so: there is no shell loop. The fan-out happens inside a Go binary the hook
cannot see. A single-command invocation that dispatches 1,500 requests is exactly the shape the hook
was written to catch, arriving in a form the hook does not recognise.

Three consequences, and one recommended change:

1. **This is a coverage gap in the control, not compliance with it.** Do not describe fuzzing as
   "allowed by `no_handrolled_loops.py`". It is *unseen* by it.
2. **The in-band bound is `-rl` plus the wall clock; the out-of-band bound is the egress filter**,
   which per `CLAUDE.md` is the only real boundary and which does not exist yet.
3. **Recommended change to the hook (RG-2 scope):** generalise `SANCTIONED` from the single
   `rate_probe.sh` regex to a small set of sanctioned wrappers, and *require* that any invocation
   naming a `TIER2_TOOLS` member goes through one. Today a bare `nuclei` command line is permitted by
   this hook and gated only by `scope_guard.py`'s tier check. Requiring
   `scripts/scan_run.py --profile <p> --gate-ref G-NNN --target <t>` gives the framework one place
   that owns the rate flag, the budget assertion, the gate reference and the ledger row — the same
   argument that produced `rate_probe.sh`, applied to a tool that loops internally instead of in
   bash.

**Tier ceiling.** Fuzzing is tier 2 and `web-fuzz-v1` declares `tested_at_tier: 2`; `scope_guard.py`
already classifies `nuclei` as a `TIER2_TOOLS` member, so an engagement scoped at ceiling 1 refuses
the invocation with no new mechanism. Any method beyond `GET`/`HEAD`/`OPTIONS` is a write and inherits
the existing write path in full: canary verification (`canary_check.py`), a conspicuous test-data
marker, the cleanup ledger, and Gate approval. **No fuzzing component may issue a write without going
through `rate_probe.sh`-equivalent accounting**; in practice this means the write-fuzzing case is out
of scope for RG-3 and is named here only so its absence is deliberate.

**The severity ceiling applies unchanged.** Fuzz-sourced findings are `discovered_by: "nuclei"` with
no `verified_by`, so RG-1 §4.5 demotes them to `low` exactly like every other scanner record. A
fuzzer cannot produce a high-severity finding in this framework. It can produce a *queue entry* for
`rg-verify`, which can.

### 5.6 Reproducibility: what survives, and what the report must say

P11 (repeatability) cannot be satisfied by fuzzing in the sense it is usually read. The honest
decomposition:

| Property | Reproducible? | Why |
|---|---|---|
| The template corpus and payload set | **Yes** | Pinned by `git_commit` and asserted by `verify_pins` V3/V4 |
| The input URL set | **Yes** | `surface.jsonl` is a committed artifact of the engagement |
| The set of requests dispatched | **Probably**, and it is `[VERIFY]` | `-fuzz-param-frequency` skips parameters based on *observed responses*, so request selection is response-dependent and therefore target-state-dependent. `-project` must be off or run 2 differs from run 1 by construction. Establish empirically by running the pinned build twice against a local fixture and diffing the `-srd` corpora — the same fixture discipline testssl.sh's absent schema forced |
| The findings produced | **No** | The target is stateful, rate limiting and WAFs respond differently under load, and a timing-based matcher is a coin weighted by the network |

**The claim that survives, and the exact sentence the report must carry:**

> "This scan's inputs are reproducible: the same profile version, template pin and endpoint list
> produce the same test plan. Its outputs are not. Re-running this scan against the same system may
> produce a different set of findings, in either direction. Every finding below was recorded with its
> request and response; a finding that could not be reproduced on re-execution is listed as such
> rather than removed."

Two mechanical consequences:

1. **Every fuzz-sourced record is `confidence: unconfirmed` at emission**, rising to `probable` only
   when the adapter re-issued the matching request within the same run and got the same result, and
   to `confirmed` only through `rg-verify`. `confidence_ceiling: unconfirmed` on the fuzzing
   component enforces it.
2. **Non-reproduction is a recorded outcome, not a deletion.** When `rg-verify` cannot reproduce a
   fuzz finding, that is a `review.jsonl` row with `verdict: REJECTED` and a rationale, and the record
   stays in the document under RG-1 §4.3's cap-never-delete rule. It also feeds §9's per-template
   false-positive count, which is where the value of recording it accrues.

### 5.7 The valuable half — discoveries reach the asset register

The operator's actual point, and the part that is worth more than the vulnerability findings: **a
fuzzer that gets a 200 on `/api/internal/v2/export` has performed asset discovery.** Today that
result exists only inside nuclei's stdout, is not a finding (no matcher fired), and is discarded.

#### 5.7.1 The gap in the current model

`assets/register.jsonl` and `assets/candidates.jsonl` key identity on **`(identifier, port)`** —
`scope_cli.normalise_identifier` and the dedup check in `cmd_add_candidate` are explicit that "a
different port on the same host is a different asset". **A path is not representable.** There is
nowhere for `/api/internal/v2/export` to go. That is the actual reason discovery is discarded, and no
amount of logging fixes it.

#### 5.7.2 `assets/surface.jsonl` — a new artifact

> **[CONTRADICTS `docs/REDGOLD-BRIEFING.md` §5, which is emphatic that the scope model is "three
> artifacts, three rules". This makes four.** Recorded 2026-08-20 by the currency audit;
> `docs/research/strategic-review.md` §1.3 assesses the addition as **well-argued and correct on
> authorisation**, and identifies three composition costs this section does not see: coverage now has
> two keys (RG-1 §8.3 is asset-keyed, §5.7.4's `SURFACE_UNDISPOSED` is surface-keyed, and the shipped
> code implements only the first); RG-4's `scope-record.yaml` has no surface concept, so the
> client-side artifact cannot express the object §5.7.4 makes phase completion depend on; and §5.7.5
> treats a fuzz **run** as a `COVERAGE_EMPTY_PHASE` candidate, which — with `rg2-rate-control.md`'s
> `run_id` — makes three units of work against one `gate_cli.py complete --phase`. **Unresolved.**
> The briefing carries the reciprocal marker. Nothing in `scripts/` reads or writes this file.**]**

One row per discovered path or endpoint. It is a *surface* register, subordinate to the asset
register, and it deliberately does not reuse the CANDIDATE/CONFIRMED vocabulary, because that
vocabulary is about **attribution** — "does the client own this?" — and a path on a host we have
already attributed raises no attribution question at all.

```json
{
  "surface_id": "S-014",
  "asset_id": "A-002",
  "path": "/api/internal/v2/export",
  "method": "GET",
  "first_seen": "2026-08-20T11:04:12Z",
  "discovery_method": "fuzz",
  "discovered_by": "nuclei",
  "run_id": "R-2026-08-20-0007",
  "profile": {"name": "web-fuzz-v1", "version": 1},
  "observed": {"status": 200, "content_length": 18422, "content_type": "application/json"},
  "evidence_ptr": "evidence/surface/S-014.http",
  "attribution": "inherited:A-002",
  "named_in_plan": false,
  "disposition": null,
  "notes": null
}
```

#### 5.7.3 Attribution, and why `scope_guard.py` needs no change

`scope_guard.py`'s CONFIRMED-asset requirement is a rule about **which hosts active tooling may
touch**. A path is not a host. Three cases, and only one of them is new:

| What the fuzzer surfaced | Where it goes | Authorisation consequence |
|---|---|---|
| A path on an already-CONFIRMED asset | `surface.jsonl`, `attribution: inherited:<asset_id>` | **None.** The host was already in the boundary and already CONFIRMED. Recording a path creates no new permission, and requests to it were already permitted by the same rule that permitted the scan |
| A path on an in-scope host that is only CANDIDATE | `surface.jsonl` with `attribution: inherited:<candidate_id>`, and **not probed further** | Unchanged: the host is untouchable above tier 1 until promoted. The row records that we saw it |
| A **new host** (a redirect target, a CORS `Access-Control-Allow-Origin` value, a hostname in a JS bundle) | `assets/candidates.jsonl` via the existing `add-candidate` path, `discovery_method: fuzz`, status CANDIDATE | Unchanged and strictly enforced: a new host is not probeable until it has two independent attribution signals or `CLIENT_CONFIRMED`. **The fuzzer discovering a host is not an attribution signal.** It is a `CONTENT_FP`-class observation at best, and one signal never promotes |

The third row is the one to guard hardest, because it is where a fuzzer could otherwise widen a
boundary by finding things. It cannot: the promotion rule is untouched, and discovery is not
attribution.

#### 5.7.4 Interaction with Gate 2 deviation

A newly discovered in-scope path that the approved plan does not name *is* a deviation, and the
resolution turns on a distinction the framework has not yet had to make:

> **Recording is not testing.** Writing a `surface.jsonl` row is an observation about a request that
> has already been sent under an existing approval. **Targeting** that path with anything beyond what
> the approved plan authorised is the deviation.

So:

- **Discovery → always recorded, never gated.** Gating the *record* would produce exactly the failure
  mode the operator is objecting to: the finding is thrown away because writing it down was
  inconvenient. A gate that suppresses evidence is worse than no gate.
- **`named_in_plan: false` raises `SURFACE_UNPLANNED`, non-blocking, at discovery**, routed to the
  operator and into the report's coverage section.
- **`disposition` is required before phase completion**, from a closed vocabulary:
  `tested` · `deferred:<reason>` · `out_of_plan` · `out_of_scope` · `duplicate:<surface_id>`.
  A `surface.jsonl` row with `disposition: null` blocks `gate_cli.py complete --phase`, raising
  **`SURFACE_UNDISPOSED`**.
- **Moving a row to `tested` when the plan did not name it requires a Gate 2 deviation record** —
  the existing mechanism, with the existing operator decision, appended to `ledger/gates.jsonl`.

This converts discovery from a silent scope expansion into a **coverage obligation**, which is the
same move RG-1 §8.1 makes with `not_attempted` reasons. The engagement cannot quietly ignore what it
found, and it cannot quietly test what it was not approved to test.

#### 5.7.5 Discovery is a result even when nothing fires

Two rules that make the discovery half actually work:

1. **`surface.jsonl` rows are written for every distinct response the fuzzer elicited that differs
   materially from the baseline for that path prefix** — a 200 or a 401/403 on a path that returns
   404 elsewhere is an existence proof and is the discovery. It does not require a matcher to fire.
   `-dfp/-display-fuzz-points` is enabled so the log records where the engine fuzzed, not only what
   it matched.
2. **A fuzz run that produces zero findings and zero surface rows is a `COVERAGE_EMPTY_PHASE`
   candidate**, not a clean result. RG-1 §8.2's rule generalises: a fuzzer that looked at 40 URLs and
   recorded nothing at all is much more likely to have been misconfigured than to have found a
   perfectly tidy application.

---

## 6. Secret scanning — gitleaks and trufflehog together

Runs in `rg-codeaudit` only, when a `SOURCE_CODE` asset is in scope. This is the track that produced
**zero artifacts** on the prior engagement while a live, spend-capable Resend key sat in a config
nobody read (RG-1 §1.2a). Of everything in this document, this is the component with the clearest
evidence that it would have found something real.

### 6.1 Why both, and not one

| | gitleaks `8.30.1` | trufflehog `3.97.0` |
|---|---|---|
| Detection model | Regex + entropy rules from a TOML config | Per-provider detectors with structured parsing |
| Corpus size | Rule count is whatever the committed config declares | Its own README at `v3.97.0` states it "classifies over 800 secret types" |
| Git history | First-class (`gitleaks git`), plus `gitleaks dir` for a working tree | Has git and filesystem sources |
| **Liveness** | **None.** Pattern matching only | **Verification**: the README states that for each detected credential it performs "programmatic verification against the API that we think it belongs to" — e.g. the AWS detector calls `GetCallerIdentity` |
| Licence | MIT | AGPL-3.0 |
| Config | `--config/-c`, `GITLEAKS_CONFIG`, or `.gitleaks.toml` | Detector flags |
| Output | `-f/--report-format json` | `-j/--json` |
| ARM64 | `gitleaks_8.30.1_linux_arm64.tar.gz` in the tagged release | `trufflehog_3.97.0_linux_arm64.tar.gz` in the tagged release |

**The argument for both is not "more coverage".** It is that they answer two different questions and
neither answer substitutes for the other:

- gitleaks answers *"is there a credential-shaped string anywhere in this repository's history?"* —
  and history is where the prior engagement's class of finding lives, because a secret removed in a
  later commit is still a secret.
- trufflehog answers *"is this string a live credential?"* — which is the difference between a
  low-severity hygiene note and RG-1 §F.5's spend-capable key.

Running only gitleaks produces a list nobody can prioritise. Running only trufflehog misses
everything its 800 detectors do not model, including every bespoke internal token format, which is
precisely what a startup's own codebase is full of.

This also does **not** contradict "one curated tool beats two", which the prior research applied to
trivy-vs-grype. That verdict was about two tools answering the *same* question with different
false-positive profiles. These two answer different questions.

### 6.2 Verification is a live network action against a third party — default OFF

This is the design decision in this section, and it is not close.

`trufflehog` verifying a Stripe key calls **Stripe's** API. Stripe is not the client, is not in
`scope.yaml`, has signed nothing, and `scope_guard.py` will never see the request because it is made
from inside a Go binary rather than from a shell command line the hook can parse. Four distinct
problems, any one of which is sufficient:

1. **Authorisation.** RedGold's hard rule 4 is that no target is touched without a signed scope. A
   verification call touches a provider that is not in the scope.
2. **It is indistinguishable from credential abuse.** An authentication attempt with the client's
   key, from an IP the client has never used, is what a leaked-credential attack looks like. It may
   land in the client's provider audit log, trigger their alerting, or in the worst case trip a
   provider's automated key-revocation — turning an audit into an outage.
3. **The boundary cannot see it.** `CLAUDE.md`'s containment argument is that the network is the
   boundary. A verification call to `api.stripe.com` from inside the contained environment is exactly
   the egress a filter would deny — so on a properly filtered host verification *fails*, and
   trufflehog reports the result as `unknown` (verification errored), which is indistinguishable from
   "the key is dead". Enabling verification without opening egress produces confidently wrong output.
4. **It generates side effects nobody recorded.** Some verifications are not read-only in the
   client's ledger sense — they create API-log entries, count against rate limits, and for some
   providers create sessions.

**Therefore: `--no-verification` is the default and is set by the wrapper, not left to a config
file.** The profile field is `verification: false` and flipping it to `true` requires all of:

- an explicit `scope.yaml` key, `third_party_credential_validation: true`, naming the providers;
- a Gate approval reference recorded on the run;
- an egress allowance for those provider hosts (which is a decision on the filtering machine, not in
  this repo);
- one secret at a time, operator-initiated, never a bulk pass;
- a `ledger/activity.jsonl` row per verification attempt, before the call, with the provider named.

**What the report says when verification is off, which is most of the time.** It must not say the
key is live and must not say it is dead:

> "A credential of type `resend` is present at `<file>:<line>`. RedGold did not attempt to validate
> it: validating a credential requires contacting the issuing provider, which is outside the
> authorised scope of this engagement. Treat it as live and rotate it."

*"Treat it as live and rotate it"* is the correct remediation regardless of liveness, which is what
makes declining to verify cost the client nothing.

### 6.3 Pinning and invocation

Both are single static Go binaries with tagged `linux/arm64` release artifacts, pinned by
`file_digest` (§1.2) taken from the release's own checksums file. Neither is fetched at runtime.

- **gitleaks** must run with a **committed config** (`-c secrets/gitleaks.toml`), never the built-in
  default set, because the built-in set changes between versions and a profile whose rule set is "the
  default" is unpinnable by construction. The config is versioned with the profile.
- **trufflehog**'s detector set is compiled into the binary, so the version pin *is* the detector
  pin. Any future detector-config surface must be committed the same way. `[VERIFY]` whether
  `v3.97.0` performs any network fetch on startup independent of verification (analytics, update
  check); if it does, disable it and record the flag.
- Both run against a **local checkout path**, never a remote URL — no `trufflehog github --org=…`,
  which would be network activity against a host outside the boundary.
- Exit codes are results, not failures: gitleaks exits `1` when leaks are present. The wrapper must
  treat `1` as a normal outcome and only `126`/other as an error, or every successful scan reads as a
  crash.

### 6.4 Output → findings, and deduplication

Both adapters produce records with `finding_class: technical`, `severity` at the profile ceiling
(`low`), `discovered_by` naming the tool, and `evidence_mode: redacted_excerpt`.

gitleaks' JSON `Finding` struct at `v8.30.1` carries `RuleID`, `Description`, `StartLine`, `EndLine`,
`StartColumn`, `EndColumn`, `Match`, `Secret`, `File`, `Commit`, `Entropy`, `Author`, `Email`, `Date`,
`Tags`, and **`Fingerprint`** — a native stable identity we can use directly.

**Deduplication key:** `(asset_id, normalised_file_path, start_line, value_fingerprint)` where
`value_fingerprint` is `sha256(secret_value)` computed **in the wrapper's memory and never written to
disk in any form that includes the value**. gitleaks' own `Fingerprint` is used where available and
the sha256 is the cross-tool join key, since trufflehog does not emit gitleaks' fingerprint.

Merge rule, and it matters that it does not touch severity:

```
one finding per (asset_id, value_fingerprint)
  discovered_by  = the first tool to report it (deterministic: gitleaks runs first)
  corroborated_by = ["trufflehog"]        # new field, list, may be empty
  confidence     = "probable" if len(corroborated_by) > 0 else "unconfirmed"
  severity       = profile.ceiling        # unchanged. Always.
```

**Two independent detectors agreeing raises `confidence`, never `severity`.** RG-1 §7.2's argument
applies verbatim: raising severity requires re-execution, and two pattern matchers agreeing is not
re-execution. A record whose severity rose because two tools matched the same regex would be a
severity claim produced by *reading*, which the framework forbids everywhere else.

Where trufflehog reports a *verified* credential (verification having been explicitly authorised per
§6.2), that is a different thing: an executed check with a provider's own answer. It sets
`verified: "executed"` and `verified_by: "trufflehog"`, and per RG-1 §4.5 the record may then exceed
`low` on its merits — a rare and legitimate case of a composed tool producing an above-ceiling
finding, because it genuinely re-executed rather than re-read.

### 6.5 The `redact.py` collision, worked out

`redact.py` is a `PostToolUse` hook that rewrites tool output before it reaches the transcript,
preserving prefix and length: `re_AbCd…` → `re_[REDACTED-32]`. A secret scanner is the one tool whose
entire output is the thing that hook exists to destroy. Four findings:

**(1) The redaction is correct and must not be weakened.** The model never needs the value. Prefix +
length is exactly enough to report the credential class, prove it is not a placeholder, and tell the
client which key to rotate — which is `redact.py`'s own stated design intent, and it is right.

**(2) But the *pipeline* must not depend on the model reading the tool's stdout.** If the wrapper
prints raw JSON and lets the hook clean it up, then the dedup fingerprint, the line spans and the
detector name all arrive at the model already mangled, and the model is being asked to reconstruct a
record from redacted text. So: **`scripts/secret_scan.py` owns the whole path.** It invokes both
tools with output to files under `evidence/secrets/`, parses them itself, computes fingerprints in
memory, writes finding records, and prints **only an already-redacted summary** to stdout.
`redact.py` then has nothing left to strip and functions as a backstop rather than as a load-bearing
component. A control that is load-bearing and best-effort at the same time is a control that will
fail quietly.

**(3) The real risk is a detector-set mismatch, and it runs the opposite way to the obvious one.**
`redact.py`'s pattern list is roughly fifteen provider formats. trufflehog models over eight hundred.
**So the dangerous case is not "redact.py destroys a secret we needed"; it is "a secret trufflehog
found in a format redact.py does not know passes through unredacted onto disk."** The fix is
structural: **redact at the source, using the finder's own span, rather than downstream by
re-matching patterns.** gitleaks reports `File`, `StartLine`, `EndLine`, `StartColumn`, `EndColumn`
and `Secret`; trufflehog reports the raw value. The wrapper therefore knows *exactly* where each
secret is and can redact by coordinates, with no pattern knowledge at all. That is strictly stronger
than pattern-based redaction and it is available for free because the scanners hand it to us.
Recommended follow-on: feed the scanners' span output back as an input to the transcript redactor for
the rest of the session, so a value found once is redacted everywhere thereafter.

**(4) The scanners' own report files are themselves a secret store.** gitleaks' JSON `Finding` has a
`Secret` field: **by default the report on disk contains the plaintext credential.** Three
consequences: run gitleaks with `--redact` (`--redact uint[=100]`) so its own report is redacted;
treat `evidence/secrets/` as never-committed and never-copied; and the `evidence_ptr` for a secret
finding points at a wrapper-generated redacted excerpt, never at the tool's raw report. This is the
single most likely way for this component to leak a client credential into an artifact, and it is a
default rather than an edge case.

**What never happens:** a raw secret value in `findings/*.json`, in `evidence/`, in the report, in
`status.md`, in a ledger row, or in this repository. The value exists in the wrapper's memory and in
the client's codebase, and nowhere else RedGold controls.

---

## 7. Generalising off Supabase

The operator's instruction: *"Don't focus on Supabase, that was one person. This is a framework."*
The spec already diagnosed the failure it is guarding against — `supabase-audit` was simultaneously
the flagship skill and the *only* implementation of backend auditing, "a design that silently assumed
every future target would be Supabase" (`09-playbooks.md` §11.4). The v1 build order then reproduced
it by shipping "one hardcoded flagship (Supabase) plus `_generic/`".

**The test of whether this document escapes that trap is not whether Supabase is mentioned. It is
whether the check definitions live in the generic layer.** A vendor layer that can define its own
checks is a Supabase system with hooks for others, whatever the directory is called.

### 7.1 The rule

> **The generic layer owns the check: its detection logic, its `finding_class`, its severity mapping
> and its `grants` floor. The vendor layer owns only three things: the fingerprint, the parameters,
> and the known-secure defaults.**
>
> A vendor playbook that needs to define a new *check* has found a missing generic family. Record it
> as `GENERIC_FAMILY_GAP` and take the extension path (§7.5). Do not special-case it.

### 7.2 The backend-agnostic check families

Seven families. Each is defined once, in `playbooks/_generic/`, parameterised per backend. Family
ids are stable and are what `coverage.jsonl` records against, so coverage is comparable across
engagements with entirely different stacks — which is a benefit that only exists if the families are
generic.

| Id | Family | The question, asked without naming a vendor |
|---|---|---|
| **G1** | Anonymous data-plane read | Does a data API return rows or objects to a caller holding no credential, or holding only a credential embedded in the public client bundle? |
| **G2** | Client-embedded credential differentiation | The bundle ships a key. Is it the *public* key or a *privileged* one, and does the server distinguish them? |
| **G3** | Object-storage listing | Can an anonymous caller enumerate stored objects? (`_bucket_listing` today — already shape-based, already vendor-neutral, and the model for the rest) |
| **G4** | Row/object-level authorisation | Given a legitimate caller, is per-row or per-object authorisation actually applied, or is the data plane trusting the client to filter? |
| **G5** | Tenant isolation / identifier substitution | Does substituting another tenant's identifier return their data? (IDOR/BOLA) |
| **G6** | Authentication-flow surface | Magic links, OAuth callbacks, password reset, session fixation, token lifetime |
| **G7** | Deployment discoverability | Preview/branch deployments reachable, and wired to production data |

**G1 and G4 are the family CVE-2025-48757 is an instance of.** Framing that CVE as "the Supabase RLS
check" is precisely the error: the misconfiguration is *"a data plane exposed directly to the client
with authorisation delegated to a policy layer that is off by default"*, and that shape exists on
Firebase, on self-hosted PostgREST, on Hasura, and on every GraphQL backend with permissive root
fields. The vendor detail is only where to send the request.

### 7.3 The four backends, side by side

| | **Supabase** | **Firebase** | **Plain Postgres + PostgREST** | **Generic session-cookie app** |
|---|---|---|---|---|
| Fingerprint signals | `*.supabase.co` host, `supabase` in JS bundle, `apikey` header convention | `*.firebaseio.com` / `*.firebasedatabase.app`, `firebaseConfig` object in bundle | `Server: postgrest/*`, OpenAPI doc at `/`, `Content-Range` on collections | **None distinctive.** This is the important row |
| Public credential in bundle | `anon` JWT | `apiKey` in `firebaseConfig` | usually none | none |
| Data-plane path shape | `/rest/v1/<table>?select=*` | RTDB `/<path>.json`; Firestore REST `/v1/projects/*/databases/*/documents/*` | `/<table>` | no client-facing data plane |
| Authorisation layer | Row Level Security policies | Security Rules | RLS + role grants | server-side handlers |
| **G1** | Parameterised: anon key + table path | Parameterised: `.json` path | Parameterised: table path | **`not_applicable`** |
| **G2** | `anon` vs `service_role` (both JWTs; the claim distinguishes them) | `apiKey` is not a secret by design — a *known-secure default*, must not be reported as a flaw | n/a | n/a |
| **G3** | Storage API listing | Cloud Storage object listing | n/a | n/a — or an S3/R2 bucket, which is its own asset |
| **G4** | RLS policy present and non-trivial | Security Rules present and non-trivial | RLS enabled per table | server-side, only observable via G5 |
| **G5** | applies | applies | applies | **applies — and is the primary family here** |
| **G6** | magic link, OAuth | Firebase Auth flows | n/a | session cookie flags, fixation, rotation on privilege change |
| **G7** | Vercel/Netlify preview + branch databases | preview channels | deployment-specific | deployment-specific |

Three things this table is doing:

1. **The generic session-cookie column is the one that proves the design.** For a conventional
   server-rendered app, G1–G4 have no analogue at all — there is no client-facing data plane to be
   unauthorised. Those coverage rows must be `not_applicable`, **not** `absent`. Emitting them as
   `absent` is RG-1 FM-7 exactly: the checklist × asset cartesian that produced 36 records for one
   fact. The generic families make this cheap to get right, because "does this backend have a data
   plane" is a single fingerprint-level question answered once per asset rather than once per check.
2. **Firebase's `apiKey` is a known-secure default and belongs in the vendor layer.** Google
   documents it as a public identifier, not a secret. A framework that reports it as an exposed
   credential burns client trust on its first paragraph. `known_secure_defaults` is a required
   section of every vendor playbook for exactly this reason, and it is the section the prior
   engagement got right when it credited Supabase RLS for blocking 9/9 privilege-escalation attempts.
   `[VERIFY]` the current Firebase documentation before this claim reaches a client.
3. **Plain PostgREST has no distinctive fingerprint worth trusting.** Which means dispatch will
   frequently match nothing, which means the no-match path is the normal path — §8.4.

### 7.4 What a vendor playbook may contain

```yaml
# playbooks/backends/supabase/PLAYBOOK.yaml — the machine-readable half
id: backends/supabase
specializes: _generic/backend-authz
fingerprint:
  any_of:
    - {signal: dns_cname,   match: "*.supabase.co"}
    - {signal: js_bundle,   match: "supabase"}
    - {signal: http_header, key: "x-client-info", match: "supabase"}   # [VERIFY]
versions: ["<2.100", "2.100-2.110", ">2.110"]
provides:                      # parameters ONLY. No check definitions.
  G1:
    data_plane_paths: ["/rest/v1/{table}?select=*&limit=1"]
    public_credential: {location: js_bundle, kind: jwt, claim_role: "anon"}
    table_names_from: fingerprint      # never a hardcoded list — see below
  G2:
    privileged_role_claim: "service_role"
  G3:
    listing_paths: ["/storage/v1/object/list/{bucket}"]
known_secure_defaults:
  - "RLS blocks anonymous row reads when a non-trivial policy exists; do not report a
     correctly-policied table as a finding."
  - "[VERIFY] RLS default-on/default-off differs by how the table was created (SQL vs
     dashboard). Establish from Supabase's own docs before asserting either to a client."
seed_hypotheses: PLAYBOOK.md          # prose, for the agent
evals: evals/evals.json
harvested_from: []
```

**`table_names_from: fingerprint` is deliberate and is the open question the prior research left.**
A hardcoded list of common table names (`users`, `profiles`, `orders`) is a wordlist wearing a
playbook's clothes: it turns G1 into a brute-force with an unbounded false-negative rate and no
recorded search space. Table names must come from what `rg-surface` actually observed — the OpenAPI
document PostgREST serves, the queries in the client bundle, the GraphQL introspection response. If
none of those is available, **G1 is `not_attempted` with reason `blocked_by`, and that is an honest
coverage gap** rather than a guessing game. If an operator later wants a name wordlist, it is a
fuzzing component under §5 with a pinned, digest-recorded wordlist and a request budget, not a
playbook parameter.

### 7.5 The extension path

Same bar as RG-1 §7.5, deliberately — one bar for the whole framework. A vendor playbook wanting a
check the generic layer does not have raises `GENERIC_FAMILY_GAP`. **Three occurrences across two
engagements** opens a candidate new generic family, with its citations, which the operator writes or
rejects with a reason. One instance is not a family, and the failure this guards against is the one
`09-playbooks.md` §11.4 already named.

---

## 8. Playbook dispatch, reopened

`12-deliverables-and-build-order.md` §17.1 deferred dispatch to v2: *"dispatch solves a problem that
does not exist at n=1, and building it early means designing the index against a single example."*
The operator has reopened it: *"that needs to change, that is a bad start, bad foundations."*

### 8.1 Why the operator is right

The deferral's reasoning is about **selection cost at library scale** — with one playbook there is
nothing to select between, so a selector is overhead. That reasoning is sound about the *dispatcher*
and wrong about the *architecture*, because the v1 cut it justified was "one hardcoded flagship
(Supabase) plus `_generic/`", and a hardcoded flagship is not a deferred dispatcher. It is a
**different data model**: check logic lives in the vendor skill, `_generic/` is documentation, and
every future backend is a port rather than a parameterisation.

That is the exact failure `09-playbooks.md` §11.4 says the design exists to prevent. The framework
would have shipped the thing it wrote down that it must not ship.

**So what changes is not "build the matcher earlier". It is "the generic layer is the implementation
and the vendor layer is data, from the first commit."** The matcher is the cheap part. The data model
is the expensive part, and the data model is what n=1 corrupts.

### 8.2 `playbooks/index.yaml`

```yaml
# playbooks/index.yaml
index_version: 1
recorded: 2026-08-20

signal_classes:            # CLOSED vocabulary. Adding a class is a framework change (§8.5).
  - dns_cname
  - http_header
  - http_body
  - js_bundle
  - cookie_name
  - openapi_doc
  - tls_cert_san
  - favicon_hash

entries:
  - id: _generic/backend-authz
    kind: generic                 # generic entries are ALWAYS loaded; they have no fingerprint
    provides_families: [G1, G2, G3, G4, G5]

  - id: _generic/session-apps
    kind: generic
    provides_families: [G5, G6]

  - id: _generic/deployment-exposure
    kind: generic
    provides_families: [G7]

  - id: backends/supabase
    kind: vendor
    specializes: _generic/backend-authz
    fingerprint:
      any_of:
        - {signal: dns_cname, match: "*.supabase.co"}
        - {signal: js_bundle, match: "supabase"}
    versions: ["<2.100", "2.100-2.110", ">2.110"]
    profile_hints: {components: [nuclei], selectors: ["http/misconfiguration"]}
    seen_in_engagements: 1
    last_updated: 2026-08-20

  - id: backends/firebase
    kind: vendor
    specializes: _generic/backend-authz
    fingerprint:
      any_of:
        - {signal: dns_cname, match: "*.firebaseio.com"}
        - {signal: js_bundle, match: "firebaseConfig"}
    seen_in_engagements: 0
    last_updated: 2026-08-20

  - id: backends/postgrest
    kind: vendor
    specializes: _generic/backend-authz
    fingerprint:
      all_of:
        - {signal: http_header, key: "server", match: "postgrest"}
    seen_in_engagements: 0
    last_updated: 2026-08-20
```

### 8.3 Dispatch, mechanically

*Input:* `fingerprint.json`, a structured artifact written by `rg-surface` — a list of observed
signals, each `{signal, key, value, evidence_ptr}`. **`rg-surface` emitting structured signals rather
than prose is a real prerequisite and is part of the cost** (§8.6).

```
1. Load every entry with kind: generic.            # unconditional — the primary path
2. Match each vendor entry's fingerprint against the observed signal set.
   any_of  -> one signal suffices;  all_of -> every signal required.
3. Load every matched vendor entry AND its `specializes` ancestors, transitively.
   Load NOTHING else.
4. Where several vendor entries match, load all of them. Never pick.
   Ambiguity is a fact about the target and is recorded, not resolved by a heuristic.
5. Append one `playbook.dispatch` row to ledger/activity.jsonl:
   {observed_signals, matched: [...], loaded: [...], index_version, at}
   -- INCLUDING when `matched` is empty.
```

Step 5's parenthetical is the one that matters. **"No playbook matched" and "dispatch never ran" must
be mechanically distinguishable**, which is RG-1 §8.2's principle applied one layer up. A `matched:
[]` row is a normal, healthy outcome; a missing row is a phase that did not dispatch.

`DISPATCH_UNRECORDED` (blocking at phase completion): a phase whose plan names a playbook-driven
family and which has no `playbook.dispatch` ledger row.

### 8.4 The no-match path is the primary path

This is the design's load-bearing claim and the answer to the overfitting risk:

> **Acceptance test for dispatch: an engagement whose fingerprint matches zero vendor entries still
> produces a complete coverage record set across every applicable generic family.**

If that test passes, then a wrong, over-broad or under-broad fingerprint costs *seed hypotheses and
known-secure-defaults*, not coverage. Dispatch becomes an accelerator that can be wrong, rather than a
router that can drop work on the floor. And §7.3 already established this path is not rare: plain
Postgres+PostgREST and generic session-cookie apps have no fingerprint worth trusting, and those are
ordinary startup stacks.

### 8.5 What the "not at n=1" argument got right

Fairly, because it is not a bad argument and the risk it names has not gone away:

1. **A schema fitted to one example is fitted to one example.** Supabase's fingerprint is unusually
   easy — a distinctive apex domain, a distinctive bundle string. A signal vocabulary designed around
   that will be too weak for stacks whose signals are ambiguous or absent. This is structurally the
   same failure RG-1 §11.2 diagnoses in the 8/11 scoreboard: *a vocabulary designed after seeing one
   corpus carries little information about out-of-sample behaviour.*
2. **Building the matcher costs real time that a first paying client does not benefit from.** The
   deferral's product instinct was right.
3. **An early index invites premature vendor entries** — writing `backends/firebase` before ever
   seeing a Firebase engagement means writing fiction, and fiction with a `fingerprint` block reads
   like knowledge.

Three mitigations, each of which is a mechanical bar rather than an intention:

- **The signal-class vocabulary is closed and versioned**, and adding a *class* takes the same
  ≥3-occurrences-across-≥2-engagements bar as everything else in the framework. Adding a *value*
  under an existing class is free. This is what stops the schema being re-fitted every engagement.
- **A vendor entry with `seen_in_engagements: 0` is a stub**, may carry a fingerprint and
  `known_secure_defaults`, and **may not carry `seed_hypotheses`** — because seed hypotheses are the
  part that is fiction when written from no evidence. `firebase` and `postgrest` above are stubs and
  are labelled as such in the index.
- **§8.4's acceptance test is the gate.** Dispatch may not be described as working until an
  engagement with zero matches produces full generic coverage.

### 8.6 What it costs to build now

| Piece | Cost | Notes |
|---|---|---|
| `index.yaml` parser + matcher | Small | ~150 lines; `any_of`/`all_of` over a closed signal vocabulary, no regex engine, no scoring |
| `fingerprint.json` from `rg-surface` | **The real cost** | `rg-surface` must emit structured, evidence-pointed signals instead of prose. This is a genuine change to an existing agent card and its output contract |
| `_generic/` families G1–G7 as parameterised checks | **The other real cost** | This is the work the v1 cut deferred by hardcoding. It is not new work created by dispatch; it is work dispatch stops us from skipping |
| Evals per entry (`09-playbooks.md` §11.6) | Moderate | Three should-trigger, three should-not-trigger per entry. **The should-not-trigger cases are the ones that catch an over-broad fingerprint**, which is the main risk of building early, so these are not optional |
| Ongoing discipline | Small but permanent | Every check written twice-abstracted: family definition plus vendor parameters |

**Net judgement:** the matcher is cheap, the generic families are expensive, and the generic families
are required by §7 regardless of whether dispatch exists. So the marginal cost of building dispatch
now is the index parser, the fingerprint contract and the evals — and the marginal saving is not
having to port a hardcoded Supabase implementation into a generic one later, with a live client
corpus already scored against the old shape. Build it now.

---

## 9. The false-positive budget

### 9.1 The problem, stated without the number

An unscoped nuclei run is noisy. The prior research attaches an anecdotal figure to that claim.
**That figure is not quoted here, is not a design input, and may never reach a client** — hard rule 2,
and §20.5's never-say list. What *is* a design input is the structural consequence, which needs no
number at all:

> RG-1 forces every above-`low` technical finding through independent verification. RG-3 holds every
> scanner finding at `low`. So a noisy profile does not produce false client-facing findings — it
> produces an unbounded **verification queue**, and `rg-verify` becomes the bottleneck. The failure
> mode of a noisy profile in this framework is cost and delay, not misinformation.

That is a much better failure mode than the usual one, and it is worth noticing that the ceiling
bought it. But an engagement that spends its whole budget triaging exposure templates has still
failed, so the profile must be narrow.

### 9.2 Four mechanisms that keep a profile narrow

1. **Selection is an allowlist, never `-t` at the corpus root.** Every profile names specific
   template paths and tags. There is no "run everything and filter later" mode, because filtering
   later is a decision nobody records.
2. **`max_templates` is a hard build failure.** Selection expands at pin time into
   `profiles/<name>.resolved.json` with a concrete count. Exceeding `max_templates` fails
   `resolve_profile.py`. This converts "narrow" from an intention into a number a reviewer can read
   in a diff, and it means an upstream bump that quietly adds 300 templates under a selected tag
   breaks the build instead of the engagement.
3. **Protocol and tag exclusions applied twice** — once in the corpus selection, once as a runtime
   filter the adapter enforces. `code`, `flow`, `headless`, `javascript`, `network`, `dos`,
   `bruteforce`, `intrusive`, `oast`.
4. **Upstream's own ignore list is honoured and extended, never overridden.** `.nuclei-ignore` at
   `v10.4.7` default-excludes the tags `dos`, `local`, `fuzz`, `bruteforce`, `txt-service` plus a
   named file list including `dast/vulnerabilities/sqli/time-based-sqli.yaml`. Upstream has more
   evidence about its own templates than we do.

### 9.3 Measuring it, so it eventually becomes evidence

One new ledger, `ledger/scanner_outcomes.jsonl`, one row per emitted scanner finding:

```json
{"profile": "web-baseline-v1", "profile_version": 1, "component": "nuclei",
 "template_id": "apache-config-file", "selector": "http/exposures",
 "finding_id": "F-031", "engagement": "<id>",
 "verdict": "REJECTED", "verdict_source": "findings/review.jsonl", "at": "..."}
```

`verdict` is `VALIDATED` / `REJECTED` / `not_reviewed`, taken from `rg-verify`'s `review.jsonl` row
(RG-1 §7.3) — never written by the producing agent, which would be the self-certification failure
RG-1 §4.5 exists to stop.

```
fp_rate(profile_version, template_id) = REJECTED / (VALIDATED + REJECTED)
```

Four rules on that number, all of which exist because P9 applies to numbers that flatter us:

- **The denominator is always reported with the rate.** A template with n=1 has an outcome, not a
  rate, and is displayed as `1 rejected / 1 reviewed`, never as `100%`.
- **`not_reviewed` is excluded from the denominator and reported separately**, because a large
  `not_reviewed` count means the queue is the bottleneck and the rate is measured on a biased sample
  — the reviewed ones are the ones that looked interesting.
- **Rates are keyed by `profile_version`.** A pin bump resets the series; the old series is retained
  and labelled, not merged.
- **The rate is internal until it has a real denominator.** It may inform retirement decisions
  immediately. It may not appear in a client report or a marketing claim until the operator signs off
  on a specific denominator, and it may never be generalised beyond the profile version it was
  measured on.

### 9.4 Retirement and promotion — one bar, both directions

Same ≥3-across-≥2 bar as RG-1 §7.5 and §7.5 above:

| Direction | Trigger | Action, at the next pin bump |
|---|---|---|
| **Retire** | A `template_id` with ≥3 `REJECTED` and 0 `VALIDATED` across ≥2 engagements | Added to the profile's `exclude_template_ids` with its three citations, in the `CHANGELOG.md` entry. Reversible; the citations are what make reversing it a decision rather than a whim |
| **Promote** | A `template_id` with ≥3 `VALIDATED` and 0 `REJECTED` across ≥2 engagements | Becomes a candidate for a hand-written tier-2 `grants` row (§4.3) plus a committed fixture, letting findings from it exceed the ceiling once `rg-verify` confirms. Written by the operator, never generated |
| **Neither** | Everything else | Stays where it is. Most templates will live here forever and that is correct |

The promotion path is what keeps §4's ceiling from being a permanent product cap. It is also
deliberately slow: a hand-written `grants` row is a claim about what an attacker gains, and RG-1 §10.3
is right that such claims need evidence rather than throughput.

**Bounding the promotion list is itself a control.** The framework may hold at most a small,
reviewable number of promoted templates — recommend **25** as the initial cap, an operator decision
(D-16). The moment that list is unbounded, we have rebuilt the per-template annotation table §4.1
rejected, one row at a time, and nobody will notice the moment it happens.

---

## 10. Build order and dependencies on RG-1

### 10.1 What blocks on RG-1, and what does not

| RG-3 item | Blocked on | Why |
|---|---|---|
| Profile format, `pins.lock.yaml`, `resolve_profile.py`, `verify_pins.py` | **Nothing** | Pure new files. Can be built today, against the current schema, and are prerequisites for everything else |
| `assets/surface.jsonl` + `SURFACE_UNDISPOSED` | **Nothing** | New artifact, new validator code. Does not touch the finding schema |
| `playbooks/index.yaml` + dispatch + `_generic/` families | `rg-surface` structured output (RG-3-internal, not RG-1) | The generic families produce coverage records, which sit better after RG-1 §8.1's coverage register but do not require it |
| gitleaks + trufflehog adapters | **Nothing structural**; benefits from RG-1 E1 | Secret findings sit at the ceiling, so they never need `grants`. `environment_at_test` is an RG-1 E1 field and should be stamped, but its absence does not block the adapter |
| nuclei adapter (non-fuzz) | **RG-1 E3** — hard | Until E3 lands, `baseline_scan.py` writes `verified: "executed"` on its own output and `UNVERIFIED_ABOVE_LOW` is structurally unreachable. If the nuclei adapter follows that precedent, **scanner findings escape the ceiling**, and §4's entire argument collapses. E3 is the load-bearing dependency of this document |
| Profile stamp on findings (§3.5) | RG-1 E1 (schema additions) | Additive; land it in the same commit as E1's other new fields to avoid two schema migrations |
| Fuzzing (§5) | `assets/surface.jsonl` — hard | **No fuzzing before the discovery sink exists.** Running a fuzzer with nowhere to put discoveries is the exact waste the operator objected to, and doing it in that order would produce one engagement's worth of discarded discovery that cannot be recovered |
| `scanner_outcomes.jsonl` + FP measurement | **RG-1 E4** (`review.jsonl` + `merge_review.py`) | Verdicts come from the review file. Without E4 there is no verdict to record and the ledger would hold only `not_reviewed` |
| Tier-2 grants promotion (§9.4) | RG-1 E4 **and** ≥2 engagements of data | Evidence-gated by construction |
| `no_handrolled_loops.py` sanctioned-wrapper change (§5.5) | RG-2 | Hook change; belongs with the enforcement work, not here |

### 10.2 The order

**S0 — Foundations. No dependencies. Build first.**
`profiles/` directory, `pins.lock.yaml`, the profile schema and its validator, `resolve_profile.py`,
`verify_pins.py` (V3 and V4 first, then V1/V2/V5), and the committed fixtures for testssl.sh's
undocumented JSON and for gitleaks' report shape. *Acceptance:* `verify_pins.py` refuses a run whose
template tree hash does not match `resolved.json`, proven by a test that passes `-td` instead of `-t`
and asserts a refusal. **That test is the whole point of S0.**

**S1 — The discovery sink.**
`assets/surface.jsonl`, its writer, `SURFACE_UNPLANNED`, `SURFACE_UNDISPOSED`, and the
`gate_cli.py complete --phase` refusal. *Acceptance:* a phase with an undispositioned surface row
cannot be completed.

**S2 — nuclei adapter, deterministic corpus only.** *Requires RG-1 E3.*
`web-baseline-v1`, ceiling-capped records, `scanner_claim`, `PROFILE_UNSTAMPED`,
`SEVERITY_FROM_TEMPLATE`. *Acceptance:* a nuclei template declaring `critical` produces a `low`
finding, and the injected fault "ceiling removed" turns a test red.

**S3 — Secret scanning.**
`scripts/secret_scan.py`, both binaries pinned by `file_digest`, `--no-verification` hard-wired,
gitleaks `--redact`, span-based redaction at the source, dedup by value fingerprint.
*Acceptance:* a fixture repo containing a known key produces one finding from two tools, with no
plaintext value anywhere in `findings/`, `evidence/` or stdout.

**S4 — Dispatch and the generic families.**
`playbooks/index.yaml`, the matcher, `rg-surface`'s `fingerprint.json` contract, `_generic/` G1–G7,
`backends/supabase` as a parameter set, `firebase`/`postgrest` as stubs, evals.
*Acceptance:* §8.4 — an engagement matching zero vendor entries still produces a complete coverage
record set.

**S5 — Fuzzing.** *Requires S1 and S2.*
`web-fuzz-v1`, the `fuzzing` block, scope-regex generation from the boundary, budget assertion,
`FUZZ_BUDGET_EXCEEDED`, discovery rows into `surface.jsonl`.
*Acceptance:* a fuzz run against a local fixture writes surface rows for paths no matcher fired on,
and a run that exceeds its declared budget raises the violation.

**S6 — Measurement.** *Requires S2 and RG-1 E4.*
`ledger/scanner_outcomes.jsonl`, the rate calculation with its denominator discipline, the retirement
rule.

**S7 — Promotion.** *Requires S6 plus two engagements of data.* The tier-2 grants list, capped.

### 10.3 Injected faults

Per RG-1 §9's rule that a new control without an injected fault grows the test count without growing
discrimination. Eight, one per control that can fail silently:

| Control | Injected fault | Module |
|---|---|---|
| §1.5 pin verification (V3) | tree-hash comparison → `if False:` | `tests.test_verify_pins` |
| §1.5 pin verification (V4) | template-id subset assertion → `if False:` | `tests.test_verify_pins` |
| §4 ceiling | `severity = profile.ceiling` → `severity = scanner_claim.claimed_severity` | `tests.test_profile_adapter` |
| §2.4 empty selector | zero-resolution build failure → warning | `tests.test_profile_resolution` |
| §2.5 rate ceiling | `min(profile, scope)` → `profile` | `tests.test_scan_run` |
| §5.4 budget assertion | post-run count comparison → `if False:` | `tests.test_fuzz_budget` |
| §5.7.4 disposition gate | `SURFACE_UNDISPOSED` refusal → `if False:` | `tests.test_gate_cli` |
| §6.2 verification default | `--no-verification` dropped from the argv builder | `tests.test_secret_scan` |

---

## 11. What this does NOT do

Written in the style of RG-1 §10. Do not describe any of the following as working.

1. **The request budget is not enforced.** §5.4. It is asserted after the fact. The only real
   in-band bound on a fuzz run is `rate_limit × wall_clock`, and that is the number the report must
   state. `FUZZ_BUDGET_EXCEEDED` tells you it happened; it does not stop it happening.
2. **`no_handrolled_loops.py` does not see nuclei.** §5.5. A single command line that dispatches
   fifteen hundred requests passes the hook because there is no shell loop in it. The hook's coverage
   of composed tools is a gap, and closing it is RG-2.
3. **Scanner output cannot exceed `low`.** §4. Inherited from RG-1 D-2 and reaffirmed. A live RCE
   found by a pinned template is reported as `low` until a human or `rg-verify` re-executes it. This
   is a product statement the operator signs, not an accident.
4. **`grants` is unsolved, not solved.** §4.2 shows the requirement is never *reached* for
   ceiling-held records. If the operator ever relaxes the ceiling, the unbounded-table problem
   returns intact and this document does not answer it.
5. **Fuzzing outputs are not reproducible** and the report must say so in the words of §5.6. Whether
   the *inputs* are reproducible is `[VERIFY]` pending a two-run diff against a fixture.
6. **Verification of a live credential is not performed** by default and, per §6.2, cannot be
   performed correctly on a properly egress-filtered host without a deliberate allowance. Any report
   sentence about a credential's liveness where verification was off is a fabrication.
7. **`redact.py` covers roughly fifteen credential formats; trufflehog models over eight hundred.**
   §6.5. Span-based redaction in the wrapper closes this for the scanner path only. Any *other* tool
   whose output contains an exotic credential format still leaks it into the transcript.
8. **Several digests in §2.7's worked example are `[VERIFY]`** — the nuclei and testssl image
   digests and the two release-tarball checksums were not resolved in this session. The example is
   structurally complete and cryptographically incomplete; resolve them at pin time, do not copy them
   forward as if resolved.
9. **`nmap`'s pin is a version string** and cannot be strengthened without building our own image.
   §1.2. Two runs six months apart are not provably identical.
10. **`profiles/`, `assets/surface.jsonl`, `playbooks/index.yaml` and `_generic/` do not exist.**
    `playbooks/` currently contains one file. Nothing in this document is built.
11. **None of this is a security boundary.** `scope_guard.py` remains defence-in-depth and the
    off-host egress filter still does not exist. A fuzzer is the component in this framework with the
    largest blast radius, and its containment rests on a filter that has not been built.

---

## 12. Open decisions for the operator

Continuing RG-1's D-numbering.

| # | Decision | Recommendation |
|---|---|---|
| **D-11** | Does fuzzing ship at all before the off-host egress filter exists? | **Yes, at tier 2, read-methods only, against a single named target per invocation, with the rate ceiling from `scope.yaml`.** The blast radius of GET-only fuzzing at 5 req/s against one in-boundary host is comparable to the baseline scan's. But record it as the largest un-contained component in the framework, and do not extend it to write methods until the filter exists |
| **D-12** | Is `requests_per_target` acceptable as a post-hoc detection rather than a control? | **Yes, with the report stating the real ceiling as `rate × wall_clock`.** The alternative — wrapping nuclei in a request-counting proxy — is a substantial build for a bound the rate limit already provides loosely |
| **D-13** | Does trufflehog verification ever get enabled? | **Not by default, and not without a `scope.yaml` key naming the providers plus an egress allowance.** §6.2's four arguments. The default remediation "treat it as live and rotate it" costs the client nothing |
| **D-14** | Is AGPL-3.0 acceptable for trufflehog given RedGold's commercial shape? | **Yes for process invocation, unmodified** — the same reasoning that cleared nmap's NPSL. **`[VERIFY]` before any packaging that bundles it or offers it over a network**, where AGPL §13 is materially different from GPL. Do not rely on this row without reading the licence text |
| **D-15** | Build dispatch now, per the operator's direction? | **Yes**, with §8.5's three mitigations as hard bars — closed signal vocabulary, stubs may not carry seed hypotheses, and §8.4's zero-match acceptance test gates the claim that dispatch works |
| **D-16** | Cap on the tier-2 promoted-template list? | **25.** Unbounded promotion rebuilds the per-template table §4.1 rejected, one reviewed row at a time, and the moment it happens is invisible without a cap |
| **D-17** | Does `web-baseline-v1` become the default for every engagement, replacing bare `baseline_scan.py`? | **Not yet.** `baseline_scan.py` runs before any fingerprint is known and is P10's guarantee. Make it `components[0]` of the profile (as in §2.7) and keep it independently runnable, so a profile failure cannot take the baseline down with it |

---
