"""Allowlisted, read-only project-test report. No tickers, forecasts or trade log."""
from __future__ import annotations
from datetime import datetime, timezone
import html
import json
import math
from pathlib import Path


def usd(units):
    return 'Unavailable' if units is None else f'US${units / 10000:,.2f}'


def stamp(ts):
    return datetime.fromtimestamp(ts, timezone.utc).strftime('%Y-%m-%d %H:%M:%S UTC') if ts else 'Not observed yet'


def public_snapshot(runtime, profile: str, until: float, now: float) -> dict:
    state = runtime.state()
    p = state['portfolio']; perf = state['performance']
    # Explicit allowlists; NEVER return Runtime.state() directly to a public artifact.
    return {
        'version': '3.1-github', 'mode': 'paper-research-only', 'generated_at': now,
        'last_cycle': state['last_cycle'], 'last_feed_success': state['health'].get('last_success'),
        'profile': profile, 'trial_expires_at': until,
        'feed_state': state['health'].get('state', 'UNKNOWN'),
        'books_this_cycle': state['health'].get('books_this_cycle', 0),
        'paused': bool(state['paused']), 'audit_ok': bool(state['audit']['ok']),
        'portfolio': {k: p[k] for k in ['initial_units', 'cash_units', 'equity_units', 'total_pnl_units',
                                      'realized_units', 'unrealized_units', 'closed_positions',
                                      'open_positions', 'win_rate', 'unpriceable_positions']},
        'performance': {k: perf[k] for k in ['distinct_closed_events', 'observed_days',
                                           'max_observed_drawdown_fraction', 'stress_closed_pnl_usd',
                                           'research_gates_passed', 'incomplete_equity_points']},
        'equity': [{'ts': r['ts'], 'value': r['value']} for r in state['equity']],
        'no_live_orders': True, 'canadian_broker_quotes_verified': False,
    }


def _plot(points):
    good = [p['value'] for p in points if p['value'] is not None and math.isfinite(p['value'])]
    if not good:
        return '<p class="muted">The equity curve appears after observations are saved.</p>'
    low, high = min(good), max(good)
    if high - low < 10000:
        low -= 5000; high += 5000
    t0, t1 = points[0]['ts'], points[-1]['ts']
    paths = []; current = []
    for point in points:
        if point['value'] is None:
            if current: paths.append(' '.join(current)); current = []
            continue
        x = 12 + (point['ts'] - t0) / max(1, t1-t0)*776
        y = 172 - (point['value'] - low) / (high-low)*156
        current.append(f'{x:.2f},{y:.2f}')
    if current: paths.append(' '.join(current))
    lines = ''.join(f'<polyline points="{p}" />' for p in paths)
    return f'<svg viewBox="0 0 800 190" role="img" aria-label="Recorded paper equity, gaps show missing valuations">{lines}</svg><div class="range">{usd(low)} to {usd(high)} · Missing valuations are not joined.</div>'


def write_report(snapshot: dict, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    p = snapshot['portfolio']; perf = snapshot['performance']; esc = html.escape
    win = 'No closed trades' if p['win_rate'] is None else f"{p['win_rate']*100:.1f}%"
    cards = [
        ('Checkpoint equity', usd(p['equity_units']), 'equity'),
        ('Total paper profit / loss', usd(p['total_pnl_units']), 'pnl'),
        ('Available paper cash', usd(p['cash_units']), 'cash'),
        ('Closed-position win rate', win, 'win'),
    ]
    card_html = ''.join(f'<article><span>{label}</span><strong id="{key}">{value}</strong></article>' for label, value, key in cards)
    status = 'EXPIRED — NO FURTHER SCANS' if snapshot['generated_at'] >= snapshot['trial_expires_at'] else snapshot['feed_state']
    facts = [
        ('Starting balance', usd(p['initial_units'])), ('Realized P&L', usd(p['realized_units'])),
        ('Open P&L at checkpoint', usd(p['unrealized_units'])),
        ('Positions', f"{p['open_positions']} open / {p['closed_positions']} closed"),
        ('Distinct closed events', str(perf['distinct_closed_events'])),
        ('Observed drawdown', f"{perf['max_observed_drawdown_fraction']*100:.2f}%"),
        ('Additional-cost stress P&L', f"US${perf['stress_closed_pnl_usd']:,.2f}"),
        ('Ledger audit', 'Reconciled' if snapshot['audit_ok'] else 'FAILED'),
        ('New paper entries', 'Paused' if snapshot['paused'] else 'Subject to risk filters'),
        ('Valuation gaps', str(perf['incomplete_equity_points'])),
    ]
    facts_html = ''.join(f'<div><dt>{esc(k)}</dt><dd>{esc(v)}</dd></div>' for k, v in facts)
    schedule = ('Five scans targeting 60 seconds apart per scheduled batch. Gaps and skipped batches are possible.'
                if snapshot['profile'] == 'minute-burst' else 'One scan per nominal five-minute scheduled batch; delays are possible.')
    body = f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; script-src 'self'; connect-src 'none'; img-src 'none'; base-uri 'none'; form-action 'none'">
<title>Prediction Finder · GitHub paper trial</title>
<style>
:root{{color-scheme:dark;font-family:system-ui,-apple-system,BlinkMacSystemFont,sans-serif;color:#e7eff8;background:#0b1220}}
*{{box-sizing:border-box}}body{{margin:0}}main{{max-width:1120px;margin:auto;padding:34px 24px 50px}}
header{{display:flex;justify-content:space-between;align-items:center;gap:18px}}h1{{font-size:clamp(25px,4vw,36px);margin:8px 0}}h2{{font-size:19px;margin:0 0 18px}}
.eyebrow{{font-size:12px;font-weight:700;letter-spacing:2px;color:#8bddcd}}p{{line-height:1.6}}
.pill{{border:1px solid #526c68;color:#a8e9db;padding:8px 12px;border-radius:99px;white-space:nowrap;font-size:12px;font-weight:700}}
.notice{{background:#292416;border:1px solid #635732;border-radius:12px;padding:14px 18px;color:#efdda7;margin:24px 0}}
.grid{{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}}article,.panel{{border:1px solid #28364b;background:#111d2f;border-radius:14px;padding:22px}}
article span{{font-size:13px;color:#a7b7cc}}article strong{{display:block;font-size:clamp(20px,2.7vw,29px);margin-top:12px;font-variant-numeric:tabular-nums}}
.panel{{margin-top:20px}}.muted,.range{{color:#a7b7cc;font-size:13px}}.status{{display:flex;gap:16px;flex-wrap:wrap;align-items:center}}
.status strong{{color:#8bddcd}}dl{{margin:0;display:grid;grid-template-columns:1fr 1fr;gap:0 28px}}dl div{{display:flex;justify-content:space-between;gap:15px;padding:12px 0;border-bottom:1px solid #28364b}}dt{{color:#a7b7cc;font-size:13px}}dd{{margin:0;text-align:right;font-size:14px}}
svg{{width:100%;height:auto;background:linear-gradient(transparent,#152a3a);border-bottom:1px solid #405169}}polyline{{stroke:#8bddcd;stroke-width:2;fill:none;vector-effect:non-scaling-stroke}}
footer{{padding:22px 0;color:#a7b7cc;font-size:12px}}#age{{font-weight:600}}@media(max-width:760px){{.grid{{grid-template-columns:1fr 1fr}}dl{{grid-template-columns:1fr}}header{{align-items:flex-start;flex-direction:column}}main{{padding:22px 16px}}article,.panel{{padding:17px}}}}@media(max-width:400px){{.grid{{grid-template-columns:1fr}}}}
</style></head><body><main data-last="{snapshot['last_cycle']}" data-generated="{snapshot['generated_at']}" data-open="{p['open_positions']}" data-expires="{snapshot['trial_expires_at']}">
<header><div><div class="eyebrow">GITHUB EDITION / 3.1</div><h1>Canada Prediction Finder</h1><div class="muted">Saved paper-test results · Not live prices or real earnings</div></div><span class="pill">PAPER ONLY · US$500 START</span></header>
<div class="notice">Experimental strategy; profitability has not been established. Public Kalshi research data is <b>not verified Canadian brokerage pricing</b>. No funded account or live-order functionality is connected.</div>
<section class="grid">{card_html}</section>
<section class="panel"><div class="status"><strong>{esc(status)}</strong><span>{snapshot['books_this_cycle']} books in the last cycle</span><span id="age">Saved checkpoint; see timestamps below.</span></div><p class="muted">{esc(schedule)}</p><p class="muted">Last scan: {stamp(snapshot['last_cycle'])}<br>Last feed success: {stamp(snapshot['last_feed_success'])}<br>Published snapshot: {stamp(snapshot['generated_at'])}<br>Trial expires: {stamp(snapshot['trial_expires_at'])}</p></section>
<section class="panel"><h2>Recorded equity</h2>{_plot(snapshot['equity'])}<p class="muted">Valuation and exits are observed only when a scan runs. Stops cannot protect positions during scheduler gaps. The line is historical, not a live valuation.</p></section>
<section class="panel"><h2>Paper-account checks</h2><dl>{facts_html}</dl></section>
<section class="panel"><h2>Read-only report</h2><p>This report cannot place orders, pause the scanner or submit forecasts. Use the authenticated GitHub Actions workflow to pause/resume paper entries. No detailed positions, forecasts, database or application logs are published here.</p><p class="muted">No trades is a valid result. Warm-up needs 60 prior usable observations and may take longer when scheduling or source access is interrupted. A cash-only account remains US$500 until a genuine paper fill is recorded.</p></section>
<footer>Do not fund a brokerage account based on this trial. Keep the state-encryption secret backed up separately. Refresh this page to see the next published checkpoint.</footer>
</main><script src="report.js"></script></body></html>'''
    (directory/'index.html').write_text(body)
    (directory/'summary.json').write_text(json.dumps(snapshot, indent=2, allow_nan=False)+'\n')
    (directory/'.nojekyll').write_text('')
    (directory/'report.js').write_text('''"use strict";
const root=document.querySelector('main');
function freshness(){
 const now=Date.now()/1000,last=Number(root.dataset.last),age=now-last;
 const note=document.getElementById('age');
 note.textContent=last ? 'Last scan '+Math.max(0,Math.floor(age/60))+' minutes ago — saved snapshot only' : 'No scan has completed yet';
 if(now>=Number(root.dataset.expires)) note.textContent='Trial expired — no further scans scheduled by the application';
 else if(age>600 && last) note.textContent+=' · CHECK ACTIONS FOR DELAYS';
 if(Number(root.dataset.open)>0 && age>90){
  document.getElementById('equity').textContent='Stale — not live';
  document.getElementById('pnl').textContent='Stale — not live';
 }
}
freshness();setInterval(freshness,15000);
''')
