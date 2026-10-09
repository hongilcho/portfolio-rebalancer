"""Imported order identity must commit/rollback with holdings and cash."""
import pytest
from data import data_manager as dm
from backend.routers import trades as router
from test_trade_reversal import DatabaseAdapter

@pytest.fixture
def db(mocker):
    database = DatabaseAdapter()
    database.raw.executescript('''



        ALTER TABLE assets ADD COLUMN ticker TEXT DEFAULT '0085P0';

        ALTER TABLE trade_history ADD COLUMN import_source TEXT;
        ALTER TABLE trade_history ADD COLUMN broker_order_no TEXT;
        CREATE UNIQUE INDEX trade_import_order ON trade_history(account_id,trade_date,import_source,broker_order_no)
            WHERE import_source IS NOT NULL AND broker_order_no IS NOT NULL;
    ''')
    mocker.patch.object(dm, 'get_connection', return_value=database)
    yield database
    database.raw.close()

def record(**changes):
    fields = dict(trade_date='2026-10-05',account_id='acc',asset_id='ast',trade_type='BUY',
                  quantity=1,price=9320,currency='KRW',exchange_rate=1,
                  import_source='NAMUH_KAKAO',broker_order_no='42954')
    fields.update(changes)
    return dm.execute_trade(**fields)

def test_repeated_order_and_changed_payload_cannot_double_charge(db):
    assert record()[0]
    original = db.state()
    for fields in ({}, {'quantity':10}, {'price':10000}):
        result, message = record(**fields)
        assert not result and '이미' in message
        assert db.state() == original
    assert db.rows('trade_history')[0]['broker_order_no'] == '42954'

def test_import_identity_and_all_cash_holdings_roll_back_on_write_failure(db):
    before = db.state()
    db.fail_on = 'INSERT INTO holdings'
    assert not record()[0]
    assert db.state() == before
    db.fail_on = None
    assert record()[0]

@pytest.mark.parametrize('changes', [dict(currency='USD'),dict(trade_type='SELL'),dict(import_source='UNKNOWN'),
    dict(broker_order_no=''),dict(import_source=None),dict(quantity=1.5),dict(trade_date='bad-date')])
def test_invalid_imports_do_not_change_ledger(db, changes):
    before = db.state()
    assert not record(**changes)[0]
    assert db.state() == before

def test_import_enforces_domestic_account_asset_scope(db):
    for update in ("UPDATE assets SET market='US'", "UPDATE assets SET is_deposit=1", "UPDATE assets SET portfolio_id='other'", "UPDATE assets SET allowed_accounts='[]'"):
        db.raw.execute(update); db.commit()
        before = db.state()
        assert not record()[0]
        assert db.state() == before
        db.raw.execute("UPDATE assets SET market='KR',is_deposit=0,portfolio_id='p',allowed_accounts='[\"acc\"]'"); db.commit()

def test_distinct_orders_batch_retry_only_registers_missing_orders(db):
    items = [router.TradeBatchItem(account_id='acc',asset_id='ast',trade_type='BUY',quantity=1,price=9320,
        currency='KRW',exchange_rate=1,import_source='NAMUH_KAKAO',broker_order_no=order) for order in ('42954','42955')]
    request = router.BatchTradeRequest(request_id='import-retry-1',portfolio_id='p',trade_date='2026-10-05',trades=items)
    assert router.execute_batch_trades(request)['success_count'] == 2
    before = db.state()
    assert router.execute_batch_trades(request)['success_count'] == 2
    assert db.state() == before

def test_explicit_delete_reverses_import_and_allows_corrected_re_registration(db):
    before = db.balances()
    assert record()[0]
    trade_id = db.rows('trade_history')[0]['id']
    assert dm.delete_trade(trade_id)[0]
    assert db.balances() == before
    assert record()[0]
