# v3.0 compared with v1/v2

## Rebuilt

- One persistent local runtime rather than a sequence of ephemeral GitHub jobs.
- Exact-money ledger with atomic cash/position/fill updates, backup and restart protection.
- Real observed depth and conservative two-sided execution assumptions instead of a price-only fill.
- Event-level and category limits rather than only per-ticker budgeting.
- Automatic experimental strategy with a warm-up; independent supplied forecasts remain a separate strategy.
- Rule-bound, time-stamped forecasts and source-verified, idempotent binary settlement.
- Honest unknown equity when liquidity or data are missing.
- Responsive local dashboard, paper-only controls, audit, logs, CSV/report exports and replay.
- macOS setup/run/diagnostic/awake scripts and explicitly opt-in login autostart.
- 109 automated offline tests at initial completion, plus packaging/browser/CLI checks detailed in TEST_REPORT.md.

## Deliberately not added

No live account access, order placement, forecast-sales subscription, unsupported source scraping, platform restriction bypass, copied unreviewed GitHub trading code, automatic import of v2 profits, or claim of a proven strategy. No implemented Canadian broker/ForecastEx feed. These are substantive limitations, not hidden switches.
