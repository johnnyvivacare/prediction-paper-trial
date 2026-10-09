"""Loopback-only dashboard. No order endpoint, authentication credential or remote control."""
from __future__ import annotations
import hmac
import json
import logging
import secrets
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from .core import Market,utcnow
from .strategies import add_forecast

ASSETS=Path(__file__).parent


def create_server(runtime,port:int=8765):
    token=secrets.token_urlsafe(32)
    class Handler(BaseHTTPRequestHandler):
        server_version='LocalResearch/3.0'
        def log_message(self,fmt,*args):logging.debug(fmt,*args)
        def valid_host(self):
            p=self.server.server_address[1]
            return self.headers.get('Host') in {f'127.0.0.1:{p}',f'localhost:{p}'}
        def send(self,status:int,body,content_type='application/json'):
            if isinstance(body,(dict,list)):body=json.dumps(body,allow_nan=False).encode()
            elif isinstance(body,str):body=body.encode()
            self.send_response(status)
            self.send_header('Content-Type',content_type+'; charset=utf-8')
            self.send_header('Content-Length',str(len(body)))
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'; form-action 'self'; base-uri 'none'")
            self.end_headers()
            try:self.wfile.write(body)
            except (BrokenPipeError,ConnectionResetError):pass
        def do_GET(self):
            if not self.valid_host():return self.send(403,{'error':'Loopback host only'})
            path=urlparse(self.path).path
            try:
                if path in {'/','/style.css','/app.js'}:
                    name={'/':'dashboard.html','/style.css':'style.css','/app.js':'app.js'}[path]
                    ct={'/':'text/html','/style.css':'text/css','/app.js':'application/javascript'}[path]
                    return self.send(200,(ASSETS/name).read_bytes(),ct)
                if path=='/state':return self.send(200,runtime.state(token))
                if path=='/report.json':
                    data=runtime.state();return self.send(200,{'mode':data['mode'],'portfolio':data['portfolio'],'performance':data['performance'],'audit':data['audit']})
                if path.startswith('/export/') and path.endswith('.csv'):
                    name=path[len('/export/'):-4]
                    return self.send(200,runtime.store.export_csv(name),'text/csv')
                return self.send(404,{'error':'Not found'})
            except ValueError as exc:return self.send(400,{'error':str(exc)})
            except Exception:
                logging.exception('Dashboard read error');return self.send(500,{'error':'Internal read error; consult local logs'})
        def do_POST(self):
            if not self.valid_host():return self.send(403,{'error':'Loopback host only'})
            port=self.server.server_address[1]
            if self.headers.get('Origin') not in {f'http://127.0.0.1:{port}',f'http://localhost:{port}'}:
                return self.send(403,{'error':'Same-origin request required'})
            supplied=self.headers.get('X-CSRF-Token','')
            if not hmac.compare_digest(supplied,token):return self.send(403,{'error':'Reload dashboard; invalid session token'})
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':return self.send(415,{'error':'JSON required'})
            try:
                length=int(self.headers.get('Content-Length','0'))
                if not 0<length<=16384:return self.send(413,{'error':'Invalid request size'})
                data=json.loads(self.rfile.read(length))
                if not isinstance(data,dict):raise ValueError('Expected JSON object')
                path=urlparse(self.path).path
                with runtime.lock:
                    if path=='/control/pause':
                        paused=data.get('paused')
                        if not isinstance(paused,bool):raise ValueError('paused must be true or false')
                        if not paused:
                            from .analytics import ledger_audit
                            if not ledger_audit(runtime.store)['ok']:raise ValueError('Cannot resume: ledger audit failed')
                        runtime.store.setmeta('paused',str(paused).lower())
                        runtime.store.event('USER_CONTROL','Entries paused' if paused else 'Entries resumed; independent risk gates still apply')
                    elif path=='/control/backup':
                        dest=runtime.backup()
                        return self.send(200,{'ok':True,'filename':dest.name})
                    elif path=='/control/close':
                        ticker=data.get('ticker')
                        if not isinstance(ticker,str) or not runtime.store.rows("SELECT id FROM positions WHERE ticker=? AND status='open'",(ticker,)):
                            raise ValueError('No open paper position for that contract')
                        runtime.store.setmeta('close:'+ticker,'true')
                        runtime.store.event('USER_CONTROL',ticker+': queued paper exit; requires next fresh executable book')
                    elif path=='/control/forecast':
                        ticker=data.get('ticker')
                        if not isinstance(ticker,str):raise ValueError('Select a contract')
                        rows=runtime.store.rows('SELECT payload FROM markets WHERE ticker=?',(ticker,))
                        if not rows:raise ValueError('Unknown market')
                        market=Market(**json.loads(rows[0]['payload']))
                        hours=float(data.get('hours',0))
                        if not 0<hours<=168:raise ValueError('Forecast expiry must be within 168 hours')
                        now=utcnow()
                        add_forecast(runtime.store,market,float(data['p']),float(data['lo']),float(data['hi']),
                            min(now+hours*3600,market.close_at),str(data.get('source','')),str(data.get('method','')),now)
                        runtime.store.event('FORECAST_ADDED',ticker+': user-supplied forecast; not independently verified')
                    else:return self.send(404,{'error':'Not found'})
                    runtime._report_time=0
                return self.send(200,{'ok':True})
            except (ValueError,TypeError,KeyError) as exc:return self.send(400,{'error':str(exc)})
            except Exception:
                logging.exception('Dashboard control error');return self.send(500,{'error':'Control failed; consult local logs'})
        def do_OPTIONS(self):return self.send(405,{'error':'Cross-origin access disabled'})
    class LocalServer(ThreadingHTTPServer):
        daemon_threads=True
        allow_reuse_address=True
        def get_request(self):
            sock,addr=super().get_request();sock.settimeout(10);return sock,addr
    return LocalServer(('127.0.0.1',port),Handler)
