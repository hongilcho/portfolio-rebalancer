"""Differential tests against the unchanged pre-refactor dividend function."""
from copy import deepcopy
from datetime import date,timedelta
import importlib.util
from pathlib import Path
import random
from unittest.mock import patch
from logic.dividend_calculator import calculate_holding_dividends_from_history
from logic.dividend_quantity import DividendHistoryContext,DividendQuantityIndex
from logic.holding_history import history

spec=importlib.util.spec_from_file_location('legacy_dividend_history',Path(__file__).parent/'fixtures/legacy_dividend_history.py')
legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)


def cases():
    rng=random.Random(271828)
    for case in range(300):
        trades=[]
        for i in range(rng.randrange(0,120)):
            day=(date(2026,1,1)+timedelta(days=rng.randrange(65))).isoformat()
            trades.append(dict(id=f'{case}-{i}',account_id='a',asset_id='s',trade_date=day,
                trade_type=rng.choice(['INIT','BUY','SELL','OTHER']),quantity=rng.choice([0,.1,.25,1,3,7.123456789]),
                trade_sequence=i,cash_delta_krw=None if i%3==0 else 0,cash_delta_usd=0))
        dividends=[dict(date=(date(2026,1,1)+timedelta(days=rng.randrange(95))).isoformat(),amount=rng.random()*2)
                   for _ in range(rng.randrange(0,70))]
        yield trades,dividends,rng.choice(['','2026-02-01']),rng.choice([0,.15,.154]),rng.choice([True,False])


def test_randomized_results_and_input_order_match_exactly():
    for trades,dividends,start,tax,is_us in cases():
        before=deepcopy((trades,dividends))
        expected=legacy.calculate_holding_dividends_from_history(trades,dividends,start,tax,is_us)
        actual=calculate_holding_dividends_from_history(trades,dividends,start,tax,is_us)
        assert actual==expected
        assert (trades,dividends)==before


def test_same_day_init_is_end_of_day_not_an_extra_purchase_and_future_trades_do_not_change_prior_dividends():
    rows=[dict(id='a',trade_date='2026-10-01',trade_type='BUY',quantity=3),
          dict(id='b',trade_date='2026-10-02',trade_type='INIT',quantity=10),
          dict(id='c',trade_date='2026-10-02',trade_type='BUY',quantity=7),
          dict(id='d',trade_date='2026-10-04',trade_type='INIT',quantity=99)]
    index=DividendQuantityIndex(rows)
    assert index.before('2026-10-02')==3
    assert index.before('2026-10-03')==10
    assert index.before('2026-10-04')==10
    assert index.before('2026-10-05')==99


def test_context_reuses_one_index_per_source_and_pair_without_cross_source_or_account_leaks():
    rows=[dict(id='t',account_id='a',asset_id='s',trade_date='2026-10-01',trade_type='BUY',quantity=5)]
    ctx=DividendHistoryContext()
    assert ctx.index(rows,'a','s') is ctx.index(rows,'a','s')
    assert ctx.index(rows,'b','s').before('2026-10-02')==0
    other=deepcopy(rows);other[0]['quantity']=9
    assert ctx.index(other,'a','s').before('2026-10-02')==9
    assert ctx.index(rows,'a','s').before('2026-10-02')==5


def test_a_multiday_history_reuses_one_dividend_index_and_preserves_frozen_books():
    from test_holding_history_reconstruction import fixture,snapshot
    ledger,trades,_=fixture()
    trades=[{**trades[0],'trade_type':'BUY'}]
    ledger['dividend_cache']['div_KR_QATEST']['data']=[{'date':'2026-10-01','amount':1}]
    rows=[snapshot(ledger,(date(2026,10,5)+timedelta(days=i)).isoformat()) for i in range(16)]
    before=deepcopy((rows,trades))
    with patch('logic.dividend_quantity.DividendQuantityIndex',wraps=DividendQuantityIndex) as build:
        result=history(rows,[],['qa'],scope='qa',reconstruction={'trade_history':trades})
    assert build.call_count==1
    assert len(result['rows'])>=16
    assert all(r['status']=='COMPLETE' and r['profit_krw']==187 for r in result['rows'] if r['date'] in {r['snapshot_date'] for r in rows})
    assert (rows,trades)==before
