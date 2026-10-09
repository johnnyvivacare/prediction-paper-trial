# v3.0 test report

Build date: October 8, 2026. This report describes software checks, not trading performance.

## Executed successfully

**109 automated offline tests passed** under Linux and Python 3.13.5. They cover exact monetary parsing, fee estimates, complementary book depth, partial fills, crossing/schema rejection, market identity, unknown fees, stale/future observations, no same-tick entries, two-scan confirmation, rule changes, event risk, duplicate entries, stop/partial exits, one-time binary settlement, cash reconciliation, restart persistence, separate demo ledgers, risk/config circuit breakers, forecast timing/uncertainty, no-lookahead signals/replay, local backup, GET-only endpoint allowlisting, provider backoff, and local HTTP controls/security.

Source compilation (`compileall`) succeeded. All eight macOS `.command` launchers passed Bash syntax checking. The headless CLI demo completed with its ledger reconciled. The fabricated two-trade example generated one win and one loss; those numbers are not a market backtest and are not included as v3 paper profit.

The local HTTP server was exercised with standard-library HTTP requests: dashboard/static assets, state/report/CSV export, same-origin/session-token control checks, Host-header rejection, traversal rejection, and absence of an order route.

The UI was rendered in headless Chromium from the actual demo state using offline in-memory responses. The desktop view (1440 px) and mobile view (390 px) were inspected. All five tabs and forecast-rule display were exercised, no JavaScript page errors were recorded, and mobile document width matched the viewport without horizontal page overflow. Browser navigation to the local HTTP URL was blocked by the container's browser policy, so this was an offline rendering check, not an end-to-end live-browser connection. Server integration was tested separately as above.

## Not verified

- The Mac installer and LaunchAgent were **not executed on macOS**. The included test workflow declares a macOS/Python matrix but was not pushed or run on GitHub.
- Public-feed connectivity from this build environment **failed**, with a DNS name-resolution error. The code follows the official documented interface, but no successful end-to-end live market scan was verified here. Run Check.command on the installation Mac. A schema/access error must be investigated, not bypassed or replaced with fabricated prices.
- No actual market paper P&L, live-money profit, validated predictive advantage, complete historical exchange backtest, or verified Canadian broker-equivalent fill was established.
- No independent penetration test, notarization, external code audit or guarantee of bug-free behavior is claimed.

## Reproduce locally

From the package folder, after installation:

```
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/python -m compileall -q app.py finder tests mac_autostart.py
.venv/bin/python app.py doctor --network
.venv/bin/python app.py demo --once
```

The first two are offline software checks. The network diagnostic is deliberately separate. A green software test suite is not evidence that a strategy makes money or that every market is available to a Canadian trader.

The release archive also includes `docs/test-evidence/unittest.txt`, `browser.json` and `network.json`. Environment-specific paths in the evidence are build paths, not instructions for your Mac. The packaged ZIP is integrity-checked and smoke-tested after extraction; its SHA-256 is distributed separately. Checksums verify transfer consistency, not authorship or trading safety.
