"""Pool lifecycle and late dependency binding after the persistence split."""
from concurrent.futures import ThreadPoolExecutor
import subprocess
import sys
import time
from unittest.mock import Mock

import pytest
from data import connection, data_manager as dm
from data.repositories import accounts, portfolios, trades
from data.repository_context import RepositoryContext


def test_pool_is_shared_by_facade_and_connection_module_under_concurrency(monkeypatch):
    monkeypatch.setattr(connection, "_connection_pool", None)
    monkeypatch.setenv("SUPABASE_URL", "postgresql://test-only")
    shared = Mock()
    def construct(*args):
        time.sleep(.01)  # Give the other callers time to contend on initialization.
        return shared
    factory = Mock(side_effect=construct)
    monkeypatch.setattr(connection.pool, "ThreadedConnectionPool", factory)
    readers = [dm.get_connection_pool, connection.get_connection_pool] * 8
    with ThreadPoolExecutor(max_workers=8) as workers:
        results = list(workers.map(lambda reader: reader(), readers))
    assert all(result is shared for result in results)
    factory.assert_called_once_with(1, 20, "postgresql://test-only")


def test_missing_connection_configuration_does_not_create_pool(monkeypatch):
    monkeypatch.setattr(connection, "_connection_pool", None)
    monkeypatch.setattr(connection, "SUPABASE_URL", "")
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    factory = Mock()
    monkeypatch.setattr(connection.pool, "ThreadedConnectionPool", factory)
    with pytest.raises(ValueError, match="SUPABASE_URL"):
        dm.get_connection_pool()
    factory.assert_not_called()


def test_lease_uses_facade_pool_override_and_returns_once(monkeypatch):
    pool = Mock()
    raw = Mock()
    pool.getconn.return_value = raw
    monkeypatch.setattr(dm, "get_connection_pool", Mock(return_value=pool))
    with dm.get_connection() as lease:
        assert lease.conn is raw
        lease.cursor(cursor_factory="synthetic")
        lease.commit()
    lease.close()
    raw.cursor.assert_called_once_with(cursor_factory="synthetic")
    raw.commit.assert_called_once_with()
    raw.close.assert_not_called()
    pool.putconn.assert_called_once_with(raw)


@pytest.mark.parametrize("rollback_fails", [False, True])
def test_exception_returns_lease_even_when_rollback_fails(rollback_fails):
    pool, raw = Mock(), Mock()
    if rollback_fails:
        raw.rollback.side_effect = RuntimeError("rollback unavailable")
    with pytest.raises(ValueError, match="operation failed"):
        with connection.PoolConnectionWrapper(pool, raw):
            raise ValueError("operation failed")
    raw.rollback.assert_called_once_with()
    pool.putconn.assert_called_once_with(raw)


def test_facade_reads_use_current_connection_override(monkeypatch):
    first, second = Mock(), Mock()
    first.cursor.return_value.fetchall.return_value = [{"id": "first"}]
    second.cursor.return_value.fetchall.return_value = [{"id": "second"}]
    monkeypatch.setattr(dm, "get_connection", Mock(return_value=first))
    assert dm.get_all_accounts("p") == [{"id": "first"}]
    monkeypatch.setattr(dm, "get_connection", Mock(return_value=second))
    assert dm.get_all_accounts("p") == [{"id": "second"}]
    first.close.assert_called_once_with()
    second.close.assert_called_once_with()


def test_repository_can_use_explicit_io_without_global_facade(monkeypatch):
    global_io = Mock(side_effect=AssertionError("global DB must not be used"))
    monkeypatch.setattr(dm, "get_connection", global_io)
    conn = Mock()
    conn.cursor.return_value.fetchall.return_value = [{"id": "local"}]
    context = RepositoryContext(Mock(return_value=conn), Mock(), Mock())
    assert accounts.get_all_accounts(context, "local-p") == [{"id": "local"}]
    global_io.assert_not_called()
    context.connect.assert_called_once_with()
    assert conn.cursor.return_value.execute.call_args.args[1] == ("local-p",)
    conn.close.assert_called_once_with()


def test_failed_account_write_rolls_back_and_returns_connection():
    conn = Mock()
    conn.cursor.return_value.execute.side_effect = RuntimeError("injected write failure")
    context = RepositoryContext(Mock(return_value=conn), lambda: "synthetic-id", Mock())
    assert accounts.add_account(context, "QA", "Synthetic", "ISA") == (False, "injected write failure")
    conn.commit.assert_not_called()
    conn.rollback.assert_called_once_with()
    conn.close.assert_called_once_with()


def test_invalid_portfolio_does_not_rent_connection():
    context = RepositoryContext(Mock(), Mock(), Mock())
    assert not portfolios.create_portfolio(context, " ")[0]
    assert not portfolios.delete_portfolio(context, "default")[0]
    context.connect.assert_not_called()


def test_invalid_trade_does_not_read_exchange_rate_or_database():
    context = RepositoryContext(Mock(), Mock(), Mock(), Mock())
    assert not trades.execute_trade(context, "2026-10-05", "a", "x", "BUY", 0, 100, "USD")[0]
    context.connect.assert_not_called()
    context.exchange_rate.assert_not_called()


def test_exchange_rate_dependency_is_bound_when_needed(monkeypatch):
    from backend.services import market_service
    monkeypatch.setattr(market_service, "usd_krw", 1450)
    context = dm._context()
    assert context.exchange_rate() == 1450
    monkeypatch.setattr(market_service, "usd_krw", 1500)
    assert context.exchange_rate() == 1500
    monkeypatch.setattr(market_service, "usd_krw", 0)
    assert context.exchange_rate() == 1380


def test_fresh_persistence_import_does_not_connect_or_initialize():
    source = '''
import psycopg2
from psycopg2 import pool
def blocked(*args, **kwargs):
    raise AssertionError("import attempted database IO")
psycopg2.connect = blocked
pool.ThreadedConnectionPool = blocked
from data import data_manager, connection, schema
assert connection._connection_pool is None
assert data_manager.get_connection_pool is connection.get_connection_pool
'''
    # The environment inherits conftest's disabled file config/credentials.
    result = subprocess.run([sys.executable, "-c", source], capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
