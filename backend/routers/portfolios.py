from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional, Dict, Any

from data.data_manager import (
    get_portfolios, get_portfolio, create_portfolio, update_portfolio, delete_portfolio,
    get_overview_batch_data
)
from backend.services import market_service
from backend.routers.dashboard import get_dashboard_summary
from backend.routers.crypto import get_crypto_summary
from logic.crypto_price_fetcher import get_crypto_prices

router = APIRouter(prefix="/api/portfolios", tags=["Portfolios"])

class CreatePortfolioRequest(BaseModel):
    name: str
    description: Optional[str] = ""

class UpdatePortfolioRequest(BaseModel):
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
    (전체 DB 테이블 및 시세 조회를 병렬/배치로 단 1회 수행하여 극적인 응답 속도 보장)
    """
    # 1. DB 전체 데이터를 단 1회의 PostgreSQL 네트워크 왕복으로 배치 조회
    batch_data = get_overview_batch_data()
    portfolios = batch_data.get("portfolios", [])
    all_accounts = batch_data.get("accounts", [])
    all_assets = batch_data.get("assets", [])
    all_holdings = batch_data.get("holdings", [])
    crypto_holdings = batch_data.get("crypto_holdings", [])

    # 2. 가격 데이터 가져오기 (인메모리 캐시 및 SWR 적용)
    _, price_map = market_service.get_prices(force_refresh=force_refresh)
    usd_krw = market_service.usd_krw

    # 3. 가상화폐 요약 (사전 조회된 crypto_holdings 및 캐시 시세 사용 -> 0ms)
    c_res = None
    if include_crypto:
        crypto_prices = get_crypto_prices(force_refresh=force_refresh)
        c_res = get_crypto_summary(
            portfolio_id="default",
            include_portfolio=False,
            db_holdings=crypto_holdings,
            prices_map=crypto_prices
        )

    # 3. 계좌 및 자산 포트폴리오 ID별 인메모리 그룹화
    accounts_by_pid: Dict[str, List[Dict[str, Any]]] = {}
    for a in all_accounts:
        pid_val = str(a.get("portfolio_id") or "default")
        accounts_by_pid.setdefault(pid_val, []).append(a)

    assets_by_pid: Dict[str, List[Dict[str, Any]]] = {}
    for a in all_assets:
        pid_val = str(a.get("portfolio_id") or "default")
        assets_by_pid.setdefault(pid_val, []).append(a)

    portfolio_summaries = []
    total_portfolios_buy = 0.0
    total_portfolios_eval = 0.0
    total_cash_krw = 0.0

    # Ticker-based aggregation map
    aggregated_assets_map: Dict[str, Dict[str, Any]] = {}

    for p in portfolios:
        pid = p["id"]
        pname = p["name"]
        pdesc = p.get("description", "")
        
        try:
            p_accounts = accounts_by_pid.get(pid, [])
            p_assets = assets_by_pid.get(pid, [])
            dash = get_dashboard_summary(
                portfolio_id=pid,
                accounts=p_accounts,
                assets=p_assets,
                all_holdings=all_holdings,
                price_map=price_map,
                usd_krw=usd_krw
            )
            kpi = dash.get("kpi", {})
            cash = dash.get("cash_assets", {})
            stock_assets = dash.get("stock_assets", [])
            
            p_stock_buy = float(kpi.get("total_stock_buy", 0.0))
            p_cash = float(cash.get("total_cash_krw", 0.0))
            p_buy = p_stock_buy + p_cash
            p_eval = float(kpi.get("total_portfolio_eval", 0.0))
            p_profit = p_eval - p_buy
            p_profit_pct = (p_profit / p_buy * 100) if p_buy > 0 else 0.0
            
            total_portfolios_buy += p_buy
            total_portfolios_eval += p_eval
            total_cash_krw += p_cash

            portfolio_summaries.append({
                "id": pid,
                "name": pname,
                "description": pdesc,
                "is_default": p.get("is_default", False),
                "total_buy": p_buy,
                "total_eval": p_eval,
                "total_profit": p_profit,
                "total_profit_pct": p_profit_pct,
                "cash_krw": p_cash,
                "account_count": len(dash.get("accounts", [])),
                "asset_count": len(stock_assets),
                "weight_pct": 0.0 # Will calculate after grand total
            })

            # Merge individual stock holdings
            for sa in stock_assets:
                ticker = sa.get("ticker", "")
                name = sa.get("name", "")
                market = sa.get("market", "KR")
                qty = float(sa.get("quantity", 0.0))
                eval_amt = float(sa.get("eval_amount", 0.0))
                buy_amt = float(sa.get("buy_amount", 0.0))
                curr_price = float(sa.get("current_price", 0.0))
                avg_price = float(sa.get("avg_price", 0.0))
                profit_krw = float(sa.get("profit_krw", 0.0))
                profit_pct = float(sa.get("profit_pct", 0.0))

                if qty <= 0:
                    continue

                is_dep = bool(sa.get("is_deposit", False))
                asset_type_val = "DEPOSIT" if is_dep else "STOCK"

                key = f"{ticker}_{market}"
                if key not in aggregated_assets_map:
                    aggregated_assets_map[key] = {
                        "key": key,
                        "ticker": ticker,
                        "name": name,
                        "market": market,
                        "asset_type": asset_type_val,
                        "is_deposit": is_dep,
                        "total_quantity": 0.0,
                        "total_buy_amount": 0.0,
                        "total_eval_amount": 0.0,
                        "current_price": curr_price,
                        "distribution": []
                    }

                entry = aggregated_assets_map[key]
                entry["total_quantity"] += qty
                entry["total_buy_amount"] += buy_amt
                entry["total_eval_amount"] += eval_amt
                if curr_price > 0:
                    entry["current_price"] = curr_price

                entry["distribution"].append({
                    "portfolio_id": pid,
                    "portfolio_name": pname,
                    "quantity": qty,
                    "avg_price": avg_price,
                    "eval_amount": eval_amt,
                    "profit_krw": profit_krw,
                    "profit_pct": profit_pct
                })

        except Exception as e:
            print(f"Error calculating overview for portfolio {pid}: {e}")

    # Process aggregated stock assets
    aggregated_assets_list = []
    for item in aggregated_assets_map.values():
        tot_qty = item["total_quantity"]
        tot_buy = item["total_buy_amount"]
        tot_eval = item["total_eval_amount"]
        weighted_avg = (tot_buy / tot_qty) if tot_qty > 0 else 0.0
        profit = tot_eval - tot_buy
        profit_pct = (profit / tot_buy * 100) if tot_buy > 0 else 0.0

        item["weighted_avg_price"] = weighted_avg
        item["total_profit"] = profit
        item["total_profit_pct"] = profit_pct
        aggregated_assets_list.append(item)

    # Crypto summary handling
    crypto_data = None
    crypto_total_buy = 0.0
    crypto_total_eval = 0.0

    if include_crypto and c_res:
        try:
            c_tot = c_res.get("crypto_total", {})
            c_assets = c_res.get("crypto_assets", [])
            
            crypto_total_buy = float(c_tot.get("total_buy", 0.0))
            crypto_total_eval = float(c_tot.get("total_eval", 0.0))
            
            crypto_data = {
                "total_buy": crypto_total_buy,
                "total_eval": crypto_total_eval,
                "total_profit": c_tot.get("total_profit", 0.0),
                "total_profit_pct": c_tot.get("total_profit_pct", 0.0),
                "assets": c_assets,
                "weight_pct": 0.0
            }

            # Add BTC and ETH to aggregated assets list
            for ca in c_assets:
                c_qty = float(ca.get("quantity", 0.0))
                if c_qty > 0:
                    c_buy = float(ca.get("buy_amount", 0.0))
                    c_eval = float(ca.get("eval_amount", 0.0))
                    c_profit = c_eval - c_buy
                    c_profit_pct = (c_profit / c_buy * 100) if c_buy > 0 else 0.0

                    aggregated_assets_list.append({
                        "key": f"crypto_{ca['symbol']}",
                        "ticker": ca["symbol"],
                        "name": ca["name"],
                        "market": "CRYPTO",
                        "asset_type": "CRYPTO",
                        "total_quantity": c_qty,
                        "weighted_avg_price": float(ca.get("avg_price", 0.0)),
                        "current_price": float(ca.get("current_price", 0.0)),
                        "total_buy_amount": c_buy,
                        "total_eval_amount": c_eval,
                        "total_profit": c_profit,
                        "total_profit_pct": c_profit_pct,
                        "distribution": [{
                            "portfolio_id": "crypto",
                            "portfolio_name": "가상화폐 자산",
                            "quantity": c_qty,
                            "avg_price": float(ca.get("avg_price", 0.0)),
                            "eval_amount": c_eval,
                            "profit_krw": c_profit,
                            "profit_pct": c_profit_pct
                        }]
                    })
        except Exception as e:
            print(f"Error fetching crypto summary in overview: {e}")

    # Grand Totals
    grand_total_buy = total_portfolios_buy + (crypto_total_buy if include_crypto else 0.0)
    grand_total_eval = total_portfolios_eval + (crypto_total_eval if include_crypto else 0.0)
    grand_total_profit = grand_total_eval - grand_total_buy
    grand_total_profit_pct = (grand_total_profit / grand_total_buy * 100) if grand_total_buy > 0 else 0.0

    # Calculate portfolio weights in grand total
    for p in portfolio_summaries:
        p["weight_pct"] = (p["total_eval"] / grand_total_eval * 100) if grand_total_eval > 0 else 0.0

    if crypto_data and grand_total_eval > 0:
        crypto_data["weight_pct"] = (crypto_total_eval / grand_total_eval * 100)

    # Calculate individual aggregated asset weights in grand total
    for item in aggregated_assets_list:
        item["weight_in_grand_total_pct"] = (item["total_eval_amount"] / grand_total_eval * 100) if grand_total_eval > 0 else 0.0

    # Sort aggregated assets by eval amount descending
    aggregated_assets_list.sort(key=lambda x: x["total_eval_amount"], reverse=True)

    return {
        "grand_total": {
            "total_buy": grand_total_buy,
            "total_eval": grand_total_eval,
            "total_profit": grand_total_profit,
            "total_profit_pct": grand_total_profit_pct,
            "total_cash_krw": total_cash_krw,
            "portfolios_total_eval": total_portfolios_eval,
            "crypto_total_eval": crypto_total_eval if include_crypto else 0.0
        },
        "portfolios": portfolio_summaries,
        "crypto": crypto_data,
        "include_crypto": include_crypto,
        "aggregated_assets": aggregated_assets_list
    }
