"""Single-writer runtime. One-minute target, persistent state and honest source health."""
from __future__ import annotations
import json
import logging
import os
import threading
import time
from dataclasses import asdict
from pathlib import Path
from .analytics import ledger_audit, performance
from .config import load
from .core import Market, money, utcnow, iso
from .engine import Engine
from .sources import KalshiPublic
from .store import Store


class Runtime:
    def __init__(self, directory:Path, mode:str='paper', config:dict|None=None, source=None):
        self.directory=Path(directory)
        self.directory.mkdir(parents=True,exist_ok=True)
        self.directory.chmod(0o700)
        self.config=config or load(self.directory/'config.json')
        path=self.directory/'config.json'
        if not path.exists():path.write_text(json.dumps(self.config,indent=2)+'\n')
        self.store=Store(self.directory/'ledger.sqlite3',money(self.config['starting_cash_usd']),mode)
        self.store.setmeta('config_current',json.dumps(self.config,sort_keys=True))
        if not self.store.meta('config_original'):
            self.store.setmeta('config_original',json.dumps(self.config,sort_keys=True))
        self.engine=Engine(self.store,self.config)
        self.source=source if source is not None else (KalshiPublic(self.store,self.config) if mode=='paper' else None)
        self.mode=mode
        self.stop=threading.Event()
        self.lock=threading.RLock()  # Serialize dashboard controls and each simulation cycle.
        self.last_cycle=float(self.store.meta('last_cycle','0'))
        self.risk_reason='WARMING_UP'
        self._report_cache=None
        self._report_time=0.0
        if not ledger_audit(self.store)['ok']:
            self.store.setmeta('paused','true')
            raise ValueError('Ledger audit failed. No scanner started; inspect data/backup before continuing.')

    @property
    def health(self):
        if self.source:return self.source.health
        return {'state':self.mode.upper(),'note':'Fabricated offline example; not market performance.' if self.mode=='demo' else 'Historical snapshot replay; not forward results.', 'last_success':self.last_cycle}

    def cycle(self):
        try:
            batch=self.source.batch(utcnow()) if self.source else []
        except Exception as exc:
            logging.exception('Source cycle failed')
            self.store.event('SOURCE_ERROR',str(exc))
            if self.source:self.source.health.update(state='ERROR',note=str(exc)[:600])
            batch=[]
        now=utcnow()
        with self.lock:
            for m,b,f in batch:
                self.store.save_market(m,now)
                if b is None:
                    self.engine.settle(m,now)
                    with self.store.connect() as db:db.execute('DELETE FROM marks WHERE ticker=?',(m.ticker,))
                elif f:self.engine.mark(m,b,f,now)
            # Mark all held positions before making any entry decisions.
            for m,b,f in batch:
                if b is not None and f is not None:self.engine.observe(m,b,f,now)
            self.last_cycle=now
            self.store.setmeta('last_cycle',str(now))
            self.store.record_equity(now,self.config['max_quote_age_seconds'])
            _,self.risk_reason=self.engine.risk_state(now)
            if not ledger_audit(self.store)['ok']:
                self.store.setmeta('paused','true')
                self.risk_reason='LEDGER_AUDIT_FAILED'
                self.store.event('AUDIT_FAILURE','New entries disabled; review ledger and backups.')
            day=self.engine.day(now)
            if self.store.meta('last_backup_day')!=day:
                self.backup()
                self.store.prune(now,self.config['retention_days'])
                self.store.setmeta('last_backup_day',day)
            self._report_time=0

    def loop(self):
        while not self.stop.is_set():
            started=time.monotonic()
            try:self.cycle()
            except Exception as exc:
                logging.exception('Paper cycle failed')
                self.store.event('ENGINE_ERROR',str(exc))
                self.store.setmeta('paused','true')
                self.risk_reason='ENGINE_ERROR_ENTRIES_PAUSED'
            elapsed=time.monotonic()-started
            # Never start overlapping scans or replay missed intervals in a burst.
            self.stop.wait(max(1,self.config['scan_seconds']-elapsed))

    def backup(self) -> Path:
        stamp=time.strftime('%Y%m%d-%H%M%S',time.gmtime())
        dest=self.directory/'backups'/('ledger-'+stamp+'.sqlite3')
        self.store.backup(dest)
        existing=sorted(dest.parent.glob('ledger-*.sqlite3'))
        for old in existing[:-7]:old.unlink()
        self.store.event('BACKUP','Local SQLite backup created; keep an external copy for device failure.')
        return dest

    def state(self, csrf:str='') -> dict:
        now=utcnow()
        with self.lock:
            if self._report_cache is None or time.monotonic()-self._report_time>30:
                self._report_cache=performance(self.store,now,self.config['max_quote_age_seconds'])
                self._report_time=time.monotonic()
            markets=[]
            for row in self.store.rows('SELECT payload,updated FROM markets ORDER BY updated DESC LIMIT 300'):
                try:
                    item=json.loads(row['payload']);item['observed_at']=row['updated'];markets.append(item)
                except ValueError:continue
            _,reason=self.engine.risk_state(now)
            return {'csrf':csrf,'mode':self.mode,'config':self.config,
                'portfolio':self.store.portfolio(now,self.config['max_quote_age_seconds']),
                'performance':self._report_cache,'health':dict(self.health),'last_cycle':self.last_cycle,
                'paused':self.store.meta('paused')=='true','risk_reason':reason or self.risk_reason,
                'audit':ledger_audit(self.store),'markets':markets,
                'positions':self.store.rows('SELECT * FROM positions ORDER BY entry DESC LIMIT 200'),
                'signals':self.store.rows('SELECT * FROM signals ORDER BY ts DESC,id DESC LIMIT 80'),
                'events':self.store.rows('SELECT * FROM events ORDER BY ts DESC,id DESC LIMIT 40'),
                'equity':self.store.rows('SELECT ts,value FROM (SELECT id,ts,value FROM equity ORDER BY id DESC LIMIT 1440) ORDER BY id')}


class SingleInstance:
    """Advisory lock released by the OS, even after a crash; macOS/Linux only."""
    def __init__(self,path:Path):self.path=Path(path);self.handle=None
    def __enter__(self):
        import fcntl
        self.path.parent.mkdir(parents=True,exist_ok=True)
        self.handle=open(self.path,'a+')
        try:fcntl.flock(self.handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc:
            self.handle.close();self.handle=None
            raise RuntimeError('This experiment is already running. Open its existing dashboard instead.') from exc
        self.handle.seek(0);self.handle.truncate();self.handle.write(str(os.getpid()));self.handle.flush()
        return self
    def __exit__(self,*args):
        if self.handle:
            import fcntl
            fcntl.flock(self.handle,fcntl.LOCK_UN);self.handle.close()
