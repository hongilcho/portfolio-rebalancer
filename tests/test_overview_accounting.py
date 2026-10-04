"""Regression tests use fixed quotes, synthetic holdings and no external IO."""

from copy import deepcopy
import pytest
from backend.routers import dashboard, portfolios, crypto


@pytest.fixture
def overview_data(mocker):
    batch = {
        "portfolios": [{"id": "default", "name": "Test", "description": "", "is_default": True}],
        "accounts": [{"id": "acc", "portfolio_id": "default", "account_no": "test",
                      "account_alias": "Test", "account_type": "ISA",
                      "deposit_krw": 1000000, "deposit_usd": 100}],
        "assets": [{"id": "ast", "portfolio_id": "default", "name": "Test ETF",
                    "ticker": "TEST", "market": "KR", "target_weight": 100}],
        "holdings": [{"account_id": "acc", "asset_id": "ast", "quantity": 10,
                      "avg_price": 100000, "original_avg_price": 100000,
                      "asset_name": "Test ETF", "ticker": "TEST", "market": "KR",
                      "first_buy_date": "2026-01-01"}],
        "trade_history": [{"id": "init", "account_id": "acc", "asset_id": "ast",
                           "trade_date": "2026-01-01", "trade_type": "INIT", "quantity": 10}],
        "crypto_holdings": [],
    }
    quotes = [{"id": "ast", "price_krw": 110000, "price_usd": 0}]
    dividends = [{"date": "2026-02-01", "amount": 5000}]
    mocker.patch.object(portfolios, "get_overview_batch_data", return_value=batch)
    mocker.patch.object(dashboard, "get_overview_batch_data", return_value=batch)
    mocker.patch.object(portfolios.market_service, "get_prices", side_effect=lambda **_: (
        quotes, {p["id"]: p["price_krw"] for p in quotes}
    ))
    mocker.patch.object(portfolios.market_service, "price_data", quotes)
    mocker.patch.object(portfolios.market_service, "usd_krw", 1400)
    mocker.patch("logic.dividend_fetcher.fetch_dividend_history", return_value=dividends)
    mocker.patch.object(portfolios, "get_crypto_prices", return_value={})
    crypto_result = {"crypto_total": {"total_buy": 10000, "total_eval": 12000,
                                     "total_profit": 2000, "total_profit_pct": 20},
                     "crypto_assets": [{"symbol": "BTC", "name": "BTC", "quantity": 1,
                                        "buy_amount": 10000, "eval_amount": 12000,
                                        "avg_price": 10000, "current_price": 12000}]}
    mocker.patch.object(portfolios, "get_crypto_summary", return_value=crypto_result)
    return batch, quotes, dividends


@pytest.mark.parametrize("include_crypto", [False, True])
def test_returns_exclude_cash_and_nav_never_adds_dividends(overview_data, include_crypto):
    result = portfolios.get_all_portfolios_overview(include_crypto=include_crypto)
    grand = result["grand_total"]
    assert grand["total_buy"] == 1000000 + (10000 if include_crypto else 0)
    assert grand["total_profit"] == 150000 + (2000 if include_crypto else 0)
    assert grand["dividend_profit"] == 50000
    assert grand["total_profit_pct"] == pytest.approx(grand["total_profit"] / grand["total_buy"] * 100)
    assert grand["total_eval"] == 2240000 + (12000 if include_crypto else 0)
    assert grand["krw_summary"]["cash_krw"] == 1000000
    assert grand["usd_summary"]["cash_usd"] == 100
    assert grand["krw_summary"]["total_eval_krw"] + grand["usd_summary"]["total_eval_usd"] * 1400 == grand["total_eval"]
    p = result["portfolios"][0]
    assert p["total_buy"] == 1000000
    assert p["total_profit_pct"] == 15
    assert p["total_eval"] == 2240000
    assert result["aggregated_assets"][0]["total_profit"] == 150000


def test_usd_cash_only_does_not_appear_in_krw_card(overview_data):
    batch, quotes, _ = overview_data
    batch["accounts"][0]["deposit_krw"] = 0
    batch["assets"].clear()
    batch["holdings"].clear()
    batch["trade_history"].clear()
    quotes.clear()
    grand = portfolios.get_all_portfolios_overview(include_crypto=False)["grand_total"]
    assert grand["krw_summary"]["cash_krw"] == 0
    assert grand["krw_summary"]["total_eval_krw"] == 0
    assert grand["usd_summary"]["total_eval_usd"] == 100
    assert grand["total_eval"] == 140000
    assert grand["total_buy"] == grand["total_profit_pct"] == 0


def test_currency_and_grand_returns_do_not_double_round_at_display_boundary(overview_data):
    grand = portfolios.get_all_portfolios_overview(include_crypto=True)["grand_total"]
    # 15.0495... must display as 15.0%, rather than rounding to 15.05 first
    # and then displaying 15.1% in the currency card for the same holdings.
    assert grand["krw_summary"]["stock_return_krw"] == grand["total_profit_pct"]
    assert grand["krw_summary"]["stock_return_krw"] < 15.05


def test_individual_rows_keep_same_return_precision_as_overview(overview_data):
    _, quotes, _ = overview_data
    quotes[0]["price_krw"] = 110049.5
    individual = dashboard.get_dashboard_bundle()["dashboard"]
    overview = portfolios.get_all_portfolios_overview(include_crypto=False)
    expected = overview["grand_total"]["total_profit_pct"]
    assert expected == pytest.approx(15.0495)
    assert individual["kpi"]["total_stock_return"] == expected
    assert individual["stock_assets"][0]["profit_pct"] == expected
    assert overview["aggregated_assets"][0]["total_profit_pct"] == expected


@pytest.mark.parametrize("manual_override", [None, 4321])
def test_history_dividends_match_individual_and_overview(overview_data, mocker, manual_override):
    batch, quotes, dividends = overview_data
    h = batch["holdings"][0]
    h.update(quantity=78, avg_price=100, original_avg_price=100,
             manual_dividend_override=manual_override)
    batch["trade_history"][0]["quantity"] = 33
    batch["trade_history"].append({"id": "buy", "account_id": "acc", "asset_id": "ast",
                                  "trade_date": "2026-02-15", "trade_type": "BUY", "quantity": 45})
    dividends[:] = [{"date": "2026-02-01", "amount": 83}, {"date": "2026-03-01", "amount": 30}]
    quotes[0]["price_krw"] = 110
    batch_reader = mocker.spy(portfolios, "get_overview_batch_data")
    individual = dashboard.get_dashboard_bundle()["dashboard"]
    overview = portfolios.get_all_portfolios_overview(include_crypto=False)
    expected = 5079 if manual_override is None else manual_override
    assert individual["kpi"]["total_dividend_profit"] == expected
    assert overview["grand_total"]["dividend_profit"] == expected
    aggregated = overview["aggregated_assets"][0]
    assert aggregated["total_dividend_profit"] == expected
    assert aggregated["total_profit"] == individual["kpi"]["total_stock_profit"]
    distribution = aggregated["distribution"][0]
    assert distribution["profit_krw"] == individual["stock_assets"][0]["profit_krw"]
    assert distribution["dividend_profit_krw"] == expected
    assert individual["stock_assets"][0]["avg_price"] == 100
    # One overview batch, not one database lookup per portfolio or holding.
    assert batch_reader.call_count == 1


def test_usd_total_return_keeps_fx_and_stock_profit_separate(overview_data):
    batch, quotes, dividends = overview_data
    batch["assets"][0]["market"] = "US"
    batch["holdings"][0].update(market="US", avg_price=130000,
        original_avg_price=130000, avg_price_usd=100, original_avg_price_usd=100, buy_fx_rate=1300)
    quotes[0].update(price_krw=154000, price_usd=110)
    dividends[0]["amount"] = 5
    grand = portfolios.get_all_portfolios_overview(include_crypto=False)["grand_total"]
    usd = grand["usd_summary"]
    assert usd["stock_profit_usd"] == 150
    assert usd["stock_return_usd"] == 15
    assert usd["stock_dividend_usd"] == 50
    assert usd["pure_stock_profit_krw"] == 140000
    assert usd["total_fx_profit_krw"] == 100000
    assert grand["total_profit"] == 310000
    assert grand["total_buy"] == 1300000
    assert grand["total_eval"] == grand["krw_summary"]["total_eval_krw"] + usd["total_eval_usd"] * 1400
    individual = dashboard.get_dashboard_bundle()["dashboard"]["kpi"]
    assert usd["stock_profit_usd"] == individual["usd_summary"]["stock_profit_usd"]
    assert grand["total_profit"] == individual["total_stock_profit"]


def test_multiple_portfolios_and_partial_sales_use_their_own_history(overview_data):
    batch, quotes, _ = overview_data
    for key in ("portfolios", "accounts", "assets", "holdings", "trade_history"):
        extra = deepcopy(batch[key][0])
        if "id" in extra:
            extra["id"] += "2"
        if "portfolio_id" in extra:
            extra["portfolio_id"] = "default2"
        if "account_id" in extra:
            extra["account_id"] = "acc2"
        if "asset_id" in extra:
            extra["asset_id"] = "ast2"
        batch[key].append(extra)
    batch["holdings"][1]["quantity"] = 5
    batch["trade_history"].append({"id": "sell", "account_id": "acc2", "asset_id": "ast2",
                                  "trade_date": "2026-01-15", "trade_type": "SELL", "quantity": 5})
    quotes.append({"id": "ast2", "price_krw": 110000, "price_usd": 0})
    result = portfolios.get_all_portfolios_overview(include_crypto=False)
    assert result["grand_total"]["dividend_profit"] == 75000
    assert result["grand_total"]["total_buy"] == 1500000
    assert result["grand_total"]["total_profit_pct"] == 15
    assert result["aggregated_assets"][0]["total_dividend_profit"] == 75000
    assert [d["dividend_profit_krw"] for d in result["aggregated_assets"][0]["distribution"]] == [50000, 25000]


def test_crypto_combined_return_excludes_portfolio_cash(overview_data, mocker):
    individual = dashboard.get_dashboard_bundle()["dashboard"]
    mocker.patch.object(crypto, "get_dashboard_summary", return_value=individual)
    mocker.patch.object(crypto, "get_portfolio", return_value={"name": "Test"})
    result = crypto.get_crypto_summary(include_portfolio=True, db_holdings=[], prices_map={
        "BTC": {"price": 100000000}, "ETH": {"price": 5000000},
    })
    assert result["combined_summary"]["total_buy"] == 1000000
    assert result["combined_summary"]["total_profit_pct"] == 15


def test_http_endpoints_have_the_same_return_definition(overview_data):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    app = FastAPI()
    app.include_router(dashboard.router)
    app.include_router(portfolios.router)
    client = TestClient(app)
    individual = client.get('/api/dashboard/bundle').json()['dashboard']['kpi']
    response = client.get('/api/portfolios/overview/summary?include_crypto=false')
    assert response.status_code == 200
    grand = response.json()['grand_total']
    assert grand['total_profit_pct'] == individual['total_stock_return'] == 15


def test_usd_computation_uses_the_returned_quote_snapshot(overview_data, mocker):
    batch, quotes, dividends = overview_data
    batch['assets'][0]['market'] = 'US'
    batch['holdings'][0].update(market='US', avg_price=140000,
        original_avg_price=140000, avg_price_usd=100, original_avg_price_usd=100, buy_fx_rate=1400)
    quotes[0].update(price_krw=154000, price_usd=110)
    dividends[0]['amount'] = 5
    # A cache replaced by another refresh must not supply the USD valuation.
    mocker.patch.object(portfolios.market_service, 'price_data', [{'id': 'ast', 'price_usd': 999}])
    grand = portfolios.get_all_portfolios_overview(include_crypto=False)['grand_total']
    individual = dashboard.get_dashboard_bundle()['dashboard']['kpi']
    assert grand['usd_summary']['stock_eval_usd'] == 1100
    assert individual['usd_summary']['stock_eval_usd'] == 1100
