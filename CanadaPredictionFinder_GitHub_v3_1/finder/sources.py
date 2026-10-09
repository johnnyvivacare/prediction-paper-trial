"""Public, keyless research source. No Canadian account entitlement is inferred."""
from __future__ import annotations
import json
import time
from dataclasses import asdict
from .core import Book, Fee, Market, money, utcnow
from .network import PublicClient, SourceError


class KalshiPublic:
    def __init__(self,store,config:dict,client=None):
        self.store,self.c=store,config
        self.client=client or PublicClient(config['request_timeout_seconds'],config['requests_per_second'])
        self.catalog={}
        self.series={}
        self.fees={}
        self.last_refresh=0.0
        self.cursor=0
        self.health={'state':'STARTING','note':'Public research data; Canadian trade access unverified','last_success':None}
        for row in store.rows("SELECT payload FROM markets"):
            try:
                m=Market(**json.loads(row['payload']))
                self.catalog[m.ticker]=m
            except (TypeError,ValueError):pass

    def _series(self,ticker:str,now:float):
        if ticker not in self.fees or not self.fees[ticker].valid(now):
            raw=self.client.get('series/'+ticker).get('series')
            if not isinstance(raw,dict):raise SourceError('Series metadata missing')
            self.series[ticker]=raw
            self.fees[ticker]=Fee(str(raw.get('fee_type','unknown')),str(raw.get('fee_multiplier','')),utcnow(),money(self.c['fee_floor_usd_per_contract']))
        return self.series[ticker],self.fees[ticker]

    def refresh_catalog(self,now:float):
        desired=list(self.c['series'])
        if self.c['discover_series']:
            try:
                data=self.client.get('series',{'include_volume':'true'})
                items=data.get('series')
                if not isinstance(items,list):raise SourceError('Series list schema changed')
                categories={s.casefold() for s in self.c['categories']}
                def supported(s):
                    cats=[s.get('category','')]+(s.get('categories') or [])
                    return any(str(x).casefold() in categories for x in cats)
                items=[s for s in items if isinstance(s,dict) and supported(s)]
                def vol(s):
                    try:return float(s.get('volume_fp') or 0)
                    except (ValueError,TypeError):return 0
                for s in sorted(items,key=vol,reverse=True):
                    t=s.get('ticker')
                    if not isinstance(t,str):continue
                    self.series[t]=s
                    self.fees[t]=Fee(str(s.get('fee_type','unknown')),str(s.get('fee_multiplier','')),utcnow(),money(self.c['fee_floor_usd_per_contract']))
                    if t not in desired:desired.append(t)
            except SourceError as exc:
                self.store.event('CATALOG_NOTICE',str(exc))
                # Source-denied/backoff is respected by PublicClient; no alternate host/proxy.
        catalog={};errors=[];truncated=False
        for t in desired[:self.c['max_series']]:
            try:
                s,_=self._series(t,utcnow())
                category=str(s.get('category') or 'Unknown')
                cursor=''
                for page in range(3):
                    args={'status':'open','series_ticker':t,'limit':200,'mve_filter':'exclude'}
                    if cursor:args['cursor']=cursor
                    response=self.client.get('markets',args)
                    rows=response.get('markets')
                    if not isinstance(rows,list):raise SourceError('Markets response schema changed')
                    for raw in rows:
                        try:
                            m=Market.parse(raw,category,t)
                            if m.active(utcnow()):catalog[m.ticker]=m
                        except (ValueError,TypeError,KeyError):continue
                    cursor=response.get('cursor') or ''
                    if not cursor:break
                if cursor:truncated=True
            except SourceError as exc:
                errors.append(t+': '+str(exc))
                if '404' not in str(exc):break
        if catalog:
            ranked=sorted(catalog.values(),key=lambda m:m.volume,reverse=True)
            if len(ranked)>self.c['max_catalog_markets']:truncated=True
            self.catalog={m.ticker:m for m in ranked[:self.c['max_catalog_markets']]}
            for m in self.catalog.values():self.store.save_market(m,utcnow())
        self.last_refresh=now
        self.health.update({'catalog_markets':len(self.catalog),'catalog_is_limited':True,
            'truncated':truncated,'catalog_errors':errors[:5],
            'coverage':'Selected categories/series only; not the whole exchange'})
        if not self.catalog:
            raise SourceError('No markets available. '+('; '.join(errors[:2]) or 'Chosen series may have no open events.'))

    def batch(self,now:float) -> list[tuple[Market,Book|None,Fee|None]]:
        if now-self.last_refresh>=self.c['catalog_refresh_seconds'] or not self.catalog:
            self.refresh_catalog(now)
        held=self.store.rows("SELECT ticker FROM positions WHERE status='open' ORDER BY entry")
        held_tickers=[r['ticker'] for r in held]
        forecasts=[r['ticker'] for r in self.store.rows("SELECT DISTINCT ticker FROM forecasts WHERE expires>? AND created<=?",(now,now))]
        ranked=[m.ticker for m in sorted(self.catalog.values(),key=lambda m:m.volume,reverse=True) if m.active(now)]
        count=self.c['books_per_scan']
        # Most watch slots remain stable so the one-hour strategy can warm up.
        pinned=ranked[:max(1,count-4)]
        rest=ranked[max(1,count-4):]
        rotated=[]
        if rest:
            rotated=(rest+rest)[self.cursor%len(rest):self.cursor%len(rest)+4]
            self.cursor=(self.cursor+4)%len(rest)
        chosen=list(dict.fromkeys(held_tickers+forecasts+pinned+rotated))[:max(count,len(held_tickers))]
        result=[];failures=[]
        # Deadline avoids overlapping cycles. A slow provider leads to visible gaps, not bursts.
        deadline=time.monotonic()+max(10,self.c['scan_seconds']-5)
        for ticker in chosen:
            if time.monotonic()>=deadline:
                failures.append('Cycle deadline reached; remaining contracts deferred')
                break
            try:
                info=self.client.get('markets/'+ticker).get('market')
                if not isinstance(info,dict):raise SourceError('Market details missing')
                old=self.catalog.get(ticker)
                series=old.series if old else str(info.get('event_ticker','')).split('-')[0]
                s,fee=self._series(series,utcnow())
                m=Market.parse(info,str(s.get('category') or 'Unknown'),series)
                if m.ticker!=ticker:raise SourceError('Requested/returned contract identity mismatch')
                self.catalog[ticker]=m
                self.store.save_market(m,utcnow())
                if not m.active(utcnow()):
                    result.append((m,None,None));continue
                raw=self.client.get('markets/'+ticker+'/orderbook',{'depth':30})
                book=Book.parse(ticker,raw,utcnow())
                result.append((m,book,fee))
            except (SourceError,ValueError,TypeError,KeyError) as exc:
                failures.append(ticker+': '+str(exc))
                if isinstance(exc,SourceError) and '404' not in str(exc):break
        self.health.update({'state':'DEGRADED' if failures else ('OK' if result else 'NO_DATA'),
            'last_success':utcnow() if result else self.health.get('last_success'),
            'books_this_cycle':sum(b is not None for _,b,_ in result),'errors':failures[:5],
            'note':'Research quotes only. No Canadian account or matching broker quotes connected.'})
        if failures:self.store.event('SOURCE_NOTICE','; '.join(failures[:3]))
        return result
