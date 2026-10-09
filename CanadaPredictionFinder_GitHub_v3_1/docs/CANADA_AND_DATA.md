# Canada, data and eventual funded-account boundaries

Documentation reviewed for this build: October 8, 2026. Availability and terms can change; this is not a legal determination for a specific account.

## Verified distinction

Interactive Brokers' January 22, 2026 announcement says eligible clients of Interactive Brokers Canada can access forecast contracts, with product availability varying by affiliate and country of residence. That does not establish that your account has the permission, that every public Kalshi ticker is listed by your broker, or that the same quote/fees are available.

ForecastEx's public data page describes pairs data refreshed every ten minutes, daily closing prices and daily activity summaries. These are not a validated one-minute executable bid/ask book. There is no ForecastEx parser or broker integration in this release.

Kalshi's official quick-start documents unauthenticated public REST access to series, markets and order books. That makes a keyless research reader possible; it says nothing by itself about Canadian trading membership, automated data-use permissions or broker access. Earlier project discussions flagged Canadian direct-trading restrictions. This software neither resolves jurisdictional eligibility nor proposes opening/funding a restricted account. It makes no eligibility claim about direct Kalshi trading.

## Implemented boundary

All current market and position records are `RESEARCH_ONLY`. The interface does not relabel a Kalshi public quote as a Canadian broker quote. Setting `require_canada_verification` to true deliberately stops all new entries because no contract in this release has such verification. It does not unlock access.

No VPN/proxy route, location spoofing, credential input, browser account automation, trade API call, wallet or payment flow exists. A denied data request pauses; it is not bypassed. No account should be funded merely to use this app.

## Before any future live system

A separate project would need to establish the permitted Canadian broker interface, your approved account and product permissions, authenticated read-only data as appropriate, exact contract identity and settlement equivalence, actual brokerage quote depth and fees, capital/currency mechanics, permissions for automation, and a reviewed execution adapter with position reconciliation and an emergency stop. Access to another exchange's prices or positive research P&L cannot substitute for these checks.

The current package has no live execution mode or credential-storage path. Do not paste account passwords or keys into the forecast form, config, GitHub or chat.

## Primary sources

- Kalshi public market-data quick start: https://docs.kalshi.com/getting_started/quick_start_market_data
- Kalshi order-book contract: https://docs.kalshi.com/api-reference/market/get-market-orderbook
- Kalshi market schema: https://docs.kalshi.com/api-reference/market/get-markets
- Kalshi series and fees metadata: https://docs.kalshi.com/api-reference/market/get-series
- Kalshi fee explanation: https://help.kalshi.com/en/articles/13823805-fees
- Kalshi fee schedule: https://kalshi.com/docs/kalshi-fee-schedule.pdf
- ForecastEx public data description: https://forecastex.com/data
- Interactive Brokers Canada eligibility statement: https://www.interactivebrokers.ca/en/general/about/mediaRelations/1-22-26.php
- Wealthsimple Predict description, for future independent eligibility review only; not integrated: https://help.wealthsimple.com/hc/en-ca/articles/51862041944219-Understanding-Wealthsimple-Predict
- GitHub scheduled-workflow limitations: https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows

Successful HTTP access is not financial/regulatory permission. Confirm all current applicable terms before continued use.
