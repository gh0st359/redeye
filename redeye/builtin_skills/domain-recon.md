---
name: domain-recon
description: Full infrastructure mapping of a domain — DNS, subdomains, registration, mail stack, hosting, historical content. Start here for any domain/company target.
---

# Domain Reconnaissance Playbook

## Methodology

1. **Baseline** — `dns_records` on the apex. Note A/AAAA (hosting), MX (mail provider),
   NS (DNS provider), TXT. TXT records are gold: SPF includes reveal every service
   allowed to send mail (Google Workspace, SendGrid, Mailchimp, Salesforce...).
2. **Subdomain enumeration** — `crtsh_subdomains`. Sort mentally: `dev.`, `staging.`,
   `api.`, `vpn.`, `mail.`, `old.`, `jenkins.`, `grafana.` tell you the stack and the
   attack surface. Pivot interesting subdomains into `dns_records` and `rdap_lookup`.
3. **Registration** — `rdap_lookup` on the apex: creation date (fly-by-night or
   established?), registrar, any published registrant org.
4. **Hosting intelligence** — resolve the A record, then `ip_intel` on each IP:
   ASN and org reveal the hosting provider; PTR records sometimes leak hostnames.
5. **Passive scan data** — `urlscan_search` for observed technologies, page titles,
   third-party requests.
6. **History** — `wayback_snapshots` on the apex and key paths. Old about/team pages,
   PDFs, and robots.txt from years ago routinely leak names, emails, and structure.
7. **Code exposure** — `github_search` with `"example.com"` and
   `"example.com" in:file filename:.env`-style queries for leaked configs and emails.

## Pivot table

| Found this         | Pivot to                                             |
|--------------------|------------------------------------------------------|
| IP address         | `ip_intel`, `rdap_lookup` (netblock owner)           |
| Subdomain          | `dns_records`, `http_headers` (if approved)          |
| Mail provider (MX) | Targeted web_search for employee emails on that stack |
| Employee name      | Load `person-investigation` skill                    |
| Old PDF/doc        | Download → `extract_metadata` (author names!)        |

## Rules

- Corroborate every material claim with ≥2 sources before recording a high-confidence finding.
- Record findings with `case_add_finding` as you go — don't batch them at the end.
- Note gaps honestly: "no CT entries older than 2023" is itself a finding.
