---
title: Adversarial test-suite review — does 564 tests mean 564 tests' worth of assurance?
date: 2026-08-20
status: draft
question: >
  The suite grew 406 → 540 → 564 today and fault injection 21 → 33 → 45, all green. The operator's
  prior is that a large suite is suspicious and that more tests often means less security. Measured
  by fine-grained mutation rather than by count, how much discrimination does this suite actually
  have, and where is it absent?
---

# Adversarial test-suite review — 2026-08-20

**Tree measured:** `c0a20bd` ("RG-2 step 1: scope_guard decision logging"), extracted with
`git archive` to a scratchpad copy. Baseline verified green: **564 passed, 18 skipped, 137
subtests, exit 0** under `/usr/bin/python3 -m pytest -q`.

The working tree was *not* used. At the time of writing it is red (a concurrent agent's red-phase
tests) and `scripts/scope_guard.py` was being edited under this review. Every mutation result below
is against the committed tree above. Results were also computed against `26ba6ec` (540 tests) first
and were identical on every mutation that exists in both trees — the 24 tests added by `c0a20bd`
changed no verdict in this report.

---

## Verdict up front

**No. 564 tests is not 564 tests' worth of assurance, and the operator's prior is correct.**

I wrote **134 fine-grained mutations** — single comparison-operator flips, one-step off-by-one on
each cap band, one added or removed value in a closed vocabulary, one inverted branch of a
two-branch conditional, one fail-closed default flipped to fail open — against the seven
dangerous-path functions named in the brief. After discarding 5 that failed to apply, 1 that broke
a regex at import (caught for the wrong reason), 1 duplicate and 1 provably equivalent mutant,
**126 are valid**.

**40 of them survive a fully green 564-test suite. 86 are caught. Mutation score: 68%.**

That is a 68% fine-grained mutation score, which sounds survivable and is not, because the
survivors are not randomly distributed. They cluster precisely where the brief predicted: on
**band boundaries**, on **closed-vocabulary membership**, and on **fail-closed defaults** — the
three places where a control is wrong by one rather than wrong by a mile. Coarse faults are caught
almost universally (45/45 in `verify_controls.py`; I could not construct a *gross* mutation that
survived except in redaction). Fine faults are caught about half the time on the paths that matter.

The single most compact statement of the problem: **`MAX_URLS_PER_COMMAND` can be 2, 3 or 4 — and
`>` can become `>=` — and all 564 tests pass.** The constant is only pinned when it is moved to 100.
The suite knows the control exists. It does not know where its boundary is.

Corroboration, not coincidence: the parallel code review (`rg1-code-review-2026-08-20.md`) found
**12 defects, 2 critical, all green against 540 tests and 33/33 fault injections**. Two of its
twelve were tests written to match the implementation rather than the requirement. This review
reaches the same conclusion from the opposite direction — it perturbs the implementation and asks
what the tests notice — and finds the same shape of hole.

### Where the discrimination is, by file

Mutation score per target. This controls for the fact that I aimed more mutations at the
dangerous paths than at the rest.

| Target | caught / total | score |
|---|---:|---:|
| `no_handrolled_loops.py` | 1 / 4 | **25%** |
| `redact.py` | 12 / 22 | **55%** |
| `report.py` | 9 / 15 | 60% |
| `scope_guard.py` | 13 / 20 | 65% |
| `findings.py` — cap table only | 10 / 15 | 67% |
| `scope_cli.py` | 2 / 3 | 67% |
| `findings.py` — rest | 21 / 29 | 72% |
| `gate_cli.py` | 7 / 8 | 88% |
| `scope.py` | 5 / 5 | 100% |
| `baseline_scan.py` | 4 / 4 | 100% |
| `canary_check.py` | 2 / 2 | 100% |
| **Total** | **86 / 126** | **68%** |

The two weakest are the two the framework most often describes as working: the burst control and
the credential redactor.

---

## Method

- Tree: `git archive c0a20bd` into a scratchpad copy. The repo was never modified except to write
  this file.
- Each mutation is applied to a **fresh copy** of the tree, the full suite is run
  (`/usr/bin/python3 -m pytest -q`, no `-x`), and the mutation is CAUGHT if the run exits non-zero.
- A mutation whose pattern does not appear exactly once is reported SKIP and excluded, so no result
  rests on a silently-unapplied edit.

**One methodological warning, because it nearly corrupted this review.** My first harness reused a
single shared work directory. A backgrounded batch I believed had died was still running against
it, and the two runs raced: three mutations were reported SURVIVED that are in fact CAUGHT
(`SG ceiling: tier > ceiling+1`, `SG attribution carve-out widened`, `SG window: end open-ended`
under the older tree). Every number in this document is from the second, isolated harness
(`tempfile.mkdtemp` per mutation), and the full set was re-run from scratch. This is the same class
of error the suite itself makes — trusting that a thing ran because nothing said it did not.

---

## 1. Census — what the tests actually assert

Classified by AST: a test counts as **security-relevant** if its body touches the *outcome* of a
control decision — an allow/deny `Decision`, a process exit code, a severity or
`severity_derivation` value, membership of a `classify()` bucket, a violation code, redactor
output, or a `assertNotIn` on rendered client text. Everything else — argument parsing, file
layout, YAML shape, README regeneration, determinism, frontmatter — is plumbing.

| File | security-relevant / total |
|---|---:|
| `test_report.py` | 33 / 36 |
| `test_scope_cli.py` | 34 / 35 |
| `test_scope_guard.py` | 60 / 75 |
| `test_audit_regressions.py` | 56 / 71 |
| `test_findings.py` | 50 / 64 |
| `test_gate_cli.py` | 41 / 55 |
| `test_step7_controls.py` | 34 / 47 |
| `test_scope.py` | 17 / 35 |
| `test_redact.py` | 9 / 23 |
| `test_baseline_scan.py` | 17 / 50 |
| `test_new_engagement.py` | 7 / 25 |
| `test_validate_prior_engagement.py` | 6 / 18 |
| `test_agents.py` | 4 / 26 |
| `test_regen_status.py` | 4 / 17 |
| `test_regen_scripts_readme.py` | 1 / 5 |
| **Total** | **373 / 582 ≈ 64%** |

The classifier is sensitive to how a test spells its assertion; a stricter pattern set puts the
figure at 52%. **The honest ratio is roughly 6:4 security-relevant to plumbing**, and I report the
range rather than the flattering end.

**This part of the operator's prior is not borne out, and I should say so plainly.** The suite is
*not* mostly plumbing with a handful of tests guarding the controls. Roughly 370 tests do touch a
control decision. `test_report.py` and `test_scope_cli.py` are almost entirely about refusals.

**But the ratio is the wrong instrument, which is the actual finding.** The suite's problem is not
*how many* tests point at the controls. It is that within those ~370, the tests establish **that a
control exists** and almost never **where its boundary is**. A control with fifteen tests proving
it fires on an obviously-bad input and none proving it fires one step from the line is a control
with fifteen tests and one bit of information. That is why 64% security-relevant coexists with a
68% fine-grained mutation score, and why `no_handrolled_loops.py` scores 25%.

---

## 2. Tautologies — tests that cannot fail for the reason they claim

### 2.1 The iterate-the-constant-under-test pattern (proven, with a surviving mutation)

`tests/test_findings.py:481`:

```python
def test_a_blocking_signal_against_a_production_declaration_is_a_discrepancy(self):
    for kind in findings_mod.ENVIRONMENT_SIGNALS_BLOCKING:
        with self.subTest(kind=kind):
            record = good_record(environment_at_test="production",
                                 env_signals=[self.signal(kind)])
            self.assertIn("ENVIRONMENT_DISCREPANCY", self.codes(record))
```

The test's claim is *"each of the four blocking signals produces a discrepancy."* What it actually
asserts is *"every element currently in `ENVIRONMENT_SIGNALS_BLOCKING` produces a discrepancy"* —
and the set it iterates is the thing under test. **Delete a signal from the tuple and the loop
runs one fewer iteration and passes.**

Proven: the mutation `ENVIRONMENT_SIGNALS_BLOCKING loses nonprod_cert` **survives** all 564 tests,
as does `loses framework_debug_page`. Two of the four blocking environment signals can be silently
switched off. (`test_payment_key` and `dev_tool_fingerprint` are caught only because
`test_baseline_scan.py` happens to name those two literally elsewhere — an accident, not a design.)

`tests/test_findings.py:493`, `test_contributes_only_signals_never_produce_a_verdict_alone`, has
the identical structure over `ENVIRONMENT_SIGNALS_CONTRIBUTES_ONLY`.

**The contrast is instructive, and it is in the same file.** `tests/test_findings.py:394`:

```python
def test_the_bypass_vocabulary_is_closed(self):
    self.assertEqual(
        findings_mod.PRODUCTION_NEXUS_KINDS,
        ("live_credential", "production_data", "shared_infrastructure", "code_defect",
         "same_artifact"))
```

This restates the vocabulary literally, so it has real discrimination — adding an `"other"` escape
hatch to `PRODUCTION_NEXUS_KINDS` is **caught**. Same author, same file, same day; one closed
vocabulary is pinned and two are not.

### 2.2 The cap table's own "is one constant" test checks only the keys

`tests/test_findings.py:290`:

```python
def test_the_cap_table_is_one_constant(self):
    self.assertEqual(set(findings_mod.ENVIRONMENT_SEVERITY_CAP),
                     set(("production", "staging", "development", "ephemeral-preview")))
```

`set()` of a dict is its **keys**. The test named after the cap table asserts nothing whatever
about the cap *values* — the numbers that decide what a client is told. Every one of the five
surviving cap-band mutations passes this test untouched.

### 2.3 A 20-subtest property test that constrains almost nothing

`tests/test_findings.py:324`, `test_no_step_after_scoring_can_raise_a_severity`, sweeps every
environment × every severity and asserts the output index is `<=` the input index. It contributes
20 subtests to the headline count. It is a genuine invariant and worth having — but it is
**one-directional**, so it is satisfied by *any* cap value at or below the input. Tightening
`staging.posture` from `medium` all the way to `info` — hiding real staging posture findings from
a client — passes this test, and passes the whole suite.

This is the clearest instance of the count-versus-discrimination gap in the repo: the single
highest-subtest-count test on the most dangerous function pins one inequality and no boundary.

### 2.4 Freshness boundaries tested 200 million seconds apart

`tests/test_report.py:195`:

```python
EPOCH_OLD = 1_700_000_000  # well before any `created` used below
EPOCH_NEW = 1_900_000_000  # well after
```

`REPORT_STALE` is a `<` comparison between two timestamps, and the only inputs it is ever given are
6.3 years apart. Consequently the mutation `written < newest` → `written < newest - 1 second`
**survives**: a deliverable written up to a second before its newest finding is now declared fresh.
One second is harmless; the point is that the comparison's boundary is untested, so *any* tolerance
inserted there — a second, an hour, a day — is invisible to the suite.

### 2.5 Not found: testing-the-mock

I looked for this and it is largely **absent**, which is worth recording as a positive. The suite
uses real temporary directories, real files, real subprocess invocations and a real local HTTP
server for `baseline_scan`. There is very little mocking, and I found no test that exercises only
its own harness. The failure mode here is boundary blindness, not mock theatre.

---

## 3. The dangerous-path audit

Each of these can *reduce what a client is told*. For each: coverage, whether boundaries are
tested, and what wrong behaviour still passes.

### 3.1 `findings.ENVIRONMENT_SEVERITY_CAP` and its application sites

**Coverage:** substantial — `TestEnvironmentCap` plus the corpus sweep, and the cap is applied in
both `baseline_scan.scan` and `report.classify`, each with its own test.

**Boundaries: half-tested.** `test_the_graduated_cap_lowers_each_environment_to_its_band` names the
**technical** column literally for staging/development/ephemeral, so all three technical bands are
caught when moved. **The posture column is named nowhere.** Five surviving mutations:

| Mutation | Effect on a client |
|---|---|
| `staging.posture` `medium` → `high` | staging posture findings over-reported |
| `staging.posture` `medium` → `low` | **real staging posture findings suppressed** |
| `staging.posture` `medium` → `info` | **suppressed harder** |
| `ephemeral-preview.posture` `low` → `medium` | over-reported |
| `ephemeral-preview.posture` `low` → `info` | **suppressed** |

Half the cap table — the half that decides posture findings, which is most of what a baseline scan
produces — has no test that would notice it moving to any other value.

**What still passes:** the posture cap silently set to `info` in staging and ephemeral-preview,
i.e. every posture finding on a non-production stack quietly demoted to informational.

**What is well covered, and should be said:** production-is-uncapped, the `min`-not-`max`
direction, idempotency, `cap_column` routing, `resolve_environment`'s fail-closed default, and the
technical bands are all caught. This function is the best-tested dangerous path in the repo.

### 3.2 `validate_record`, `classify()`, `needs_verification()`, `UNVERIFIED_ABOVE_LOW`

**`needs_verification` fails closed correctly and is tested for it** — flipping the unknown-severity
`return True` to `return False` is caught immediately. Good.

**But its other default is not.** `str(record.get("finding_class", "technical"))` — the default that
makes a record with **no `finding_class` at all** get treated as technical and therefore gated.
Changing that default to `"posture"` **survives**. A record missing its class would skip the
verification gate entirely.

**`UNVERIFIED_ABOVE_LOW` — the flagship rule — has no test at the layer that enforces it.**
`status.md` advertises: *"unverified above-Low findings never reach the client body."* Adding
`blocking=False` to that `Violation` **survives all 564 tests**. Demonstrated directly:

```
BASELINE  blocking codes: ['UNVERIFIED_ABOVE_LOW']
MUTANT    blocking codes: []
```

At the report layer this is masked — `needs_verification` independently re-checks, which is good
defence-in-depth and is why `classify` still holds the record back. But `validate_findings.py` is a
`SubagentStop` hook, and it stops a subagent on *blocking* violations. With the mutation, a subagent
emitting an unverified critical finishes cleanly. **The hook-level enforcement of the rule the
framework most prominently claims has zero test discrimination.**

**Two more `classify` survivors:**

- `proven = verified in VERIFIED_STRONG or (verified == "n/a" and klass in NO_EXPLOIT_CLASSES)` →
  dropping the class check **survives**. A *technical* finding claiming `verified: "n/a"` would count
  as proven.
- The comment above `classify` says *"Order matters and is part of the specification — the cap runs
  **before** the §10.3 verification gate."* Swapping those two statements **survives**. A documented
  specification property has no test.

### 3.3 `production_nexus` and the `code_defect` default

**Well covered:** the closed vocabulary is pinned literally (§2.1), the unrecognised-kind
double-direction behaviour is tested, `CODE_DEFECT_PRODUCERS` emptying is caught, and
`test_clearing_code_defect_must_be_explicit` exists.

**One survivor, and it is the worst single result in this review.** Making
`PRODUCTION_NEXUS_UNRESOLVED` advisory (`blocking=False`) **survives all 564 tests**, and it is
directly exploitable at the client boundary. Demonstrated on a `development` engagement with a
`high` posture finding carrying `production_nexus: {kind: live_credential, evidence_ptr:
evidence/does-not-exist.http}`:

```
BASELINE  body [] | invalid [('F-001', 'high')]
MUTANT    body [('F-001', 'high')] | invalid []
```

A finding that escapes the environment cap on a **nexus pointer that resolves to nothing** goes
straight into the client report body at its uncapped severity. The module docstring names this
exact risk — *"a bypass supported by prose is the free-text escape hatch this vocabulary exists to
close"* — and nothing tests that the door is shut.

Relatedly, adding `PRODUCTION_NEXUS_UNRECOGNISED` to `report.VERIFICATION_CODES` also **survives**,
re-routing unreadable-nexus records from `invalid` to `unverified`.

### 3.4 `report.classify` — what reaches the client body

Mostly good: `EVIDENCE_UNRESOLVED`, prose pointers, unconfirmed confidence, `ENVIRONMENT_DISCREPANCY`
suppression, the rollup logic and the tier gate are all caught. Survivors are §3.2's three plus
`engagement_environment` below.

**`engagement_environment` fails open and nothing notices.** Its docstring is explicit: *"an
unreadable boundary caps nothing… a report that silently capped every severity because it could not
read scope.yaml would be the flattering failure."* Changing the `except ScopeError` fallback from
`"production"` to `"development"` **survives all 564 tests**. An engagement whose `scope.yaml`
became unreadable would have every technical finding capped at `medium` and every posture finding at
`low`, in silence — precisely the named failure. (The sibling `scope.effective_environment` *is*
tested: the same mutation there fails 79 tests. Two implementations of one fail-closed rule; one is
pinned, one is not — exactly the drift the duplication comment in `findings.py` warns about.)

### 3.5 `redact.py`

**The weakest control in the repo relative to its claims — 55%, and the survivors are whole
credential classes.** `test_redact.py` has 23 tests, but they exercise 8 of the 16 patterns.
**Seven patterns can be deleted outright with a green suite:**

`google-api-key` · `slack-token` · `sendgrid` · `openai` (`sk-`) · `stripe-restricted` (`rk_`) ·
`anthropic` (`sk-ant-`) · and the `ghu_`/`gho_`/`ghs_`/`ghr_` half of `github-token`
(narrowing `gh[pousr]_` to `ghp_` survives).

Two more survivors:
- `PLACEHOLDERS` gaining a plausible real value (`"admin"`) **survives** — the deny-list that
  suppresses redaction is not pinned, so a value can be added to it and every credential matching it
  passes through in cleartext.
- `prefix = value[:7] if len(value) > 12 else ""` → `value[:7]` **survives**: short secrets would
  leak their first seven characters into the transcript.

The tested patterns are tested *well* (length thresholds on `sk_`, `AKIA`, JWT, `Authorization` and
the assignment rule are all caught at the boundary). The problem is not depth, it is that half the
list has no test at all.

### 3.6 `scope_guard.py`'s deny paths

**Strong on the boundary-matching logic.** Wildcard lookalike suffixes, unknown asset types
authorising nothing, `out_of_scope` overriding `in_scope`, undeterminable targets denying, port
authorisation both ways, the ceiling in both directions and the §5.5 attribution carve-out in both
directions are **all caught**. This is the best-tested deny logic in the repo.

**The authorization window is the glaring hole.** `TestAuthorizationWindow`
(`tests/test_scope_guard.py:390`) contains **exactly one test**, and it exercises only the
*before-start* half:

```python
def test_before_window_start_denies(self):
    ...
    _dt.datetime(2019, 6, 1, tzinfo=_dt.timezone.utc),
```

Every fixture in the repo uses `window_start: 2020-01-01, window_end: 2099-12-31`. Consequently:

| Mutation | Survives? |
|---|---|
| `today > window_end` → `today >= window_end` | **survives** |
| `today < window_start` → `today <= window_start` | **survives** |
| **drop the `window_end` clause entirely** | **survives** |

`status.md` lists "outside window" as a condition `scope_guard.py` denies. **Half of it — the half
that expires an engagement — is untested, and can be deleted without turning the suite red.**
Neither the first day nor the last day of a window is ever exercised.

Three more survivors: the testing-window wraparound branch (`end <= start` → `end < start`, and
`minutes >= start` → `>`), the weekday/weekend boundary at Friday (`weekday() >= 5` → `>= 4`), and
`tool_input is not an object` → permit instead of deny — a fail-closed default at the very top of
`evaluate()`, flipped to fail open, unnoticed.

### 3.7 `gate_cli.close_violations` / `phase_evidence`

**The best-covered area at 88%.** All three close reasons are individually pinned, the
"every failing check is named, not only the first" property is pinned, the zero-zero AND/OR
distinction is caught, and `not_applicable` mis-counting is caught.

**One survivor, and it is the exact failure the function was written to close.** `phase_evidence`'s
docstring:

> `not_applicable` ("structurally meaningless here") and `not_attempted` ("did not look") are
> neither — counting them would let a phase close on 36 records proving that nobody probed anything.

Making `not_attempted` count as a recorded negative **survives all 564 tests**. `not_applicable` is
tested; `not_attempted`, named in the same sentence, is not. (The parallel code review reached the
same place from the other direction — its S4 is that `not_attempted` records are already counted as
*findings*. The requirement is stated in prose in the docstring and tested for one of its two terms.)

---

## 4. Boundary probing — the 40 surviving mutations

Every one of these leaves the suite at **564 passed, 18 skipped, exit 0**.

### The three most alarming

**1. `findings.py` — `PRODUCTION_NEXUS_UNRESOLVED` made advisory.**
Add `blocking=False` to the `Violation` at `scripts/findings.py:560`. A finding that bypasses the
environment cap on an evidence pointer resolving to **nothing** moves from `invalid` into the
**client report body** at its uncapped severity. Proven end-to-end (§3.3). This is the free-text
escape hatch the whole `production_nexus` vocabulary exists to close, and its enforcement is
untested.

**2. `scope_guard.py` — the authorization window never expires.**
Change `if today < …window_start or today > …window_end:` to `if today < …window_start:`. An
engagement whose signed window ended last year keeps authorising traffic. `status.md` advertises
this denial; one test covers the other half of the condition; every fixture runs to 2099.

**3. `no_handrolled_loops.py` — the burst threshold is unpinned in every direction.**
`MAX_URLS_PER_COMMAND = 3` can become **2** or **4**, and `if len(urls) > MAX` can become `>=`, and
all three survive. Only moving it to 100 is caught. This is the control that exists to stop an agent
firing a burst at a client's production system, and the suite constrains its threshold to
"somewhere between 2 and 4, or at any rate below 100".

### Full list

**Cap bands — `scripts/findings.py:70-75`** (5)
1. `staging.posture` `"medium"` → `"high"`
2. `staging.posture` `"medium"` → `"low"`
3. `staging.posture` `"medium"` → `"info"`
4. `ephemeral-preview.posture` `"low"` → `"medium"`
5. `ephemeral-preview.posture` `"low"` → `"info"`

**Fail-closed defaults flipped to fail open** (4)

6. `report.engagement_environment`: `except ScopeError: return "production"` → `"development"`
7. `report.needs_verification`: `record.get("finding_class", "technical")` → `"posture"`
8. `scope_guard.evaluate`: `tool_input` not an object → `Decision.permit()` instead of `deny`
9. `findings.py`: `if cap is not None and before in SEVERITIES:` → `before in SEVERITIES + ("",)`

**Blocking → advisory** (2)

10. `UNVERIFIED_ABOVE_LOW` gains `blocking=False`
11. `PRODUCTION_NEXUS_UNRESOLVED` gains `blocking=False`

**Closed vocabularies, one value changed** (7)

12. `ENVIRONMENT_SIGNALS_BLOCKING` loses `nonprod_cert`
13. `ENVIRONMENT_SIGNALS_BLOCKING` loses `framework_debug_page`
14. `STATUSES` gains `"CONFIRMED"`
15. `CONFIDENCES` gains `"high"`
16. `ID_RE` `^F-\d{3,}$` → `^F-\d{2,}$`
17. `redact.PLACEHOLDERS` gains `"admin"`
18. `scope_cli.promotion_verdict`: unknown signal classes tolerated (`unknown = set()`)

**Comparison operators and off-by-one** (9)

19. `scope_guard`: `today > window_end` → `today >= window_end`
20. `scope_guard`: `today < window_start` → `today <= window_start`
21. `scope_guard`: `window_end` clause dropped entirely
22. `scope_guard.within_testing_window`: `if end <= start:` → `if end < start:`
23. `scope_guard.within_testing_window`: `minutes >= start` → `minutes > start`
24. `scope_guard`: `local.weekday() >= 5` → `>= 4`
25. `no_handrolled_loops`: `MAX_URLS_PER_COMMAND = 3` → `4`
26. `no_handrolled_loops`: `MAX_URLS_PER_COMMAND = 3` → `2`
27. `no_handrolled_loops`: `if len(urls) > MAX_URLS_PER_COMMAND:` → `>=`

**Report assembly / ordering** (4)

28. `report.freshness_violation`: `written < newest` → `written < newest - 1s`
29. `report.classify`: `verified == "n/a"` counts as proven regardless of `finding_class`
30. `report.VERIFICATION_CODES` gains `PRODUCTION_NEXUS_UNRECOGNISED`
31. `report.classify`: environment cap applied **after** `validate_corpus` instead of before
    (a documented specification property)

**Coverage accounting** (1)

32. `gate_cli.phase_evidence`: `not_attempted` counted as a recorded negative

**Redaction patterns deleted or narrowed** (8)

33. `google-api-key` neutered
34. `slack-token` neutered
35. `sendgrid` neutered
36. `openai` (`sk-`) neutered
37. `stripe-restricted` (`rk_`) neutered
38. `anthropic` (`sk-ant-`) neutered
39. `github-token` narrowed `gh[pousr]_` → `ghp_`
40. `_mask` prefix leak: `value[:7] if len(value) > 12 else ""` → `value[:7]`

---

## 5. What the suite does not test at all

Distinct from "tests weakly" — these have no coverage whatever.

1. **The end of an authorization window.** No test, no fixture. Every `scope.yaml` in the repo runs
   to 2099-12-31. The framework cannot demonstrate that an expired engagement stops.
2. **Boundary days.** Neither `window_start` nor `window_end` is exercised on the day itself, nor
   the day either side. Same for the testing-window clock: no test at `09:00:00` or `17:00:00`
   exactly on a non-wraparound window.
3. **Eight of sixteen credential classes** in `redact.py` (§3.5).
4. **The posture column of the cap table** (§3.1).
5. **`validate_findings.py` as a hook, for `UNVERIFIED_ABOVE_LOW`.** The rule is tested where a
   second control masks it, never where it is enforced.
6. **`ENVIRONMENT_DISCREPANCY` when `environment_at_test` is absent.** The check keys off the string
   being exactly `"production"`; a record that never had the field cannot trigger it. In `classify`
   the cap stamps the field first, so this is currently unreachable — but `validate_record` is a
   public entry point called directly by the hook, and nothing tests or documents the dependency.
7. **Concurrent/interleaved ledger writes.** Every ledger test is single-writer. `append_ledger` and
   `blockers.jsonl` are append-only files written by hooks that can overlap.
8. **`redact.py` against a payload large enough to matter.** `scope_guard` has
   `MAX_ANALYSABLE_COMMAND` and a test that garbage stays fast; the redactor has no size bound and
   no equivalent test, and it runs `PostToolUse` on every tool response.
9. **What happens when two controls disagree.** Each is tested alone. `report.engagement_environment`
   and `scope.effective_environment` implement the same fail-closed rule twice, and no test asserts
   they agree — which is exactly how one of them came to be unpinned.

---

## 6. Verdict on the growth — are today's tests better or worse than the old ones?

Today the suite went 406 → 540 → 564 and fault injection 21 → 33 → 45. The question is whether
discrimination grew with the count.

**Measured by `git blame` against `c0a20bd`,** today's commits wrote 295/766 lines of
`findings.py`, 220/558 of `report.py`, 305/752 of `gate_cli.py` and 376/1130 of `scope_guard.py`,
and **zero** lines of `redact.py` and `no_handrolled_loops.py`.

**Survivors split 17 in code written today, 23 in code written 2026-08-04/05.**

**The answer is: today's tests are better than the pre-existing ones, and that is still not good
enough.** Per-area mutation scores line up almost exactly with age:

| Written | Area | Score |
|---|---|---:|
| today | `baseline_scan.py` (RG-1 §4.1/4.2) | 100% |
| today | `gate_cli.py` (RG-1 §8.2/9.1a) | 88% |
| today | `findings.py` | 67–72% |
| today | `report.py` | 60% |
| 08-04 | `scope_guard.py` | 65% |
| 08-04 | `redact.py` | 55% |
| 08-04 | `no_handrolled_loops.py` | 25% |

So the process did improve. The counterweights added today (`COVERAGE_EMPTY_PHASE`, `REPORT_STALE`,
the close gate) are the best-discriminated controls in the repo, and the 12 new injected faults are
real ones. **The count grew 33% and discrimination grew with it — not proportionally, but
genuinely.** I will not tell the operator that today's work diluted the suite, because the data
says the opposite.

**Three qualifications, and they matter more than the trend.**

1. **The new tests reproduce the old tests' worst habit.** The iterate-the-constant tautology
   (§2.1) is in code written *today*, guarding a vocabulary introduced *today*. Two of the four new
   blocking environment signals can be deleted silently. The pattern was not inherited; it was
   re-invented.

2. **The new code's most dangerous single line is its least tested.** `PRODUCTION_NEXUS_UNRESOLVED`
   is the enforcement point of the bypass that the release notes call the most dangerous code
   written today, and making it advisory walks an uncapped finding into the client body with the
   suite green. Highest risk, zero discrimination.

3. **Growth was measured in the wrong unit and that is how the two criticals shipped.** The release
   claimed "406 → 540, 21 → 33 injected faults, all green." The parallel review then found 12
   defects, 2 critical, against that same green. The 12 new injected faults in
   `verify_controls.py` are all *gross* mutations — a control removed or inverted wholesale. Not one
   of them moves a band by one step, changes one enum value, or flips one fail-closed default. So
   the fault-injection number cannot see the failure mode that actually shipped, and reporting it
   as evidence of discrimination is the confidence laundering the brief warned about.

**The correct summary of today's work:** the new controls are well tested *that they fire*, and
untested *where their edges are*. That is a better place to be than `redact.py`, and it is not a
place from which to build Release 3.

---

## 7. Direct answer to the question asked

> Does 564 tests represent 564 tests' worth of assurance?

**No.** It represents roughly 370 tests' worth of security-relevant assertion, of which the
overwhelming majority establish that a control fires on an obviously-bad input. Against
fine-grained perturbation — the class of defect that actually ships — the suite catches 68%, and
misses on the boundaries of the burst limiter, the expiry of the authorization window, half the
severity cap table, half the credential redactor, three fail-closed defaults and two
blocking-violation flags.

Where the operator's prior is **right**: more tests here has not meant more security, the green
number is being used as evidence of a claim it does not support, and four audit rounds plus today's
twelve defects are the empirical proof.

Where the operator's prior is **wrong**, and I would be doing them a disservice not to say so: this
is not a suite of tautologies and mock theatre. Mocking is essentially absent, the fixtures are real
files and real subprocesses, `test_report.py` and `test_scope_cli.py` are genuinely about refusals,
and several controls — `scope.py`, `baseline_scan.py`, `canary_check.py`, the scope-guard boundary
matcher, the gate-close reasons — resisted every fine mutation I could construct. **The suite is
mediocre in a specific and fixable way, not fraudulent.** Its defect is that it was written to
demonstrate controls rather than to locate their edges.

## 8. What would actually move the number

Ordered by discrimination gained per unit of work.

1. **Ban the iterate-the-constant pattern.** Any test looping over a vocabulary defined in the
   module under test must *also* assert the vocabulary's literal contents, as
   `test_the_bypass_vocabulary_is_closed` already does. Two lines; recovers survivors 12–13 and
   prevents the next one.
2. **Pin the whole cap table, values included.** Assert `ENVIRONMENT_SEVERITY_CAP` equals a literal
   dict. One assertion; recovers survivors 1–5.
3. **Add off-by-one faults to `verify_controls.py`.** Every threshold in the repo — the cap bands,
   `MAX_URLS_PER_COMMAND`, the window comparisons, the canary budget — gets a ±1 injected fault, not
   only a removal. This is the single change that would make the fault-injection number mean what
   it is reported to mean.
4. **Test both ends of every window, on the boundary day.** `window_start`, `window_end`, the day
   before and the day after. Add a fixture whose window has already closed.
5. **Assert `blocking=True` on the violations that carry the guarantees.** `UNVERIFIED_ABOVE_LOW`
   and `PRODUCTION_NEXUS_UNRESOLVED` at minimum, at the `validate_record` layer where the hook reads
   them — not only through `classify`, where a second control masks the first.
6. **One test per redaction pattern.** Sixteen patterns, eight tests. The missing eight are
   mechanical to write.
7. **Cross-check the duplicated fail-closed rule.** One test asserting
   `report.engagement_environment` and `scope.effective_environment` agree on unreadable input.
