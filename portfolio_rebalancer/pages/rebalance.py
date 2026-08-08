import reflex as rx
from typing import List, Dict, Any
from portfolio_rebalancer.state import AppState
from portfolio_rebalancer.components.navbar import navbar
from data.data_manager import get_all_assets, get_all_accounts, get_holdings_by_account
from logic.rebalance_calculator import calculate_rebalancing_plan

class RebalanceState(AppState):
    assets: List[Dict[str, Any]] = []
    accounts: List[Dict[str, Any]] = []
    
    scenario: str = "NEW_CASH"
    new_cash_in: float = 0.0
    drift_threshold: float = 5.0
    
    run_success: bool = False
    run_message: str = ""
    has_run: bool = False
    
    trade_plan: List[Dict[str, Any]] = []
    transfer_plan: List[Dict[str, Any]] = []
    simulated_assets: List[Dict[str, Any]] = []
    
    def on_load(self):
        super().on_load()
        self.assets = get_all_assets()
        self.accounts = get_all_accounts()
        
    def run_rebalance(self):
        self.has_run = True
        
        if not self.assets or not self.accounts:
            self.run_success = False
            self.run_message = "자산과 계좌를 먼저 등록해주세요."
            return
            
        total_krw_cash = sum(a['deposit_krw'] for a in self.accounts if a['account_type'] != 'CMA')
        
        holdings_raw = []
        for a in self.accounts:
            holdings_raw.extend(get_holdings_by_account(a['id']))
            
        price_map = {}
        if self.price_data:
            for item in self.price_data:
                price_map[str(item['id'])] = item['price_krw']
                
        portfolio_assets = {}
        for h in holdings_raw:
            aid = str(h['asset_id'])
            qty = h['quantity']
            price = price_map.get(aid, 0.0)
            if aid not in portfolio_assets:
                portfolio_assets[aid] = {'qty': 0, 'eval_amt_krw': 0, 'buy_amt_krw': 0}
            portfolio_assets[aid]['qty'] += qty
            portfolio_assets[aid]['eval_amt_krw'] += qty * price
            portfolio_assets[aid]['buy_amt_krw'] += qty * h['avg_price']
            
        t_plan, tr_plan, sim_assets, success, msg = calculate_rebalancing_plan(
            assets=self.assets,
            portfolio_assets=portfolio_assets,
            accounts=self.accounts,
            holdings=holdings_raw,
            price_map=price_map,
            total_krw_cash=total_krw_cash,
            usd_krw_rate=self.usd_krw,
            scenario=self.scenario,
            new_cash_krw=self.new_cash_in,
            drift_threshold=self.drift_threshold
        )
        
        self.run_success = success
        self.run_message = msg
        
        if success:
            self.trade_plan = []
            for t in t_plan:
                self.trade_plan.append({
                    "account": t['account_alias'],
                    "type": "🔴 매도" if t['type'] == 'SELL' else "🔵 매수",
                    "asset": t['asset_name'],
                    "qty": t['qty'],
                    "price": t['price'],
                    "total": t['total_krw']
                })
                
            self.transfer_plan = []
            for tr in tr_plan:
                self.transfer_plan.append({
                    "type": "📥 입금" if tr['type'] == 'DEPOSIT' else "✔️ 기타",
                    "msg": tr['msg']
                })
                
            self.simulated_assets = []
            total_sim = sum(s['projected_val'] for s in sim_assets)
            for s in sim_assets:
                projected_w = (s['projected_val'] / total_sim * 100) if total_sim > 0 else 0
                drift = projected_w - s['target_weight']
                self.simulated_assets.append({
                    "name": s['asset_name'],
                    "final_qty": s['current_qty'] + s['qty_diff'],
                    "qty_diff": s['qty_diff'],
                    "val": s['projected_val'],
                    "target_w": s['target_weight'],
                    "projected_w": projected_w,
                    "drift": drift
                })
        else:
            self.trade_plan = []
            self.transfer_plan = []
            self.simulated_assets = []
            
    def clear_results(self):
        self.has_run = False
        self.trade_plan = []
        self.transfer_plan = []
        self.simulated_assets = []

def rebalance_page() -> rx.Component:
    return rx.vstack(
        rx.heading("⚖️ 리밸런싱 전략 수립", size="7"),
        rx.text("현재 자산 상태와 목표 비중을 바탕으로 구체적인 매매/이체 지시서를 생성합니다.", size="3", color="gray", margin_bottom="4"),
        
        rx.hstack(
            rx.vstack(
                rx.text("시나리오 선택", weight="bold"),
                rx.radio(
                    ["NEW_CASH", "DRIFT"],
                    value=RebalanceState.scenario,
                    on_change=RebalanceState.set_scenario,
                    direction="row"
                )
            ),
            rx.vstack(
                rx.text("신규 투입 현금액", weight="bold"),
                rx.input(
                    type="number",
                    value=RebalanceState.new_cash_in.to_string(),
                    on_change=RebalanceState.set_new_cash_in
                )
            ),
            rx.vstack(
                rx.text("허용 괴리율 (%)", weight="bold"),
                rx.input(
                    type="number",
                    value=RebalanceState.drift_threshold.to_string(),
                    on_change=RebalanceState.set_drift_threshold,
                    #disabled=RebalanceState.scenario == "NEW_CASH"
                )
            ),
            spacing="6",
            align_items="flex-start",
            margin_bottom="4"
        ),
        
        rx.button("🚀 리밸런싱 전략 계산하기", on_click=RebalanceState.run_rebalance, size="4", color_scheme="green", width="100%", margin_bottom="6"),
        
        rx.cond(
            RebalanceState.has_run,
            rx.vstack(
                rx.cond(
                    RebalanceState.run_success,
                    rx.box(
                        rx.heading("1️⃣ 자금 이체 지시서", size="5"),
                        rx.foreach(
                            RebalanceState.transfer_plan,
                            lambda tp: rx.text(tp["msg"])
                        ),
                        
                        rx.heading("2️⃣ 매매 지시서", size="5", margin_top="4"),
                        rx.data_table(
                            data=RebalanceState.trade_plan,
                            pagination=False,
                            search=False,
                            sort=False
                        ),
                        
                        rx.heading("📊 리밸런싱 후 예상 포트폴리오 비중", size="5", margin_top="4"),
                        rx.data_table(
                            data=RebalanceState.simulated_assets,
                            pagination=False,
                            search=False,
                            sort=False
                        ),
                        
                        rx.button("🗑️ 계산 결과 지우기", on_click=RebalanceState.clear_results, width="100%", margin_top="4"),
                        width="100%"
                    ),
                    rx.text(RebalanceState.run_message, color="red")
                ),
                width="100%"
            ),
            rx.box()
        ),
        
        width="100%",
        align_items="flex-start"
    )
