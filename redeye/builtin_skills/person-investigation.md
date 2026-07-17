---
name: person-investigation
description: Lawful public-footprint assessment of a named person — for due diligence, journalism, and security research. Establishes identity, presence, and public exposure.
---

# Person of Interest — Public Footprint Assessment

## Scope discipline (read first)

Use only for legitimate purposes: due diligence, journalism, security research,
locating consenting contacts. **Never** for stalking, harassment, doxxing, or
targeting private individuals for intimidation. Collect what is *publicly
published*, corroborate, and report proportionately — no home addresses or
family details in the report unless they are squarely relevant and already
widely published.

## Methodology

1. **Disambiguate** — before collecting, establish you have the right person:
   name + one anchor (employer, city, handle, domain). Search `"Full Name" anchor`.
2. **Professional layer** — `web_search`:
   - `"Full Name" employer` , `site:linkedin.com/in "Full Name"`
   - conference talks, patents, papers, press releases.
3. **Handle discovery** — from any profile, extract handles → `username_search`.
4. **GitHub** — `github_user` + `github_search` for their commits (commit emails!).
5. **Email patterns** — derive from employer domain, validate with `email_intel`.
6. **Domain ownership** — personal sites: `rdap_lookup`, then `domain-recon` on it.
7. **Images & docs** — public PDFs they authored: download → `extract_metadata`
   (authors, software, sometimes GPS).
8. **Timeline** — assemble career/event timeline from sources; note contradictions.

## Output

- Findings: identity anchors, professional history, public accounts (verified),
  public contact points, exposure assessment (what an adversary could learn).
- Every claim carries source + confidence. Contradictions between sources are
  findings, not inconveniences — record them.
