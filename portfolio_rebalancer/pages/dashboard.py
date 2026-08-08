import reflex as rx
import pandas as pd
from typing import List, Dict, Any
from portfolio_rebalancer.state import AppState
from portfolio_rebalancer.components.navbar import navbar
from data.data_manager import get_all_assets, get_all_accounts, get_holdings_by_account, ACCOUNT_TYPES

class DashboardState(AppState):
    """State for the Dashboard page."""
    
    accounts: List[Dict[str, Any]] = []
    assets: List[Dict[str, Any]] = []
    
    total_stock_buy: float = 0.0
    total_stock_eval: float = 0.0
    total_stock_profit: float = 0.0
    total_stock_return: float = 0.0
    
    stock_summary_rows: List[Dict[str, Any]] = []
    cash_summary_rows: List[Dict[str, Any]] = []
    account_summaries: List[Dict[str, Any]] = []
    
    def on_load(self):
        super().on_load()
        self.load_dashboard_data()
        
    def load_dashboard_data(self):
        self.assets = get_all_assets()
        self.accounts = get_all_accounts()
        
        price_map = {}
        if self.price_data:
            for item in self.price_data:
                price_map[str(item['id'])] = item['price_krw']
                
        self.account_summaries = []
        total_portfolio_eval = 0.0
        portfolio_assets = {}
        total_krw_cash = 0.0
        total_usd_cash = 0.0
        
        for acc in self.accounts:
            acc_id = acc['id']
            dep_krw = acc['deposit_krw']
            dep_usd = acc['deposit_usd']
            dep_usd_krw = dep_usd * self.usd_krw
            total_deposit = dep_krw + dep_usd_krw
            
            total_krw_cash += dep_krw
            total_usd_cash += dep_usd
            
            holdings = get_holdings_by_account(acc_id)
            stock_eval = 0.0
            risk_stock_eval = 0.0
            safe_stock_eval = 0.0
            stock_buy_total = 0.0
            holding_details = []
            
            for h in holdings:
                aid = str(h['asset_id'])
                qty = h['quantity']
                avg_p_krw = h['avg_price']
                curr_p = price_map.get(aid, avg_p_krw if avg_p_krw > 0 else 0)
                eval_val = qty * curr_p
                
                stock_eval += eval_val
                stock_buy_total += (qty * avg_p_krw)
                
                if h['is_risk_asset']:
                    risk_stock_eval += eval_val
                else:
                    safe_stock_eval += eval_val
                    
                profit_krw = eval_val - (qty * avg_p_krw)
                profit_pct = (profit_krw / (qty * avg_p_krw) * 100) if (qty * avg_p_krw) > 0 else 0.0
                
                holding_details.append({
                    "name": h['asset_name'],
                    "qty": qty,
                    "profit_krw": profit_krw,
                    "profit_pct": profit_pct,
                    "eval_val": eval_val,
                    "avg_p": avg_p_krw,
                    "curr_p": curr_p,
                    "ticker": h['ticker'],
                    "is_risk": h['is_risk_asset']
                })
                
                if aid not in portfolio_assets:
                    portfolio_assets[aid] = {
                        "name": h['asset_name'],
                        "ticker": h['ticker'],
                        "qty": 0.0,
                        "buy_amt_krw": 0.0,
                        "eval_amt_krw": 0.0,
                    }
                portfolio_assets[aid]['qty'] += qty
                portfolio_assets[aid]['buy_amt_krw'] += qty * avg_p_krw
                portfolio_assets[aid]['eval_amt_krw'] += eval_val
                
            total_acc_val = total_deposit + stock_eval
            total_portfolio_eval += total_acc_val
            risk_pct = (risk_stock_eval / total_acc_val * 100) if total_acc_val > 0 else 0.0
            
            self.account_summaries.append({
                "acc": acc,
                "total_val": total_acc_val,
                "deposit_krw": dep_krw,
                "deposit_usd": dep_usd,
                "stock_eval": stock_eval,
                "stock_buy_total": stock_buy_total,
                "risk_eval": risk_stock_eval,
                "safe_eval": safe_stock_eval,
                "risk_pct": risk_pct,
                "holdings": holding_details
            })

        self.total_stock_eval = sum(data['eval_amt_krw'] for data in portfolio_assets.values() if data['qty'] > 0)
        self.total_stock_buy = sum(data['buy_amt_krw'] for data in portfolio_assets.values() if data['qty'] > 0)
        self.total_stock_profit = self.total_stock_eval - self.total_stock_buy
        self.total_stock_return = (self.total_stock_profit / self.total_stock_buy * 100) if self.total_stock_buy > 0 else 0.0
        
        target_weight_map = {str(a['id']): a['target_weight'] for a in self.assets}
        
        self.stock_summary_rows = []
        for a in self.assets:
            aid = str(a['id'])
            data = portfolio_assets.get(aid, {
                "name": a['name'],
                "ticker": a['ticker'],
                "qty": 0.0,
                "buy_amt_krw": 0.0,
                "eval_amt_krw": 0.0
            })
            
            profit_krw = data['eval_amt_krw'] - data['buy_amt_krw']
            profit_pct = (profit_krw / data['buy_amt_krw'] * 100) if data['buy_amt_krw'] > 0 else 0.0
            weight_pct = (data['eval_amt_krw'] / self.total_stock_eval * 100) if self.total_stock_eval > 0 else 0.0
            target_w = target_weight_map.get(aid, 0.0)
            diff_w = weight_pct - target_w
            
            self.stock_summary_rows.append({
                "name": data['name'],
                "qty": data['qty'],
                "eval_amt": data['eval_amt_krw'],
                "profit_krw": profit_krw,
                "profit_pct": profit_pct,
                "avg_price": data['buy_amt_krw'] / data['qty'] if data['qty'] > 0 else 0,
                "curr_price": price_map.get(aid, 0.0),
                "weight_pct": weight_pct,
                "target_w": target_w,
                "diff_w": diff_w,
            })
            
        self.stock_summary_rows.sort(key=lambda x: x['weight_pct'], reverse=True)
        
        self.cash_summary_rows = []
        if total_krw_cash > 0:
            self.cash_summary_rows.append({
                "name": "💵 현금 (KRW)",
                "qty_str": "-",
                "eval_amt": total_krw_cash
            })
        if total_usd_cash > 0:
            self.cash_summary_rows.append({
                "name": "💵 현금 (USD)",
                "qty_str": f"${total_usd_cash:,.2f}",
                "eval_amt": total_usd_cash * self.usd_krw
            })

def dashboard_page() -> rx.Component:
    return rx.vstack(
        rx.heading("📊 전체 포트폴리오 요약", size="7"),
        rx.hstack(
            rx.box(
                rx.text("💵 총 매입 금액 (투자 원금)", color="gray", size="2"),
                rx.text(DashboardState.total_stock_buy.to_string(format="{:,.0f}") + " 원", size="7", weight="bold"),
            ),
            rx.box(
                rx.text("📈 총 주식 평가금액 (현금 제외)", color="gray", size="2"),
                rx.text(DashboardState.total_stock_eval.to_string(format="{:,.0f}") + " 원", size="7", weight="bold"),
            ),
            rx.box(
                rx.text("총 평가 손익", color="gray", size="2"),
                rx.text(DashboardState.total_stock_profit.to_string(format="{:,.0f}") + " 원", 
                        size="7", weight="bold", 
                        color=rx.cond(DashboardState.total_stock_profit > 0, "red", rx.cond(DashboardState.total_stock_profit < 0, "blue", "gray"))),
            ),
            rx.box(
                rx.text("총 수익률", color="gray", size="2"),
                rx.text(DashboardState.total_stock_return.to_string(format="{:.1f}") + "%", 
                        size="7", weight="bold", 
                        color=rx.cond(DashboardState.total_stock_return > 0, "red", rx.cond(DashboardState.total_stock_return < 0, "blue", "gray"))),
            ),
            spacing="7",
            margin_bottom="6",
            flex_wrap="wrap"
        ),
        
        rx.heading("📈 주식 및 금현물 자산", size="5"),
        rx.data_table(
            data=DashboardState.stock_summary_rows,
            pagination=True,
            search=True,
            sort=True,
        ),
        rx.heading("💵 현금성 자산", size="5", margin_top="4"),
        rx.data_table(
            data=DashboardState.cash_summary_rows,
            pagination=False,
            search=False,
            sort=False,
        ),
        width="100%",
        align_items="flex-start",
    )
