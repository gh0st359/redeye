---
name: email-osint
description: Investigate an email address — breaches, profiles, infrastructure, connected accounts. For phishing analysis and identity resolution.
---

# Email Investigation

## Methodology

1. **Assess** — `email_intel <addr>`: disposable? MX provider? Gravatar? HIBP breaches
   (if key configured).
2. **Profile pivot** — `gravatar_lookup`: display names, bios, linked accounts.
3. **Domain pivot** — the part after @: run the `domain-recon` methodology on it
   (custom domain = their infrastructure; freemail = dead end there).
4. **Search pivot** — `web_search` the address quoted: `"jane.doe@example.com"`.
   Then variations: with `mailto:`, in data-breach paste contexts, on GitHub
   (`github_search` with the address).
5. **Breach correlation** — breach names from HIBP tell you services the person used,
   which gives new platforms to check via `username_search` with the local part.
6. **Username pivot** — the local part (`jane.doe`) is often reused as a handle —
   sweep it with `username_search` (also try without the dot).

## Phishing-analysis specifics

- Check domain age via `rdap_lookup` — domains < 30 days old claiming to be a bank
  are a finding by themselves.
- Compare MX of the sender domain vs. the legitimate organization.
- `wayback_snapshots` on the sender domain: was it ever a real site?

## Boundaries

- Never attempt to access, reset, or log in to the mailbox. Public data only.
- Breach data: report *which* services and *what categories* of data were exposed.
  Do not seek or repeat passwords/hashes.
