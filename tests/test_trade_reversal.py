"""Run production accounting SQL against an in-memory transactional database.

The adapter translates placeholders and removes PostgreSQL row-lock clauses.
It verifies real commit/rollback behavior, not PostgreSQL concurrency or DDL.
"""

import sqlite3
from decimal import Decimal
import pytest
from data import data_manager as dm
from backend.routers import trades as router
from logic.trade_accounting import replay_holding


def test_legacy_same_day_order_survives_arbitrary_migration_sequence():
    trades = [
        dict(id="b", trade_date="2026-01-01", trade_type="SELL", quantity=5,
             price=120, currency="KRW", trade_sequence=1),
        dict(id="a", trade_date="2026-01-01", trade_type="BUY", quantity=10,
             price=100, currency="KRW", trade_sequence=2),
    ]
    assert replay_holding(trades) == (5, 100, 0, 0)


class CursorAdapter:
    def __init__(self, db):
        self.db = db
        self.cursor = db.raw.cursor()

    def execute(self, sql, params=()):
        if self.db.fail_on and self.db.fail_on in sql:
            raise sqlite3.OperationalError("injected write failure")
        return self.cursor.execute(sql.replace('%s', '?').replace(' FOR UPDATE', ''),
                                   tuple(float(v) if isinstance(v, Decimal) else v for v in params))

    def fetchone(self):
        row = self.cursor.fetchone()
        return dict(row) if row is not None else None

    def fetchall(self):
        return [dict(row) for row in self.cursor.fetchall()]


class DatabaseAdapter:
    def __init__(self):
        self.raw = sqlite3.connect(':memory:', check_same_thread=False)
        self.raw.row_factory = sqlite3.Row
        self.fail_on = None
        self.raw.executescript('''
            CREATE TABLE accounts (id TEXT PRIMARY KEY, deposit_krw REAL, deposit_usd REAL);
            CREATE TABLE assets (id TEXT PRIMARY KEY, market TEXT);
            CREATE TABLE trade_history (
                trade_sequence INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE,
                trade_date TEXT, account_id TEXT, asset_id TEXT, trade_type TEXT,
                quantity REAL, price REAL, currency TEXT, exchange_rate REAL,
                cash_delta_krw REAL, cash_delta_usd REAL
            );
            CREATE TABLE holdings (
                id TEXT PRIMARY KEY, account_id TEXT, asset_id TEXT, quantity REAL,
                avg_price REAL, avg_price_usd REAL, buy_fx_rate REAL,
                original_avg_price REAL, original_avg_price_usd REAL,
                first_buy_date TEXT DEFAULT '', manual_dividend_override REAL,
                UNIQUE(account_id, asset_id)
            );
            INSERT INTO accounts VALUES ('acc', 1000000, 1000);
            INSERT INTO assets VALUES ('ast', 'KR');
            CREATE TABLE usd_cash_state (account_id TEXT PRIMARY KEY, usd_balance NUMERIC,
                cost_krw NUMERIC, last_event_date TEXT, started_at TEXT DEFAULT CURRENT_TIMESTAMP);
            CREATE TABLE usd_cash_events (sequence INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE,
                account_id TEXT, kind TEXT, occurred_at TEXT, event_date TEXT,
                recorded_at TEXT DEFAULT CURRENT_TIMESTAMP, usd_amount NUMERIC, krw_amount NUMERIC,
                fx_rate NUMERIC, cash_delta_krw REAL, cash_delta_usd REAL, trade_id TEXT UNIQUE,
                trade_reference TEXT, asset_id TEXT, before_state TEXT, after_state TEXT, notes TEXT,
                reversed_at TEXT);
            CREATE TABLE ledger_adjustments(id TEXT UNIQUE,sequence INTEGER PRIMARY KEY AUTOINCREMENT,portfolio_id TEXT,account_id TEXT,request_id TEXT,event_date TEXT,kind TEXT,reason TEXT,request TEXT,before_state TEXT,after_state TEXT,history TEXT,reviews TEXT DEFAULT '[]',trade_id TEXT,usd_event_id TEXT,created_at TEXT DEFAULT CURRENT_TIMESTAMP,reversed_at TEXT,UNIQUE(portfolio_id,request_id));
            CREATE TABLE nh_notice_items(id TEXT,linked_trade_id TEXT,linked_usd_event_id TEXT,reversed_at TEXT);
        ''')

    def cursor(self, **kwargs):
        return CursorAdapter(self)

    def commit(self):
        self.raw.commit()

    def rollback(self):
        self.raw.rollback()

    def close(self):
        pass  # Returning a connection to a pool must not discard the fixture.

    def rows(self, table):
        return [dict(row) for row in self.raw.execute(f'SELECT * FROM {table} ORDER BY id')]

    def state(self):
        return {table: self.rows(table) for table in ('accounts', 'holdings', 'trade_history')}

    def balances(self):
        row = self.rows('accounts')[0]
        return row['deposit_krw'], row['deposit_usd']

    def holding(self):
        rows = [h for h in self.rows('holdings') if h['quantity'] > 0]
        if not rows:
            return 0, 0, 0, 0
        row = rows[0]
        return tuple(row[k] for k in ('quantity', 'avg_price', 'avg_price_usd', 'buy_fx_rate'))


@pytest.fixture
def db(mocker):
    database = DatabaseAdapter()
    mocker.patch.object(dm, 'get_connection', return_value=database)
    yield database
    database.raw.close()


def record(db, kind, quantity=10, price=100, currency='KRW', fx=1, date='2026-01-02'):
    success, message = dm.execute_trade(date, 'acc', 'ast', kind, quantity, price, currency, fx)
    assert success, message
    return db.raw.execute('SELECT id FROM trade_history ORDER BY trade_sequence DESC LIMIT 1').fetchone()[0]


@pytest.mark.parametrize('currency,usd', [('KRW', 1000), ('USD', 1000), ('USD', 0)])
def test_buy_delete_round_trip_restores_cash_cost_and_nav(db, currency, usd):
    db.raw.execute('UPDATE accounts SET deposit_usd = ?', (usd,))
    if currency == 'USD' and usd == 0:
        db.raw.execute('UPDATE accounts SET deposit_krw = 2000000')
    db.commit()
    before = db.balances(), db.holding()
    nav_before = before[0][0] + before[0][1] * 1400
    trade_id = record(db, 'BUY', currency=currency, fx=1400)
    assert dm.delete_trade(trade_id)[0]
    assert (db.balances(), db.holding()) == before
    qty, _, _, _ = db.holding()
    assert db.balances()[0] + db.balances()[1] * 1400 + qty * 100 == nav_before
    assert not dm.delete_trade(trade_id)[0]  # No second cash reversal.


@pytest.mark.parametrize('currency,usd', [('KRW', 1000), ('USD', 1000), ('USD', 0)])
def test_sell_delete_round_trip_restores_original_cost_basis(db, currency, usd):
    db.raw.execute('UPDATE accounts SET deposit_usd = ?', (usd,))
    db.commit()
    record(db, 'INIT', currency=currency, fx=1300, date='2026-01-01')
    before = db.balances(), db.holding()
    trade_id = record(db, 'SELL', quantity=2, price=120, currency=currency, fx=1400)
    assert dm.delete_trade(trade_id)[0]
    assert db.balances() == before[0]
    assert db.holding() == pytest.approx(before[1])


def test_usd_purchase_spent_to_zero_restores_usd_not_krw(db):
    trade_id = record(db, 'BUY', currency='USD', fx=1400)
    assert db.balances() == (1000000, 0)
    row = db.rows('trade_history')[0]
    assert (row['cash_delta_krw'], row['cash_delta_usd']) == (0, -1000)
    assert dm.delete_trade(trade_id)[0]
    assert db.balances() == (1000000, 1000)


def test_sell_reversal_uses_recorded_currency_after_cash_changes(db):
    db.raw.execute('UPDATE accounts SET deposit_usd = 0')
    db.commit()
    record(db, 'INIT', currency='USD', fx=1300, date='2026-01-01')
    trade_id = record(db, 'SELL', quantity=2, currency='USD', fx=1400)
    db.raw.execute('UPDATE accounts SET deposit_usd = 100')
    db.commit()
    assert dm.delete_trade(trade_id)[0]
    assert db.balances() == (1000000, 100)


def test_buy_and_sell_can_be_deleted_together_in_any_request_order(db):
    record(db, 'INIT', quantity=10, date='2026-01-01')
    before = db.balances(), db.holding()
    buy_id = record(db, 'BUY', quantity=5)
    sell_id = record(db, 'SELL', quantity=12, date='2026-01-03')
    assert dm.delete_trades([sell_id, buy_id])[0]
    assert (db.balances(), db.holding()) == before


def test_deleting_buy_needed_by_later_sale_rolls_back_everything(db):
    buy_id = record(db, 'BUY')
    record(db, 'SELL', quantity=5, date='2026-01-03')
    before = db.state()
    success, message = dm.delete_trade(buy_id)
    assert not success
    assert '보유 수량' in message
    assert db.state() == before


def test_batch_write_failure_rolls_back_cash_history_and_holdings(db):
    record(db, 'INIT', date='2026-01-01')
    first = record(db, 'BUY', quantity=5)
    second = record(db, 'BUY', quantity=2, date='2026-01-03')
    before = db.state()
    db.fail_on = 'INSERT INTO holdings'
    assert not dm.delete_trades([first, second])[0]
    assert db.state() == before


def test_legacy_settlement_is_never_guessed(db):
    trade_id = record(db, 'BUY')
    db.raw.execute('UPDATE trade_history SET cash_delta_krw = NULL, cash_delta_usd = NULL')
    db.commit()
    before = db.state()
    success, message = dm.delete_trade(trade_id)
    assert not success
    assert '잔고 대사' in message
    assert db.state() == before


def test_legacy_init_has_no_cash_effect(db):
    trade_id = record(db, 'INIT')
    db.raw.execute('UPDATE trade_history SET cash_delta_krw = NULL, cash_delta_usd = NULL')
    db.commit()
    assert dm.delete_trade(trade_id)[0]
    assert db.balances() == (1000000, 1000)


def test_unknown_or_duplicate_id_does_not_partially_delete(db):
    trade_id = record(db, 'BUY')
    before = db.state()
    assert not dm.delete_trades([trade_id, 'missing'])[0]
    assert not dm.delete_trades([trade_id, trade_id])[0]
    assert db.state() == before


def test_oversell_and_insufficient_cash_never_commit(db):
    before = db.state()
    assert not dm.execute_trade('2026-01-01', 'acc', 'ast', 'SELL', 1, 100)[0]
    assert not dm.execute_trade('2026-01-01', 'acc', 'ast', 'BUY', 100000, 100)[0]
    assert db.state() == before


def test_replay_preserves_manual_dividend_and_first_buy_date(db):
    record(db, 'INIT', date='2026-01-01')
    db.raw.execute("UPDATE holdings SET first_buy_date = '2026-01-01', manual_dividend_override = 4321")
    db.commit()
    trade_id = record(db, 'BUY')
    assert dm.delete_trade(trade_id)[0]
    row = db.rows('holdings')[0]
    assert row['first_buy_date'] == '2026-01-01'
    assert row['manual_dividend_override'] == 4321


def test_same_day_replay_uses_recorded_sequence_not_random_uuid(db, mocker):
    mocker.patch.object(dm, 'generate_id', side_effect=['z-init', 'holding', 'z-buy', 'a-sell', 'last-buy', 'unused'])
    record(db, 'INIT', quantity=1, date='2026-01-01')
    record(db, 'BUY', quantity=10)
    record(db, 'SELL', quantity=5)
    trade_id = record(db, 'BUY', quantity=1, date='2026-01-03')
    assert dm.delete_trade(trade_id)[0]
    assert db.holding()[0] == 6


def test_batch_delete_http_failure_is_atomic(db):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(router.router)
    client = TestClient(app)
    trade_id = record(db, 'BUY')
    before = db.state()
    response = client.request('DELETE', '/api/trades/batch', json={'trade_ids': [trade_id, 'missing']})
    assert response.status_code == 400
    assert db.state() == before
    response = client.request('DELETE', '/api/trades/batch', json={'trade_ids': [trade_id]})
    assert response.status_code == 200
    assert response.json()['deleted_count'] == 1


def test_usd_weighted_average_and_deletion_use_production_accounting(db):
    db.raw.execute('UPDATE accounts SET deposit_krw = 10000000, deposit_usd = 5000')
    db.commit()
    record(db, 'BUY', currency='USD', fx=1300, date='2026-01-01')
    second = record(db, 'BUY', currency='USD', price=150, fx=1400)
    record(db, 'SELL', quantity=5, price=160, currency='USD', fx=1370, date='2026-01-03')
    assert db.holding() == pytest.approx((15, 170000, 125, 1360))
    qty, avg_krw, avg_usd, fx = db.holding()
    eval_profit = qty * (160 * 1380 - avg_krw)
    pure_profit = qty * (160 - avg_usd) * 1380
    fx_profit = qty * avg_usd * (1380 - fx)
    assert eval_profit == pytest.approx(pure_profit + fx_profit)
    assert eval_profit == 762000
    assert dm.delete_trade(second)[0]
    assert db.holding() == pytest.approx((5, 130000, 100, 1300))
    assert db.balances() == (10000000, 4800)
