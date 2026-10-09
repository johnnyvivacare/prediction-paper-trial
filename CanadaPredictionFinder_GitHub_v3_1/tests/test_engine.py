import json
from contextlib import closing
import math
from pathlib import Path
import sqlite3
import tempfile
import unittest
from dataclasses import replace
from finder.config import validate
from finder.core import USD,Book,Fee,digest
from finder.demo import sample_market,sample_book
from finder.engine import Engine
from finder.store import Store
from finder.analytics import ledger_audit,performance,bootstrap_event_mean
from finder.strategies import add_forecast,forecast_signal,reversion_signal,empirical_probability

T=1791435600.0

class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'ledger.sqlite3'
        self.s=Store(self.path);self.c=validate({});self.e=Engine(self.s,self.c)
        self.m=sample_market('TEST','EVENT',T)
    def tearDown(self):self.tmp.cleanup()
    def forecast(self,m=None,at=T,p=.72,lo=.65,hi=.8):
        m=m or self.m
        return add_forecast(self.s,m,p,lo,hi,at+3600,'Independent test input only','Fixture probability method',at)
    def tick(self,t,m=None,mid=.4,size=1000,allow=True):
        m=m or self.m
        self.e.observe(m,sample_book(m,t,mid,size),Fee('quadratic','1',t),t,allow)
    def opened(self):
        self.forecast();self.tick(T);self.tick(T+60)
        return self.s.rows('SELECT * FROM positions')[0]
    def test_two_scan_confirmation(self):
        self.forecast();self.tick(T)
        self.assertEqual(len(self.s.rows('SELECT * FROM positions')),0)
        self.tick(T+60);self.assertEqual(len(self.s.rows('SELECT * FROM positions')),1)
    def test_no_same_tick_confirmation(self):
        self.forecast();self.tick(T);self.tick(T+1)
        self.assertFalse(self.s.rows('SELECT * FROM positions'))
    def test_delayed_confirmation_restarts(self):
        self.forecast();self.tick(T);self.tick(T+300)
        self.assertFalse(self.s.rows('SELECT * FROM positions'))
    def test_entries_fit_two_percent_including_fees(self):
        p=self.opened();self.assertLessEqual(p['cost'],10*USD);self.assertGreater(p['fees'],0)
        self.assertTrue(ledger_audit(self.s)['ok'])
    def test_event_group_exposure_not_ticker_only(self):
        p=self.opened();other=sample_market('OTHER','EVENT',T)
        budget,_=self.e.budget(other,T+60)
        self.assertLessEqual(budget,10*USD-p['cost'])
    def test_duplicate_protection(self):
        self.opened();self.tick(T+120);self.tick(T+180)
        self.assertEqual(len(self.s.rows('SELECT * FROM positions')),1)
    def test_fresh_bid_mark_includes_exit_cost(self):
        p=self.opened();v=self.s.portfolio(T+60)
        self.assertLess(v['equity_units'],500*USD)
        self.assertLess(v['equity_units']-v['cash_units'],p['cost'])
    def test_stale_marks_make_nav_unknown(self):
        self.opened();p=self.s.portfolio(T+151)
        self.assertIsNone(p['equity_units']);self.assertEqual(p['unpriceable_positions'],1)
    def test_mark_age_uses_actual_fetch_time(self):
        self.opened()
        b=sample_book(self.m,T+60)
        self.e.mark(self.m,b,Fee('quadratic','1',T+60),T+100)
        self.assertIsNone(self.s.portfolio(T+151)['equity_units'])
    def test_partial_depth_not_full_nav(self):
        self.opened();b=sample_book(self.m,T+120,size=4)
        self.e.mark(self.m,b,Fee('quadratic','1',T+120),T+120)
        self.assertIsNone(self.s.portfolio(T+120)['equity_units'])
    def test_stale_book_cannot_open(self):
        self.forecast();b=sample_book(self.m,T)
        self.e.observe(self.m,b,Fee('quadratic','1',T),T+200)
        self.assertFalse(self.s.rows('SELECT * FROM positions'))
    def test_future_book_cannot_open(self):
        self.forecast();self.e.observe(self.m,sample_book(self.m,T+60),Fee('quadratic','1',T),T)
        self.assertFalse(self.s.rows('SELECT * FROM positions'))
    def test_unknown_fee_cannot_open(self):
        self.forecast()
        for t in (T,T+60):self.e.observe(self.m,sample_book(self.m,t),Fee('unknown','1',t),t)
        self.assertFalse(self.s.rows('SELECT * FROM positions'))
    def test_pause_blocks_entries(self):
        self.s.setmeta('paused','true');self.forecast();self.tick(T);self.tick(T+60)
        self.assertFalse(self.s.rows('SELECT * FROM positions'))
    def test_pause_does_not_block_exit(self):
        self.opened();self.s.setmeta('paused','true');self.tick(T+120,mid=.2)
        self.assertEqual(self.s.rows('SELECT status FROM positions')[0]['status'],'closed')
    def test_manual_paper_exit_requires_fresh_book(self):
        self.opened();self.s.setmeta('close:TEST','true');self.tick(T+120)
        self.assertEqual(self.s.rows('SELECT status FROM positions')[0]['status'],'closed')
    def test_partial_exit_preserves_remaining_and_audit(self):
        p=self.opened();self.tick(T+120,mid=.2,size=8)
        row=self.s.rows('SELECT * FROM positions')[0]
        self.assertEqual(row['remaining'],p['qty']-2);self.assertEqual(row['status'],'open')
        self.assertTrue(ledger_audit(self.s)['ok'])
    def test_no_exit_same_observation(self):
        self.opened()
        self.assertFalse(self.e.exit_position(self.m,sample_book(self.m,T+60,.2),Fee('quadratic','1',T+60),T+60,True))
    def test_settlement_yes_credits_once(self):
        p=self.opened();m=replace(self.m,status='finalized',result='YES')
        self.assertTrue(self.e.settle(m,T+7201));cash=self.s.portfolio(T+7201)['cash_units']
        self.assertFalse(self.e.settle(m,T+7202));self.assertEqual(self.s.portfolio(T+7202)['cash_units'],cash)
        self.assertEqual(cash,500*USD-p['cost']+p['qty']*USD)
        self.assertTrue(ledger_audit(self.s)['ok'])
    def test_losing_settlement_zero_payout(self):
        p=self.opened();self.e.settle(replace(self.m,status='settled',result='NO'),T+7201)
        self.assertEqual(self.s.portfolio(T+7201)['realized_units'],-p['cost'])
    def test_provisional_settlement_rejected(self):
        self.opened();self.assertFalse(self.e.settle(replace(self.m,status='finalized',result='YES',provisional=True),T+7201))
    def test_closed_is_not_final_settlement(self):
        self.opened();self.assertFalse(self.e.settle(replace(self.m,status='closed',result='YES'),T+7201))
    def test_early_finalization_rejected(self):
        self.opened();self.assertFalse(self.e.settle(replace(self.m,status='finalized',result='YES'),T+120))
    def test_changed_rules_do_not_credit(self):
        self.opened();self.assertFalse(self.e.settle(replace(self.m,status='finalized',result='YES',rules_hash='different'),T+7201))
    def test_changed_rules_do_not_exit_or_refresh_mark(self):
        self.opened();self.tick(T+120,m=replace(self.m,rules_hash='different'),mid=.2)
        self.assertEqual(self.s.rows('SELECT status FROM positions')[0]['status'],'open')
        self.assertIsNone(self.s.portfolio(T+151)['equity_units'])
    def test_no_side_trade_and_settlement(self):
        self.forecast(p=.25,lo=.2,hi=.3)
        self.tick(T,mid=.6);self.tick(T+60,mid=.6)
        p=self.s.rows('SELECT * FROM positions')[0];self.assertEqual(p['side'],'NO')
        self.e.settle(replace(self.m,status='finalized',result='NO'),T+7201)
        self.assertGreater(self.s.portfolio(T+7201)['realized_units'],0)
    def test_canada_verification_gate_blocks_unverified_feed(self):
        e=Engine(self.s,{**self.c,'require_canada_verification':True})
        self.assertEqual(e.budget(self.m,T)[0],0)
    def test_strategy_change_does_not_mix_after_first_trade(self):
        self.opened();e=Engine(self.s,{**self.c,'min_edge_usd':.05})
        self.assertIn('CONFIG_CHANGED',e.risk_state(T+60)[1])
    def test_daily_loss_circuit(self):
        self.e.risk_state(T)
        with self.s.connect() as db:db.execute('UPDATE cash SET units=? WHERE id=1',(480*USD,))
        self.assertEqual(self.e.risk_state(T+60)[1],'DAILY_LOSS_LIMIT')
    def test_drawdown_halt_latches(self):
        self.e.risk_state(T)
        with self.s.connect() as db:db.execute('UPDATE cash SET units=? WHERE id=1',(450*USD,))
        self.assertEqual(self.e.risk_state(T+60)[1],'DRAWDOWN_CIRCUIT_BREAKER')
        with self.s.connect() as db:db.execute('UPDATE cash SET units=? WHERE id=1',(500*USD,))
        self.assertEqual(self.e.risk_state(T+120)[1],'DRAWDOWN_CIRCUIT_BREAKER')
    def test_forecast_no_lookahead(self):
        self.forecast(at=T+300);self.assertFalse(forecast_signal(self.s,self.m,T))
    def test_expired_forecast_rejected(self):
        self.forecast();self.assertFalse(forecast_signal(self.s,self.m,T+3601))
    def test_forecast_rules_must_match(self):
        self.forecast();self.assertFalse(forecast_signal(self.s,replace(self.m,rules_hash='x'),T))
    def test_forecast_uses_interval_not_point(self):
        self.forecast();signals=forecast_signal(self.s,self.m,T)
        self.assertEqual(signals[0].fair_units,6500);self.assertAlmostEqual(signals[1].fair_units,2000,delta=1)
    def test_forecast_invalid_probabilities_rejected(self):
        for vals in ((.7,.8,.9),(.7,.69,.71),(float('nan'),.5,.8)):
            with self.assertRaises(ValueError):self.forecast(p=vals[0],lo=vals[1],hi=vals[2])
    def test_reversion_warmup_required(self):
        signals,note=reversion_signal(self.s,self.m,sample_book(self.m,T),self.c,T)
        self.assertFalse(signals);self.assertIn('WARMUP',note)
    def seed_history(self,spacing=60):
        for i in range(60):
            t=T-(60-i)*spacing
            self.s.snapshot(self.m,sample_book(self.m,t,.62),Fee('quadratic','1',t),t)
    def test_reversion_produces_price_target_not_forecast(self):
        self.seed_history();signals,note=reversion_signal(self.s,self.m,sample_book(self.m,T,.4),self.c,T)
        self.assertEqual(signals[0].side,'YES');self.assertIsNone(signals[0].p)
        self.assertIn('not outcome probability',signals[0].note)
    def test_reversion_rejects_too_dense_samples(self):
        self.seed_history(spacing=1);signals,note=reversion_signal(self.s,self.m,sample_book(self.m,T,.4),self.c,T)
        self.assertFalse(signals);self.assertIn('WARMUP',note)
    def test_reversion_rejects_long_history_gap(self):
        self.seed_history();signals,note=reversion_signal(self.s,self.m,sample_book(self.m,T+1000,.4),self.c,T+1000)
        self.assertFalse(signals);self.assertIn('HISTORY_GAP',note)
    def test_empirical_forecast_requires_enough_draws(self):
        with self.assertRaises(ValueError):empirical_probability([1,2],1)
    def test_ledger_survives_restart_without_reset(self):
        self.opened();cash=self.s.portfolio(T+60)['cash_units']
        other=Store(self.path,initial=1000*USD)
        self.assertEqual(other.portfolio(T+60)['cash_units'],cash)
        self.assertEqual(other.portfolio(T+60)['initial_units'],500*USD)
    def test_demo_cannot_mix_with_paper(self):
        with self.assertRaises(ValueError):Store(self.path,mode='demo')
    def test_legacy_db_rejected(self):
        path=Path(self.tmp.name)/'legacy.db'
        with closing(sqlite3.connect(path)) as db:db.execute('CREATE TABLE trades(id INTEGER)')
        with self.assertRaises(ValueError):Store(path)
    def test_backup_is_consistent(self):
        self.opened();dest=Path(self.tmp.name)/'backup.db';self.s.backup(dest)
        self.assertTrue(ledger_audit(Store(dest))['ok'])
    def test_audit_detects_cash_corruption(self):
        with self.s.connect() as db:db.execute('UPDATE cash SET units=units+1')
        self.assertFalse(ledger_audit(self.s)['ok'])
    def test_csv_formula_injection_escaped(self):
        self.s.event('TEST','=HYPERLINK("unsafe")',T)
        self.assertIn("'=HYPERLINK",self.s.export_csv('events'))
    def test_csv_arbitrary_table_rejected(self):
        with self.assertRaises(ValueError):self.s.export_csv('sqlite_master')
    def test_no_report_enables_live_execution(self):self.assertFalse(performance(self.s,T)['live_trading_ready'])
    def test_bootstrap_small_sample_not_confidence(self):self.assertIsNone(bootstrap_event_mean([1]*9))

    def test_first_entry_freezes_actual_configuration(self):
        self.s.setmeta('config_original',json.dumps(self.c))
        self.e=Engine(self.s,{**self.c,'slippage_usd_per_contract':.02})
        self.opened()
        self.assertEqual(json.loads(self.s.meta('config_original'))['slippage_usd_per_contract'],.02)
    def test_mismatched_book_identity_rejected(self):
        self.forecast()
        b=replace(sample_book(self.m,T),ticker='OTHER')
        with self.assertRaises(ValueError):self.e.observe(self.m,b,Fee('quadratic','1',T),T)
    def test_mismatched_book_cannot_mark(self):
        self.opened()
        b=replace(sample_book(self.m,T+120),ticker='OTHER')
        self.e.mark(self.m,b,Fee('quadratic','1',T+120),T+120)
        self.assertIsNone(self.s.portfolio(T+151)['equity_units'])
    def test_exact_four_point_forecast_interval(self):
        self.forecast(p=.78,lo=.76,hi=.80)
        self.assertEqual(len(forecast_signal(self.s,self.m,T)),2)
