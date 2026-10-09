from contextlib import closing
from dataclasses import asdict
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import time
import unittest
from unittest.mock import patch

from finder.analytics import ledger_audit
from finder.runtime import Runtime
from github_support.state import GitState, StateError, make_checkpoint, restore_checkpoint, passphrase
from github_support.runner import config_for, read_profile, scan_batch, compact_history, save_source, restore_source
from github_support.report import public_snapshot, write_report

SECRET='unit-test-only-random-passphrase-not-a-real-secret-0123456789'
REPO='example/prediction-test'


class Fixture(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.runtime=Runtime(self.root/'paper',mode='paper')
        self.runtime.store.setmeta('github_experiment','test-experiment')
        self.meta={'repository':REPO,'experiment':'test-experiment','sequence':1,'created_at':1}
    def tearDown(self):self.temp.cleanup()


class ProfileTests(Fixture):
    def test_profile_valid(self):
        p=self.root/'profile.json';p.write_text(json.dumps({'profile':'minute-burst','trial_days':7,'checkpoint_samples_per_ticker':360}))
        self.assertEqual(config_for(read_profile(p))['scan_seconds'],60)
    def test_economy_is_explicit_300_seconds(self):
        self.assertEqual(config_for({'profile':'economy'})['scan_seconds'],300)
    def test_reject_unbounded_trial(self):
        p=self.root/'profile.json';p.write_text(json.dumps({'profile':'minute-burst','trial_days':1000,'checkpoint_samples_per_ticker':360}))
        with self.assertRaises(StateError):read_profile(p)
    def test_short_passphrase_rejected(self):
        with self.assertRaises(StateError):passphrase('short')
    def test_linebreak_passphrase_rejected(self):
        with self.assertRaises(StateError):passphrase(SECRET+'\n')
    def test_profile_rejects_unknown_fields(self):
        p=self.root/'profile.json';p.write_text(json.dumps({'profile':'minute-burst','trial_days':7,'checkpoint_samples_per_ticker':360,'live':True}))
        with self.assertRaises(StateError):read_profile(p)


@unittest.skipUnless(shutil.which('gpg'),'GnuPG is required for encrypted GitHub checkpoints')
class CheckpointTests(Fixture):
    def build(self):
        path=self.root/'state.gpg';make_checkpoint(self.runtime,path,SECRET,self.meta);return path
    def test_roundtrip_audit_and_persistence(self):
        self.runtime.store.setmeta('custom_marker','retained across runners')
        path=self.build();dest=self.root/'restored'
        meta=restore_checkpoint(path,dest,SECRET,REPO)
        restored=Runtime(dest,mode='paper')
        self.assertTrue(ledger_audit(restored.store)['ok'])
        self.assertEqual(restored.store.meta('custom_marker'),'retained across runners')
        self.assertEqual(restored.store.portfolio(time.time())['initial_units'],5000000)
        self.assertEqual(meta['sequence'],1)
    def test_plaintext_not_visible_in_ciphertext(self):
        self.runtime.store.setmeta('private_text','never-publish-my-private-forecast-ABCDEF')
        encrypted=self.build().read_bytes()
        self.assertNotIn(b'never-publish-my-private-forecast',encrypted)
        self.assertNotIn(b'SQLite format',encrypted)
    def test_wrong_secret_stops_no_reset(self):
        path=self.build();dest=self.root/'wrong'
        with self.assertRaises(StateError):restore_checkpoint(path,dest,SECRET+'wrong',REPO)
        self.assertFalse((dest/'ledger.sqlite3').exists())
    def test_corrupted_checkpoint_stops(self):
        path=self.build();data=bytearray(path.read_bytes());data[len(data)//2]^=1;path.write_bytes(data)
        with self.assertRaises(StateError):restore_checkpoint(path,self.root/'corrupt',SECRET,REPO)
        self.assertFalse((self.root/'corrupt'/'ledger.sqlite3').exists())
    def test_repository_identity_mismatch_stops(self):
        path=self.build()
        with self.assertRaises(StateError):restore_checkpoint(path,self.root/'wrong-repo',SECRET,'other/repo')
    def test_cannot_overwrite_existing_directory(self):
        path=self.build();dest=self.root/'nonempty';dest.mkdir();(dest/'keep').write_text('safe')
        with self.assertRaises(StateError):restore_checkpoint(path,dest,SECRET,REPO)
        self.assertEqual((dest/'keep').read_text(),'safe')
    def test_missing_checkpoint_not_empty_account(self):
        with self.assertRaises(StateError):restore_checkpoint(self.root/'missing.gpg',self.root/'missing',SECRET,REPO)
    def test_invalid_account_not_checkpointed(self):
        with self.runtime.store.connect() as db:db.execute('UPDATE cash SET units=12345')
        with self.assertRaises(StateError):self.build()
    def test_missing_cash_record_rejected_on_restore(self):
        # Forge a syntactically valid encrypted archive with no cash row. It must
        # be rejected BEFORE Store would recreate the initial cash record.
        import hashlib,zipfile
        from github_support.state import _gpg
        path=self.build();archive=self.root/'plain.zip';_gpg(path,archive,SECRET,True)
        with zipfile.ZipFile(archive) as z:members={i:z.read(i) for i in z.namelist()}
        dbpath=self.root/'broken.sqlite3';dbpath.write_bytes(members['ledger.sqlite3'])
        with closing(sqlite3.connect(dbpath)) as db:db.execute('DELETE FROM cash');db.commit()
        members['ledger.sqlite3']=dbpath.read_bytes()
        metadata=json.loads(members['checkpoint.json']);metadata['database_sha256']=hashlib.sha256(members['ledger.sqlite3']).hexdigest()
        members['checkpoint.json']=json.dumps(metadata).encode()
        with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
            for name,data in members.items():z.writestr(name,data)
        _gpg(archive,path,SECRET,False)
        with self.assertRaises(StateError):restore_checkpoint(path,self.root/'cashless',SECRET,REPO)
    def test_zip_traversal_not_extracted(self):
        import zipfile
        from github_support.state import _gpg
        archive=self.root/'bad.zip'
        with zipfile.ZipFile(archive,'w') as z:z.writestr('../escape','evil')
        target=self.root/'bad.gpg';_gpg(archive,target,SECRET,False)
        with self.assertRaises(StateError):restore_checkpoint(target,self.root/'target',SECRET,REPO)
        self.assertFalse((self.root/'escape').exists())


class BatchTests(Fixture):
    def run_batch(self,count=5,run_id='1',expires=10000,cycle_time=0):
        clock=[1000.];calls=[]
        def cycle():calls.append(clock[0]);clock[0]+=cycle_time
        def sleep(s):clock[0]+=s
        with patch.object(self.runtime,'cycle',side_effect=cycle):
            result=scan_batch(self.runtime,count,run_id,expires,clock=lambda:clock[0],monotonic=lambda:clock[0],sleep=sleep)
        return result,calls
    def test_five_minute_spaced_scans(self):
        r,calls=self.run_batch();self.assertEqual(calls,[1000,1060,1120,1180,1240]);self.assertEqual(r['scans'],5)
    def test_slow_scan_does_not_burst_catch_up(self):
        r,calls=self.run_batch(cycle_time=140);self.assertEqual(len(calls),1)
    def test_already_completed_run_skipped(self):
        self.run_batch();r,calls=self.run_batch();self.assertTrue(r['duplicate']);self.assertEqual(calls,[])
    def test_older_rerun_after_new_run_skipped(self):
        self.run_batch(run_id='1');self.run_batch(run_id='2');r,calls=self.run_batch(run_id='1')
        self.assertTrue(r['duplicate']);self.assertEqual(calls,[])
    def test_expired_trial_no_scans(self):
        r,calls=self.run_batch(expires=999);self.assertTrue(r['expired']);self.assertEqual(calls,[])
    def test_expiry_mid_batch_respected(self):
        r,calls=self.run_batch(expires=1100);self.assertEqual(calls,[1000,1060]);self.assertTrue(r['expired'])
    def test_engine_exception_pauses_entries(self):
        with patch.object(self.runtime,'cycle',side_effect=RuntimeError('boom')):
            r=scan_batch(self.runtime,1,'7',time.time()+100)
        self.assertTrue(r['engine_error']);self.assertEqual(self.runtime.store.meta('paused'),'true')
    def test_unknown_scan_count_rejected(self):
        with self.assertRaises(StateError):scan_batch(self.runtime,10000,'8',time.time()+100)
    def test_pause_preserved_between_batches(self):
        self.runtime.store.setmeta('paused','true');self.run_batch()
        self.assertEqual(self.runtime.store.meta('paused'),'true')


class CacheAndReportTests(Fixture):
    def test_backoff_converts_monotonic_to_wall_clock(self):
        self.runtime.source.client.blocked_until=1500
        self.runtime.source.client.failures=4
        with patch('github_support.runner.time.monotonic',return_value=1000),patch('github_support.runner.time.time',return_value=10000):
            save_source(self.runtime)
        with patch('github_support.runner.time.monotonic',return_value=50),patch('github_support.runner.time.time',return_value=10200):
            restore_source(self.runtime)
        self.assertEqual(self.runtime.source.client.blocked_until,350)
        self.assertEqual(self.runtime.source.client.failures,4)
    def test_no_live_orders_in_public_snapshot(self):
        snap=public_snapshot(self.runtime,'minute-burst',time.time()+100,time.time())
        self.assertTrue(snap['no_live_orders']);self.assertFalse(snap['canadian_broker_quotes_verified'])
    def test_private_fields_excluded_from_report(self):
        self.runtime.store.event('SECRET_MARKER','do-not-publish-this-text')
        self.runtime.store.setmeta('private_key','not-a-real-secret')
        snap=public_snapshot(self.runtime,'minute-burst',time.time()+100,time.time())
        site=self.root/'site';write_report(snap,site)
        content=''.join(p.read_text() for p in site.iterdir())
        self.assertNotIn('do-not-publish-this-text',content);self.assertNotIn('not-a-real-secret',content)
        for field in ['positions','signals','events','markets','config','csrf']:
            self.assertNotIn(field,snap)
    def test_static_report_relative_script(self):
        site=self.root/'site';write_report(public_snapshot(self.runtime,'minute-burst',time.time()+100,time.time()),site)
        page=(site/'index.html').read_text();self.assertIn('src="report.js"',page)
        self.assertNotIn('src="/',page);self.assertIn('Stale — not live',(site/'report.js').read_text())
    def test_report_initial_cash_not_fabricated_profit(self):
        s=public_snapshot(self.runtime,'minute-burst',time.time()+100,time.time())
        self.assertEqual(s['portfolio']['total_pnl_units'],0);self.assertEqual(s['portfolio']['closed_positions'],0)
    def test_compaction_keeps_latest_samples(self):
        with self.runtime.store.connect() as db:
            for i in range(500):db.execute('INSERT INTO snapshots(ts,ticker,mid,market_json,book_json,fee_json) VALUES (?,?,?,?,?,?)',(i,'TEST',.5,'{}','{}','{}'))
        compact_history(self.runtime,360)
        samples=self.runtime.store.rows('SELECT ts FROM snapshots ORDER BY ts')
        self.assertEqual(len(samples),360);self.assertEqual(samples[0]['ts'],140)
        self.assertTrue(ledger_audit(self.runtime.store)['ok'])


class GitStateTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.remote=self.root/'remote.git';self.checkout=self.root/'checkout'
        self.cmd('git','init','--bare',str(self.remote));self.cmd('git','init','-b','main',str(self.checkout))
        self.cmd('git','-C',str(self.checkout),'config','user.name','Test')
        self.cmd('git','-C',str(self.checkout),'config','user.email','test@example.invalid')
        self.cmd('git','-C',str(self.checkout),'remote','add','origin',str(self.remote))
        (self.checkout/'source.txt').write_text('leave my source alone')
        self.cmd('git','-C',str(self.checkout),'add','source.txt')
        self.cmd('git','-C',str(self.checkout),'commit','-m','source')
        self.cmd('git','-C',str(self.checkout),'push','origin','main')
        self.initial=self.cmd('git','-C',str(self.checkout),'rev-parse','HEAD').strip()
    def tearDown(self):self.temp.cleanup()
    def cmd(self,*args):
        return subprocess.run(args,check=True,capture_output=True,text=True).stdout
    def checkpoint(self,name,data):
        p=self.root/name;p.write_bytes(data);return p
    def initial_write(self):
        state=GitState(self.checkout);self.assertFalse(state.fetch(self.root/'incoming',initialize=True))
        state.publish(self.checkpoint('first.gpg',b'encrypted-placeholder-one'))
        return state
    def test_missing_remote_requires_initialization(self):
        with self.assertRaises(StateError):GitState(self.checkout).fetch(self.root/'incoming')
    def test_only_reserved_branch_can_be_written(self):
        for name in ['main','master','gh-pages','../main']:
            with self.assertRaises(StateError):GitState(self.checkout,name)
    def test_state_push_does_not_touch_source(self):
        self.initial_write()
        self.assertEqual(self.cmd('git','-C',str(self.checkout),'rev-parse','HEAD').strip(),self.initial)
        self.assertEqual(self.cmd('git','-C',str(self.checkout),'status','--porcelain'),'')
        self.assertEqual((self.checkout/'source.txt').read_text(),'leave my source alone')
    def test_roundtrip_and_previous_checkpoint(self):
        self.initial_write();state=GitState(self.checkout);target=self.root/'again'
        self.assertTrue(state.fetch(target));self.assertEqual(target.read_bytes(),b'encrypted-placeholder-one')
        state.publish(self.checkpoint('second.gpg',b'encrypted-placeholder-two'))
        previous=self.cmd('git','-C',str(self.checkout),'show',state.expected+':previous.gpg')
        self.assertEqual(previous,'encrypted-placeholder-one')
        self.assertEqual(self.cmd('git','-C',str(self.checkout),'rev-list','--count',state.expected).strip(),'1')
    def test_conflicting_writer_rejected_by_lease(self):
        self.initial_write();one=GitState(self.checkout);two=GitState(self.checkout)
        one.fetch(self.root/'one');two.fetch(self.root/'two')
        one.publish(self.checkpoint('new.gpg',b'new'))
        with self.assertRaises(StateError):two.publish(self.checkpoint('loser.gpg',b'loser'))
    def test_no_fetch_no_write(self):
        with self.assertRaises(StateError):GitState(self.checkout).publish(self.checkpoint('x.gpg',b'x'))
    def test_state_unreachable_does_not_initialize(self):
        self.cmd('git','-C',str(self.checkout),'remote','set-url','origin',str(self.root/'missing-remote'))
        with self.assertRaises(StateError):GitState(self.checkout).fetch(self.root/'incoming',initialize=True)
    def test_remote_contents_allowlist(self):
        state=self.initial_write()
        files=self.cmd('git','-C',str(self.checkout),'ls-tree','--name-only',state.expected).splitlines()
        self.assertEqual(set(files),{'state.gpg','README.txt'})



@unittest.skipUnless(shutil.which('gpg'),'GnuPG is required')
class EndToEndCloudTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
        self.repo=self.root/'checkout';remote=self.root/'remote.git'
        subprocess.run(['git','init','--bare',str(remote)],check=True,capture_output=True)
        subprocess.run(['git','init','-b','main',str(self.repo)],check=True,capture_output=True)
        for args in [['config','user.name','Test'],['config','user.email','test@example.invalid'],['remote','add','origin',str(remote)]]:
            subprocess.run(['git','-C',str(self.repo),*args],check=True,capture_output=True)
        (self.repo/'github_profile.json').write_text(json.dumps({'profile':'economy','trial_days':7,'checkpoint_samples_per_ticker':360}))
        for args in [['add','github_profile.json'],['commit','-m','source'],['push','origin','main']]:
            subprocess.run(['git','-C',str(self.repo),*args],check=True,capture_output=True)
        self.env={'GITHUB_REPOSITORY':REPO,'GITHUB_RUN_ID':'100','STATE_PASSPHRASE':SECRET,
                  'REPOSITORY_PRIVATE':'false','GITHUB_OUTPUT':str(self.root/'outputs'),
                  'GITHUB_STEP_SUMMARY':str(self.root/'summary'),'PUBLISH_PAPER_SUMMARY':'false'}
    def tearDown(self):self.temp.cleanup()
    def initialize(self):
        from github_support.runner import execute
        with patch.dict(os.environ,self.env):
            return execute('initialize',self.repo,self.root/'init-output',True)
    def restored(self,name='inspect'):
        state=GitState(self.repo);cipher=self.root/(name+'.gpg');state.fetch(cipher)
        folder=self.root/name;metadata=restore_checkpoint(cipher,folder,SECRET,REPO)
        return Runtime(folder,mode='paper'),metadata
    def test_initialization_then_scan_retains_executed_paper_fills(self):
        from github_support.runner import execute
        from finder.demo import sample_market,sample_book
        from finder.core import Fee
        from finder.strategies import add_forecast
        self.assertEqual(self.initialize(),0)
        def fake_cycle(rt):
            now=time.time();m=sample_market('FIXTURE','FIXTURE-EVENT',now-600)
            add_forecast(rt.store,m,.75,.69,.82,now+1800,'Fabricated integration fixture only','Fake forecast for software testing',now-600)
            for ts,mid in [(now-600,.4),(now-300,.4),(now,.8)]:
                if ts==now:rt.store.setmeta('close:FIXTURE','true')
                rt.engine.observe(m,sample_book(m,ts,mid),Fee('quadratic','1',ts),ts)
            rt.last_cycle=now;rt.store.setmeta('last_cycle',str(now));rt.store.record_equity(now)
            rt.source.health.update(state='OK',last_success=now,books_this_cycle=1)
        with patch.dict(os.environ,{**self.env,'GITHUB_RUN_ID':'101'}),patch.object(Runtime,'cycle',fake_cycle):
            self.assertEqual(execute('scan',self.repo,self.root/'scan-output'),0)
        restored,meta=self.restored()
        p=restored.store.portfolio(time.time())
        self.assertEqual(p['closed_positions'],1);self.assertNotEqual(p['cash_units'],p['initial_units'])
        self.assertTrue(ledger_audit(restored.store)['ok']);self.assertEqual(meta['sequence'],2)
        self.assertNotIn('Paper equity:',(self.root/'summary').read_text())
        # Re-running a saved GitHub run never reexecutes the cycle.
        with patch.dict(os.environ,{**self.env,'GITHUB_RUN_ID':'101'}),patch.object(Runtime,'cycle',side_effect=AssertionError('duplicate')):
            self.assertEqual(execute('scan',self.repo,self.root/'duplicate-output'),0)
    def test_reinitialize_refuses_to_replace_existing_experiment(self):
        self.initialize()
        with self.assertRaises(StateError):self.initialize()
        restored,meta=self.restored();self.assertEqual(meta['sequence'],1)
    def test_private_cost_acknowledgement_required(self):
        from github_support.runner import execute
        with patch.dict(os.environ,{**self.env,'REPOSITORY_PRIVATE':'true','ACK_PRIVATE_ACTIONS_COSTS':''}):
            with self.assertRaises(StateError):execute('initialize',self.repo,self.root/'out',True)
    def test_dex_repository_guard(self):
        from github_support.runner import execute
        with patch.dict(os.environ,{**self.env,'GITHUB_REPOSITORY':'johnnyvivacare/paper-dex-logger'}):
            with self.assertRaises(StateError):execute('initialize',self.repo,self.root/'out',True)
    def test_manual_initialization_confirmation_required(self):
        from github_support.runner import execute
        with patch.dict(os.environ,self.env):
            with self.assertRaises(StateError):execute('initialize',self.repo,self.root/'out',False)

if __name__=='__main__':unittest.main()
