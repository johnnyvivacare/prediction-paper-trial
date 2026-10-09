# Canada Prediction Finder 3.1 — GitHub Edition

**Runs a bounded paper-trading software trial on GitHub Actions, without keeping your Mac awake. It does not trade real money and has no demonstrated profitable edge.**

Start with **[GITHUB_SETUP.md](GITHUB_SETUP.md)**. Upload the extracted project files, including `.github`, into a **new, separate repository**. Do not upload only the ZIP and do not replace either DEX bot.

## What changed from the Mac-only v3

| Capability | GitHub Edition |
|---|---|
| Runs without your Mac | GitHub-hosted Ubuntu workflow; disabled until you initialize and opt into scheduling |
| Requested minute scanning | Five scans targeting 60 seconds apart inside each nominal five-minute batch; delays, gaps and skipped batches are possible |
| Durable paper account | US$500 starting ledger restored from an encrypted checkpoint before each run |
| Private state | Database and forecasts encrypted using GnuPG/AES256; no plaintext state, logs or forecasts committed |
| Write-conflict protection | Serialized workflow plus a Git compare-and-swap lease; only the reserved state branch is replaced |
| No silent reset | Missing, corrupt, mismatched or undecryptable state halts the run; explicit initialization cannot overwrite an existing trial |
| Read-only dashboard | Optional public aggregate results through GitHub Pages; financial publication is off until explicitly enabled |
| Paper controls | Authenticated workflow actions for pause/resume; risk halts stay in force |
| Bounded trial | Seven days by default, then no more scans; the workflow attempts to disable its own schedule |
| Safer restarts | Completed-run receipts, persisted provider backoff, rolling observation history and ledger reconciliation |
| Original engine | v3 paper risk controls and costs retained; confirmation timing now follows the configured scan cadence |

**This fixes hosting, not the Canadian-market data gap.** The feed remains keyless public Kalshi research data, not verified executable quotes from a Canadian broker. There is no IBKR Canada, Wealthsimple or ForecastEx account/quote adapter. Research results cannot be assumed achievable through your funded account. No live mode or brokerage credentials exist.

## Scheduling and costs

GitHub's minimum scheduled interval is five minutes, and scheduled jobs can be delayed or dropped. The default `minute-burst` profile does five observations per batch, but is **not a continuous one-minute trading service**. Risk checks and paper exits only run when observations actually arrive.

A nominal 24-hour day has 288 five-minute batches. Five scans span four minutes before the final scan finishes, so the waiting alone is about 1,152 runner minutes/day. A hypothetical 30-day continuation would be 34,560 minutes before overhead; **the supplied trial stops after seven days**. Public repositories using standard runners have free compute under GitHub's published billing rules, but storage limits, terms and policies still apply. Private repositories have a plan allowance and can incur substantial charges; the workflow blocks private runs without an explicit cost acknowledgement. Optional report deployments add runner usage.

This package is for bounded software testing and evaluation, not using Actions as an always-on funded trading backend. Review GitHub's Actions terms and your current billing settings before enabling it. Official references are in [docs/GITHUB_REFERENCES.md](docs/GITHUB_REFERENCES.md).

## Credentials and privacy

No trading API key is needed. You do need one **state-encryption secret**, `STATE_PASSPHRASE`, stored in GitHub Actions Secrets and backed up in your password manager. It is not a brokerage key. GitHub provides the limited per-run token used to save the encrypted checkpoint and disable this workflow at expiry.

Publishing the optional dashboard exposes aggregate paper balances, P&L, performance and timestamps. It never publishes detailed positions, raw quotes, forecasts, account keys, application logs or the database. Treat any GitHub Pages report as public even when the source repository is private. Leave `PUBLISH_PAPER_SUMMARY` unset to keep financial summaries unpublished.

Do not give untrusted collaborators write access: someone who can change a trusted workflow can try to read its secrets. Never commit a password file, account credentials, local data directory or decrypted checkpoint.

## Reliability and limits

The last **successfully saved batch** is durable. If a runner is terminated before checkpoint publication, that unfinished batch can be lost. Do not mistake this for uninterrupted sampling. A rejected state write fails the run; an encrypted recovery artifact is attempted, but older state is never silently selected as a fallback.

Only the most recent 360 observation snapshots per ticker are retained by default, alongside bounded diagnostic logs; **all cash flows, trades, positions and equity records are retained**. Older raw order-book replay is therefore unavailable after compaction. No profits are deleted to improve results. State files have hard size caps; this is not indefinite database hosting.

The reserved `prediction-paper-state` branch contains a current and previous encrypted checkpoint in a single reachable commit. It uses force-with-lease on that branch only, never on your source branch. GitHub controls eventual garbage collection of superseded Git objects; rotating reachable state is not a guarantee of immediate storage reclamation. Daily encrypted artifact backup is best-effort and retained for seven days. Keep an independent encrypted backup and the secret.

## Verification status

**153 offline automated tests passed on Linux**, including encrypted save/restore of actual simulated fills, wrong-key/corruption rejection, conflicting writers, duplicate runs, profile timing, privacy allowlists and a complete local bare-Git-repository workflow simulation.

The workflow YAML was parsed locally and the static dashboard was checked at desktop/mobile sizes. **The workflow has not been executed in your GitHub account, GitHub Pages publication has not been verified there, and a live market feed could not be tested from this environment because outbound DNS is unavailable.** The first manual scan is your deployment test, not proof of profitability.

The old local launchers remain available for optional offline inspection; they are not required to keep the GitHub trial running. See [LOCAL_MAC_GUIDE.md](LOCAL_MAC_GUIDE.md) only for local use. V1/v2/v3 results are not automatically imported or merged into this new cloud trial.
