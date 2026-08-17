import os
import sys

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from data.data_manager import init_db
from backend.routers import auth, market, dashboard, accounts, assets, holdings, rebalance, trades, sync

# Initialize Database schema
init_db()

app = FastAPI(
    title="Portfolio Rebalancer API",
    description="High-performance backend API for portfolio rebalancing and multi-account asset management",
    version="2.0.0"
)

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

@app.get("/api/health")
def health_check():
    return {"status": "ok", "message": "Portfolio Rebalancer API is healthy"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
