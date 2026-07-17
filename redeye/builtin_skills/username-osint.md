---
name: username-osint
description: Track a handle across platforms, verify account ownership, and pivot from username to real identity. For handle/alias investigations.
---

# Username / Handle Investigation

## Methodology

1. **Sweep** — `username_search <handle>`. Expect false positives on common words;
   platform hits are leads, not proof.
2. **Verify linkage** — accounts on different platforms belong to the same person only if
   they share: avatar image, bio text/links, display name, posting style, cross-links
   (GitHub profile links to the same Twitter, etc.). Always verify with `fetch_url` on
   the profile and compare.
3. **Richest sources first**:
   - GitHub → `github_user`: often has real name, email (also check commit emails via
     `github_search` commits), employer, location.
   - Keybase → cryptographic proofs linking their other accounts.
   - Gravatar (if you have an email) → `gravatar_lookup`.
4. **Content analysis** — read recent posts/bios via `fetch_url`. Extract: timezone from
   posting times, language, employer mentions, personal sites.
5. **Email derivation** — once you have a name + employer domain, generate likely
   patterns (first.last@, flast@, first@) and validate via `email_intel`
   (MX + Gravatar presence is a decent oracle).

## Anti-loop discipline

One sweep per handle variant max. If a variant returns nothing, do not retry it —
try the next pivot (name, email, domain) instead.

## Recording

- Each *verified* account linkage = one `case_add_finding` with the evidence for linkage.
- Unverified platform hits = a single finding listing candidates, confidence LOW.
