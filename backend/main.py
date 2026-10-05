"""
FastAPI 애플리케이션 엔트리포인트 모듈
======================================
포트폴리오 리밸런서 백엔드 REST API 서버를 기동하고, 미들웨어 및 라우터를 등록합니다.

주요 아키텍처:
1. Lifespan 이벤트(프리워밍):
   - 서버 시작 시 시세·가상자산 및 보유 종목의 저장된 배당 캐시를 백그라운드에서 준비합니다.
2. W3C Server-Timing 미들웨어:
   - 모든 HTTP 응답 헤더에 실제 백엔드 처리 지연시간(ms)을 기록하여 프론트엔드 및 성능 모니터링 지원.
3. CORS 및 12개 도메인별 라우터 분기 등록.
"""

import os
import sys

import threading
from contextlib import asynccontextmanager

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from logic.refreshing_cache import MarketRefreshUnavailable
from data.data_manager import init_db, get_overview_batch_data
from backend.routers import forex
from logic.dividend_fetcher import prepare_dividend_cache
from backend.services import market_service
from logic.crypto_price_fetcher import get_crypto_prices
from backend.routers import auth, market, dashboard, accounts, assets, holdings, rebalance, trades, sync, crypto, portfolios, system

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Imports and test collection must not connect to a database.
    init_db()
    # Market collection and dividend DB restoration run independently.
    def _background_warmup():
        try:
            market_service.warmup()
            get_crypto_prices()
        except Exception as e:
            print(f"Background warmup notice: {e}")

    threading.Thread(target=_background_warmup, daemon=True).start()
    def _background_dividend_warmup():
        try:
            prepare_dividend_cache(get_overview_batch_data())
        except Exception as e:
            print(f"Dividend cache warmup notice: {type(e).__name__}")

    threading.Thread(target=_background_dividend_warmup, daemon=True).start()
    yield

app = FastAPI(
    title="Portfolio Rebalancer API",
    description="High-performance backend API for portfolio rebalancing and multi-account asset management",
    version="2.0.0",
    lifespan=lifespan
)

@app.exception_handler(MarketRefreshUnavailable)
async def market_unavailable(request, error):
    return JSONResponse(status_code=503, content={
        "detail": "최신 시장 데이터 수집에 실패했습니다. 잠시 후 다시 시도해주세요."})

# Server-Timing Middleware (W3C standard header for performance measurement)
@app.middleware("http")
async def add_server_timing_header(request: Request, call_next):
    start_time = time.time()
    response = await call_next(request)
    duration_ms = round((time.time() - start_time) * 1000, 1)
    response.headers["Server-Timing"] = f"total;desc=\"Total Process Time\";dur={duration_ms}"
    return response

# Setup CORS for development and production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register Routers
app.include_router(auth.router)
app.include_router(market.router)
app.include_router(dashboard.router)
app.include_router(accounts.router)
app.include_router(assets.router)
app.include_router(holdings.router)
app.include_router(rebalance.router)
app.include_router(trades.router)
app.include_router(sync.router)
app.include_router(crypto.router)
app.include_router(portfolios.router)
app.include_router(system.router)
app.include_router(forex.router)

@app.get("/api/health")
def health_check():
    return {"status": "ok", "message": "Portfolio Rebalancer API is healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
