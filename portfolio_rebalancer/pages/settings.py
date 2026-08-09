import reflex as rx
from typing import List, Dict, Any
from portfolio_rebalancer.state import AppState
from portfolio_rebalancer.components.navbar import navbar
from data.data_manager import get_all_assets, get_all_accounts, add_account, update_account, delete_account, add_asset, update_asset, delete_asset, ACCOUNT_TYPES

class SettingsState(AppState):
    assets: List[Dict[str, Any]] = []
    accounts: List[Dict[str, Any]] = []

    # --- Add Account State ---
    new_acc_no: str = ""
    new_acc_alias: str = ""
    new_acc_type: str = "일반매매"
    new_krw: float = 0.0
    new_usd: float = 0.0
    new_annual_limit: float = 20000000.0
    new_tax_limit: float = 0.0
    new_acc_notes: str = ""
    new_acc_priority: int = 99
    new_acc_limit_pref: str = "ANNUAL"
    is_unlimited: bool = False

    def set_new_krw(self, val: str):
        try: self.new_krw = float(val)
        except ValueError: pass
    def set_new_usd(self, val: str):
        try: self.new_usd = float(val)
        except ValueError: pass
    def set_new_annual_limit(self, val: str):
        try: self.new_annual_limit = float(val)
        except ValueError: pass
    def set_new_tax_limit(self, val: str):
        try: self.new_tax_limit = float(val)
        except ValueError: pass
    def set_new_acc_priority(self, val: str):
        try: self.new_acc_priority = int(val)
        except ValueError: pass
        
    def set_is_unlimited(self, val: bool):
        self.is_unlimited = val
    
    # --- Edit Account State ---
    edit_acc_id: int = -1
    edit_acc_no: str = ""
    edit_acc_alias: str = ""
    edit_acc_type: str = "일반매매"
    edit_krw: float = 0.0
    edit_usd: float = 0.0
    edit_annual_limit: float = 20000000.0
    edit_tax_limit: float = 0.0
    edit_acc_notes: str = ""
    edit_acc_priority: int = 99
    edit_acc_limit_pref: str = "ANNUAL"
    edit_is_unlimited: bool = False
    
    def select_edit_account(self, acc_id_str: str):
        acc_id = int(acc_id_str)
        self.edit_acc_id = acc_id
        for acc in self.accounts:
            if acc["id"] == acc_id:
                self.edit_acc_no = acc["account_no"]
                self.edit_acc_alias = acc["account_alias"]
                self.edit_acc_type = acc["account_type"]
                self.edit_krw = float(acc["deposit_krw"])
                self.edit_usd = float(acc["deposit_usd"])
                self.edit_annual_limit = float(acc.get("annual_limit", 0))
                self.edit_tax_limit = float(acc.get("tax_limit", 0))
                self.edit_acc_notes = acc.get("notes", "")
                self.edit_acc_priority = int(acc.get("priority", 99))
                self.edit_acc_limit_pref = acc.get("limit_preference", "ANNUAL")
                self.edit_is_unlimited = (self.edit_annual_limit == 0 and self.edit_tax_limit == 0)
                break
                
    def set_edit_krw(self, val: str):
        try: self.edit_krw = float(val)
        except ValueError: pass
    def set_edit_usd(self, val: str):
        try: self.edit_usd = float(val)
        except ValueError: pass
    def set_edit_annual_limit(self, val: str):
        try: self.edit_annual_limit = float(val)
        except ValueError: pass
    def set_edit_tax_limit(self, val: str):
        try: self.edit_tax_limit = float(val)
        except ValueError: pass
    def set_edit_acc_priority(self, val: str):
        try: self.edit_acc_priority = int(val)
        except ValueError: pass
        
    def set_edit_is_unlimited(self, val: bool):
        self.edit_is_unlimited = val

    # --- Add Asset State ---
    is_gold_new: bool = False
    new_ast_name: str = ""
    new_ast_ticker: str = ""
    new_ast_market: str = "KR"
    new_ast_weight: float = 10.0
    new_ast_is_risk: bool = True
    new_ast_notes: str = ""
    new_ast_allowed_accs: List[str] = []

    def set_new_ast_weight(self, val: str):
        try: self.new_ast_weight = float(val)
        except ValueError: pass
        
    def set_is_gold_new(self, val: bool):
        self.is_gold_new = val

    # --- Edit Asset State ---
    edit_ast_id: int = -1
    edit_is_gold: bool = False
    edit_ast_name: str = ""
    edit_ast_ticker: str = ""
    edit_ast_market: str = "KR"
    edit_ast_weight: float = 10.0
    edit_ast_is_risk: bool = True
    edit_ast_notes: str = ""
    edit_ast_allowed_accs: List[str] = []
    
    def select_edit_asset(self, ast_id_str: str):
        ast_id = int(ast_id_str)
        self.edit_ast_id = ast_id
        for ast in self.assets:
            if ast["id"] == ast_id:
                self.edit_is_gold = (ast["ticker"] == "없음")
                self.edit_ast_name = ast["name"]
                self.edit_ast_ticker = ast["ticker"]
                self.edit_ast_market = ast["market"]
                self.edit_ast_weight = float(ast["target_weight"])
                self.edit_ast_is_risk = bool(ast["is_risk_asset"])
                self.edit_ast_notes = ast.get("notes", "")
                self.edit_ast_allowed_accs = [str(x) for x in ast.get("allowed_accounts", [])]
                break

    def set_edit_ast_weight(self, val: str):
        try: self.edit_ast_weight = float(val)
        except ValueError: pass
        
    def set_edit_is_gold(self, val: bool):
        self.edit_is_gold = val


    @rx.var
    def price_data_list(self) -> List[Dict[str, Any]]:
        return list(self.price_data.values())


    # --- Auto-generated String & Bool Setters ---
    def set_new_acc_no(self, val: str): self.new_acc_no = val
    def set_new_acc_alias(self, val: str): self.new_acc_alias = val
    def set_new_acc_type(self, val: str): self.new_acc_type = val
    def set_new_acc_notes(self, val: str): self.new_acc_notes = val
    def set_new_acc_limit_pref(self, val: str): self.new_acc_limit_pref = val
    
    def set_edit_acc_no(self, val: str): self.edit_acc_no = val
    def set_edit_acc_alias(self, val: str): self.edit_acc_alias = val
    def set_edit_acc_type(self, val: str): self.edit_acc_type = val
    def set_edit_acc_notes(self, val: str): self.edit_acc_notes = val
    def set_edit_acc_limit_pref(self, val: str): self.edit_acc_limit_pref = val
    
    def set_new_ast_name(self, val: str): self.new_ast_name = val
    def set_new_ast_ticker(self, val: str): self.new_ast_ticker = val
    def set_new_ast_market(self, val: str): self.new_ast_market = val
    def set_new_ast_notes(self, val: str): self.new_ast_notes = val
    def set_new_ast_is_risk(self, val: bool): self.new_ast_is_risk = val
    def set_new_ast_allowed_accs(self, val: list): self.new_ast_allowed_accs = val
    
    def set_edit_ast_name(self, val: str): self.edit_ast_name = val
    def set_edit_ast_ticker(self, val: str): self.edit_ast_ticker = val
    def set_edit_ast_market(self, val: str): self.edit_ast_market = val
    def set_edit_ast_notes(self, val: str): self.edit_ast_notes = val
    def set_edit_ast_is_risk(self, val: bool): self.edit_ast_is_risk = val
    def set_edit_ast_allowed_accs(self, val: list): self.edit_ast_allowed_accs = val


    def set_edit_acc_id(self, val: int): self.edit_acc_id = val
    def set_edit_ast_id(self, val: int): self.edit_ast_id = val

    def on_load(self):
        super().on_load()
        self.load_data()
        
    def load_data(self):
        self.assets = get_all_assets()
        self.accounts = get_all_accounts()
        
    # --- Actions ---
    def add_new_account(self):
        if not self.new_acc_no or not self.new_acc_alias:
            return rx.window_alert("계좌번호와 별명을 입력해주세요.")
        ann = 0.0 if self.is_unlimited else self.new_annual_limit
        tax = 0.0 if self.is_unlimited else self.new_tax_limit
        success, msg = add_account(
            self.new_acc_no, self.new_acc_alias, self.new_acc_type, 
            self.new_krw, self.new_usd, ann, tax,
            self.new_acc_notes, self.new_acc_priority, self.new_acc_limit_pref, 0.0
        )
        if success:
            self.load_data()
            self.new_acc_no = ""
            self.new_acc_alias = ""
            return rx.window_alert(msg)
        return rx.window_alert(f"오류: {msg}")

    def submit_edit_account(self):
        if self.edit_acc_id == -1: return
        ann = 0.0 if self.edit_is_unlimited else self.edit_annual_limit
        tax = 0.0 if self.edit_is_unlimited else self.edit_tax_limit
        
        # Get current_year_deposit from existing account
        curr_dep = 0.0
        for a in self.accounts:
            if a["id"] == self.edit_acc_id:
                curr_dep = float(a.get("current_year_deposit", 0.0))
                break
                
        success, msg = update_account(
            self.edit_acc_id, self.edit_acc_no, self.edit_acc_alias, self.edit_acc_type, 
            self.edit_krw, self.edit_usd, ann, tax,
            self.edit_acc_notes, self.edit_acc_priority, self.edit_acc_limit_pref, curr_dep
        )
        if success:
            self.load_data()
            self.edit_acc_id = -1
            return rx.window_alert(msg)
        return rx.window_alert(f"오류: {msg}")
            
    def delete_acc(self, acc_id: str):
        success, msg = delete_account(int(acc_id))
        if success:
            self.load_data()
            return rx.window_alert(msg)
        return rx.window_alert(f"오류: {msg}")
            
    def add_new_asset(self):
        if not self.new_ast_name:
            return rx.window_alert("자산명을 입력해주세요.")
        tic = "없음" if self.is_gold_new else self.new_ast_ticker
        accs = [int(x.strip()) for x in self.new_ast_allowed_accs if x.strip()]
        success, msg = add_asset(
            self.new_ast_name, tic, self.new_ast_market,
            self.new_ast_weight, accs, self.new_ast_is_risk, self.new_ast_notes
        )
        if success:
            self.load_data()
            self.new_ast_name = ""
            self.new_ast_ticker = ""
            return rx.window_alert(msg)
        return rx.window_alert(f"오류: {msg}")
        
    def submit_edit_asset(self):
        if self.edit_ast_id == -1: return
        tic = "없음" if self.edit_is_gold else self.edit_ast_ticker
        accs = [int(x.strip()) for x in self.edit_ast_allowed_accs if x.strip()]
        success, msg = update_asset(
            self.edit_ast_id, self.edit_ast_name, tic, self.edit_ast_market,
            self.edit_ast_weight, accs, self.edit_ast_is_risk, self.edit_ast_notes
        )
        if success:
            self.load_data()
            self.edit_ast_id = -1
            return rx.window_alert(msg)
        return rx.window_alert(f"오류: {msg}")

    def delete_ast(self, ast_id: str):
        success, msg = delete_asset(int(ast_id))
        if success:
            self.load_data()
            return rx.window_alert(msg)
        return rx.window_alert(f"오류: {msg}")



def form_field(label: str, component: rx.Component) -> rx.Component:
    return rx.vstack(
        rx.text(label, size="2", weight="bold", color="gray"),
        component,
        width="100%", spacing="1"
    )

def settings_page() -> rx.Component:
    return rx.vstack(
        rx.heading("⚙️ 계좌/자산 등록 및 관리", size="7"),
        rx.text("실시간 시세를 조회하고 계좌나 자산을 등록, 수정, 삭제할 수 있습니다.", size="3", color="gray", margin_bottom="4"),
        
        # --- Live Price Viewer ---
        rx.card(
            rx.vstack(
                rx.heading("📊 실시간 시세 현황", size="5"),
                rx.cond(
                    SettingsState.price_data,
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("종목명"),
                                rx.table.column_header_cell("티커"),
                                rx.table.column_header_cell("위험 구분"),
                                rx.table.column_header_cell("시장"),
                                rx.table.column_header_cell("목표 비중"),
                                rx.table.column_header_cell("현재가(현지)"),
                                rx.table.column_header_cell("원화 환산가"),
                                rx.table.column_header_cell("상태")
                            )
                        ),
                        rx.table.body(
                            rx.foreach(
                                SettingsState.price_data_list,
                                lambda item: rx.table.row(
                                    rx.table.cell(item['name']),
                                    rx.table.cell(rx.badge(item['ticker'])),
                                    rx.table.cell(rx.cond(item['is_risk_asset'], "🔴 위험자산", "🟢 안전자산")),
                                    rx.table.cell(rx.cond(item['market'] == 'KR', "🇰🇷 국내", "🇺🇸 미국")),
                                    rx.table.cell(item['target_weight'], "%"),
                                    rx.table.cell(rx.cond(item['market'] == 'KR', item['price_native'].to_string() + " 원", "$ " + item['price_native'].to_string())),
                                    rx.table.cell(item['price_krw'], " 원"),
                                    rx.table.cell(item['status'])
                                )
                            )
                        ),
                        width="100%", variant="surface", size="2"
                    ),
                    rx.text("조회된 시세 데이터가 없습니다. 대시보드에서 시세를 업데이트 해주세요.", color="orange")
                ),
                width="100%"
            ),
            width="100%", margin_bottom="6"
        ),
        
        rx.vstack(
            # Account Section
            rx.card(
                rx.vstack(
                    rx.heading("📋 등록된 계좌 관리", size="5"),
                    rx.text("등록된 모든 계좌의 목록입니다.", color="gray", size="2"),
                    
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("유형"),
                                rx.table.column_header_cell("별명/계좌번호"),
                                rx.table.column_header_cell("원화 예수금"),
                                rx.table.column_header_cell("달러 예수금"),
                                rx.table.column_header_cell("연납입/비과세 한도"),
                                rx.table.column_header_cell("우선순위/방식"),
                                rx.table.column_header_cell("관리")
                            )
                        ),
                        rx.table.body(
                            rx.foreach(
                                SettingsState.accounts,
                                lambda acc: rx.table.row(
                                    rx.table.cell(rx.badge(acc['account_type'])),
                                    rx.table.cell(acc['account_alias'], " (", acc['account_no'], ")"),
                                    rx.table.cell(acc['deposit_krw'], " 원"),
                                    rx.table.cell("$ ", acc['deposit_usd']),
                                    rx.table.cell(acc['annual_limit'], " / ", acc['tax_limit']),
                                    rx.table.cell("우선순위:", acc['priority'], " (", acc['limit_preference'], ")"),
                                    rx.table.cell(
                                        rx.hstack(
                                            rx.button("수정", on_click=lambda: SettingsState.select_edit_account(acc["id"].to_string()), size="1", variant="soft"),
                                            rx.button("삭제", on_click=lambda: SettingsState.delete_acc(acc["id"].to_string()), size="1", color_scheme="red")
                                        )
                                    ),
                                )
                            )
                        ),
                        width="100%", variant="surface",
                    ),
                    
                    rx.divider(margin_y="4"),
                    
                    rx.accordion.root(
                        rx.accordion.item(
                            header=rx.heading("➕ 신규 계좌 등록", size="4"),
                            content=rx.box(
                                rx.hstack(
                                    rx.text("한도 제한 없음 (종합매매 등)", weight="bold"),
                                    rx.switch(checked=SettingsState.is_unlimited, on_change=SettingsState.set_is_unlimited, size="2", color_scheme="indigo"),
                                    justify="between", width="100%", padding="3", background_color="var(--gray-2)", border_radius="md", margin_bottom="4"
                                ),
                                rx.grid(
                                    form_field("계좌번호", rx.input(placeholder="계좌번호 입력", value=SettingsState.new_acc_no, on_change=SettingsState.set_new_acc_no)),
                                    form_field("별명", rx.input(placeholder="예: ISA, IRP", value=SettingsState.new_acc_alias, on_change=SettingsState.set_new_acc_alias)),
                                    form_field("계좌 종류", rx.select(list(ACCOUNT_TYPES.keys()), value=SettingsState.new_acc_type, on_change=SettingsState.set_new_acc_type)),
                                    form_field("매수 우선순위", rx.input(placeholder="작을수록 먼저 매수", type="number", value=SettingsState.new_acc_priority.to_string(), on_change=SettingsState.set_new_acc_priority)),
                                    form_field("원화 예수금", rx.input(placeholder="0", type="number", value=SettingsState.new_krw.to_string(), on_change=SettingsState.set_new_krw)),
                                    form_field("달러 예수금", rx.input(placeholder="0.0", type="number", value=SettingsState.new_usd.to_string(), on_change=SettingsState.set_new_usd)),
                                    form_field("연납입 한도", rx.input(placeholder="0", type="number", value=SettingsState.new_annual_limit.to_string(), on_change=SettingsState.set_new_annual_limit, disabled=SettingsState.is_unlimited)),
                                    form_field("비과세 한도", rx.input(placeholder="0", type="number", value=SettingsState.new_tax_limit.to_string(), on_change=SettingsState.set_new_tax_limit, disabled=SettingsState.is_unlimited)),
                                    form_field("한도 우선 적용", rx.select(["ANNUAL", "TAX"], value=SettingsState.new_acc_limit_pref, on_change=SettingsState.set_new_acc_limit_pref)),
                                    form_field("메모", rx.input(placeholder="메모 입력", value=SettingsState.new_acc_notes, on_change=SettingsState.set_new_acc_notes)),
                                    columns="2", spacing="4", width="100%"
                                ),
                                rx.button("계좌 등록하기", on_click=SettingsState.add_new_account, width="100%", size="3", margin_top="4"),
                                width="100%"
                            ),
                            value="add_acc"
                        ),
                        collapsible=True, type="multiple", width="100%"
                    ),
                    rx.cond(
                        SettingsState.edit_acc_id != -1,
                        rx.accordion.root(
                            rx.accordion.item(
                                header=rx.heading("✏️ 선택된 계좌 수정", size="4"),
                                content=rx.box(
                                    rx.hstack(
                                        rx.text("한도 제한 없음 (종합매매 등)", weight="bold"),
                                        rx.switch(checked=SettingsState.edit_is_unlimited, on_change=SettingsState.set_edit_is_unlimited, size="2", color_scheme="indigo"),
                                        justify="between", width="100%", padding="3", background_color="var(--gray-2)", border_radius="md", margin_bottom="4"
                                    ),
                                    rx.grid(
                                        form_field("계좌번호", rx.input(placeholder="계좌번호", value=SettingsState.edit_acc_no, on_change=SettingsState.set_edit_acc_no)),
                                        form_field("별명", rx.input(placeholder="별명", value=SettingsState.edit_acc_alias, on_change=SettingsState.set_edit_acc_alias)),
                                        form_field("계좌 종류", rx.select(list(ACCOUNT_TYPES.keys()), value=SettingsState.edit_acc_type, on_change=SettingsState.set_edit_acc_type)),
                                        form_field("매수 우선순위", rx.input(placeholder="매수 우선순위", type="number", value=SettingsState.edit_acc_priority.to_string(), on_change=SettingsState.set_edit_acc_priority)),
                                        form_field("원화 예수금", rx.input(placeholder="0", type="number", value=SettingsState.edit_krw.to_string(), on_change=SettingsState.set_edit_krw)),
                                        form_field("달러 예수금", rx.input(placeholder="0.0", type="number", value=SettingsState.edit_usd.to_string(), on_change=SettingsState.set_edit_usd)),
                                        form_field("연납입 한도", rx.input(placeholder="0", type="number", value=SettingsState.edit_annual_limit.to_string(), on_change=SettingsState.set_edit_annual_limit, disabled=SettingsState.edit_is_unlimited)),
                                        form_field("비과세 한도", rx.input(placeholder="0", type="number", value=SettingsState.edit_tax_limit.to_string(), on_change=SettingsState.set_edit_tax_limit, disabled=SettingsState.edit_is_unlimited)),
                                        form_field("한도 우선 적용", rx.select(["ANNUAL", "TAX"], value=SettingsState.edit_acc_limit_pref, on_change=SettingsState.set_edit_acc_limit_pref)),
                                        form_field("메모", rx.input(placeholder="메모", value=SettingsState.edit_acc_notes, on_change=SettingsState.set_edit_acc_notes)),
                                        columns="2", spacing="4", width="100%"
                                    ),
                                    rx.grid(
                                        rx.button("수정 저장하기", on_click=SettingsState.submit_edit_account, size="3"),
                                        rx.button("취소", on_click=SettingsState.set_edit_acc_id(-1), variant="soft", size="3"),
                                        columns="2", spacing="4", width="100%", margin_top="4"
                                    ),
                                    width="100%"
                                ),
                                value="edit_acc"
                            ),
                            collapsible=True, type="multiple", width="100%"
                        ),
                        rx.box()
                    ),
                    width="100%",
                ),
                width="100%", margin_bottom="6",
            ),
            
            # Asset Section
            rx.card(
                rx.vstack(
                    rx.heading("📋 등록된 자산 관리", size="5"),
                    rx.text("관리 중인 전체 자산 목록입니다.", color="gray", size="2"),
                    
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("티커"),
                                rx.table.column_header_cell("자산명"),
                                rx.table.column_header_cell("시장"),
                                rx.table.column_header_cell("위험자산"),
                                rx.table.column_header_cell("관리")
                            )
                        ),
                        rx.table.body(
                            rx.foreach(
                                SettingsState.assets,
                                lambda ast: rx.table.row(
                                    rx.table.cell(rx.badge(ast['ticker'], color_scheme="indigo")),
                                    rx.table.cell(ast['name']),
                                    rx.table.cell(ast['market']),
                                    rx.table.cell(rx.cond(ast['is_risk_asset'], rx.badge("위험자산", color_scheme="red"), rx.badge("안전자산", color_scheme="green"))),
                                    rx.table.cell(
                                        rx.hstack(
                                            rx.button("수정", on_click=lambda: SettingsState.select_edit_asset(ast["id"].to_string()), size="1", variant="soft"),
                                            rx.button("삭제", on_click=lambda: SettingsState.delete_ast(ast["id"].to_string()), size="1", color_scheme="red")
                                        )
                                    ),
                                )
                            )
                        ),
                        width="100%", variant="surface",
                    ),
                    
                    rx.divider(margin_y="4"),
                    
                    rx.accordion.root(
                        rx.accordion.item(
                            header=rx.heading("➕ 신규 자산 등록", size="4"),
                            content=rx.box(
                                rx.grid(
                                    rx.hstack(
                                        rx.text("KRX 실물 금 등록 (티커 불필요)", weight="bold"),
                                        rx.switch(checked=SettingsState.is_gold_new, on_change=SettingsState.set_is_gold_new, size="2", color_scheme="amber"),
                                        justify="between", width="100%", padding="3", background_color="var(--gray-2)", border_radius="md"
                                    ),
                                    rx.hstack(
                                        rx.text("위험자산 (IRP 70% 룰 적용)", weight="bold"),
                                        rx.switch(checked=SettingsState.new_ast_is_risk, on_change=SettingsState.set_new_ast_is_risk, size="2", color_scheme="red"),
                                        justify="between", width="100%", padding="3", background_color="var(--gray-2)", border_radius="md"
                                    ),
                                    columns="2", spacing="4", width="100%", margin_bottom="4"
                                ),
                                rx.grid(
                                    form_field("자산명", rx.input(placeholder="예: S&P500", value=SettingsState.new_ast_name, on_change=SettingsState.set_new_ast_name)),
                                    form_field("티커", rx.input(placeholder="티커", value=SettingsState.new_ast_ticker, on_change=SettingsState.set_new_ast_ticker, disabled=SettingsState.is_gold_new)),
                                    form_field("시장", rx.select(["KR", "US"], value=SettingsState.new_ast_market, on_change=SettingsState.set_new_ast_market)),
                                    form_field("메모", rx.input(placeholder="메모 입력", value=SettingsState.new_ast_notes, on_change=SettingsState.set_new_ast_notes)),
                                    columns="2", spacing="4", width="100%"
                                ),
                                rx.button("자산 등록하기", on_click=SettingsState.add_new_asset, width="100%", size="3", margin_top="4"),
                                width="100%"
                            ),
                            value="add_ast"
                        ),
                        collapsible=True, type="multiple", width="100%"
                    ),
                    rx.cond(
                        SettingsState.edit_ast_id != -1,
                        rx.accordion.root(
                            rx.accordion.item(
                                header=rx.heading("✏️ 선택된 자산 수정", size="4"),
                                content=rx.box(
                                    rx.grid(
                                        rx.hstack(
                                            rx.text("KRX 실물 금", weight="bold"),
                                            rx.switch(checked=SettingsState.edit_is_gold, on_change=SettingsState.set_edit_is_gold, size="2", color_scheme="amber"),
                                            justify="between", width="100%", padding="3", background_color="var(--gray-2)", border_radius="md"
                                        ),
                                        rx.hstack(
                                            rx.text("위험자산", weight="bold"),
                                            rx.switch(checked=SettingsState.edit_ast_is_risk, on_change=SettingsState.set_edit_ast_is_risk, size="2", color_scheme="red"),
                                            justify="between", width="100%", padding="3", background_color="var(--gray-2)", border_radius="md"
                                        ),
                                        columns="2", spacing="4", width="100%", margin_bottom="4"
                                    ),
                                    rx.grid(
                                        form_field("자산명", rx.input(placeholder="자산명", value=SettingsState.edit_ast_name, on_change=SettingsState.set_edit_ast_name)),
                                        form_field("티커", rx.input(placeholder="티커", value=SettingsState.edit_ast_ticker, on_change=SettingsState.set_edit_ast_ticker, disabled=SettingsState.edit_is_gold)),
                                        form_field("시장", rx.select(["KR", "US"], value=SettingsState.edit_ast_market, on_change=SettingsState.set_edit_ast_market)),
                                        form_field("메모", rx.input(placeholder="메모", value=SettingsState.edit_ast_notes, on_change=SettingsState.set_edit_ast_notes)),
                                        columns="2", spacing="4", width="100%"
                                    ),
                                    rx.grid(
                                        rx.button("수정 저장하기", on_click=SettingsState.submit_edit_asset, size="3"),
                                        rx.button("취소", on_click=SettingsState.set_edit_ast_id(-1), variant="soft", size="3"),
                                        columns="2", spacing="4", width="100%", margin_top="4"
                                    ),
                                    width="100%"
                                ),
                                value="edit_ast"
                            ),
                            collapsible=True, type="multiple", width="100%"
                        ),
                        rx.box()
                    ),
                    width="100%",
                ),
                width="100%",
            ),
            width="100%",
            align_items="stretch"
        ),
        
        width="100%",
        align_items="flex-start"
    )
