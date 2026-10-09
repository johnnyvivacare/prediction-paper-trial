"""Explicit, falsifiable strategies. None is claimed to have a profitable edge."""
from __future__ import annotations
import math
import statistics
from dataclasses import dataclass
from .core import USD, Book, Market, money


@dataclass(frozen=True)
class Candidate:
    strategy: str
    side: str
    fair_units: int
    note: str
    forecast_id: int | None = None
    p: float | None = None


def add_forecast(store,market:Market,p:float,lo:float,hi:float,expires:float,
                 source:str,method:str,now:float) -> int:
    vals=(p,lo,hi,expires,now)
    if any(not math.isfinite(float(v)) for v in vals) or not 0.01<=lo<=p<=hi<=0.99:
        raise ValueError("Require 1% <= lower <= probability <= upper <= 99%")
    if hi-lo+1e-12<0.04:
        raise ValueError("Use an uncertainty range at least 4 percentage points wide")
    if not now<expires<=min(market.close_at,now+7*86400):
        raise ValueError("Forecast expiry must be before close and within seven days")
    if not market.active(now):
        raise ValueError("Forecast only an open, non-provisional market")
    if not isinstance(source,str) or len(source.strip())<10 or len(source)>1500:
        raise ValueError("Provide an independent source or rationale (10–1500 characters)")
    if not isinstance(method,str) or len(method.strip())<5 or len(method)>1000:
        raise ValueError("Explain the forecasting method (5–1000 characters)")
    with store.connect() as db:
        cur=db.execute("INSERT INTO forecasts(ticker,created,expires,rules_hash,p,lo,hi,method,source) VALUES (?,?,?,?,?,?,?,?,?)",
            (market.ticker,now,expires,market.rules_hash,p,lo,hi,method,source))
        return cur.lastrowid


def forecast_signal(store,market:Market,now:float) -> list[Candidate]:
    rows=store.rows("SELECT * FROM forecasts WHERE ticker=? AND created<=? ORDER BY created DESC LIMIT 1",(market.ticker,now))
    if not rows:return []
    f=rows[0]
    if f['expires']<=now or f['rules_hash']!=market.rules_hash:return []
    # Risk uses the pessimistic end of the user's interval, not the point estimate.
    return [Candidate("independent_value","YES",int(f['lo']*USD),"Conservative lower probability; "+f['method'],f['id'],f['p']),
            Candidate("independent_value","NO",int((1-f['hi'])*USD),"Conservative complement probability; "+f['method'],f['id'],f['p'])]


def reversion_signal(store,market:Market,book:Book,config:dict,now:float) -> tuple[list[Candidate],str]:
    """Experimental price reversion, NOT an independent event probability model.

    Requires a full prior window and at least 55 s between samples. A sharp move
    may be genuine news, so this strategy can lose; it must stay in paper mode.
    """
    n=config['reversion_window']
    hist=store.history(market.ticker,now,n*3)
    picked=[]
    for row in reversed(hist):
        if not picked or picked[-1]['ts']-row['ts']>=55:
            picked.append(row)
        if len(picked)==n:break
    picked=picked[::-1]
    if len(picked)<n:return [],f"WARMUP {len(picked)}/{n} independent time samples"
    if now-picked[-1]['ts']>config['scan_seconds']*3:
        return [],"HISTORY_GAP: restart warm-up after stale observations"
    if picked[-1]['ts']-picked[0]['ts']>(n-1)*config['scan_seconds']*2:
        return [],"HISTORY_GAP: samples too sparse"
    mids=[r['mid'] for r in picked]
    current=book.mid()
    if current is None:return [],"NO_TWO_SIDED_BOOK"
    mean=statistics.mean(mids);sd=max(statistics.pstdev(mids),0.01)
    z=(current-mean)/sd
    if abs(z)<config['reversion_zscore']:
        return [],f"NO_SIGNAL: price deviation z={z:.2f}"
    side='YES' if z<0 else 'NO'
    fair=(mean if side=='YES' else 1-mean)-config['reversion_haircut']
    if not 0.05<fair<0.95:return [],"EXTREME_TARGET"
    return [Candidate("experimental_reversion",side,int(fair*USD),
             f"Price target, not outcome probability; {n} prior samples, z={z:.2f}")],"CANDIDATE"


def empirical_probability(values:list[float],threshold:float,greater:bool=True) -> tuple[float,float,float]:
    """Offline baseline for explicitly matched external forecast ensembles.

    Input must be independent scenario draws of the EXACT contract variable, not
    past prices mistaken for a future distribution. Wilson interval only captures
    finite sample uncertainty, not model error. Additional model haircut is needed.
    """
    if len(values)<30 or any(not math.isfinite(v) for v in values) or not math.isfinite(threshold):
        raise ValueError("Need at least 30 finite independent scenario values")
    wins=sum(v>threshold if greater else v<threshold for v in values)
    n=len(values);p=wins/n;z=1.96;den=1+z*z/n
    center=(p+z*z/(2*n))/den
    radius=z*math.sqrt(p*(1-p)/n+z*z/(4*n*n))/den
    return p,max(0,center-radius),min(1,center+radius)
