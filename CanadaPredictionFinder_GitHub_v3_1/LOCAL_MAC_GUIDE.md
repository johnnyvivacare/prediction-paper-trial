# Canada Prediction Finder v3.0 — Research Lab

**An installable, local paper-trading research application. Not a proven money-making system. No live execution, account login, wallet, API key, or broker connection exists in this release.**

Start with **START_HERE.html**. The application uses Python's standard library only: no paid services, pip packages, or language-model subscriptions are required.

## The important Canadian limitation

The implemented market source is **public, unauthenticated Kalshi research data**. Reading a public price does not establish that a Canadian resident can trade that contract. Every position is labelled `RESEARCH_ONLY`. There is **no implemented ForecastEx, IBKR Canada, or Wealthsimple quote/execution adapter**, and no verified mapping to your brokerage's available contracts. Do not treat these simulated returns as returns achievable through a Canadian account.

IBKR's January 22, 2026 announcement confirms eligible Canadian clients can access forecast contracts, with availability varying by affiliate and residence. ForecastEx's public data page describes pairs refreshed every ten minutes and daily closing prices, not a one-minute executable bid/ask depth feed. The program does not pretend those files provide real-time fills. See [Canada and data limitations](docs/CANADA_AND_DATA.md).

## Installation on your Mac

1. Unzip the folder and place it somewhere permanent, such as your Applications folder. Leave your two DEX projects untouched.
2. Double-click **Install.command**. It checks Python 3.10+, creates a local environment without downloading dependencies, runs the offline tests, and checks local storage. Python itself must already be installed; the installer prints the official download address when missing.
3. Double-click **Check.command** to test public-feed access, then **Start.command**. The local dashboard opens at `http://127.0.0.1:8765`.

Keep the Terminal process running, the Mac awake, and the network connected. Control-C in that Terminal stops the scanner. Closing only the browser does not stop it. The optional **Start-Awake.command** prevents idle sleep while running; it does not defeat lid closure, shutdown, or network loss. Connect power and leave the lid open.

**Report.command** prints the current paper report without making trades or changing cash.

**Demo.command** opens a completely separate, fabricated preview on port 8766. Demo profits are software fixtures, not market performance. Never fund an account based on them.

If macOS will not launch a downloaded shell script, review the file first, then run it from Terminal with `bash` followed by the dragged-in `Install.command` path. Do not disable Gatekeeper globally. Missing Python or certificate errors are explained in [troubleshooting](docs/TROUBLESHOOTING.md).

## What is actually included

| Capability | Implementation |
|---|---|
| Scan cadence | Continuous local process, 60-second target; no overlapping scans or catch-up bursts |
| Market coverage | Selected economics/financial/climate series; capped catalog, stable watch slots plus rotation; held contracts get priority |
| Automatic research strategy | Experimental price mean-reversion, requiring 60 prior time-spaced observations and two-scan confirmation |
| Independent-value strategy | User-supplied probability, uncertainty interval, source, method, expiry and exact settlement-rule fingerprint |
| Paper execution | Actual observed bid depth and complementary ask depth, whole-contract sizing, 25% depth participation, adverse slippage and conservative fees |
| Durable ledger | SQLite WAL, transactional cash accounting in $0.0001 units, crash/restart persistence and reconciliation |
| Risk controls | 2% per event including related strikes; 20% total and 6% per category; daily loss, drawdown and entry-count gates |
| Exits | Stop, target, time limit, near-close and user-requested paper exit; partial fills supported, unavailable exits not invented |
| Settlement | Wait for source `settled`/`finalized` YES/NO, reject provisional/inconsistent outcomes and changed rules, credit only once |
| Dashboard | Local-only responsive interface, equity, cash, realized/open P&L, decisions, positions, source errors, strategy statistics and controls |
| Evaluation | Event-level bootstrap screen, cost stress test, Brier score for settled supplied forecasts, incomplete-valuation warnings |
| Maintenance | Rotating application logs, daily local SQLite backup retaining seven copies, snapshot retention and opt-in login autostart |
| Export and replay | CSV exports, JSON report, chronological replay of retained local snapshots in a separate ledger |
| Security | No order route, no credentials, GET-only allowlisted source, no redirects/bypass, loopback host/origin checks and session-token controls |

The automated reversion strategy estimates a **future price target**, not the probability of the event. It can be wrong when a sharp move reflects real information. It has no demonstrated profitable edge. The value strategy is not an autonomous economic or weather forecaster; it needs a researched, independently justified forecast. A market's own price is not an independent forecast.

## What to expect initially

The real-data paper ledger starts at **US$500, zero trades, zero verified profit**. Catalog discovery happens first. Stable watched markets need about an hour of uninterrupted observations before the automatic strategy can signal; market rotation, gaps and slow data can lengthen this. Signals must survive a later scan, costs, depth and all risk gates. Several hours or days without a trade can be legitimate. Do not reduce safeguards just to force activity.

`OK` means a data cycle succeeded, not that the strategy is profitable. `DEGRADED`, `NO_DATA`, `ERROR`, `FEE_UNKNOWN`, `HISTORY_GAP` and `UNPRICEABLE_OPEN_POSITION` are meaningful states, not numbers to hide. If a position cannot be valued from sufficient fresh bid depth, equity and open P&L become unavailable rather than misleadingly carrying an optimistic value.

All cash is simulated USD. The displayed win rate counts fully closed positions, not signals or scans. A high win rate alone is not evidence of profit. See [methodology](docs/METHODOLOGY.md).

## Data and upgrades

On macOS, private data lives outside the application folder:

```
~/Library/Application Support/CanadaPredictionFinder/paper/
~/Library/Application Support/CanadaPredictionFinder/demo/
```

Each directory contains `config.json`, `ledger.sqlite3`, logs and `backups/`. Updating/unzipping the code does not reset your money or silently replace the ledger. Close the old process before starting the new one. A single-instance lock prevents duplicate scanner processes for the same experiment.

V1/v2 ledgers are **not automatically imported into v3 performance**. Those versions used different execution and accounting assumptions. Keep them as historical archives; start v3 as a new trial. Do not rename a v2 database to the v3 filename.

Settings are read at startup. Once the first position has opened, strategy/risk settings are fingerprinted. Changing them pauses new entries in that ledger. For a clean experiment use a new `--data-dir`; do not edit the database to erase losses or unlock a drawdown halt. Existing paper exits/settlements can still be processed. Storage/network/presentation settings are not all part of the strategy fingerprint.

Local backups protect against some software mistakes, not laptop loss. Copy the private data directory to your own secure backup storage. Do not publish ledgers, forecasts, logs, or exports in a public GitHub repository. The included `.gitignore` excludes common private files.

## Optional login autostart

Stop the foreground scanner first. Keep the application folder in a permanent place, then run **Enable-Autostart.command**, read the notice, and type `ENABLE`. It installs only this application's user LaunchAgent and starts it at login. It does not stop the Mac sleeping. Open the dashboard manually after login. **Disable-Autostart.command** removes only that agent; it does not delete the ledger.

This is explicitly opt-in and is not performed by Install.command. The LaunchAgent has not been executed on macOS in the build environment; local verification is still required.

## Command-line use

From this application folder:

```bash
python3 -m unittest discover -s tests -v
python3 app.py doctor --network
python3 app.py run --open
python3 app.py run --once
python3 app.py demo --open --port 8766
python3 app.py report
python3 app.py run --data-dir "$HOME/PredictionExperiments/trial-002" --port 8767 --open
python3 app.py replay \
  --source "$HOME/Library/Application Support/CanadaPredictionFinder/paper/ledger.sqlite3" \
  --destination "$HOME/PredictionExperiments/replay-001/ledger.sqlite3"
```

Replay consumes already recorded v3 observations. It is not a download of years of historical exchange data, does not reconstruct user pauses/manual exits, and is not an independent forward trial. It never rewrites the source ledger.

## GitHub

The included workflow tests source code on a Linux/macOS and Python-version matrix. It has not been pushed or run in your account. It does **not** host the bot or store a live paper ledger. GitHub scheduled workflows cannot guarantee minute-by-minute execution; this release instead keeps the scanner and durable state together on your Mac. No writes were made to either DEX repository.

## Tests and limits

See [test report](docs/TEST_REPORT.md) for actual executed checks and unverified items. At build time, 109 offline tests passed on Linux/Python 3.13.5. A Chromium offline UI render was checked at desktop/mobile sizes, with local HTTP security/controls tested separately. macOS installation and live public-feed connectivity are not verified; this environment's outbound DNS failed. Included diagnostics must be run on your Mac.

**No real-money performance was measured. No paper market profit has been established. No configuration switch enables live trading.** Even positive forward results would require a separate Canadian broker integration, exact contract/fee checks, independent review, and an explicit decision before any funded trade.
