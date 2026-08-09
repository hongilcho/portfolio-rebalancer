import re

with open("portfolio_rebalancer/pages/dashboard.py", "r", encoding="utf-8") as f:
    content = f.read()

# 1. Add EditableAsset to the imports/models
editable_asset_model = """
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
"""
content = content.replace("class StockSummary(BaseModel):", editable_asset_model + "\nclass StockSummary(BaseModel):")

# 2. Add state variables and methods to DashboardState
state_additions = """
    selected_edit_account_id: str = ""
    
    @rx.var
    def current_edit_krw(self) -> float:
        if not self.selected_edit_account_id: return 0.0
        acc = next((a for a in self.accounts if str(a['id']) == self.selected_edit_account_id), None)
        return float(acc['deposit_krw']) if acc else 0.0
        
    @rx.var
    def current_edit_usd(self) -> float:
        if not self.selected_edit_account_id: return 0.0
        acc = next((a for a in self.accounts if str(a['id']) == self.selected_edit_account_id), None)
        return float(acc['deposit_usd']) if acc else 0.0

    @rx.var
    def edit_account_allowed_assets(self) -> List[EditableAsset]:
        if not self.selected_edit_account_id:
            return []
        acc = next((a for a in self.accounts if str(a['id']) == self.selected_edit_account_id), None)
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
        
    def set_edit_account(self, val: str):
        if ":" in val:
            self.selected_edit_account_id = val.split(":")[0]
            
    def handle_holdings_submit(self, form_data: dict):
        if not self.selected_edit_account_id:
            return rx.window_alert("계좌를 선택해주세요.")
            
        krw = float(form_data.get("edit_krw", 0))
        usd = float(form_data.get("edit_usd", 0))
        
        acc = next((a for a in self.accounts if str(a['id']) == self.selected_edit_account_id), None)
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
"""
content = content.replace("    def on_load(self):", state_additions + "\n    def on_load(self):")

with open("portfolio_rebalancer/pages/dashboard.py", "w", encoding="utf-8") as f:
    f.write(content)
