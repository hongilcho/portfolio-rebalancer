import re

with open("portfolio_rebalancer/pages/dashboard.py", "r", encoding="utf-8") as f:
    content = f.read()

editor_ui = """
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
                    DashboardState.selected_edit_account_id != "",
                    rx.form.root(
                        rx.vstack(
                            rx.heading("예수금 설정", size="4", margin_top="4"),
                            rx.hstack(
                                rx.vstack(
                                    rx.text("원화 예수금 (원)", weight="bold"),
                                    rx.input(name="edit_krw", default_value=DashboardState.current_edit_krw.to_string(), type="number", step="10000"),
                                    width="100%"
                                ),
                                rx.vstack(
                                    rx.text("달러 예수금 ($)", weight="bold"),
                                    rx.input(name="edit_usd", default_value=DashboardState.current_edit_usd.to_string(), type="number", step="10"),
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
"""

insertion_point = """        rx.heading("📂 계좌별 상세 현황", size="5", margin_top="6", margin_bottom="4"),"""
content = content.replace(insertion_point, editor_ui + "\n" + insertion_point)

with open("portfolio_rebalancer/pages/dashboard.py", "w", encoding="utf-8") as f:
    f.write(content)
