"""
총수익(Total Return) 기반 배당금 집계 및 평단가 보존 단위 테스트
================================================================
MTS 원본 매입단가(avg_price) 100% 보존, 전 종목 자동 배당 수집 및
계좌 유형별(일반 15.4%, ISA/IRP 0%) 세후 배당금 반영,
시세평가손익(eval_profit) + 배당수익(dividend_profit) = 총손익(Total Return) 집계를 검증합니다.
"""

import pytest
from logic.dividend_fetcher import calculate_adjusted_holding_prices
from backend.routers.dashboard import get_dashboard_summary


def test_calculate_adjusted_holding_prices_preserves_avg_price(mocker):
    """배당 발생 시에도 MTS 평단가가 차감되지 않고 100% 보존되는지 검증"""
    mock_dividends = [
        {"date": "2024-03-15", "amount": 100.0},
        {"date": "2024-06-15", "amount": 100.0}
    ]
    mocker.patch("logic.dividend_fetcher.fetch_dividend_history", return_value=mock_dividends)

    holding = {
        "ticker": "069500",
        "market": "KR",
        "avg_price": 30000.0,
        "avg_price_usd": 0.0,
        "first_buy_date": "2024-01-01"
    }
    asset_meta = {"name": "KODEX 200", "ticker": "069500"}

    # 1. 일반 계좌: 15.4% 배당소득세 차감
    res_general = calculate_adjusted_holding_prices(holding, asset_meta, usd_krw=1350.0, account_type="GENERAL")
    assert res_general["avg_price"] == 30000.0  # 평단가 보존!
    assert res_general["dividend_count"] == 2
    # 총 배당 200원 - 15.4% = 169.2원
    assert pytest.approx(res_general["cumulative_dividend"], 0.01) == 169.2

    # 2. ISA 계좌: 비과세/과세이연 (0% 원천징수)
    res_isa = calculate_adjusted_holding_prices(holding, asset_meta, usd_krw=1350.0, account_type="ISA")
    assert res_isa["avg_price"] == 30000.0  # 평단가 보존!
    assert res_isa["dividend_count"] == 2
    # 세금 공제 없이 전액 200원 반영
    assert pytest.approx(res_isa["cumulative_dividend"], 0.01) == 200.0


def test_dashboard_total_return_metrics(mocker):
    """대시보드 KPI 및 개별 종목에서 Total Return = 시세손익 + 배당손익이 정확히 계산되는지 검증"""
    mock_accounts = [
        {
            "id": "acc-1",
            "account_no": "111-222",
            "account_alias": "일반위탁",
            "account_type": "GENERAL",
            "deposit_krw": 500000.0,
            "deposit_usd": 0.0,
            "annual_limit": 0.0,
            "tax_limit": 0.0,
            "is_limit_exhausted": False,
            "priority": 1,
            "portfolio_id": "default"
        }
    ]

    mock_assets = [
        {
            "id": "ast-kr",
            "name": "KODEX 머니마켓액티브",
            "ticker": "488770",
            "market": "KR",
            "is_risk_asset": False,
            "target_weight": 50.0,
            "is_active": True,
            "include_in_rebalance": True,
            "portfolio_id": "default"
        },
        {
            "id": "ast-us",
            "name": "SGOV",
            "ticker": "SGOV",
            "market": "US",
            "is_risk_asset": False,
            "target_weight": 50.0,
            "is_active": True,
            "include_in_rebalance": True,
            "portfolio_id": "default"
        }
    ]

    mock_holdings = [
        {
            "asset_id": "ast-kr",
            "account_id": "acc-1",
            "asset_name": "KODEX 머니마켓액티브",
            "ticker": "488770",
            "market": "KR",
            "is_risk_asset": False,
            "quantity": 10.0,
            "avg_price": 100000.0,
            "avg_price_usd": 0.0,
            "buy_fx_rate": 0.0,
            "first_buy_date": "2024-01-01"
        },
        {
            "asset_id": "ast-us",
            "account_id": "acc-1",
            "asset_name": "SGOV",
            "ticker": "SGOV",
            "market": "US",
            "is_risk_asset": False,
            "quantity": 10.0,
            "avg_price": 135000.0,
            "avg_price_usd": 100.0,
            "buy_fx_rate": 1350.0,
            "first_buy_date": "2024-01-01"
        }
    ]

    # Mock real-time prices:
    # KODEX: 현재가 101,000원 (+1,000원/주 시세차익)
    # SGOV: 현재가 $102 (+ $2/주 시세차익)
    mock_price_map = {
        "ast-kr": 101000.0,
        "ast-us": 102.0 * 1350.0
    }
    mock_price_usd_map = {
        "ast-us": 102.0
    }

    # Mock dividends:
    # KODEX: 주당 세후 500원 배당
    # SGOV: 주당 세후 $1.0 배당
    def mock_calc_adj(h, ast, fx, account_type="GENERAL"):
        is_us = (h.get("market") == "US" or ast.get("market") == "US")
        c_div = 1.0 if is_us else 500.0
        return {
            "avg_price": h["avg_price"],
            "avg_price_usd": h["avg_price_usd"],
            "cumulative_dividend": c_div,
            "dividend_count": 2,
            "first_buy_date": "2024-01-01",
            "buy_fx_rate": h.get("buy_fx_rate") or fx
        }
    mocker.patch("backend.routers.dashboard.calculate_adjusted_holding_prices", side_effect=mock_calc_adj)

    res = get_dashboard_summary(
        portfolio_id="default",
        accounts=mock_accounts,
        assets=mock_assets,
        all_holdings=mock_holdings,
        price_map=mock_price_map,
        usd_krw=1350.0
    )
    kpi = res["kpi"]
    stock_assets = res["stock_assets"]

    # 1. KODEX 머니마켓 검증
    kr_row = next(r for r in stock_assets if r["asset_id"] == "ast-kr")
    assert kr_row["avg_price"] == 100000.0  # 평단가 보존
    assert kr_row["current_price"] == 101000.0
    assert kr_row["eval_profit_krw"] == 10000.0  # 10주 * 1,000원 = 10,000원 시세손익
    assert kr_row["dividend_profit_krw"] == 5000.0  # 10주 * 500원 = 5,000원 배당수익
    assert kr_row["total_profit_krw"] == 15000.0  # 10,000 + 5,000 = 15,000원 총손익
    assert kr_row["total_profit_pct"] == 1.5  # 15,000 / 1,000,000 * 100 = 1.5%

    # 2. SGOV (US) 검증
    us_row = next(r for r in stock_assets if r["asset_id"] == "ast-us")
    assert us_row["avg_price_usd"] == 100.0  # 달러 평단가 보존
    assert us_row["current_price_usd"] == 102.0
    assert us_row["eval_profit_usd"] == 20.0  # 10주 * $2 = $20 시세손익
    assert us_row["dividend_profit_usd"] == 10.0  # 10주 * $1 = $10 배당수익
    assert us_row["total_profit_usd"] == 30.0  # $20 + $10 = $30 달러 총손익
    assert us_row["total_profit_pct_usd"] == 3.0  # $30 / $1000 * 100 = 3.0%

    # 3. 전체 KPI 집계 검증
    # total_stock_buy = 1,000,000 + 1,350,000 = 2,350,000원
    # total_eval_profit = 10,000 + (20 * 1350) = 37,000원
    # total_dividend_profit = 5,000 + (10 * 1350) = 18,500원
    # total_stock_profit = 37,000 + 18,500 = 55,500원
    assert kpi["total_eval_profit"] == 37000.0
    assert kpi["total_dividend_profit"] == 18500.0
    assert kpi["total_stock_profit"] == 55500.0
    assert kpi["usd_summary"]["stock_eval_profit_usd"] == 20.0
    assert kpi["usd_summary"]["stock_dividend_usd"] == 10.0
    assert kpi["usd_summary"]["stock_profit_usd"] == 30.0
