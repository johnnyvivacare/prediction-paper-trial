"""GitHub-hosted bounded paper trial. Execution is always simulation only."""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import json
import logging
import math
import os
from pathlib import Path
import re
import signal
import sys
import tempfile
import time
import uuid

from finder.config import DEFAULT, validate
from finder.core import Fee, utcnow
from finder.runtime import Runtime, SingleInstance
from .state import GitState, StateError, make_checkpoint, restore_checkpoint, passphrase
from .report import public_snapshot, write_report, usd


def read_profile(path: Path) -> dict:
    p=json.loads(path.read_text())
    if set(p) != {'profile','trial_days','checkpoint_samples_per_ticker'}:
        raise StateError('Unknown or missing GitHub profile setting.')
    if p['profile'] not in {'minute-burst','economy'}:
        raise StateError('Profile must be minute-burst or economy.')
    if type(p['trial_days']) is not int or not 1 <= p['trial_days'] <= 7:
        raise StateError('Use a bounded test of one to seven days.')
    if type(p['checkpoint_samples_per_ticker']) is not int or not 120 <= p['checkpoint_samples_per_ticker'] <= 1000:
        raise StateError('Checkpoint sample retention must be 120..1000 per ticker.')
    return p


def config_for(profile: dict) -> dict:
    return validate({**DEFAULT, 'scan_seconds': 60 if profile['profile']=='minute-burst' else 300,
                     'retention_days': 7})


def restore_source(runtime):
    saved=runtime.store.meta('github_source_cache')
    if not saved: return
    try:
        cached=json.loads(saved)
        runtime.source.cursor=int(cached.get('cursor',0))
        runtime.source.last_refresh=float(cached.get('last_refresh',0))
        runtime.source.series=cached.get('series',{})
        runtime.source.fees={k:Fee(**v) for k,v in cached.get('fees',{}).items()}
        runtime.source.health=cached.get('health',runtime.source.health)
        # PublicClient backoff must survive ephemeral-runner restarts.
        blocked=cached.get('blocked_until_epoch',0)
        if isinstance(blocked,(int,float)) and math.isfinite(blocked):
            runtime.source.client.blocked_until=time.monotonic()+max(0,blocked-time.time())
        runtime.source.client.failures=max(0,min(10,int(cached.get('failures',0))))
    except (ValueError, TypeError, KeyError):
        runtime.source.last_refresh=0
        runtime.source.fees={}


def save_source(runtime):
    from dataclasses import asdict
    source=runtime.source
    if source is None:return
    wanted={m.series for m in getattr(source,'catalog',{}).values()} | set(runtime.config['series'])
    client=getattr(source,'client',None)
    remaining=max(0,getattr(client,'blocked_until',0)-time.monotonic())
    cached={
        'cursor':getattr(source,'cursor',0), 'last_refresh':getattr(source,'last_refresh',0),
        'series':{k:v for k,v in getattr(source,'series',{}).items() if k in wanted},
        'fees':{k:asdict(v) for k,v in getattr(source,'fees',{}).items() if k in wanted},
        'health':getattr(source,'health',{}),
        'blocked_until_epoch':time.time()+remaining,
        'failures':getattr(client,'failures',0),
    }
    runtime.store.setmeta('github_source_cache',json.dumps(cached))


def compact_history(runtime, keep: int):
    """Preserve ALL fills/accounting; only rolling observations and diagnostics shrink.

    Replay of discarded snapshots is unavailable; this is disclosed in the guide.
    """
    keep=max(keep, runtime.config['reversion_window']*3+10)
    with runtime.store.connect() as db:
        db.execute('''DELETE FROM snapshots WHERE id IN (
          SELECT id FROM (SELECT id,ROW_NUMBER() OVER(PARTITION BY ticker ORDER BY ts DESC,id DESC) AS n
          FROM snapshots) WHERE n>?)''',(keep,))
        db.execute('DELETE FROM signals WHERE id NOT IN (SELECT id FROM signals ORDER BY id DESC LIMIT 5000)')
        db.execute("DELETE FROM events WHERE id NOT IN (SELECT id FROM events ORDER BY id DESC LIMIT 2000) AND kind NOT IN ('OPEN','EXIT','SETTLE','CONFIG_CHANGED')")


@contextmanager
def batch_deadline(seconds: int):
    def expired(*_): raise TimeoutError('Batch time budget reached; next run will not replay missed minutes.')
    prior=signal.signal(signal.SIGALRM,expired)
    signal.alarm(seconds)
    try: yield
    finally:
        signal.alarm(0);signal.signal(signal.SIGALRM,prior)


def scan_batch(runtime, count: int, run_id: str, expires: float,
               clock=utcnow, monotonic=time.monotonic, sleep=time.sleep) -> dict:
    if count not in {1,5}:raise StateError('Only one or five scans are permitted per batch.')
    receipts=json.loads(runtime.store.meta('github_processed_runs','[]'))
    if run_id in receipts or runtime.store.meta('github_last_run')==run_id:
        return {'scans':0,'duplicate':True,'expired':False,'engine_error':False}
    if clock()>=expires:
        return {'scans':0,'duplicate':False,'expired':True,'engine_error':False}
    start=monotonic(); completed=0;engine_error=False
    for index in range(count):
        if clock()>=expires or monotonic()-start>=360:break
        if index:
            delay=start+index*runtime.config['scan_seconds']-monotonic()
            if delay>0:sleep(delay)
            elif -delay>=runtime.config['scan_seconds']:
                # Do not bunch up stale scan slots to "catch up".
                break
        if clock()>=expires:break
        try:
            runtime.cycle();completed+=1
        except Exception:
            logging.exception('Paper engine batch stopped')
            runtime.store.setmeta('paused','true')
            runtime.store.event('GITHUB_BATCH_ERROR','Engine exception; entries paused. Inspect encrypted checkpoint locally.')
            engine_error=True;break
    runtime.store.setmeta('github_last_run',run_id)
    runtime.store.setmeta('github_processed_runs',json.dumps((receipts+[run_id])[-5000:]))
    runtime.store.setmeta('github_batches',str(int(runtime.store.meta('github_batches','0'))+1))
    return {'scans':completed,'duplicate':False,'expired':clock()>=expires,'engine_error':engine_error}


def output(key,value):
    dest=os.environ.get('GITHUB_OUTPUT')
    if dest:
        with open(dest,'a') as f:f.write(f'{key}={value}\n')


def write_summary(text):
    path=os.environ.get('GITHUB_STEP_SUMMARY')
    if path:
        with open(path,'a') as f:f.write(text+'\n')


def execute(operation: str, root: Path, output_root: Path, initialize_confirmed=False) -> int:
    repository=os.environ.get('GITHUB_REPOSITORY','')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+',repository):
        raise StateError('Run the cloud workflow in your own GitHub repository.')
    if repository.lower()=='johnnyvivacare/paper-dex-logger':
        raise StateError('Use a separate prediction repository. This package must not modify either DEX bot.')
    run_id=os.environ.get('GITHUB_RUN_ID','')
    if not re.fullmatch(r'[0-9]+',run_id):raise StateError('A GitHub workflow run ID is required.')
    secret=passphrase(os.environ.get('STATE_PASSPHRASE',''))
    if os.environ.get('REPOSITORY_PRIVATE')=='true' and os.environ.get('ACK_PRIVATE_ACTIONS_COSTS')!='true':
        raise StateError('Private Actions can incur substantial charges. Set ACK_PRIVATE_ACTIONS_COSTS=true only after checking your budget.')
    if operation=='initialize' and not initialize_confirmed:
        raise StateError('Initialization must be an explicit manual workflow action.')
    profile=read_profile(root/'github_profile.json')
    output_root.mkdir(parents=True,exist_ok=True)
    output_root.chmod(0o700)
    output('persisted','false');output('report_ready','false');output('trial_expired','false');output('backup_checkpoint','false')
    with tempfile.TemporaryDirectory(prefix='prediction-private-') as td:
        temp=Path(td)
        log=logging.FileHandler(temp/'application.log')
        logging.basicConfig(level=logging.INFO,handlers=[log],force=True)
        remote=GitState(root)
        incoming=temp/'incoming.gpg'
        existing=remote.fetch(incoming,initialize=operation=='initialize')
        data=temp/'paper'
        if existing:
            if operation=='initialize':
                raise StateError('This experiment already exists. Initialization refuses to erase or replace it; select scan.')
            meta=restore_checkpoint(incoming,data,secret,repository)
            runtime=Runtime(data,mode='paper')
            if runtime.store.meta('github_profile')!=profile['profile']:
                raise StateError('Cadence changed mid-experiment. Restore the original profile or use a separate new repository.')
            restore_source(runtime)
        else:
            runtime=Runtime(data,mode='paper',config=config_for(profile))
            now=utcnow();experiment=str(uuid.uuid4())
            runtime.store.setmeta('github_experiment',experiment)
            runtime.store.setmeta('github_profile',profile['profile'])
            runtime.store.setmeta('github_trial_expires',str(now+profile['trial_days']*86400))
            runtime.store.setmeta('github_batches','0')
            meta={'repository':repository,'experiment':experiment,'sequence':0,'created_at':now}
            runtime.store.event('GITHUB_INITIALIZE','New bounded paper test; starting funds are simulated, not a deposit.')
        expires=float(runtime.store.meta('github_trial_expires','0'))
        result={'scans':0,'duplicate':False,'expired':utcnow()>=expires,'engine_error':False}
        with SingleInstance(data/'scanner.lock'):
            if operation=='pause':
                runtime.store.setmeta('paused','true')
                runtime.store.event('GITHUB_PAUSE','New paper entries paused through authenticated workflow controls.')
            elif operation=='resume':
                if utcnow()>=expires:raise StateError('Trial expired; resume cannot extend or restart it.')
                runtime.store.setmeta('paused','false')
                runtime.store.event('GITHUB_RESUME','Manual resume requested; daily loss, drawdown and all risk limits remain in force.')
            elif operation=='scan':
                with batch_deadline(360):
                    result=scan_batch(runtime,5 if profile['profile']=='minute-burst' else 1,run_id,expires)
            # Expired read-only scans don't rewrite the ledger indefinitely.
            if operation=='scan' and result['expired'] and result['scans']==0:
                output('trial_expired','true')
                snapshot=public_snapshot(runtime,profile['profile'],expires,utcnow())
                write_report(snapshot,output_root/'site')
                output('report_ready','true')
                write_summary('### Paper trial expired\nNo scan or new trade was attempted. Disable the scheduled workflow and review results. No account is funded or connected.')
                return 0
            if result['duplicate']:
                write_summary('This workflow run already has a saved checkpoint. No duplicate scans or paper entries were made.')
                return 0
            if result['expired']:output('trial_expired','true')
            day=time.strftime('%Y-%m-%d',time.gmtime())
            need_backup=runtime.store.meta('github_backup_day')!=day
            if need_backup:runtime.store.setmeta('github_backup_day',day)
            save_source(runtime)
            compact_history(runtime,profile['checkpoint_samples_per_ticker'])
            meta.update(sequence=meta['sequence']+1,updated_at=utcnow(),last_run_id=run_id,
                        code_sha=os.environ.get('GITHUB_SHA',''))
            recovery=output_root/'state.gpg'
            make_checkpoint(runtime,recovery,secret,meta)
            # Re-read and audit the encrypted file before changing the remote pointer.
            verify=temp/'verification'
            restore_checkpoint(recovery,verify,secret,repository)
            remote.publish(recovery)
            output('persisted','true')
            output('backup_checkpoint','true' if need_backup else 'false')
            snapshot=public_snapshot(runtime,profile['profile'],expires,utcnow())
            write_report(snapshot,output_root/'site')
            output('report_ready','true')
            good=runtime.health.get('state')=='OK'
            message=('### Encrypted paper checkpoint saved\n'
                     f'Completed scans: **{result["scans"]}**. Feed state: **{runtime.health.get("state","UNKNOWN")}**. '
                     f'Account audit: **reconciled**. Trial profile: **{profile["profile"]}**.\n\n'
                     'This is a saved software-test result, not real earnings. No brokerage account is connected.\n')
            if os.environ.get('PUBLISH_PAPER_SUMMARY')=='true':
                p=snapshot['portfolio'];message+=f'\nPaper equity: **{usd(p["equity_units"])}**; total paper P&L: **{usd(p["total_pnl_units"])}**.\n'
            else:
                message+='\nFinancial details and the dashboard are not public. PUBLISH_PAPER_SUMMARY is off.\n'
            write_summary(message)
            if result['engine_error']:return 2
            if operation=='scan' and result['scans'] and not good:
                write_summary('\n**Attention:** the checkpoint was saved, but the public feed was degraded or unavailable. No fabricated prices were substituted.')
                return 3
            return 0


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--operation',choices=['initialize','scan','pause','resume'],default='scan')
    p.add_argument('--root',type=Path,default=Path.cwd())
    p.add_argument('--output',type=Path,default=Path('.github-output'))
    p.add_argument('--confirm-initialize',action='store_true')
    args=p.parse_args()
    try:return execute(args.operation,args.root.resolve(),args.output.resolve(),args.confirm_initialize)
    except Exception as exc:
        # Deliberately no tracebacks or arbitrary provider notes in public job logs.
        public=str(exc) if isinstance(exc,StateError) else 'Unexpected checkpoint/runtime failure. No live orders exist; review workflow setup and the last encrypted checkpoint.'
        output('halt_workflow','true')
        print('Paper test stopped safely: '+public,file=sys.stderr)
        write_summary('### Paper test stopped\n'+public+'\n\nThe bot did not reset its account or submit live orders.')
        return 1

if __name__=='__main__':
    raise SystemExit(main())
