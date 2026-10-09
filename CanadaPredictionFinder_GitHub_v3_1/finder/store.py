"""Durable SQLite ledger. All cash flows and position changes are transactional."""
from __future__ import annotations
import csv
import io
import json
import sqlite3
from contextlib import contextmanager,closing
from dataclasses import asdict
from pathlib import Path
from .core import USD, dollars, iso, utcnow

SCHEMA=3
SQL='''
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS cash(id INTEGER PRIMARY KEY CHECK(id=1),units INTEGER NOT NULL CHECK(units>=0));
CREATE TABLE IF NOT EXISTS markets(ticker TEXT PRIMARY KEY,event TEXT NOT NULL,category TEXT NOT NULL,
    updated REAL NOT NULL,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS snapshots(id INTEGER PRIMARY KEY,ts REAL NOT NULL,ticker TEXT NOT NULL,
    mid REAL,market_json TEXT NOT NULL,book_json TEXT NOT NULL,fee_json TEXT NOT NULL,
    UNIQUE(ts,ticker));
CREATE INDEX IF NOT EXISTS snapshots_ticker_time ON snapshots(ticker,ts);
CREATE TABLE IF NOT EXISTS forecasts(id INTEGER PRIMARY KEY,ticker TEXT NOT NULL,created REAL NOT NULL,
    expires REAL NOT NULL,rules_hash TEXT NOT NULL,p REAL NOT NULL,lo REAL NOT NULL,hi REAL NOT NULL,
    method TEXT NOT NULL,source TEXT NOT NULL,UNIQUE(ticker,created));
CREATE TABLE IF NOT EXISTS positions(id INTEGER PRIMARY KEY,ticker TEXT NOT NULL UNIQUE,event TEXT NOT NULL,
    category TEXT NOT NULL,title TEXT NOT NULL,strategy TEXT NOT NULL,side TEXT NOT NULL,
    qty INTEGER NOT NULL CHECK(qty>0),remaining INTEGER NOT NULL CHECK(remaining>=0),
    cost INTEGER NOT NULL,fees INTEGER NOT NULL,proceeds INTEGER NOT NULL DEFAULT 0,
    entry REAL NOT NULL,exit REAL,target INTEGER,stop INTEGER NOT NULL,rules_hash TEXT NOT NULL,
    forecast_id INTEGER,entry_market_p REAL,status TEXT NOT NULL DEFAULT 'open',
    outcome TEXT,access TEXT NOT NULL DEFAULT 'RESEARCH_ONLY');
CREATE TABLE IF NOT EXISTS fills(id INTEGER PRIMARY KEY,position_id INTEGER NOT NULL,
    ts REAL NOT NULL,action TEXT NOT NULL,qty INTEGER NOT NULL,price INTEGER NOT NULL,
    cash INTEGER NOT NULL,fee INTEGER NOT NULL,reason TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS marks(ticker TEXT PRIMARY KEY,ts REAL NOT NULL,qty INTEGER NOT NULL,
    value INTEGER NOT NULL,required INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS signals(id INTEGER PRIMARY KEY,ts REAL NOT NULL,ticker TEXT NOT NULL,
    strategy TEXT NOT NULL,side TEXT,edge REAL,decision TEXT NOT NULL,note TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,ts REAL NOT NULL,kind TEXT NOT NULL,note TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS equity(id INTEGER PRIMARY KEY,ts REAL NOT NULL,cash INTEGER NOT NULL,
    value INTEGER,lower_bound INTEGER NOT NULL,realized INTEGER NOT NULL,open_cost INTEGER NOT NULL);
CREATE TABLE IF NOT EXISTS resolutions(id INTEGER PRIMARY KEY,ts REAL NOT NULL,ticker TEXT NOT NULL UNIQUE,payload TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS risk_days(day TEXT PRIMARY KEY,opening_equity INTEGER NOT NULL,halted INTEGER NOT NULL DEFAULT 0);
'''


class Store:
    def __init__(self,path:Path,initial:int=500*USD,mode:str="paper"):
        self.path=Path(path)
        self.path.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            existing={r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if existing and "meta" not in existing:
                raise ValueError("Legacy/unknown database. Archive v2; do not mix unvalidated ledgers.")
            db.executescript(SQL)
            prior=db.execute("SELECT value FROM meta WHERE key='schema'").fetchone()
            if prior and int(prior[0])!=SCHEMA:
                raise ValueError("Unsupported database version")
            for k,v in {"schema":str(SCHEMA),"initial":str(initial),"mode":mode,"created":str(utcnow()),
                        "paused":"false","high_water":str(initial),"drawdown_halt":"false"}.items():
                db.execute("INSERT OR IGNORE INTO meta VALUES (?,?)",(k,v))
            prior_mode=db.execute("SELECT value FROM meta WHERE key='mode'").fetchone()[0]
            if prior_mode != mode:
                raise ValueError("Demo, replay and real-data paper ledgers must stay separate")
            db.execute("INSERT OR IGNORE INTO cash VALUES (1,?)",(initial,))
        try:self.path.chmod(0o600)
        except OSError:pass

    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=15)
        db.row_factory=sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=15000")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:db.close()

    def meta(self,key:str,default:str="") -> str:
        with self.connect() as db:
            r=db.execute("SELECT value FROM meta WHERE key=?",(key,)).fetchone()
            return r[0] if r else default

    def setmeta(self,key:str,value:str):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO meta VALUES (?,?)",(key,value))

    def event(self,kind:str,note:str,ts:float|None=None):
        with self.connect() as db:
            db.execute("INSERT INTO events(ts,kind,note) VALUES (?,?,?)",(utcnow() if ts is None else ts,kind,note[:2000]))

    def save_market(self,market,ts:float):
        with self.connect() as db:
            db.execute("INSERT OR REPLACE INTO markets VALUES (?,?,?,?,?)",
                (market.ticker,market.event,market.category,ts,json.dumps(asdict(market))))

    def snapshot(self,market,book,fee,ts:float):
        with self.connect() as db:
            db.execute("INSERT OR IGNORE INTO snapshots(ts,ticker,mid,market_json,book_json,fee_json) VALUES (?,?,?,?,?,?)",
                (ts,market.ticker,book.mid(),json.dumps(asdict(market)),json.dumps(asdict(book)),json.dumps(asdict(fee))))

    def history(self,ticker:str,before:float,limit:int):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT ts,mid FROM snapshots WHERE ticker=? AND ts<? AND mid IS NOT NULL ORDER BY ts DESC LIMIT ?",(ticker,before,limit))][::-1]

    def rows(self,sql:str,args:tuple=()):
        with self.connect() as db:return [dict(r) for r in db.execute(sql,args)]

    def signal(self,ts,ticker,strategy,side,edge,decision,note):
        with self.connect() as db:
            db.execute("INSERT INTO signals(ts,ticker,strategy,side,edge,decision,note) VALUES (?,?,?,?,?,?,?)",
                       (ts,ticker,strategy,side,edge,decision,note[:2000]))

    def portfolio(self,now:float,max_age:float=90) -> dict:
        with self.connect() as db:
            cash=db.execute("SELECT units FROM cash WHERE id=1").fetchone()[0]
            initial=int(db.execute("SELECT value FROM meta WHERE key='initial'").fetchone()[0])
            rows=db.execute("SELECT * FROM positions").fetchall()
            marks={r['ticker']:r for r in db.execute("SELECT * FROM marks")}
        realized=0;open_cost=0;value=0;missing=0;open_count=0;fees=0
        wins=0;closed=0
        for r in rows:
            fees+=r['fees']
            if r['status']=='open':
                open_count+=1
                # Whole-position cost/proceeds stay together until the final exit.
                open_cost+=r['cost']-r['proceeds']
                m=marks.get(r['ticker'])
                if m and 0<=now-m['ts']<=max_age and m['required']==r['remaining']:
                    value+=m['value']
                    if m['qty']<r['remaining']:missing+=1
                else:missing+=1
            else:
                closed+=1
                pnl=r['proceeds']-r['cost']
                realized+=pnl
                wins+=pnl>0
        exact=cash+value if not missing else None
        return {"initial_units":initial,"cash_units":cash,"equity_units":exact,
            "equity_floor_units":cash+value,"realized_units":realized,"open_cost_units":open_cost,
            "fees_units":fees,"unpriceable_positions":missing,"open_positions":open_count,
            "closed_positions":closed,"win_rate":wins/closed if closed else None,
            "total_pnl_units":exact-initial if exact is not None else None,
            "unrealized_units":exact-initial-realized if exact is not None else None}

    def record_equity(self,ts:float,max_age:float=90):
        p=self.portfolio(ts,max_age)
        with self.connect() as db:
            db.execute("INSERT INTO equity(ts,cash,value,lower_bound,realized,open_cost) VALUES (?,?,?,?,?,?)",
                (ts,p['cash_units'],p['equity_units'],p['equity_floor_units'],p['realized_units'],p['open_cost_units']))
        return p

    def backup(self,dest:Path):
        dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True)
        with self.connect() as src:
            with closing(sqlite3.connect(dest)) as out:src.backup(out)
        dest.chmod(0o600)

    def prune(self,now:float,days:int):
        cutoff=now-days*86400
        with self.connect() as db:
            db.execute("DELETE FROM snapshots WHERE ts<?",(cutoff,))
            db.execute("DELETE FROM signals WHERE ts<?",(cutoff,))
            db.execute("DELETE FROM events WHERE ts<? AND kind NOT IN ('OPEN','EXIT','SETTLE','CONFIG_CHANGED')",(cutoff,))
            # Keep all equity, fills, closed trades and forecasts for performance evaluation.

    def export_csv(self,table:str) -> str:
        if table not in {"positions","fills","signals","equity","forecasts","events"}:
            raise ValueError("Unsupported export")
        with self.connect() as db:
            cur=db.execute("SELECT * FROM "+table+" ORDER BY 1")
            names=[d[0] for d in cur.description]
            stream=io.StringIO(newline="");writer=csv.writer(stream);writer.writerow(names)
            def safe(v):
                # Prevent spreadsheet formula injection from external market titles.
                if isinstance(v,str) and v[:1] in {'=','+','-','@','\t','\r'}:return "'"+v
                return v
            for row in cur:writer.writerow([safe(x) for x in row])
        return stream.getvalue()
