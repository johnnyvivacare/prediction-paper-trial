"""Entirely fabricated scenarios to exercise the engine, not a profitable backtest."""
from dataclasses import replace
import math
from .core import Market,Book,Fee,USD,digest,utcnow
from .strategies import add_forecast


def sample_market(ticker='DEMO-YES',event='DEMO-EVENT',now=None):
    now=utcnow() if now is None else now
    return Market(ticker,event,'DEMO','FABRICATED example: will the test event resolve YES?',
        'Economics',now+7200,'active',digest({'ticker':ticker,'terms':'fabricated binary test v1'}),
        'Fabricated fixture only. YES pays $1 and NO pays $0 if the test event resolves YES; otherwise reversed.',
        10000,3900,4100,source='fabricated_demo')


def sample_book(m,now,mid=.40,size=1000):
    p=int(round(mid*USD))
    return Book(m.ticker,now,((p-100,size),),((USD-p-100,size),))


def populate(runtime):
    store=runtime.store
    if store.meta('mode')!='demo':raise ValueError('Refuse to put fabricated data in a paper ledger')
    if store.meta('demo_populated')=='true':return
    end=utcnow()-1
    start=end-15000
    e=runtime.engine
    store.record_equity(start)
    # Two deliberate value tests: one win and one loss. Both go through confirmation,
    # exact-money accounting and source-style settlement, not preloaded profit rows.
    for i,outcome in enumerate(('YES','NO')):
        t=start+i*6000
        m=sample_market('DEMO-VALUE-'+str(i),'DEMO-EVENT-'+str(i),t)
        m=replace(m,close_at=t+4000)
        store.save_market(m,t)
        add_forecast(store,m,.72,.65,.80,t+3800,'Fabricated scenario, not an external forecast','Software test fixture only',t)
        for dt in (0,60):
            ts=t+dt
            e.observe(m,sample_book(m,ts),Fee('quadratic','1',ts),ts)
            store.record_equity(ts)
        final=replace(m,status='finalized',result=outcome)
        e.settle(final,t+4001);store.save_market(final,t+4001)
        store.record_equity(t+4001)
    # Show a full reversion warm-up and sharp fabricated deviation on a fresh day
    # boundary only when naturally present; risk gates remain active, never overridden.
    m=sample_market('DEMO-REVERSION','DEMO-MOVE',end)
    store.save_market(m,end)
    for i in range(60):
        ts=end-(62-i)*60
        mid=.62+.004*math.sin(i)
        store.snapshot(m,sample_book(m,ts,mid),Fee('quadratic','1',ts),ts)
    # Keep the illustrated reversion event as a candidate, not a pre-filled profit claim.
    ts=end-60
    e.observe(m,sample_book(m,ts,.40),Fee('quadratic','1',ts),ts)
    store.record_equity(end)
    store.setmeta('demo_populated','true')
    store.setmeta('last_cycle',str(end))
    store.setmeta('paused','true')
    store.event('DEMO_ONLY','All prices, forecasts and outcomes in this ledger are fabricated. Not evidence of profit.',end)
    runtime.last_cycle=end
