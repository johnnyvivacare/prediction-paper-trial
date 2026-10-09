# Provenance and third-party scope

This release is newly written first-party Python, HTML, CSS and JavaScript. It is not a downloaded profit bot, a fork of an unreviewed wallet program, or a copy of another project's private strategies. No third-party project source code was vendored. There are no non-standard-library runtime dependencies.

The v2 source was inspected and the system rebuilt around more durable accounting and testing. Prior results were not carried over as v3 profit.

## Public projects studied for engineering patterns

**0106ss/polymarket-market-scanner** — https://github.com/0106ss/polymarket-market-scanner

Its public documentation describes read-only scanning, conservative fee uncertainty, depth-aware execution checks, persistence and reporting. Its MIT license was inspected. These engineering ideas informed the new implementation; no source files were imported or copied. No Polymarket trading or account connection is implemented.

**Viprasol-Tech/kalshi-trading-bot** — https://github.com/Viprasol-Tech/kalshi-trading-bot

Reviewed public architectural descriptions of strategy modules, risk controls and testing. Its executable trading components were not installed, audited or reused. No claim is made about profitability or security of that repository.

**jabrahamtech/oraclebook** — https://github.com/jabrahamtech/oraclebook

Mentioned in v2 as a snapshot/replay inspiration. Source retrieval was unsuccessful during this build, so it was not relied on as inspected implementation evidence and no code was copied.

## What 'improved' means here

Concrete improvements are inspectable and tested: persistent integer-money ledger, event-group risk, conservative depth walking, separate demo/replay experiments, two-observation confirmation, expired/rule-bound forecasts, explicit research-only market eligibility, error/backoff handling, settlement reconciliation, local controls, diagnostics and tests. None demonstrates a trading edge. The reversion strategy and its parameters are new experimental baselines, not borrowed or verified profitable algorithms.

Public documentation/API schema references appear in CANADA_AND_DATA.md. Those protocols, not another bot's marketing claims, define source integration. Official source accessibility was not verified from this container because outbound DNS failed; diagnostics are included for the installation machine.

No GitHub repository was created, pushed or modified. The user's DEX projects remain untouched. The shipped GitHub workflow runs offline tests only after the user chooses to upload it.
