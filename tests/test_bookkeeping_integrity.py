"""Production accounting on synthetic data, including lost-response retries."""
from copy import deepcopy
import json
import pytest
from fastapi import HTTPException
from data import data_manager as dm
from data.repositories import trades, forex, assets, accounts, performance, deposits, nh_notices
from backend.routers.trades import BatchTradeRequest
from backend.routers.forex import CashEvent
from backend.routers.deposits import Entry
from test_nh_notices import db


@pytest.fixture
def book(db):
    db.raw.execute('UPDATE accounts SET deposit_krw=1000000');db.commit()
    for name,definition in {
        'name':"TEXT DEFAULT 'QA ETF'",'target_weight':'REAL DEFAULT 0',
        'is_risk_asset':'BOOLEAN DEFAULT 1','is_active':'BOOLEAN DEFAULT 1','notes':"TEXT DEFAULT ''",
        'deposit_principal':'REAL DEFAULT 0','interest_rate':'REAL DEFAULT 0',
        'start_date':"TEXT DEFAULT ''",'maturity_date':"TEXT DEFAULT ''",
        'early_termination_rate':'REAL DEFAULT 0','tax_rate':'REAL DEFAULT 15.4',
        'lock_rebalance_sell':'BOOLEAN DEFAULT 1','account_no':"TEXT DEFAULT ''",
        'include_in_rebalance':'BOOLEAN DEFAULT 1','is_dividend_cost_deduct':'BOOLEAN DEFAULT 0',
    }.items():db.raw.execute(f'ALTER TABLE assets ADD COLUMN {name} {definition}')
    db.commit();return db


def batch(**changes):
    row=dict(account_id='acc',asset_id='ast',trade_type='BUY',quantity=1,price=100,currency='KRW')
    request=dict(request_id='manual-trade-1',portfolio_id='p',trade_date='2026-01-02',trades=[row])
    request.update(changes)
    return BatchTradeRequest(**request).model_dump(mode='json')


def fx(kind='EXCHANGE_IN',**changes):
    request=dict(request_id='manual-fx-1',portfolio_id='p',kind=kind,occurred_at='2026-01-02T09:00:00+09:00',
        usd_amount=10,krw_amount=13000,rate=1300,notes='QA')
    request.update(changes)
    return CashEvent(**request).model_dump(mode='json')


def test_manual_retry_returns_original_receipt_and_only_one_trade(book):
    request=batch();first=trades.execute_batch(book.ctx,request);before=deepcopy(book.state())
    assert trades.execute_batch(book.ctx,request)==first
    assert book.state()==before and len(book.rows('trade_history'))==1
    changed=deepcopy(request);changed['trades'][0]['quantity']=2
    with pytest.raises(ValueError,match='변경'):trades.execute_batch(book.ctx,changed)
    assert book.state()==before


def test_manual_batch_failure_has_no_partial_cash_history_or_receipt(book):
    request=batch();request['trades'].append({**request['trades'][0],'quantity':1000000})
    before=book.state()
    with pytest.raises(ValueError,match='모두 미반영'):trades.execute_batch(book.ctx,request)
    assert book.state()==before
    assert not book.raw.execute('SELECT * FROM bookkeeping_requests').fetchall()


@pytest.mark.parametrize('change',[dict(currency='USD'),dict(asset_id='unknown'),dict(account_id='unknown')])
def test_manual_validation_rejects_wrong_currency_missing_scope(book,change):
    request=batch();request['trades'][0].update(change);before=book.state()
    with pytest.raises(ValueError):trades.execute_batch(book.ctx,request)
    assert book.state()==before


@pytest.mark.parametrize('sql',["UPDATE assets SET portfolio_id='other'","UPDATE assets SET allowed_accounts='[]'","UPDATE assets SET is_deposit=1"])
def test_manual_validation_matches_notice_scope(book,sql):
    book.raw.execute(sql);book.commit();before=book.state()
    with pytest.raises(ValueError):trades.execute_batch(book.ctx,batch())
    assert book.state()==before


def test_backdated_buy_replays_average_in_actual_date_order(book):
    for day,kind,price in [('2026-01-01','BUY',100),('2026-01-03','SELL',300),('2026-01-02','BUY',200)]:
        ok,message=trades.execute_trade(book.ctx,day,'acc','ast',kind,1,price,'KRW',1)
        assert ok,message
    assert book.holding()[:2]==(1,150)
    assert book.balances()[0]==1000000


def test_unknown_seeded_holding_cannot_be_erased_by_trade_cancellation(book):
    book.raw.execute("INSERT INTO holdings(id,account_id,asset_id,quantity,avg_price,original_avg_price) VALUES('seed','acc','ast',7,200,200)");book.commit()
    assert trades.execute_trade(book.ctx,'2026-01-02','acc','ast','BUY',1,100,'KRW',1)[0]
    before=book.state()
    ok,message=trades.delete_trades(book.ctx,[book.rows('trade_history')[0]['id']])
    assert not ok and '복원' in message and book.state()==before


def test_canceled_manual_receipt_retry_never_recreates_trade(book):
    request=batch();result=trades.execute_batch(book.ctx,request)
    assert trades.delete_trades(book.ctx,result['trade_ids'])[0]
    cash=book.balances()
    result=trades.execute_batch(book.ctx,request)
    assert '취소' in result['message'] and not book.rows('trade_history') and book.balances()==cash


def test_manual_fx_retry_and_undo_are_idempotent(book):
    request=fx();result=forex.record_manual_event(book.ctx,'acc',request)
    cash=book.balances()
    assert forex.record_manual_event(book.ctx,'acc',request)==result
    assert book.balances()==cash
    assert forex.undo_event(book.ctx,'acc',result['event_id'])[0]
    assert forex.undo_event(book.ctx,'acc',result['event_id'])[0]
    assert forex.record_manual_event(book.ctx,'acc',request)['reversed']
    assert book.balances()==(1000000,10)


def test_external_usd_cash_cost_and_performance_are_one_reversible_entry(book):
    before=book.balances();request=fx('DEPOSIT');result=forex.record_manual_event(book.ctx,'acc',request)
    assert book.balances()==(before[0],20)
    flow=next(f for f in book.rows('performance_flows') if f['id']==result['flow_id'])
    assert flow['amount_krw']==13000 and flow['native_amount']==10
    with pytest.raises(ValueError,match='함께 취소'):performance.void_flow(book.ctx,'p',flow['id'],True)
    assert forex.undo_event(book.ctx,'acc',result['event_id'])[0]
    assert book.balances()==before
    assert next(f for f in book.rows('performance_flows') if f['id']==flow['id'])['voided']
    with pytest.raises(ValueError,match='함께 취소'):performance.void_flow(book.ctx,'p',flow['id'],False)


def test_failed_performance_write_rolls_back_usd_cash_cost_and_receipt(book):
    book.fail_on='INSERT INTO performance_flows';before=book.balances();old=book.rows('usd_cash_state')
    with pytest.raises(Exception):forex.record_manual_event(book.ctx,'acc',fx('DEPOSIT'))
    assert book.balances()==before and book.rows('usd_cash_state')==old and not book.rows('usd_cash_events')
    assert not book.raw.execute('SELECT * FROM bookkeeping_requests').fetchall()


def test_income_does_not_become_external_investment_flow(book):
    before=len(book.rows('performance_flows'))
    result=forex.record_manual_event(book.ctx,'acc',fx('DEPOSIT',flow_mode='INCOME'))
    assert result['flow_id'] is None and len(book.rows('performance_flows'))==before
    assert book.balances()[1]==20


def test_negative_cash_can_be_repaired_by_a_real_deposit_notice(book):
    from backend.routers.nh_notices import Batch,Row
    book.raw.execute('UPDATE accounts SET deposit_krw=-10000');book.commit()
    request=Batch(request_id='repair-negative-1',confirmed=True,
        expected_cash={'acc':{'deposit_krw':-10000,'deposit_usd':10}},
        rows=[Row(kind='DEPOSIT',account_id='acc',event_date='2026-01-02',krw_amount=20000,duplicate_confirmed=True)])
    nh_notices.commit(book.ctx,'p',request.model_dump(mode='json'))
    assert book.balances()[0]==10000


def test_settings_cannot_delete_an_account_balance_or_asset_history(book):
    before=book.state()
    assert not accounts.delete_account(book.ctx,'acc')[0]
    assert book.state()==before
    trades.execute_batch(book.ctx,batch());before=book.state()
    assert not assets.delete_asset(book.ctx,'ast')[0]
    assert book.state()==before


def contract(**changes):
    config=dict(name='QA deposit',ticker='DEP-QA',deposit_principal=1000000,interest_rate=3,
                start_date='2026-01-01',maturity_date='2027-01-01')
    config.update(changes)
    return Entry(request_id='deposit-entry-1',asset_id='qa-deposit',reason='QA contract correction',
                 confirmed=True,asset=config).model_dump(mode='json')


def test_deposit_registration_correction_and_undo_preserve_receipts(book):
    request=contract();first=deposits.save(book.ctx,'p',request)
    assert deposits.save(book.ctx,'p',request)==first
    assert book.raw.execute("SELECT deposit_principal FROM assets WHERE id='qa-deposit'").fetchone()[0]==1000000
    change=contract(deposit_principal=900000);change['request_id']='deposit-entry-2'
    deposits.save(book.ctx,'p',change)
    with pytest.raises(ValueError,match='후속'):deposits.undo(book.ctx,'p','qa-deposit',request['request_id'])
    deposits.undo(book.ctx,'p','qa-deposit',change['request_id'])
    assert book.raw.execute("SELECT deposit_principal FROM assets WHERE id='qa-deposit'").fetchone()[0]==1000000
    deposits.undo(book.ctx,'p','qa-deposit',request['request_id'])
    assert book.raw.execute("SELECT deposit_principal FROM assets WHERE id='qa-deposit'").fetchone()[0]==0
    assert len(book.raw.execute('SELECT * FROM bookkeeping_requests').fetchall())==2


def test_settings_cannot_change_deposit_contract(book):
    result=deposits.save(book.ctx,'p',contract())
    allowed={'name','ticker','market','target_weight','allowed_accounts','is_risk_asset','is_active','notes',
        'is_deposit','deposit_principal','interest_rate','start_date','maturity_date','early_termination_rate',
        'tax_rate','lock_rebalance_sell','account_no','include_in_rebalance','is_dividend_cost_deduct'}
    fields={k:v for k,v in result['after'].items() if k in allowed};fields['deposit_principal']=2000000
    ok,message=assets.update_asset(book.ctx,'qa-deposit',**fields)
    assert not ok and '5번 탭' in message
    assert book.raw.execute("SELECT deposit_principal FROM assets WHERE id='qa-deposit'").fetchone()[0]==1000000


def test_untracked_portfolio_accepts_initial_usd_cash_before_a_positive_baseline(book):
    book.raw.execute("DELETE FROM performance_flows");book.raw.execute('DELETE FROM performance_tracking');book.commit()
    result=forex.record_manual_event(book.ctx,'acc',fx('DEPOSIT'))
    assert result['flow_id'] is None and result['performance_not_started']
    assert book.balances()[1]==20
    assert forex.undo_event(book.ctx,'acc',result['event_id'])[0]


def test_existing_usd_flow_can_be_linked_without_becoming_a_second_contribution(book):
    book.raw.execute("INSERT INTO performance_flows(id,portfolio_id,account_id,request_id,event_date,amount_krw,currency,native_amount,exchange_rate) VALUES('existing-usd','p','acc','old-usd','2026-01-02',13000,'USD',10,1300)");book.commit()
    before=len(book.rows('performance_flows'))
    request=fx('DEPOSIT',flow_mode='ALREADY_RECORDED',existing_flow_id='existing-usd')
    result=forex.record_manual_event(book.ctx,'acc',request)
    assert result['flow_id']=='existing-usd' and not result['created_flow']
    assert len(book.rows('performance_flows'))==before
    assert forex.undo_event(book.ctx,'acc',result['event_id'])[0]
    assert not next(r for r in book.rows('performance_flows') if r['id']=='existing-usd')['voided']
    request['request_id']='relink-existing-2'
    assert forex.record_manual_event(book.ctx,'acc',request)['flow_id']=='existing-usd'


def test_distinct_same_amount_usd_deposit_requires_explicit_duplicate_confirmation(book):
    forex.record_manual_event(book.ctx,'acc',fx('DEPOSIT'))
    request=fx('DEPOSIT',request_id='separate-usd-2')
    before=book.balances()
    with pytest.raises(ValueError,match='별도 실제'):forex.record_manual_event(book.ctx,'acc',request)
    assert book.balances()==before
    request['duplicate_confirmed']=True
    forex.record_manual_event(book.ctx,'acc',request)
    assert book.balances()[1]==30


def test_startup_deposit_cleanup_is_read_only_and_does_not_rent_a_connection():
    from data import schema
    class Guard:
        def connect(self):raise AssertionError('startup cleanup attempted IO')
    schema.clean_deposit_shadow_accounts(Guard())
