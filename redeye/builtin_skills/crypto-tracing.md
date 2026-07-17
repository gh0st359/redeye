---
name: crypto-tracing
description: Trace cryptocurrency addresses and transactions on public ledgers — balances, flows, counterparty clustering, off-ramps. For fraud, ransomware, and sanctions research.
---

# Cryptocurrency Tracing

## Methodology

1. **Identify** — `crypto_address_intel` auto-detects BTC/ETH. Record balance,
   tx count, first/last activity.
2. **Flow analysis** — from recent transactions, pick the largest counterparties
   and recurse with `crypto_address_intel`. Depth 2–3 is usually enough to spot
   the pattern. Watch for:
   - **Peel chains** — long chains where small amounts peel off at each hop.
   - **Consolidation** — many addresses feeding one (exchange deposit? mixer?).
   - **Round-amount transfers** — often fiat off-ramps.
3. **Attribution** — `web_search` the address quoted. Addresses appear in: ransomware
   notes, scam reports (BitcoinAbuse), forum posts, donation pages, sanctions lists.
   Also `github_search` the address.
4. **Clustering heuristics** (state as heuristics, never fact):
   - BTC: common-input ownership — inputs to the same tx usually share an owner.
   - Reused change addresses, identical timing patterns.
5. **Off-ramp hypothesis** — funds ending at known exchange deposit patterns are
   where legal process works. Note the exchange hypothesis with confidence LOW
   unless the address is publicly labeled.

## Rules

- Blockchain data is public but pseudonymous: report *flows*, not identities,
  unless an address is publicly labeled by a credible source.
- Amounts + dates in every finding; screenshots/URLs as sources.
- This playbook supports journalists and researchers. It is not a substitute for
  a licensed chain-analytics platform in legal proceedings.
