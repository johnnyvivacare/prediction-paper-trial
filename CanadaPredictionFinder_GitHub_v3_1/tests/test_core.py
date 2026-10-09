import math
import unittest
from dataclasses import replace
from finder.core import USD,Book,Fee,Market,money,decimal,timestamp,walk,digest
from finder.config import validate,fingerprint

T=1791435600.0

class CoreTests(unittest.TestCase):
    def test_exact_money(self):self.assertEqual(money('0.1234'),1234)
    def test_nonfinite_money(self):
        for x in ('NaN','Infinity','-Infinity'):
            with self.assertRaises(ValueError):money(x)
    def test_unsupported_precision(self):
        with self.assertRaises(ValueError):money('0.00001')
    def test_timezone_required(self):
        with self.assertRaises(ValueError):timestamp('2026-10-07T12:00:00')
    def test_timestamp_offset_equivalence(self):
        self.assertEqual(timestamp('2026-10-07T12:00:00Z'),timestamp('2026-10-07T05:00:00-07:00'))
    def test_fee_floor_and_rounding(self):
        self.assertEqual(Fee('quadratic','1',T).charge(3,5000),900)
        self.assertEqual(Fee('quadratic','1',T,0).charge(3,5000),600)
    def test_fee_metadata_fail_closed(self):
        for f in (Fee('unknown','1',T),Fee('quadratic','NaN',T),Fee('quadratic','0',T),Fee('quadratic','1',T-3601)):
            self.assertFalse(f.valid(T))
    def test_fee_future_rejected(self):self.assertFalse(Fee('quadratic','1',T+1).valid(T))
    def book(self):return Book.parse('X',{'orderbook_fp':{'yes_dollars':[['.39','12.8'],['.38','10']], 'no_dollars':[['.59','8.2'],['.58','20']]}},T)
    def test_complement_price_and_size(self):self.assertEqual(self.book().asks('YES'),((4100,8),(4200,20)))
    def test_no_side_complement(self):self.assertEqual(self.book().asks('NO')[0],(6100,12))
    def test_crossed_books_rejected(self):
        with self.assertRaises(ValueError):Book.parse('X',{'orderbook_fp':{'yes_dollars':[['.60','10']],'no_dollars':[['.50','10']]}},T)
    def test_unknown_book_schema_rejected(self):
        with self.assertRaises(ValueError):Book.parse('X',{'orderbook':{'yes':[[40,10]]}},T)
    def test_empty_books_no_fill(self):
        b=Book.parse('X',{'orderbook_fp':{}},T)
        self.assertIsNone(b.mid());self.assertEqual(walk(b,'YES',10,Fee('quadratic','1',T),True).qty,0)
    def test_depth_cap_partial_fill(self):
        f=walk(self.book(),'YES',20,Fee('quadratic','1',T),True,100,.25)
        self.assertEqual(f.qty,7);self.assertEqual(f.gross,2*4200+5*4300)
    def test_sell_uses_bid_not_ask(self):
        f=walk(self.book(),'YES',2,Fee('quadratic','1',T),False,100,.25)
        self.assertEqual(f.gross,2*3800);self.assertEqual(f.cash,7000)
    def test_unprofitable_fee_exceeding_exit_is_not_free(self):
        b=Book('X',T,((200,100),),((9700,100),))
        self.assertEqual(walk(b,'YES',10,Fee('quadratic','1',T),False).qty,0)
    def test_invalid_side(self):
        with self.assertRaises(ValueError):self.book().asks('MAYBE')
    def test_duplicate_levels_merged(self):
        b=Book.parse('X',{'orderbook_fp':{'yes_dollars':[['.4','5'],['.4','7']]}},T)
        self.assertEqual(b.yes_bids,((4000,12),))
    def test_negative_depth_rejected(self):
        with self.assertRaises(ValueError):Book.parse('X',{'orderbook_fp':{'yes_dollars':[['.4','-1']]}},T)
    def test_live_mode_rejected(self):
        with self.assertRaises(ValueError):validate({'execution':'live'})
    def test_unsafe_event_risk_rejected(self):
        with self.assertRaises(ValueError):validate({'max_event_risk_fraction':.5})
    def test_unknown_config_rejected(self):
        with self.assertRaises(ValueError):validate({'api_key':'test'})
    def test_fractional_interval_rejected(self):
        with self.assertRaises(ValueError):validate({'scan_seconds':60.5})
    def test_fingerprint_excludes_port_not_strategy(self):
        c=validate({})
        self.assertEqual(fingerprint(c),fingerprint({**c,'port':8766}))
        self.assertNotEqual(fingerprint(c),fingerprint({**c,'min_edge_usd':.05}))
    def test_nan_config_rejected(self):
        with self.assertRaises(ValueError):validate({'min_volume':float('nan')})
    def raw(self):return {'ticker':'T','event_ticker':'E','market_type':'binary','close_time':'2026-10-09T00:00:00Z','status':'active','rules_primary':'YES when metric above threshold','notional_value_dollars':'1.0000','volume_fp':'500'}
    def test_market_rules_required(self):
        raw=self.raw();del raw['rules_primary']
        with self.assertRaises(ValueError):Market.parse(raw)
    def test_market_non_binary_rejected(self):
        raw=self.raw();raw['market_type']='scalar'
        with self.assertRaises(ValueError):Market.parse(raw)
    def test_market_wrong_notional_rejected(self):
        raw=self.raw();raw['notional_value_dollars']='100'
        with self.assertRaises(ValueError):Market.parse(raw)
    def test_market_settlement_scalar_conflict_rejected(self):
        raw={**self.raw(),'status':'finalized','result':'yes','settlement_value_dollars':'.5'}
        with self.assertRaises(ValueError):Market.parse(raw)
    def test_rule_changes_change_hash(self):
        raw=self.raw();a=Market.parse(raw);raw['rules_primary']='Different threshold'
        self.assertNotEqual(a.rules_hash,Market.parse(raw).rules_hash)
    def test_quote_change_does_not_change_rule_hash(self):
        raw=self.raw();a=Market.parse(raw);raw['yes_bid_dollars']='.7'
        self.assertEqual(a.rules_hash,Market.parse(raw).rules_hash)
    def test_provisional_market_not_active(self):
        m=Market.parse({**self.raw(),'is_provisional':True})
        self.assertFalse(m.active(T))
