"""
다중 포트폴리오 관리 및 종합 요약 API 라우터 (Portfolios Router)
================================================================
복수의 금융 포트폴리오 생성/수정/삭제 및 전체 자산 종합 요약(Overview Summary)을 제공합니다.

주요 특징:
1. 포트폴리오 CRUD: 멀티 포트폴리오의 독립된 자산/계좌 배분 환경 제공
2. 전체 자산 종합 요약(/api/portfolios/overview/summary):
   - 모든 개별 포트폴리오(금융자산) + 가상자산(BTC/ETH)을 포괄하는 전체 순자산(NAV) 산출
   - 여러 포트폴리오에서 동일 종목을 중복 보유할 경우, 가중평균 평단가(Weighted Average Price) 자동 계산
"""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import Optional

from data.data_manager import (
    get_portfolios, get_portfolio, create_portfolio, update_portfolio, delete_portfolio,
    get_overview_batch_data
)
from backend.services import market_service
from backend.routers import dashboard as dashboard_router
from backend.valuation_service import evaluate_portfolios
from logic.overview_valuation import calculate_overview_summary
from logic.portfolio_valuation import index_valuation_inputs
from backend.routers.crypto import get_crypto_summary
from logic.crypto_price_fetcher import get_crypto_prices, get_crypto_status
from logic.dividend_fetcher import begin_dividend_request, get_dividend_status, prepare_dividend_cache

router = APIRouter(prefix="/api/portfolios", tags=["Portfolios"])

class CreatePortfolioRequest(BaseModel):
    """새 포트폴리오 생성 요청 모델"""
    name: str
    description: Optional[str] = ""

class UpdatePortfolioRequest(BaseModel):
    """포트폴리오 수정 요청 모델"""
    name: str
    description: Optional[str] = ""

@router.get("/")
def list_portfolios():
    return {"portfolios": get_portfolios()}

@router.get("/{portfolio_id}")
def retrieve_portfolio(portfolio_id: str):
    p = get_portfolio(portfolio_id)
    if not p:
        raise HTTPException(status_code=404, detail="포트폴리오를 찾을 수 없습니다.")
    return {"portfolio": p}

@router.post("/")
def add_new_portfolio(req: CreatePortfolioRequest):
    success, msg, data = create_portfolio(req.name, req.description or "")
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg, "portfolio": data}

@router.put("/{portfolio_id}")
def edit_portfolio(portfolio_id: str, req: UpdatePortfolioRequest):
    success, msg = update_portfolio(portfolio_id, req.name, req.description or "")
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}

@router.delete("/{portfolio_id}")
def remove_portfolio(portfolio_id: str):
    success, msg = delete_portfolio(portfolio_id)
    if not success:
        raise HTTPException(status_code=400, detail=msg)
    return {"success": True, "message": msg}

@router.get("/overview/summary")
def get_all_portfolios_overview(include_crypto: bool = Query(True), force_refresh: bool = Query(False)):
    """
    모든 포트폴리오를 통합 종합 집계하고,
    동일 종목을 여러 포트폴리오에서 보유한 경우 가중평균 평단가 및 통합 수량을 산출하는 API
    (한 번의 DB 배치 조회와 요청 내 공유 계산 데이터 사용)
    """
    # 1. DB 전체 데이터를 단 1회의 PostgreSQL 네트워크 왕복으로 배치 조회
    batch_data = get_overview_batch_data()
    prepare_dividend_cache(batch_data)
    portfolios = batch_data.get("portfolios", [])
    all_accounts = batch_data.get("accounts", [])
    all_assets = batch_data.get("assets", [])
    all_holdings = batch_data.get("holdings", [])
    all_trades = batch_data.get("trade_history", [])
    crypto_holdings = batch_data.get("crypto_holdings", [])

    # 2. 가격 데이터 가져오기 (인메모리 캐시 및 SWR 적용)
    prices, price_map = market_service.get_prices(force_refresh=force_refresh)
    usd_krw = market_service.request_snapshot()['usd_krw']
    begin_dividend_request(force_refresh)

    # 3. 가상화폐 요약 (사전 조회한 보유량과 캐시 시세 사용)
    c_res = None
    if include_crypto:
        crypto_prices = get_crypto_prices(force_refresh=force_refresh)
        c_res = get_crypto_summary(
            portfolio_id="default",
            include_portfolio=False,
            db_holdings=crypto_holdings,
            prices_map=crypto_prices
        )

    valuation_inputs = index_valuation_inputs(all_holdings, all_trades, prices)

    dashboards, errors, accounts_by_pid = evaluate_portfolios(
        portfolios, all_accounts, all_assets, valuation_inputs, price_map, usd_krw,
        calculate_adjustment=dashboard_router.calculate_adjusted_holding_prices,
    )
    result, aggregation_errors = calculate_overview_summary(
        portfolios, dashboards, c_res, include_crypto, usd_krw, accounts_by_pid,
    )
    for message in errors + aggregation_errors:
        print(message)
    result['rate_source'] = market_service.request_snapshot()['rate_source']
    result['market_status'] = {
        'prices': market_service.request_status(), 'dividends': get_dividend_status(),
        **({'crypto': get_crypto_status()} if include_crypto else {}),
    }
    return result
