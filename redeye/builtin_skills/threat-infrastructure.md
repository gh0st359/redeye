---
name: threat-infrastructure
description: Analyze suspicious/malicious infrastructure passively — phishing domains, C2 patterns, fast-flux, lookalikes. For defenders and researchers.
---

# Threat Infrastructure Analysis (defensive)

## Methodology

1. **Triage the indicator** — domain, IP, or URL. `dns_records`, `rdap_lookup`,
   `ip_intel`. Note: creation date, registrar (bulletproof?), NS (shared with
   other badness?), hosting ASN.
2. **Passive detonation data** — `urlscan_search` shows what the page does,
   technologies, and *other domains it contacts* — that's your expansion set.
3. **Lookalike detection** — for brand impersonation: generate permutations
   mentally (homoglyphs, hyphenation, TLD swaps) and `dns_records` each —
   resolving lookalikes = active phishing prep.
4. **History** — `wayback_snapshots`: when did content appear? Parked → live
   transitions date the campaign.
5. **Shared infrastructure** — same IP, same NS, same registrar+date cluster,
   same TLS cert patterns (`crtsh_subdomains` on the apex shows cert reuse).
6. **Fast-flux signal** — multiple A records across unrelated ASNs, short TTL
   patterns, PTR churn.

## Boundaries

- RedEye stays **passive**. Do not port-scan, exploit, or interact beyond a
  single ordinary page fetch — and prefer not fetching live malicious
  infrastructure at all: `urlscan_search` already did it for you.
- Output feeds blocklists and reports: structure findings as indicator +
  type + confidence + first/last seen + related indicators.
- If the target of an investigation is criminal infrastructure, recommend in the
  report that takedown/abuse reporting go through proper channels (registrar
  abuse contact from `rdap_lookup`, hosting ASN abuse desk).
