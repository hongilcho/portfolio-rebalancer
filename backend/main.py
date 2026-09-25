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
from data.data_manager import init_db
from backend.services import market_service
from logic.crypto_price_fetcher import get_crypto_prices
from backend.routers import auth, market, dashboard, accounts, assets, holdings, rebalance, trades, sync, crypto, portfolios, system

# Safe DB schema initialization on import
try:
    init_db()
except Exception as e:
    print(f"Database initialization warning (safe to ignore if already initialized): {e}")

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Zero-Cold-Start 백그라운드 프리워밍:
    # 컨테이너 기동 즉시 데몬 스레드로 백그라운드 갱신을 시작하여 사용자가 들어오기 전에 항상 최신 시세 준비
    def _background_warmup():
        try:
            market_service.warmup()
            get_crypto_prices()
        except Exception as e:
            print(f"Background warmup notice: {e}")

    threading.Thread(target=_background_warmup, daemon=True).start()
    yield

app = FastAPI(
    title="Portfolio Rebalancer API",
    description="High-performance backend API for portfolio rebalancing and multi-account asset management",
    version="2.0.0",
    lifespan=lifespan
)

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

@app.get("/api/health")
def health_check():
    return {"status": "ok", "message": "Portfolio Rebalancer API is healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
