---
title: "Case study: a one-person security audit, run by an agent team"
date: 2026-08-04
status: draft — anonymised; not re-checked against the 2026-08-20 control inventory
question: What did the prior engagement actually look like, told as an anonymised case study a prospect can read?
warning: >
  Client-facing material, and it is about a real engagement. Two checks before it is shown to
  anyone: (1) the anonymisation pass of 2026-08-20 — no target hostname, tailnet, IP, container,
  database, repo URL or absolute home path; (2) every enforcement claim against `status.md`'s "NOT
  enforced" section, which gained nine items on 2026-08-20. The currency audit did not verify this
  file claim-by-claim.
---

# Case Study: A One-Person Security Audit, Run by an Agent Team

> **Anonymised.** Shown with the engagement owner's permission, on the condition that the client
> remains unidentified. Client name, sector specifics, keys, project references and endpoints are
> removed. Findings and method are as-run, and have been verified claim-by-claim against the
> engagement's own phase artifacts (`case-study-verification.md`).

## 1. What the target was

The client was building a pre-launch, location-aware social product — the kind of app where strangers
find each other nearby, start a session together, and share a video call and live chat. It ran on a
modern stack: a hosted frontend talking to a managed database-plus-authentication backend, the class
of service that gives a small team a production backend without writing one. The app already held
real signed-up users' data — including profile photos imported automatically from a professional
network, and precise GPS coordinates for anyone hosting a session — which mattered because this is a
real-name, real-location product: exposing either one means exposing exactly who someone is and
exactly where they physically are.

## 2. What was asked

The client wanted a preliminary outside-in check before showing the product to prospective users,
framed around two specific worries:

- **Hypothesis A — data leakage.** Could a stranger get at other people's location, identity, or
  private information through the app or its backend?
- **Hypothesis B — cheap abuse.** Could someone flood the system with junk signups or fake data with
  no effort, running up the client's bill or polluting the database?

The one hard constraint governing everything: the client had live product demos scheduled in the days
ahead, on this exact production system. Nothing could be allowed to slow it down, lock an account, or
take it offline. The rule of the entire engagement was to prove a lock was unlocked without ever
kicking the door down to prove it.

## 3. How it was run

The work was run as a staged pipeline, not a single pass, with each stage handing structured findings
to the next: passive reconnaissance, then stack and surface mapping, then controlled access-control
testing, then desk research against known vulnerability databases, then deeper hands-on tests, then a
final client report.

Each stage was handled by a different agent role — a recon agent for open-source intelligence, a
stack-profiling agent to map the backend surface, a web-app tester agent to actually attempt
break-ins with disposable test accounts, a research agent to cross-reference findings against public
vulnerability advisories, and a report-writing agent to translate all of it into plain language. A
living tracker file recorded every phase's status, every test account created and deleted, and every
open question, so nothing was lost between stages and nothing was claimed twice.

The evidence discipline was strict: every finding was tagged either **PROVEN** — directly
demonstrated with a real, captured HTTP request and response — or **SPECULATED** — a plausible signal
that could not be confirmed without deeper access, and was reported as an open question rather than
dressed up as fact.

### The one that got away

All destructive-looking tests were run in small, capped bursts against test data only — **except
one.** The first rate-limit probe was authorised for at most ten requests. It sent twenty. The loop
counted its own iterations rather than the HTTP calls it actually dispatched, and the body of the
loop fired two requests per pass. A hand-rolled script quietly doubled its own authorised ceiling.

It was caught, logged, and disclosed to the client in full. The two later bursts in the same
engagement were rewritten to count dispatched calls against an explicit guard, and both stopped
exactly on their cap — fifteen of fifteen, no overrun.

That is a small failure with a large lesson, and it is the reason this case study belongs in a
conversation about tooling. **The control that governed that burst was my own care, and my own care
is not a control.** It held twice and failed once, which is precisely the reliability profile you
should expect from discipline that lives in a person's head rather than in a program. The framework
built after this engagement refuses hand-rolled request loops outright — not because the operator
might be careless, but because the operator was careful and it happened anyway.

## 4. What was found

| Finding | Severity | Status | What it means |
|---|---|---|---|
| Public photo storage folder | **High — live now** | PROVEN | Real users' profile photos were downloadable by anyone on the internet, no login required. |
| Exact live location exposed | Medium (time-sensitive) | PROVEN | Public sessions broadcast a host's precise GPS coordinates to anonymous visitors — **along with the session's live video-call join link and its invitee list**. Harmless today only because the location data in play is still test data. |
| No speed limit on signups/forms | Medium | PROVEN | Scripted, unlimited account creation and form spam was possible with zero pushback — a slow-burn cost and clutter risk, not a crash risk. |
| Live chat privacy | Low | SPECULATED | A test to prove chat updates stay private came back inconclusive due to a test-setup quirk, not a leak — flagged honestly rather than guessed at. |
| Name lookup via invite code | Low | SPECULATED | A helper feature appears to reveal a person's name from an invite code without needing to belong to the session. |

The public photo folder is the headline finding. It was confirmed by listing the storage folder with
nothing but the same public site key every visitor's browser already has, which returned every real
user's photo folder — twelve of them — each individually downloadable. To avoid handling anyone's
personal data unnecessarily, the actual photos were never downloaded; the test stopped at confirming
the file existed and would open.

The second finding is worth reading carefully, because the "test data" caveat is doing real work. The
exposure is live and structural: an anonymous stranger can pull a host's exact coordinates, the link
that drops them into that host's video call, and the list of who else was invited. What makes it a
Medium today rather than a High is only that the coordinates currently in the database are seeded
values. **The day real hosts start posting real sessions, this becomes a High with no code change
whatsoever** — it is a setting that is already wrong, waiting for real data to arrive.

## 5. The technique that did the work

The single most valuable move in the engagement wasn't a scanner or a brute-force tool — it was
reading the app's own delivered code. Every modern web app ships its logic to the visitor's browser
as a compiled bundle of JavaScript, and that bundle has to contain the exact, literal names of every
database table, every backend function, and every storage folder the app actually uses — because the
code has to call them by name to work at all. By fetching that bundle the same way a browser normally
would, and searching it for those literal names, the engagement recovered the app's real internal map
— not a guess at what tables might exist, but the exact names in use.

That distinction is what turned this from a guessing exercise into proof. A normal outside scan can
only try plausible-sounding names and see what sticks. This method instead read the answer key
directly out of the app's own delivery mechanism, then used those exact names to test the real, live
features — which is why the photo-folder finding could be stated as a fact backed by a captured
server response, not floated as a possibility.

## 6. What was not found, and why that matters

Just as important as what broke is what held. Nine separate attempts to reach another test user's
private session or profile — reading it, editing it, deleting it, joining it uninvited, or hijacking
ownership of it — were all correctly blocked. A separate attempt to grant a test account admin
privileges over the platform was blocked. Malicious code planted in the session chat was rendered
safely as escaped plain text in a real browser, not executed — confirmed live, with all four payloads
inert.

The software's third-party components were checked against public vulnerability databases and no
known-vulnerable version was in use. Two component-level questions could not be closed from outside
and remain open rather than cleared: how one markdown renderer is configured with respect to raw
HTML, and how one mapping library escapes text in popups. Neither is a demonstrated flaw; both are
places where a black-box view genuinely cannot see the answer.

Crediting the positives is not a courtesy — it is half of what an audit is for. A report that only
lists what's broken tells a client nothing about whether their core design is sound. Here, the parts
that matter most — who can see and touch what — held up under direct, repeated attack.

## 7. Honest limitations

This was a black-box engagement: no source code, no admin access, no inside knowledge — everything
was tested the way an anonymous stranger on the internet would experience the app.

At the time of testing, the session location data was seeded test data rather than real user data,
which is what caps that finding at Medium rather than High. Read it as a setting that is live and
wrong now, not as damage that has already happened.

A handful of items could not be resolved from outside and are disclosed as open rather than guessed
at: chat-privacy behaviour under live-update subscriptions, the strength of invite codes, and the two
component-configuration questions in §6. The storage-bucket sweep was also partial — a full
enumeration would likely have strengthened the headline finding rather than weakened it, and was left
undone rather than claimed.

Cleanup of the test accounts and records created during the engagement was handed to the client as a
manual task rather than executed automatically. That is debt, and it is named here for the same
reason the overrun in §3 is: a report that hides its own loose ends is not an audit, it is marketing.

A follow-up review with source-code access would close every one of these questions directly, rather
than inferring them from the outside.
