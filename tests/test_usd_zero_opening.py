"""Zero-USD first conversions run production SQL on isolated in-memory cash only."""
from copy import deepcopy
from datetime import date

import pytest
from backend.routers.forex import CashEvent
from data.repositories import forex, nh_notices, trades
from test_nh_notices import db, row, payload, NoticeCursor


@pytest.fixture
def empty_usd(db):
    db.raw.execute('DELETE FROM usd_cash_state')
    db.raw.execute('UPDATE accounts SET deposit_krw=1000000,deposit_usd=0')
    db.commit()
    return db


def request(db, mode, usd=100, krw=140001, request_id='zero-exchange-1', day='2026-01-02'):
    if mode == 'notice':
        return payload(db, [row('EXCHANGE_IN', usd_amount=usd, krw_amount=krw).model_copy(
            update={'event_date':date.fromisoformat(day)})], request_id)
    return CashEvent(request_id=request_id, portfolio_id='p', kind='EXCHANGE_IN',
        occurred_at=day+'T09:00:00+09:00', usd_amount=usd, krw_amount=krw).model_dump(mode='json')


def commit(db, mode, body):
    return nh_notices.commit(db.ctx,'p',body) if mode == 'notice' else forex.record_manual_event(db.ctx,'acc',body)


def undo(db, mode, result):
    if mode == 'notice':
        assert nh_notices.undo(db.ctx,'p',result['batch_id'])['reversed']
    else:
        ok,message=forex.undo_event(db.ctx,'acc',result['event_id'])
        assert ok,message


def snapshot(db):
    return deepcopy({name:[NoticeCursor.decode(dict(r)) for r in db.raw.execute('SELECT * FROM '+name+' ORDER BY rowid')] for name in ('accounts','holdings','trade_history',
        'usd_cash_state','usd_cash_events','performance_flows','bookkeeping_requests',
        'nh_notice_batches','nh_notice_items')})


@pytest.mark.parametrize('mode',['manual','notice'])
def test_first_exchange_preserves_holdings_uses_actual_spend_retries_and_undoes(empty_usd,mode):
    db=empty_usd
    db.raw.execute("UPDATE assets SET market='US'");db.commit()
    ok,message=trades.execute_trade(db.ctx,'2026-01-01','acc','ast','INIT',5,100,'USD',1250)
    assert ok,message
    old=snapshot(db)
    body=request(db,mode)
    result=commit(db,mode,body)
    assert db.balances()==(859999,100)
    state=db.rows('usd_cash_state')[0]
    assert state['cost_krw']==140001 and state['usd_balance']==100
    events=snapshot(db)['usd_cash_events']
    assert len(events)==1 and events[0]['kind']=='EXCHANGE_IN'
    assert events[0]['fx_rate']==pytest.approx(1400.01)
    assert events[0]['before_state'] is None
    assert events[0]['after_state']['opening_holdings']==old['holdings']
    assert (events[0]['occurred_at'] is None) == (mode == 'notice')
    assert db.rows('holdings')==old['holdings'] and db.rows('trade_history')==old['trade_history']
    assert db.rows('performance_flows')==old['performance_flows']
    posted=snapshot(db)
    assert commit(db,mode,body)==result and snapshot(db)==posted
    ok,message=trades.delete_trades(db.ctx,[old['trade_history'][0]['id']])
    assert not ok and '시작 이전' in message
    undo(db,mode,result)
    assert db.balances()==(1000000,0) and not db.rows('usd_cash_state')
    assert db.rows('holdings')==old['holdings'] and db.rows('trade_history')==old['trade_history']
    assert db.rows('usd_cash_events')[0]['reversed_at']
    undone=snapshot(db)
    if mode == 'notice':
        with pytest.raises(ValueError,match='취소된 요청'):commit(db,mode,body)
    else:
        commit(db,mode,body)  # An old retry must never reapply a cancelled conversion.
    assert snapshot(db)==undone


@pytest.mark.parametrize('mode',['manual','notice'])
@pytest.mark.parametrize('usd',[10,0.00000001,-1])
def test_missing_cost_with_nonzero_cash_stays_blocked(empty_usd,mode,usd):
    db=empty_usd
    db.raw.execute('UPDATE accounts SET deposit_usd=?',(usd,));db.commit()
    old=snapshot(db)
    with pytest.raises(ValueError,match='시작 기준환율'):commit(db,mode,request(db,mode))
    assert snapshot(db)==old


@pytest.mark.parametrize('mode',['manual','notice'])
@pytest.mark.parametrize('starting_usd',[0,10])
def test_existing_opening_and_prior_exchange_are_never_reinitialized(empty_usd,mode,starting_usd):
    db=empty_usd
    db.raw.execute('UPDATE accounts SET deposit_usd=?',(starting_usd,));db.commit()
    opening=CashEvent(request_id='existing-opening-1',portfolio_id='p',kind='OPENING',
        occurred_at='2026-01-01T09:00:00+09:00',rate=1300).model_dump(mode='json')
    forex.record_manual_event(db.ctx,'acc',opening)
    prior=forex.record_manual_event(db.ctx,'acc',request(db,'manual',usd=20,krw=27000,request_id='prior-exchange-1'))
    if starting_usd==0:
        # Return the cash pool to zero while preserving its established start/history.
        out=CashEvent(request_id='prior-out-1',portfolio_id='p',kind='EXCHANGE_OUT',
            occurred_at='2026-01-02T09:00:00+09:00',usd_amount=20,krw_amount=27000).model_dump(mode='json')
        forex.record_manual_event(db.ctx,'acc',out)
    old=snapshot(db)
    result=commit(db,mode,request(db,mode))
    state=db.rows('usd_cash_state')[0]
    assert state['cost_krw']==old['usd_cash_state'][0]['cost_krw']+140001
    assert state['usd_balance']==old['usd_cash_state'][0]['usd_balance']+100
    assert state['started_at']==old['usd_cash_state'][0]['started_at']
    for event in old['usd_cash_events']:assert event in snapshot(db)['usd_cash_events']
    undo(db,mode,result)
    assert db.rows('usd_cash_state')==old['usd_cash_state'] and db.balances()==(
        old['accounts'][0]['deposit_krw'],old['accounts'][0]['deposit_usd'])
    for event in old['usd_cash_events']:assert event in snapshot(db)['usd_cash_events']
    assert prior['event_id'] in [event['id'] for event in db.rows('usd_cash_events')]


@pytest.mark.parametrize('mode',['manual','notice'])
def test_existing_cost_drift_is_still_rejected(empty_usd,mode):
    db=empty_usd
    db.raw.execute("INSERT INTO usd_cash_state(account_id,usd_balance,cost_krw,last_event_date) VALUES('acc',10,13000,'2026-01-01')");db.commit()
    old=snapshot(db)
    with pytest.raises(ValueError,match='원가 기록'):commit(db,mode,request(db,mode))
    assert snapshot(db)==old


@pytest.mark.parametrize('mode',['manual','notice'])
@pytest.mark.parametrize('failure',['INSERT INTO usd_cash_state','UPDATE accounts SET deposit_krw','INSERT INTO usd_cash_events'])
def test_first_exchange_failure_rolls_back_start_cash_and_receipts(empty_usd,mode,failure):
    db=empty_usd;old=snapshot(db);db.fail_on=failure
    with pytest.raises(Exception,match='injected write failure'):commit(db,mode,request(db,mode))
    assert snapshot(db)==old


@pytest.mark.parametrize('mode',['manual','notice'])
@pytest.mark.parametrize('usd,krw',[(0,140000),(100,0),(100,1000001)])
def test_invalid_or_unfunded_first_exchange_leaves_no_start(empty_usd,mode,usd,krw):
    db=empty_usd;old=snapshot(db)
    with pytest.raises(ValueError):commit(db,mode,request(db,mode,usd,krw))
    assert snapshot(db)==old


def test_two_first_notice_exchanges_accumulate_and_batch_undo_removes_start(empty_usd):
    db=empty_usd
    body=payload(db,[row('EXCHANGE_IN',usd_amount=100,krw_amount=140000),
        row('EXCHANGE_IN',usd_amount=50,krw_amount=75000).model_copy(update={'fingerprint':'c'*64})])
    result=commit(db,'notice',body)
    assert db.balances()==(785000,150)
    assert db.rows('usd_cash_state')[0]['cost_krw']==215000
    assert len(db.rows('usd_cash_events'))==2
    undo(db,'notice',result)
    assert db.balances()==(1000000,0) and not db.rows('usd_cash_state')
    assert all(event['reversed_at'] for event in db.rows('usd_cash_events'))


def test_later_notice_failure_rolls_back_first_conversion_and_start(empty_usd):
    db=empty_usd;old=snapshot(db)
    body=payload(db,[row('EXCHANGE_IN',usd_amount=100,krw_amount=140000),
        row('EXCHANGE_IN',usd_amount=1000,krw_amount=1400000).model_copy(update={'fingerprint':'c'*64})])
    with pytest.raises(ValueError,match='부족'):commit(db,'notice',body)
    assert snapshot(db)==old


def test_first_manual_exchange_waits_for_later_event_undo(empty_usd):
    db=empty_usd
    first=commit(db,'manual',request(db,'manual'))
    second=commit(db,'manual',request(db,'manual',usd=50,krw=75000,request_id='second-exchange-1'))
    posted=snapshot(db)
    ok,message=forex.undo_event(db.ctx,'acc',first['event_id'])
    assert not ok and '가장 최근' in message and snapshot(db)==posted
    undo(db,'manual',second);undo(db,'manual',first)
    assert db.balances()==(1000000,0) and not db.rows('usd_cash_state')


def test_missing_state_cannot_restart_over_live_events(empty_usd):
    db=empty_usd
    commit(db,'manual',request(db,'manual'))
    db.raw.execute('DELETE FROM usd_cash_state');db.raw.execute('UPDATE accounts SET deposit_usd=0');db.commit()
    old=snapshot(db)
    with pytest.raises(ValueError,match='기존 달러 기록'):commit(db,'manual',request(db,'manual',request_id='broken-start-1'))
    assert snapshot(db)==old
