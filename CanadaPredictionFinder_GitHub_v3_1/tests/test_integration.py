import io
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch,MagicMock
from urllib.error import HTTPError
from urllib.request import Request,urlopen
from finder.config import validate
from finder.demo import populate
from finder.network import PublicClient,NoRedirect,SourceError
from finder.runtime import Runtime,SingleInstance
from finder.replay import replay
from finder.server import create_server
from finder.analytics import ledger_audit

class NetworkTests(unittest.TestCase):
    def test_write_account_and_arbitrary_routes_rejected(self):
        c=PublicClient()
        for path in ('portfolio/orders','https://example.com/','../series','markets/X/../../orders','login'):
            with self.assertRaises(SourceError):c.get(path)
    def test_redirects_rejected(self):
        with self.assertRaises(SourceError):NoRedirect().redirect_request(None,None,302,'',{},'https://other.example')
    def test_rate_limit_retry_after(self):
        c=PublicClient();c.opener.open=MagicMock(side_effect=HTTPError('url',429,'rate limit',{'Retry-After':'120'},None))
        with self.assertRaises(SourceError):c.get('series')
        import time
        self.assertGreaterEqual(c.blocked_until-time.monotonic(),119)
        with self.assertRaises(SourceError):c.get('series')
        self.assertEqual(c.opener.open.call_count,1)
    def test_access_denied_no_bypass(self):
        c=PublicClient();c.opener.open=MagicMock(side_effect=HTTPError('url',403,'denied',{},None))
        with self.assertRaises(SourceError):c.get('markets')
        import time
        self.assertGreater(c.blocked_until-time.monotonic(),3500)
    def test_404_not_global_lockout(self):
        c=PublicClient();c.opener.open=MagicMock(side_effect=HTTPError('url',404,'missing',{},None))
        with self.assertRaises(SourceError):c.get('series/MISSING')
        self.assertEqual(c.blocked_until,0)
    def test_cached_feed_rejected(self):
        c=PublicClient();response=MagicMock();response.__enter__.return_value=response
        response.headers={'Age':'60'};response.read.return_value=b'{}'
        c.opener.open=MagicMock(return_value=response)
        with self.assertRaises(SourceError):c.get('markets')
    def test_valid_get_and_json(self):
        c=PublicClient();response=MagicMock();response.__enter__.return_value=response
        response.headers={};response.read.return_value=b'{"series":[]}';c.opener.open=MagicMock(return_value=response)
        self.assertEqual(c.get('series'),{'series':[]})
        self.assertEqual(c.opener.open.call_args[0][0].get_method(),'GET')

class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
        self.rt=Runtime(self.root/'demo','demo');populate(self.rt)
    def tearDown(self):self.tmp.cleanup()
    def test_demo_reconciles_and_stays_separate(self):
        self.assertTrue(ledger_audit(self.rt.store)['ok'])
        paper=Runtime(self.root/'paper','paper')
        self.assertEqual(paper.store.portfolio(0)['closed_positions'],0)
        self.assertEqual(paper.store.portfolio(0)['cash_units'],5000000)
    def test_demo_does_not_repopulate_profit(self):
        cash=self.rt.store.portfolio(0)['cash_units'];populate(self.rt)
        self.assertEqual(self.rt.store.portfolio(0)['cash_units'],cash)
    def test_replay_is_chronological_and_auditable(self):
        result=replay(self.rt.store.path,self.root/'replay'/'ledger.sqlite3')
        self.assertTrue(result['audit']['ok']);self.assertEqual(result['source_mode'],'demo')
        self.assertEqual(result['performance']['closed_positions'],2)
        self.assertFalse(result['performance']['live_trading_ready'])
    def test_replay_refuses_overwrite(self):
        with self.assertRaises(ValueError):replay(self.rt.store.path,self.rt.store.path)
    def test_single_instance(self):
        path=self.root/'lock'
        with SingleInstance(path):
            with self.assertRaises(RuntimeError):
                with SingleInstance(path):pass
        with SingleInstance(path):pass
    def test_database_backup_limit(self):
        p=self.rt.backup();self.assertTrue(p.is_file());self.assertTrue(ledger_audit(self.rt.store)['ok'])
    def test_headless_report_state(self):
        result=self.rt.state('test');self.assertEqual(result['csrf'],'test');self.assertEqual(result['mode'],'demo')
        json.dumps(result,allow_nan=False)
    def test_source_failure_does_not_fabricate_trades(self):
        source=MagicMock();source.batch.side_effect=SourceError('offline test');source.health={}
        rt=Runtime(self.root/'offline','paper',source=source)
        with self.assertLogs(level='ERROR'):rt.cycle()
        self.assertEqual(rt.store.portfolio(0)['closed_positions'],0)
        self.assertEqual(rt.health['state'],'ERROR')

class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.rt=Runtime(Path(cls.tmp.name),'demo');populate(cls.rt)
        cls.server=create_server(cls.rt,0);cls.port=cls.server.server_address[1]
        cls.base=f'http://127.0.0.1:{cls.port}'
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
    @classmethod
    def tearDownClass(cls):cls.server.shutdown();cls.server.server_close();cls.thread.join();cls.tmp.cleanup()
    def get(self,path):return urlopen(self.base+path,timeout=3)
    def token(self):
        with self.get('/state') as r:return json.load(r)['csrf']
    def post(self,path,body,token=None,origin=None):
        headers={'Content-Type':'application/json','Origin':origin or self.base}
        if token:headers['X-CSRF-Token']=token
        req=Request(self.base+path,data=json.dumps(body).encode(),headers=headers,method='POST')
        return urlopen(req,timeout=3)
    def test_page_and_csp(self):
        with self.get('/') as r:
            self.assertIn('frame-ancestors',r.headers['Content-Security-Policy']);self.assertIn(b'PAPER',r.read())
    def test_static_javascript(self):
        with self.get('/app.js') as r:self.assertIn(b'render',r.read())
    def test_no_path_traversal(self):
        with self.assertRaises(HTTPError) as ex:self.get('/../app.py')
        self.assertEqual(ex.exception.code,404)
    def test_host_header_blocks_dns_rebinding(self):
        req=Request(self.base+'/state',headers={'Host':'evil.example'})
        with self.assertRaises(HTTPError) as ex:urlopen(req,timeout=3)
        self.assertEqual(ex.exception.code,403)
    def test_mutation_requires_token(self):
        with self.assertRaises(HTTPError) as ex:self.post('/control/pause',{'paused':True})
        self.assertEqual(ex.exception.code,403)
    def test_mutation_requires_same_origin(self):
        with self.assertRaises(HTTPError) as ex:self.post('/control/pause',{'paused':True},self.token(),'https://other.example')
        self.assertEqual(ex.exception.code,403)
    def test_pause_control(self):
        with self.post('/control/pause',{'paused':True},self.token()) as r:self.assertTrue(json.load(r)['ok'])
    def test_export_and_report(self):
        with self.get('/export/positions.csv') as r:self.assertIn(b'ticker',r.read())
        with self.get('/report.json') as r:self.assertFalse(json.load(r)['performance']['live_trading_ready'])
    def test_no_order_route(self):
        with self.assertRaises(HTTPError) as ex:self.post('/orders',{'side':'YES'},self.token())
        self.assertEqual(ex.exception.code,404)
