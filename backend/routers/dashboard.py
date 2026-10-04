"""
포트폴리오 대시보드 API 라우터 (Dashboard Router)
==================================================
단일 포트폴리오의 종합 자산 평가, 계좌별 잔고/수익률, 자산군별 비중,
목표 비중 대비 괴리율 현황을 고속으로 산출하여 제공합니다.

주요 특징:
1. 단일 번들 통신(/api/dashboard/bundle):
   - 프론트엔드가 대시보드를 그리기 위해 필요한 5가지 데이터(포트폴리오 목록, 대시보드 요약,
     자산 목록, 계좌 목록, 실시간 시세/환율)를 단 1회의 HTTP 요청으로 통합 반환하여 왕복 지연시간(RTT) 최소화.
2. PostgreSQL 1회 배치 쿼리:
   - `get_overview_batch_data()`로 필요한 데이터를 한 번에 조회하고 계산 서비스에 전달.
"""

from fastapi import APIRouter
from typing import Dict, Any, List, Optional

from data.data_manager import get_overview_batch_data
from backend.services import market_service
from backend.valuation_service import evaluate_portfolio
from logic.portfolio_valuation import index_valuation_inputs
from logic.dividend_fetcher import calculate_adjusted_holding_prices, begin_dividend_request, get_dividend_status, prepare_dividend_cache

router = APIRouter(prefix="/api/dashboard", tags=["Dashboard"])

@router.get("/bundle")
def get_dashboard_bundle(portfolio_id: str = "default", force_refresh: bool = False):
    """
    대시보드 초기 렌더링에 필요한 모든 데이터를 단 1회의 HTTP 요청으로 제공하는 통합 번들 API.

    Args:
        portfolio_id (str): 대상 포트폴리오 ID (기본값: 'default')
        force_refresh (bool): 시세 강제 새로고침 여부 (기본값: False)

    Returns:
        dict: portfolios, dashboard, assets, accounts, prices_data, usd_krw, rate_source
    """
    batch_data = get_overview_batch_data()
    prepare_dividend_cache(batch_data)
    portfolios = batch_data.get("portfolios", [])
    all_accounts = batch_data.get("accounts", [])
    all_assets = batch_data.get("assets", [])
    all_holdings = batch_data.get("holdings", [])
    all_trades = batch_data.get("trade_history", [])

    p_accounts = [a for a in all_accounts if str(a.get("portfolio_id") or "default") == str(portfolio_id)]
    p_assets = [a for a in all_assets if str(a.get("portfolio_id") or "default") == str(portfolio_id)]

    prices, price_map = market_service.get_prices(force_refresh=force_refresh)
    snapshot = market_service.request_snapshot()
    usd_krw = snapshot['usd_krw']
    rate_source = snapshot['rate_source']
    begin_dividend_request(force_refresh)

    dash = get_dashboard_summary(
        portfolio_id=portfolio_id,
        accounts=p_accounts,
        assets=p_assets,
        all_holdings=all_holdings,
        price_map=price_map,
        usd_krw=usd_krw,
        price_data=prices,
        all_trades=all_trades
    )
    dash['market_status'] = {'prices': market_service.request_status(), 'dividends': get_dividend_status()}

    p_asset_ids = {str(a["id"]) for a in p_assets}
    p_prices = [p for p in prices if str(p["id"]) in p_asset_ids]

    return {
        "portfolios": portfolios,
        "dashboard": dash,
        "assets": p_assets,
        "accounts": p_accounts,
        "prices_data": {
            "prices": p_prices,
            "price_map": price_map,
            "usd_krw": usd_krw,
            "rate_source": rate_source
        },
        "usd_krw": usd_krw,
        "rate_source": rate_source
    }

@router.get("/summary")
def get_dashboard_summary(
    portfolio_id: str = "default",
    accounts: Optional[List[Dict[str, Any]]] = None,
    assets: Optional[List[Dict[str, Any]]] = None,
    all_holdings: Optional[List[Dict[str, Any]]] = None,
    price_map: Optional[Dict[str, float]] = None,
    usd_krw: Optional[float] = None,
    all_trades: Optional[List[Dict[str, Any]]] = None,
    price_data: Optional[List[Dict[str, Any]]] = None
):
    """
    포트폴리오 대시보드 종합 데이터 집계 API (portfolio_id 기준 필터링)
    - accounts, assets, all_holdings, price_map, usd_krw 전달 시 DB 재조회 없이 인메모리 고속 연산 수행
    - 파라미터 미전달 시 단 1회의 PostgreSQL 배치 조회 사용
    """
    if accounts is None or assets is None or all_holdings is None:
        batch_data = get_overview_batch_data()
        prepare_dividend_cache(batch_data)
        all_accounts = batch_data.get("accounts", [])
        all_assets = batch_data.get("assets", [])
        if all_holdings is None:
            all_holdings = batch_data.get("holdings", [])
        if all_trades is None:
            all_trades = batch_data.get("trade_history", [])
        if accounts is None:
            accounts = [a for a in all_accounts if str(a.get("portfolio_id") or "default") == str(portfolio_id)]
        if assets is None:
            assets = [a for a in all_assets if str(a.get("portfolio_id") or "default") == str(portfolio_id)]
    
    if price_map is None:
        begin_dividend_request()
        price_data, price_map = market_service.get_prices()
        if usd_krw is None:
            usd_krw = market_service.request_snapshot()['usd_krw']
    elif price_data is None:
        price_data = market_service.request_snapshot()['prices']
    if usd_krw is None:
        usd_krw = market_service.usd_krw

    inputs = index_valuation_inputs(all_holdings, all_trades, price_data)
    return build_dashboard_summary(accounts, assets, inputs, price_map, usd_krw)


def build_dashboard_summary(accounts, assets, inputs, price_map, usd_krw):
    """Internal adapter shared by single-portfolio and overview routes."""
    result = evaluate_portfolio(
        accounts, assets, inputs, price_map, usd_krw,
        calculate_adjustment=calculate_adjusted_holding_prices,
    )
    result['rate_source'] = market_service.request_snapshot()['rate_source']
    result['market_status'] = {
        'prices': market_service.request_status(), 'dividends': get_dividend_status(),
    }
    return result
