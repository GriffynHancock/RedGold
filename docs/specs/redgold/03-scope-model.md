---
title: The scope model
question: How is authorisation expressed, how are assets attributed, and what may be touched?
sections: [5]
spec: RedGold design
status: draft
date: 2026-08-03
---

## 5. The scope model

The single most important correction to the prior engagement's design. A non-technical founder does not know
what assets they have; clicking through a dashboard spawns cloud objects and changes configs
invisibly. Scope therefore cannot be a static input the client fills in — but it also cannot be
something discovery is allowed to widen on its own, or the tool authorises itself.

Three artifacts, three different rules.

### 5.1 Authorization boundary — `scope.yaml`

What the client actually signed. Deliberately coarse. Small, human-verified, and changed **only by
written amendment**. This — and only this — is what the hooks enforce.

Asset types adopt the **HackerOne scope vocabulary** rather than inventing one, so the document
reads like something a client's lawyer has seen before:
`URL, WILDCARD, CIDR, IP_ADDRESS, API, SOURCE_CODE, HARDWARE, AI_MODEL, SMART_CONTRACT,
APPLE_STORE_APP_ID, GOOGLE_PLAY_APP_ID, TESTFLIGHT, DOWNLOADABLE_EXECUTABLES, OTHER_APK, OTHER_IPA,
OTHER`, extended with `CLOUD_ACCOUNT`, `GITHUB_ORG`, `SUPABASE_PROJECT`, `FIREBASE_PROJECT`.

```yaml
engagement_id: acme-2026-08
client:
  name: Acme Pty Ltd
  contact: founder@acme.example
authorization:
  document: ../authorization/acme-signed-roe-2026-08-01.pdf   # outside the repo
  signed_by: Jane Founder
  signed_date: 2026-08-01
  window_start: 2026-08-05
  window_end:   2026-08-19
mode: audit            # posture | audit | redteam   (§6)
ceiling: 1             # blast-radius tier ceiling   (§6)
crown_jewels:
  - "user geolocation and presence data"
  - "payment records"
in_scope:
  - {asset_type: WILDCARD,         pattern: "*.acme.example"}
  - {asset_type: SUPABASE_PROJECT, pattern: "abcdefghijklmnop"}
  - {asset_type: GITHUB_ORG,       pattern: "github.com/acme"}
out_of_scope:                                    # wins over in_scope, always
  - {asset_type: URL, pattern: "https://blog.acme.example", note: "third-party WordPress"}
constraints:
  no_destructive: true
  testing_window: "weekdays 09:00-17:00 AEST"
  max_requests_per_burst: 10
  forbidden_actions: ["password reset on real accounts", "email sending"]
notify:
  before_active: true      # operator must approve Gate 1
```

### 5.2 Discovered asset register — `assets/register.jsonl`

What we found. Grows all engagement. **Also a first-class deliverable** — for a founder who does
not know that clicking a dashboard spawned a public bucket, "here is everything you actually own,
and here is how I proved it's yours" may land harder than the findings.

```json
{
  "asset_id": "A-014",
  "asset_type": "URL",
  "identifier": "api-staging.acme.example",
  "discovery_method": "crt.sh CT log",
  "attribution_signals": [
    {"class": "TLS_SAN",    "value": "api-staging.acme.example", "source": "crt.sh"},
    {"class": "CONTENT_FP", "value": "matches prod app bundle hash", "source": "httpx"}
  ],
  "attribution_confidence": "HIGH",
  "matched_boundary_entry": "WILDCARD:*.acme.example",
  "status": "CONFIRMED",
  "first_seen": "2026-08-05T09:14:00Z",
  "last_seen":  "2026-08-06T11:02:00Z"
}
```

**Attribution rule: never promote on a single signal.** Qualys' published confidence cascade treats
ASN/domain/TLS-SAN matches as high confidence and bare org-name string matches as medium, because
org strings collide across registrars, resellers and hosts. Promotion from `CANDIDATE` to
`CONFIRMED` requires **two independent signal classes**.

**IP address never counts as an attribution signal on its own.** Cloudflare's edge IPs are shared
across every proxied hostname; the same is true of Vercel, Netlify and any multi-tenant PaaS —
which is by definition where this client base lives. Favicon hashes fingerprint the *platform*, not
the *owner*, so every customer of a no-code host shares one.

Signal classes: `RDAP_REGISTRANT`, `ASN_OWNER`, `TLS_SAN`, `CT_COOCCURRENCE`, `DNS_CNAME_CHAIN`,
`CONTENT_FP`, `ANALYTICS_ID`, `COPYRIGHT_STRING`, `AUTHENTICATED_CONFIRM`, `CLIENT_CONFIRMED`.

### 5.3 Candidate queue — `assets/candidates.jsonl`

Looks like theirs; not confirmed. **Structurally untouchable.** Same schema, `status: CANDIDATE`.
Promotion requires either two independent high-class signals *plus* operator sign-off, or explicit
client confirmation. If the asset sits outside the authorization boundary, it additionally requires
a written scope amendment before anything touches it.

### 5.4 The enforcement invariant

> Active tooling generates its target list **only** from `CONFIRMED` register rows that map to an
> `in_scope` boundary entry and do not match any `out_of_scope` entry.

Candidates are visible in reporting and unreachable by anything that tests them.
Discovery feeds the register; enforcement reads the boundary. **Nothing an agent finds can widen
what an agent may do.**

### 5.5 The attribution carve-out

The invariant as stated would deadlock: `TLS_SAN`, `CONTENT_FP` and `AUTHENTICATED_CONFIRM` can only
be obtained *by contacting the asset*, yet an asset cannot be contacted until it is CONFIRMED by two
such signals. Left implicit, this would become an undocumented exception that quietly voids the
guarantee — so it is defined explicitly and narrowly:

**Attribution probes against CANDIDATE assets are permitted** subject to all of:

1. **Tier 0–1 only** — a TLS handshake, one unauthenticated GET of a root or a static bundle. Never
   authenticated, never parameterised, never a write.
2. **Inside the authorization boundary only.** A candidate matching no `in_scope` pattern is *not*
   probeable at all; it requires client confirmation or a scope amendment first. This is the case
   that carries the real legal risk, and it stays closed.
3. **Rate-limited** — at most a small fixed number of requests per candidate.
4. **Logged** to `ledger/activity.jsonl` and tagged `purpose: attribution`.
5. **Cannot produce a finding.** Anything observed during attribution is discarded as evidence. If
   it looked interesting, the asset gets promoted properly and re-tested under normal rules.

Rule 5 is what preserves the guarantee: attribution buys the right to *identify*, never the right to
*conclude*.

---
