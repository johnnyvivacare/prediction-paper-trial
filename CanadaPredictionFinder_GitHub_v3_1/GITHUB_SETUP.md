# GitHub setup — Canada Prediction Finder 3.1

This edition runs on GitHub. Your Mac is only needed for uploading the project or viewing the website, not for keeping the scanner running. Nothing has already been deployed to your account.

The default is a **seven-day, US$500 paper-only software trial**. No real-money account, brokerage login, private wallet key or live-order capability is included. Canadian executable market access is still unverified.

## 1. Create a separate repository and upload the files

On GitHub, create a new repository named `canada-prediction-finder` under your account. Do **not** use `paper-dex-logger`: leave both existing DEX bots unchanged.

Choose visibility knowingly. A public repository exposes source code and workflow logs; standard public GitHub-hosted runner compute is free under the published billing rules, subject to terms and limits. A private repository hides source but may incur significant Actions charges. The saved account is encrypted in either case. Do not publish real account credentials or personal forecasts.

Unzip `CanadaPredictionFinder_GitHub_v3_1.zip`. Upload the **contents of the extracted folder**, not the ZIP and not another enclosing folder. On GitHub use **Add file → Upload files**, or use your existing Git/GitHub Desktop workflow. Include the hidden `.github` directory. On a Mac, **Command–Shift–Period** shows hidden files in Finder.

At the repository root, confirm these exist:

```
.github/workflows/paper-scan.yml
.github/workflows/tests.yml
github_profile.json
github_support/
finder/
app.py
README.md
```

Do not upload a local `ledger.sqlite3`, passphrase text file, `.env`, log, exported forecasts or private data directory. The supplied ZIP contains no initialized ledger or encryption secret.

## 2. Save one encryption secret

Generate a new random passphrase and save it in your password manager. A terminal command that creates 64 random hexadecimal characters is:

```
openssl rand -hex 32
```

Do not send the result in chat or commit it to the repository.

Open **Settings → Secrets and variables → Actions → Secrets → New repository secret**.

Name: `STATE_PASSPHRASE`

Value: the generated passphrase.

The code requires at least 32 characters. This protects saved paper results; it is **not** a trading API key. Losing or changing it without migrating your checkpoint makes the old encrypted state unreadable. No reset will occur automatically.

## 3. Check the profile and costs before initialization

The included `github_profile.json` contains:

```json
{
  "profile": "minute-burst",
  "trial_days": 7,
  "checkpoint_samples_per_ticker": 360
}
```

`minute-burst` requests five scans 60 seconds apart within each nominal five-minute Actions batch. Scheduling, setup, provider backoff and runtime limits cause gaps. It is not a guaranteed 60-second feed. The automatic strategy needs 60 prior usable observations and confirmation on a later scan; gaps can prevent a signal indefinitely.

The alternative `economy` profile performs one scan per five-minute batch. Change the profile **before** initialization, not in the middle of a trial. Economy mode needs roughly five hours of regularly spaced data for 60 prior observations; gaps can make it longer. It still uses runner minutes.

Private-repository warning: 288 nominal batches/day × at least four minutes between the first and fifth scan is about **1,152 runner minutes/day before overhead**, or **8,064 minutes over a nominal seven-day trial**, before setup, final scans, report deployments and billing rounding. Public standard-runner compute and private allowances differ; check your account's current plan, storage and budget settings. Do not assume this is free in a private repository.

For a private repository, the workflow refuses to start until you explicitly create this **Actions repository variable** after reviewing costs:

`ACK_PRIVATE_ACTIONS_COSTS` = `true`

Repository variables are under **Settings → Secrets and variables → Actions → Variables**. Do not put passphrases in Variables; those are for non-secret settings.

## 4. Run initialization once

Open **Actions → Offline safety tests** and check the tests on the default branch. Resolve failures before enabling the paper test.

Then open **Actions → Prediction paper trial → Run workflow**. Select your default branch, set operation to **initialize**, and run it.

This creates a new encrypted paper account with **US$500 and zero trades**. It creates only the reserved state branch, `prediction-paper-state`. It does not call a trading account, and initialization itself does not scan markets.

Initialization refuses to overwrite an existing state branch. For subsequent runs choose **scan**, not initialize.

The workflow requests contents write permission for the state branch and Actions write permission to disable its own schedule after trial expiry. A restrictive organization policy may block these permissions. Keep the source branch protected; do not broadly weaken repository protections. Any branch rule that forbids force updates must exempt only `prediction-paper-state` for its checkpoint rotation, or this deployment method will stop on its next save.

## 5. Test a scan, then enable automatic runs

Use **Run workflow → scan** once. Check the run summary, not just the existence of a green test workflow.

A market-source failure can produce a failed scan job even when the encrypted account was saved safely. No fabricated data will replace missing quotes. `DEGRADED`, `ERROR`, `NO_DATA`, `HISTORY_GAP` and no paper trades are meaningful outcomes. A code-test pass does not establish live data access or profitability.

After the manual scan is acceptable, create the Actions repository variable:

`ENABLE_PAPER_SCANS` = `true`

The schedule is `2-59/5 * * * *` in UTC, away from the top of the hour. GitHub may delay or drop scheduled starts. Jobs are serialized; a new job cannot overlap an account writer and may replace a pending queued job under GitHub concurrency rules.

Once enabled, the Mac can be off. The browser does not need to stay open.

## 6. Optional public dashboard

Financial publication is off by default. To publish the aggregate paper report:

Open **Settings → Pages → Build and deployment → Source → GitHub Actions**. Then create this Actions repository variable:

`PUBLISH_PAPER_SUMMARY` = `true`

Run **scan** again. The workflow's publish job uses GitHub Pages and reports the actual site URL after a successful deployment. The report will show paper equity, P&L, cash, closed/open position counts, drawdown, ledger audit, feed health and timestamps. It is a static checkpoint, not a live interactive trading terminal. Refresh the page for a later published checkpoint.

**Treat the website as public.** A private repository does not by itself guarantee a private Pages site, and Pages availability depends on your GitHub plan. Do not enable this variable to publish information you want kept private.

No full positions, market titles/tickers, forecasts, application logs, raw quote history, database or account secrets appear in the report. It has no order buttons or privileged controls. Once marks are stale, current open-position equity/P&L are labelled stale rather than represented as live values.

Leaving the variable unset keeps financial details out of public run summaries and skips publication. A summary can still report generic scan status and accounting-health status. If you later turn publication off, **the last already-published website remains visible** until you unpublish it in Pages settings. Turning the variable off is not a deletion request.

## 7. Stop, pause and expiry

To pause only new paper entries, use **Run workflow → pause**. Existing paper positions can still receive exit/settlement handling on later scans. **resume** requests entries again but does not remove daily-loss or drawdown halts.

To stop all scanning, set `ENABLE_PAPER_SCANS` to `false` and disable **Prediction paper trial** from its Actions menu. This does not close any simulated positions; no real positions exist in this release.

Seven days after initialization, the scanner refuses new scans and the workflow attempts to disable itself. A scheduling delay may postpone that cleanup job. If GitHub denies the disable request, manually disable the workflow to avoid repeated setup-only runs. No live mode is enabled at expiry and there is no automatic trial extension. Archive and review the ledger before deliberately beginning another separate experiment. Do not erase losing results.

## Recovery and integrity

The state branch contains encrypted `state.gpg` and, after a second save, `previous.gpg`. Each completed batch creates a verified checkpoint and replaces only that branch with a compare-and-swap Git lease. Source code and the normal Git index are not rewritten.

Missing, corrupt or unreadable current state stops the application and requests that its workflow be disabled. After fixing the problem, explicitly re-enable that workflow before retrying. It does not reset to US$500 and does not silently select a possibly stale previous checkpoint. A failed remote save attempts to upload an encrypted recovery artifact; daily backup artifacts are also attempted and expire after seven days. Check actual upload outcomes. Keep an independent copy of both the encrypted checkpoint and its passphrase.

If a runner is killed before checkpoint publication, that unfinished batch may be lost. A successful earlier checkpoint remains, but this is not uninterrupted sampling. Published reports are created only after state is saved, except for a clearly expired read-only report.

The local inspection command below requires GnuPG and Python 3.10+ on a trusted machine; it decrypts without running a network scanner. Download `state.gpg`, run from the extracted project folder, and replace the repository string with your exact owner/name:

```python
from getpass import getpass
from pathlib import Path
from github_support.state import restore_checkpoint
restore_checkpoint(
    Path("state.gpg"),
    Path("private-inspection"),
    getpass("State passphrase: "),
    "johnnyvivacare/canada-prediction-finder",
)
```

Then `python app.py report --data-dir private-inspection` produces a read-only local report. Do not upload the decrypted directory. If recovery from an older checkpoint is necessary, keep the original and record the rollback as a limitation; do not pretend all runs survived.

## What has and has not been tested

The release passed 153 offline Linux tests, including encrypted persistence of simulated fills, full local Git save/restore, wrong-key/corruption rejection, conflict detection, privacy checks and run receipts. It does not rely on third-party Python packages.

This environment could not reach the public feed because DNS was unavailable. The actual GitHub runner, account permissions, Actions billing and Pages deployment have not been tested in your account. The first manual scan is the integration test.

No profit, Canadian brokerage access or future real-money trading capability is promised. This remains a separate research project alongside—not a replacement for—the two DEX bots.
