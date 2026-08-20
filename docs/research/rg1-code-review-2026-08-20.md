---
title: Adversarial code review — RG-1 Releases 1 and 2
date: 2026-08-20
status: draft
question: >
  Releases 1 (e4e60b7) and 2 (b084cb3) were each reviewed only by the agent that wrote them.
  Are they sound enough to build Release 3 on, and what does an independent adversarial round
  find that the self-written suite (406 → 540, fault injection 21 → 33, all green) missed?
---

# Adversarial code review — RG-1 Releases 1 and 2

**Scope.** `e4e60b7` (Release 1), `b084cb3` (Release 2), `459a638` (spec context).
Files: `scripts/findings.py`, `scripts/report.py`, `scripts/gate_cli.py`, `scripts/scope.py`,
`scripts/baseline_scan.py`, `scripts/regen_status.py`, `scripts/new_engagement.py`,
`docs/specs/rg1-finding-integrity.md`. Read-only; nothing in the repo was modified except this
file. Every finding marked *proven* was demonstrated with a throwaway script under
`/tmp/claude-1000/-home-hiranya-RedGold/b94af6b3-…/scratchpad` against `/usr/bin/python3`.

**Result: 12 defects — 2 critical, 3 high, 4 medium, 3 low.** Ten are proven with a concrete
input and observed output. Two are unproven and marked as such.

**Verdict up front: no.** Release 3 should not be built on this. Two of the twelve are in the
exact failure class RG-1 exists to prevent — one silently under-reports a real vulnerability to a
client, the other puts a never-verified finding into a client report body. Both are in the
environment cap, which the release notes correctly identify as "the most dangerous code written
today". Neither is exotic; S1 fires on the ordinary workflow of an operator correcting a severity
upward after verification.

---

## Ranking

Ranked by harm to the **client's** interests: a defect that under-reports a real vulnerability
outranks a crash, and a crash outranks an inconsistency.

| # | Severity | Defect | Proven |
|---|---|---|---|
| S1 | **critical** | `apply_environment_cap` overwrites `severity` from an agent-writable `before_env_cap`, in production too | yes |
| S2 | **critical** | The cap walks an unverified SPECULATED finding into the client report body | yes |
| S3 | high | `gate_cli close` succeeds with no deliverable and prints a false assurance about it | yes |
| S4 | high | `phase_evidence` counts `not_attempted` records as findings — the vacuous pass it was written to close | yes |
| S5 | high | A record's self-declared `environment_at_test` overrides the scope downward, uncross-checked | yes |
| S6 | medium | `code_defect` default-on is inert: nothing produces `discovered_by: "rg-codeaudit"` | yes |
| S7 | medium | `ENVIRONMENT_DISCREPANCY` fires on realistic production traffic, and its action is suppression | yes |
| S8 | medium | `regen_status.py` and `report.py` disagree on the coverage gap; status.md fails open | yes |
| S9 | medium | `raise_blocker` ids come from `hash()` — non-deterministic per process, and they collide | yes |
| S10 | low | `close` never validates Gate 1; an engagement with a voided approval closes clean | yes |
| S11 | low | An unrecognised `production_nexus.kind` bypasses the cap *and* deletes the finding from the report | yes |
| S12 | low | `in_phase` makes `complete --phase` near-unfalsifiable — no producer writes `phase` | unproven |

Plus a state note that is not a Release 1/2 defect but contradicts the "all green" claim: see
[Working tree is red](#working-tree-is-red).

---

## S1 — critical. The cap overwrites `severity` from a field agents write, including in production

**`scripts/findings.py:228-232`, applied at `:257`.**

```python
derivation = record.get("severity_derivation")
derivation = dict(derivation) if isinstance(derivation, dict) else {}
before = derivation.get("before_env_cap")        # <-- trusted, from the record
if not isinstance(before, str) or not before:
    before = str(record.get("severity", ""))
...
record["severity"] = after                        # after == before when cap is None
```

The idempotency mechanism re-derives from `before_env_cap` "each time, never applied
cumulatively". But `before_env_cap` lives *on the record*, and every writer of a findings record
— every subagent, and the operator with an editor — can set it. When it is present it becomes the
severity, and `record["severity"]` is overwritten to match. **In production the cap is `None`, so
`applied` is `False` and nothing is disclosed — yet the severity still changes.**

The question the framing asks — *can any input cause a production finding to be capped?* — is
answered yes.

**Failing input** (`p1_cap.py`):

```python
rec = {"id": "F-001", "finding_class": "technical", "severity": "critical",
       "severity_derivation": {"before_env_cap": "info"}}
apply_environment_cap(rec, "production")
```

**Observed:**

```
environment      : production  (cap column = None, uncapped)
input severity   : critical
output severity  : info
env_cap          : None
env_cap_applied  : False
```

### The realistic path, end-to-end

No malice required. `baseline_scan` writes a record at its checklist severity and stamps a
derivation. `rg-verify` re-executes it, and the operator raises the severity — which is the
workflow §10.3 mandates. At report time the stale `before_env_cap` reverts it.

`p5_e2e.py`: a **production** engagement, one record on disk, `status: PROVEN`,
`verified: executed`, `confidence: confirmed`, `severity: high`, `real_world_impact: "Anyone can
read every registered user's email address."`, with a `severity_derivation` left over from the
earlier pass carrying `before_env_cap: "low"`. Running `report.py --tier 1`:

```
--- client report, 'What we found' ---
| Severity | Count | What it means |
|---|---|---|
| low | 1 | Worth doing; not urgent. |

--- Findings section ---
### F-001 -- Anonymous read of every user row
**Severity:** low  |  **Status:** PROVEN  |  **Independently verified:** executed

'Why this severity' disclosure present: False
'reduced' limits-clause present      : False
```

A proven, independently verified high-severity finding is printed to the client as **low**, with
**no disclosure at all** — because §6.4's disclosure is keyed on `env_cap_applied`, which is
`False`. Expected: `high`, or a refusal.

### It also kills DERIVATION_MISMATCH on the path that matters

`docs/specs/rg1-finding-integrity.md:423` says of `DERIVATION_MISMATCH`: *"that is how a
hand-edited severity gets caught."* In `report.classify` (`scripts/report.py:200`) the cap runs
over the whole corpus **before** `result_codes()` validates anything. The cap sets
`record["severity"] = after_env_cap`, so by the time `validate_record` compares the two they are
equal by construction. Confirmed in `p1_cap.py`: codes returned are `['NO_EVIDENCE', 'NO_TIER']`,
`DERIVATION_MISMATCH present: False`.

This is the fourth gate the brief told me to assume exists. **Name a state at which
`DERIVATION_MISMATCH` fires inside the report pipeline: there is none.** It still fires in the
`SubagentStop` hook (`scripts/validate_findings.py:79` calls `validate_record` without the cap),
so it is not globally dead — but on the path that produces the client deliverable, a hand-edited
severity is silently *reverted* rather than refused, which is worse than either alternative.

### Could the tests have caught it?

No. `tests/test_findings.py:441-447`:

```python
def test_a_hand_edited_severity_is_caught(self):
    record = findings_mod.apply_environment_cap(good_record(severity="critical"), "development")
    self.assertNotIn("DERIVATION_MISMATCH", self.codes(record))
    record["severity"] = "critical"
    self.assertIn("DERIVATION_MISMATCH", self.codes(record))
```

It edits `severity` **after** the cap and never re-runs it. That is the one call order
`report.classify` never uses. `test_the_cap_is_idempotent` only ever feeds back a derivation the
cap itself just wrote, so it never sees a `before_env_cap` that disagrees with `severity`. The
`verify_controls.py` mutation for this area flips `min` to `max`, which is orthogonal.

---

## S2 — critical. The cap walks an unverified finding into the client report body

**`scripts/report.py:151-163` and `:258-265`, in combination with `:200`.**

`classify` applies the cap first, then gates on the **post-cap** severity — documented as
deliberate at `report.py:193-196`. The consequence is not: `UNVERIFIED_ABOVE_LOW` (§10.3) and
`SPECULATED_ABOVE_LOW` both key on `severity in ABOVE_LOW`. Cap a technical finding to `low`
— which `ephemeral-preview` does unconditionally, and `development` does for `posture` — and both
gates fall silent.

**Failing input** (`p8_verifgate.py`): `scope.yaml` with `environment: ephemeral-preview`, and

```json
{"id": "F-001", "title": "Remote code execution in the upload handler",
 "finding_class": "technical", "status": "SPECULATED", "severity": "critical",
 "verified": "none", "confidence": "confirmed", "result": "present",
 "real_world_impact": "An attacker can run arbitrary code on the server."}
```

**Observed** in `deliverables/report-tier1.md`:

```
## Findings

### F-001 -- Remote code execution in the upload handler

**Severity:** low  |  **Status:** SPECULATED  |  **Independently verified:** none

**Why this severity.** Rated low because it was observed in a ephemeral-preview environment.
The same issue in your production system would be rated critical.

**What it means for you.** An attacker can run arbitrary code on the server.

in Open Questions bucket: False
```

**Expected:** the Open Questions bucket. This record is `SPECULATED`, `verified: none`, and the
report's own preamble promises *"Unverified technical findings above Low do not appear in the
body"* and *"a finding whose evidence pointer does not resolve is demoted, not printed"*.

The harm is worse than a mis-rating. The body now asserts to the client, in the framework's own
voice, that an unreproduced claim *"would be rated critical in your production system"* and that
*"an attacker can run arbitrary code on the server"* — at published autonomous-detection
false-positive rates of 15.3–45.8%, that is close to a coin flip printed as a finding. This is
the same class as the audit defect that "put an unverified finding into a client report".

The cap-before-gate ordering is defensible for *severity*. It is not defensible for *status* and
*verification level*, which are not severities and should never have been made reachable through
a severity transform.

**Could the tests have caught it?** No. `tests/test_report.py` has no case where the cap lowers a
record across the `low`/`medium` band boundary; every environment-cap report test uses production
or a discrepancy record. This is the exact boundary the brief predicted (`<=` vs `<`, "wrong by
one on a band boundary"): every fault-injection mutation passes and the control is still wrong at
the boundary.

---

## S3 — high. `close` succeeds with no deliverable, and prints a false assurance about it

**`scripts/report.py:128-131` (the `total == 0` early return), reached from
`scripts/gate_cli.py:524-527`; the false line is `scripts/gate_cli.py:554`.**

`freshness_violation` returns `None` when the corpus is empty — "nothing to predate". The
coverage half of `close_violations` is satisfied independently, by `phase_evidence` counting
`absent` rows in `coverage.jsonl` (`gate_cli.py:430-433`). So an engagement with **zero finding
records** and **one clean row in the coverage register** clears all three refusals.

**Failing input** (`p6_close.py`): empty `findings/`, empty `deliverables/`, and
`coverage.jsonl` containing `{"phase": "P1", "check": "tls", "outcome": "absent"}`.

**Observed:**

```
findings/            : []
deliverables/        : []

$ gate_cli.py complete --phase P1  -> exit 0
Phase 'P1' complete: 0 finding(s), 1 recorded negative(s).

$ gate_cli.py close  -> exit 0
Engagement closed as G-001
  phases completed : P1
  deliverable      : deliverables/report-tier1.md postdates every finding

deliverables/ after close: []
```

Two problems, the second worse than the first. The engagement closes with **no client
deliverable in existence**; and `close` prints, into the operator's terminal and by implication
into the audit trail, that a file postdates every finding when that file does not exist. That is
a fabricated assurance emitted by the control whose whole purpose is to prevent fabricated
assurance.

**Expected:** `REPORT_STALE` — the same refusal
`test_an_engagement_whose_deliverable_was_never_written_cannot_close` already asserts for the
non-empty case. The rule "an engagement does not close on a deliverable that was never written"
should not have an exemption for engagements that found nothing; those are precisely the
engagements whose report is the entire product.

**Could the tests have caught it?** They assert the opposite.
`tests/test_gate_cli.py:619-628`, `test_recorded_negatives_alone_satisfy_the_coverage_half`,
sets up exactly this state and asserts `exit 0`, with the comment *"No findings exist, so there is
nothing for a deliverable to predate."* The test enshrines the hole. This is a test written to
match the implementation rather than the requirement.

---

## S4 — high. `phase_evidence` counts `not_attempted` as a finding

**`scripts/gate_cli.py:425-428`.**

```python
result = str(record.get("result", "")).lower()
if result == "absent":
    absent_count += 1
elif result != "not_applicable":
    finding_count += 1
```

Its own docstring, four lines above, says:

> `not_applicable` ("structurally meaningless here") and `not_attempted` ("did not look") are
> neither — counting them would let a phase close on 36 records proving that nobody probed
> anything.

Only `not_applicable` is excluded. `not_attempted` — which `rg1-finding-integrity.md:1268` and
`:1271` establish as a first-class disposition with its own closed reason vocabulary — falls
through the `elif` and is counted as a finding. So does any record with a missing, empty or
misspelled `result`.

**Failing input** (`p6_close.py`, second half): a single record

```json
{"id": "F-001", "title": "Auth bypass -- did not look", "result": "not_attempted",
 "reason": "ceiling", "severity": "info", "status": "SPECULATED"}
```

**Observed:** `exit 0: Phase 'P1' complete: 1 finding(s), 0 recorded negative(s).`

**Expected:** `COVERAGE_EMPTY_PHASE`. A record that says "we did not look" is the canonical input
this gate exists to refuse; it currently satisfies it.

**Could the tests have caught it?**
`test_records_that_only_say_the_check_could_not_run_do_not_satisfy_it`
(`tests/test_gate_cli.py:482-491`) writes 36 `not_applicable` **finding** records plus one
`not_attempted` **coverage row**. `not_attempted` on the coverage-register side is filtered by a
different, correct check (`outcome == "absent"`, `gate_cli.py:431`). The findings side was never
tested with `not_attempted`. The two dispositions were split across the two stores in a way that
happened to exercise only the correct one.

---

## S5 — high. A record's self-declared environment overrides the scope, downward, uncross-checked

**`scripts/findings.py:215-218`.**

```python
declared = record.get("environment_at_test")
at_test = resolve_environment(declared) if declared is not None \
    else resolve_environment(environment)
```

A record that carries its own `environment_at_test` is scored against that, not against
`scope.yaml`. The rationale — "the environment at the moment of the test is a fact about the test"
— is sound for the *raising* direction. In the *lowering* direction there is no cross-check
anywhere: nothing compares a record's declared environment with the engagement's, nothing raises a
blocker, and `ENVIRONMENT_DISCREPANCY` (`findings.py:582-595`) only fires in the opposite
direction — declared `production`, dev signals observed.

**Failing input** (`p1_cap.py`, P2): engagement scope `environment: production`; record

```json
{"id": "F-002", "title": "Anon read of all users", "finding_class": "technical",
 "status": "PROVEN", "severity": "critical", "verified": "executed",
 "environment_at_test": "ephemeral-preview"}
```

**Observed:** `severity in/out : critical -> low`, `discrepancy? : []`.

**Expected:** at minimum a recorded contradiction. A record claiming a weaker environment than the
signed scope is a claim that should have to survive the same `decision`/`reason` ceremony that
`environment_discrepancy_resolution` demands in the other direction. One agent-written key is
currently sufficient to take a critical to a low on a production engagement.

The release notes name half of this: *"2.4's four-signal table detects two: the prod-signal
direction it calls 'the case that matters most' has no producer."* The missing producer is a known
gap. The absence of any **declaration-vs-declaration** check — which needs no signals and no
contact at all, only `scope.yaml` and the record — is not, and is much cheaper to fix.

**Could the tests have caught it?**
`test_environment_at_test_is_stamped_and_never_recomputed` (`tests/test_findings.py:358-365`)
asserts exactly this behaviour, including `severity == "medium"` after a critical. It is
deliberate. What is missing is any test asking whether the lowering direction is *permitted* to be
uncontested.

---

## S6 — medium. `code_defect` default-on is inert

**`scripts/findings.py:85`, `:220-226`.**

```python
CODE_DEFECT_PRODUCERS = frozenset({"rg-codeaudit"})
...
if str(record.get("discovered_by", "")) in CODE_DEFECT_PRODUCERS \
        and "production_nexus" not in record:
```

The default is gated on `discovered_by == "rg-codeaudit"`. **Nothing in the repository produces
that value.** `grep -rn discovered_by` across `agents/`, `commands/`, `templates/` and `scripts/`
returns: nothing in `agents/rg-codeaudit.md` (which never mentions the findings schema at all),
nothing in `templates/`, nothing in `commands/`. The only occurrences are in `tests/test_findings.py`
(which supplies the field itself) and in prose. The producers that *do* write records —
`baseline_scan.py:377` — write `"baseline_scan"`.

So on a `development`-declared engagement, every whitebox finding is capped at `medium`
(technical) or `low` (posture) — which is the precise outcome the constant exists to prevent, and
which the fault-injection description calls out by name: *"the missing unique constraint, the
absent fulfilment fallback and the dead sweeper, all three affecting paying customers in
production."* Name a state at which the `code_defect` default fires: with the repo as it stands,
none.

**Related, same function.** The clearing mechanism is asymmetric with every other bypass in RG-1.
`p1_cap.py`, P4: `discovered_by: "rg-codeaudit"` plus `production_nexus: null` →
`severity: critical → medium`, `production_nexus_kind: None`, and the violations raised by the
clearing are `['NO_EVIDENCE', 'NO_IMPACT', 'NO_TIER']` — none of them about the clearing. Writing
four characters suppresses a whitebox finding with no reason, no evidence pointer, no `by`, and no
violation. Compare `environment_discrepancy_resolution` (`findings.py:140-150`), which demands a
closed-vocabulary decision *and* a non-empty reason. `test_clearing_code_defect_must_be_explicit`
asserts the mechanism works; nothing asserts that it costs anything.

**Could the tests have caught it?** Not the inertness — every test supplies `discovered_by`
itself, so the tests prove the constant works on input no producer generates. Catching this needs
an integration assertion that some real producer emits a value in `CODE_DEFECT_PRODUCERS`.

---

## S7 — medium. `ENVIRONMENT_DISCREPANCY` fires on realistic production traffic, and its action is suppression

**`scripts/baseline_scan.py:253`, `:258-259`, `:269-284`.**

This gate's action clause removes findings from the client report body
(`report.py:243-245`), so a false positive here is a suppression event, not a nuisance. The brief
asks for both directions. *Name any state at which it fires:* several. *Name a healthy state at
which it fires:* also several.

**Failing inputs and observed output** (`p7_coverage.py`, run against `baseline_scan.env_signals`):

```
Stripe-style docs page on a production site           -> ['test_payment_key']
Production SPA built with Vite                        -> clean
Production Celery dashboard banner                    -> ['dev_tool_fingerprint']
Production marketing site mentioning Mailtrap in a header -> ['dev_tool_fingerprint']
Ordinary production page                              -> clean
```

The exact inputs:

- `<title>API keys</title>Use your test key <code>pk_test_51HxYzAbCdEfGhIjK</code> to try this.`
  — `TEST_KEY_RE` is `\b[ps]k_test_…`, which treats a **publishable** test key identically to a
  secret one. `pk_test_` is designed to be embedded in a page and is routinely present on
  production documentation pages, "try it" widgets and SDK landing pages.
- `Server: Flower/2.0` and `X-Powered-By: Mailtrap-Edge/1.2` — `vite`, `mailtrap` and `flower`
  were removed from `DEV_TOOL_TITLE_TOKENS` for exactly this false-positive reason, with the
  reasoning written out at `baseline_scan.py:261-263`. They were **retained** in
  `DEV_TOOL_HEADER_TOKENS`, matched as bare substrings of the concatenated `server` +
  `x-powered-by` banner. The Vite reasoning survived; the Flower and Mailtrap reasoning did not
  cross the two-line gap.

Consequence on a healthy engagement: a blocker is raised, and every finding on that asset is held
out of the report body (`report.py:243`, `findings.py:582`) until the operator records which side
was wrong. Splitting `pk_test_`/`sk_test_` — publishable versus secret — and dropping `flower`
and `mailtrap` from the header list would leave the signals that actually mean one thing.

**Could the tests have caught it?** `tests/test_baseline_scan.py` tests the signals fire on
dev-tool responses. There is no negative corpus of realistic production responses, which is the
only test shape that catches this class.

---

## S8 — medium. `regen_status.py` and `report.py` disagree on the coverage gap

**`scripts/regen_status.py:195-198` vs `scripts/report.py:397-405`.**

The release notes say *"report.py and regen_status.py count checks_skipped, not records —
collapsing storage must not shrink the reported coverage gap."* They count differently.

```python
# regen_status.py
gaps = [r for r in records if r.get("not_applicable_reason") == "no_http_response"
        or (r.get("result") == "not_applicable" and "not_applicable_reason" not in r)]
untested = sum(r.get("checks_skipped") if isinstance(r.get("checks_skipped"), int) else 1
               for r in gaps)

# report.py
count = record.get("checks_skipped")
count = count if isinstance(count, int) and count > 0 else 1
target = (inapplicable if record.get("not_applicable_reason") == "scheme_inapplicable"
          else unassessed)
```

`report.py` uses an allow-list for the *inapplicable* bucket and treats everything else as a
coverage gap — the disclosing direction. `regen_status.py` uses an allow-list for the *gap*
bucket, so anything it does not recognise vanishes.

**Failing inputs and observed output** (`p7_coverage.py`), one collapsed record standing for 12
checks each time:

```
A: recognised no_http_response, 12 checks   report unassessed={'…:8025': 12}  |  status.md untested=12
B: UNRECOGNISED reason, 12 checks           report unassessed={'…:8025': 12}  |  status.md untested=0
C: checks_skipped = 0                       report unassessed={'…:8025': 1}   |  status.md untested=0
D: checks_skipped = True (a JSON bool)      report unassessed={'…:8025': 1}   |  status.md untested=1
```

Case B is the defect: a single typo or a future third reason in `not_applicable_reason` and
status.md — the file `CLAUDE.md` calls authoritative and the operator reads at every session start
— reports **zero** unassessed services while the client report reports twelve. It fails open in
the flattering direction, which is the drift `regen_status`'s own docstring says the file exists
to prevent. Cases C and D are minor divergences from the same missing `> 0` / `isinstance(_, bool)`
guards.

**Could the tests have caught it?** No. The `verify_controls.py` mutation for this area rewrites
`"checks_skipped": len(skipped_checks)` to `1` — it perturbs the *value*, never the *filter*, and
both readers see the perturbed value identically. This is precisely the "coarse mutation, correct
against every mutation and still wrong" case the brief describes.

---

## S9 — medium. Blocker ids are built from `hash()`

**`scripts/baseline_scan.py:602`:** `"id": f"B-{abs(hash(base)) % 1000:03d}"`.

Python randomises `str.__hash__` per process unless `PYTHONHASHSEED` is set.

**Observed** (`p7_coverage.py`, four fresh interpreters, same asset string):

```
B-id across 4 fresh interpreters: ['910', '143', '959', '639']
```

Two consequences. Re-running `baseline_scan` re-raises the same asset's blocker under a **new
id**, so `ledger/blockers.jsonl` accumulates duplicates and an operator's `gate_cli.py resolve`
never sticks to the asset — the discrepancy is permanently unresolvable by re-scan. And two
distinct assets collide onto one id at roughly 1 in 1000 per pair; `cmd_resolve`
(`gate_cli.py:583`) takes `next(...)`, the first match, so resolving one silently resolves the
wrong blocker and leaves the other unaddressed. A content hash (`hashlib.sha256(base)`) or a
monotonic `B-NNN` from the existing ledger fixes it; `next_gate_id` already implements the latter
pattern eight lines away.

---

## S10 — low. `close` never validates Gate 1

**`scripts/gate_cli.py:494-529`.** `close_violations` checks the coverage half, phase completion
and deliverable freshness. It never calls `check_gate`. Under §9.7 an amended `scope.yaml` or an
edited `ledger/plan.json` voids the approval — including an amendment that changes `environment`
after Gate 1 approved it, which changes the cap every agent-written record is scored against at
report assembly (`report.py:199`). An engagement whose approval was voided mid-flight closes with
`exit 0` and a `gate.close` row that asserts nothing about the gate it was closed under.
Two lines: resolve `latest_approval_id`, run `check_gate`, append the reason. Unproven only in the
sense that I did not script it; the absence of the call is plain in the source.

---

## S11 — low. An unrecognised nexus kind bypasses the cap *and* deletes the record from the report

**`scripts/findings.py:181-193` with `scripts/report.py:246-248`.**

`production_nexus_kind` returns any non-empty string, so an unrecognised kind bypasses the cap.
The docstring calls this taking both directions: *"the cap is bypassed (the disclosing direction)
and `validate_record` raises a blocking violation (the correctness direction)."*

**Observed** (`p1_cap.py`, P3): `production_nexus: {"kind": "definitely_production_trust_me", …}`
in a `development` engagement → `severity: critical`, `cap: None`.

But `PRODUCTION_NEXUS_UNRECOGNISED` is blocking and not in `VERIFICATION_CODES`, so
`report.classify` routes the record to `invalid` — **out of the report entirely**, surfacing only
as *"N record(s) could not be substantiated by evidence that resolves"*. The record is uncapped
and unreported: the second direction is not "correctness", it is deletion. The disclosing outcome
for a malformed-but-severe finding is the Open Questions bucket, where the client at least learns
it exists. `test_an_unrecognised_kind_bypasses_the_cap_and_blocks` asserts both halves in
isolation and never asks what the report does with a record carrying both.

---

## S12 — low, unproven. `complete --phase` is near-unfalsifiable

**`scripts/gate_cli.py:395-408`.** `in_phase` counts any artifact that declares no `phase` toward
whichever phase is being closed. The rationale is sound in isolation — a gate that fires on
healthy input gets switched off. But no producer in the repo writes a `phase` field:
`baseline_scan.make_finding` does not, and no template or agent instruction mentions it. So in
practice one untagged `absent` record makes **every** phase name completable, including phases
that were never worked and phase names that do not exist. `close_violations` then needs only one
`phase.complete` row of any kind. `test_another_phases_work_does_not_close_this_phase` passes only
because its fixture sets `phase` explicitly. Marked unproven because I did not demonstrate it
end-to-end, and because the intended fix (a `phase` field on every producer) is a Release 3
question rather than a Release 2 regression.

---

## What I checked and did not find

Recording this because a review that lists only what broke says nothing about the rest.

- **`effective_environment` fail-closed behaviour is correct** on every input I could construct:
  `""`, `None`, `"unknown"`, `"banana"`, `"Development"`, `" production"`, a list, an int, a YAML
  bool. All resolve to `production` (uncapped) or are refused at Gate 1 with a distinct message.
  `scope.parse` strips whitespace and type-checks; `report.engagement_environment` catches
  `ScopeError` (including `ScopeDependencyError`) and returns `production`. Membership-test-then-
  indexed-read is used consistently; I found no `dict.get(value, default)` in a rank lookup.
- **`min` versus `max`** in the cap is correct, and `test_no_step_after_scoring_can_raise_a_severity`
  asserts it across the full cross-product of environments and severities. The cap genuinely
  cannot raise a severity.
- **The cap does not mutate a caller's record** on the corpus path
  (`apply_environment_cap_to_corpus` shallow-copies, and the derivation dict is rebuilt rather
  than mutated in place). `baseline_scan` mutates deliberately, at write time.
- **Capping does not touch `created`**, so it cannot make a fresh report read as stale or a stale
  one as fresh. The Release 1 / Release 2 interaction the brief asked about is clean in that
  direction. `close_violations`'s freshness check reads the uncapped corpus, which is correct.
- **`header_applicable`** is narrow and correct, including after `probe_root` switches the base to
  the alternate scheme — HSTS is judged against the scheme actually spoken.
- **`parse_created`** handles `Z`, `z`, naive stamps and garbage correctly, and `corpus_freshness`
  treats unreadable as neither old nor new. `freshness_violation` refuses on any unreadable stamp.
  Its only hole is the empty-corpus case (S3).
- **`x-vercel-deployment-url` and `server: Vercel`** are correctly excluded from the signal set,
  with the reasoning recorded. The `vite` title-match exclusion is correct. It is only the header
  list that regressed (S7).

<a id="working-tree-is-red"></a>
## State note — the working tree is red

Not a Release 1/2 defect, but it contradicts the "all green" framing.

```
$ /usr/bin/python3 -m pytest tests/ -q          # in ~/RedGold
18 failed, 545 passed, 18 skipped
$ /usr/bin/python3 -m pytest tests/test_scope_guard.py -q
19 failed, 55 passed
```

All failures are `tests/test_scope_guard.py::TestDecisionLogging`, and all are `IndexError: list
index out of range` — `scope_guard.py` writes no `ledger/activity.jsonl` row. `git status` shows
`M tests/test_scope_guard.py` (+305 lines, mtime `2026-08-20 12:44`, i.e. after all three commits
under review). Exporting each commit with `git archive` and running the suite in isolation:

```
8982927: 51 passed    e4e60b7: 51 passed    1af5b35: 51 passed
b084cb3: 51 passed    HEAD:    51 passed    HEAD (full suite): 540 passed, 18 skipped
```

So the committed tree is green at 540 as claimed, and the red came from **uncommitted RG-2 §5
decision-logging tests written ahead of their implementation** — a legitimate TDD red state.

The tree moved underneath this review: a concurrent session landed `scripts/scope_guard.py` and
`scripts/verify_controls.py` while it was being written, and the same command 40 minutes later
reported `1 failed, 563 passed, 18 skipped` (the remaining failure is
`test_audit_regressions.py::TestFrameworkCanRunItself::test_rate_probe_refuses_a_destination_outside_the_boundary`).
Nothing in this review depends on that work — every defect above was reproduced against the
committed trees of `e4e60b7` and `b084cb3`. The point that survives is procedural: any claim of
"all green" must name which tree it means, because the working tree was neither green nor stable
during this review.

---

## Verdict

**Releases 1 and 2 are not sound enough to build Release 3 on as they stand.** The framework and
the reasoning are good — the commit messages find and record real spec defects, the fail-closed
discipline on `effective_environment` is genuinely correct, and the siting rule caught three gates
firing on nothing. But the environment cap ships with two defects that each realise the exact
failure RG-1 was written to prevent:

- **S1** takes a proven, verified, high-severity finding on a **production** engagement to `low`
  in the client report, with no disclosure, on an ordinary workflow. It also disables
  `DERIVATION_MISMATCH` on the only path a client's document travels — the control the spec names
  as "how a hand-edited severity gets caught".
- **S2** takes a `SPECULATED`, never-verified critical claim and prints it in the client body with
  the assertion that it would rate critical in production.

Both are suppression defects in a transform whose only job is to lower severities, and both were
green against 540 tests and 33 fault injections. That is the base rate the brief warned about
holding again: the suite grew 33% and the fault injection grew 57%, and neither could see either
defect, because the tests exercise the controls in call orders the pipeline does not use
(`test_a_hand_edited_severity_is_caught`) or assert the defect as intended behaviour
(`test_recorded_negatives_alone_satisfy_the_coverage_half`).

**Minimum before Release 3:** S1, S2, S3, S4. S1 is one line (derive `before` from `severity` and
treat a disagreeing `before_env_cap` as `DERIVATION_MISMATCH` rather than as truth). S2 is a
gate that reads the pre-cap severity, or reads `status`/`verified` directly. S3 is deleting the
`total == 0` exemption from the close path. S4 is one `elif`.

**Recommended alongside:** S5 and S6, because they are the difference between the cap doing what
§6 describes and the cap being a one-key suppression primitive with an inert bypass.

Two observations for the next round's method. First, three of the twelve defects (S1, S3, S4) are
cases where **the docstring is correct and the code below it is not** — the reasoning was done and
then not implemented. Grepping this codebase for claims in prose and checking each against the
five lines beneath it is a high-yield pass on its own. Second, two defects (S3, and the shape of
S1's test) are **tests written to match the implementation rather than the requirement**; test
review, separate from code review, is now the higher-yield activity on this repo.
