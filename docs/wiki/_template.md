---
title: <Human-readable title>
wiki_id: <stable-kebab-case-slug>
question: <The single question this page answers>
subject: <e.g. Claude Code hooks>
status: partial
last_verified: YYYY-MM-DD
verified_against: <doc URL + fetch date, or "N/A — no versioned source exists">
recheck_trigger: <optional — plain-language condition that should force a recheck regardless of date>
sources:
  - url: <https://...>
    kind: primary   # primary | secondary | community
related:
  - <other-wiki-id>
---

# <Title>

<One dense front-loaded paragraph: what this page answers, in the fewest words that don't lose
precision. A reader deciding whether to keep reading should be able to stop after this
paragraph and know whether the page has what they need.>

## <Section>

<Body. Tag every claim inline with one of:>
- `[SOURCE: <short cite matching an entry in the sources list>]` — stated directly by a primary
  source.
- `[COMMUNITY]` — from a secondary/community source, plausible but not Anthropic-authoritative.
- `[INFERRED]` — this repo's own reasoning, not stated directly anywhere.
- `[VERIFY]` — unconfirmed; do not build a design decision or client claim on this without
  checking first.

<Do not set `status: verified` while any `[VERIFY]` tag remains in the body — see
docs/wiki/README.md §4.>

## Related

- [<link text>](<relative-path>.md) — <why it's related, one line>
