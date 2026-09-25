"""
통화 표시 전환(KRW / USD) 및 듀얼 통화 요약 집계 단위 테스트
================================================================
미국 주식 자산의 순수 달러($) 환산 지표 산출과
대시보드 및 전체 자산 통합 요약의 듀얼 통화(USD/KRW) 집계를 검증합니다.
"""

import pytest
from backend.routers.dashboard import get_dashboard_summary
from backend.routers.portfolios import get_all_portfolios_overview


def test_dashboard_summary_usd_metrics(mocker):
    """대시보드 요약 API에서 미국 주식의 달러 지표 및 듀얼 통화 KPI가 올바르게 반환되는지 검증"""
    # 1. Mock accounts
    mock_accounts = [
        {
            "id": "acc-1",
            "account_no": "111-222",
            "account_alias": "해외위탁",
            "account_type": "GENERAL",
            "deposit_krw": 1000000.0,
            "deposit_usd": 500.0,
            "annual_limit": 0.0,
            "tax_limit": 0.0,
            "is_limit_exhausted": False,
            "portfolio_id": "p-1"
        }
    ]

    # 2. Mock assets (1 US stock, 1 KR stock)
    mock_assets = [
        {
            "id": "ast-us",
            "name": "뱅가드 토탈월드스탁(VT)",
            "ticker": "VT",
            "market": "US",
            "is_risk_asset": True,
            "target_weight": 50.0,
            "is_active": True,
            "include_in_rebalance": True,
            "portfolio_id": "p-1"
        },
        {
            "id": "ast-kr",
            "name": "KODEX 200",
            "ticker": "069500",
            "market": "KR",
            "is_risk_asset": True,
            "target_weight": 50.0,
            "is_active": True,
            "include_in_rebalance": True,
            "portfolio_id": "p-1"
        }
    ]

    # 3. Mock holdings
    # VT: 10주 @ 200,000 KRW 평단 (환율 1000원 가정 시 $200 평단)
    # KODEX 200: 50주 @ 30,000 KRW 평단
    mock_holdings = [
        {
            "id": "h-1",
            "account_id": "acc-1",
            "asset_id": "ast-us",
            "asset_name": "뱅가드 토탈월드스탁(VT)",
            "ticker": "VT",
            "market": "US",
            "quantity": 10.0,
            "avg_price": 200000.0,
            "is_risk_asset": True
        },
        {
            "id": "h-2",
            "account_id": "acc-1",
            "asset_id": "ast-kr",
            "asset_name": "KODEX 200",
            "ticker": "069500",
            "market": "KR",
            "quantity": 50.0,
            "avg_price": 30000.0,
            "is_risk_asset": True
        }
    ]

    # 4. Mock prices: VT 현재가 220,000 KRW (환율 1000원 -> $220), KODEX 200 현재가 35,000 KRW
    mock_price_map = {
        "ast-us": 220000.0,
        "ast-kr": 35000.0
    }
    usd_krw_rate = 1000.0

    res = get_dashboard_summary(
        portfolio_id="p-1",
        accounts=mock_accounts,
        assets=mock_assets,
        all_holdings=mock_holdings,
        price_map=mock_price_map,
        usd_krw=usd_krw_rate
    )

    kpi = res["kpi"]
    assert "usd_summary" in kpi
    assert "krw_summary" in kpi

    # USD Summary 검증
    # VT: 10주 @ $220 = $2200 평가액, 매입 $2000, 손익 +$200 (+10.0%)
    # 달러 예수금: $500
    usd_sum = kpi["usd_summary"]
    assert usd_sum["stock_eval_usd"] == 2200.0
    assert usd_sum["stock_buy_usd"] == 2000.0
    assert usd_sum["stock_profit_usd"] == 200.0
    assert usd_sum["stock_return_usd"] == 10.0
    assert usd_sum["cash_usd"] == 500.0
    assert usd_sum["total_eval_usd"] == 2700.0

    # KRW Summary 검증 (KODEX 200: 50주 @ 35,000 = 1,750,000원, 매입 1,500,000원, 원화 예수금 1,000,000원)
    krw_sum = kpi["krw_summary"]
    assert krw_sum["stock_eval_krw"] == 1750000.0
    assert krw_sum["stock_buy_krw"] == 1500000.0
    assert krw_sum["stock_profit_krw"] == 250000.0
    assert krw_sum["cash_krw"] == 1000000.0
    assert krw_sum["total_eval_krw"] == 2750000.0

    # 개별 종목 행 검증
    us_row = next(r for r in res["stock_assets"] if r["ticker"] == "VT")
    assert us_row["is_us"] is True
    assert us_row["eval_amount_usd"] == 2200.0
    assert us_row["buy_amount_usd"] == 2000.0
    assert us_row["current_price_usd"] == 220.0
    assert us_row["avg_price_usd"] == 200.0
    assert us_row["profit_usd"] == 200.0
    assert us_row["profit_pct_usd"] == 10.0
