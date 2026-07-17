---
name: opsec
description: Protect the investigator — attribution risk, passive-vs-active discipline, legal boundaries. Load when investigating adversaries who may look back.
---

# Investigator OPSEC & Legal Boundaries

## The rule that matters most

**Passive beats active.** Every tool in RedEye is passive by design — it queries
third-party public sources (search engines, CT logs, archives, public APIs).
The subject never sees you. Keep it that way:

- Prefer `urlscan_search` over fetching the subject's site. Someone else
  already touched it; read their notes.
- `http_headers` is the one built-in that contacts subject infrastructure —
  it's a single ordinary GET, but it exists in their logs. RedEye flags it
  as `active` and asks before running outside fullauto mode. When in doubt,
  don't.

## Attribution hygiene (advise the operator)

- Assume the subject monitors: referrer logs, their TLS transparency, social
  profile views (LinkedIn notifies!). View profiles logged-out or via search
  caches where possible.
- Timezone and working-hours patterns in *your* activity can fingerprint you.
- Don't reuse investigative infrastructure (VMs, accounts) across cases.

## Legal lines RedEye will not cross

- No authentication to systems you don't own. No credential use, no session
  tokens from breaches, no "just checking if this password works".
- No circumvention: CAPTCHAs, rate limits, robots controls, paywalls.
- No collection of non-public data; no pretexting (lying to humans for info).
- Breach data: report categories and services, never replay secrets.
- Stalking, harassment, and doxxing are out — always, regardless of target.
- When you find exposed systems or data: the move is responsible disclosure to
  the owner, not exploration.

## If the subject is dangerous (criminal/nation-state)

Recommend in the report: dedicated research environment, legal review,
law-enforcement liaison where appropriate. OSINT is an input to process,
not a substitute for it.
