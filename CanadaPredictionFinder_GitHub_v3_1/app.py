#!/usr/bin/env python3
"""Canada Prediction Finder v3 — local read-only research and paper trading."""
from __future__ import annotations
import argparse
from contextlib import closing
import json
import logging
from logging.handlers import RotatingFileHandler
import os
from pathlib import Path
import signal
import sys
import threading
import time
import webbrowser

if sys.version_info<(3,10):
    raise SystemExit('Python 3.10 or newer is required. Install a supported Python from python.org.')

from finder.analytics import ledger_audit,performance
from finder.config import load
from finder.core import utcnow
from finder.runtime import Runtime,SingleInstance
from finder.server import create_server


def default_root():
    if sys.platform=='darwin':return Path.home()/'Library'/'Application Support'/'CanadaPredictionFinder'
    return Path.home()/'.local'/'share'/'CanadaPredictionFinder'


def doctor(directory,network=False):
    from zoneinfo import ZoneInfo
    from finder.network import PublicClient
    result={'python':sys.version.split()[0],'platform':sys.platform,'data_directory':str(directory),
            'live_execution':'NOT IMPLEMENTED','network_checked':network,'checks':{}}
    directory.mkdir(parents=True,exist_ok=True)
    probe=directory/'.write-probe'
    try:probe.write_text('ok');probe.unlink();result['checks']['data_writable']=True
    except OSError:result['checks']['data_writable']=False
    try:ZoneInfo('America/Vancouver');result['checks']['timezone_available']=True
    except Exception:result['checks']['timezone_available']=False
    try:
        c=load(directory/'config.json');result['checks']['config_valid']=True
    except Exception as exc:result['checks']['config_valid']=False;result['config_error']=str(exc)
    if network:
        try:
            data=PublicClient().get('series/KXHIGHNY')
            result['checks']['public_feed_reachable']=isinstance(data.get('series'),dict)
        except Exception as exc:
            result['checks']['public_feed_reachable']=False;result['network_error']=str(exc)
    result['ok']=all(result['checks'].values())
    return result


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    for name in ('run','demo','doctor','report'):
        p=sub.add_parser(name)
        p.add_argument('--data-dir',type=Path,help='Experiment directory; default is durable per-user storage')
        if name in {'run','demo'}:
            p.add_argument('--open',action='store_true',help='Open local browser dashboard')
            p.add_argument('--once',action='store_true',help='Perform one cycle then print report, no web server')
            p.add_argument('--port',type=int,help='Override dashboard port without changing strategy')
        if name=='doctor':p.add_argument('--network',action='store_true',help='Also test the keyless public read-only endpoint')
    p=sub.add_parser('replay');p.add_argument('--source',type=Path,required=True);p.add_argument('--destination',type=Path,required=True)
    args=parser.parse_args()
    if args.command=='replay':
        from finder.replay import replay
        print(json.dumps(replay(args.source,args.destination),indent=2));return 0
    mode='demo' if args.command=='demo' else 'paper'
    directory=(args.data_dir or default_root()/mode).expanduser().resolve()
    if args.command=='doctor':
        result=doctor(directory,args.network);print(json.dumps(result,indent=2));return 0 if result['ok'] else 1
    if args.command=='report':
        if not (directory/'ledger.sqlite3').is_file():raise ValueError('No paper ledger yet. Start the application first.')
        # Read-only reporting uses an online SQLite snapshot, leaving original config/ledger unchanged.
        from finder.store import Store
        import tempfile,sqlite3
        with tempfile.TemporaryDirectory() as td:
            dest=Path(td)/'report.sqlite3'
            with closing(sqlite3.connect((directory/'ledger.sqlite3').as_uri()+'?mode=ro',uri=True)) as src:
                with closing(sqlite3.connect(dest)) as out:src.backup(out)
            s=Store(dest,mode='paper')
            print(json.dumps({'portfolio':s.portfolio(utcnow()),'performance':performance(s),'audit':ledger_audit(s)},indent=2))
        return 0
    directory.mkdir(parents=True,exist_ok=True);directory.chmod(0o700)
    with SingleInstance(directory/'scanner.lock'):
        log=RotatingFileHandler(directory/'application.log',maxBytes=2_000_000,backupCount=3)
        logging.basicConfig(level=logging.INFO,handlers=[log,logging.StreamHandler()],format='%(asctime)s %(levelname)s %(message)s')
        c=load(directory/'config.json')
        if args.port is not None:
            if not 1024<=args.port<=65535:raise ValueError('Port must be 1024..65535')
            c['port']=args.port
        runtime=Runtime(directory,mode,c)
        if mode=='demo':
            from finder.demo import populate
            populate(runtime)
        if args.once:
            if mode=='paper':runtime.cycle()
            print(json.dumps(runtime.state(),indent=2));return 0
        server=create_server(runtime,c['port'])
        stopped=threading.Event()
        def stop(*_):stopped.set();runtime.stop.set()
        signal.signal(signal.SIGINT,stop);signal.signal(signal.SIGTERM,stop)
        web=threading.Thread(target=server.serve_forever,daemon=True);web.start()
        worker=None
        if mode=='paper':worker=threading.Thread(target=runtime.loop,daemon=True);worker.start()
        url=f'http://127.0.0.1:{c["port"]}'
        print(f'\nPAPER RESEARCH ONLY — NO LIVE ORDERS\nDashboard: {url}\nPrivate data: {directory}\nKeep this process running and the Mac awake. Control-C stops it.\n',flush=True)
        if args.open:webbrowser.open(url)
        try:
            while not stopped.wait(.5):pass
        finally:
            runtime.stop.set();server.shutdown();server.server_close()
            if worker:
                worker.join(timeout=c['request_timeout_seconds']+5)
                # A daemon worker still finishing network I/O cannot have overlapping scans;
                # process exit releases its lock. SQLite transactions are atomic on interruption.
            runtime.backup()
        return 0

if __name__=='__main__':
    try:raise SystemExit(main())
    except (ValueError,RuntimeError,OSError) as exc:
        print('Cannot start safely: '+str(exc),file=sys.stderr)
        raise SystemExit(1)
