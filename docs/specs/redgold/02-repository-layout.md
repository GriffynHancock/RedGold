---
title: Repository layout
question: Where does everything live, and why are framework and client data separated?
sections: [4]
spec: RedGold design
status: draft
date: 2026-08-03
---

## 4. Repository layout

Two repositories, permanently separate.

```
~/RedGold/                          # the framework. private git repo, installs as a CC plugin
  .claude-plugin/
    plugin.json
    marketplace.json                # so it installs by name on a fresh VM
  agents/                           # the capped roster (§8)
  skills/
    using-redgold/SKILL.md          # entry-point skill (§12)
    playbook-dispatch/SKILL.md      # fingerprint → playbook loader (§11)
    <procedure skills>/
  commands/                         # /rg:new, /rg:scope, /rg:gate, /rg:harvest, /rg:report
  hooks/
    hooks.json                      # plugin-level, non-enforcing hooks only
  scripts/                          # deterministic enforcement + validation (§9, §10)
    scope_guard.py
    baseline_scan.py
    no_handrolled_loops.py
    canary_check.py
    redact.py
    validate_findings.py
    session_start.py
    cleanup_gate.py
    rate_probe.sh
    regen_status.py
  playbooks/                        # the skill factory (§11)
    index.yaml
    _generic/
    backends/ frontends/ hosting/ payments/ patterns/
  templates/
    engagement/                     # scaffold copied by /rg:new
    reports/
    handoff/
  evals/                            # per-skill trigger evals (§11.6)
  docs/specs/

~/engagements/<client>-<yyyy-mm>/   # one private repo per engagement. NEVER inside RedGold
  .claude/
    settings.json                   # ← THE ENFORCEMENT LAYER LIVES HERE (§9.1)
    rules/                          # path-scoped methodology rules
  CLAUDE.md                         # constitution (§7.1)
  status.md                         # ledger, script-regenerated (§7.2)
  session.md                        # append-only working log (§7.3)
  scope.yaml                        # authorization boundary (§5.1)
  assets/
    register.jsonl                  # discovered + confirmed assets (§5.2)
    candidates.jsonl                # unconfirmed, untouchable (§5.3)
  findings/*.json                   # findings records (§10.1)
  evidence/                         # raw HTTP, screenshots, captures
  ledger/
    gates.jsonl                     # approval decisions
    activity.jsonl                  # append-only action log
    cleanup.jsonl                   # write-test debt and canary results
    sessions/NNN-YYYY-MM-DD.md      # archived session logs
  deliverables/
```

**Hard rule: client data never enters the framework repo.** The prior engagement kept `.secrets.env`
and Burp captures beside `FRAMEWORK.md`. That is tolerable for one gig and untenable at five, because the
moment the framework is worth backing up or sharing it carries a client's credentials. Separation
also forces `/rg:harvest` to redact deliberately when promoting a lesson, rather than allowing
knowledge to leak between clients by accident.

---
