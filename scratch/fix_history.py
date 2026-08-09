import re

with open("portfolio_rebalancer/pages/history.py", "r", encoding="utf-8") as f:
    content = f.read()

# Fix account_options and asset_options
new_options = """    @rx.var
    def account_options(self) -> List[str]:
        return [f"{a['id']}: [{a['account_type']}] {a['account_alias']}" for a in self.accounts]
        
    @rx.var
    def asset_options(self) -> List[str]:
        return [f"{a['id']}: {a['name']} ({a['ticker']})" for a in self.assets]"""

content = re.sub(r'    @rx\.var\n    def account_options.*?def asset_options\(self\) -> List\[str\]:\n.*?return \[str\(a\["id"\]\) for a in self\.assets\]', new_options, content, flags=re.DOTALL)

# Fix set_buy_value to parse ID
new_set_buy = """    def set_buy_value(self, row_id: str, field: str, value: str):
        for i, row in enumerate(self.buy_rows):
            if row["id"] == row_id:
                if field in ["acc_id", "ast_id"]:
                    val = value.split(":")[0] if ":" in value else value
                    self.buy_rows[i][field] = val
                elif field in ["qty", "price"]:
                    try:
                        self.buy_rows[i][field] = float(value) if value else 0.0
                    except:
                        pass
                else:
                    self.buy_rows[i][field] = value
                break"""

content = re.sub(r'    def set_buy_value\(self, row_id: str, field: str, value: str\):.*?break', new_set_buy, content, flags=re.DOTALL)

# Fix set_sell_value to parse ID
new_set_sell = """    def set_sell_value(self, row_id: str, field: str, value: str):
        for i, row in enumerate(self.sell_rows):
            if row["id"] == row_id:
                if field in ["acc_id", "ast_id"]:
                    val = value.split(":")[0] if ":" in value else value
                    self.sell_rows[i][field] = val
                elif field in ["qty", "price"]:
                    try:
                        self.sell_rows[i][field] = float(value) if value else 0.0
                    except:
                        pass
                else:
                    self.sell_rows[i][field] = value
                break"""

content = re.sub(r'    def set_sell_value\(self, row_id: str, field: str, value: str\):.*?break', new_set_sell, content, flags=re.DOTALL)

with open("portfolio_rebalancer/pages/history.py", "w", encoding="utf-8") as f:
    f.write(content)
