# Troubleshooting

## Python missing

Install Python 3.10 or newer for macOS from https://www.python.org/downloads/macos/ and rerun Install.command. The scripts also check common Homebrew/local Python locations. They never silently install Homebrew or download an arbitrary remote shell script. A standard-library virtual environment is created without pip dependencies.

## A command file opens in an editor or macOS will not launch it

Review the file. In Terminal, type `bash `, drag Install.command into the window to insert its quoted path, then press Return. Afterwards the Start.command file can be run the same way. Do not turn off security software or Gatekeeper globally. These are unsigned scripts, not a notarized native application.

## Feed check fails

Run Check.command and read the exact error. DNS, offline Wi-Fi and temporary server failures do not prove the source is unavailable everywhere. Authentication/403/451 denials and geographic restrictions must not be bypassed. A 429 causes backoff; avoid adding more scanners. For `CERTIFICATE_VERIFY_FAILED` with a python.org installation, follow that distribution's macOS certificate-installation instructions (the supplied Install Certificates.command in its Applications folder when present). Never disable HTTPS verification. There is no fake-data fallback in paper mode.

## No trades / warm-up

The app waits for a sufficiently stable watch history, then tests opportunities after fees, liquidity and risk. Default automatic warm-up needs at least 60 correctly spaced prior samples, usually about an hour on pinned markets with no gaps. A forecast does not remove liquidity/fee/confirmation/risk checks. A quiet strategy can be correct. Check Scanner decisions before modifying settings.

## Blank equity or P&L

At least one open position may lack enough fresh, valid bid depth to value or exit. A blank value is deliberate. The app does not value such a position at the ask or keep an old profitable mark forever. Settlement is not guessed from the clock. Look for changed settlement terms, missing fees, finalization delay and source errors.

## 'Already running' or port in use

Open the existing dashboard. Do not run Start.command and an enabled login agent at the same time. Disable-Autostart.command stops/removes the app's login agent, then the foreground launcher can be used. Different experiments require different data directories AND ports. Do not delete a lock file while a process is active: the OS lock belongs to the open file.

## Config change or drawdown halt

Existing ledgers are not reset by reinstalling. Once a trade opens, changed strategy/risk assumptions block new entries in that ledger. Start a new explicitly labelled trial via `app.py run --data-dir /your/new/folder --port 8767`. Preserve the old results. A latched drawdown breaker is not cleared by Resume entries. Do not edit the database to erase losses or force it open.

## Resume after the Mac sleeps

Start.command cannot scan while the Mac sleeps. Start-Awake.command prevents idle sleep while it is running; keep the lid open and power connected. Forced sleep, closed-lid behavior, shutdown and loss of connectivity can still stop observations. After a gap, stale marks and strategy history may need refreshing/warm-up. No missed trades are retroactively invented.

## Data safety and disk use

Private data is in `~/Library/Application Support/CanadaPredictionFinder/`. Daily backups retain seven files. Snapshot/decision logs default to 30 days; trades, fills, forecasts and equity history are retained. Storage can grow to hundreds of megabytes or more with continuous sampling; watch free disk space. Copy backups securely off the device. If the disk fills, stop, preserve the ledger and resolve storage before resuming. The database is protected by local permissions but is not application-encrypted.

## Ledger audit failure

The scanner refuses startup or pauses new entries after an audit failure. Preserve the current data directory and backups. Do not start a fresh ledger under the old name to hide the discrepancy. Investigation/restoration is a deliberate manual operation; the app never silently swaps an older backup for current positions.

## Reinstall or move the application

Stop scanning and disable autostart before moving the application. A virtual environment can contain absolute paths; recreate `.venv` by moving that directory aside and rerunning Install.command in the new location. Never move/delete the private ledger as part of reinstalling code. Reenable autostart only after the folder is in its final location.
