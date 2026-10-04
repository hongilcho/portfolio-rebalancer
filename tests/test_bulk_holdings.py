"""Query-count, portfolio-scope and asset-default regression checks."""
import copy
from unittest.mock import Mock

import pytest

from data import data_manager as dm
from backend.routers import holdings as router


@pytest.fixture
def database(monkeypatch):
    cursor = Mock()
    conn = Mock()
    conn.cursor.return_value = cursor
    connection = Mock(return_value=conn)
    monkeypatch.setattr(dm, "get_connection", connection)
    return connection, conn, cursor


def test_raw_holdings_use_one_scoped_query(database):
    connection, conn, cursor = database
    row = dict(account_id="selected", asset_id="us", quantity=1.25,
               avg_price=140000, original_avg_price=145000)
    cursor.fetchall.return_value = [row]
    assert dm.get_all_holdings("portfolio") == [row]
    connection.assert_called_once_with()
    cursor.execute.assert_called_once()
    sql, params = cursor.execute.call_args.args
    assert "WHERE acc.portfolio_id = %s" in sql
    assert params == ("portfolio",)
    assert "trade_history" not in sql
    conn.commit.assert_not_called()
    conn.close.assert_called_once_with()


def test_unfiltered_holdings_remain_backward_compatible(database):
    _, conn, cursor = database
    cursor.fetchall.return_value = []
    assert dm.get_all_holdings() == []
    assert len(cursor.execute.call_args.args) == 1
    assert "WHERE" not in cursor.execute.call_args.args[0]
    conn.close.assert_called_once_with()


def test_holdings_endpoint_forwards_portfolio_scope(monkeypatch):
    reader = Mock(return_value=[{"quantity": 1.25}])
    monkeypatch.setattr(router, "get_all_holdings", reader)
    assert router.get_all_holdings_list("selected") == {"holdings": [{"quantity": 1.25}]}
    reader.assert_called_once_with(portfolio_id="selected")


def test_rebalance_uses_one_snapshot_and_matches_normal_asset_reader(database):
    connection, conn, cursor = database
    asset = dict(id="a", allowed_accounts='["first", "second"]',
                 is_active=None, lock_rebalance_sell=None, include_in_rebalance=None,
                 tax_rate=None, deposit_principal="125000.5", is_dividend_cost_deduct=1)
    cursor.fetchall.return_value = [copy.deepcopy(asset)]
    expected_assets = dm.get_all_assets("selected")
    cursor.reset_mock()
    conn.reset_mock()
    connection.reset_mock()
    holdings = [dict(account_id="second", asset_id="a", quantity=1.25, avg_price=100),
                dict(account_id="first", asset_id="a", quantity=3, avg_price=200)]
    cursor.fetchone.return_value = (dict(
        accounts=[{"id": "first"}, {"id": "second"}],
        assets=[copy.deepcopy(asset)], holdings=holdings),)
    result = dm.get_rebalance_batch_data("selected")
    assert result['assets'] == expected_assets
    assert result['assets'][0]['allowed_accounts'] == ["first", "second"]
    assert result['assets'][0]['tax_rate'] == 15.4
    assert result['assets'][0]['lock_rebalance_sell'] is True
    assert result['holdings'] == [holdings[1], holdings[0]]
    connection.assert_called_once_with()
    cursor.execute.assert_called_once()
    sql, params = cursor.execute.call_args.args
    assert sql.count("portfolio_id = %s") == 3
    assert params == ("selected",) * 3
    assert "trade_history" not in sql
    conn.commit.assert_not_called()
    conn.close.assert_called_once_with()


def test_empty_rebalance_snapshot(database):
    _, _, cursor = database
    cursor.fetchone.return_value = ({"assets": [], "accounts": [], "holdings": []},)
    assert dm.get_rebalance_batch_data("empty") == dict(assets=[], accounts=[], holdings=[])


def test_connection_returns_to_pool_on_query_failure(database):
    _, conn, cursor = database
    cursor.execute.side_effect = RuntimeError("query failed")
    with pytest.raises(RuntimeError, match="query failed"):
        dm.get_rebalance_batch_data("selected")
    conn.close.assert_called_once_with()
