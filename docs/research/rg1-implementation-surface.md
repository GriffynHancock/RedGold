---
title: RG-1 (finding integrity) implementation surface — code map against the prior-engagement autopsy
date: 2026-08-20
status: draft
question: For each of the six counterfactual changes in docs/research/prior-engagement-autopsy.md §E, exactly which files, functions, and lines change, what depends on the current behaviour, and what sequencing constraints exist between the six?
---

# RG-1 implementation surface

Read-only survey. No file was modified to produce this. All line numbers are against the working
tree as of 2026-08-20 (i.e. including the uncommitted changes described in §0).

---

## 0. The uncommitted working-tree changes — provenance and scope

`git diff --stat` on 2026-08-20 shows modifications to eight scripts, four test files, and
`commands/gate.md` (992 insertions / 58 deletions). **None of it is RG-1 work.** It is two
unrelated, already-in-progress bug-fix tracks, both referencing incident IDs (`B-002`, `B-003`)
that predate this autopsy:

1. **Write-endpoint / canary-budget correctness** (`scripts/gate_cli.py`, `scripts/canary_check.py`,
   `commands/gate.md`, `tests/test_gate_cli.py`):
   - `gate_cli.parse_write_endpoint()` (`scripts/gate_cli.py:130-219`) is rewritten so
     `--write-endpoint` takes named fields (`label=`, `op=`, `max=`) instead of a positional
     `[:operation]` slot. **B-002**: an operator following the old syntax wrote a human label
     (`signup`) into the `operation` field, which `canary_check.plan_preapproval()` matches
     verbatim against `resolve_operation()`'s output (`"METHOD /route"`), so the pre-approved
     write became permanently unmatchable. Fixed by deriving `operation` mechanically and keeping
     the label in a new `label` field, ignored by the checker.
   - `canary_check.writes_already_made()` (`scripts/canary_check.py:212-240`) now returns
     `(dispatched, undispatched)` instead of a single count. **B-003**: a cleanup row is logged
     *before* a write is attempted (audit-trail-first rule), so a write the guard itself refused
     still left a row, and that row was counted against the write budget — two denied attempts
     exhausted a budget of two with zero requests ever reaching the target. Fixed via a
     `NEVER_DISPATCHED_STATES = frozenset({"denied_not_sent"})` allow-list, deliberately failing
     closed on any other/unknown `state`.
   - `commands/gate.md:41-67` diff is the doc update for the new `--write-endpoint` syntax.

2. **Asset identity is (host, port), not host** (`scripts/scope_cli.py`, `scripts/baseline_scan.py`,
   `tests/test_scope_cli.py`, `tests/test_baseline_scan.py`):
   - `scope_cli.cmd_add_candidate` / `cmd_promote` (`scripts/scope_cli.py:218-348`) now dedup and
     match on `(identifier, port)` instead of `identifier` alone, so two services on one hostname
     (e.g. `:3306` and `:6379`) can each be a separate CONFIRMED asset instead of the second one
     being silently refused as a duplicate.
   - `baseline_scan.confirmed_targets()` (`scripts/baseline_scan.py:298-324`) gained `base_url()`
     (`:275-295`) to rebuild `scheme://host:port` from the register row's `identifier` **and**
     `port` field (previously the port was dropped entirely — six assets on one host all resolved
     to `https://<bare-host>` and were scanned as one target six times over) and dedups on
     `(hostname, port)` via `urlsplit`.
   - `baseline_scan.probe_root()` / `alternate_scheme()` (`scripts/baseline_scan.py:327-360`) probe
     a target over both schemes and pick whichever answers, replacing a hardcoded
     `https://` default. This is a **byproduct that partially overlaps E2** — see §2 below, this
     is the one place the uncommitted diff and the autopsy's ask touch the same function.
   - `make_finding(..., applicable=False)` (`scripts/baseline_scan.py:192-225`) and the
     `not_applicable` result value are new: a target that never answers HTTP at all now produces
     records with `result: "not_applicable"` / `severity: "info"` instead of false "absent"
     results. `regen_status.py:158-198` and `report.py:104-121, 255-267` were updated in lockstep
     to treat `not_applicable` as neither a finding nor a clean result (its own bucket/section).

**Why this matters for planning RG-1**: nothing here implements environment classification,
`verified_by`, structured verification merge, or the impact-vs-executed lint. The `not_applicable`
work is adjacent to E2/FM-7 (see §2) and should be sequenced *before* E2, not duplicated — E2's
"collapse per-check into one coverage record per asset" is still entirely unbuilt on top of it.
The `(host, port)` identity fix is a prerequisite for environment fingerprinting done well (a
fingerprint keyed only on hostname would still conflate a dev Redis on `:6379` with anything else
on the same host), so it should land before E1's dev-fingerprint table, not after.

---

## 1. E1 — Environment classification gate (`environment:` in `scope.yaml`)

**Nothing exists today.** `environment` does not appear anywhere in `scripts/scope.py`,
`scripts/new_engagement.py`, `scripts/gate_cli.py`, `scripts/report.py`, or either fixture
(`tests/fixtures/engagement/scope.yaml`, `tests/fixtures/scope-prior-engagement.yaml`).

**Where the key would be parsed and required** — `scripts/scope.py`:
- `Scope` dataclass (`scripts/scope.py:151-163`) has no `environment` field. It would join
  `engagement_id`, `mode`, `ceiling`, etc.
- `parse()` (`scripts/scope.py:277-364`) is the single validation function; the pattern to copy is
  the `mode` handling at `:314-316` (`_require_str` + enum membership check against a frozen
  tuple), or the `redteam`-requires-`emergency_contact` conditional at `:320-324` for the "unknown
  or missing blocks Gate 1" behaviour — though note that check currently raises inside `parse()`
  itself (hard failure at load time, not a Gate 1-specific refusal). Blocking `environment: unknown`
  *only* at Gate 1 rather than at every `scope.load()` call is a design choice the parallel design
  agent needs to make explicit: `scope.load()` is called by `baseline_scan.scan()`
  (`scripts/baseline_scan.py:373`), `report.render()` (`scripts/report.py:157`),
  `regen_status.render()` (`scripts/regen_status.py:87`), and `gate_cli.cmd_plan`/`cmd_approve`
  (`scripts/gate_cli.py:230, 337-339`) — if `environment` absent/unknown is a hard `ScopeError`,
  it blocks *everything* that loads scope, not just Gate 1 approval, because `ScopeError` is
  DENY-by-contract (`scripts/scope.py:10-12`).
- `to_dict()` (`scripts/scope.py:165-181`) is the round-trip serialiser `new_engagement.py` uses to
  prove what it writes can be read back (`scripts/new_engagement.py:202-203`) — a new field must be
  added here too or the scaffolder's round-trip assertion silently drops it.

**Where Gate 1 approval is recorded** — `scripts/gate_cli.py`:
- `cmd_approve()` (`scripts/gate_cli.py:330-358`) is the only place a `gate.approve` row is
  written to `ledger/gates.jsonl`. This is the natural refusal point for "environment absent/unknown
  → refuse Gate 1" *if* the design intends a softer refusal than a `ScopeError` at parse time — it
  already loads nothing but `plan_path`/`scope_path` existence today, so it would need to
  `scope_mod.load()` and check `.environment` before writing the approval row.
- `cmd_plan()` (`scripts/gate_cli.py:227-287`) already calls `scope_mod.load()` at `:230` and could
  carry the same check, but per the autopsy's E1 text the refusal belongs to *approval*, not plan
  authoring — worth confirming with the design agent which command should refuse.
- The dev-fingerprint comparison ("hostname suffix / dev-tool banner / ephemeral path against
  `assets/register.jsonl` and evidence") has no existing home. Nothing in `scope_cli.py` or
  `gate_cli.py` reads evidence file contents today; this is new code, not a hook into an existing
  function.

**Where severity is assigned and capped** — `scripts/baseline_scan.py` and `scripts/findings.py`:
- Baseline check severity is a constant on the `Check` namedtuple (`scripts/baseline_scan.py:139-178`,
  e.g. `Check("ghost_admin_open", ..., "high", ...)`) applied verbatim in `make_finding()`
  (`scripts/baseline_scan.py:226-244`, specifically `"severity": check.severity if present else
  "info"` at line 235). A cap for `environment != production` would need to intercept this — either
  in `make_finding()` itself (needs the environment threaded in from `scan()`) or as a corpus-level
  pass in `findings.py` (parallel to `validate_corpus()`, `scripts/findings.py:371-431`).
- `findings.validate_record()` (`scripts/findings.py:202-323`) is the natural place for a
  `applies_to_production` field's presence/absence rule (analogous to the existing `NO_IMPACT`
  pattern at `:314-321`), but it operates per-record with no scope context — it would need `root`
  (which it already receives, for evidence resolution) to load `scope.yaml` and read `environment`,
  or the cap needs to happen upstream before validation runs.

**Where the report banner would land** — `scripts/report.py`:
- `render()` (`scripts/report.py:156-337`) already loads `boundary = scope_mod.load(...)` at
  `:157` and has an established "add a banner section" pattern (the `## What we could NOT check`
  section at `:255-267`, itself part of the uncommitted diff). A mandatory environment banner would
  be a new `add(...)` block near the top (`:167-173`, where the engagement header is built),
  gated on `boundary.environment != "production"`.

**`new_engagement.py` and fixtures that need the new key**:
- `build_scope_document()` (`scripts/new_engagement.py:97-127`) constructs the dict later parsed by
  `scope_mod.parse()`. It has no `environment` field and no `--environment` CLI arg
  (`build_parser()`, `scripts/new_engagement.py:254-280`). Both need a new arg and dict key, plus a
  scaffold-time refusal if the operator doesn't supply one (mirroring the existing
  `--allow-missing-authorization` escape-hatch pattern at `:188-195`, though the autopsy's intent —
  refuse Gate 1, not scaffolding itself — suggests scaffolding *should* allow `unknown` and let
  Gate 1 be the actual gate).
- `templates/engagement/CLAUDE.md` / `status.md` / `session.md` (rendered via
  `render_template()`/`mapping` at `scripts/new_engagement.py:219-235`) do not currently mention
  environment; if the banner/gate is meant to be visible to the operator at scaffold time, the
  templates need a line.
- `tests/fixtures/engagement/scope.yaml` (19 lines, confirmed above) and
  `tests/fixtures/scope-prior-engagement.yaml` (39 lines) both lack `environment:`. Every test that
  loads either fixture through `scope_mod.load()`/`scope_mod.parse()` will break the moment
  `environment` becomes `_require`d rather than optional — that is essentially every test in
  `tests/test_scope.py`, `tests/test_scope_guard.py`, `tests/test_scope_cli.py`,
  `tests/test_gate_cli.py`, `tests/test_baseline_scan.py`, `tests/test_report.py`,
  `tests/test_regen_status.py`, `tests/test_new_engagement.py` — i.e. most of the suite, because
  nearly everything roots an engagement directory off one of these two files or a copy of one
  built in `setUp()`.

**Existing schema consumer**: `docs/specs/redgold/08-findings-and-verification.md:44-49` documents
the finding schema and makes no mention of `environment` on `scope.yaml` at all — the spec has no
§ for this key yet; it is entirely new ground, consistent with the autopsy calling it a "parallel
design agent" decision.

---

## 2. E2 — Scheme/protocol applicability filter in `baseline_scan.py`

**Partially built by the uncommitted diff, but not the autopsy's actual ask.** Two sub-problems,
tracked separately in the autopsy:

**(a) HSTS checked on `http://` origins.** Still present. `SECURITY_HEADERS`
(`scripts/baseline_scan.py:181-185`) is a flat dict applied uniformly in the `for header,
consequence in SECURITY_HEADERS.items()` loop (`scripts/baseline_scan.py:402-417`) with **no
scheme check at all** — `present = header not in root_probe.headers and applicable` (line 403) does
not look at `urlsplit(base).scheme`. The uncommitted `probe_root()`/`base_url()` work (§0.2) fixed
*which* scheme gets probed (deriving it from the port/register row instead of hardcoding `https`),
which incidentally means a genuinely plaintext asset is now probed over `http://` correctly — but
once probed, HSTS-on-plaintext is still evaluated and still fires. The autopsy's fix ("(a) skip the
check and record nothing — HSTS on a plaintext origin is not a finding") is unbuilt. The fix point
is exactly `scripts/baseline_scan.py:402-417`: skip the `strict-transport-security` entry of the
loop, or the whole record write, when `urlsplit(base).scheme == "http"`.

**(b) One `not_applicable` record per (check × dead asset) instead of one per dead asset.** Still
present, in a different sense than before the uncommitted diff. Before it, dead assets produced
false `"absent"` records (worse). After it, they correctly produce `not_applicable` records
(`scripts/baseline_scan.py:390-400`, the `for check in CHECKS:` loop calling `make_finding(...,
applicable=False)` once per `Check`) — but it is still **one call per check**, i.e. still 12 records
per dead asset (9 endpoint checks + 3 header checks), not the single collapsed coverage record the
autopsy asks for. The fix point: the `for check in CHECKS:` loop at `:390-400` and the
`SECURITY_HEADERS` loop at `:402-417` both need to short-circuit to a single `make_finding` call
(or the `applicable=False` branch of `make_finding`, `:202-225`, needs to move outside both loops
entirely and be called once per asset naming all skipped checks, as the autopsy's `E2` text
specifies: *"emit **one** `not_applicable` coverage record naming all skipped checks"*).

**Dependents**: `regen_status.py:158-198` and `report.py:104-121, 255-267` (both in the uncommitted
diff) already treat `not_applicable` as its own bucket and would not need to change further if the
1-record-per-asset collapse lands — they iterate/count by `result == "not_applicable"` and by
`asset`, not by record count per check, so collapsing 12 records into 1 changes the numbers printed
but not the code that prints them. `tests/test_baseline_scan.py`'s new `MultiPortHarness` class
(uncommitted, `tests/test_baseline_scan.py:220-...`) asserts on per-check `not_applicable` records
existing per port; those assertions would need rewriting if collapse lands, since they currently
expect one record per check.

---

## 3. E3 — `verified_by != discovered_by` above Low

**Confirmed exactly as the autopsy states, still true after the uncommitted diff (which never
touches this line).**

- `scripts/baseline_scan.py:233` (unchanged by the working-tree diff — it sits in the
  `present`-branch of `make_finding()`, the branch reached when `applicable=True`):
  ```python
  "verified": "executed" if present else "none",
  ```
  with the comment at line 232: `# An automated GET that observed the condition is a mechanical
  demonstration.` No `verified_by` field is written anywhere in `make_finding()` — grep confirms
  `verified_by` does not appear in `scripts/baseline_scan.py` at all.

- **`UNVERIFIED_ABOVE_LOW`** — `scripts/findings.py:274-280`:
  ```python
  if severity in ABOVE_LOW and verified not in VERIFIED_STRONG:
      violations.append(Violation(
          rid, "UNVERIFIED_ABOVE_LOW", ...
      ))
  ```
  `VERIFIED_STRONG = frozenset({"replayed", "executed"})` (`scripts/findings.py:40`). Because
  `baseline_scan.py:233` writes `"executed"` on any `present=True` check, this rule is structurally
  satisfied by baseline's own self-certification — exactly the autopsy's FM-3. There is currently no
  `verified_by` field anywhere in the schema (see §5 below) for a `verified_by != discovered_by`
  check to compare against.

- **Other sites writing `verified`**: `scripts/baseline_scan.py:415` sets
  `record["verified"] = "n/a"` for header/posture checks (correct per §10.3, unaffected by E3).
  `scripts/findings.py`'s `normalise_legacy()` (`:349-368`) sets `out.setdefault("verified",
  "none")` for prior-engagement records with no verification step — also correct, and actually the
  precedent E3 should follow (`verified: "none"` is honest when nothing has independently checked
  the record). No other script in `scripts/` writes a `verified` value; `rg-verify` writes prose,
  not a findings-record field at all (§4).

- **`classify()`/`needs_verification()` fail-closed behaviour** — `scripts/report.py:71-84`:
  ```python
  def needs_verification(record: dict) -> bool:
      """... Fails closed on an unrecognised or missing severity. ..."""
      if str(record.get("finding_class", "technical")).lower() != "technical":
          return False
      severity = str(record.get("severity", "")).lower()
      if severity not in findings_mod.SEVERITIES:
          return True
      return severity in findings_mod.ABOVE_LOW
  ```
  This already exists and does fail closed on unknown severity, exactly as the session log
  requires — no work needed here for E3, but it is the consumer that a `verified_by` demotion rule
  must not break: `classify()` (`scripts/report.py:90-153`) calls `needs_verification()` at `:144`
  and compares against `proven` computed from `verified` at `:145-146`. If E3 demotes severity to
  `low` rather than rewriting `verified`, `needs_verification()`'s `severity in ABOVE_LOW` check
  (line 83) already naturally stops routing the (now-`low`) record to the unverified bucket — so E3
  should demote `severity`, not fabricate a `verified` value, to compose cleanly with existing
  `report.py` logic. This matches the autopsy's own stated precedent (`EVIDENCE_UNRESOLVED`,
  `scripts/findings.py:258-263`, which also demotes rather than warns).

**Tests that would break / need extension**: `tests/test_baseline_scan.py` almost certainly asserts
`verified == "executed"` on `present=True` records somewhere (needs a full read to enumerate every
assertion, but the field is central to the module's own docstring and is asserted against in
`TestBaseline`, e.g. any test checking `admin_open`/`git_exposed` results). `tests/test_findings.py`
will need new cases for a `verified_by`-vs-`discovered_by` rule. `tests/test_report.py` will need a
case proving a baseline-discovered high finding without independent verification prints at `low`
in the body, not in the unverified bucket at `high`.

---

## 4. E4 — Structured verification merge

**No merge path exists today. Confirmed absence, not just a gap.**

- `agents/rg-verify.md` tells the agent to produce a **verdict** (`VALIDATED / REJECTED /
  NEEDS-WORK`, "with per-gate reasoning recorded", `agents/rg-verify.md:48-59`) but never names an
  output file, a JSON shape, or any instruction to write to `findings/*.json` or any new file at
  all. The word "write" does not appear in the agent card except in "write a blocker to
  `ledger/blockers.jsonl`" (`:87`) for the unrelated nesting-refusal case. `rg-verify`'s tools are
  `Bash, WebFetch, Read` (`agents/rg-verify.md:5`) — **no `Write` or `Edit` tool at all**, so as
  currently specified the agent cannot write a verification file even if told to.
- The autopsy's own evidence for this gap (`findings/verification.md:184-186, 251-252` in the
  prior engagement) is prose in a `.md` file the agent apparently wrote despite not having a
  documented output contract — consistent with "verdicts land in prose" being the *default*
  behaviour of an under-specified agent, not a deliberate design.
- **No code path merges anything into a finding record post-creation.** Grep of `scripts/findings.py`
  confirms the only writers of finding-record fields are: `baseline_scan.make_finding()` (creation),
  `validate_findings.demote_records()` (`scripts/validate_findings.py:63-95`, which only ever sets
  `status` to `"SPECULATED"` and appends to `validator_note`), and nothing else. There is no
  `merge_verification()`, no `apply_verdict()`, no function that reads a second file and reconciles
  it against `findings/*.json`. `regen_status.all_findings()` (`scripts/regen_status.py:68-76`) and
  `report.render()`/`classify()` (`scripts/report.py:90-162`) both read `findings/*.json` directly
  and nothing else — there is no `findings/verification.json` reader anywhere in `scripts/`.
- **Building this**: the natural shape, per the autopsy's own proposal, is a new loader
  (`load_verification(root) -> dict[id, verdict]`) parallel to `regen_status.all_findings()`, called
  from both `regen_status.render()` and `report.classify()`/`render()`, taking the lower of the
  record's own `severity` and the verdict's `severity_recommendation` (autopsy §E4). This is new
  code in `scripts/findings.py` (schema + loader) plus call-site changes in `regen_status.py` and
  `report.py`, plus rewriting `agents/rg-verify.md` to (1) grant `Write`/`Edit`, (2) name the exact
  output path and JSON shape, (3) require a verdict row per finding above `low`.
- `docs/specs/redgold/08-findings-and-verification.md:91-109` (§10.4, the six gates) already
  specifies the verdict vocabulary (`VALIDATED / REJECTED / NEEDS-WORK`, per-gate `pass|fail`) that
  a `verification.json` schema should reuse — the autopsy is correct that "the gap is a file format,
  not a judgement."

---

## 5. E5 — Impact-vs-executed lint

**No text-field linting exists today.** `scripts/validate_findings.py` and `scripts/findings.py`
validate structure (required fields, enums, evidence resolvability, verification-level enums) but
never inspect the *content* of `real_world_impact` or any other free-text field for a
non-execution admission. Confirmed by reading `findings.validate_record()` in full
(`scripts/findings.py:202-323`): every check is either a type/enum check (`_enum()`, `:176-199`) or
a structural cross-field check (evidence resolves, `verified` vs `status` vs `severity`
consistency). No regex or substring scan against `real_world_impact` exists anywhere in the
codebase (grep for `not tested|not attempted|reasoned from` in `scripts/` returns nothing).

**Where it would go**: a new rule inside `validate_record()` (`scripts/findings.py:202-323`),
conditioned on `severity in ("high", "critical")` per the autopsy's spec, scanning
`record.get("real_world_impact", "")` against a marker list. It should be `blocking=False`
(non-blocking, per the autopsy: "routes the record into `report.py`'s open-questions section"),
which means it needs a new `Violation` code (e.g. `REASONED_ESCALATION`) that `report.classify()`
recognises. Note `report.classify()`'s `VERIFICATION_CODES` set (`scripts/report.py:58-60`,
currently `{"PROVEN_UNVERIFIED", "UNVERIFIED_ABOVE_LOW", "NA_NOT_PERMITTED"}`) is exactly the
mechanism that routes a record to "unverified" rather than "invalid" — the new code would need
adding to that set (or a new bucket) so a record carrying only this advisory violation still lands
in Open Questions rather than being silently dropped by the `blocking_codes - VERIFICATION_CODES`
check at `scripts/report.py:131-133`.

---

## 6. Coverage counterweight (whitebox-produced-nothing failure)

**Phase completion recording**: `regen_status.render()` (`scripts/regen_status.py:86-227`) derives
the `## Phase` table (`:113-124`) purely from **event counts** in `ledger/activity.jsonl` and
`ledger/gates.jsonl` — `PHASES` (`scripts/regen_status.py:40-46`) is a list of
`(label, event_type, noun)` tuples, and a phase is `"**done**"` the moment `events.get(event, 0)`
is nonzero (`:118-121`). **This cannot distinguish "ran and found nothing" from "never ran"** in
the way the autopsy needs, because the whitebox engagement's actual failure mode (`status.md:11` in
the prior engagement's repo, per the autopsy) was that *no event of any kind* was ever logged — every ledger
file was 0 bytes. `regen_status.py` would have correctly rendered every phase as "not started" for
that engagement; the gap is not in `regen_status.py`'s logic but in the absence of anything that
**refuses to let an engagement close** while every phase reads "not started". No such refusal
exists — there is no `cleanup_gate.py`-style closing check anywhere in `scripts/` (confirmed absent
by `ls scripts/`; `status.md`'s own "NOT enforced" table item 2 names `cleanup_gate.py` as
unbuilt).

**Negative/tested-and-clean results**: these *are* recorded today, robustly — `result: "absent"` in
`baseline_scan.make_finding()` (`scripts/baseline_scan.py:226-244`, the non-`present` branch) is a
first-class output, surfaced in `regen_status.py:187-191` ("Additionally N checks ran and found
nothing") and `report.py:247-253` ("N checks ran and found nothing"). This machinery is sound and
is not what failed in the autopsy's whitebox case — the whitebox engagement produced *zero* records
of any kind, not zero-severity records, so "recording negatives" was never invoked because nothing
ran.

**What a coverage counterweight needs, concretely**: a check that a phase marked "done" (or an
engagement whose Gate 1 was approved) produced at least one artifact — a `findings/*.json` file, an
`assets/register.jsonl` row, or an explicit "nothing to test" record — before the engagement is
allowed to close or a report generated. The nearest existing hook point is `report.main()`
(`scripts/report.py:340-358`), which currently generates a report unconditionally from whatever
`regen_status.all_findings()`/`read_jsonl()` return, including all-empty inputs (this is exactly
the D.1 defect the autopsy documents: the report predates its inputs and nothing detected the
staleness). A cheap version of the counterweight the autopsy proposes — "refuse to close an
engagement whose report is older than its newest finding" — is a mtime comparison at the top of
`report.main()` or a new `cleanup_gate.py`-equivalent; neither exists.

---

## 7. Findings schema — code vs spec, verbatim

**As implemented**, the complete field list any `baseline_scan.make_finding()`-produced record
carries (`scripts/baseline_scan.py:226-244`, present branch):

```
id, asset, title, finding_class, status, verified, confidence, severity, evidence_ptr,
real_world_impact, remediation, tested_at_tier, result, discovered_by, created
```

Plus, for the `applicable=False` branch (`:202-225`), the same set (with `result:
"not_applicable"`).

**As validated** — `findings.REQUIRED_FIELDS` (`scripts/findings.py:47`): only
`id, title, finding_class, status, severity` are strictly required; `verified`, `confidence`,
`evidence_ptr` are checked if present but not mandated by `REQUIRED_FIELDS` (though `evidence_ptr`
is effectively mandatory in practice via the `NO_EVIDENCE` violation, `scripts/findings.py:239-245`,
which demotes a `PROVEN` record without one).

**As specced** — `docs/specs/redgold/08-findings-and-verification.md:14-42` (§10.1) lists a
materially larger schema:

```
id, asset_id, asset, title, finding_class, obligation_refs, data_classes,
notifiable_assessment, status, verified, confidence, evidence_ptr, severity, likelihood,
real_world_impact, tested_at_tier, gate_ref, playbook_ref, standard_refs, remediation,
cost_tier, cleanup_required, discovered_by, verified_by, created
```

**Drift, field by field**:
- **`verified_by`** — specced (§10.1 example, line 39: `"verified_by": "rg-verify"`), described in
  prose as new-vs-prior-engagement (`:44-49`), **not implemented anywhere in `scripts/`**. Grep
  confirms zero occurrences of `verified_by` in `scripts/`. This is the field E3 needs and it does
  not exist yet — E3's design must add it to the schema, not just add a comparison rule.
- **`asset_id`** — specced, not written by `baseline_scan.make_finding()` (which writes `asset`,
  the URL string, but not the register's `asset_id`). Present as a general schema field in spec
  prose but absent from the actual record shape produced by the only script that creates records
  from scratch.
- **`gate_ref`** — specced as letting "a finding self-certify which approval authorised the test
  that produced it" (`:47-49`), not written anywhere in `scripts/`.
- **`obligation_refs`, `data_classes`, `notifiable_assessment`, `likelihood`, `playbook_ref`,
  `standard_refs`, `cost_tier`, `cleanup_required`** — all specced, none written or validated by
  any script. These belong to Subsystem F (compliance) and playbook-dispatch machinery per
  `status.md`, both explicitly unbuilt — the drift here is consistent with "not yet built," not a
  regression.
- Conversely, `result` (`"present" | "absent" | "not_applicable"`) is written by
  `baseline_scan.py` and consumed throughout `regen_status.py`/`report.py`, but **does not appear
  in the spec's §10.1 schema at all** — it is implementation-only, undocumented in the spec.

---

## 8. Test topology

| Script | Covering test file(s) |
|---|---|
| `scope.py` | `tests/test_scope.py` |
| `scope_guard.py` | `tests/test_scope_guard.py`, parts of `tests/test_audit_regressions.py` |
| `scope_cli.py` | `tests/test_scope_cli.py` |
| `gate_cli.py` | `tests/test_gate_cli.py` |
| `canary_check.py` | `tests/test_step7_controls.py`, `tests/test_gate_cli.py` (new B-003 case) |
| `no_handrolled_loops.py` | `tests/test_step7_controls.py` |
| `no_nesting.py` | `tests/test_agents.py` |
| `findings.py` | `tests/test_findings.py` |
| `validate_findings.py` | exercised indirectly via `tests/test_findings.py` and hook-payload
  fixtures under `tests/fixtures/hook-payloads`; no dedicated `test_validate_findings.py` was found
  — worth confirming with a targeted grep before relying on this. |
| `baseline_scan.py` | `tests/test_baseline_scan.py` |
| `report.py` | `tests/test_report.py` |
| `regen_status.py` | `tests/test_regen_status.py` |
| `new_engagement.py` | `tests/test_new_engagement.py` |
| `redact.py` | `tests/test_redact.py` |
| `validate_agents.py` | `tests/test_agents.py` |
| `regen_scripts_readme.py` | `tests/test_regen_scripts_readme.py` |
| prior-engagement acceptance | `tests/test_validate_prior_engagement.py` |
| cross-cutting audit-history regressions | `tests/test_audit_regressions.py` |

**Running the suite**: `/usr/bin/python3 -m unittest discover -s tests -v` (stdlib `unittest`
deliberately — no pytest — per `scripts/README.md:20-26`, so a control-gating test suite runs on a
bare interpreter).

**`verify_controls.py`** (`scripts/verify_controls.py`): copies the whole repo to a temp dir, then
for each of 21 `Mutation` entries (`:45-169`) — `(name, file, old_string, new_string, test_module,
breaks)` — replaces `old` with `new` in one file, runs the named test module, and asserts it goes
**red**. `undetected` mutations (still green) fail the run. Pattern for adding a new one, e.g. for
E3's `verified_by` rule once built: pick the exact line(s) that implement the rule, write the
before/after string pair, name the test module that should catch the fault, and describe what real
incident it stands in for (every existing entry has a one-line "breaks" description tied to a named
incident or rule number). Each of the six RG-1 changes should get at least one corresponding
`Mutation` entry once implemented — the harness has none of the six today (confirmed by reading the
full `MUTATIONS` list, `:45-169`: no entry references `environment`, `verified_by`,
`verification.json`, the impact-lint, scheme filtering, or a phase-emptiness check).

---

## 9. Sequencing risk — which of the six touch the same functions

- **E1 and E2 both touch `scripts/baseline_scan.py`'s per-check loop**
  (`:390-417`, `make_finding()` at `:192-244`). E1 needs the loop to know the engagement's
  `environment` (to cap severity / stamp records); E2 needs the same loop restructured to
  short-circuit per-asset instead of per-check. **Do E2's loop restructuring first** — collapsing
  12 calls into 1 per dead asset — then thread `environment` through the already-simplified loop,
  rather than adding environment-awareness to code about to be rewritten.

- **E1 and E3 both touch `scripts/findings.py`'s `validate_record()`** (`:202-323`) and both want to
  **demote severity** as their enforcement mechanism (E1: cap at `low` for non-production without
  `applies_to_production: true`; E3: demote to `low` when `verified_by == discovered_by` above
  Low). These are two independent demotion triggers landing on the same field via the same
  precedent (`EVIDENCE_UNRESOLVED`, `:258-263`). **Design them together** — if both can fire on one
  record, the resulting `Violation` list and the final `severity` need one agreed order of
  application, not two competing single-field writers. This is the single highest sequencing risk
  on the list.

- **E1 and E6 (precondition ladder, not in the "build now" set but adjacent) both touch
  `scripts/report.py`'s banner/section logic** (`:156-337`) — not a conflict, just worth noting E1's
  mandatory banner and any future precondition-cap explanation would live in the same function and
  should share a "why this record's severity was adjusted" rendering convention rather than each
  inventing its own.

- **E3 and E4 are sequence-dependent, not merely adjacent.** E4 (structured verification merge)
  is the mechanism that would let `rg-verify` supply a real `verified_by`/verdict; E3's
  `verified_by != discovered_by` rule is close to meaningless without something *other than
  `baseline_scan` itself* ever populating `verified_by` with a value that could legitimately differ.
  Practically: E3 can and should ship first (it correctly parks every self-certified baseline high
  at `low` immediately, per the autopsy's own ranking), but E4 is what makes `verified_by` a field
  with real content on the other side of the ledger — **build E3's schema field and demotion rule
  first, but do not consider E3 "done" until E4 gives `rg-verify` a documented way to write
  `verified_by: "rg-verify"` back**, or the demotion becomes permanent for every finding regardless
  of whether it was actually reviewed.

- **E5 is independent of the other five** — it only reads `real_world_impact` and `verified`, adds
  a new non-blocking `Violation` code, and needs one new entry in `report.classify()`'s
  `VERIFICATION_CODES` set (`scripts/report.py:58-60`). It can be built and landed in any order
  relative to the rest, including first, since it shares no mutated state with E1-E4.

- **The coverage counterweight (§6) touches none of the same functions as E1-E5** — it is a new
  gate on `report.main()`/an equivalent to the unbuilt `cleanup_gate.py`, operating on ledger
  emptiness rather than finding content. No ordering constraint against the other five, but it
  should probably land *after* E1 given both want to add refusal logic around Gate 1/report
  generation — sharing one "why did this refuse" reporting convention would avoid two
  independently-invented refusal message formats.

**Recommended build order given the above**: E2 loop restructuring → E1 (environment field +
severity cap, reusing E2's simplified loop) → E3 (schema field + demotion rule, designed jointly
with E1's demotion) → E5 (independent, can slot in anywhere, cheapest) → E4 (verification merge,
which retroactively completes E3) → coverage counterweight (shares E1's refusal-reporting
convention).
