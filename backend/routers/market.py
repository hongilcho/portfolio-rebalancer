from fastapi import APIRouter, Response
from pydantic import BaseModel
import pandas as pd
import io
import zipfile
import datetime
from backend.services import market_service
from data.data_manager import get_all_accounts, get_all_assets, get_all_holdings, get_trade_history

router = APIRouter(prefix="/api/market", tags=["market"])

class RateOverrideRequest(BaseModel):
    usd_krw: float

@router.get("/exchange-rate")
def get_exchange_rate():
    return {
        "usd_krw": market_service.usd_krw,
        "rate_source": market_service.rate_source,
        "is_custom": market_service.is_custom_rate
    }

@router.post("/exchange-rate/override")
def override_exchange_rate(req: RateOverrideRequest):
    market_service.set_custom_exchange_rate(req.usd_krw)
    return {
        "success": True,
        "usd_krw": market_service.usd_krw,
        "rate_source": market_service.rate_source
    }

@router.post("/exchange-rate/refresh")
def refresh_exchange_rate():
    market_service.reset_custom_exchange_rate()
    market_service.get_prices(force_refresh=True)
    return {
        "success": True,
        "usd_krw": market_service.usd_krw,
        "rate_source": market_service.rate_source
    }

@router.get("/prices")
def get_prices(force_refresh: bool = False):
    prices, price_map = market_service.get_prices(force_refresh=force_refresh)
    return {
        "prices": prices,
        "price_map": price_map,
        "usd_krw": market_service.usd_krw,
        "rate_source": market_service.rate_source
    }

@router.get("/export-csv")
def export_csv_backup():
    accounts_df = pd.DataFrame(get_all_accounts())
    assets_df = pd.DataFrame(get_all_assets())
    holdings_df = pd.DataFrame(get_all_holdings())
    trades_df = pd.DataFrame(get_trade_history())
    
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zip_file:
        if not accounts_df.empty:
            zip_file.writestr("accounts.csv", accounts_df.to_csv(index=False).encode('utf-8-sig'))
        if not assets_df.empty:
            zip_file.writestr("assets.csv", assets_df.to_csv(index=False).encode('utf-8-sig'))
        if not holdings_df.empty:
            zip_file.writestr("holdings.csv", holdings_df.to_csv(index=False).encode('utf-8-sig'))
        if not trades_df.empty:
            zip_file.writestr("trade_history.csv", trades_df.to_csv(index=False).encode('utf-8-sig'))
    
    zip_buffer.seek(0)
    filename = f"portfolio_backup_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
    
    return Response(
        content=zip_buffer.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )
