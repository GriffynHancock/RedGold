# scripts/

Deterministic enforcement and validation (spec §9, §10).

## Interpreter — read this before wiring any hook

**These scripts require PyYAML, and the interpreter matters.** On the reference Kali VM:

| Interpreter | Version | PyYAML |
|---|---|---|
| `/usr/bin/python3` | 3.13 | **yes** (Debian `python3-yaml`) |
| `python3` on `PATH` (linuxbrew) | 3.14 | **no** |

A hook wired as bare `python3` therefore dies on import — and **a `PreToolUse` hook that crashes
does not deny, it fails open.** The enforcement layer written by `/rg:new` (step 4) must pin an
absolute interpreter path verified at scaffold time, never rely on `PATH` resolution.

`scope.require_yaml()` exists so this failure names itself instead of surfacing as a bare
traceback. Every guard must additionally wrap its own body and emit a **deny** decision on any
exception, so that a broken control is a closed control.

## Running the tests

```sh
/usr/bin/python3 -m unittest discover -s tests -v
```

stdlib `unittest`, deliberately — tests that gate a security control must run on a bare
interpreter without installing a test framework first.

## Files

| Script | Step | State |
|---|---|---|
| `scope.py` | 2 | **done** — schema, parser, validator for `scope.yaml` |
| `scope_guard.py` | 3 | not built |
| `baseline_scan.py` | 5b | not built |
| `validate_findings.py` | 5 | not built |
| `no_handrolled_loops.py`, `rate_probe.sh`, `canary_check.py` | 7 | not built |
| `redact.py`, `session_start.py`, `cleanup_gate.py`, `regen_status.py` | 9 | not built |
