"""
가상자산(암호화폐) 관리 API 라우터 (Crypto Router)
==================================================
비트코인(BTC), 이더리움(ETH) 등 소유자(홍일, 윤아)별 가상자산 보유량 관리,
실시간 업비트 시세 반영 평가금액 및 손익 집계 API를 제공합니다.
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from data.data_manager import get_crypto_holdings, save_crypto_holding, get_portfolio
from logic.crypto_price_fetcher import get_crypto_prices
from backend.routers.dashboard import get_dashboard_summary

router = APIRouter(prefix="/api/crypto", tags=["crypto"])

class CryptoHoldingItem(BaseModel):
    """가상자산 보유 종목 스키마"""
    owner: Optional[str] = "홍일"
    symbol: str
    quantity: float
    avg_price: float
    notes: Optional[str] = ""

class CryptoHoldingsUpdateRequest(BaseModel):
    """가상자산 보유량 일괄 수정 요청 스키마"""
    holdings: List[CryptoHoldingItem]

@router.get("/summary")
def get_crypto_summary(
    portfolio_id: Optional[str] = "default",
    include_portfolio: bool = False,
    db_holdings: Optional[List[Dict[str, Any]]] = None,
    prices_map: Optional[Dict[str, Any]] = None
):
    # 1. Fetch live prices & DB holdings
    if prices_map is None:
        prices_map = get_crypto_prices()
    if db_holdings is None:
        db_holdings = get_crypto_holdings()
    db_map = {(h.get('owner', '윤아'), h['symbol'].upper()): h for h in db_holdings}

    OWNERS = ["홍일", "윤아"]
    SYMBOLS = ["BTC", "ETH"]

    by_owner = {}
    for owner_name in OWNERS:
        owner_assets = []
        owner_total_buy = 0.0
        owner_total_eval = 0.0

        for sym in SYMBOLS:
            p_info = prices_map.get(sym, {})
            h_info = db_map.get((owner_name, sym), {})

            curr_price = float(p_info.get("price", 0.0))
            qty = float(h_info.get("quantity", 0.0))
            avg_price = float(h_info.get("avg_price", 0.0))

            buy_amt = qty * avg_price
            eval_amt = qty * curr_price
            profit_krw = eval_amt - buy_amt
            profit_pct = (profit_krw / buy_amt * 100) if buy_amt > 0 else 0.0

            owner_total_buy += buy_amt
            owner_total_eval += eval_amt

            owner_assets.append({
                "owner": owner_name,
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

        owner_total_profit = owner_total_eval - owner_total_buy
        owner_total_profit_pct = (owner_total_profit / owner_total_buy * 100) if owner_total_buy > 0 else 0.0

        by_owner[owner_name] = {
            "owner": owner_name,
            "assets": owner_assets,
            "total_buy": owner_total_buy,
            "total_eval": owner_total_eval,
            "total_profit": owner_total_profit,
            "total_profit_pct": owner_total_profit_pct,
            "share_pct": 0.0  # Will calculate below
        }

    # 2. Combined Crypto by Symbol (홍일 + 윤아)
    crypto_assets_combined = []
    crypto_total_buy = 0.0
    crypto_total_eval = 0.0

    for sym in SYMBOLS:
        p_info = prices_map.get(sym, {})
        curr_price = float(p_info.get("price", 0.0))

        comb_qty = sum(
            next((a["quantity"] for a in by_owner[o]["assets"] if a["symbol"] == sym), 0.0)
            for o in OWNERS
        )
        comb_buy = sum(
            next((a["buy_amount"] for a in by_owner[o]["assets"] if a["symbol"] == sym), 0.0)
            for o in OWNERS
        )
        comb_eval = sum(
            next((a["eval_amount"] for a in by_owner[o]["assets"] if a["symbol"] == sym), 0.0)
            for o in OWNERS
        )
        comb_avg_price = (comb_buy / comb_qty) if comb_qty > 0 else 0.0
        comb_profit = comb_eval - comb_buy
        comb_profit_pct = (comb_profit / comb_buy * 100) if comb_buy > 0 else 0.0

        crypto_total_buy += comb_buy
        crypto_total_eval += comb_eval

        crypto_assets_combined.append({
            "symbol": sym,
            "name": "비트코인" if sym == "BTC" else "이더리움",
            "current_price": curr_price,
            "change_24h_pct": p_info.get("change_24h_pct", 0.0),
            "high_24h": p_info.get("high_24h", 0.0),
            "low_24h": p_info.get("low_24h", 0.0),
            "source": p_info.get("source", "업비트"),
            "quantity": comb_qty,
            "avg_price": comb_avg_price,
            "buy_amount": comb_buy,
            "eval_amount": comb_eval,
            "profit_krw": comb_profit,
            "profit_pct": comb_profit_pct,
        })

    crypto_total_profit = crypto_total_eval - crypto_total_buy
    crypto_total_profit_pct = (crypto_total_profit / crypto_total_buy * 100) if crypto_total_buy > 0 else 0.0

    # Calculate owner share percentages within crypto
    for owner_name in OWNERS:
        if crypto_total_eval > 0:
            by_owner[owner_name]["share_pct"] = (by_owner[owner_name]["total_eval"] / crypto_total_eval) * 100
        else:
            by_owner[owner_name]["share_pct"] = 0.0

    # 3. Financial portfolio data (요청 시에만 조회하여 불필요한 시세 동기화 지연 방지)
    target_pid = portfolio_id or "default"
    portfolio_name = "금융 포트폴리오"
    portfolio_eval = 0.0
    portfolio_buy = 0.0
    portfolio_profit = 0.0
    portfolio_profit_pct = 0.0

    if include_portfolio:
        port = get_portfolio(target_pid)
        if port:
            portfolio_name = port.get("name", "금융 포트폴리오")
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

    # 4. Calculate Combined Metrics (Portfolio + All Crypto)
    combined_eval = portfolio_eval + crypto_total_eval
    combined_buy = portfolio_buy + crypto_total_buy
    combined_profit = combined_eval - combined_buy
    combined_profit_pct = (combined_profit / combined_buy * 100) if combined_buy > 0 else 0.0

    portfolio_weight_pct = (portfolio_eval / combined_eval * 100) if combined_eval > 0 else 0.0
    crypto_weight_pct = (crypto_total_eval / combined_eval * 100) if combined_eval > 0 else 0.0

    # Individual combined crypto weights
    for item in crypto_assets_combined:
        item["weight_in_crypto_pct"] = (item["eval_amount"] / crypto_total_eval * 100) if crypto_total_eval > 0 else 0.0
        item["weight_in_combined_pct"] = (item["eval_amount"] / combined_eval * 100) if combined_eval > 0 else 0.0

    # Owner weights
    for owner_name in OWNERS:
        by_owner[owner_name]["weight_in_crypto_pct"] = (
            (by_owner[owner_name]["total_eval"] / crypto_total_eval * 100) if crypto_total_eval > 0 else 0.0
        )
        by_owner[owner_name]["weight_in_combined_pct"] = (
            (by_owner[owner_name]["total_eval"] / combined_eval * 100) if combined_eval > 0 else 0.0
        )
        for a in by_owner[owner_name]["assets"]:
            a["weight_in_crypto_pct"] = (
                (a["eval_amount"] / crypto_total_eval * 100) if crypto_total_eval > 0 else 0.0
            )
            a["weight_in_combined_pct"] = (
                (a["eval_amount"] / combined_eval * 100) if combined_eval > 0 else 0.0
            )

    return {
        "by_owner": by_owner,
        "crypto_assets_combined": crypto_assets_combined,
        "crypto_assets": crypto_assets_combined,  # Backwards compatibility
        "crypto_total": {
            "total_buy": crypto_total_buy,
            "total_eval": crypto_total_eval,
            "total_profit": crypto_total_profit,
            "total_profit_pct": crypto_total_profit_pct,
        },
        "owner_shares": {
            "hongil_eval": by_owner["홍일"]["total_eval"],
            "hongil_pct": by_owner["홍일"]["share_pct"],
            "yoona_eval": by_owner["윤아"]["total_eval"],
            "yoona_pct": by_owner["윤아"]["share_pct"],
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
        owner = (item.owner or "홍일").strip()
        success, msg = save_crypto_holding(
            symbol=sym,
            quantity=item.quantity,
            avg_price=item.avg_price,
            owner=owner,
            notes=item.notes or ""
        )
        if success:
            success_count += 1
        else:
            errors.append(f"[{owner} - {sym}] {msg}")

    if errors:
        raise HTTPException(status_code=400, detail="; ".join(errors))

    return {
        "success": True,
        "message": "가상화폐 보유 정보가 성공적으로 업데이트되었습니다.",
        "updated_count": success_count
    }
