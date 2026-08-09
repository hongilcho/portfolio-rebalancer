import reflex as rx
from typing import List, Dict, Any
import datetime
import uuid
from portfolio_rebalancer.state import AppState
from portfolio_rebalancer.components.navbar import navbar
from data.data_manager import get_all_assets, get_all_accounts, execute_trade, get_trade_history, delete_trade

class HistoryState(AppState):
    assets: List[Dict[str, Any]] = []
    accounts: List[Dict[str, Any]] = []
    trade_history: List[Dict[str, str]] = []
    
    # Simple list of dicts for rows
    buy_rows: List[Dict[str, Any]] = []
    sell_rows: List[Dict[str, Any]] = []
    
    trade_date: str = ""
    
    @rx.var
    def account_options(self) -> List[str]:
        return [f"{a['id']}: [{a['account_type']}] {a['account_alias']}" for a in self.accounts]
        
    @rx.var
    def asset_options(self) -> List[str]:
        return [f"{a['id']}: {a['name']} ({a['ticker']})" for a in self.assets]
        
    def set_trade_date(self, value: str):
        self.trade_date = value
    
    def on_load(self):
        super().on_load()
        self.load_data()
        
    def load_data(self):
        self.assets = get_all_assets()
        self.accounts = get_all_accounts()
        self.load_history()
        
        if not self.buy_rows:
            self.add_buy_row()
        if not self.sell_rows:
            self.add_sell_row()
            
        KST = datetime.timezone(datetime.timedelta(hours=9))
        if not self.trade_date:
            self.trade_date = datetime.datetime.now(KST).strftime("%Y-%m-%d")
            
    def load_history(self):
        history = get_trade_history()
        # format it for display
        formatted = []
        for t in history:
            formatted.append({
                "date": t["trade_date"],
                "account": f"[{t['account_type']}] {t['account_alias']}",
                "asset": t["asset_name"],
                "type": "🔴 매도" if t["trade_type"] == "SELL" else "🔵 매수",
                "qty": f"{int(t['quantity'])}" if t['quantity'] == int(t['quantity']) else str(t['quantity']),
                "price": f"{t['price']:,.0f} 원",
                "total": f"{t['quantity'] * t['price']:,.0f} 원",
                "id": str(t["id"])
            })
        self.trade_history = formatted
        
    def add_buy_row(self):
        self.buy_rows.append({
            "id": str(uuid.uuid4()),
            "acc_id": "",
            "ast_id": "",
            "qty": 0.0,
            "price": 0.0
        })
        
    def remove_buy_row(self, row_id: str):
        if len(self.buy_rows) > 1:
            self.buy_rows = [r for r in self.buy_rows if r["id"] != row_id]
            
    def set_buy_value(self, row_id: str, field: str, value: str):
        for i, row in enumerate(self.buy_rows):
            if row["id"] == row_id:
                if field in ["acc_id", "ast_id"]:
                    self.buy_rows[i][field] = value
                    if field == "ast_id" and value:
                        ast_id_str = value.split(":")[0]
                        if ast_id_str in self.price_data:
                            self.buy_rows[i]["price"] = self.price_data[ast_id_str].get("price_krw", 0.0)
                elif field in ["qty", "price"]:
                    try:
                        self.buy_rows[i][field] = float(value) if value else 0.0
                    except:
                        pass
                else:
                    self.buy_rows[i][field] = value
                break

    def add_sell_row(self):
        self.sell_rows.append({
            "id": str(uuid.uuid4()),
            "acc_id": "",
            "ast_id": "",
            "qty": 0.0,
            "price": 0.0
        })
        
    def remove_sell_row(self, row_id: str):
        if len(self.sell_rows) > 1:
            self.sell_rows = [r for r in self.sell_rows if r["id"] != row_id]
            
    def set_sell_value(self, row_id: str, field: str, value: str):
        for i, row in enumerate(self.sell_rows):
            if row["id"] == row_id:
                if field in ["acc_id", "ast_id"]:
                    self.sell_rows[i][field] = value
                    if field == "ast_id" and value:
                        ast_id_str = value.split(":")[0]
                        if ast_id_str in self.price_data:
                            self.sell_rows[i]["price"] = self.price_data[ast_id_str].get("price_krw", 0.0)
                elif field in ["qty", "price"]:
                    try:
                        self.sell_rows[i][field] = float(value) if value else 0.0
                    except:
                        pass
                else:
                    self.sell_rows[i][field] = value
                break

    def save_trades(self):
        success_count = 0
        errors = []
        
        for r in self.buy_rows:
            if r["acc_id"] and r["ast_id"] and float(r["qty"]) > 0:
                acc_id = int(r["acc_id"].split(":")[0])
                ast_id = int(r["ast_id"].split(":")[0])
                s, m = execute_trade(self.trade_date, acc_id, ast_id, "BUY", float(r["qty"]), float(r["price"]))
                if s: success_count += 1
                else: errors.append(m)
                
        for r in self.sell_rows:
            if r["acc_id"] and r["ast_id"] and float(r["qty"]) > 0:
                acc_id = int(r["acc_id"].split(":")[0])
                ast_id = int(r["ast_id"].split(":")[0])
                s, m = execute_trade(self.trade_date, acc_id, ast_id, "SELL", float(r["qty"]), float(r["price"]))
                if s: success_count += 1
                else: errors.append(m)
                
        if errors:
            return rx.window_alert("일부 처리에 실패했습니다:\n" + "\n".join(errors))
        if success_count > 0:
            self.buy_rows = []
            self.sell_rows = []
            self.add_buy_row()
            self.add_sell_row()
            self.load_history()
            return rx.window_alert(f"{success_count}건의 매매 기록이 성공적으로 저장되었습니다!")
            
    def delete_selected_trade(self, trade_id: str):
        success, msg = delete_trade(int(trade_id))
        if success:
            self.load_history()
            return rx.window_alert("기록이 성공적으로 삭제 및 복구되었습니다!")
        else:
            return rx.window_alert(f"삭제 실패: {msg}")

def history_page() -> rx.Component:
    return rx.vstack(
        rx.heading("📝 실제 매매 기록 (일괄 입력)", size="7"),
        rx.text("리밸런싱 전략 실행 결과를 한 번에 입력하세요.", size="3", color="gray", margin_bottom="4"),
        
        rx.hstack(
            rx.text("체결 일자: ", weight="bold"),
            rx.input(
                type="date", 
                value=HistoryState.trade_date,
                on_change=HistoryState.set_trade_date,
                width="200px"
            )
        ),
        
        rx.vstack(
            # Buy Column
            rx.box(
                rx.heading("🔴 매수(Buy) 입력", size="5", margin_bottom="2"),
                rx.foreach(
                    HistoryState.buy_rows,
                    lambda row: rx.hstack(
                        rx.select(
                            HistoryState.account_options,
                            placeholder="계좌 선택",
                            value=row["acc_id"],
                            on_change=lambda val: HistoryState.set_buy_value(row["id"], "acc_id", val)
                        ),
                        rx.select(
                            HistoryState.asset_options,
                            placeholder="종목 선택",
                            value=row["ast_id"],
                            on_change=lambda val: HistoryState.set_buy_value(row["id"], "ast_id", val)
                        ),
                        rx.input(
                            placeholder="수량",
                            type="number",
                            value=row["qty"].to_string(),
                            on_change=lambda val: HistoryState.set_buy_value(row["id"], "qty", val)
                        ),
                        rx.input(
                            placeholder="단가",
                            type="number",
                            value=row["price"].to_string(),
                            on_change=lambda val: HistoryState.set_buy_value(row["id"], "price", val)
                        ),
                        rx.button("❌", on_click=lambda: HistoryState.remove_buy_row(row["id"]), variant="ghost"),
                        width="100%",
                        align_items="center",
                        margin_bottom="2"
                    )
                ),
                rx.button("➕ 매수 추가", on_click=HistoryState.add_buy_row, width="100%"),
                width="100%"
            ),
            
            # Sell Column
            rx.box(
                rx.heading("🔵 매도(Sell) 입력", size="5", margin_bottom="2"),
                rx.foreach(
                    HistoryState.sell_rows,
                    lambda row: rx.hstack(
                        rx.select(
                            HistoryState.account_options,
                            placeholder="계좌 선택",
                            value=row["acc_id"],
                            on_change=lambda val: HistoryState.set_sell_value(row["id"], "acc_id", val)
                        ),
                        rx.select(
                            HistoryState.asset_options,
                            placeholder="종목 선택",
                            value=row["ast_id"],
                            on_change=lambda val: HistoryState.set_sell_value(row["id"], "ast_id", val)
                        ),
                        rx.input(
                            placeholder="수량",
                            type="number",
                            value=row["qty"].to_string(),
                            on_change=lambda val: HistoryState.set_sell_value(row["id"], "qty", val)
                        ),
                        rx.input(
                            placeholder="단가",
                            type="number",
                            value=row["price"].to_string(),
                            on_change=lambda val: HistoryState.set_sell_value(row["id"], "price", val)
                        ),
                        rx.button("❌", on_click=lambda: HistoryState.remove_sell_row(row["id"]), variant="ghost"),
                        width="100%",
                        align_items="center",
                        margin_bottom="2"
                    )
                ),
                rx.button("➕ 매도 추가", on_click=HistoryState.add_sell_row, width="100%"),
                width="100%"
            ),
            width="100%",
            spacing="6",
            align_items="flex-start",
            margin_y="4"
        ),
        
        rx.button("💾 위 내역 전체 일괄 저장", on_click=HistoryState.save_trades, size="4", color_scheme="blue", width="100%", margin_bottom="6"),
        
        rx.heading("📜 최근 매매 기록 (Trade History)", size="6", margin_bottom="4"),
        rx.cond(
            HistoryState.trade_history.length() > 0,
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("거래일자"),
                        rx.table.column_header_cell("계좌"),
                        rx.table.column_header_cell("유형"),
                        rx.table.column_header_cell("자산명"),
                        rx.table.column_header_cell("수량"),
                        rx.table.column_header_cell("단가"),
                        rx.table.column_header_cell("결제금액(원)"),
                        rx.table.column_header_cell("동작"),
                    )
                ),
                rx.table.body(
                    rx.foreach(
                        HistoryState.trade_history,
                        lambda row: rx.table.row(
                            rx.table.cell(row["date"]),
                            rx.table.cell(row["account"]),
                            rx.table.cell(row["type"]),
                            rx.table.cell(row["asset"], weight="bold"),
                            rx.table.cell(row["qty"]),
                            rx.table.cell(row["price"]),
                            rx.table.cell(row["total"]),
                            rx.table.cell(
                                rx.button("삭제", size="1", color_scheme="red", on_click=lambda: HistoryState.delete_selected_trade(row["id"]))
                            ),
                        )
                    )
                ),
                variant="surface",
                size="2",
                width="100%"
            ),
            rx.text("매매 기록이 없습니다.", color="gray")
        ),
        
        width="100%",
        align_items="flex-start"
    )
