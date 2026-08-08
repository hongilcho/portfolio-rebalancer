import reflex as rx
from typing import List, Dict, Any
from portfolio_rebalancer.state import AppState
from portfolio_rebalancer.components.navbar import navbar
from data.data_manager import get_all_assets, get_all_accounts, add_account, delete_account, add_asset, delete_asset, ACCOUNT_TYPES

class SettingsState(AppState):
    assets: List[Dict[str, Any]] = []
    accounts: List[Dict[str, Any]] = []
    
    # Account Form
    new_acc_no: str = ""
    new_acc_alias: str = ""
    new_acc_type: str = "일반매매"
    new_krw: float = 0.0
    new_usd: float = 0.0
    new_annual_limit: float = 20000000.0
    new_tax_limit: float = 0.0
    
    # Asset Form
    new_ast_name: str = ""
    new_ast_ticker: str = ""
    new_ast_market: str = "KR"
    new_ast_weight: float = 10.0
    new_ast_is_risk: bool = True
    
    def on_load(self):
        super().on_load()
        self.load_data()
        
    def load_data(self):
        self.assets = get_all_assets()
        self.accounts = get_all_accounts()
        
    def add_new_account(self):
        if not self.new_acc_no or not self.new_acc_alias:
            return rx.window_alert("계좌번호와 별명을 입력해주세요.")
            
        success, msg = add_account(
            self.new_acc_no, self.new_acc_alias, self.new_acc_type, 
            self.new_krw, self.new_usd, self.new_annual_limit, self.new_tax_limit,
            "", 99, "ANNUAL", 0.0
        )
        if success:
            self.load_data()
            self.new_acc_no = ""
            self.new_acc_alias = ""
            return rx.window_alert(msg)
        else:
            return rx.window_alert(f"오류: {msg}")
            
    def delete_acc(self, acc_id: str):
        success, msg = delete_account(int(acc_id))
        if success:
            self.load_data()
            return rx.window_alert(msg)
        else:
            return rx.window_alert(f"오류: {msg}")
            
    def add_new_asset(self):
        if not self.new_ast_name or not self.new_ast_ticker:
            return rx.window_alert("자산명과 티커를 입력해주세요.")
            
        success, msg = add_asset(
            self.new_ast_name, self.new_ast_ticker, self.new_ast_market,
            self.new_ast_weight, [], self.new_ast_is_risk, ""
        )
        if success:
            self.load_data()
            self.new_ast_name = ""
            self.new_ast_ticker = ""
            return rx.window_alert(msg)
        else:
            return rx.window_alert(f"오류: {msg}")
            
    def delete_ast(self, ast_id: str):
        success, msg = delete_asset(int(ast_id))
        if success:
            self.load_data()
            return rx.window_alert(msg)
        else:
            return rx.window_alert(f"오류: {msg}")

def settings_page() -> rx.Component:
    return rx.vstack(
        rx.heading("⚙️ 계좌/자산 등록 및 관리", size="7"),
        rx.text("새로운 계좌나 자산을 등록하고 삭제할 수 있습니다.", size="3", color="gray", margin_bottom="4"),
        
        rx.hstack(
            rx.vstack(
                rx.heading("📋 등록된 계좌 목록", size="5"),
                rx.foreach(
                    SettingsState.accounts,
                    lambda acc: rx.hstack(
                        rx.text(f"[{acc['account_type']}] {acc['account_alias']}"),
                        rx.button("삭제", on_click=lambda: SettingsState.delete_acc(acc["id"].to_string()), size="1", color_scheme="red"),
                        width="100%", justify="between"
                    )
                ),
                
                rx.divider(margin_y="4"),
                
                rx.heading("➕ 신규 계좌 등록", size="5"),
                rx.input(placeholder="계좌번호", value=SettingsState.new_acc_no, on_change=SettingsState.set_new_acc_no),
                rx.input(placeholder="별명", value=SettingsState.new_acc_alias, on_change=SettingsState.set_new_acc_alias),
                rx.select(list(ACCOUNT_TYPES.keys()), value=SettingsState.new_acc_type, on_change=SettingsState.set_new_acc_type),
                rx.hstack(
                    rx.input(placeholder="원화 예수금", type="number", value=SettingsState.new_krw.to_string(), on_change=SettingsState.set_new_krw),
                    rx.input(placeholder="달러 예수금", type="number", value=SettingsState.new_usd.to_string(), on_change=SettingsState.set_new_usd),
                ),
                rx.button("계좌 등록하기", on_click=SettingsState.add_new_account, width="100%", margin_top="2"),
                
                width="100%", padding="4", border=f"1px solid {rx.color('gray', 4)}", border_radius="md"
            ),
            
            rx.vstack(
                rx.heading("📋 등록된 자산 목록", size="5"),
                rx.foreach(
                    SettingsState.assets,
                    lambda ast: rx.hstack(
                        rx.text(f"[{ast['ticker']}] {ast['name']}"),
                        rx.button("삭제", on_click=lambda: SettingsState.delete_ast(ast["id"].to_string()), size="1", color_scheme="red"),
                        width="100%", justify="between"
                    )
                ),
                
                rx.divider(margin_y="4"),
                
                rx.heading("➕ 신규 자산 등록", size="5"),
                rx.input(placeholder="자산명", value=SettingsState.new_ast_name, on_change=SettingsState.set_new_ast_name),
                rx.input(placeholder="티커", value=SettingsState.new_ast_ticker, on_change=SettingsState.set_new_ast_ticker),
                rx.select(["KR", "US"], value=SettingsState.new_ast_market, on_change=SettingsState.set_new_ast_market),
                rx.checkbox("위험자산(IRP 제약)", checked=SettingsState.new_ast_is_risk, on_change=SettingsState.set_new_ast_is_risk),
                rx.button("자산 등록하기", on_click=SettingsState.add_new_asset, width="100%", margin_top="2"),
                
                width="100%", padding="4", border=f"1px solid {rx.color('gray', 4)}", border_radius="md"
            ),
            width="100%", spacing="6", align_items="flex-start"
        ),
        
        width="100%",
        align_items="flex-start"
    )
