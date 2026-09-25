import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

import time
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from data.data_manager import init_db
from backend.routers import auth, market, dashboard, accounts, assets, holdings, rebalance, trades, sync, crypto, portfolios, system

# Initialize Database schema
init_db()

app = FastAPI(
    title="Portfolio Rebalancer API",
    description="High-performance backend API for portfolio rebalancing and multi-account asset management",
    version="2.0.0"
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
