# Methodology and evaluation limits

## 1. Observation and coverage

A single persistent process attempts a cycle every 60 seconds. Cycles do not overlap. Slow requests, provider backoff, startup discovery, sleep and internet interruptions cause visible gaps; missed scans are not replayed in bursts. Catalog refresh is every 15 minutes. By default eight selected series and 240 catalog markets are allowed, with up to 16 order books sampled per cycle. Open positions and unexpired user forecasts are prioritized. Most remaining slots stay stable to build history; a small rotating tail improves discovery. This is a limited watchlist, not comprehensive market coverage and not an exchange-wide arbitrage search.

All current source requests are unauthenticated, allowlisted public Kalshi HTTPS GETs. No cookies or credentials are required by the documented endpoints. A 403/451 does not trigger proxies or alternate hosts; the source pauses. A 429 honors Retry-After. No redirect or TLS bypass exists. A failed source remains failed; fabricated fixtures are never substituted into real-data paper mode.

Order books use the documented fixed-point bid arrays. A NO bid of $0.59 with quantity 20 supplies a YES ask of $0.41 with quantity 20, not unlimited quantity. Missing sides do not become executable quotes. Inconsistent crossed books are rejected rather than reported as free arbitrage. Only plain $1 binary contracts with identifiable settlement terms are supported. Market data receipts are timestamped locally; this is not proof of exchange-internal timestamp freshness. Responses with an explicit stale cache-age header are rejected.

## 2. Experimental price-reversion strategy

The baseline needs 60 prior observations spaced at least 55 seconds apart, rejects sparse/stale history, and compares the new midpoint with the prior mean and standard deviation. A 1-cent volatility floor avoids a nearly constant window creating infinite confidence. The default deviation threshold is 2.5 standard deviations. It proposes the side that would benefit from price reverting toward the previous mean, with a 3-cent target haircut. Estimated round-trip fees, slippage and at least 4 cents of additional edge must be covered.

This is a falsifiable experiment, NOT an independent event probability estimator, news forecaster, guaranteed anomaly, or finding of mispricing. A discontinuity can be an efficient response to genuine news; repeatedly buying such moves can lose money. A one-hour window is an engineering default, not an optimized or empirically validated choice. Raising scan frequency does not create an edge.

Candidates must survive two observations at least 50 seconds and at most 180 seconds apart, with consistent side, strategy, terms and target. The second observation supplies the fill book. Confirmation reduces same-tick optimism but does not replicate network latency, queue priority, cancellation races or actual broker matching.

## 3. Independent-value strategy

The user supplies a point probability, lower/upper uncertainty range, independent source/rationale, method and expiration. The probability must be between 1% and 99% and the range at least four percentage points wide. The program timestamps receipt; it cannot be backdated through the UI. The forecast is bound to an exact ticker and settlement-rules hash and expires within seven days and before close.

For YES, the pessimistic lower bound is used; for NO, one minus the upper bound is used. The point estimate is saved for later calibration scoring, not used to overstate entry confidence. Today's market midpoint, a language model's unsupported guess, or a historical token-price distribution is not an independent fundamental forecast.

`empirical_probability` is an optional offline helper for at least 30 externally supplied scenario draws of an EXACT matched variable and threshold. It has no automatic data feed or UI pipeline. Its Wilson interval covers finite-sample uncertainty only, not forecast bias or structural/model risk. Do not confuse it with a validated forecasting engine.

The value strategy evaluates a $1 terminal payout, but stop/time/near-close exits can realize a different payoff earlier. This policy itself needs empirical evaluation. It has not been shown to improve expected returns.

## 4. Hypothetical execution and money

Cash is stored in integer units: 10,000 units = US$1. Prices with more than four decimals are rejected. Whole contracts only; fractional quoted size is floored. Entries consume complementary ask depth; exits consume own-side bid depth. Only 25% of displayed size at each level is assumed available. Adverse slippage is one cent per contract on entry and exit. Entry quantity must completely fit available assumed depth and the risk budget; exits may be partial.

Fee estimate per consumed level is the maximum of:

```
ceil_to_cent(0.07 * series_multiplier * contracts * price * (1-price))
ceil_to_cent(0.03 * contracts)
```

Only supported quadratic fee metadata with a recent, positive multiplier is accepted. Unknown/stale/unsupported fees block entry and fresh valuation. Rounding to a whole cent and the 3-cent floor are deliberate conservative estimates, not an exact reproduction of all current exchange or Canadian broker charges. Changing schedules, specific-product charges, rebates, currency conversion, account costs, taxes and ForecastEx coupons are not modeled. No settlement fee is modeled for supported finalized Kalshi binary contracts. Check the source schedule independently.

Risk includes entry fees. The simulator never sells at an impossible free price when estimated fees exceed proceeds: that level supplies no modeled sellable quantity. Displayed depth and conservative assumptions still do not guarantee a real fill. There is no live broker or blockchain execution simulation.

## 5. Risk and exits

Initial bankroll: US$500. Entry-risk budgets use the smaller of current priceable equity and initial capital, not an automatically compounding leverage base. Defaults: 2% per event, 6% per category, 20% total, at most six new positions per Pacific calendar day. Different strikes under the same event identifier share the event cap. Residual open risk is maximum zero or original cost minus already received proceeds. Broader correlations across different event identifiers can remain; category limits mitigate but do not model them precisely.

A 3% loss from the day's reference equity pauses new entries for that day. An 8% high-water drawdown latches a permanent new-entry halt for the experiment. Config changes after first entry also block new entries. User pause stops entries but not observation, possible exits, or settlement. No averaging down and no repeat entry into a ticker, even after closing it, in the same experiment.

The 25% stop threshold is a trigger, NOT a guaranteed maximum loss. It is based on modeled net exit proceeds versus original per-contract cost. Available exit size can be partial or absent. Reversion positions also have target exits. All positions can have a 24-hour time exit or near-close exit. User-requested paper closes wait for a new, eligible book. None of these creates missing liquidity. Worst-case per-position loss can be its full cash cost.

## 6. Settlement and accounting

`closed`, `determined` or an expired clock is not sufficient. Automatic payout waits for source status `settled` or `finalized`, a non-provisional YES/NO result, no scalar payout inconsistency, close time passed and unchanged settlement terms. Uncertain/cancelled/scalar or changed-rule resolutions remain unresolved for investigation; the program does not guess a refund. Source observations and credits are saved, and settled positions cannot be paid twice.

Realized P&L covers completely closed positions only. Proceeds from a partial exit remain attached to the open position until its final close. Cash always reconciles to initial capital less entry costs plus exit/settlement credits. Marks use sufficient fresh bid depth less assumed exit costs. If any open position lacks a complete valid mark, total equity and total/open P&L are unknown; a conservative cash-plus-supported-value floor is separately available in the state/export. Missing quotes do not mean a loss has disappeared.

A lightweight audit runs each cycle, checking the cash equation, per-position fill quantities/costs/proceeds/fees, and SQLite integrity. Local transactional storage avoids partial cash/position updates on interruption. The single-process lock prevents duplicate scanners for one experiment.

## 7. Research evidence, not permission to go live

Reports separate strategies and aggregate closed profits by event before bootstrap resampling. With at least ten events, a deterministic 2,000-resample percentile interval for mean event P&L is provided. It assumes sufficiently independent events; macro releases and related products can violate this. It is not a return forecast or rigorous proof after repeated strategy tuning.

A stress scenario subtracts an additional two cents per contract on each entry and pre-settlement exit, beyond all recorded costs. Brier scores compare supplied point probabilities with entry-market midpoints only for positions with confirmed final outcomes. Early-exit forecasts without collected final outcomes are excluded; sample counts are shown. Observed maximum drawdown excludes unknown valuation points and can understate the true path. Calendar-span days are reported, not a claim of uninterrupted sampling; gaps and warm-up still need review.

Research screens include 100 distinct closed events, 30 observed calendar days, positive closed and stress P&L, positive event-bootstrap lower bound, complete recorded valuations, no open positions, a reconciled ledger and real-data paper mode. These are screening defaults, not statistically validated minimum sample requirements. A higher trade count is not automatically better evidence; correlated trades and tuning can overfit.

**`live_trading_ready` is always false.** There is no live order adapter. Passing every screen cannot enable one. Canadian eligibility, exact equivalent contracts, brokerage prices/fees, new out-of-sample performance, independent code review and explicit user authorization remain separate requirements.

## 8. Replay and retention

Replay merges retained snapshots and final-resolution observations in timestamp order, restores original strategy configuration and only lets forecasts become visible at or after their recorded receipt time. It writes a new database. The default 30-day snapshot retention means a later replay may have incomplete early history. It does not recreate manual pauses, manual closes, changed code, provider timing or the entire historical exchange universe. Demo-source replay is still fabricated. Replaying after seeing outcomes is not a fresh forward test.
