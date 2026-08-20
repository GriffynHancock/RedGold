---
title: RG-4 — the client-side scoping questionnaire
date: 2026-08-20
status: draft
question: How does a client, in their own Claude and on documents the operator may not see, produce an engagement document and a scope record that `/rg:new` will accept — and how does the operator trust an artifact whose inputs they cannot read?
---

# RG-4 — the client-side scoping questionnaire

Sub-project RG-4. Consumes `docs/specs/redgold/03-scope-model.md` (§5), `11-governance.md` (§15.1),
`docs/specs/rg1-finding-integrity.md` (§3.1, §4.2, §6), and `scripts/new_engagement.py`'s refusals.
Produces the input to `/rg:new` and the artifact that turns B-1's "verbal approval" into an
authorisation record on disk.

This is a design document. Nothing here is built.

## Index

| § | Contains |
|---|---|
| 1 | The trust boundary, and what actually crosses it |
| 2 | The client-truthfulness problem — the honest answer |
| 3 | The field list — what the questionnaire must extract |
| 4 | Branching, and what was cut |
| 5 | Documents — extraction, provenance, and what must never be inferred |
| 6 | The two outputs, with worked examples |
| 7 | Refusal, contradiction, and "cannot determine" |
| 8 | The dev-environment walkthrough and the environment delta |
| 9 | The goal-loop close |
| 10 | What a Claude skill can and cannot guarantee |
| 11 | Open decisions for the operator |

---

## 1. The trust boundary, and what actually crosses it

### 1.1 Where the skill runs

`rg-scoping` runs in **the client's own Claude, on the client's own machine, against the client's own
documents**. It is not a RedGold plugin command and it is not run by the operator. This is not a
convenience: the operator is not permitted to read the inputs, so the inputs must never reach a
machine the operator controls.

CLAUDE.md hard rule 3 already says client data never enters this repo. RG-4 tightens it by one
notch: **client data never enters the operator's filesystem at all, including
`~/engagements/`, except the fields the client deliberately published in the bundle.**

```
CLIENT SIDE                                    ║  OPERATOR SIDE
                                               ║
architecture diagrams, privacy policy,         ║
data inventory, prior pentest reports,         ║
infra dashboards, internal wikis               ║
        │                                      ║
        ▼                                      ║
  rg-scoping  (client's Claude)                ║
        │                                      ║
        ▼                                      ║
  scoping-bundle/                  ─────────►  ║  rg4_ingest.py  ──►  /rg:new  ──►  scope.yaml
    engagement-document.md                     ║   (validates shape,      (validates boundary,
    scope-record.yaml                          ║    refuses on missing     pins interpreter,
    answers.jsonl                              ║    authority, emits       requires the signed
    documents.manifest.json                    ║    the command line)      document on disk)
    unresolved.md                              ║
    signature.txt                              ║
                                               ║
  the documents themselves  ──────X            ║  never crosses
```

### 1.2 What crosses, exactly

**Crosses:** the six bundle files above. Every one is a file the client can read end to end in under
twenty minutes before they send it. That property is a requirement, not an accident — a client cannot
consent to disclosing something they cannot read.

**Does not cross:** the source documents; credentials; any excerpt or quotation from a document
longer than a host name, a project identifier, or a date; any customer record; any employee name
other than the signer and the named technical contact.

**Explicitly permitted to cross Anthropic's servers:** everything. The operator has stated that model
inference over client documents is acceptable to them; the constraint is on the *operator's eyes*.

> **[CONTRADICTED — `docs/research/data-sovereignty.md` §4.2 item 4 (gitignored) reaches the opposite
> conclusion on the same day, and names the gap this sentence creates as *"the misleading-conduct
> exposure"* under ACL s 18. Recorded 2026-08-20 by the currency audit; see also
> `docs/research/strategic-review.md` §1.6 and the reciprocal marker at
> `docs/specs/redgold/11-governance.md` §15.5. **Unresolved, and `[VERIFY]` — it needs a lawyer.**]**
>
> The distinction the two documents are talking past: *the operator* consenting to model inference
> over client documents is not *the client* consenting, and the client is the one whose personal
> information it is. **The permission recorded here is recorded in a spec the client never sees.** If
> `rg-scoping` runs on the client's machine over the client's documents and nothing in the
> client-facing skill says the documents cross to a US-hosted model, the client has not been told —
> and `data-sovereignty.md` argues that presenting the exercise as compliance-improving while it is
> itself creating a cross-border disclosure is the exposure, not the disclosure itself.
>
> **What is not in dispute:** the design decision below — spend nothing on preventing the model from
> reading, spend everything on controlling what lands in the bundle — is sound and is not what the
> contradiction is about. What is missing is a **disclosure sentence in the client-facing skill**.
> `data-sovereignty.md` §2 also establishes that an Australian-residency inference path exists and is
> reachable by configuration, which changes what that sentence would have to say.
So the design spends nothing on preventing the model from reading the documents, and spends
everything on controlling what lands in the bundle. Designing against the wrong threat here would
produce a skill that cannot read the documents it exists to read.

### 1.3 Why this is a distinct system, not a mode of `/rg:new`

CLAUDE.md names three systems with different trust properties. RG-4 adds a fourth, upstream of all of
them, and it has the weakest trust properties of any: **it runs on a machine the operator does not
control, under a Claude the operator does not configure, with no hooks, no ledgers, and no ability to
enforce anything.** Everything it emits is a *claim by the client*, arriving over an untrusted
channel, in a format the operator's own tooling must re-validate from scratch.

Treat the bundle exactly as CLAUDE.md hard rule 6 says to treat agent output crossing the containment
boundary: **reviewed, not trusted.** The bundle is parsed by `rg4_ingest.py` on the operator's side
with the same posture `scope_guard.py` has toward a subagent's proposed command.

---

## 2. The client-truthfulness problem — the honest answer

### 2.1 State the problem correctly first

The failure is not fraud. It is the ordinary case: **a client who does not know their own system.**
§5's opening sentence already says it — *"a non-technical founder does not know what assets they
have; clicking through a dashboard spawns cloud objects and changes configs invisibly."* RG-4 is that
sentence turned into a product, so RG-4 inherits its problem in the sharpest possible form: the
questionnaire's only witness to the truth is the person least equipped to know it.

A client who misdescribes their system produces a scope record that authorises the wrong thing. Three
concrete shapes, all realistic, none dishonest:

| Shape | Example | Consequence |
|---|---|---|
| **Under-declaration** | Names `app.example.com`; forgets the Retool instance holding the same database | Real risk unaudited. The report claims a coverage it does not have |
| **Over-declaration** | Names `*.example.com`; a subdomain is a reseller's WordPress the client does not control | **Unauthorised access to a third party.** The Criminal Code exposure §15.1 exists for |
| **Mis-declaration** | Declares `environment: staging` for a host that is in fact production | RG-1's environment cap suppresses real findings, or a tier-2 write lands on live customers |

Over-declaration is the one that carries legal risk and it is the one a signature does not fix.

### 2.2 Four layers, and what each actually buys

**No layer establishes truth. Say so plainly and do not let the stack of four imply otherwise.**

**Layer 1 — attestation. Buys: a shift in who is responsible, not a check on the facts.**
The engagement document ends in a signature block in which a named person states their role, states
that they have authority to bind the organisation, and states that the asset list is accurate to
their knowledge. This converts a misdescription from *the operator failed to verify* into *the client
misrepresented*. That is a real and worthwhile change to the operator's position, and it is a legal
change, not an epistemic one. It stops nothing.

**Layer 2 — provenance and self-consistency. Buys: proof the artifact was not hand-trimmed, and a
record of where each fact came from.**
Every answer in `answers.jsonl` carries `provenance` (§5.3), a timestamp, and — where it came from a
document — the SHA-256 of that document plus a locator. Every field in `scope-record.yaml` carries a
back-pointer to the answer id that produced it. `rg4_ingest.py` refuses a bundle in which any
`in_scope` entry has no answer behind it, or any answer's provenance is `document` alone. So an
asset cannot appear in the boundary without a human having typed a confirmation of it. That is
mechanical and it is worth having, and it still cannot tell you whether the human was right.

**Layer 3 — the client's own review step. Buys: the single highest-yield correction available.**
The skill's last act before emitting anything is to render the complete asset list, the complete
"what we will do to it" list, and the complete exclusion list back to the respondent in plain
language, and require an explicit per-line acknowledgement of the in-scope list. This is not
ceremony: the failure mode is *forgetting*, and a list read back is the cheapest known intervention
against forgetting. It is also where over-declaration gets caught, because *"we will send test
traffic to every host under `*.example.com`, including `shop.example.com` and `blog.example.com`"* is
a sentence that makes a client say "wait, the blog isn't ours".

**Layer 4 — reconciliation against observation. Buys: the only genuine truth check in the design, and
it is narrow.**
The operator cannot check the declaration against the documents. The operator *can* check it against
the target, and RG-1 already built the machinery. Reuse it verbatim rather than inventing a parallel
mechanism:

| Declared fact | Reconciliation, before Gate 1 | Existing rule reused |
|---|---|---|
| in-scope hosts | every declared host resolves, and its attribution reaches CONFIRMED on two independent signal classes | §5.2 promotion rule, `scope_cli.py` |
| `environment` | classifier's four blocking signals from RG-1 §2.4 must not contradict the declaration in either direction | `ENVIRONMENT_DISCREPANCY`, RG-1 §4.2 |
| "we hold no payment data" | a `pk_live_`/`sk_live_` prefix observed in a response contradicts it | RG-1 §4.2 signal table |
| "the blog is ours" | RDAP/ASN/CNAME signals attribute it elsewhere | §5.2 signal classes |
| declared platform list | observed CNAME chain names a platform the client did not declare | §15.1 — new AUP question needed |

**New violation code, blocking at Gate 1: `SCOPE_DECLARATION_DISCREPANCY`.** Fires when a tier-0/1
observation contradicts a client declaration recorded in the bundle. Same shape and same disposition
as `ENVIRONMENT_DISCREPANCY`: the affected assets do not enter active testing until a **recorded
operator decision names which side was wrong**, and the resolution goes back to the client, because
correcting a declaration is a scope amendment (`scope_cli.py amend`) and not an operator judgement
call.

### 2.3 The residual, stated and accepted

> **A client who misdescribes their system in a way that produces no observable contradiction gets an
> audit of the wrong thing, and RedGold will not detect it.**

Layer 4 only fires when the target visibly disagrees. Under-declaration — the most common shape — is
by construction invisible to it: an asset nobody mentioned generates no contradiction, because
nothing points at it. Recon (`rg-recon`) partially covers this and is the right partial answer, but
it can only find what is externally discoverable, and the Retool instance behind SSO is not.

This is **accepted risk**, and it is accepted in three places so it cannot be quietly forgotten:

1. **In the engagement document**, as a paragraph the client signs: *"This assessment covers only the
   systems listed above. If a system holding customer data is not on that list, it was not tested,
   and this report does not speak to it. The list came from you."*
2. **In the report's coverage section**, as a rendered list of every fact whose only support is the
   client's declaration — the `established_by: client-declared` set, already a vocabulary value in
   RG-1 §3.2. RG-4 makes the report print them rather than merely storing them.
3. **In `status.md` for the engagement**, as a count.

### 2.4 Two things deliberately rejected

**Rejected: cryptographic signing of the bundle.** Considered — a client keypair, a detached
signature, verification on ingest. Rejected because it authenticates the *channel*, and the channel
was never the threat: nobody is forging bundles, and a client who can be talked into signing a wrong
declaration can be talked into signing it with a key. It adds key management to a workflow whose
respondent may not know what a subdomain is. A typed name, role, date and attestation sentence in
`signature.txt`, countersigned by the operator into a PDF, carries the same legal weight and zero
setup. Revisit if a client's own procurement demands it.

**Rejected: hashes of documents as evidence of their content.** The bundle carries document hashes
(§5.4), and they are useful — they pin *which* file a fact came from and prove it has not changed
since. They are not evidence of what the file says, because the operator cannot open it. Do not let
a hash manifest read as verification in any deliverable. It is a chain-of-custody record for a
dispute, nothing more.

---

## 3. The field list — what the questionnaire must extract

Derived by working backwards from four consumers: `new_engagement.py`'s `required=True` arguments and
its three refusals; `scope.py`'s `parse()` validation; RG-1 §3.1's required `environment` keys; and
§15.1's platform-authorisation checklist.

**Required (R)** means some consumer refuses without it. **Conditional (C)** means required on a
branch. **Optional (O)** means it improves the engagement and its absence blocks nothing.

### 3.1 Block A — who is answering, and can they authorise this

The most consequential block in the questionnaire, asked **first**, because a negative answer ends
the session before anyone spends thirty minutes on it. No field in this block has a home in
`scope.yaml` today — see **D-3**.

| # | Field | R/O | Question, as a non-technical respondent reads it |
|---|---|---|---|
| A1 | `respondent.name` | R | "What's your full name?" |
| A2 | `respondent.role` | R | "What's your role at the organisation?" |
| A3 | `respondent.can_bind` | R | **"Are you able to sign contracts on behalf of the organisation — or authorise someone to do work that affects its systems? If you're not sure, the test is: could you approve this spend and this access without asking anyone else?"** |
| A4 | `authority.holder_name` / `authority.holder_role` | C — required when A3 is *no* or *unsure* | "Who can? We'll need their name and role, and they'll need to be the one who signs." |
| A5 | `authority.others_required` | R | "Is there anyone else whose sign-off you'd normally need for something like this — a co-founder, a board, a parent company, a client whose data you hold? List anyone, even if you think it's a formality." |
| A6 | `owner.is_client` | R | "Are the systems we'd be testing owned and run by your organisation? Not a system you use as a customer — for example, you can authorise us to test your own website, but not your accounting software vendor's." |
| A7 | `signer.name` / `signer.role` / `signer.email` | R | "Who will sign the engagement document?" (defaults to A1 when A3 is yes) |
| A8 | `signature.attestation` | R | Typed verbatim, not a checkbox: *"I have authority to authorise security testing of the systems listed in this document on behalf of \<organisation\>, and the list is accurate to the best of my knowledge."* |

**Why A3 is phrased as a spend-and-access test rather than "do you have authority".** Asked
abstractly, almost everyone says yes; asked as "could you approve this without asking anyone", people
answer accurately, because it maps onto a decision they have actually had to make. A5 exists because
A3 catches the respondent's *own* authority and misses the *organisation's* constraints — the founder
who can bind their company but whose enterprise customer's contract forbids third-party testing of a
system holding that customer's data. A5's answer never blocks by itself; it produces a line in the
engagement document and an operator flag.

**A6 is the over-declaration guard at the source.** The Shopify-tenant case, the marketplace-listing
case and the "our website, built by an agency who still hosts it" case all fail here, and all three
are common. A6 *no* does not end the session; it routes to A6a: *"Who does run it? We'd need their
written permission too, and we can help you ask for it."*

### 3.2 Block B — the organisation and the engagement envelope

| # | Field | R/O | Question |
|---|---|---|---|
| B1 | `client.name` | R | "What's the organisation's full legal name, as it appears on an invoice?" |
| B2 | `client.contact` | R | "What email address should we use for anything about this work?" |
| B3 | `client.slug` | R (derived) | Not asked. Generated from B1, shown back for confirmation: "We'll refer to this engagement as `acme-2026-08`. OK?" |
| B4 | `authorization.window_start` / `window_end` | R | "What two-week period would suit for the testing? We need a start and an end date. We won't touch anything outside those dates." |
| B5 | `authorization.emergency_contact` | C — required for `redteam` (enforced by `scope.parse()`); O otherwise, strongly recommended | "If something breaks at 2am during the testing window, who do we ring? Name and phone number." |
| B6 | `constraints.testing_window` | O | "Are there times of day, or days, when we should stay off your systems? For example, if you have a busy period, or an overnight batch job." |
| B7 | `notification.internal_done` | R | "Have you told the people who'd notice? Your on-call, your hosting provider's support, anyone who watches alerts. Security testing looks exactly like an attack in the logs." |
| B8 | `constraints.forbidden_actions` | O | "Is there anything you want to put explicitly off-limits, even if it's technically part of the systems above?" |

**B7 is required and has no field in `scope.yaml`.** It goes in the engagement document and in the
operator's pre-flight. A `no` does not block; it produces a prerequisite line — *"before we start, you
need to notify X"* — and the operator's kickoff confirms it. The reason it is required rather than
optional: an unannounced test that pages an on-call engineer at 3am is the fastest way to turn a
client into a former client, and it costs one question.

### 3.3 Block C — what may be touched

This block produces `in_scope`, `out_of_scope` and `crown_jewels`. Every entry produced here must
carry provenance `stated` or `stated-confirmed` (§5.3); nothing derived from a document alone may
land here.

| # | Field | R/O | Question |
|---|---|---|---|
| C1 | `in_scope[]` — web addresses | R (≥1 entry; `new_engagement.py` refuses an empty boundary) | "List every web address you'd like us to look at — the whole thing, like `https://app.example.com`. Include anything customers log into, and any admin or staff area." |
| C2 | `in_scope[]` — subdomain wildcard consent | R | "Do you want us to look at *everything* under `example.com`, including addresses you might have forgotten about? We often find things people didn't know were public. Answer yes only if you're confident you own every address under that domain." |
| C3 | `out_of_scope[]` | R (may be empty, must be asked) | "Is there anything under those addresses that is **not** yours, or that we must leave alone? A blog someone else runs, a status page, a shop on someone else's platform, a partner's system." |
| C4 | `in_scope[]` — backend project ids | C — custom-app branch | "If your app has a database or backend service — Supabase, Firebase, something like that — what's the project name or ID? You'll find it in the URL when you're logged into its dashboard." |
| C5 | `in_scope[]` — source code | O | "Would you like us to read the source code as well? It roughly doubles what we find. If yes, what's the repository, and can you give read access to one account for the two weeks?" |
| C6 | `in_scope[]` — mobile apps | O | "Do you have a mobile app? If so, on which stores, and what's it called there?" |
| C7 | `platforms[]` | R | "Which of these are you using? Squarespace / Shopify / Wix / WordPress / Webflow / Vercel / Netlify / AWS / Google Cloud / Azure / Supabase / Firebase / other. Tick everything that applies." |
| C8 | `platforms[].aup_position` | R (operator-resolved, client-informed) | Not asked of the client. Resolved by the operator against each platform's acceptable-use policy per §15.1, recorded per platform, shown in the engagement document. The client's question is only C8a: "Do you have an enterprise or business agreement with any of these, rather than a normal signup?" |
| C9 | `crown_jewels[]` | R | "If someone got into your systems, what would be the worst thing for them to reach? Answer in plain words — 'our customer list', 'the payment records', 'the photos people upload'. This is what we'll aim at first." |

**C7 exists because of §15.1, and it is the question a technical scoping form usually omits.** The
client cannot authorise what the client does not control. The answer determines whether testing is
confined to the application layer, whether a provider needs notifying, and whether a reference number
must be recorded — three facts §15.1 requires and `scope.yaml` currently has nowhere to put (**D-3**).

**C2's phrasing carries a deliberate warning.** A wildcard is the most useful in-scope entry and the
most dangerous. Naming the failure inside the question is cheaper than any check available
afterwards, and it is followed at review time (§2.2 layer 3) by reading the enumerated list back.

### 3.4 Block D — the environment (RG-1's required fact)

RG-1 §3.1 makes `environment` a required `scope.yaml` key and a Gate 1 refusal when absent, empty,
`unknown`, or unrecognised. **This block is where that fact comes from**, and it is the strongest
single argument for the questionnaire existing at all rather than being an email thread.

| # | Field | R/O | Question |
|---|---|---|---|
| D1 | `environment` | R | "Which of these are we testing? (a) the live site your real customers use; (b) a copy of it used for testing, with fake data; (c) a version running on a developer's machine; (d) a temporary preview of a change. If you're not sure, say so — we'd rather record 'not sure' than guess." |
| D2 | `environment_established` | R (derived) | Always `client-declared` for a bundle-sourced engagement. Not asked. |
| D3 | `environment_source` | R (derived) | Back-pointer to D1's answer id: `scoping-bundle/answers.jsonl#D1`. Not asked. |
| D4 | `env.is_separate` | C — asked when D1 is (b), (c) or (d) | "Is that copy completely separate from the live one, or do they share anything — the same database, the same file storage, the same email sending?" |
| D5 | `env.delta_available` | C — as above | "Is there someone who could tell us how the copy differs from the live site? We'll ask them about a dozen specific things." (Routes to §8) |
| D6 | `assets[].signup_open` | R | "Can anyone create an account on your system without you approving it?" |
| D7 | `reachable_population` | O | "Who can reach these systems at all — anyone on the internet, or only people on your office network or VPN? If it's restricted, roughly how many people is that?" |

**D1's option list is the vocabulary in plain words, and the "say so" clause is load-bearing.**
`scope.py` makes `unknown` *a legal value to type and an illegal value to proceed on* precisely so
that not knowing is representable. A question that pressures a respondent toward an answer
manufactures the false client declaration that comment exists to prevent. D1 must make "not sure"
feel like a normal answer, and the skill must never suggest one.

**D6 defaults to `true` when unanswered** (RG-1 §3.1) — the value that makes `public-account` cheapest
and severity highest. The plain-English phrasing is also more reliable than the field name: founders
answer "can anyone sign up" correctly and answer "is signup open" inconsistently.

### 3.5 Block E — how far we may go

Produces `mode` and `ceiling`. **The client is never asked for a tier number.** They are asked three
consequence questions and the skill derives the pair.

| # | Field | R/O | Question |
|---|---|---|---|
| E1 | `permit.writes` | R | **"Is it acceptable for us to create test records in your live system? For example: signing up a test account, submitting a test order, sending a test message. Everything we create is obviously labelled `RedGold-TEST-…` and we give you a list and a single query to delete it all — but some of it may briefly be visible to your staff, and some may not be removable."** |
| E2 | `permit.rate_testing` | R | "Is it acceptable for us to send a burst of rapid requests to check that your system limits them? This is how we test whether someone can brute-force your login. It may set off alerts, and on a small server it may slow the site for a minute." |
| E3 | `permit.exploitation` | R | "If we find a way in, do you want us to go through it and show you how far it reaches — or stop at the door and describe what we found? Going through proves the impact. It also means we're inside your system doing what a real attacker would do." |
| E4 | `fanout.known` | R | "Do any of your forms or sign-ups trigger something outside your system — an email to a customer, a text message, a Slack alert, a record in a CRM, a charge to a card?" |
| E5 | `permit.credentials` | O | "Can you give us login accounts to test with? Ideally one of each kind — a normal customer, and a staff or admin account. Use throwaway accounts, not real people's." |

Derivation, mechanical and stated in the engagement document so the client can check it:

| E1 | E2 | E3 | → `mode` | → `ceiling` |
|---|---|---|---|---|
| no | no | stop at door | `posture` | 1 |
| yes | yes | stop at door | `audit` | 2 |
| yes | yes | go through | `redteam` | 3 — **plus** B5 emergency contact, which `scope.parse()` enforces |
| no | yes | — | — | contradiction: rate testing requires writes. Routed to §7.2, not resolved by the skill |

**E4 changes the boundary regardless of E1.** §6.1: *"Any endpoint with known or suspected fan-out is
tier 3, not tier 2."* So an E4 `yes` produces a named `forbidden_actions` entry for that flow rather
than raising the ceiling — the flow is excluded, and the engagement document says which one and why.
This is the highest-value question in Block E and the one a client would never volunteer, because the
fan-out is invisible from their side too.

**Rejected phrasing: "what blast-radius tier do you authorise?"** Unusable, and worse, unauditable — a
client who ticks "tier 2" has not consented to anything, because they were never told what tier 2
does to them. The consequence questions are what make the authorisation real rather than formal.

### 3.6 Block F — data, for the report's impact statements

Feeds `crown_jewels`, `data_classes[]` and the report's impact sentences. **Nothing in this block may
produce a legal conclusion** — hard rule 1, and `privacy-act-feasibility.md` §5. The skill records
what data exists; it never states an obligation, never names a statute, never says "notifiable", and
never uses the word "compliant".

| # | Field | R/O | Question |
|---|---|---|---|
| F1 | `data_classes[]` | R | "Which of these do you hold about your customers or staff? Names and contact details / addresses / dates of birth / payment card details / bank details / government ID numbers (licence, passport, tax file) / health information / location data / photos or uploads / message content / anything about children under 18." |
| F2 | `data.volume_band` | O | "Roughly how many people's records are in there? Under 100 / hundreds / thousands / tens of thousands / more." |
| F3 | `data.recipients` | O | "Which outside services receive customer data? Payment processor, email tool, analytics, support desk, anything AI." |
| F4 | `prior_testing` | O | "Has anyone tested these systems before? If yes, when, and by whom? Don't send us the report yet — we'll ask for it separately if it's useful." |

F3 is a `CROSS-CHECK` question in the sense of `privacy-act-feasibility.md` §6.2: it deliberately
overlaps something the operator can observe, and **the delta is the finding**. The client says "just
Google Analytics"; the operator's surface pass sees six recipients. The finding is not that the
client lied — it is that their recorded understanding of where customer data goes is incomplete.

**F4 deliberately does not collect the prior report.** It is exactly the class of document the
operator may not hold, it is frequently under an NDA the client cannot unilaterally waive, and its
findings would bias the engagement toward reproduction rather than discovery. Record its existence
and date; request it later, deliberately, under its own terms.

### 3.7 Coverage check against the consumers

Every `required=True` argument of `new_engagement.py`, and where it comes from:

| `new_engagement.py` argument | Source |
|---|---|
| `--client` | B3 (derived from B1) |
| `--date` | B4 (`window_start`'s year-month) |
| `--client-name`, `--client-contact` | B1, B2 |
| `--auth-document` | The countersigned engagement document. **The operator saves it; the bundle never supplies a path** (§6.1) |
| `--signed-by` | A7 |
| `--signed-date` | Date of signature, filled at countersign by the operator, not by the client |
| `--window-start`, `--window-end` | B4 |
| `--environment` | D1 |
| `--in-scope` (≥1) | C1–C6 |
| `--mode`, `--ceiling` | E1–E3 derivation |
| `--python`, `--root` | The operator's machine. Never in the bundle |

Required by RG-1 §3.1 but **not implemented in `scope.py` today**: `environment_established`,
`environment_source`, per-asset `environment`, per-asset `signup_open`. RG-4 produces all four and
they currently have nowhere to land — **D-4**.

Required by §15.1 but **not implemented in `scope.py` today**: platform list, per-platform AUP
position, provider notification state and reference number — **D-3**.

---

## 4. Branching, and what was cut

### 4.1 The cut rule, stated before the structure

> **A question survives only if (a) some consumer refuses without its answer, or (b) its answer
> changes what gets touched. Everything else moves to the operator's kickoff call.**

This is the whole design of the branching. It is a deliberately harsh rule and it removes most of
what a conventional scoping form asks: team size, tech stack detail, framework versions, CI provider,
deployment frequency, ticketing system, previous incidents, security budget, compliance goals. Every
one of those is interesting; none of them changes what may be touched, and none of them makes
`/rg:new` refuse. The operator learns the stack in recon, faster and more accurately than the client
can describe it.

The failure being designed against is not incompleteness — it is **abandonment**. A questionnaire that
takes two hours is not completed, and an uncompleted questionnaire produces a verbal authorisation,
which is exactly the state blocker B-1 describes. Target: **25 minutes, 22 core questions, at most 8
on any one branch, never more than two levels deep.**

### 4.2 The structure

One root branch, taken from a single question, plus two orthogonal add-ons.

```
                         ┌── Block A (authority)  ── 8 q, always, first
                         ├── Block B (envelope)   ── 8 q, always
      ROOT QUESTION ─────┤
      "Which best        ├── Block C/D/E/F        ── core, always, but
       describes what    │        branch-shaped   ── phrasing and defaults differ
       we'd be           │
       looking at?"      └── one of three branches, ≤8 q each
                                 │
       ┌─────────────────────────┼──────────────────────────┐
       │                         │                          │
   BRANCH 1                  BRANCH 2                  BRANCH 3
   Hosted site               Custom product            "I'm not sure"
   (Squarespace, Shopify,    (you or your team         │
    Wix, WordPress,           wrote the code;          └── 3 orienting questions,
    Webflow)                  it has a login)              then routes to 1 or 2,
                                                           or stops (§7.3)

   ADD-ON M1: mobile app       (3 q, offered when C6 = yes)
   ADD-ON M2: source code      (4 q, offered when C5 = yes)
```

**The root question, in the client's words:** *"Which of these is closest? (1) A website or online
shop built on a platform like Squarespace, Shopify, Wix or WordPress — you edit it, but you didn't
write the code. (2) A product you or your team built, that people log into. (3) I'm honestly not
sure."*

### 4.3 What differs between branches, and what does not

| | Branch 1 — hosted site | Branch 2 — custom product |
|---|---|---|
| `environment` (D1) | Almost always `production`; there is no staging. **D1 is still asked** — never inferred | Genuinely varies; D4/D5 fire, §8 usually runs |
| Backend project ids (C4) | Skipped | Asked |
| Platforms (C7) | The platform *is* the system. AUP position dominates the engagement and may confine it to the application layer entirely | Usually a hosting platform plus a data platform; two AUP positions |
| Writes (E1) | Framed around **orders and customer records**: "a test order will appear in your orders list and may email you" | Framed around **accounts and records**: "a test account will appear in your user list" |
| Fan-out (E4) | Near-certain yes — order confirmation emails, abandoned-cart, review requests. Ask which, not whether | Genuinely varies |
| Typical outcome | `posture` / ceiling 1 or `audit` / ceiling 2 | `audit` / ceiling 2 |
| Extra questions | *"Do you have any custom code or apps installed on the platform?"* and *"Can customers create accounts, or is it checkout-only?"* | *"Does one customer's data live alongside another's in the same database?"* (multi-tenancy — it changes what an access-control failure means) |

Everything in Blocks A, B, D, E and F is asked on both branches with the same field names and
different wording. **The bundle schema is identical across branches.** A branch changes the words and
the defaults, never the shape of the output — otherwise `rg4_ingest.py` needs a parser per branch,
and a parser per branch is where an unvalidated field slips in.

### 4.4 What was cut, and the alternative rejected

**Rejected: a branch per backend platform** (Supabase / Firebase / custom Postgres / Rails / Django).
The strongest argument for it is that each has a distinct and well-known misconfiguration class —
Supabase RLS, Firebase security rules, exposed admin panels. Rejected because those change **how the
operator tests**, not **what the operator is permitted to touch**, and only the second is the
questionnaire's job. The knowledge belongs in a playbook, keyed off `platforms[]` from C7, and the
operator loads it after recon confirms the platform anyway. Keeping it in the questionnaire would
have added roughly forty questions across five branches to produce information the operator obtains
in ten minutes with better accuracy.

**Rejected: adaptive depth — "ask more when the answers look complex."** Attractive, and it is the
thing an LLM-driven questionnaire is uniquely able to do. Rejected for this version because it makes
the questionnaire's output non-deterministic in length, which makes it impossible to tell a client
how long it takes, which is the promise the 25-minute target depends on. It also makes two bundles
from two clients structurally incomparable. Revisit once there is data on where real bundles come
back incomplete — **D-10**.

**Rejected: the compliance module in v1.** `privacy-act-feasibility.md` §6 sketches a governance
questionnaire sharing this machinery, and it should eventually be add-on M3. Not in v1: Subsystem F
is entirely `[VERIFY]`, and a compliance question inside a client-facing artifact is the single most
likely place for hard rule 1 to be broken — the question *"do you have a privacy policy?"* is
harmless, and the sentence that follows it in a generated document is not. Block F collects the data
classes the compliance module will need, and stops there.

**Cut but worth naming**: uptime/SLA expectations, backup and restore posture, incident response
plan, MFA posture, employee offboarding. All belong in the `posture` engagement's own governance
review (§6.2), asked by the operator, evidenced, and reportable as `governance` findings. Asking them
in a scoping questionnaire produces client assertions with no evidence attached — precisely the
`ASSERTED_NO_ARTIFACT` failure `privacy-act-feasibility.md` §6.4 warns about — and they would arrive
looking like established facts.

---

## 5. Documents — extraction, provenance, and what must never be inferred

### 5.1 What the client may supply

Architecture diagrams, a privacy policy, a data inventory or ROPA, prior pentest reports, an asset
spreadsheet, infrastructure-as-code, a screenshot of a hosting dashboard, an internal wiki page.

The skill **reads all of them**. It is running on the client's machine, in the client's Claude, on the
client's own files, with the client's consent. There is no reason to restrict reading, and §1.2
already establishes that model inference over these documents is acceptable to the operator. The
entire control surface is **what lands in the bundle**, because the bundle is the only thing that
crosses.

### 5.2 What is extracted, and what is never extracted

| Extracted into the bundle | Never extracted |
|---|---|
| Host names, domains, wildcards | Any prose quotation longer than an identifier |
| Repository and cloud project identifiers | Credentials, keys, tokens, connection strings — **in any form, including redacted** |
| Platform and vendor names | Employee names other than the signer and the technical contact |
| Environment names as written (`staging`, `prod-au`) | Customer data of any kind |
| Data class names present in a schema or inventory | Row counts from a real table (band it, per F2) |
| Dates, and the existence of a prior test | Prior findings, their titles, their severities |
| A one-line description of what each document is | The document itself, or any excerpt of it |

**Credentials are excluded even when redacted**, because a redacted credential in a bundle is still a
statement that a credential exists at a named location, and §15.2 already routes credentials outside
both repos by path.

**Prior findings are excluded** for the reason in §3.6 F4, and additionally because a prior report's
findings arriving in a scope record would enter the engagement as facts with no evidence pointer —
they would be indistinguishable from RedGold's own findings by the time they reached `report.py`.

### 5.3 Provenance — three values, and one of them may never drive scope

Every row in `answers.jsonl` carries exactly one:

| `provenance` | Means | May appear in `in_scope` / `environment` / `mode` |
|---|---|---|
| `stated` | A human typed it in answer to a question | **Yes** |
| `stated-confirmed` | The skill proposed it from a document; the human read the proposal and said yes | **Yes** — and this is the only path from a document into the boundary |
| `document` | Read from a supplied document; never put to the human, or put and not confirmed | **No. `rg4_ingest.py` refuses the bundle** |

A fourth value, `document-inferred` — a fact the model concluded from a document rather than read in
it — is **not in the vocabulary and must not be added**. Its absence is the point: if the skill cannot
label an inference, it cannot smuggle one in. An inference from a document is put to the respondent as
a question or it does not exist.

**The conversion rule, which is the whole of §5:**

> A document-derived fact is a **proposal**, never an answer. It is rendered back to the respondent in
> their own terms, with its source named, and only their explicit yes converts it to
> `stated-confirmed`.

Rendered as: *"Your architecture diagram (`architecture-v3.png`) appears to show a service at
`api-staging.example.com`. Two questions: is that yours, and should we test it?"* — never as
*"I've added `api-staging.example.com` to the list."* The difference is that the first is answerable
by a person who does not read diagrams, and the second is not.

**Why this matters more than it looks.** A fact typed by a respondent is a claim they will be shown
again at review (§2.2 layer 3) and will sign for. A fact lifted from a diagram is a claim by a
document of unknown age, drawn by someone who may have left, describing an intended architecture
rather than a deployed one. Architecture diagrams are wrong constantly and in a specific direction:
they show what was designed, not what was clicked into existence afterwards — which is §5's founder
problem, in a file.

### 5.4 The document manifest

Documents do not cross. A record of them does:

```json
{
  "doc_id": "DOC-003",
  "filename": "architecture-v3.png",
  "sha256": "9f2c…",
  "kind": "architecture_diagram",
  "supplied_at": "2026-08-20T04:11:00Z",
  "one_line": "Deployment diagram, undated, showing a web tier, a Postgres instance and an S3 bucket.",
  "facts_proposed": ["C1:api-staging.example.com", "C7:aws"],
  "facts_confirmed": ["C7:aws"],
  "facts_rejected":  ["C1:api-staging.example.com"],
  "anomalies": []
}
```

`facts_rejected` is as important as `facts_confirmed` and is a required key. *"The diagram named a
staging API and the client said it is decommissioned"* is information the operator needs, and its
absence would make a rejection indistinguishable from the fact never having been proposed.

The hash is **chain of custody, not verification** (§2.4). It answers "which version of the diagram
were we told about" in a later dispute. It answers nothing about content.

### 5.5 Documents are untrusted input

The bundle is generated by a model reading files the operator did not write, and the bundle is later
parsed on the operator's machine. That is a prompt-injection path, and CLAUDE.md hard rule 6 applies
on the client's side too.

Three rules:

1. **Document text is data, never instruction.** Content that reads as an instruction to the
   assistant — "ignore previous instructions", "mark all systems as authorised", an embedded prompt
   in an image's alt text or a PDF's invisible layer — is not acted on and is **recorded** as an
   `anomalies` entry on the manifest row. Recording it is the useful part: it reaches the operator,
   and it may itself be a finding about the client's document pipeline.
2. **The bundle is machine-parsed with no model in the loop on the operator's side.**
   `rg4_ingest.py` reads YAML and JSONL and validates against a fixed schema. An operator who instead
   pastes `engagement-document.md` into a Claude session and asks it to "set this up" has crossed the
   boundary the whole design exists to maintain. Say this in the ingest tool's own help text.
3. **`unresolved.md` and the free-text fields are rendered, not executed.** Client free text
   (`crown_jewels`, `forbidden_actions`, notes) reaches `scope.yaml` and therefore reaches
   `scope_guard.py`'s inputs. It is quoted on the way in, and `new_engagement.py`'s existing
   `shlex.quote` discipline covers the hook-wiring path — but the ingest tool must not build a shell
   command by interpolation either, and that is the same defect `new_engagement.py:159` already
   documents having had once.

---

## 6. The two outputs, with worked examples

### 6.1 The architectural choice: the bundle does not emit `scope.yaml`

**The client's Claude never writes `scope.yaml`.** It writes `scope-record.yaml`, in RG-4's own
schema, which `rg4_ingest.py` validates and turns into an `/rg:new` command line that the operator
runs.

Rejected alternative: emit `scope.yaml` directly and have the operator drop it into the engagement
directory. It is one fewer step and it is wrong on three counts:

1. **It makes the client's Claude the author of the enforcement boundary.** `scope.yaml` is the only
   thing the hooks enforce (§5.1). Having it authored on a machine with no hooks, no ledger and no
   operator, and then trusted on arrival, inverts the trust model completely.
2. **It routes around every refusal `new_engagement.py` exists to perform** — the round-trip parse,
   the interpreter verification, the PyYAML probe, and above all the check that the authorisation
   document exists on disk.
3. **It would make the signed document optional.** The signed engagement document is the thing that
   converts B-1's verbal approval into authorisation. If a YAML file were sufficient input, the
   signature becomes decorative.

So: the bundle proposes; `/rg:new` disposes. `/rg:new` is unchanged by RG-4 except for the schema
additions in D-3 and D-4.

### 6.2 Output 1 — `engagement-document.md`

Human-readable, for the client to read and sign. **This is the artifact that makes authorisation real
rather than verbal**, and it becomes `--auth-document` once countersigned.

Required sections, in order, with the rule governing each:

| § | Section | Rule |
|---|---|---|
| 1 | **What this document is** | One paragraph. States that signing it authorises security testing, and that it is not a contract for services — the contract is separate (§15.7) |
| 2 | **Who is authorising** | A1–A7 rendered. Names the signer, their role, their stated authority, and anyone A5 named whose sign-off may also be required |
| 3 | **What we will touch** | The enumerated in-scope list, **expanded** — a wildcard is rendered as "every address under `example.com`, which today includes: …" with the client's own enumeration, not a pattern |
| 4 | **What we will not touch** | `out_of_scope`, plus the standing exclusions: no other organisation's systems, nothing outside the window, nothing above the ceiling |
| 5 | **What we will do** | The tier table in plain English, showing only the tiers the ceiling permits, each with its concrete consequence. Ceiling 2 says "we will create test records"; ceiling 1 says "we will not write anything" |
| 6 | **When** | The window, the testing hours, and the statement that nothing happens outside them |
| 7 | **What could go wrong** | See below. Mandatory, and specific |
| 8 | **What you need to do before we start** | B7 notification, E5 credentials, provider notifications from C7/C8, and any dev environment from §8 |
| 9 | **What this assessment cannot tell you** | The §2.3 residual, the environment delta if any (§8.4), and the list of facts accepted on the client's word |
| 10 | **Signature** | The A8 attestation typed verbatim, name, role, date, and the operator's countersignature line |

**§7 "What could go wrong" is mandatory and must be specific to this engagement's derived ceiling.**
A generic risk paragraph is not informed consent. Rendered from the answers:

> - Test accounts and test orders will appear in your systems. They are labelled `RedGold-TEST-…` and
>   we will give you a list and a single query that removes them. Some may not be removable — for
>   example if a delete is refused by your own permission checks. Anything left behind is listed in
>   the report.
> - Because you told us the checkout sends a confirmation email (E4), we have excluded the checkout
>   from testing entirely. That means this assessment does not cover your payment flow.
> - Rate-limit testing will send several hundred requests in a few seconds. This may trigger alerts,
>   may briefly slow the site, and may temporarily lock the test account.
> - Security testing looks like an attack in logs. If your hosting provider auto-suspends on abuse
>   signals, tell them the dates before we start.
> - We may see real customer data while proving that an access-control flaw exists. We take the
>   smallest observation that proves it and stop. Anything we do see is recorded, minimised, and
>   destroyed on the schedule in §5.

**§9 must exist even when there is nothing to put in it**, and in that case says so. A limitations
section that appears only when things went badly teaches the reader to skim it.

**Hard rule 1 applies to this document with full force.** It may state facts about data the client
holds. It may **not** state that an obligation applies, name a statute, use "compliant",
"notifiable", or "breach" in a legal sense, or imply that passing the assessment has any regulatory
effect. `rg4_ingest.py` runs a literal word-list check over the generated document for exactly these
terms and refuses on a hit — cheap, mechanical, and a lint rather than a judgement (**D-8**).

### 6.3 Output 2 — `scope-record.yaml`

Machine-readable. Every field carries `from:`, the answer id that produced it, so §2.2 layer 2 is
checkable without a model.

### 6.4 Worked example A — retail business, Squarespace and Shopify

Branch 1. Respondent is the owner. No staging environment exists, so `environment: production` and
the ceiling drops to 1 — the operator is not writing test orders into a live shop that emails
customers.

```yaml
# scoping-bundle/scope-record.yaml
schema: rg4/1
status: complete                      # `incomplete` when any REQUIRED field is unresolved (§7)
generated: 2026-08-20T05:40:00Z
generated_by: rg-scoping/1 (client-side)

authority:
  respondent:  {name: "Dana Reid", role: "Owner", from: A1}
  can_bind:    {value: true, from: A3}
  others_required: {value: [], from: A5}
  owner_is_client: {value: true, from: A6}
  signer:      {name: "Dana Reid", role: "Owner", email: "dana@northbay.example", from: A7}
  attestation: {typed: true, text_hash: "sha256:4c1e…", from: A8}

client:
  name:    {value: "Northbay Interiors Pty Ltd", from: B1}
  contact: {value: "dana@northbay.example", from: B2}
  slug:    {value: "northbay", from: B3}

window:
  start: {value: 2026-09-01, from: B4}
  end:   {value: 2026-09-12, from: B4}
  testing_window: {value: "weekdays 09:00-16:00 AEST, not Saturdays", from: B6}
  emergency_contact: {value: "Dana Reid +61 4xx xxx xxx", from: B5}
  internal_notification_done: {value: false, note: "Dana to email Shopify support", from: B7}

environment:
  value: {value: production, from: D1}
  established: client-declared
  source: "scoping-bundle/answers.jsonl#D1"
  separate_copy_exists: {value: false, from: D4}

in_scope:
  - {asset_type: URL,      pattern: "https://www.northbay.example",  provenance: stated, from: C1}
  - {asset_type: URL,      pattern: "https://shop.northbay.example", provenance: stated, from: C1,
     note: "Shopify storefront on a custom domain"}
out_of_scope:
  - {asset_type: URL, pattern: "https://blog.northbay.example", provenance: stated, from: C3,
     note: "client states this is run by their marketing agency"}

wildcard_consent: {value: false, from: C2}

platforms:
  - {name: squarespace, aup_position: unresolved, notified: false, reference: null, from: C7}
  - {name: shopify,     aup_position: unresolved, notified: false, reference: null, from: C7}
# aup_position is resolved by the OPERATOR before /rg:new. `unresolved` here is correct and honest.

assets_facts:
  signup_open: {value: true, from: D6, note: "customers can create accounts at checkout"}
  reachable_population: {description: "anyone on the internet", established_by: client-declared, from: D7}

permissions:
  writes:        {value: false, from: E1, note: "a test order would email a real confirmation"}
  rate_testing:  {value: false, from: E2}
  exploitation:  {value: "stop at door", from: E3}
  fanout:        {value: true, from: E4,
                  detail: "checkout sends order confirmation; newsletter form sends welcome email"}
  credentials_available: {value: false, from: E5}

derived:
  mode: posture
  ceiling: 1
  derivation: "E1=no, E2=no, E3=stop-at-door -> posture/1 (§3.5 table row 1)"
  forbidden_actions:
    - {value: "any checkout or order submission", because: "E4 fan-out: customer email"}
    - {value: "newsletter signup submission",     because: "E4 fan-out: welcome email"}

crown_jewels:
  - {value: "our customer list and their addresses", from: C9}
  - {value: "the card payments in Shopify",          from: C9}

data_classes: {value: [names_contact, addresses, payment_card_details], from: F1}
data_volume_band: {value: "thousands", from: F2}
prior_testing: {value: none, from: F4}

documents: []
unresolved: []
```

The `/rg:new` line `rg4_ingest.py` emits from it:

```
/usr/bin/python3 scripts/new_engagement.py \
  --client northbay --date 2026-09 \
  --client-name "Northbay Interiors Pty Ltd" --client-contact dana@northbay.example \
  --auth-document ~/engagements/_auth/northbay-signed-roe-2026-08-25.pdf \
  --signed-by "Dana Reid" --signed-date 2026-08-25 \
  --window-start 2026-09-01 --window-end 2026-09-12 \
  --emergency-contact "Dana Reid +61 4xx xxx xxx" \
  --mode posture --ceiling 1 --environment production \
  --in-scope 'URL:https://www.northbay.example' \
  --in-scope 'URL:https://shop.northbay.example' \
  --out-of-scope 'URL:https://blog.northbay.example|client states run by their marketing agency' \
  --crown-jewel "our customer list and their addresses" \
  --crown-jewel "the card payments in Shopify" \
  --forbid "any checkout or order submission" \
  --forbid "newsletter signup submission" \
  --testing-window "weekdays 09:00-16:00 AEST, not Saturdays"
```

Note what the operator still has to do by hand, and why that is correct: resolve both AUP positions,
countersign, save the PDF, and fill `--signed-date`. None of those are the client's to assert.

### 6.5 Worked example B — startup, Next.js on Vercel with Supabase

Branch 2, with add-on M2 (source code). A staging environment exists; §8 runs and produces an
environment delta. The interesting part of this example is that the delta, not the scope record, is
where most of the value lands.

```yaml
schema: rg4/1
status: complete
generated: 2026-08-20T06:15:00Z

authority:
  respondent:  {name: "Sam Okonkwo", role: "Co-founder and CTO", from: A1}
  can_bind:    {value: true, from: A3}
  others_required: {value: ["co-founder (CEO) — informed, not required"], from: A5}
  owner_is_client: {value: true, from: A6}
  signer:      {name: "Sam Okonkwo", role: "Co-founder and CTO", email: "sam@wavelet.example", from: A7}
  attestation: {typed: true, text_hash: "sha256:b70a…", from: A8}

client:
  name:    {value: "Wavelet Labs Pty Ltd", from: B1}
  contact: {value: "sam@wavelet.example", from: B2}
  slug:    {value: "wavelet", from: B3}

window:
  start: {value: 2026-09-08, from: B4}
  end:   {value: 2026-09-19, from: B4}
  emergency_contact: {value: "Sam Okonkwo +61 4xx xxx xxx", from: B5}
  internal_notification_done: {value: true, from: B7}

environment:
  value: {value: staging, from: D1}
  established: client-declared
  source: "scoping-bundle/answers.jsonl#D1"
  separate_copy_exists: {value: true, from: D4}
  shares_with_production: {value: ["object storage bucket"], from: D4}   # -> §8, and a finding
  delta_contact: {value: "Priya N., platform engineer", from: D5}
  delta_ref: "scoping-bundle/environment-delta.yaml"

in_scope:
  - {asset_type: WILDCARD,         pattern: "*.staging.wavelet.example", provenance: stated, from: C2}
  - {asset_type: URL,              pattern: "https://app.wavelet.example", provenance: stated, from: C1,
     note: "production, read-only observation only — see per_asset below"}
  - {asset_type: SUPABASE_PROJECT, pattern: "qzrtklmnopabcdef", provenance: stated-confirmed, from: C4,
     source_doc: "DOC-002", note: "proposed from infra README, confirmed by respondent"}
  - {asset_type: GITHUB_ORG,       pattern: "github.com/wavelet-labs", provenance: stated, from: C5}
out_of_scope:
  - {asset_type: URL, pattern: "https://status.wavelet.example", provenance: stated, from: C3,
     note: "hosted by a third-party status provider"}
  - {asset_type: URL, pattern: "https://wavelet.example", provenance: stated, from: C3,
     note: "marketing site, Webflow, out of scope by client request"}

per_asset:
  - {pattern: "*.staging.wavelet.example", environment: staging,    signup_open: true}
  - {pattern: "https://app.wavelet.example", environment: production, signup_open: true,
     ceiling_override: 1, note: "read-only. Narrowing only — never widens the engagement ceiling"}

wildcard_consent: {value: true, from: C2,
                   enumeration_confirmed: ["app.staging", "api.staging", "admin.staging"]}

platforms:
  - {name: vercel,   aup_position: unresolved, notified: false, reference: null, from: C7}
  - {name: supabase, aup_position: unresolved, notified: false, reference: null, from: C7}
  - {name: github,   aup_position: unresolved, notified: false, reference: null, from: C7}

permissions:
  writes:       {value: true, from: E1, note: "on staging only"}
  rate_testing: {value: true, from: E2}
  exploitation: {value: "stop at door", from: E3}
  fanout:       {value: true, from: E4,
                 detail: "staging sends real Slack alerts to #eng; email goes to a catcher"}
  credentials_available: {value: true, from: E5,
                          detail: "one member account and one org-admin account, on staging"}

derived:
  mode: audit
  ceiling: 2
  derivation: "E1=yes, E2=yes, E3=stop-at-door -> audit/2 (§3.5 table row 2)"
  forbidden_actions:
    - {value: "any action that posts to the #eng Slack channel", because: "E4 fan-out"}
    - {value: "any write against app.wavelet.example", because: "per-asset ceiling override 1"}

crown_jewels:
  - {value: "customer documents people upload", from: C9}
  - {value: "the list of who our customers are", from: C9}

data_classes: {value: [names_contact, message_content, uploads], from: F1}
data_volume_band: {value: "hundreds", from: F2}
data_recipients: {value: ["Stripe", "Postmark", "PostHog", "OpenAI"], from: F3}   # CROSS-CHECK
prior_testing: {value: {when: "2025-11", by: "a friend of the founder, informal"}, from: F4}

documents:
  - {doc_id: DOC-001, filename: "wavelet-architecture.excalidraw.png", sha256: "…",
     kind: architecture_diagram,
     facts_proposed: ["C1:api-internal.wavelet.example", "C4:qzrtklmnopabcdef"],
     facts_confirmed: ["C4:qzrtklmnopabcdef"],
     facts_rejected:  ["C1:api-internal.wavelet.example"],
     rejection_reason: "respondent states this was decommissioned in March",
     anomalies: []}
  - {doc_id: DOC-002, filename: "infra/README.md", sha256: "…", kind: internal_doc,
     facts_proposed: ["C7:vercel", "C7:supabase"], facts_confirmed: ["C7:vercel", "C7:supabase"],
     facts_rejected: [], anomalies: []}

unresolved:
  - {id: U-1, field: data_recipients, kind: NOTE,
     text: "Respondent unsure whether PostHog session replay captures form contents.
            Recorded as a question for the operator; does not block."}
```

Two things this example is meant to show.

**`app.wavelet.example` is in scope at a lower ceiling than the engagement.** This is the resolution
of §8's tension in one row: production is in the boundary for read-only observation of the things only
production can answer, and every write stays on staging. RG-1 §3.1 permits a per-asset environment
override **narrowing only**, and this uses the same discipline for the ceiling. It requires a
per-asset ceiling, which `scope.py` does not have — **D-5**.

**`shares_with_production: [object storage bucket]` is a finding before testing starts.** A staging
environment writing to the production bucket means a tier-2 write on staging can land in production
data. It belongs in `forbidden_actions` or the shared component leaves the boundary; either way the
operator decides before Gate 1, not after.

---

## 7. Refusal, contradiction, and "cannot determine"

### 7.1 The claim, and the honest version of it

The task asks that it be **impossible** for the skill to emit a scope record `/rg:new` would accept
when authority to authorise was not established.

**A Claude skill cannot make anything impossible.** It is a prompt. It has no hooks, it runs on a
machine the operator does not control, and a determined or confused user can talk it into writing any
file. Anything phrased as "the skill will refuse" is an instruction that usually holds and sometimes
does not. Under P1 that is not a control.

So the impossibility is relocated to where it can be mechanical. The honest formulation:

> **The skill's refusals are advisory. The property that is actually guaranteed is that a bundle
> lacking established authority cannot reach `scope.yaml`, because two mechanical checks on the
> operator's side stand between it and `/rg:new` — and one of them already exists and has never been
> weakened.**

The existing one is `new_engagement.py`'s refusal to scaffold without an authorisation document on
disk. **Nothing the client's Claude writes can satisfy it.** The client's Claude cannot create a file
on the operator's machine; only the operator saving a countersigned document does that. That single
refusal is the backstop for the entire authority question, it was built before RG-4 existed, and RG-4
must not add a path around it. Specifically: `rg4_ingest.py` **never emits
`--allow-missing-authorization`**, and its help text says why.

The new one is `rg4_ingest.py` itself (§7.5).

### 7.2 The three states of an answer

Inherited directly from `privacy-act-feasibility.md` §6.3, because it is the same problem and one
mechanism is better than two:

| State | Means | Effect on a REQUIRED field |
|---|---|---|
| `STATED` | The respondent answered | Proceeds |
| `EVIDENCED` | The answer is corroborated by a supplied document | Proceeds; recorded as stronger |
| `CANNOT_DETERMINE` | Not asked, don't know, contradicted, or refused | **Bundle is `status: incomplete`** |

`CANNOT_DETERMINE` carries a reason from a closed list: `NOT_ASKED`, `RESPONDENT_UNSURE`,
`CONTRADICTED`, `REQUIRES_SOMEONE_ELSE`, `REFUSED`, `OUT_OF_RESPONDENT_KNOWLEDGE`.

**Deliberately absent: a "probably" state.** The reasoning is `privacy-act-feasibility.md` §6.3's, and
it transfers exactly: the intermediate verdict is the one that does the reader no good. "Probably
production" is acted on as "production" and defended as "probably".

### 7.3 The rules, by failure shape

**(a) The respondent does not know.**
The field is written with its sentinel, never omitted and never guessed.

- `environment` unknown → the literal string `unknown`, which `scope.py` accepts and
  `gate_cli.cmd_approve` refuses at Gate 1. This is the design working as intended: the honest value
  is representable and unusable.
- Any other required field unknown → `CANNOT_DETERMINE` with a reason, and the bundle is
  `status: incomplete`.

**Omission is the failure mode being designed against, not the unknown.** An omitted field looks like
a question that was never asked; a sentinel looks like a question that was asked and not answered. The
first is invisible, the second is a refusal downstream. Every required field is present in the bundle
in every case.

**(b) The respondent contradicts themselves.**
The skill **records both answers verbatim, does not choose, and does not ask the respondent to
choose**. It writes a `CONTRADICTION` row into `unresolved.md` naming both answer ids, marks the
derived field `CANNOT_DETERMINE / CONTRADICTED`, and continues the questionnaire.

Not choosing is deliberate. The two live contradiction classes are:

- *"This is our live site" (D1) and "there are no real customers on it yet" (F2)* — resolvable, and
  the resolution matters: it is the difference between a production cap and no cap.
- *"No writes" (E1) and "yes to rate testing" (E2)* — the §3.5 row-4 case. Rate testing needs writes.

An LLM asked to reconcile these will reconcile them, plausibly, and the reconciliation will be
invisible in the output. Recording both and stopping is worse UX and better epistemics, and the
operator resolves it in one message on the kickoff call.

**(c) The answers make the engagement unauthorisable.**
**Hard stop.** The skill stops the questionnaire, emits no `scope-record.yaml` at all, and writes a
one-page `cannot-proceed.md` naming the reason and what would change it. Triggers:

| Trigger | Answers |
|---|---|
| No authority, and no one named who has it | A3 no/unsure **and** A4 empty |
| Not the client's system | A6 no **and** A6a names a third party whose permission is not held |
| Nothing in scope | C1, C4, C5, C6 all empty |
| Attestation not typed | A8 |
| Someone else's system named as a target | Any in-scope entry the respondent states is not theirs |

`cannot-proceed.md` is a genuinely useful artifact — it tells the client precisely what to get. For
the A4 case it says: *"the questionnaire needs to be completed by, or countersigned by, \<named
person\>."*

**(d) The answers make the engagement unsafe rather than unauthorisable.**
**Not a hard stop — an operator escalation.** The bundle is emitted, `status: incomplete`, with a
`REQUIRES_OPERATOR_DECISION` row. The skill must not decide these, because they are commercial and
professional judgements and the client's Claude is the wrong party to make them:

- Production with no test environment, plus fan-out that reaches real customers (worked example A —
  resolved by dropping to ceiling 1, but the operator confirms it)
- A system whose failure has safety consequences — clinical, emergency dispatch, access control for a
  physical building
- The client asking for testing against live customer data, or with real payment cards
- A platform whose AUP is known to prohibit automated testing (§15.1) with no enterprise agreement
- `redteam` derived without an emergency contact — `scope.parse()` refuses this anyway, so the skill
  raising it early is convenience, not control

**(e) The respondent is being led.**
The skill must not suggest answers to any field that widens scope, raises the ceiling, or establishes
authority. Concretely: it may not offer a default for A3, D1, E1, E2, E3, or C2, and it may not
re-ask a question after a "no" in a form that invites a different answer. This is advisory and
unenforceable, stated because it is the failure the questionnaire is most likely to have in practice
and it will only be caught by reading transcripts.

### 7.4 Where each rule is actually enforced

The honest accounting. **A rule with nothing in the "mechanical backstop" column is advisory and is
labelled as such in this document and in the skill's own text.**

| Rule | Skill (advisory) | Mechanical backstop | Where |
|---|---|---|---|
| Authority established before a scope record exists | stops, writes `cannot-proceed.md` | **`--auth-document` must exist on disk** | `new_engagement.py:193-200` (exists) |
| Attestation typed by the named signer | requires it | ingest refuses when `attestation.typed` false, or `signer.name` ≠ the countersigned document's signatory | `rg4_ingest.py` (new) |
| `environment` never guessed | offers "not sure" | `unknown` refused at Gate 1 | `gate_cli.cmd_approve` (exists, per RG-1 §3.1) |
| No document-only fact in the boundary | proposes, never asserts | ingest refuses any `in_scope` entry with `provenance: document` | `rg4_ingest.py` (new) |
| Incomplete bundle never scaffolds | marks `status: incomplete` | ingest refuses to emit a command line for an incomplete bundle | `rg4_ingest.py` (new) |
| Ceiling matches the consented answers | derives it | ingest recomputes the derivation from E1–E3 and refuses on a mismatch | `rg4_ingest.py` (new) |
| Boundary is well-formed | — | round-trip parse before anything is written | `new_engagement.py:205-208` (exists) |
| No legal claim in the client document | instructed | word-list lint over `engagement-document.md` | `rg4_ingest.py` (new), **D-8** |
| Declaration matches reality | — | `SCOPE_DECLARATION_DISCREPANCY` at Gate 1 (§2.2 layer 4) | new, RG-1 §4.2 shape |
| Respondent not led | instructed | **nothing** | — |
| Client's understanding of their own system is correct | — | **nothing beyond §2.2 layer 4** | accepted risk, §2.3 |
| Client's Claude is not talked into a friendlier bundle | — | **nothing**. Ingest checks shape, never sincerity | accepted risk |

The last three rows are the honest cost of this design and they should be quoted, not buried, when
the framework's guarantees are described to anyone.

### 7.5 `rg4_ingest.py` — the operator-side gate

New script in this repo. Reads a bundle directory, writes nothing into the repo, and either prints a
`/rg:new` command line or refuses with every reason at once (following `close_violations`' precedent
— an operator who fixes one refusal and is immediately refused for a different reason learns to
distrust the gate).

Refusal codes, all blocking:

| Code | Fires when |
|---|---|
| `BUNDLE_INCOMPLETE` | `status: incomplete`, or any required field `CANNOT_DETERMINE` |
| `AUTHORITY_UNESTABLISHED` | `can_bind` false/absent with no A4 holder, or `attestation.typed` not true |
| `SIGNER_MISMATCH` | `signer.name` differs from the `--signed-by` the operator supplies |
| `PROVENANCE_UNCONFIRMED` | any scope-driving field with `provenance: document` |
| `NO_ANSWER_BACKING` | any `in_scope` entry with no `from:` answer id, or an id absent from `answers.jsonl` |
| `CEILING_DERIVATION_MISMATCH` | recomputed mode/ceiling ≠ `derived` |
| `OWNER_NOT_CLIENT` | `owner_is_client` false without a recorded third-party permission |
| `ENVIRONMENT_UNDECLARED` | `environment` absent, empty, `unknown`, or unrecognised — same message as RG-1 |
| `LEGAL_CLAIM_IN_DOCUMENT` | word-list lint hit in `engagement-document.md` |
| `SCHEMA_UNKNOWN` | `schema:` is not a version this ingest understands |

`SCHEMA_UNKNOWN` matters more than it looks: the bundle is produced by a skill the operator does not
version-control, running on a machine the operator does not control, possibly months out of date.
Refusing an unrecognised schema version is the difference between a stale bundle failing loudly and a
stale bundle silently missing the field that was added because of an incident.

---

## 8. The dev-environment walkthrough and the environment delta

### 8.1 The tension, stated before the design

RG-1 §1 is unambiguous: **seven of eleven of the prior engagement's findings, including the only critical, were artifacts
of testing a Docker dev stack and reporting it as the client's production system.** A dev environment
is exactly the state that produced junk findings.

And testing only production is not available either: production is where writes are dangerous, where
rate testing pages an on-call engineer, and where the client will not consent to a tier-2 ceiling.
Meanwhile testing only dev produces "secure on my machine" — the WAF that only exists in production,
the rate limiter that lives at the CDN, the debug flag left on in dev and off in prod (and the reverse),
the environment variable that differs, the TLS configuration that is entirely a production concern.

**Neither environment can answer the other's questions, and the design must stop pretending
otherwise.** The resolution is not a choice between them. It is:

> **Record the difference as a first-class artifact, test each environment for what only it can
> answer, and print every recorded difference in the report's coverage section as something the audit
> cannot speak to.**

### 8.2 Shape: a companion skill, run with the operator present

`rg-devenv` is a **separate skill**, not a mode of `rg-scoping`, and it runs **after signature**, with
the operator and the client's technical person together.

Rejected alternative: a fifth block of `rg-scoping`. Rejected on three counts. Its respondent is
different — the founder answers Blocks A–F, and only a platform engineer can answer "does staging use
the same WAF". Its timing is different — it is a setup activity, not an authorisation activity, and
bolting it on would push the questionnaire well past the 25-minute target that §4.1 exists to protect.
And its trust boundary is different: by the time it runs, the operator is authorised and present, so
its answers can be established rather than merely declared.

Two modes:

- **`stand up`** — the client has no test environment and needs one. The walkthrough is a checklist
  the operator drives: clone the app, point it at a separate database with synthetic data, separate
  every credential, disable outbound fan-out or point it at a catcher, and *record every deviation
  from production as you create it*. The recording is the product; standing the environment up is the
  side effect.
- **`describe`** — the client already has one. Same questions, asked backwards.

Both write the same file.

### 8.3 `environment-delta.yaml`

> **[CONTRADICTED — `docs/specs/rg2-containment.md` §8.3 models this same object as a `parity:` block
> **inside `scope.yaml`**, with 5 dimensions instead of 12, a boolean instead of this tri-state, and
> sourced *"from the scoping questionnaire (Part 2 of RedGold)"* — which is the mechanism this
> section's "Rejected alternative" note rejects by name. Same date, same status. Recorded 2026-08-20
> by the currency audit; the design question is **open** and neither side has been adopted.**]
>
> The full comparison table is in `rg2-containment.md` §8.3 and in
> `docs/research/strategic-review.md` §1.1, which assesses **this** design as the better one on every
> axis. **But RG-2's block carries one rule this section does not**, and it should survive any merge:
> *a divergence in TLS termination, environment config or infrastructure makes "we found nothing" an
> unsupportable sentence about production.* §8.4's mechanical consequences do not include it. The
> strategic review's recommendation is to migrate it here as a fourth consequence — **not yet done**.

Twelve dimensions. Each takes `same` | `differs` | `unknown`, plus a note. **`unknown` is a legal
value and it costs the same as `differs`** — the same discipline as `environment: unknown`.

| # | Dimension | The question, plainly | Why it is on the list |
|---|---|---|---|
| 1 | `edge` | "Is the CDN, WAF or DDoS protection the same in front of both?" | Almost always **differs**. The single largest source of "secure on my machine" — every header, rate-limit and injection result from dev may be invalid |
| 2 | `rate_limiting` | "Is request rate limiting configured the same?" | The E2 test's result is meaningless if it differs |
| 3 | `tls_and_certs` | "Same certificate authority, same TLS configuration, same domain?" | A self-signed or `*.local` cert is one of RG-1 §2.4's four blocking non-prod signals; recording it here stops it presenting as a discrepancy later |
| 4 | `auth_provider` | "Same login system and same providers — Google, SSO, magic links?" | Auth findings do not transfer across a changed IdP |
| 5 | `data` | "Is the data in it synthetic, a scrubbed copy of real data, a raw copy of real data, or empty?" | A raw copy means dev **holds production personal data**, which changes what a dev finding means and may itself be the most serious finding of the engagement |
| 6 | `secrets` | "Are the API keys and credentials different from production? Are any production keys present in the test environment?" | The prior engagement's live spend-capable Resend key in a dev config (RG-1 §1.2a). This question exists because that was missed |
| 7 | `outbound_fanout` | "Does it really send email, SMS, webhooks and Slack messages, or are they caught?" | A mail catcher is one of RG-1 §2.4's blocking non-prod signals **and** an `env-secret-read` capability rung |
| 8 | `payment` | "Test-mode payment keys, live keys, or no payments?" | `pk_test_`/`sk_test_` is a §2.4 blocking signal, and a live key in dev is severe |
| 9 | `build_and_debug` | "Same commit? Debug mode, verbose errors or source maps on in one and not the other?" | Verbose errors are a §2.4 blocking signal and a finding in their own right against production |
| 10 | `datastore` | "Same database engine and version, same storage, same region?" | A version delta invalidates injection and query-behaviour findings |
| 11 | `shared_components` | "Does anything get shared — the same bucket, the same queue, the same third-party account?" | Worked example B. A shared component means a tier-2 write on dev can land in production |
| 12 | `access_control` | "Who can reach the test environment — the internet, or only your team?" | Sets `reach` for scoring, and an internet-exposed non-production environment is its own `high` posture finding (`NONPROD_INTERNET_EXPOSED`, RG-1 §4.2) |

```yaml
schema: rg4-delta/1
engagement: wavelet-2026-09
established_by: "Priya N., platform engineer"     # a person, on a date, not a document
established_at: 2026-09-02
production_ref: "https://app.wavelet.example"
nonproduction_ref: "https://app.staging.wavelet.example"
dimensions:
  edge:             {state: differs, note: "production sits behind Cloudflare with a WAF; staging is Vercel-direct"}
  rate_limiting:    {state: differs, note: "rate limiting is a Cloudflare rule; staging has none"}
  tls_and_certs:    {state: same}
  auth_provider:    {state: same,    note: "same Supabase Auth project settings, separate project"}
  data:             {state: differs, note: "synthetic, seeded from a fixture script"}
  secrets:          {state: differs, note: "separate keys; Stripe in test mode; Postmark key is a SHARED PRODUCTION KEY"}
  outbound_fanout:  {state: differs, note: "email to Mailpit; Slack alerts are REAL and go to #eng"}
  payment:          {state: differs, note: "pk_test_ / sk_test_"}
  build_and_debug:  {state: unknown, note: "nobody could confirm whether NEXT_PUBLIC_DEBUG differs"}
  datastore:        {state: same,    note: "same Postgres major version"}
  shared_components:{state: differs, note: "SHARED: the uploads bucket is the production bucket"}
  access_control:   {state: differs, note: "staging is internet-reachable with no IP restriction"}
```

### 8.4 What the delta does downstream — three mechanical consequences

1. **Every `differs` and every `unknown` becomes a line in the report's coverage section**, rendered
   from this file, in the client body and not an appendix:
   > *"This assessment tested `app.staging.wavelet.example`. Production sits behind a WAF and a rate
   > limiter that the tested environment does not have, so no result in this report should be read as
   > a statement about how production responds to injection attempts or to rapid repeated requests.
   > We could not establish whether debug output differs between the two."*

   **What differs is what the audit cannot speak to.** That sentence is the section's specification.
   RG-1 §8 already establishes that coverage is a first-class deliverable; this is the environment's
   contribution to it.

2. **Three rows above are findings, not context**, and must be emitted as such rather than left in a
   YAML file: the shared production uploads bucket, the production Postmark key in a non-production
   environment, and the internet-reachable non-production environment. `NONPROD_INTERNET_EXPOSED`
   already exists in RG-1 §4.2 and is exempt from the environment cap. The other two need a
   `production_nexus` of kind `live_credential` and `shared_infrastructure` respectively — both
   already in RG-1 §3.3's vocabulary, which is what stops the environment cap burying them.

3. **`unknown` on any dimension raises `ENV_DELTA_UNESTABLISHED`, non-blocking**, counted in
   `status.md`. Non-blocking is deliberate: a client who cannot answer dimension 9 should not be
   prevented from having an audit, but the count should be visible and should trend down. A dozen
   unknowns is an audit whose coverage section is longer than its findings.

### 8.5 The recommendation on which environment gets which tier

Stated as a recommendation because it is the operator's commercial call — **D-5**.

| Tier | Environment | Rationale |
|---|---|---|
| 0–1 (passive, safe reads) | **Both**, and production is in the boundary specifically for this | Headers, TLS, edge behaviour, error pages, exposed paths and published bundles are production facts and cannot be learned anywhere else. All read-only, all normal-user-equivalent |
| 2 (bounded reversible writes) | **Non-production only** | This is where the consent problem lives, and it is where a mistake is expensive |
| 3 | Non-production only, with the operator present | §6 already requires this |

Implemented as the per-asset `ceiling_override` in worked example B. It needs a per-asset ceiling that
`scope.py` does not currently have, and it must be **narrowing only**, exactly as RG-1 §3.1 makes the
per-asset environment override narrowing only. A per-asset ceiling that could *raise* the engagement
ceiling would be a scope-widening mechanism inside the scope file, which is the thing §5.4 exists to
prevent.

---

## 9. The goal-loop close

### 9.1 The pattern the operator named

> *"Closing an engagement should be a user decision, but it should be made sure that everything is
> covered beforehand, sort of like a goal loop."*

And the questionnaire is the same shape: the system establishes completeness, the human decides.
**Build it once.** `completeness_loop.py` renders a list of items in a fixed shape and is used by
`rg4_ingest.py`, by `/rg:close`, and by the questionnaire's own review step:

```python
{"id": "...", "state": "SATISFIED|OUTSTANDING|OVERRIDDEN",
 "what": "...", "why_it_matters": "...", "fix_command": "...", "overridable": bool}
```

Three consumers, one renderer. The alternative — a bespoke checklist per site — is how the three
diverge and how one of them silently stops listing an item.

### 9.2 What `/rg:close` does today

> **[COMPOSITION CONFLICT — this document's §9.3 is the second of three incompatible engagement
> lifecycles, and nothing owns the composite. Recorded 2026-08-20 by the currency audit; see
> `docs/research/strategic-review.md` §1.2 and the reciprocal marker at
> `docs/specs/rg1-finding-integrity.md` §9.1a.]**
>
> Two specific problems with §9.3's nine-item preflight, neither of which is a reason to abandon it:
> **five of its new soft items are sourced from artifacts that do not exist** (`environment-delta`,
> `scope-facts`, credential attestation, evidence retention, harvest), and it makes `/rg:harvest` a
> checklist item when `commands/harvest.md` declares itself **NOT IMPLEMENTED**.
>
> The third lifecycle is `rg2-containment.md` §3.4/§8.2's containment sequence, whose step 6 —
> revert `rg-work` to snapshot — **destroys the machine the ledgers and evidence are on** unless
> evidence was pulled first. That ordering dependency appears in RG-2 and in neither this document
> nor RG-1.
>
> **Also correct the paragraph below before relying on it.** It describes `close_violations()` as
> refusing on three conditions; the current code refuses on **four** — `COVERAGE_EMPTY_PHASE`,
> `PHASE_NEVER_COMPLETED`, `REPORT_STALE` and `GATE_1_VOID` (the S10 fix). And two of the four are
> defective: `REPORT_STALE` reads a `created` field only `baseline_scan.py` writes, and
> `COVERAGE_EMPTY_PHASE`'s phase discrimination reads a `phase` field nothing writes. See
> `docs/wiki/architecture/current.md` §6 D-1 and D-2, and `status.md` "NOT enforced" items 7 and 8.

`gate_cli.cmd_close` computes `close_violations()` and refuses on any of three: `COVERAGE_EMPTY_PHASE`
across the whole engagement, `PHASE_NEVER_COMPLETED`, and `REPORT_STALE`. All three are hard; there is
no override. It reports every reason at once, which is already the right behaviour and the reason is
already documented in place.

status.md caveat 6 is also already honest about the limit: there is no Claude Code lifecycle event for
engagement close, so `/rg:close` narrows the failure from "forgot a check" to "skipped the documented
close step" and makes the skip detectable afterwards. RG-4 does not fix that and should not claim to.

### 9.3 The loop

`/rg:close` gains a preflight that runs by default and prints the full completeness set — satisfied
items included, because a list that only shows problems gives no sense of what was checked.

```
Engagement wavelet-2026-09 — close readiness

  HARD (cannot be overridden — these mean there is no record the engagement happened)
  [ok]  coverage        18 findings, 44 recorded negatives
  [ok]  phases          recon, surface, webtest completed
  [!!]  report          deliverables/report-tier2.md predates F-031 (2026-09-18T22:04Z)
                        -> scripts/report.py --tier 2

  SOFT (you may close over these; the reason is recorded and printed in the report)
  [ok]  blockers        0 unresolved
  [!]   cleanup         3 rows in ledger/cleanup.jsonl with no deletion confirmed
                        -> record the deletion, or close over it and the report lists the residue
  [!]   credentials     no record that client credentials were destroyed (§15.2)
                        -> gate_cli.py attest --item credentials-destroyed
  [!]   evidence        no retention decision recorded (§15.5)
  [ok]  register        assets/register.jsonl delivered with the report
  [!]   env-delta       2 dimensions unknown (build_and_debug, datastore) — will print as
                        coverage limitations in the report
  [!]   scope-facts     4 facts rest only on the client's declaration and are unreconciled
  [ok]  harvest         /rg:harvest run 2026-09-19

  1 hard item outstanding. Close is refused until it is fixed.
```

**The hard/soft split, and why it falls where it does.** The three existing refusals stay hard because
each means *there is no evidence this engagement happened* — an empty corpus, no completed phase, a
deliverable that predates its own findings. Those are integrity properties of the record, and an
override on them would be an override on whether the engagement is real.

Everything RG-4 and §15.6 add is **soft**, because each is *work the operator chose not to finish*.
Cleanup residue, an unrecorded credential destruction, an unresolved environment dimension: these are
real and they are the operator's to weigh against a client's deadline. Making them hard produces the
disabled-gate failure RG-1 §2.3 and §4.8 both name — a gate that fires on ordinary states gets worked
around, and the workaround is worse than the override because it leaves no record. **D-7** asks the
operator to confirm the split.

### 9.4 Closing anyway

`gate_cli.py close --override <item-id> --reason "<text>"`, repeatable. Record, do not block.

Three mechanical properties:

1. **A blank or whitespace-only reason is refused.** This is the only enforcement in the override
   path, and it is enough: the cost of an override is one sentence, and one sentence is exactly the
   friction that makes an operator ask whether it is worth it.
2. **An override names an item that is actually outstanding.** Overriding a satisfied item, or an
   unknown id, is refused — otherwise a blanket `--override all` becomes the habit.
3. **A hard item cannot be overridden at all.** `--override` on one prints the hard/soft distinction
   and exits non-zero.

The `gate.close` ledger row gains:

```json
{"id": "G-014", "gate": 1, "event_type": "gate.close", "decision": "closed",
 "phases_completed": ["recon", "surface", "webtest"],
 "closed_by": "operator",
 "overrides": [
   {"item": "cleanup", "reason": "3 test orders could not be deleted; the client's own permission check refuses the anonymous creator's delete. Removal query supplied in the cleanup appendix.", "by": "operator", "ts": "2026-09-19T04:10:00Z"},
   {"item": "env-delta", "reason": "platform engineer left before confirming the debug flag; client accepted the limitation in writing 2026-09-18.", "by": "operator", "ts": "2026-09-19T04:11:00Z"}
 ],
 "ts": "2026-09-19T04:11:00Z"}
```

### 9.5 How the override reaches the report

**This is the part that makes the override meaningful rather than a private note.**

`report.py` gains a section, rendered from the `gate.close` row plus the environment delta plus the
`client-declared`-only scope facts, titled **"What this engagement did not establish"**, placed **in
the client body, immediately after the findings summary** — not in an appendix.

> **What this engagement did not establish**
>
> - Three test orders created during testing could not be removed; your own permission check refuses
>   the deletion. They are listed in Appendix C with a query that removes them.
> - We could not confirm whether debug output differs between your test environment and production,
>   so no statement in this report about error messages should be read as applying to production.
> - Four facts in the scope of this assessment rest only on your description of your systems and were
>   not independently confirmed: \<list\>.

Three consequences, all intended:

1. **Closing early costs a paragraph in the client's own document.** That is the right price — high
   enough to be felt, low enough that it never justifies skipping `/rg:close` entirely.
2. **It is calibrated honesty applied to the operator** (P9, hard rule 5). The section is unflattering
   by construction, which is what makes it credible.
3. **It composes with RG-1 §8's coverage counterweights** rather than duplicating them. The coverage
   section says what was looked at; this section says what was left open, and the environment delta
   feeds both.

**Failure mode to watch, named now:** if this section becomes long on every engagement, the response
must be to do the work, not to shorten the section. Track its length as a number in `status.md` for
the same reason RG-1 §4.3 brake 4 tracks the suppression rate — a rule nobody counts is a rule nobody
knows is misfiring.

---

## 10. What a Claude skill can and cannot guarantee

Collected in one place so it can be quoted without reading the document.

**Can:**
- Ask every required question, in a phrasing a non-technical person can answer.
- Read documents the operator may not read, and keep them out of the bundle.
- Produce a bundle whose shape is machine-validatable on the operator's side.
- Mark its own output incomplete, and record contradictions instead of resolving them.
- Refuse to continue, in the ordinary case where the respondent cooperates.

**Cannot:**
- Enforce any of the above. It is a prompt. A user who wants a different bundle can get one.
- Verify a single client statement about the client's own system.
- Prevent the operator from bypassing `rg4_ingest.py` and typing `/rg:new` by hand — nothing does,
  and `--allow-missing-authorization` still exists for dry runs.
- Guarantee that a signature was made by someone with the authority they claimed.

**The one property actually guaranteed**, restated: an engagement cannot be scaffolded without an
authorisation document existing on the operator's filesystem, and no artifact produced on the client's
machine can create that file. Everything else in RG-4 raises the probability that the document says
something true.

---

## 11. Open decisions for the operator

| # | Decision | Recommendation |
|---|---|---|
| **D-1** | Bundle emits `scope-record.yaml` for `rg4_ingest.py`, or `scope.yaml` directly? | **`scope-record.yaml`.** §6.1. Emitting `scope.yaml` makes the client's Claude the author of the enforcement boundary and routes around all four of `new_engagement.py`'s refusals |
| **D-2** | How does the client get the skill? Plugin install, a pasted `SKILL.md`, or a hosted page? | **A single self-contained `SKILL.md` plus one reference file, sent as an attachment**, that the client drops in `.claude/skills/`. No install, no marketplace account, nothing the operator must host or keep up. The cost is version drift, which `SCHEMA_UNKNOWN` (§7.5) makes loud rather than silent |
| **D-3** | Add `authority:` and `platforms:` blocks to `scope.py`? | **Yes, and this is the smallest blocking item.** §15.1 requires three platform facts that `scope.yaml` has nowhere to hold, so today they are recorded nowhere. Also gives A1–A8 a home |
| **D-4** | Implement RG-1 §3.1's `environment_established` and `environment_source`, which are specced but absent from `scope.py`? | **Yes, before RG-4 is built.** RG-4 produces both, and `environment_established: client-declared` is what makes the report's provenance banner honest about the fact that the environment rests on the client's word |
| **D-5** | Per-asset `ceiling_override`, narrowing only — production in scope at tier 1 while non-production carries tier 2? | **Yes.** §8.5. It is the only structure that lets the audit answer production-only questions without writing to production. Must be narrowing-only, on the RG-1 §3.1 precedent |
| **D-6** | Should an unsigned bundle ever scaffold? | **No.** `rg4_ingest.py` never emits `--allow-missing-authorization`; that flag stays for dry runs the operator types deliberately |
| **D-7** | Confirm the hard/soft close split (§9.3) | **As proposed:** the three existing refusals stay hard (record integrity); cleanup, credentials, evidence retention, register delivery, environment delta and unreconciled scope facts are soft and overridable with a mandatory reason |
| **D-8** | Word-list lint over `engagement-document.md` for legal terms — mechanical refusal or warning? | **Mechanical refusal.** A false positive costs the operator one rewrite; a false negative puts a legal claim in a client's hands under hard rule 1. The list starts small: "compliant", "compliance", "notifiable", "breach" in a legal sense, "Privacy Act", "APP", "certified" |
| **D-9** | Keep the document hash manifest? | **Yes**, with the §2.4 caveat stated in the ingest output itself: chain of custody, never verification. It must never be described to a client as making the declaration verified |
| **D-10** | Compliance module (add-on M3) in v1? Adaptive question depth? | **Defer both.** M3 until Subsystem F clears `[VERIFY]` — hard rule 1 is at its highest risk inside a client-facing generated document. Adaptive depth until there is data on where real bundles come back incomplete |
| **D-11** | Does RG-4 unblock a pending authorisation blocker? | **Only if the client completes a bundle and signs the document.** RG-4 is the mechanism for turning that verbal approval into a record; it is not itself the record, and B-1 stays until `scope.yaml` exists on disk |

### Build order, if this is approved

1. **D-3 and D-4** — `scope.py` schema additions. Everything else depends on them, and both are
   already owed to `11-governance.md` §15.1 and RG-1 §3.1 regardless of RG-4.
2. **`rg4_ingest.py`** with its refusal codes and a fixture bundle per worked example. Build the gate
   before the thing it gates, so the skill is developed against a validator that already refuses.
3. **`rg-scoping` SKILL.md** — Blocks A–F, two branches, the review step.
4. **`completeness_loop.py`** and the `/rg:close` preflight, overrides, and the report section (§9).
5. **`rg-devenv`** and `environment-delta.yaml` (§8), plus the report's coverage rendering.
6. **D-5's per-asset ceiling**, last, because it is the only item that changes what `scope_guard.py`
   enforces and it deserves its own fault-injection round in `verify_controls.py`.


---
