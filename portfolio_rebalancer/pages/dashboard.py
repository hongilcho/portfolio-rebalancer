import reflex as rx
import pandas as pd
from typing import List, Dict, Any
from portfolio_rebalancer.state import AppState
from data.data_manager import get_all_assets, get_all_accounts, get_holdings_by_account, ACCOUNT_TYPES
from typing import List, Dict, Any
from pydantic import BaseModel


class EditableAsset(BaseModel):
    asset_id: str
    name: str
    ticker: str
    market_str: str
    risk_str: str
    qty: float
    avg_price: float
    qty_name: str
    avg_price_name: str

class StockSummary(BaseModel):
    name: str
    qty_str: str
    avg_price_native: str
    curr_price_native: str
    buy_amt_krw: str
    eval_native: str
    eval_krw: str
    target_w: str
    actual_w: str
    deviation: str
    profit_krw: str
    return_rate: str
    is_profit: bool
    is_loss: bool
    dev_alert: bool
    dev_is_positive: bool
    dev_is_negative: bool

class ChartData(BaseModel):
    name: str
    value: float
    fill: str

class CashSummary(BaseModel):
    name: str
    qty_str: str
    eval_krw: str

class AccountHolding(BaseModel):
    name: str
    qty_str: str
    avg_p_str: str
    curr_p_str: str
    eval_val_str: str
    profit_krw_str: str
    profit_pct_str: str
    is_profit: bool
    is_loss: bool

class AccountSummary(BaseModel):
    title: str
    account_type: str
    account_alias: str
    deposit_krw: str
    deposit_usd: str
    stock_eval: str
    risk_pct_str: str
    risk_pct_val: float
    has_holdings: bool
    holdings: List[AccountHolding]
    annual_limit: float
    tax_limit: float
    current_year_deposit: float
    annual_limit_str: str
    tax_limit_str: str
    current_year_deposit_str: str
    total_acc_val_str: str
    acc_profit_krw_str: str
    acc_profit_pct_str: str
    acc_is_profit: bool
    acc_is_loss: bool

class DashboardState(AppState):
    """State for the Dashboard page."""
    
    accounts: List[Dict[str, Any]] = []
    assets: List[Dict[str, Any]] = []
    
    total_stock_eval: float = 0.0
    total_stock_buy: float = 0.0
    total_stock_profit: float = 0.0
    total_stock_profit_rate: float = 0.0
    
    @rx.var
    def total_stock_eval_str(self) -> str:
        return f"{self.total_stock_eval:,.0f}"
    
    @rx.var
    def total_stock_buy_str(self) -> str:
        return f"{self.total_stock_buy:,.0f}"
    
    @rx.var
    def total_stock_profit_str(self) -> str:
        return f"{self.total_stock_profit:,.0f}"
        
    @rx.var
    def total_stock_profit_rate_str(self) -> str:
        return f"{self.total_stock_profit_rate:.2f}"
    
    stock_basic_rows: List[StockSummary] = []
    stock_weight_rows: List[StockSummary] = []
    cash_summary_rows: List[CashSummary] = []
    account_summaries: List[AccountSummary] = []
    donut_data: List[Dict[str, Any]] = []
    

    selected_edit_account_id: str = ""
    
    @rx.var
    def current_edit_krw(self) -> float:
        if not self.parsed_edit_acc_id: return 0.0
        acc = next((a for a in self.accounts if str(a['id']) == self.parsed_edit_acc_id), None)
        return float(acc['deposit_krw']) if acc else 0.0
        
    @rx.var
    def current_edit_usd(self) -> float:
        if not self.parsed_edit_acc_id: return 0.0
        acc = next((a for a in self.accounts if str(a['id']) == self.parsed_edit_acc_id), None)
        return float(acc['deposit_usd']) if acc else 0.0

    @rx.var
    def edit_account_allowed_assets(self) -> List[EditableAsset]:
        if not self.parsed_edit_acc_id:
            return []
        acc = next((a for a in self.accounts if str(a['id']) == self.parsed_edit_acc_id), None)
        if not acc: return []
        
        from data.data_manager import get_holdings_by_account
        current_holdings = get_holdings_by_account(acc['id'])
        holding_map = {str(h['asset_id']): h for h in current_holdings}
        
        allowed = []
        for asset in self.assets:
            if str(acc['id']) in [str(x) for x in asset.get('allowed_accounts', [])]:
                aid = str(asset['id'])
                exist_qty = float(holding_map.get(aid, {}).get('quantity', 0.0))
                exist_avg = float(holding_map.get(aid, {}).get('avg_price', 0.0))
                
                allowed.append(EditableAsset(
                    asset_id=aid,
                    name=asset['name'],
                    ticker=asset['ticker'],
                    market_str="🇰🇷 국내" if asset['market'] == 'KR' else "🇺🇸 미국",
                    risk_str="🔴 위험자산" if asset['is_risk_asset'] else "🟢 안전자산",
                    qty=exist_qty,
                    avg_price=exist_avg,
                    qty_name=f"qty_{aid}",
                    avg_price_name=f"avg_{aid}"
                ))
        return allowed
        
    @rx.var
    def parsed_edit_acc_id(self) -> str:
        if not self.selected_edit_account_id or ":" not in self.selected_edit_account_id: return ""
        return self.selected_edit_account_id.split(":")[0]

    def set_edit_account(self, val: str):
        self.selected_edit_account_id = val
            
    def handle_holdings_submit(self, form_data: dict):
        if not self.parsed_edit_acc_id:
            return rx.window_alert("계좌를 선택해주세요.")
            
        krw = float(form_data.get("edit_krw", 0))
        usd = float(form_data.get("edit_usd", 0))
        
        acc = next((a for a in self.accounts if str(a['id']) == self.parsed_edit_acc_id), None)
        if not acc: return rx.window_alert("계좌를 찾을 수 없습니다.")
        
        from data.data_manager import update_account, save_account_holdings
        update_account(
            acc['id'], acc['account_no'], acc['account_alias'], acc['account_type'], 
            krw, usd, float(acc.get('annual_limit', 0.0)), float(acc.get('tax_limit', 0.0)), 
            acc['notes'], int(acc.get('priority', 99)), acc.get('limit_preference', 'ANNUAL'), 
            float(acc.get('current_year_deposit', 0.0))
        )
        
        holding_inputs = []
        for asset in self.assets:
            aid = str(asset['id'])
            qty_key = f"qty_{aid}"
            avg_key = f"avg_{aid}"
            if qty_key in form_data and avg_key in form_data:
                q = float(form_data[qty_key])
                a_p = float(form_data[avg_key])
                holding_inputs.append({'asset_id': asset['id'], 'quantity': q, 'avg_price': a_p})
                
        save_account_holdings(acc['id'], holding_inputs)
        
        self.load_dashboard_data()
        return rx.window_alert("성공적으로 저장되었습니다!")

    @rx.var
    def edit_account_options(self) -> List[str]:
        opts = ["선택해주세요"]
        for a in self.accounts:
            opts.append(f"{a['id']}: [{a['account_type']}] {a['account_alias']} ({a['account_no']})")
        return opts

    def on_load(self):
        super().on_load()
        self.load_dashboard_data()
        
    def on_refresh_prices(self):
        self.refresh_price_data()
        self.load_dashboard_data()
        
    def load_dashboard_data(self):
        self.assets = get_all_assets()
        self.accounts = get_all_accounts()
        
        price_map = {}
        if self.price_data:
            for aid, res in self.price_data.items():
                price_map[aid] = res.get('price_krw', 0.0)
                
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
                curr_p_krw = price_map.get(aid, avg_p_krw if avg_p_krw > 0 else 0)
                
                # identify market 
                asset_info = next((a for a in self.assets if str(a['id']) == aid), None)
                market = asset_info['market'] if asset_info else 'KR'
                
                eval_krw = qty * curr_p_krw
                buy_krw = qty * avg_p_krw
                
                stock_eval += eval_krw
                stock_buy_total += buy_krw
                
                if h['is_risk_asset']:
                    risk_stock_eval += eval_krw
                else:
                    safe_stock_eval += eval_krw
                    
                profit_krw = eval_krw - buy_krw
                profit_pct = (profit_krw / buy_krw * 100) if buy_krw > 0 else 0.0
                
                holding_details.append({
                    "name": h['asset_name'],
                    "qty": qty,
                    "profit_krw": profit_krw,
                    "profit_pct": profit_pct,
                    "eval_val": eval_krw,
                    "avg_p": avg_p_krw,
                    "curr_p": curr_p_krw,
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
                        "market": market
                    }
                portfolio_assets[aid]['qty'] += qty
                portfolio_assets[aid]['buy_amt_krw'] += buy_krw
                portfolio_assets[aid]['eval_amt_krw'] += eval_krw
                
            total_acc_val = total_deposit + stock_eval
            total_portfolio_eval += total_acc_val
            risk_pct = (risk_stock_eval / total_acc_val * 100) if total_acc_val > 0 else 0.0
            
            holdings_list = []
            for h in holding_details:
                if '금' in h['name'] or 'Gold' in h['name']:
                    qty_str = f"{h['qty']:,.2f}g"
                else:
                    qty_str = f"{h['qty']:,.0f}"
                avg_p_str = f"{h['avg_p']:,.0f} 원"
                curr_p_str = f"{h['curr_p']:,.0f} 원"
                eval_val_str = f"{h['eval_val']:,.0f} 원"
                profit_krw_str = f"{h['profit_krw']:,.0f} 원"
                profit_pct_str = f"{h['profit_pct']:.1f}%"
                
                holdings_list.append(AccountHolding(
                    name=h['name'],
                    qty_str=qty_str,
                    avg_p_str=avg_p_str,
                    curr_p_str=curr_p_str,
                    eval_val_str=eval_val_str,
                    profit_krw_str=profit_krw_str,
                    profit_pct_str=profit_pct_str,
                    is_profit=h['profit_krw'] > 0,
                    is_loss=h['profit_krw'] < 0
                ))
            
            acc_type = acc['account_type']
            acc_profit = stock_eval - stock_buy_total
            acc_profit_pct = (acc_profit / stock_buy_total * 100) if stock_buy_total > 0 else 0.0
            
            self.account_summaries.append(AccountSummary(
                title=f"[{acc_type}] {acc['account_alias']}",
                account_type=acc_type,
                account_alias=acc['account_alias'],
                total_acc_val_str=f"{total_acc_val:,.0f} 원",
                acc_profit_krw_str=f"{acc_profit:,.0f} 원",
                acc_profit_pct_str=f"{acc_profit_pct:+.2f}%",
                acc_is_profit=acc_profit > 0,
                acc_is_loss=acc_profit < 0,
                deposit_krw=f"{dep_krw:,.0f} 원",
                deposit_usd=f"${dep_usd:,.2f}",
                stock_eval=f"{stock_eval:,.0f} 원",
                risk_pct_str=f"{risk_pct:.1f}%",
                risk_pct_val=risk_pct,
                has_holdings=len(holdings_list) > 0,
                holdings=holdings_list,
                annual_limit=acc.get('annual_limit', 0.0),
                tax_limit=acc.get('tax_limit', 0.0),
                current_year_deposit=stock_buy_total,
                annual_limit_str=f"{acc.get('annual_limit', 0.0):,.0f}",
                tax_limit_str=f"{acc.get('tax_limit', 0.0):,.0f}",
                current_year_deposit_str=f"{stock_buy_total:,.0f}",
            ))

        self.total_stock_eval = sum(data['eval_amt_krw'] for data in portfolio_assets.values() if data['qty'] > 0)
        self.total_stock_buy = sum(data['buy_amt_krw'] for data in portfolio_assets.values() if data['qty'] > 0)
        self.total_stock_profit = self.total_stock_eval - self.total_stock_buy
        self.total_stock_profit_rate = (self.total_stock_profit / self.total_stock_buy * 100) if self.total_stock_buy > 0 else 0.0
        
        target_weight_map = {str(a['id']): a['target_weight'] for a in self.assets}
        
        self.stock_basic_rows = []
        self.stock_weight_rows = []
        self.donut_data = []
        
        # Color palette for donut chart
        colors = ["#3b82f6", "#ef4444", "#10b981", "#f59e0b", "#8b5cf6", "#ec4899", "#14b8a6", "#f97316"]
        color_idx = 0
        
        for a in self.assets:
            aid = str(a['id'])
            data = portfolio_assets.get(aid, {
                "name": a['name'],
                "ticker": a['ticker'],
                "qty": 0.0,
                "buy_amt_krw": 0.0,
                "eval_amt_krw": 0.0,
                "buy_amt_native": 0.0,
                "eval_amt_native": 0.0,
                "market": a['market']
            })
            
            qty = data['qty']
            if qty == 0:
                continue
                
            if '금' in a['name'] or 'Gold' in a['name']:
                qty_str = f"{qty:,.2f}g"
            else:
                qty_str = f"{qty:,.0f}"
            
            profit_krw = data['eval_amt_krw'] - data['buy_amt_krw']
            profit_pct = (profit_krw / data['buy_amt_krw'] * 100) if data['buy_amt_krw'] > 0 else 0.0
            actual_w = (data['eval_amt_krw'] / self.total_stock_eval * 100) if self.total_stock_eval > 0 else 0.0
            target_w = a['target_weight']
            deviation = actual_w - target_w
            
            avg_p_krw = (data['buy_amt_krw'] / qty) if qty > 0 else 0.0
            curr_p_krw = (data['eval_amt_krw'] / qty) if qty > 0 else 0.0
            
            # 1. Basic Info Row
            summary_obj = StockSummary(
                name=a['name'],
                qty_str=qty_str,
                avg_price_native=f"{avg_p_krw:,.0f} 원",
                curr_price_native=f"{curr_p_krw:,.0f} 원",
                buy_amt_krw=f"{data['buy_amt_krw']:,.0f} 원",
                eval_native=f"{data['eval_amt_krw']:,.0f} 원",
                eval_krw=f"{data['eval_amt_krw']:,.0f} 원",
                target_w=f"{target_w:.1f}%",
                actual_w=f"{actual_w:.1f}%",
                deviation=f"{deviation:+.1f}%",
                profit_krw=f"{profit_krw:,.0f} 원",
                return_rate=f"{profit_pct:.1f}%",
                is_profit=profit_krw > 0,
                is_loss=profit_krw < 0,
                dev_alert=abs(deviation) >= 5.0,
                dev_is_positive=deviation > 0,
                dev_is_negative=deviation < 0
            )
            self.stock_basic_rows.append(summary_obj)
            self.stock_weight_rows.append(summary_obj)
            
            if data['eval_amt_krw'] > 0:
                self.donut_data.append({
                    "name": a['name'],
                    "value": round(actual_w, 1),
                    "fill": colors[color_idx % len(colors)]
                })
                color_idx += 1
            
        self.stock_basic_rows.sort(key=lambda x: float(x.actual_w.strip('%')), reverse=True)
        self.stock_weight_rows.sort(key=lambda x: float(x.actual_w.strip('%')), reverse=True)
        
        self.cash_summary_rows = []
        if total_krw_cash > 0:
            self.cash_summary_rows.append(CashSummary(
                name="💵 현금 (KRW)",
                qty_str=f"{total_krw_cash:,.0f} 원",
                eval_krw=f"{total_krw_cash:,.0f} 원"
            ))
        if total_usd_cash > 0:
            self.cash_summary_rows.append(CashSummary(
                name="💵 현금 (USD)",
                qty_str=f"${total_usd_cash:,.2f}",
                eval_krw=f"{total_usd_cash * self.usd_krw:,.0f} 원"
            ))

def account_card(summary: AccountSummary) -> rx.Component:
    return rx.card(
        rx.vstack(
            rx.hstack(
                rx.vstack(
                    rx.heading(summary.account_alias, size="6"),
                    rx.badge(summary.account_type, color_scheme="blue", variant="solid"),
                    align_items="flex-start",
                    spacing="2"
                ),
                rx.spacer(),
                rx.vstack(
                    rx.text("총 자산 평가액", size="2", color="gray", weight="bold"),
                    rx.heading(summary.total_acc_val_str, size="7"),
                    rx.hstack(
                        rx.text(summary.acc_profit_krw_str, color=rx.cond(summary.acc_is_profit, "red", rx.cond(summary.acc_is_loss, "blue", "gray")), weight="bold", size="4"),
                        rx.text(summary.acc_profit_pct_str, color=rx.cond(summary.acc_is_profit, "red", rx.cond(summary.acc_is_loss, "blue", "gray")), weight="bold", size="4"),
                        spacing="2"
                    ),
                    align_items="flex-end",
                    spacing="1"
                ),
                width="100%",
                align_items="center"
            ),
            
            rx.divider(margin_top="4", margin_bottom="4"),
            
            rx.hstack(
                rx.badge(f"원화 예수금: {summary.deposit_krw}", color_scheme="gray", variant="surface"),
                rx.badge(f"달러 예수금: {summary.deposit_usd}", color_scheme="gray", variant="surface"),
                rx.badge(f"주식 평가금액: {summary.stock_eval}", color_scheme="gray", variant="surface"),
                rx.badge(f"위험자산 비중: {summary.risk_pct_str}", color_scheme="red", variant="surface"),
                spacing="4", 
                margin_bottom="4",
                flex_wrap="wrap"
            ),
            
            rx.cond(
                summary.account_type == "IRP",
                rx.cond(
                    summary.risk_pct_val <= 70.0,
                    rx.callout(
                        f"✅ 위험자산 비중이 {summary.risk_pct_str}로 70% 한도 이내를 준수하고 있습니다.",
                        icon="check_circle",
                        color_scheme="green",
                        margin_bottom="4",
                        width="100%"
                    ),
                    rx.callout(
                        f"⚠️ 위험자산 비중이 {summary.risk_pct_str}로 70% 한도를 초과했습니다!",
                        icon="alert_triangle",
                        color_scheme="red",
                        margin_bottom="4",
                        width="100%"
                    )
                )
            ),
            
            rx.cond(
                (summary.account_type == "IRP") | (summary.account_type == "연금저축"),
                rx.vstack(
                    rx.text(f"연간 납입한도: {summary.current_year_deposit_str} / {summary.annual_limit_str} 원", size="2", weight="bold", color="var(--slate-11)"),
                    rx.progress(value=rx.cond(summary.annual_limit > 0, (summary.current_year_deposit / summary.annual_limit * 100).to(int), 0), color_scheme="blue", margin_bottom="2"),
                    rx.text(f"세액공제한도: {summary.current_year_deposit_str} / {summary.tax_limit_str} 원", size="2", weight="bold", color="var(--slate-11)"),
                    rx.progress(value=rx.cond(summary.tax_limit > 0, (summary.current_year_deposit / summary.tax_limit * 100).to(int), 0), color_scheme="green", margin_bottom="4"),
                    width="100%",
                    align_items="stretch"
                )
            ),
            rx.cond(
                summary.account_type == "ISA",
                rx.vstack(
                    rx.text(f"연간 납입한도: {summary.current_year_deposit_str} / {summary.annual_limit_str} 원", size="2", weight="bold", color="var(--slate-11)"),
                    rx.progress(value=rx.cond(summary.annual_limit > 0, (summary.current_year_deposit / summary.annual_limit * 100).to(int), 0), color_scheme="blue", margin_bottom="4"),
                    width="100%",
                    align_items="stretch"
                )
            ),
            
            rx.accordion.root(
                rx.accordion.item(
                    header=rx.heading("보유 자산 상세 보기", size="3", color="var(--slate-11)"),
                    content=rx.cond(
                        summary.has_holdings,
                        rx.table.root(
                            rx.table.header(
                                rx.table.row(
                                    rx.table.column_header_cell("자산명"),
                                    rx.table.column_header_cell("수량"),
                                    rx.table.column_header_cell("평단가"),
                                    rx.table.column_header_cell("현재가"),
                                    rx.table.column_header_cell("평가금액"),
                                    rx.table.column_header_cell("평가손익"),
                                    rx.table.column_header_cell("수익률"),
                                )
                            ),
                            rx.table.body(
                                rx.foreach(
                                    summary.holdings,
                                    lambda h: rx.table.row(
                                        rx.table.cell(h.name, weight="bold"),
                                        rx.table.cell(h.qty_str),
                                        rx.table.cell(h.avg_p_str),
                                        rx.table.cell(h.curr_p_str),
                                        rx.table.cell(h.eval_val_str),
                                        rx.table.cell(rx.text(h.profit_krw_str, color=rx.cond(h.is_profit, "red", rx.cond(h.is_loss, "blue", "gray")))),
                                        rx.table.cell(rx.text(h.profit_pct_str, color=rx.cond(h.is_profit, "red", rx.cond(h.is_loss, "blue", "gray")), weight="bold")),
                                    )
                                )
                            ),
                            variant="surface"
                        ),
                        rx.text("보유 자산이 없습니다.", color="gray")
                    ),
                    value="holdings"
                ),
                width="100%",
                type="multiple",
                color_scheme="gray",
                variant="ghost"
            ),
            
            width="100%",
            align_items="stretch"
        ),
        width="100%",
        box_shadow="0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)",
        border_radius="xl",
        margin_bottom="6"
    )

def dashboard_page() -> rx.Component:
    return rx.vstack(
        # Top Header & Controls
        rx.hstack(
            rx.heading("📊 전체 포트폴리오 요약", size="7"),
            rx.spacer(),
            rx.hstack(
                rx.badge("USD/KRW", color_scheme="green"),
                rx.input(
                    value=DashboardState.usd_krw.to_string(),
                    on_change=DashboardState.set_custom_usd_krw,
                    width="120px"
                ),
                rx.text(DashboardState.rate_source, size="1", color="gray"),
                rx.button(
                    rx.icon(tag="refresh-cw"),
                    "시세 새로고침",
                    on_click=DashboardState.on_refresh_prices,
                    color_scheme="blue",
                    variant="soft"
                ),
                align_items="center",
                spacing="3"
            ),
            width="100%",
            align_items="center"
        ),
        
        # KPI Cards
        rx.grid(
            rx.card(
                rx.vstack(
                    rx.text("💵 총 매입 금액 (투자 원금)", color="gray", size="2"),
                    rx.text(DashboardState.total_stock_buy_str + " 원", size="7", weight="bold"),
                ),
                width="100%",
            ),
            rx.card(
                rx.vstack(
                    rx.text("📈 총 주식 평가금액 (현금 제외)", color="gray", size="2"),
                    rx.text(DashboardState.total_stock_eval_str + " 원", size="7", weight="bold"),
                ),
                width="100%",
            ),
            rx.card(
                rx.vstack(
                    rx.text("총 평가 손익", color="gray", size="2"),
                    rx.text(DashboardState.total_stock_profit_str + " 원", 
                            size="7", weight="bold", 
                            color=rx.cond(DashboardState.total_stock_profit > 0, "red", rx.cond(DashboardState.total_stock_profit < 0, "blue", "gray"))),
                ),
                width="100%",
            ),
            rx.card(
                rx.vstack(
                    rx.text("총 수익률", color="gray", size="2"),
                    rx.text(DashboardState.total_stock_profit_rate_str + "%", 
                            size="7", weight="bold", 
                            color=rx.cond(DashboardState.total_stock_profit_rate > 0, "red", rx.cond(DashboardState.total_stock_profit_rate < 0, "blue", "gray"))),
                ),
                width="100%",
            ),
            columns="4",
            spacing="4",
            width="100%",
            margin_bottom="6"
        ),
        
        # Charts & Tables Area
        rx.heading("📈 자산 기본 정보", size="5", margin_top="6", margin_bottom="4"),
        rx.scroll_area(
            rx.table.root(
                rx.table.header(
                    rx.table.row(
                        rx.table.column_header_cell("자산명"),
                        rx.table.column_header_cell("수량"),
                        rx.table.column_header_cell("수익률"),
                        rx.table.column_header_cell("평가손익"),
                        rx.table.column_header_cell("평단가"),
                        rx.table.column_header_cell("현재가"),
                        rx.table.column_header_cell("매입금액"),
                        rx.table.column_header_cell("평가금액"),
                    )
                ),
                rx.table.body(
                    rx.foreach(
                        DashboardState.stock_basic_rows,
                        lambda row: rx.table.row(
                            rx.table.cell(rx.text(row.name, weight="bold")),
                            rx.table.cell(row.qty_str),
                            rx.table.cell(
                                rx.text(row.return_rate, color=rx.cond(row.is_profit, "red", rx.cond(row.is_loss, "blue", "gray")), weight="bold")
                            ),
                            rx.table.cell(
                                rx.text(row.profit_krw, color=rx.cond(row.is_profit, "red", rx.cond(row.is_loss, "blue", "gray")))
                            ),
                            rx.table.cell(row.avg_price_native),
                            rx.table.cell(row.curr_price_native),
                            rx.table.cell(row.buy_amt_krw),
                            rx.table.cell(row.eval_krw),
                        )
                    )
                )
            ),
            width="100%",
        ),
        
        rx.heading("⚖️ 비중 및 괴리율", size="5", margin_top="6", margin_bottom="4"),
        rx.hstack(
            # Left: Donut Chart
            rx.box(
                rx.recharts.pie_chart(
                    rx.recharts.pie(
                        rx.recharts.label_list(
                            data_key="value", 
                            position="inside", 
                            fill="white", 
                            stroke="none",
                            font_weight="bold"
                        ),
                        data=DashboardState.donut_data,
                        data_key="value",
                        name_key="name",
                        cx="50%",
                        cy="50%",
                        inner_radius="50%",
                        outer_radius="85%",
                    ),
                    rx.recharts.tooltip(),
                    rx.recharts.legend(),
                    height=300,
                    width="100%"
                ),
                width="35%",
                padding="4",
                border=f"1px solid {rx.color('gray', 4)}",
                border_radius="md",
            ),
            # Right: Weight Table
            rx.box(
                rx.scroll_area(
                    rx.table.root(
                        rx.table.header(
                            rx.table.row(
                                rx.table.column_header_cell("자산명"),
                                rx.table.column_header_cell("원화 환산 평가금액"),
                                rx.table.column_header_cell("목표 비중"),
                                rx.table.column_header_cell("실제 비중"),
                                rx.table.column_header_cell("괴리율"),
                            )
                        ),
                        rx.table.body(
                            rx.foreach(
                                DashboardState.stock_weight_rows,
                                lambda row: rx.table.row(
                                    rx.table.cell(rx.text(row.name, weight="bold")),
                                    rx.table.cell(row.eval_krw),
                                    rx.table.cell(row.target_w),
                                    rx.table.cell(row.actual_w),
                                    rx.table.cell(
                                        rx.text(row.deviation, color=rx.cond(row.dev_is_positive, "red", rx.cond(row.dev_is_negative, "blue", "gray")), weight="bold")
                                    ),
                                )
                            )
                        )
                    ),
                    width="100%",
                ),
                width="65%",
                padding="4",
                border=f"1px solid {rx.color('gray', 4)}",
                border_radius="md",
            ),
            width="100%",
            spacing="4",
            margin_bottom="6",
            align_items="flex-start"
        ),
        
        rx.heading("💵 현금성 자산", size="5", margin_top="4", margin_bottom="4"),
        rx.table.root(
            rx.table.header(
                rx.table.row(
                    rx.table.column_header_cell("자산명"),
                    rx.table.column_header_cell("수량/금액"),
                    rx.table.column_header_cell("원화 환산액"),
                )
            ),
            rx.table.body(
                rx.foreach(
                    DashboardState.cash_summary_rows,
                    lambda row: rx.table.row(
                        rx.table.cell(row.name),
                        rx.table.cell(row.qty_str),
                        rx.table.cell(row.eval_krw),
                    )
                )
            )
        ),
        

        rx.heading("📂 계좌별 상세 현황", size="5", margin_top="6", margin_bottom="4"),
        rx.vstack(
            rx.foreach(
                DashboardState.account_summaries,
                account_card
            ),
            width="100%"
        ),
        rx.heading("✏️ 보유 잔고 및 예수금 입력/수정하기", size="5", margin_top="6", margin_bottom="4"),
        rx.card(
            rx.vstack(
                rx.text("잔고 및 수량을 수정할 계좌 선택", weight="bold"),
                rx.select(
                    DashboardState.edit_account_options,
                    value=DashboardState.selected_edit_account_id,
                    on_change=DashboardState.set_edit_account,
                    width="100%"
                ),
                rx.cond(
                    DashboardState.parsed_edit_acc_id != "",
                    rx.form.root(
                        rx.vstack(
                            rx.heading("예수금 설정", size="4", margin_top="4"),
                            rx.hstack(
                                rx.vstack(
                                    rx.text("원화 예수금 (원)", weight="bold"),
                                    rx.input(key=DashboardState.selected_edit_account_id + "_krw", name="edit_krw", default_value=DashboardState.current_edit_krw.to_string(), type="number", step="10000"),
                                    width="100%"
                                ),
                                rx.vstack(
                                    rx.text("달러 예수금 ($)", weight="bold"),
                                    rx.input(key=DashboardState.selected_edit_account_id + "_usd", name="edit_usd", default_value=DashboardState.current_edit_usd.to_string(), type="number", step="10"),
                                    width="100%"
                                ),
                                width="100%",
                                spacing="4"
                            ),
                            
                            rx.heading("이 계좌에서 운용 가능한 종목 수량 및 평단가", size="4", margin_top="4"),
                            rx.foreach(
                                DashboardState.edit_account_allowed_assets,
                                lambda asset: rx.vstack(
                                    rx.text(asset.name + " (" + asset.ticker + " | " + asset.market_str + " | " + asset.risk_str + ")", weight="bold"),
                                    rx.hstack(
                                        rx.vstack(
                                            rx.text("보유 수량", size="2", color="gray"),
                                            rx.input(name=asset.qty_name, default_value=asset.qty.to_string(), type="number", step="1"),
                                            width="100%"
                                        ),
                                        rx.vstack(
                                            rx.text("평균 매입가 (원)", size="2", color="gray"),
                                            rx.input(name=asset.avg_price_name, default_value=asset.avg_price.to_string(), type="number", step="100"),
                                            width="100%"
                                        ),
                                        width="100%",
                                        spacing="4"
                                    ),
                                    rx.divider(margin_top="2", margin_bottom="2"),
                                    width="100%"
                                )
                            ),
                            
                            rx.button(
                                "💾 예수금 및 보유 수량/평단가 저장", 
                                type="submit", 
                                color_scheme="blue", 
                                size="3", 
                                width="100%",
                                margin_top="4"
                            ),
                            width="100%",
                            align_items="stretch"
                        ),
                        on_submit=DashboardState.handle_holdings_submit,
                        width="100%"
                    ),
                    rx.text("계좌를 먼저 선택해주세요.", color="gray", margin_top="4")
                ),
                width="100%",
                align_items="stretch"
            ),
            width="100%",
            margin_bottom="8",
            variant="surface"
        ),

        width="100%",
        align_items="flex-start",
    )
