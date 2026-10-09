"""Real transactional accounting with synthetic cash; PG locks checked separately."""
from copy import deepcopy
from decimal import Decimal
import csv
import io
import json
import zipfile

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from data import data_manager as dm
from backend.routers import forex as router
from logic.usd_cost import average, spend, receive
from test_trade_reversal import DatabaseAdapter


@pytest.fixture
def ledger_db(mocker):
    database = DatabaseAdapter()
    database.raw.execute("UPDATE assets SET market='US'")
    database.raw.execute('UPDATE accounts SET deposit_krw=5000000, deposit_usd=400')
    database.commit()
    mocker.patch.object(dm, 'get_connection', return_value=database)
    yield database
    database.raw.close()


def event(db, kind, **kwargs):
    ok, message = dm.record_usd_event('acc', kind, '2026-01-02T09:00:00+09:00', **kwargs)
    assert ok, message
    return db.raw.execute('SELECT id FROM usd_cash_events ORDER BY sequence DESC LIMIT 1').fetchone()[0]


def start(db):
    return event(db, 'OPENING', rate=1300, notes='마지막 환전 기준')


def state(db):
    row = db.raw.execute('SELECT * FROM usd_cash_state').fetchone()
    return dict(row) if row else None


def all_state(db):
    return deepcopy({**db.state(), 'cost': state(db), 'events': db.rows('usd_cash_events')})


def test_opening_preserves_existing_cost_and_cash(ledger_db):
    assert dm.execute_trade('2026-01-01', 'acc', 'ast', 'INIT', 5, 100, 'USD', 1250)[0]
    before = ledger_db.state()
    opening = start(ledger_db)
    assert ledger_db.state() == before
    assert state(ledger_db)['cost_krw'] == 520000
    opening_snapshot = json.loads(ledger_db.rows('usd_cash_events')[0]['after_state'])['opening_holdings']
    assert opening_snapshot == before['holdings']
    assert dm.undo_usd_event('acc', opening)[0]
    assert state(ledger_db) is None
    assert ledger_db.state() == before
    assert ledger_db.rows('usd_cash_events')[0]['reversed_at']


def test_exchange_buy_uses_cash_average_and_preserves_old_holding(ledger_db):
    assert dm.execute_trade('2026-01-01', 'acc', 'ast', 'INIT', 5, 100, 'USD', 1250)[0]
    start(ledger_db)
    fx_id = event(ledger_db, 'EXCHANGE_IN', usd_amount=600, krw_amount=840000)
    before = ledger_db.holding(), state(ledger_db)
    assert dm.execute_trade('2026-01-02', 'acc', 'ast', 'BUY', 7, 100, 'USD', 9999)[0]
    assert ledger_db.balances() == (4160000, 300)
    assert state(ledger_db)['cost_krw'] == pytest.approx(408000)
    assert average(state(ledger_db)['usd_balance'], state(ledger_db)['cost_krw']) == Decimal(1360)
    trade = ledger_db.rows('trade_history')[-1]
    trade = next(t for t in ledger_db.rows('trade_history') if t['trade_type']=='BUY')
    assert trade['exchange_rate'] == 1360  # client-supplied rate cannot override cash cost.
    assert ledger_db.holding() == pytest.approx((12, 1577000/12, 100, 1577000/1200))
    assert not dm.undo_usd_event('acc', fx_id)[0]  # newer buy must be undone first.
    assert dm.delete_trade(trade['id'])[0]
    assert ledger_db.holding() == before[0]
    assert state(ledger_db) == before[1]
    assert dm.undo_usd_event('acc', fx_id)[0]
    assert ledger_db.balances() == (5000000, 400)


def test_insufficient_usd_never_falls_back_to_krw(ledger_db):
    start(ledger_db)
    before = all_state(ledger_db)
    ok, message = dm.execute_trade('2026-01-02', 'acc', 'ast', 'BUY', 5, 100, 'USD', 1400)
    assert not ok and '달러 예수금이 부족' in message
    assert all_state(ledger_db) == before


def test_sell_proceeds_in_usd_even_at_zero_cash_and_undo_is_exact(ledger_db):
    start(ledger_db)
    assert dm.execute_trade('2026-01-02', 'acc', 'ast', 'BUY', 4, 100, 'USD', 1400)[0]
    before = all_state(ledger_db)
    assert state(ledger_db)['usd_balance'] == state(ledger_db)['cost_krw'] == 0
    assert dm.execute_trade('2026-01-02', 'acc', 'ast', 'SELL', 2, 120, 'USD', 1500)[0]
    assert ledger_db.balances() == (5000000, 240)
    assert state(ledger_db)['cost_krw'] == 360000
    latest = ledger_db.raw.execute('SELECT id FROM usd_cash_events ORDER BY sequence DESC LIMIT 1').fetchone()[0]
    assert dm.undo_usd_event('acc', latest)[0]
    assert ledger_db.state() == {key: before[key] for key in ('accounts', 'holdings', 'trade_history')}
    assert ledger_db.balances() == (5000000, 0)
    assert ledger_db.holding() == (4, 130000, 100, 1300)
    assert state(ledger_db) == before['cost']


def test_posting_failure_rolls_back_everything(ledger_db):
    start(ledger_db)
    before = all_state(ledger_db)
    ledger_db.fail_on = 'INSERT INTO usd_cash_events'
    assert not dm.execute_trade('2026-01-02', 'acc', 'ast', 'BUY', 1, 100, 'USD', 1400)[0]
    assert all_state(ledger_db) == before
    assert not dm.record_usd_event('acc', 'EXCHANGE_IN', '2026-01-02T10:00+09:00', 100, 140000)[0]
    assert all_state(ledger_db) == before


def test_balance_drift_is_not_guessed_and_reconcile_does_not_double_credit(ledger_db):
    start(ledger_db)
    ledger_db.raw.execute('UPDATE accounts SET deposit_usd=450')
    ledger_db.commit()
    before = all_state(ledger_db)
    assert not dm.execute_trade('2026-01-02', 'acc', 'ast', 'BUY', 1, 100, 'USD', 1400)[0]
    assert not dm.record_usd_event('acc', 'DEPOSIT', '2026-01-02T09:00+09:00', usd_amount=50, rate=1400)[0]
    assert all_state(ledger_db) == before
    event(ledger_db, 'RECONCILE', rate=1350)
    assert ledger_db.balances() == (5000000, 450)
    assert state(ledger_db)['cost_krw'] == 607500


def test_forex_out_and_cash_movements_keep_the_remaining_average(ledger_db):
    start(ledger_db)
    out = event(ledger_db, 'EXCHANGE_OUT', usd_amount=100, krw_amount=140000)
    assert ledger_db.balances() == (5140000, 300)
    assert state(ledger_db)['cost_krw'] == 390000
    assert dm.undo_usd_event('acc', out)[0]
    deposit = event(ledger_db, 'DEPOSIT', usd_amount=100, rate=1400)
    assert ledger_db.balances() == (5000000, 500)
    withdrawal = event(ledger_db, 'WITHDRAW', usd_amount=50)
    assert state(ledger_db)['cost_krw'] == 594000
    assert dm.undo_usd_event('acc', withdrawal)[0]
    assert dm.undo_usd_event('acc', deposit)[0]
    assert ledger_db.balances() == (5000000, 400)


def test_duplicate_opening_and_invalid_inputs_do_not_write(ledger_db):
    start(ledger_db)
    before = all_state(ledger_db)
    for kind, arguments in [('OPENING', dict(rate=1400)), ('EXCHANGE_IN', dict(usd_amount=0, krw_amount=100)),
                            ('EXCHANGE_IN', dict(usd_amount=1, krw_amount=float('nan'))),
                            ('DEPOSIT', dict(usd_amount=1, rate=-1))]:
        assert not dm.record_usd_event('acc', kind, '2026-01-02T09:00+09:00', **arguments)[0]
        assert all_state(ledger_db) == before
    assert not dm.record_usd_event('acc', 'EXCHANGE_IN', '2025-01-01T09:00+09:00', 1, 1400)[0]
    assert not dm.record_usd_event('acc', 'EXCHANGE_IN', '2099-01-01T09:00+09:00', 1, 1400)[0]
    assert all_state(ledger_db) == before


def test_old_us_records_and_manual_holding_edits_are_protected(ledger_db):
    assert dm.execute_trade('2026-01-01', 'acc', 'ast', 'INIT', 1, 100, 'USD', 1300)[0]
    old = ledger_db.rows('trade_history')[0]['id']
    start(ledger_db)
    before = all_state(ledger_db)
    assert not dm.delete_trade(old)[0]
    assert not dm.execute_trade('2026-01-02', 'acc', 'ast', 'BUY', 1, 100, 'KRW', 1)[0]
    assert not dm.save_account_holdings('acc', [dict(asset_id='ast', quantity=10, avg_price=140000)])[0]
    assert all_state(ledger_db) == before


def test_batch_undo_latest_us_trades_in_any_requested_order(ledger_db):
    start(ledger_db)
    before = ledger_db.state(), state(ledger_db)
    for quantity in (1, 2):
        assert dm.execute_trade('2026-01-02', 'acc', 'ast', 'BUY', quantity, 100, 'USD', 1400)[0]
    ids = [t['id'] for t in ledger_db.rows('trade_history')]
    assert dm.delete_trades(ids)[0]
    assert state(ledger_db) == before[1]
    assert ledger_db.balances() == (5000000, 400)
    assert ledger_db.holding() == (0, 0, 0, 0)


def test_http_validation_and_error_messages(ledger_db):
    app = FastAPI()
    app.include_router(router.router)
    client = TestClient(app)
    body = dict(request_id='opening-retry-1',portfolio_id='p',kind='OPENING', occurred_at='2026-01-02T09:00:00+09:00', rate=1300)
    response = client.post('/api/forex/acc/events', json=body)
    assert response.status_code == 200
    assert client.post('/api/forex/acc/events', json=body).status_code == 200
    assert client.post('/api/forex/acc/events', json={**body, 'rate': -1}).status_code == 422
    records = client.get('/api/forex/acc/events').json()['events']
    assert records[0]['kind'] == 'OPENING'
    assert client.delete('/api/forex/acc/events/' + records[0]['id']).status_code == 200


def test_later_cash_event_blocks_batch_trade_deletion_atomically(ledger_db):
    start(ledger_db)
    for quantity in (1, 1):
        assert dm.execute_trade('2026-01-02', 'acc', 'ast', 'BUY', quantity, 100, 'USD', None)[0]
    event(ledger_db, 'DEPOSIT', usd_amount=20, rate=1500)
    before = all_state(ledger_db)
    assert not dm.delete_trades([t['id'] for t in ledger_db.rows('trade_history')])[0]
    assert all_state(ledger_db) == before


def test_repeated_undo_cannot_reverse_twice(ledger_db):
    start(ledger_db)
    latest = event(ledger_db, 'EXCHANGE_IN', usd_amount=100, krw_amount=140000)
    assert dm.undo_usd_event('acc', latest)[0]
    before = all_state(ledger_db)
    assert not dm.undo_usd_event('acc', latest)[0]
    assert all_state(ledger_db) == before


def test_sell_requires_explicit_receipt_rate_and_kr_assets_cannot_spend_usd(ledger_db):
    start(ledger_db)
    assert dm.execute_trade('2026-01-02', 'acc', 'ast', 'BUY', 1, 100, 'USD', None)[0]
    before = all_state(ledger_db)
    assert not dm.execute_trade('2026-01-02', 'acc', 'ast', 'SELL', 1, 100, 'USD', None)[0]
    assert all_state(ledger_db) == before
    ledger_db.raw.execute("INSERT INTO assets(id,market) VALUES ('kr','KR')")
    ledger_db.commit()
    assert not dm.execute_trade('2026-01-02', 'acc', 'kr', 'BUY', 1, 100, 'USD', 1300)[0]
    assert all_state(ledger_db) == before


def test_failed_manual_batch_is_atomic_and_safe_to_correct(ledger_db):
    from backend.routers.trades import BatchTradeRequest, execute_batch_trades
    from fastapi import HTTPException
    start(ledger_db)
    before=all_state(ledger_db)
    request=BatchTradeRequest(request_id='manual-failed-1',portfolio_id='p',trade_date='2026-01-02',trades=[
        dict(account_id='acc',asset_id='ast',trade_type='BUY',quantity=3,price=100,currency='USD'),
        dict(account_id='acc',asset_id='ast',trade_type='BUY',quantity=3,price=100,currency='USD')])
    with pytest.raises(HTTPException) as error:
        execute_batch_trades(request)
    assert '모두 미반영' in error.value.detail
    assert all_state(ledger_db)==before
    assert ledger_db.raw.execute('SELECT COUNT(*) FROM bookkeeping_requests').fetchone()[0]==0



def test_csv_export_preserves_journal_json_and_canceled_events(mocker):
    from backend.routers import market
    for name in ('get_all_accounts', 'get_all_assets', 'get_all_holdings', 'get_trade_history'):
        mocker.patch.object(market, name, return_value=[])
    mocker.patch.object(market, 'get_usd_ledgers', return_value=[dict(account_id='acc', usd_balance='400', cost_krw='520000')])
    mocker.patch.object(market, 'get_usd_events', return_value=[dict(id='event', reversed_at='2026-01-03',
        before_state=None, after_state=dict(usd_balance='400', cost_krw='520000', opening_holdings=[dict(asset_id='VT', quantity=5)]))])
    archive = zipfile.ZipFile(io.BytesIO(market.export_csv_backup().body))
    assert set(archive.namelist()) == {'usd_cash_state.csv', 'usd_cash_events.csv'}
    records = list(csv.DictReader(io.StringIO(archive.read('usd_cash_events.csv').decode('utf-8-sig'))))
    assert records[0]['reversed_at'] == '2026-01-03'
    assert json.loads(records[0]['after_state'])['opening_holdings'][0]['quantity'] == 5
    assert json.loads(records[0]['before_state']) is None
