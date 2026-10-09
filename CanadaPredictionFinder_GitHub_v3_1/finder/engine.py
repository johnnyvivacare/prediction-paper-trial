"""Conservative paper execution, exits, source settlement and risk circuit breakers."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
from .config import fingerprint
from .core import USD, Book, Fee, Market, money, walk
from .strategies import Candidate, forecast_signal, reversion_signal


class Engine:
    def __init__(self,store,config:dict):
        self.store,self.c=store,config
        self.config_hash=fingerprint(config)
        self.zone=ZoneInfo(config['timezone'])

    def day(self,now:float) -> str:
        return datetime.fromtimestamp(now,self.zone).date().isoformat()

    def risk_state(self,now:float) -> tuple[dict,str]:
        p=self.store.portfolio(now,self.c['max_quote_age_seconds'])
        reason=""
        if self.store.meta('paused')=='true':reason="USER_PAUSED"
        if self.store.meta('drawdown_halt')=='true':reason="DRAWDOWN_CIRCUIT_BREAKER"
        locked=self.store.meta('config_hash')
        if locked and locked!=self.config_hash:reason="CONFIG_CHANGED: start a separate experiment directory"
        if p['equity_units'] is None:return p,reason or "UNPRICEABLE_OPEN_POSITION"
        eq=p['equity_units'];initial=p['initial_units']
        day=self.day(now)
        with self.store.connect() as db:
            high=int(db.execute("SELECT value FROM meta WHERE key='high_water'").fetchone()[0])
            high=max(high,eq)
            db.execute("UPDATE meta SET value=? WHERE key='high_water'",(str(high),))
            if high>0 and (high-eq)/high>=self.c['max_drawdown_fraction']:
                db.execute("UPDATE meta SET value='true' WHERE key='drawdown_halt'")
                reason="DRAWDOWN_CIRCUIT_BREAKER"
            # After a restart, use the last equity available before today's first
            # scan as a conservative start-of-day reference, rather than resetting a loss.
            prior=db.execute("SELECT value FROM equity WHERE value IS NOT NULL AND ts<? ORDER BY ts DESC LIMIT 1",(now,)).fetchone()
            start=max(eq,prior[0]) if prior else eq
            db.execute("INSERT OR IGNORE INTO risk_days VALUES (?,?,0)",(day,start))
            r=db.execute("SELECT * FROM risk_days WHERE day=?",(day,)).fetchone()
            if r['opening_equity']>0 and (r['opening_equity']-eq)/r['opening_equity']>=self.c['max_daily_loss_fraction']:
                db.execute("UPDATE risk_days SET halted=1 WHERE day=?",(day,))
                reason=reason or "DAILY_LOSS_LIMIT"
            if r['halted']:reason=reason or "DAILY_LOSS_LIMIT"
        return p,reason

    def budget(self,m:Market,now:float) -> tuple[int,str]:
        p,reason=self.risk_state(now)
        if reason:return 0,reason
        if self.c['require_canada_verification']:
            return 0,"CANADIAN_EXECUTION_NOT_VERIFIED: research feed is not a broker quote"
        base=min(p['initial_units'],p['equity_units'])
        rows=self.store.rows("SELECT * FROM positions WHERE status='open'")
        # Group different strikes of the same event; do not treat them as independent bets.
        risk=lambda r:max(0,r['cost']-r['proceeds'])
        event=sum(risk(r) for r in rows if r['event']==m.event)
        category=sum(risk(r) for r in rows if r['category']==m.category)
        total=sum(risk(r) for r in rows)
        if self.store.rows("SELECT id FROM positions WHERE ticker=?",(m.ticker,)):
            return 0,"DUPLICATE: at most one lifetime entry per contract per experiment"
        entries=self.store.rows("SELECT entry FROM positions")
        count=sum(self.day(r['entry'])==self.day(now) for r in entries)
        if count>=self.c['max_entries_per_day']:return 0,"DAILY_ENTRY_CAP"
        amount=min(p['cash_units'],int(base*self.c['max_event_risk_fraction'])-event,
                   int(base*self.c['max_category_risk_fraction'])-category,
                   int(base*self.c['max_total_risk_fraction'])-total)
        return max(0,amount),"RISK_BUDGET" if amount>0 else "EXPOSURE_LIMIT"

    def mark(self,m:Market,b:Book,f:Fee,now:float):
        if m.ticker!=b.ticker:return
        rows=self.store.rows("SELECT * FROM positions WHERE ticker=? AND status='open'",(m.ticker,))
        if not rows:return
        if not 0<=now-b.fetched_at<=self.c['max_quote_age_seconds'] or not f.valid(now):return
        p=rows[0]
        if p['rules_hash']!=m.rules_hash:return
        fill=walk(b,p['side'],p['remaining'],f,False,money(self.c['slippage_usd_per_contract']),self.c['depth_participation'])
        with self.store.connect() as db:
            db.execute("INSERT OR REPLACE INTO marks VALUES (?,?,?,?,?)",
                (m.ticker,b.fetched_at,fill.qty,fill.cash,p['remaining']))

    def exit_position(self,m:Market,b:Book,f:Fee,now:float,force:bool=False) -> bool:
        if m.ticker!=b.ticker:return False
        rows=self.store.rows("SELECT * FROM positions WHERE ticker=? AND status='open'",(m.ticker,))
        if not rows or not m.active(now) or not f.valid(now) or not 0<=now-b.fetched_at<=self.c['max_quote_age_seconds']:
            return False
        p=rows[0]
        if p['rules_hash']!=m.rules_hash:
            self.store.signal(now,m.ticker,p['strategy'],p['side'],None,'RULES_CHANGED','Settlement terms changed; hold for manual investigation')
            return False
        # Never enter and exit on the same observation.
        if now-p['entry']<30:return False
        fill=walk(b,p['side'],p['remaining'],f,False,money(self.c['slippage_usd_per_contract']),self.c['depth_participation'])
        if fill.qty==0:return False
        net_per=fill.cash/fill.qty
        reason=""
        if force:reason="USER_PAPER_CLOSE"
        elif net_per<=p['stop']:reason="STOP_LOSS"
        elif p['target'] is not None and net_per>=p['target']:reason="TARGET"
        elif now-p['entry']>=self.c['max_holding_hours']*3600:reason="TIME_LIMIT"
        elif m.close_at-now<self.c['min_time_to_close_seconds']:reason="NEAR_CLOSE"
        if not reason:return False
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            current=db.execute("SELECT remaining,status FROM positions WHERE id=?",(p['id'],)).fetchone()
            if current['status']!='open' or current['remaining']!=p['remaining']:return False
            remaining=p['remaining']-fill.qty
            db.execute("UPDATE positions SET remaining=?,proceeds=proceeds+?,fees=fees+?,status=?,exit=? WHERE id=?",
                (remaining,fill.cash,fill.fee,'closed' if not remaining else 'open',now if not remaining else None,p['id']))
            db.execute("UPDATE cash SET units=units+? WHERE id=1",(fill.cash,))
            db.execute("INSERT INTO fills(position_id,ts,action,qty,price,cash,fee,reason) VALUES (?,?,?,?,?,?,?,?)",
                (p['id'],now,'SELL',fill.qty,fill.average,fill.cash,fill.fee,reason))
            db.execute("DELETE FROM marks WHERE ticker=?",(m.ticker,))
            db.execute("INSERT INTO events(ts,kind,note) VALUES (?,?,?)",(now,'EXIT',f'{m.ticker}: {fill.qty} {p["side"]}; {reason}; paper only'))
        return True

    def settle(self,m:Market,now:float) -> bool:
        # Closed/expired/determined is NOT sufficient. Wait for source finalized/settled.
        if m.status not in {'settled','finalized'} or m.result not in {'YES','NO'} or m.provisional or now<m.close_at:
            return False
        from dataclasses import asdict
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute('INSERT OR IGNORE INTO resolutions(ts,ticker,payload) VALUES (?,?,?)',(now,m.ticker,json.dumps(asdict(m))))
            p=db.execute("SELECT * FROM positions WHERE ticker=? AND status='open'",(m.ticker,)).fetchone()
            if not p:return False
            if p['rules_hash']!=m.rules_hash:
                db.execute("INSERT INTO events(ts,kind,note) VALUES (?,?,?)",(now,'SETTLEMENT_REVIEW',m.ticker+': rules hash changed; no automatic credit'))
                return False
            cash=p['remaining']*USD if p['side']==m.result else 0
            db.execute("UPDATE cash SET units=units+? WHERE id=1",(cash,))
            db.execute("UPDATE positions SET remaining=0,proceeds=proceeds+?,status='settled',outcome=?,exit=? WHERE id=?",(cash,m.result,now,p['id']))
            db.execute("INSERT INTO fills(position_id,ts,action,qty,price,cash,fee,reason) VALUES (?,?,?,?,?,?,?,?)",
                (p['id'],now,'SETTLE',p['remaining'],USD if cash else 0,cash,0,'Source confirmed '+m.result))
            db.execute("DELETE FROM marks WHERE ticker=?",(m.ticker,))
            db.execute("INSERT INTO events(ts,kind,note) VALUES (?,?,?)",(now,'SETTLE',m.ticker+': source settled '+m.result))
        return True

    def observe(self,m:Market,b:Book,f:Fee,now:float,allow_entries:bool=True):
        if m.ticker!=b.ticker:raise ValueError("Market/orderbook identity mismatch")
        self.store.save_market(m,now)
        if not 0<=now-b.fetched_at<=self.c['max_quote_age_seconds']:
            self.store.signal(now,m.ticker,'safety',None,None,'STALE_BOOK','No paper fill from stale/future data')
            return
        self.store.snapshot(m,b,f,now)
        self.mark(m,b,f,now)
        force=self.store.meta('close:'+m.ticker)=='true'
        if self.exit_position(m,b,f,now,force):
            self.mark(m,b,f,now)
            if not self.store.rows("SELECT id FROM positions WHERE ticker=? AND status='open'",(m.ticker,)):
                self.store.setmeta('close:'+m.ticker,'false')
        if not allow_entries:return
        if not m.active(now) or m.close_at-now<self.c['min_time_to_close_seconds']:
            self.store.signal(now,m.ticker,'safety',None,None,'CLOSED_OR_NEAR_CLOSE','No new entry')
            return
        if not f.valid(now):
            self.store.signal(now,m.ticker,'safety',None,None,'FEE_UNKNOWN','Missing, unsupported or stale fee metadata; skip')
            return
        if m.volume<self.c['min_volume']:return
        candidates=[];note='NO_FORECAST'
        if self.c['enable_value_strategy']:candidates+=forecast_signal(self.store,m,now)
        if self.c['enable_reversion_strategy']:
            signals,note=reversion_signal(self.store,m,b,self.c,now);candidates+=signals
        if not candidates:
            self.store.setmeta('intent:'+m.ticker,'')
            self.store.signal(now,m.ticker,'experimental_reversion',None,None,'WAIT',note)
            return
        budget,why=self.budget(m,now)
        if budget<=0:
            self.store.signal(now,m.ticker,'risk',None,None,why,'No new paper position')
            return
        viable=[]
        slip=money(self.c['slippage_usd_per_contract'])
        min_edge=money(self.c['min_edge_usd'])
        for candidate in candidates:
            spread=b.spread(candidate.side)
            if spread is None or not 0<=spread<=money(self.c['max_spread_usd']):continue
            asks=b.asks(candidate.side)
            if not asks:continue
            ask=asks[0][0]
            if not money(self.c['min_entry_price_usd'])<=ask<=money(self.c['max_entry_price_usd']):continue
            max_qty=min(200,int(budget/max(1,ask+slip)))
            for qty in range(max_qty,0,-1):
                fill=walk(b,candidate.side,qty,f,True,slip,self.c['depth_participation'])
                if fill.qty!=qty or fill.cash>budget:continue
                # For value, target is conservative outcome probability ($1 payoff), not an exit.
                # Reversion models a FUTURE bid, so subtract both estimated exit fees and slippage.
                exit_reserve=0
                if candidate.strategy=='experimental_reversion':
                    exit_reserve=f.charge(qty,candidate.fair_units)+qty*slip
                edge=(qty*candidate.fair_units-fill.cash-exit_reserve)/qty
                if edge>=min_edge:
                    viable.append((edge,candidate,fill));break
        if not viable:
            self.store.setmeta('intent:'+m.ticker,'')
            self.store.signal(now,m.ticker,'filters',None,None,'COST_OR_LIQUIDITY','No size clears spread, depth, fee and slippage requirements')
            return
        edge,candidate,fill=max(viable,key=lambda x:x[0])
        intent_key='intent:'+m.ticker
        old=json.loads(self.store.meta(intent_key) or '{}')
        valid=(old.get('side')==candidate.side and old.get('strategy')==candidate.strategy
               and old.get('rules_hash')==m.rules_hash
               and max(50,self.c['scan_seconds']-10)<=now-old.get('ts',0)<=self.c['scan_seconds']*3
               and abs(old.get('fair',0)-candidate.fair_units)<=200)
        if not valid:
            self.store.setmeta(intent_key,json.dumps({'side':candidate.side,'strategy':candidate.strategy,
                'rules_hash':m.rules_hash,'ts':now,'fair':candidate.fair_units}))
            self.store.signal(now,m.ticker,candidate.strategy,candidate.side,edge/USD,'CONFIRMING','Must remain valid at next scan; no same-tick fill')
            return
        with self.store.connect() as db:
            db.execute("BEGIN IMMEDIATE")
            # Single scanner process; transactional duplicate/cash guard also protects a restart.
            if db.execute("SELECT id FROM positions WHERE ticker=?",(m.ticker,)).fetchone():return
            cash=db.execute("SELECT units FROM cash WHERE id=1").fetchone()[0]
            if fill.cash>cash:return
            target=None
            if candidate.strategy=='experimental_reversion':
                target=candidate.fair_units-slip-f.charge(fill.qty,candidate.fair_units)//fill.qty
            stop=int((fill.cash/fill.qty)*(1-self.c['stop_loss_fraction']))
            cur=db.execute('''INSERT INTO positions(ticker,event,category,title,strategy,side,qty,remaining,cost,fees,
                              entry,target,stop,rules_hash,forecast_id,entry_market_p) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
                (m.ticker,m.event,m.category,m.title,candidate.strategy,candidate.side,fill.qty,fill.qty,
                 fill.cash,fill.fee,now,target,stop,m.rules_hash,candidate.forecast_id,b.mid()))
            pid=cur.lastrowid
            db.execute("UPDATE cash SET units=units-? WHERE id=1",(fill.cash,))
            db.execute("INSERT INTO fills(position_id,ts,action,qty,price,cash,fee,reason) VALUES (?,?,?,?,?,?,?,?)",
                (pid,now,'BUY',fill.qty,fill.average,fill.cash,fill.fee,candidate.note))
            first=db.execute("INSERT OR IGNORE INTO meta VALUES ('config_hash',?)",(self.config_hash,)).rowcount
            if first:
                db.execute("INSERT OR REPLACE INTO meta VALUES ('config_original',?)",(json.dumps(self.c,sort_keys=True),))
            db.execute("INSERT INTO events(ts,kind,note) VALUES (?,?,?)",(now,'OPEN',f'{m.ticker}: {fill.qty} {candidate.side}; {candidate.strategy}; paper only'))
        self.store.setmeta(intent_key,'')
        self.store.signal(now,m.ticker,candidate.strategy,candidate.side,edge/USD,'PAPER_OPENED',candidate.note)
        self.mark(m,b,f,now)
