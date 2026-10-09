"""Encrypted SQLite checkpoints; rotating, lease-protected state-only Git branch.

No plaintext database, forecast, application log, or credentials are committed.
GnuPG handles authenticated decryption; its exit status is checked before use.
"""
from __future__ import annotations
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sqlite3
import subprocess
import tempfile
import zipfile

BRANCH = 'prediction-paper-state'
MAX_ENCRYPTED = 24 * 1024 * 1024
MAX_DATABASE = 160 * 1024 * 1024
FILES = {'ledger.sqlite3', 'config.json', 'checkpoint.json'}


class StateError(RuntimeError):
    pass


def passphrase(value: str) -> str:
    if not isinstance(value, str) or len(value) < 32 or len(value) > 1024 or any(c in value for c in '\r\n\x00'):
        raise StateError('STATE_PASSPHRASE must be a saved random secret of 32+ characters, without line breaks.')
    return value


def _gpg(source: Path, destination: Path, secret: str, decrypt: bool) -> None:
    passphrase(secret)
    if not shutil.which('gpg'):
        raise StateError('GnuPG is required; use the included Ubuntu GitHub runner.')
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='prediction-gpg-') as home:
        os.chmod(home, 0o700)
        command = ['gpg', '--homedir', home, '--batch', '--yes', '--quiet',
                   '--pinentry-mode', 'loopback', '--passphrase-fd', '0',
                   '--no-symkey-cache', '--output', str(destination)]
        command += ['--decrypt'] if decrypt else ['--symmetric', '--cipher-algo', 'AES256',
                     '--s2k-mode', '3', '--s2k-count', '65011712', '--compress-algo', 'none']
        command.append(str(source))
        try:
            result = subprocess.run(command, input=(secret+'\n').encode(), capture_output=True, timeout=60)
        except (OSError, subprocess.TimeoutExpired) as exc:
            destination.unlink(missing_ok=True)
            raise StateError('Checkpoint encryption/decryption did not finish safely.') from exc
        finally:
            if shutil.which('gpgconf'):
                subprocess.run(['gpgconf', '--homedir', home, '--kill', 'gpg-agent'],
                               capture_output=True, timeout=10)
        if result.returncode:
            destination.unlink(missing_ok=True)
            raise StateError('Checkpoint decryption/authentication failed; no reset or older-state fallback was attempted.'
                             if decrypt else 'Checkpoint encryption failed; nothing was published.')
    destination.chmod(0o600)


def make_checkpoint(runtime, destination: Path, secret: str, metadata: dict) -> None:
    from finder.analytics import ledger_audit
    if not ledger_audit(runtime.store)['ok']:
        raise StateError('Ledger does not reconcile; refusing to replace the last good checkpoint.')
    with tempfile.TemporaryDirectory(prefix='prediction-checkpoint-') as td:
        folder = Path(td)
        database = folder/'ledger.sqlite3'
        runtime.store.backup(database)
        # SQLite backup may retain free pages; reclaim them before packaging.
        with closing(sqlite3.connect(database)) as db:
            db.execute('VACUUM')
        if database.stat().st_size > MAX_DATABASE:
            raise StateError('Checkpoint database exceeded the trial size limit. Archive/review it before continuing.')
        config = json.dumps(runtime.config, sort_keys=True).encode()
        metadata = {**metadata, 'format': 1,
                    'database_sha256': hashlib.sha256(database.read_bytes()).hexdigest(),
                    'config_sha256': hashlib.sha256(config).hexdigest()}
        archive = folder/'checkpoint.zip'
        with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as z:
            z.write(database, 'ledger.sqlite3')
            z.writestr('config.json', config)
            z.writestr('checkpoint.json', json.dumps(metadata, sort_keys=True))
        _gpg(archive, destination, secret, False)
        if destination.stat().st_size > MAX_ENCRYPTED:
            destination.unlink(missing_ok=True)
            raise StateError('Encrypted checkpoint exceeded 24 MiB; trial stopped before uploading it.')


def restore_checkpoint(source: Path, directory: Path, secret: str, repository: str) -> dict:
    from finder.config import validate
    from finder.analytics import ledger_audit
    from finder.store import Store
    if not source.is_file() or source.stat().st_size > MAX_ENCRYPTED:
        raise StateError('Checkpoint is missing or exceeds the permitted size.')
    if directory.exists() and any(directory.iterdir()):
        raise StateError('Restore destination must be empty; refusing to overwrite local results.')
    directory.mkdir(parents=True, exist_ok=True)
    directory.chmod(0o700)
    with tempfile.TemporaryDirectory(prefix='prediction-restore-') as td:
        temp = Path(td)
        archive = temp/'checkpoint.zip'
        _gpg(source, archive, secret, True)
        try:
            with zipfile.ZipFile(archive) as z:
                entries = z.infolist()
                if len(entries) != 3 or {i.filename for i in entries} != FILES:
                    raise StateError('Unexpected checkpoint members; refusing extraction.')
                for i in entries:
                    limit = MAX_DATABASE if i.filename == 'ledger.sqlite3' else 1024*1024
                    if i.file_size > limit or i.is_dir():
                        raise StateError('Invalid checkpoint size or file type.')
                meta = json.loads(z.read('checkpoint.json'))
                config = z.read('config.json')
                database = z.read('ledger.sqlite3')
        except (zipfile.BadZipFile, json.JSONDecodeError, KeyError) as exc:
            raise StateError('Checkpoint archive is invalid.') from exc
        if (meta.get('format') != 1 or meta.get('repository') != repository
                or not isinstance(meta.get('sequence'), int) or meta['sequence'] < 1
                or not isinstance(meta.get('experiment'), str)):
            raise StateError('Checkpoint identity/version does not match this repository.')
        if (hashlib.sha256(config).hexdigest() != meta.get('config_sha256') or
                hashlib.sha256(database).hexdigest() != meta.get('database_sha256')):
            raise StateError('Checkpoint integrity check failed.')
        validate(json.loads(config))
        dbpath = temp/'ledger.sqlite3'
        dbpath.write_bytes(database)
        # Read-only validation BEFORE Store can create tables or default cash.
        with closing(sqlite3.connect(dbpath.as_uri()+'?mode=ro', uri=True)) as db:
            if db.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                raise StateError('SQLite checkpoint is corrupt.')
            recorded = dict(db.execute('SELECT key,value FROM meta'))
            if (recorded.get('schema') != '3' or recorded.get('mode') != 'paper'
                    or recorded.get('github_experiment') != meta['experiment']
                    or db.execute('SELECT COUNT(*) FROM cash').fetchone()[0] != 1):
                raise StateError('Missing account identity or cash record; no reset is allowed.')
        store = Store(dbpath, mode='paper')
        if not ledger_audit(store)['ok']:
            raise StateError('Restored ledger failed its accounting audit.')
        store.backup(directory/'ledger.sqlite3')
        (directory/'config.json').write_bytes(config)
        (directory/'config.json').chmod(0o600)
        return meta


class GitState:
    """Use Git plumbing and a separate index; never change source/index/branches.

    The state branch has one reachable commit and two encrypted checkpoints.
    A force-with-lease replaces ONLY this reserved branch if it is unchanged.
    Remote garbage collection of superseded objects is controlled by GitHub.
    """
    def __init__(self, checkout: Path, branch: str = BRANCH):
        if branch != BRANCH:
            raise StateError('Only the reserved prediction-paper-state branch may be written.')
        self.root = checkout.resolve()
        self.branch = branch
        self.expected = ''
        self.current = None
        self.fetched = False

    def git(self, *args, input: bytes | None = None, env: dict | None = None, check=True):
        result = subprocess.run(['git', '-C', str(self.root), *args], input=input,
                                capture_output=True, timeout=90, env=env)
        if check and result.returncode:
            # Avoid returning remote URLs, auth headers or other potentially sensitive stderr.
            raise StateError('Git checkpoint operation failed. Check repository write permission, connectivity and state-branch rules.')
        return result

    def fetch(self, destination: Path, initialize: bool = False) -> bool:
        ref = 'refs/heads/'+self.branch
        found = self.git('ls-remote', '--exit-code', 'origin', ref, check=False)
        if found.returncode == 2:
            if not initialize:
                raise StateError('No remote checkpoint exists. Run Initialize once; scheduled scans never create a replacement account.')
            self.expected = ''; self.fetched = True
            return False
        if found.returncode:
            raise StateError('Cannot verify remote state; refusing to initialize or scan.')
        parts = found.stdout.decode().strip().split()
        if len(parts) != 2 or not re.fullmatch(r'[0-9a-f]{40,64}', parts[0]) or parts[1] != ref:
            raise StateError('Unexpected remote state reference.')
        self.expected = parts[0]
        self.git('fetch', '--no-tags', '--depth=1', 'origin', self.expected)
        size = self.git('cat-file', '-s', self.expected+':state.gpg')
        if int(size.stdout) > MAX_ENCRYPTED:
            raise StateError('Remote checkpoint exceeds the download size limit.')
        data = self.git('show', self.expected+':state.gpg').stdout
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes(data); destination.chmod(0o600)
        self.current = destination; self.fetched = True
        return True

    def publish(self, checkpoint: Path) -> str:
        if not self.fetched:
            raise StateError('Fetch remote state before attempting a write.')
        if not checkpoint.is_file() or checkpoint.stat().st_size > MAX_ENCRYPTED:
            raise StateError('Checkpoint is missing or too large.')
        with tempfile.TemporaryDirectory(prefix='prediction-index-') as td:
            env = dict(os.environ)
            env['GIT_INDEX_FILE'] = str(Path(td)/'index')
            env.update(GIT_AUTHOR_NAME='github-actions[bot]', GIT_COMMITTER_NAME='github-actions[bot]',
                       GIT_AUTHOR_EMAIL='41898282+github-actions[bot]@users.noreply.github.com',
                       GIT_COMMITTER_EMAIL='41898282+github-actions[bot]@users.noreply.github.com')
            self.git('read-tree', '--empty', env=env)
            blobs = {'state.gpg': checkpoint.read_bytes(),
                     'README.txt': b'Encrypted paper-test checkpoints only. Never merge this branch into the source branch.\n'}
            if self.current is not None:
                blobs['previous.gpg'] = self.current.read_bytes()
            for name, content in blobs.items():
                oid = self.git('hash-object', '-w', '--stdin', input=content).stdout.decode().strip()
                self.git('update-index', '--add', '--cacheinfo', '100644,'+oid+','+name, env=env)
            tree = self.git('write-tree', env=env).stdout.decode().strip()
            commit = self.git('commit-tree', tree, '-m', 'Encrypted paper-test checkpoint', env=env).stdout.decode().strip()
            ref = 'refs/heads/'+self.branch
            self.git('push', '--force-with-lease='+ref+':'+self.expected, 'origin', commit+':'+ref)
        self.expected = commit
        return commit
