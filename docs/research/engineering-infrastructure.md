---
title: Engineering infrastructure — what this repo needs, what it would benefit from, what it should refuse
date: 2026-08-20
status: draft
question: >
  All testing here is hand-rolled and there is no CI, no linter, no type checker, no coverage and
  no config file of any kind. Is this an experiment or production software, and what standard
  tooling does it actually need — as distinct from what it would merely benefit from?
---

# Engineering infrastructure

**Method.** Every claim about what a tool would or would not have caught was tested, not assumed.
`ruff` 0.16.3 was installed into a throwaway venv outside the repo and run over `scripts/` and
`tests/` at several rule strengths; the results are quoted below. Every version and action ref was
read from a primary source (GitHub Releases API, PyPI JSON API, the action's own `action.yml`) on
2026-08-20 — none is from memory. Nothing in the repo was modified except this file.

---

## 1. Verdict — experiment or production software?

**Neither, and the mismatch is the interesting part. This is a research prototype with
production-grade epistemics and prototype-grade reproducibility.**

The discipline here is genuinely better than most funded engineering teams manage: a fault-injection
harness that asserts the suite goes *red*, four adversarial review rounds that found 21 defects the
self-written suite missed, a fifth that found 12 more, a written convention that a caught mutation
is not proof of a correct control, and a `status.md` section headed "NOT enforced — do not describe
these as working". That is not vibe coding. Vibe coding does not produce
`docs/research/test-suite-review-2026-08-20.md`, whose verdict on its own project is "564 tests is
not 564 tests' worth of assurance, and the operator's prior is correct".

What is missing is not quality. It is **reproducibility by anyone other than this operator on this
machine.** Concretely, right now:

- `status.md` line 26 asserts **"564 tests, 18 skipped, exit 0. 45/45 fault injection, exit 0.
  Measured 2026-08-20."** Measured just now against `HEAD`: **605 passed, 18 skipped, 12.9s** and
  **60/60 fault injection, exit 0, 2m33s**. The authoritative file was stale within hours of being
  written, because the number is produced by an operator remembering to run a command and
  remembering to transcribe the result.
- `rg1-code-review-2026-08-20.md` §"Working tree is red" documents the sharper version: the review
  had to `git archive` five separate commits into a scratchpad and run the suite against each, by
  hand, to establish which tree the "all green" claim referred to. Its closing procedural point is
  *"any claim of 'all green' must name which tree it means."* Nothing in the repo names the tree.
- `docs/specs/redgold/07-enforcement.md` §9.1 specifies a CI check and argues for it explicitly:
  *"Convention would not survive a tired operator adding an agent at 11pm."* The **check was
  built** — `scripts/validate_agents.py`, with tests in `tests/test_agents.py`. The **CI was not**.
  So the argument for machine-checking-at-PR-time was accepted, implemented, and then left
  depending on convention anyway.

That last one is the whole diagnosis in one artifact, and CLAUDE.md already contains the rule it
violates — design judgement 4: **"A control nobody is forced to run is not a control. If it depends
on being remembered, it will be forgotten."** `verify_controls.py` is, today, exactly such a
control. It is the best thing in this repository and nothing forces it to run.

**So the answer to the operator's question is: the code is being *reviewed* like production
software and *run* like a lab notebook.** The gap that matters is not a missing linter. It is that
the project's honesty conventions — which are its actual product differentiator — are enforced by
operator memory, and CLAUDE.md's own design judgements say that is not enforcement.

**One further consequence, since the code is security-critical and the repo is public:** a reader
who clones `github.com/GriffynHancock/RedGold` today has no way to confirm any claim in `status.md`
without setting up an environment and running it. For a tool whose pitch is calibrated honesty
about what it can and cannot prove, an unverifiable green badge is worse than a bad one — and a
verifiable one is free, because Actions is free on public repositories.

---

## 2. NEEDS — without this, correctness or a client is at real risk

Four items. Each names a defect or documented incident it would have caught. Anything I could not
attach to a real event is in §3 instead, however sensible it sounds.

### N1. CI that runs the existing checks on the committed tree, on every push

The whole of it: `pytest`, `scripts/validate_agents.py`, `scripts/verify_controls.py`. All three
already exist. The missing piece is a runner that executes them against a named commit rather than
against whatever happens to be in the operator's working directory.

**What it would have caught:**

- **The "working tree is red" state note** (`rg1-code-review-2026-08-20.md`, §State note).
  `status.md` claimed "all green" while `/usr/bin/python3 -m pytest tests/ -q` in the working tree
  returned `18 failed, 545 passed, 18 skipped`. CI reports per-commit, so the claim and the tree it
  refers to cannot drift apart. The red was legitimate (TDD red-phase tests for RG-2 §5), which is
  the point: CI distinguishes *a legitimately red working tree* from *a broken commit*, and the
  operator currently cannot, without hand-archiving five commits.
- **The stale count in `status.md` right now** — 564 asserted, 605 actual, 45/45 asserted, 60/60
  actual. Under CI the number is read off a run, not off a memory.
- **`verify_controls.py`'s `SKIP` path.** When a mutation site no longer exists in the source, the
  harness prints *"the code moved and this check is now vacuous"* and counts the mutation as
  undetected. That failure fires precisely when someone edits a control — i.e. on the commit that
  edits it. Today nothing runs it on that commit. This is the strongest single argument in the
  whole document, because it is a control that silently becomes vacuous, which is judgement 2's
  "a gate that never fires is worse than a wrong one, because it reads as coverage".
- **§9.1's own stated failure mode.** `validate_agents.py` enforces that any `Bash`-capable agent
  card carries `RG-SCOPE-GUARDED`, that `tools:` is set explicitly (an unset `tools:` grants
  everything), and that at most one card uses `opus`. The spec's justification is the tired
  operator at 11pm. A tired operator at 11pm also does not run `validate_agents.py`.

Runtime is not an obstacle: the suite is **12.9 seconds** and the fault injection is **2m33s**.
Both belong on every push. See §6 for why the mutation job should not be moved to a nightly
schedule.

### N2. A "name a producer" check — every closed vocabulary must have an emitter

A test that asserts each producer-keyed constant is actually emitted by some non-test file in the
repo. Roughly: for `CODE_DEFECT_PRODUCERS`, grep `agents/`, `commands/`, `templates/` and
`scripts/` for a writer of `discovered_by` with a value in the set, and fail if there is none.

**What it would have caught: S6 and S12, directly.**

- **S6 (medium):** `CODE_DEFECT_PRODUCERS = frozenset({"rg-codeaudit"})` gates the whole
  `code_defect` default-on path, and **nothing in the repository produces that value**. The only
  producer that writes findings records, `baseline_scan.py:377`, writes `"baseline_scan"`. The
  review's phrasing: *"Name a state at which the `code_defect` default fires: with the repo as it
  stands, none."* Every test supplied `discovered_by` itself, so the tests proved the constant
  works on input no producer generates.
- **S12 (low):** `in_phase` counts any artifact declaring no `phase` toward whichever phase is
  being closed — and **no producer writes `phase`**, making `complete --phase` near-unfalsifiable
  for every phase name including ones that do not exist.

This is not an off-the-shelf tool, and that is the honest finding: **the highest-value check
available to this repo is not something you can `pip install`.** It is roughly forty lines of
pytest, and it mechanises the review's own recommendation — *"Grepping this codebase for claims in
prose and checking each against the five lines beneath it is a high-yield pass on its own."*

### N3. An anonymisation check over the diff — repo-specific denylist, not a secret scanner

`.gitignore` records an incident in its comments: an unanchored `*-verification.md` glob made a
real spec file invisible to working-tree greps, *"and that is how a client name once survived into
a commit undetected, caught only by a git-history check."* `status.md`'s PUBLIC section makes this
a standing constraint on every session: no target hostname, tailnet, IP, container name, database
name, repo URL or absolute home path may reach this repo.

**What it would have caught: the client name that reached a commit** — the one documented incident
of the repo's hard rule 3 actually failing.

**Note carefully what would *not* have caught it.** `gitleaks` and `trufflehog` detect
credential-shaped strings: API keys, tokens, private keys, high-entropy blobs. A client's company
name is none of those. Neither is a tailnet hostname or `/home/hiranya/...`. The standard secret
scanner has a **zero** hit rate on the only leak this repo has ever had. What is needed is a
project-specific check — a denylist file kept outside the repo, or a grep for `/home/[a-z]*/`,
bare IPs, and `.ts.net`/`.local` suffixes across the diff. This is the discrimination test doing
real work: the famous tool fails it and the boring custom one passes.

An adjacent grep is cheap and worth folding in: the same job should fail on an absolute home path
anywhere in a tracked file. `scripts/verify_controls.py` currently hardcodes `/usr/bin/python3`
(fine — that is a system path, not a home path), but review scratchpad paths of the form
`/tmp/claude-1000/-home-hiranya-RedGold/...` already appear in `docs/research/`, and one of those
is a home directory name spelled out in a public repository.

### N4. A declared, pinned interpreter — because the default one is already wrong

`python3` on this machine is **linuxbrew Python 3.14.3 without PyYAML**. `/usr/bin/python3` is
**Python 3.13.12 with PyYAML 6.0.3**. This is not two module sets on one interpreter; it is two
different Python versions, and the wrong one is first on `PATH`.

`scripts/new_engagement.py:70-94` already treats this as a hazard worth a control:
`verify_interpreter` refuses a relative path and refuses an interpreter that cannot
`import yaml`, with the reasoning written out — *"a hook that dies on import fails OPEN."* There is
a fault injection for it (`"scaffolder skips interpreter verification"`). `verify_controls.py`
hardcodes `PYTHON = "/usr/bin/python3"` for the same reason.

**What it would have caught:** the fail-open hook hazard is identified and controlled at the
`/rg:new` boundary, so I will not claim it has bitten in production. What it *has* already caused
is narrower and real: **the entire 605-test suite has only ever been executed under one
interpreter, on one machine, and Python 3.14 is already the default there.** The suite has no
recorded evidence it runs under the interpreter a fresh `python3` invocation would select. That is
a reproducibility defect in the same family as N1, not a hypothetical.

The consequence for CI is concrete and easy to get wrong — see §6. On `ubuntu-24.04` runners
`/usr/bin/python3` is **3.12.3** and PyYAML is **not** listed among preinstalled packages
([actions/runner-images](https://github.com/actions/runner-images) Ubuntu2404 README, read
2026-08-20). So a workflow that copies the repo's convention and invokes `/usr/bin/python3` would
run an older Python without PyYAML, and `scope.py`'s lazy `import yaml` would fail at a different
point than it does locally. The workflow must parameterise the interpreter, not inherit the
convention.

---

## 3. BENEFITS — genuinely useful, not load-bearing

Ordered by value per unit of maintenance. None of these can be attached to a defect that actually
happened, which is why they are here and not in §2.

**B1. `ruff check --select E9,F` — syntax errors and undefined/unused names.** Zero config, sub-
second, effectively zero maintenance. Measured against the current tree at `E9,F` it finds
**exactly three things**, all unused imports (`json` in `report.py:32`, `findings` in
`test_audit_regressions.py:28`, `tempfile` in `test_regen_scripts_readme.py:12`); under §6.1's
tuned config it finds **exactly one**, `json` in `report.py:32`, auto-fixable — so the PR that adds
the config is green after a one-line deletion. The value is not those three; it is that
`F821 undefined-name` catches a typo'd variable in an error path no test exercises — which in this
codebase means a fail-open branch that raises `NameError` instead of denying. Cheap insurance,
honestly labelled as insurance.

**B2. `ruff format --check`, or better, `ruff check --select E501` only.** The repo has a
consistent hand style at ~100 columns and 2204 `E501` hits at ruff's default 88. Pin
`line-length = 100` and the number drops to near zero. See §4 for why the *formatter* is a bad
idea and the *line-length check* is a fine one.

**B3. Running the suite under a second interpreter (3.14) in CI.** A matrix leg costs one line and
proves the claim N4 says is currently unproven. It is a benefit rather than a need because nothing
has broken yet.

**B4. `ruff check --select B` (bugbear).** Two hits, both `B007 unused-loop-control-variable`.
Low yield here, but `B008`/`B006` (mutable default arguments, function calls in defaults) are the
class of latent bug that survives review and that this codebase's dataclass-and-dict style could
plausibly grow.

**B5. `shellcheck` on `scripts/rate_probe.sh`.** One file, 8KB. It is the script that owns the
rate-limit counter after the prior engagement's 20-requests-against-a-10-cap incident, so it is
worth being correct — but §9.1's "shellchecks every script" is, at n=1 script, a very small job.
`shellcheck` is not installed locally, so I could not measure its yield and will not guess at it.
Free to add in CI (`ubuntu-24.04` ships it), so add it; just do not expect it to find the next S1.

**B6. `zizmor` 1.29.0 — a linter for GitHub Actions workflows themselves.** Only meaningful once
§6's workflow exists. It catches the workflow-specific footguns (over-broad `permissions`,
injectable `${{ }}` into `run:` blocks) that a security tool's own CI should not have. Add it in
the second PR, not the first.

**B7. `mutmut` on the pure-logic functions.** See §5.

---

## 4. What to actively NOT adopt

**`mypy` — no.** The discriminating question is what it would have caught, and the answer is
nothing. Every one of the 12 defects is a semantic defect in fully-typed-compatible code: S1 reads
a `str` from the wrong place, S4 has one `elif` too few, S2 orders two correct operations wrongly.
The one defect that is nearly type-shaped is **S8 case D**, where `checks_skipped = True` (a JSON
bool) passes `isinstance(count, int)` — and mypy would *approve* that, because `bool` is a subtype
of `int`. The codebase is stdlib-only, has no public API, no consumers importing it, and parses
untyped JSON and YAML at every boundary, which is precisely the shape where mypy degenerates into
`Any` propagation and `# type: ignore`. Cost: real. Yield against measured evidence: zero. **Not
worth it.**

**Coverage measurement as a gate — no.** This is judgement 7's trap wearing a percentage sign.
`test_suite-review-2026-08-20.md` already establishes that this suite has **76% fine-grained
mutation score with 32 survivors clustered on band boundaries** — while line coverage of those same
functions is presumably near total, because the tests execute the lines and merely fail to assert
about them. `test_recorded_negatives_alone_satisfy_the_coverage_half` (S3) has 100% coverage of the
hole it enshrines. Adding a coverage number creates a second, worse, "number goes up" metric
alongside the test count the operator is already correctly suspicious of, and it would have caught
none of the 12. **If you want a number, the mutation score is the honest one and you already have
it.** Running `coverage` occasionally, by hand, to find *entirely unexecuted* files is a fine
one-off diagnostic; wiring it to a threshold in CI is not.

**`pre-commit` — no.** Judgement 4 cuts both ways. A solo operator will hit a
pre-commit hook that reformats mid-thought and will type `--no-verify`, and after the third time
that becomes reflex, at which point the hook is a control that does not run *and* reads as
coverage. Worse, this repo's whole containment thesis is that local, in-reach enforcement is not a
boundary — an agent with write access to the tree can edit `.pre-commit-config.yaml` as easily as
it can edit `scope_guard.py`. CI on a different machine is the same argument as off-host egress
filtering, one tier down. **Put the checks where the operator cannot skip them and the agent cannot
reach them.**

**`ruff format` (or `black`) — no, not now.** Zero other contributors means zero diff-noise
arguments to settle, which is the formatter's actual value proposition. What it would cost is a
several-thousand-line reformat commit that invalidates every line number in
`rg1-code-review-2026-08-20.md`, `test-suite-review-2026-08-20.md`, the spec's file:line citations,
and — critically — **every one of `verify_controls.py`'s 60 mutations**, which match on exact source
strings and would all silently flip to `SKIP` ("the code moved and this check is now vacuous"). A
formatter would take the repo's best control to 0/60 in a single commit. Revisit if a second
contributor ever appears; until then take B2's line-length check and nothing else.

**`bandit` as a separate tool — no.** `ruff`'s `S` ruleset is a port of bandit's checks and is
already in the tool you are adding for B1. Running measured: **8 hits across `scripts/`, all of
them expected and correct** — `S603 subprocess-without-shell-equals-true` ×3 on deliberate
argv-list calls, `S310 suspicious-url-open-usage` ×2 in `baseline_scan.py:64,66` where making HTTP
requests is the entire job, `S607`, `S101`, and one `S608 hardcoded-sql-expression` at
`report.py:509` which is the cleanup-appendix query template handed to the client. A second tool
producing the same eight false positives is pure maintenance.

**Dependency scanning / Dependabot / SBOM — moot, say so plainly.** Every import across `scripts/`
and `tests/` was enumerated: `argparse base64 binascii collections contextlib dataclasses datetime
hashlib http importlib io ipaddress json os pathlib re shlex shutil socketserver subprocess sys
tempfile threading time typing unittest urllib` — all stdlib — plus local modules, plus **one**
third-party package, PyYAML, imported lazily inside a function at `scope.py:48`. There is no
`requirements.txt` to scan and one line to audit. Dependabot's `github-actions` ecosystem (keeping
pinned action SHAs fresh) is worth enabling once §6's workflow exists; the `pip` ecosystem has
nothing to do.

**SLSA / provenance attestation — no.** Provenance answers "was this artifact built from this
source by this builder". RedGold ships as **files in a git repo installed as a Claude Code plugin**.
There is no build step, no wheel, no release artifact, and therefore no gap between source and
artifact for provenance to close. Signed tags would be a reasonable gesture if the plugin ever gets
a versioned release; today it would be ceremony over a `git clone`.

---

## 5. `verify_controls.py` versus `mutmut` / `cosmic-ray`

**Judgement: keep `verify_controls.py`, and add `mutmut` for a different job. They are
complementary, and the review evidence says exactly where the seam is.**

They are not the same instrument:

| | `verify_controls.py` | `mutmut` 3.7.0 / `cosmic-ray` 8.7.0 |
|---|---|---|
| Mutation selection | 60 **hand-authored, named** faults | exhaustive **mechanical** operators over the AST |
| Granularity | coarse — `if X:` → `if False:`, whole-function short-circuits | fine — `>` → `>=`, `+1` → `-1`, constant perturbation |
| Failure it reports | *"the undeletable-rows incident is no longer caught"* | *"mutant 412 in findings.py survived"* |
| Failure when code moves | `SKIP` — loudly announces itself vacuous | silently re-derives new mutants |
| Runtime | 2m33s, whole repo | hours if unscoped |

**The case for keeping the hand-rolled one is not sentiment; it is the `breaks` field.** Each
`Mutation` carries a plain-English statement of *which real-world incident stops being caught* —
`"the 20-vs-10 request overrun"`, `"the undeletable-rows incident"`, `"shell injection via an
engagement path or interpreter containing a quote"`, `"silent subagent nesting"`. That is a
traceability matrix from the prior engagement's actual failures to the tests that prevent their
recurrence, and no mechanical mutation tool can produce it, because the mapping from `line 412` to
`the prior engagement left 15 undeletable rows in a live client database` does not exist in the
source. A `mutmut` report telling you 3 mutants survived in `canary_check.py` does not tell you
that write authorisation is now unenforced. **`verify_controls.py` is a specification of what must
not regress, disguised as a test harness.** Deleting it in favour of a standard tool would trade
that specification for a percentage.

**The case for adding `mutmut` is equally evidenced, and it is the boundary problem.**
`test-suite-review-2026-08-20.md` measured it directly: **136 hand-written fine-grained mutations,
32 survivors**, clustered on band boundaries, closed-vocabulary membership, and fail-closed
defaults — while `verify_controls.py` scored 45/45 (now 60/60) on coarse ones. Its most compact
finding: *"`MAX_URLS_PER_COMMAND` can be 2, 3 or 4 — and `>` can become `>=` — and all 564 tests
pass."* And the code review's S2 is the same hole realised as a real critical defect: *"every
fault-injection mutation passes and the control is still wrong at the boundary."* S8 names the
mechanism outright — *"the `verify_controls.py` mutation for this area rewrites `checks_skipped` to
`1` — it perturbs the value, never the filter."*

Those 136 mutations were written by hand, by an agent, once. **That is precisely the job to hand to
a mechanical tool**, because comparison-operator flips and off-by-one perturbations are what
`mutmut`'s operator set generates for free, exhaustively, without anyone having to think of them.

**How to add it without it becoming a chore.** Do not run `mutmut` over the repo — scope it to the
pure-logic functions where mutation is cheap and meaningful: `findings.apply_environment_cap` and
its rank/vocabulary helpers, `scope.parse`'s ceiling rules, `gate_cli.phase_evidence`,
`report.classify`. Run it **on demand and on a schedule, never on push** (it is minutes-to-hours,
and unlike `verify_controls.py` a surviving mutant is usually a *question*, not a failure). Treat
the survivor list as a review queue, not a gate — a `mutmut` score wired to a threshold recreates
exactly the coverage-percentage problem §4 rejects.

`cosmic-ray` over `mutmut`: no strong preference, but `mutmut` 3.7.0 is the lighter setup and this
is a `unittest`-style suite run through pytest, which both support. Start with `mutmut`; it is a
one-afternoon experiment, and if the survivor list is not interesting, drop it and lose nothing.

**Summary in one line:** `verify_controls.py` answers *"is this named control still enforced?"* and
must stay on every push; `mutmut` answers *"do the tests know where the boundaries are?"* and
belongs in a periodic review queue. The evidence says the repo needs both answers and currently
gets only the first.

---

## 6. Concrete first step — one PR

**Scope:** add CI. Do not add mypy, coverage, pre-commit, a formatter, or any appsec scanner. Wire
up the three checks that already exist, plus `ruff` at its cheapest setting, and fix the one
interpreter assumption that would make the workflow lie.

Four files, plus one three-line source change.

### 6.1 `pyproject.toml` (new)

The repo has no packaging story and should not acquire one — this file exists **only** as a config
holder for `ruff` and `pytest`, so both behave identically in CI and locally. There is no
`[project]` table on purpose: adding one implies a distributable package, and this is a plugin
distributed as files.

```toml
# pyproject.toml — tool configuration only.
#
# There is deliberately NO [project] table. RedGold is a Claude Code plugin distributed as files
# in a git repo, not a package: no build step, no wheel, no install. This file exists so that ruff
# and pytest read the same settings in CI as on the operator's machine, and for no other reason.
#
# Runtime dependency surface, in full: PyYAML, imported lazily at scripts/scope.py:48.
# Everything else in scripts/ and tests/ is the standard library. Do not add a dependency here
# without a reason that survives that sentence.

[tool.ruff]
line-length = 100          # the repo's existing hand style; ruff's default 88 would flag ~2200 lines
target-version = "py313"
extend-exclude = ["docs", "playbooks", "templates"]

[tool.ruff.lint]
# Deliberately narrow. See docs/research/engineering-infrastructure.md §3-§4: measured against this
# tree, E9+F finds 3 unused imports and nothing else, and none of the 12 defects in
# rg1-code-review-2026-08-20.md is lint-visible. This is insurance against a NameError in an
# unexercised error path — which in this codebase means a fail-open branch — not a quality gate.
# Do not broaden it to ALL; that produces 258+ findings that are style opinions, and a check the
# operator learns to ignore is judgement 4 all over again.
select = ["E4", "E7", "E9", "F", "B"]
ignore = [
    "B007",   # unused loop control variable — 2 sites, both intentional
    "E741",   # ambiguous name `l` — 11 sites, all `for l in ...splitlines()` in tests
]

[tool.ruff.lint.per-file-ignores]
"tests/*" = ["F401"]       # test modules import for side effects / fixture wiring

[tool.pytest.ini_options]
testpaths = ["tests"]
# -q matches what status.md's measurements are taken with, so the CI number and the file agree.
addopts = "-q"
```

### 6.2 `.github/workflows/ci.yml` (new)

Action refs pinned to commit SHAs, each read from the GitHub API on 2026-08-20:
`actions/checkout` **v7.0.1** → `3d3c42e5aac5ba805825da76410c181273ba90b1`;
`actions/setup-python` **v7.0.0** → `5fda3b95a4ea91299a34e894583c3862153e4b97`. Inputs verified
against `setup-python`'s own `action.yml`. Pin by SHA rather than tag: a security tool whose CI
tracks a mutable tag is a supply-chain lecture waiting to be given back to it.

```yaml
name: ci

on:
  push:
    branches: [main]
  pull_request:
  workflow_dispatch:

# Least privilege. This workflow reads code and reports status; it writes nothing.
permissions:
  contents: read

concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true

env:
  # THE INTERPRETER RULE.
  #
  # On the operator's machine `python3` is linuxbrew 3.14.3 WITHOUT PyYAML, and /usr/bin/python3 is
  # 3.13.12 WITH it — which is why every doc and scripts/verify_controls.py hardcode the absolute
  # path. That convention must NOT be copied here: on ubuntu-24.04 runners /usr/bin/python3 is
  # 3.12.3 and PyYAML is not preinstalled, so hardcoding it would run a different, PyYAML-less
  # interpreter and scope.py's lazy `import yaml` would fail somewhere unlike production.
  #
  # Instead: setup-python provides the interpreter, PyYAML is installed into it explicitly and
  # pinned to the version the operator actually runs, and every step resolves the interpreter
  # through RG_PYTHON. See scripts/new_engagement.py:70 (verify_interpreter) for the same rule
  # applied at the /rg:new boundary, and the "fails OPEN" reasoning behind it.
  PYYAML_VERSION: "6.0.3"

jobs:
  checks:
    name: tests, roster, lint
    runs-on: ubuntu-24.04
    timeout-minutes: 10
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1

      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97  # v7.0.0
        id: py
        with:
          python-version: "3.13"

      - name: Resolve and prove the interpreter
        run: |
          set -euo pipefail
          echo "RG_PYTHON=${{ steps.py.outputs.python-path }}" >> "$GITHUB_ENV"
          "${{ steps.py.outputs.python-path }}" -m pip install --quiet \
            "PyYAML==${PYYAML_VERSION}" "ruff==0.16.3"
          # Mirror verify_interpreter's assertion: a guard whose `import yaml` dies fails OPEN, so
          # prove the import here rather than discovering it inside a hook.
          "${{ steps.py.outputs.python-path }}" -c \
            'import sys, yaml; print(sys.version); print("PyYAML", yaml.__version__)'

      - name: Test suite
        run: $RG_PYTHON -m pytest tests/

      - name: Agent roster (spec 07-enforcement.md §9.1)
        run: $RG_PYTHON scripts/validate_agents.py

      - name: Lint
        run: $RG_PYTHON -m ruff check scripts/ tests/

      - name: Shellcheck
        # shellcheck 0.9.0-1 is preinstalled on ubuntu-24.04 (runner-images Ubuntu2404 README,
        # read 2026-08-20) — no install step needed.
        run: shellcheck scripts/rate_probe.sh

  mutation:
    name: fault injection (verify_controls)
    runs-on: ubuntu-24.04
    timeout-minutes: 20
    steps:
      - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1  # v7.0.1

      - uses: actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97  # v7.0.0
        id: py
        with:
          python-version: "3.13"

      - name: Resolve and prove the interpreter
        run: |
          set -euo pipefail
          echo "RG_PYTHON=${{ steps.py.outputs.python-path }}" >> "$GITHUB_ENV"
          "${{ steps.py.outputs.python-path }}" -m pip install --quiet "PyYAML==${PYYAML_VERSION}"
          "${{ steps.py.outputs.python-path }}" -c 'import yaml'

      # Measured 2026-08-20 on the operator's machine: 60 faults, 60 caught, 2m33s. This runs on
      # EVERY push, not on a nightly schedule, and the reason is specific: verify_controls.py's
      # worst failure is SKIP — "mutation site not found, the code moved and this check is now
      # vacuous" — which fires exactly on the commit that edits a control. A nightly run reports
      # that days later, against a tree nobody is looking at. See CLAUDE.md judgement 2: a gate
      # that never fires is worse than a wrong one, because it reads as coverage.
      - name: Fault injection
        run: $RG_PYTHON scripts/verify_controls.py
```

### 6.3 The three-line source change this PR must include

`scripts/verify_controls.py:32` hardcodes `PYTHON = "/usr/bin/python3"`. On a CI runner that is a
PyYAML-less 3.12. Make it overridable while keeping the local default that exists for a good
reason:

```python
import os
# /usr/bin/python3 is the right default on the operator's machine, where `python3` resolves to a
# linuxbrew build without PyYAML. CI overrides it because the runner's /usr/bin/python3 is a
# different, PyYAML-less interpreter again. See docs/research/engineering-infrastructure.md §6.
PYTHON = os.environ.get("RG_PYTHON") or "/usr/bin/python3"
```

Add a matching entry to `MUTATIONS` in the same PR, per judgement 7 — a mutation that replaces the
`os.environ.get` with a bare hardcode, asserting some test notices. If no test notices, the
override is untested and the CI job could be running the wrong interpreter silently.

### 6.4 `.github/dependabot.yml` (new, four lines that will almost never fire)

```yaml
# github-actions only. There is no `pip` ecosystem here: the entire third-party dependency surface
# is PyYAML, imported lazily at scripts/scope.py:48. This file exists to keep the pinned action
# SHAs above from rotting, and for nothing else.
version: 2
updates:
  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "monthly"
```

### 6.5 What this PR must also do to `status.md`

One line, and it is the point of the whole exercise. Replace the hand-transcribed
*"564 tests, 18 skipped, exit 0. 45/45 fault injection, exit 0. Measured 2026-08-20."* with the
actual numbers (**605 / 18 / 60-of-60**) **and a statement of which tree they refer to**, plus the
CI badge. After this PR, that sentence is a claim CI can falsify, which is the difference between
the two halves of §1.

### 6.6 Explicitly out of scope for this PR

`mypy`, `coverage`, `pre-commit`, `ruff format`, `bandit`, `semgrep`, CodeQL, `gitleaks`, SLSA. N2
(the "name a producer" test) and N3 (the anonymisation check) are needs, but they are *code* rather
than *config* and each deserves its own PR with its own tests — putting them here would mean this
PR cannot be reviewed as "does the CI run".

---

## 7. AppSec tooling — the discrimination test applied to a security product

The repo is a security tool and it is public, which is the standard argument for turning everything
on. Applied honestly, most of it fails.

| Tool | Would it have caught anything here? | Verdict |
|---|---|---|
| `bandit` | Measured via ruff's `S` port: 8 hits in `scripts/`, all correct-by-design (`S603` ×3 argv-list subprocess, `S310` ×2 in `baseline_scan.py:64,66` where HTTP requests *are the product*, `S607`, `S101`, `S608` on the client cleanup-query template). **Zero of the 12 defects.** | **No** — and it is already inside ruff if you want it |
| Ruff `S` ruleset | Same eight. Worth running **once, by hand**, to read them and decide; not worth a gate that is 8-for-8 false positives | Manual, one-off |
| `semgrep` (registry rules) | Generic Python rules target injection/deserialisation/crypto. None of S1–S12 is that shape. The one shell-injection defect in the audit history was **f-string interpolation into a command string written to `settings.json`** (`new_engagement.py:155-160`, now `shlex.quote`d) — not a `subprocess(shell=True)` call, so no registry rule sees it | **No** |
| `semgrep` (**custom rules**) | The only appsec tool with a plausible hit. A custom rule *"builtin `hash()` must not feed a persisted identifier"* would have caught **S9** — `baseline_scan.py:602`, `f"B-{abs(hash(base)) % 1000:03d}"`, which Python randomises per process and which made blocker ids permanently unresolvable. I verified no linter has this rule: ruff's full rule list has nothing matching, and bandit does not either. But a five-line pytest asserting id stability across two subprocesses does the same job with no new tool | **Complementary at best** — prefer the test |
| CodeQL | Its Python queries are taint-tracking for injection into sinks. This codebase's sinks are `json.dump` and `print`. It would find nothing, and its default setup adds a multi-minute job | **No** |
| Dependency scanning / SBOM | One third-party import in the entire repo (PyYAML, lazily, at `scope.py:48`). **Moot — say so in the docs rather than adding a scanner that reports an empty set** | **Moot** |
| Dependabot (`github-actions` only) | Nothing yet, because there are no workflows yet. Once §6 exists, it keeps pinned SHAs fresh | **Yes, after §6** |
| `gitleaks` / `trufflehog` | **This is the important row.** The repo's one documented leak — recorded in `.gitignore`'s own comments — is *"a client name once survived into a commit undetected, caught only by a git-history check."* A company name is not a credential, has no entropy signature, and matches no gitleaks rule. The famous tool has a **0% hit rate on the only incident this repo has had**, while N3's boring project-specific denylist has 100% | **No** — build N3 instead |
| SLSA / provenance | No build step, no artifact, no source-to-artifact gap to attest. Ceremony over a `git clone` | **No** |

**The pattern worth naming:** every generic appsec tool fails the discrimination test here, and
both checks that pass it (N2, N3) are forty-line project-specific scripts. That is not an argument
against standard tooling in general — it is a fact about *this* codebase, which has almost no
dependency surface, almost no untrusted-input parsing in the classic sense, and whose entire risk
sits in **domain logic that decides what a client is told about their own vulnerabilities**. No
scanner has an opinion about whether `phase_evidence` should count `not_attempted` as a finding.
Only a test written by someone who understands what the gate is for does.

---

## 8. Answering the operator's framing directly

> *"We don't need parity with Atlassian, but we do need to be a step above vibe coding."*

**On review discipline you are already several steps above, and further than most funded teams.**
The thing to protect is `verify_controls.py`'s `breaks` field and the `status.md` "NOT enforced"
section — those are the differentiators, and neither is something a tool gave you.

**On reproducibility you are at vibe-coding level, and one PR fixes it.** Not because the code is
bad but because every assurance the project offers is currently a sentence an operator typed after
running a command on a machine nobody else has. §6 is that PR. It is roughly 120 lines of YAML and
TOML and one three-line source change, and after it, `status.md`'s numbers are falsifiable.

**The residual to record honestly, in the project's own convention:** CI runs on GitHub's
infrastructure, on a tree the operator pushes, and an agent with commit access can edit
`.github/workflows/ci.yml` in the same commit that breaks a control — exactly as it can edit
`scope_guard.py`. CI is a *reproducibility* mechanism and a *forgetfulness* mechanism. **It is not
a boundary**, and it should never be described as one in the same document that says off-host
egress filtering is the only real boundary. Branch protection requiring a green check narrows it;
it does not close it.
