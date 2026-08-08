import reflex as rx
from typing import List, Dict, Any, Set
from portfolio_rebalancer.state import AppState
from portfolio_rebalancer.components.navbar import navbar
from data.data_manager import get_all_assets, get_all_accounts, update_asset

class TargetState(AppState):
    assets: List[Dict[str, Any]] = []
    accounts: List[Dict[str, Any]] = []
    
    # Store inputs by asset ID
    weight_inputs: Dict[str, float] = {}
    account_inputs: Dict[str, List[str]] = {}
    
    total_weight: float = 0.0
    
    def on_load(self):
        super().on_load()
        self.load_data()
        
    def load_data(self):
        self.assets = get_all_assets()
        self.accounts = get_all_accounts()
        
        # Initialize inputs
        self.weight_inputs = {str(a['id']): float(a['target_weight']) for a in self.assets}
        self.account_inputs = {str(a['id']): [str(x) for x in a['allowed_accounts']] for a in self.assets}
        self.calculate_total()
        
    def calculate_total(self):
        self.total_weight = sum(self.weight_inputs.values())
        
    def set_weight(self, aid: str, value: str):
        try:
            self.weight_inputs[aid] = float(value)
            self.calculate_total()
        except ValueError:
            pass

    def toggle_account(self, aid: str, acc_id: str, checked: bool):
        current = self.account_inputs.get(aid, [])
        if checked and acc_id not in current:
            current.append(acc_id)
        elif not checked and acc_id in current:
            current.remove(acc_id)
        self.account_inputs[aid] = current
        
    def has_account(self, aid: str, acc_id: str) -> bool:
        return acc_id in self.account_inputs.get(aid, [])

        
    def save_targets(self):
        for asset in self.assets:
            aid_str = str(asset['id'])
            w = self.weight_inputs.get(aid_str, float(asset['target_weight']))
            accs = self.account_inputs.get(aid_str, asset['allowed_accounts'])
            
            update_asset(
                asset['id'], 
                asset['name'], 
                asset['ticker'], 
                asset['market'], 
                w, 
                accs, 
                asset['is_risk_asset'], 
                asset['notes']
            )
        
        # Trigger reload of app state data if needed
        self.price_data = [] # force refresh maybe?
        return rx.window_alert("저장되었습니다!")

def target_page() -> rx.Component:
    return rx.vstack(
        rx.heading("🎯 포트폴리오 목표 비중 및 계좌 매핑 설정", size="7"),
        rx.text("각 자산별 목표 비중을 설정하고, 매수할 계좌를 지정합니다.", size="3", color="gray", margin_bottom="4"),
        
        rx.foreach(
            TargetState.assets,
            lambda asset: rx.box(
                rx.vstack(
                    rx.heading(f"📌 {asset['name']} ({asset['ticker']} | {asset['market']})", size="5"),
                    rx.hstack(
                        rx.box(
                            rx.text("목표 비중 (%)", weight="bold"),
                            rx.input(
                                value=TargetState.weight_inputs[asset['id'].to_string()].to_string(),
                                on_change=lambda val: TargetState.set_weight(asset['id'].to_string(), val),
                                type="number",
                                step="0.1",
                            ),
                            width="200px"
                        ),
                        rx.box(
                            rx.text("매수/운용 계좌 선택", weight="bold", margin_bottom="2"),
                            rx.vstack(
                                rx.foreach(
                                    TargetState.accounts,
                                    lambda acc: rx.checkbox(
                                        f"[{acc['account_type']}] {acc['account_alias']}",
                                        checked=TargetState.has_account(asset['id'].to_string(), acc['id'].to_string()),
                                        on_change=lambda c: TargetState.toggle_account(asset['id'].to_string(), acc['id'].to_string(), c)
                                    )
                                ),
                                align_items="flex-start"
                            ),
                            width="400px"
                        ),
                        rx.box(
                            rx.cond(
                                asset['is_risk_asset'],
                                rx.text("🔴 위험자산 (IRP 70% 제한)", color="red", weight="bold"),
                                rx.text("🟢 안전자산", color="green", weight="bold")
                            )
                        ),
                        align_items="center",
                        spacing="6",
                        width="100%"
                    ),
                    padding="4",
                    border=f"1px solid {rx.color('gray', 4)}",
                    border_radius="md",
                    width="100%",
                    margin_bottom="4"
                )
            )
        ),
        
        rx.heading(f"🧮 설정된 목표 비중 합계: {TargetState.total_weight}%", size="6", margin_top="4"),
        rx.button("💾 목표 비중 및 계좌 매핑 저장", on_click=TargetState.save_targets, size="4", color_scheme="blue", margin_top="4"),
        
        width="100%",
        align_items="flex-start"
    )
