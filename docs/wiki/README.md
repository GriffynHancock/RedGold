---
title: RedGold internal wiki — index and format spec
question: What is this tree, why does it exist, and how do I read or write a page in it?
status: draft
date: 2026-08-20
last_verified: 2026-08-20
---

# RedGold internal wiki

## 0. Why this exists

Repeated cost observed in session `docs/sessions/2026-08-03-04-sessions-001-004.md` and the
2026-08-20 session that produced `docs/specs/rg1-finding-integrity.md`: multiple agents
independently re-derived the same facts about the Claude Code harness (which hook fires when,
what exit code 2 does per event, what a plugin agent may configure) and discarded that knowledge
on exit. This tree is where that knowledge is meant to accumulate instead of evaporating.

This is **not** an engagement artifact. It documents the tools this repo is built on (Claude Code,
the Claude Agent SDK, and — over time — other platform mechanics RedGold agents need and keep
re-deriving). It is not findings, not scope, not client data. It lives in the framework repo
because it is framework-of-the-framework: knowledge about the platform RedGold runs on.

## 1. What "Karpathy LLM wiki" actually is, and what it is not

The operator's instruction named a specific source. Before designing anything, it was worth
finding out what that source actually specifies, per this repo's hard rule against attributing
an invented specification to a named person.

**What exists, confirmed from primary sources:**

- Andrej Karpathy published a gist titled `llm-wiki.md` on 2026-04-04
  (<https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f>), following a tweet on
  2026-04-02 describing using LLMs to build personal knowledge bases. Fetched and read directly
  2026-08-20.
- The gist is explicitly an **idea file**, not a spec: "the exact directory structure, the schema
  conventions, the page formats... will depend on your domain." Karpathy states this himself —
  he is deliberately under-specifying.
- What the gist *does* commit to: a three-layer architecture (immutable raw sources → an
  LLM-maintained wiki of markdown pages → a schema document defining structure/workflow), two
  special files (`index.md`, a content-oriented catalog; `log.md`, an append-only chronological
  record), and three operations (**ingest** — ~10-15 wiki pages updated per source; **query** —
  search + synthesize with citations; **lint** — check for contradictions, stale claims, orphan
  pages, missing cross-references). Its stated thesis: "the wiki is a persistent, compounding
  artifact... the tedious part of maintaining a knowledge base is not the reading or the
  thinking — it's the bookkeeping," which is the part an LLM can carry that a human abandons.
- A separate, real, community-built **Obsidian plugin** ("Karpathy LLM Wiki",
  <https://community.obsidian.md/plugins/karpathywiki>) implements the pattern concretely: it
  generates entity/concept/source pages under a `wiki/` folder, writes standard frontmatter
  (`tags:`, `type:`, `aliases:`) on every page, links pages with Obsidian `[[bidirectional
  links]]`, retrieves via Personalized PageRank over the link graph instead of embeddings, never
  modifies the source notes, and shows a "no wiki source matches" fallback banner when it can't
  answer from the wiki. This plugin — not Karpathy's gist — is the source of the specific
  mechanics (frontmatter fields, page types, bidirectional links) that "an Obsidian plugin" in the
  operator's instruction points to.

**What does not exist, confirmed by its absence from the primary source:** the gist does not
specify page frontmatter fields, one-fact-per-page granularity, a staleness/`last_verified`
protocol, a way to distinguish verified from inferred facts, disambiguation pages, or a
narrative-vs-dense-summary rule. These are plausible principles worth wanting, but they are not
things Karpathy wrote down — attributing them to him would be exactly the fabrication error P1/P9
and this repo's hard rules exist to prevent. **Everything below this line is this repo's own
design**, built by combining (a) the parts of Karpathy's pattern that are load-bearing and
verified (compounding pages, index + log, ingest/query/lint), (b) the parts of the Obsidian
plugin's implementation worth reusing (typed pages, frontmatter, explicit "couldn't answer"
signal), and (c) this repo's pre-existing house style, which already solves problems Karpathy's
gist leaves open.

Sources: [Karpathy gist](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f) ·
[Obsidian plugin listing](https://community.obsidian.md/plugins/karpathywiki) · both fetched
2026-08-20.

## 2. Reconciling with the existing house style

`docs/specs/redgold/README.md` already establishes: YAML frontmatter (`title`/`question`/`status`/
`date`), one question per file, files split before they grow, an index that routes by question.
`CLAUDE.md`'s working preferences state the same rule directly: "Split documents before they grow.
Frontmatter + index on everything." This predates the wiki idea and already satisfies part of what
Karpathy's `index.md` and the plugin's frontmatter are for. The wiki format below **extends** that
house style rather than replacing it — same frontmatter keys, same one-question-per-file
discipline, plus the fields a wiki page needs that a spec section doesn't (a stable link target,
a staleness anchor, a provenance tag per claim).

Where the two traditions diverge, this repo's own discipline wins:

- **Linking:** the Obsidian plugin uses `[[bare double-bracket links]]`, meaningful only inside an
  Obsidian vault. This repo is read by agents via the `Read`/`Grep` tools and by humans via `git`,
  not opened in Obsidian. Pages use **standard relative markdown links**
  (`[hooks](claude-code/hooks.md)`) instead, which resolve for both readers and any renderer. Each
  page also declares a `wiki_id` (a stable kebab-case slug) in frontmatter, which is the thing a
  link should be considered to point to even if the file is later moved — a link that breaks
  because a path changed is a maintenance bug; a `wiki_id` collision is a naming bug, and the two
  should not be conflated.
- **Provenance:** neither Karpathy's gist nor the plugin specifies how to mark a claim's source
  confidence. This repo already has a working answer — `[VERIFY]` — used throughout
  `docs/specs/redgold/15-compliance-and-obligations.md` and the finding-integrity work. The wiki
  reuses that tag exactly rather than inventing a parallel scheme, and adds two siblings for
  symmetry (§4 below).

## 3. Where it lives, and how it's organised

```
docs/wiki/
  README.md              # this file — format spec + index
  _template.md            # copy this to start a new page
  <subject>/               # one directory per subject area, e.g. claude-code/
    <topic>.md
```

Subject directories are added as needed; the first is `claude-code/` (the harness this repo runs
on). A subject directory does not need its own index file while it holds only a handful of pages —
this README's index (§6) is the single entry point until a subject grows large enough to need its
own split, per the same rule that already governs `docs/specs/redgold/`.

## 4. Page template and field meanings

See `_template.md` for the literal file to copy. Frontmatter:

| Field | Meaning |
|---|---|
| `title` | Human-readable page title. |
| `wiki_id` | Stable kebab-case identifier. Never reused for a different page, never changed once another page links to it. This is the actual link target; the file path is allowed to move under it. |
| `question` | House-style: the single question this page answers. If a page starts answering two questions, split it — same rule as the spec tree. |
| `subject` | The directory/topic area, e.g. `Claude Code hooks`. |
| `status` | One of `verified` (checked against a primary source, current), `partial` (some claims still `[VERIFY]`), `stale` (known to be past its recheck trigger, not yet rechecked), `disputed` (a later page or session contradicted something here and it hasn't been resolved). |
| `last_verified` | Date the page's claims were last checked against a source, not the date the page was last edited. |
| `verified_against` | What was checked: a doc URL plus the date it was fetched, and a product version/build if the source states one. This is the staleness anchor — see §5. |
| `sources` | List of URLs, each tagged primary/secondary/community. |
| `related` | List of `wiki_id`s, not file paths. |

Body convention: **one fact, one provenance tag**, inline at the point of the claim:

- `[SOURCE: <short cite>]` — stated directly by a primary source (official docs, a gist from the
  named author, a spec file already in this repo). The short cite should be resolvable against the
  `sources` list.
- `[INFERRED]` — this repo's own reasoning from confirmed facts, not stated directly anywhere. Safe
  to build on, but re-derive if a downstream decision is expensive, since it hasn't been checked
  against ground truth the way `[SOURCE]` has.
  `[COMMUNITY]` — from a secondary/community source (a plugin, a blog, a forum post) that is
  plausible but not Anthropic-authoritative. Treat as a hypothesis, not a fact, until corroborated.
- `[VERIFY]` — this repo's existing tag, reused unchanged: unconfirmed, must not be treated as fact,
  must not reach a client or a design decision without checking first.

A page with any `[VERIFY]` tag in its body cannot have `status: verified` — that combination is a
contradiction and should be caught on read, not just on write (no automated lint for this exists
yet; see §7).

## 5. Staleness: why `last_verified` + `verified_against` is necessary but not sufficient

The obvious mechanism is a date: "checked on 2026-08-20, believe it until it's old." That is
necessary but assessed here as **not sufficient alone**, for a reason specific to this product:
Claude Code's documentation is a rolling web page, not a versioned artifact with a changelog a page
can pin to. There is no dated release note this wiki can cite that says "hooks.md is accurate as of
build N" the way a library's CHANGELOG would let it. A `last_verified` date on its own tells a
reader only that *someone* checked *something* on that date — not what changed since, or whether
the specific fact they need was even in scope of that check.

Two things a `last_verified` date does not solve, and how this format compensates without adding
enforcement machinery outside this task's remit (`scripts/` is out of scope for this session):

- **It cannot tell a reader whether the specific claim they need is still true**, only that the
  page as a whole was looked at. Mitigated by keeping provenance per-claim (§4) rather than
  per-page — a reader checking one fact checks one tag, not the whole page's age.
- **It cannot detect drift on its own** — nothing currently re-checks a page when the underlying
  product changes, because Claude Code ships no changelog this repo watches. Compensated for by a
  `recheck_trigger` field (optional, added when a page can name one): a plain-language condition
  that should force a recheck regardless of date, e.g. "before relying on this page to design a new
  enforcement hook" or "if `code.claude.com/docs/en/hooks` 404s or its section headers change."
  This is a design recommendation, not a mechanism — no lint script enforces it yet (§7).

A page's `status: stale` should be set by whoever next reads it and finds a gap, not inferred
automatically from date math, until a lint script exists to do that math consistently.

## 6. Index

| wiki_id | Page | Subject | Status | Last verified |
|---|---|---|---|---|
| `claude-code-hooks` | [Claude Code hooks reference](claude-code/hooks.md) | Claude Code | partial | 2026-08-20 |
| `redgold-hooks-facts` | [RedGold-specific hook facts](claude-code/hooks-redgold-notes.md) | Claude Code / RedGold | verified | 2026-08-20 |
| `claude-code-execution-model` | [Claude Code execution model](claude-code/execution-model.md) | Claude Code | partial | 2026-08-20 |
| `redgold-execution-model-notes` | [What the execution model means for RedGold's controls](claude-code/execution-model-redgold-notes.md) | Claude Code / RedGold | partial | 2026-08-20 |

## 7. How an agent is directed here

No hook or automated injection currently points agents at this tree — that would require editing
`CLAUDE.md` or the plugin's `hooks.json`/skills, both out of scope for this task (constraint: do
not modify existing spec or research documents; this is a new tree, added standalone). The
recommended follow-up, left for the operator to action: add one line to `CLAUDE.md`'s "Read first"
section pointing at `docs/wiki/README.md`, the same way it already points at
`docs/specs/redgold/README.md`. Until that line exists, an agent finds this tree only by being told
about it or by discovering it in a directory listing — recorded here as a known gap, not silently
assumed away.

## 8. Open items, stated rather than hidden

- No lint script yet enforces the `status: verified` + body-`[VERIFY]` contradiction (§4), the
  `recheck_trigger` convention (§5), or `wiki_id` uniqueness. All three are checkable mechanically;
  none is built. Building them would touch `scripts/`, out of scope for this session.
- The index (§6) is maintained by hand. At the point this tree gains enough pages that hand
  maintenance becomes unreliable, split it the way `docs/specs/redgold/` already models, and
  consider whether `regen_status.py`'s pattern (script-regenerated ledger) is worth adapting here —
  a design question for later, not answered by this document.
