from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from data.data_manager import get_crypto_holdings, save_crypto_holding, get_portfolio
from logic.crypto_price_fetcher import get_crypto_prices
from backend.routers.dashboard import get_dashboard_summary

router = APIRouter(prefix="/api/crypto", tags=["crypto"])

class CryptoHoldingItem(BaseModel):
    symbol: str
    quantity: float
    avg_price: float
    notes: Optional[str] = ""

class CryptoHoldingsUpdateRequest(BaseModel):
    holdings: List[CryptoHoldingItem]

@router.get("/summary")
def get_crypto_summary(portfolio_id: Optional[str] = "default"):
    # 1. Fetch live prices & DB holdings
    prices_map = get_crypto_prices()
    db_holdings = get_crypto_holdings()
    db_map = {h['symbol'].upper(): h for h in db_holdings}

    crypto_assets = []
    crypto_total_buy = 0.0
    crypto_total_eval = 0.0

    for sym in ["BTC", "ETH"]:
        p_info = prices_map.get(sym, {})
        h_info = db_map.get(sym, {})
        
        curr_price = float(p_info.get("price", 0.0))
        qty = float(h_info.get("quantity", 0.0))
        avg_price = float(h_info.get("avg_price", 0.0))
        
        buy_amt = qty * avg_price
        eval_amt = qty * curr_price
        profit_krw = eval_amt - buy_amt
        profit_pct = (profit_krw / buy_amt * 100) if buy_amt > 0 else 0.0

        crypto_total_buy += buy_amt
        crypto_total_eval += eval_amt

        crypto_assets.append({
            "symbol": sym,
            "name": "비트코인" if sym == "BTC" else "이더리움",
            "current_price": curr_price,
            "change_24h_pct": p_info.get("change_24h_pct", 0.0),
            "high_24h": p_info.get("high_24h", 0.0),
            "low_24h": p_info.get("low_24h", 0.0),
            "source": p_info.get("source", "업비트"),
            "quantity": qty,
            "avg_price": avg_price,
            "buy_amount": buy_amt,
            "eval_amount": eval_amt,
            "profit_krw": profit_krw,
            "profit_pct": profit_pct,
            "notes": h_info.get("notes") or ""
        })

    crypto_total_profit = crypto_total_eval - crypto_total_buy
    crypto_total_profit_pct = (crypto_total_profit / crypto_total_buy * 100) if crypto_total_buy > 0 else 0.0

    # 2. Fetch existing financial portfolio data
    target_pid = portfolio_id or "default"
    port = get_portfolio(target_pid)
    portfolio_name = port.get("name", "금융 포트폴리오") if port else "금융 포트폴리오"

    try:
        dash = get_dashboard_summary(portfolio_id=target_pid)
        kpi = dash.get("kpi", {})
        cash = dash.get("cash_assets", {})
        
        portfolio_eval = float(kpi.get("total_portfolio_eval", 0.0))
        portfolio_stock_buy = float(kpi.get("total_stock_buy", 0.0))
        portfolio_cash = float(cash.get("total_cash_krw", 0.0))
        portfolio_buy = portfolio_stock_buy + portfolio_cash
        portfolio_profit = float(kpi.get("total_stock_profit", 0.0))
        portfolio_profit_pct = float(kpi.get("total_stock_return", 0.0))
    except Exception as e:
        print(f"Error loading dashboard summary in crypto router: {e}")
        portfolio_eval = 0.0
        portfolio_buy = 0.0
        portfolio_profit = 0.0
        portfolio_profit_pct = 0.0

    # 3. Calculate Combined Metrics (Portfolio + Crypto)
    combined_eval = portfolio_eval + crypto_total_eval
    combined_buy = portfolio_buy + crypto_total_buy
    combined_profit = combined_eval - combined_buy
    combined_profit_pct = (combined_profit / combined_buy * 100) if combined_buy > 0 else 0.0

    portfolio_weight_pct = (portfolio_eval / combined_eval * 100) if combined_eval > 0 else 0.0
    crypto_weight_pct = (crypto_total_eval / combined_eval * 100) if combined_eval > 0 else 0.0

    # Individual crypto weights in combined total
    for item in crypto_assets:
        item["weight_in_combined_pct"] = (item["eval_amount"] / combined_eval * 100) if combined_eval > 0 else 0.0

    return {
        "crypto_assets": crypto_assets,
        "crypto_total": {
            "total_buy": crypto_total_buy,
            "total_eval": crypto_total_eval,
            "total_profit": crypto_total_profit,
            "total_profit_pct": crypto_total_profit_pct,
        },
        "portfolio_summary": {
            "portfolio_id": target_pid,
            "portfolio_name": portfolio_name,
            "total_eval": portfolio_eval,
            "total_buy": portfolio_buy,
            "total_profit": portfolio_profit,
            "total_profit_pct": portfolio_profit_pct,
            "weight_pct": portfolio_weight_pct
        },
        "combined_summary": {
            "total_eval": combined_eval,
            "total_buy": combined_buy,
            "total_profit": combined_profit,
            "total_profit_pct": combined_profit_pct,
            "portfolio_weight_pct": portfolio_weight_pct,
            "crypto_weight_pct": crypto_weight_pct
        }
    }

@router.put("/holdings")
def update_crypto_holdings(req: CryptoHoldingsUpdateRequest):
    success_count = 0
    errors = []

    for item in req.holdings:
        sym = item.symbol.strip().upper()
        if sym not in ["BTC", "ETH"]:
            continue
        success, msg = save_crypto_holding(
            symbol=sym,
            quantity=item.quantity,
            avg_price=item.avg_price,
            notes=item.notes or ""
        )
        if success:
            success_count += 1
        else:
            errors.append(f"[{sym}] {msg}")

    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    return {
        "success": True,
        "message": "가상화폐 보유 정보가 성공적으로 업데이트되었습니다.",
        "updated_count": success_count
    }
