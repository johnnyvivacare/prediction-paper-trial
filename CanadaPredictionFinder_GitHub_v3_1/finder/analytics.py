from __future__ import annotations
import math
import random
import statistics
from collections import defaultdict
from .core import USD,dollars,utcnow


def ledger_audit(store) -> dict:
    initial=int(store.meta('initial'))
    with store.connect() as db:
        cash=db.execute('SELECT units FROM cash WHERE id=1').fetchone()[0]
        buys=db.execute("SELECT COALESCE(SUM(cash),0) FROM fills WHERE action='BUY'").fetchone()[0]
        credits=db.execute("SELECT COALESCE(SUM(cash),0) FROM fills WHERE action IN ('SELL','SETTLE')").fetchone()[0]
        bad=[]
        for p in db.execute('SELECT * FROM positions'):
            fs=db.execute('SELECT * FROM fills WHERE position_id=?',(p['id'],)).fetchall()
            q=sum(f['qty'] if f['action']=='BUY' else -f['qty'] for f in fs)
            cost=sum(f['cash'] for f in fs if f['action']=='BUY')
            proceeds=sum(f['cash'] for f in fs if f['action']!='BUY')
            fees=sum(f['fee'] for f in fs)
            if q!=p['remaining'] or cost!=p['cost'] or proceeds!=p['proceeds'] or fees!=p['fees']:
                bad.append(p['ticker'])
        integrity=db.execute('PRAGMA quick_check').fetchone()[0]
    return {'ok':cash==initial-buys+credits and not bad and integrity=='ok',
        'cash_usd':dollars(cash),'reconciled_cash_usd':dollars(initial-buys+credits),
        'mismatched_positions':bad,'sqlite':integrity}


def bootstrap_event_mean(profits:list[float],samples:int=2000) -> list[float]|None:
    if len(profits)<10:return None
    rng=random.Random(31007)
    n=len(profits)
    means=sorted(sum(rng.choices(profits,k=n))/n for _ in range(samples))
    return [round(means[int(.025*samples)],4),round(means[int(.975*samples)],4)]


def performance(store,now:float|None=None,max_age:float=90) -> dict:
    now=utcnow() if now is None else now
    p=store.portfolio(now,max_age)
    closed=store.rows("SELECT * FROM positions WHERE status!='open'")
    by_event=defaultdict(float);by_strategy=defaultdict(lambda:{'closed':0,'pnl_usd':0,'wins':0})
    stress=0;value_scores=[];market_scores=[]
    for r in closed:
        pnl=(r['proceeds']-r['cost'])/USD
        by_event[r['event']]+=pnl
        item=by_strategy[r['strategy']];item['closed']+=1;item['pnl_usd']+=pnl;item['wins']+=pnl>0
        # Additional 2c/contract EACH entry and pre-settlement exit, beyond recorded costs.
        stress+=pnl-0.02*r['qty']
        sells=store.rows("SELECT COALESCE(SUM(qty),0) AS n FROM fills WHERE position_id=? AND action='SELL'",(r['id'],))[0]['n']
        stress-=0.02*sells
        if r['outcome'] in {'YES','NO'} and r['forecast_id']:
            f=store.rows('SELECT p FROM forecasts WHERE id=?',(r['forecast_id'],))
            if f:
                y=int(r['outcome']=='YES');value_scores.append((f[0]['p']-y)**2)
                if r['entry_market_p'] is not None:market_scores.append((r['entry_market_p']-y)**2)
    for x in by_strategy.values():x['pnl_usd']=round(x['pnl_usd'],4)
    eq=store.rows('SELECT ts,value FROM equity ORDER BY ts')
    high=p['initial_units'];drawdown=0;missing=sum(r['value'] is None for r in eq)
    for r in eq:
        if r['value'] is None:continue
        high=max(high,r['value'])
        drawdown=max(drawdown,(high-r['value'])/high if high else 0)
    span=(eq[-1]['ts']-eq[0]['ts'])/86400 if len(eq)>1 else 0
    ci=bootstrap_event_mean(list(by_event.values()))
    gates={
        '100_distinct_closed_events':len(by_event)>=100,
        '30_days_observed':span>=30,
        'positive_closed_pnl_after_costs':sum(by_event.values())>0,
        'positive_event_bootstrap_lower_bound':ci is not None and ci[0]>0,
        'positive_stress_pnl':stress>0,
        'no_open_positions':p['open_positions']==0,
        'complete_valuation_history':missing==0,
        'ledger_reconciles':ledger_audit(store)['ok'],
        'not_demo_or_replay':store.meta('mode')=='paper',
    }
    return {
        'distinct_closed_events':len(by_event),'closed_positions':len(closed),'observed_days':round(span,2),
        'max_observed_drawdown_fraction':round(drawdown,6),'incomplete_equity_points':missing,
        'event_mean_pnl_95pct_bootstrap_usd':ci,'stress_closed_pnl_usd':round(stress,4),
        'by_strategy':dict(by_strategy),'brier_value_forecasts':statistics.mean(value_scores) if value_scores else None,
        'brier_market_at_entry':statistics.mean(market_scores) if market_scores else None,
        'brier_sample':len(value_scores),'cash_benchmark_return':0,
        'research_gates':gates,'research_gates_passed':sum(gates.values()),
        'live_trading_ready':False,
        'hard_blockers':['No live execution adapter exists in this release.','Canadian account/contract permissions and broker fills are unverified.',
                         'Paper strategies, including reversion, have no demonstrated profitable edge.'],
        'statistics_warning':'Event bootstrap assumes events are sufficiently independent. Correlated releases, selection and strategy tuning can invalidate it. Passing these screens is not proof of future profit.',
    }
