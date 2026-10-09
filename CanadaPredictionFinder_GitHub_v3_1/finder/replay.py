"""Chronological replay of retained snapshots, never a historical market-data downloader."""
from __future__ import annotations
import json
import sqlite3
from dataclasses import fields
from itertools import groupby
from pathlib import Path
from .analytics import performance,ledger_audit
from .config import validate
from .core import Market,Book,Fee
from .engine import Engine
from .store import Store


def replay(source:Path,destination:Path) -> dict:
    source=Path(source).resolve();destination=Path(destination).resolve()
    if not source.is_file():raise ValueError('Source ledger does not exist')
    if source==destination or destination.exists():raise ValueError('Replay requires a new, separate destination database')
    connection=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)
    connection.row_factory=sqlite3.Row
    try:
        meta={r['key']:r['value'] for r in connection.execute('SELECT * FROM meta')}
        if meta.get('schema')!='3':raise ValueError('Only v3 recorded snapshots can be replayed')
        config=validate(json.loads(meta.get('config_original','{}')))
        store=Store(destination,int(meta['initial']),'replay')
        store.setmeta('config_original',json.dumps(config,sort_keys=True))
        store.setmeta('replay_source_mode',meta.get('mode','unknown'))
        forecasts=[dict(r) for r in connection.execute('SELECT * FROM forecasts ORDER BY created')]
        with store.connect() as db:
            for f in forecasts:
                cols=list(f)
                db.execute('INSERT INTO forecasts('+','.join(cols)+') VALUES ('+','.join('?' for _ in cols)+')',tuple(f.values()))
        # Copying a forecast into storage does not make it available early: every strategy
        # query enforces created <= current replay time and expires > current time.
        stream=[]
        for row in connection.execute('SELECT * FROM snapshots ORDER BY ts,id'):
            stream.append((row['ts'],'snapshot',dict(row)))
        for row in connection.execute('SELECT * FROM resolutions ORDER BY ts,id'):
            stream.append((row['ts'],'resolution',dict(row)))
    finally:connection.close()
    stream.sort(key=lambda x:(x[0],0 if x[1]=='resolution' else 1))
    engine=Engine(store,config);last=None
    for ts,group in groupby(stream,key=lambda x:x[0]):
        items=list(group);books=[]
        for _,kind,row in items:
            if kind=='resolution':
                m=Market(**json.loads(row['payload']));store.save_market(m,ts);engine.settle(m,ts)
            else:
                m=Market(**json.loads(row['market_json']))
                raw=json.loads(row['book_json'])
                raw['yes_bids']=tuple(tuple(x) for x in raw['yes_bids'])
                raw['no_bids']=tuple(tuple(x) for x in raw['no_bids'])
                b=Book(**raw);f=Fee(**json.loads(row['fee_json']))
                books.append((m,b,f));engine.mark(m,b,f,ts)
        for m,b,f in books:engine.observe(m,b,f,ts)
        store.record_equity(ts,config['max_quote_age_seconds']);last=ts
    store.setmeta('last_cycle',str(last or 0))
    report={'mode':'replay','source_mode':meta.get('mode'),'observations':sum(x[1]=='snapshot' for x in stream),
        'resolutions':sum(x[1]=='resolution' for x in stream),'audit':ledger_audit(store),
        'performance':performance(store,last,config['max_quote_age_seconds']),
        'limitations':['Only retained local observations, not complete exchange history.',
                      'User pauses, manual close requests and intra-cycle timing are not reconstructed.',
                      'Replays and parameter tuning are not independent forward validation.',
                      'A source demo remains fabricated even when replayed.']}
    destination.with_suffix('.report.json').write_text(json.dumps(report,indent=2))
    return report
