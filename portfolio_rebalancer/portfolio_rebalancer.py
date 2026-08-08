"""Welcome to Reflex! This file outlines the steps to create a basic app."""

import reflex as rx
from rxconfig import config

from portfolio_rebalancer.state import AppState
from portfolio_rebalancer.auth import require_auth
from portfolio_rebalancer.components.navbar import navbar
from portfolio_rebalancer.pages.dashboard import dashboard_page, DashboardState
from portfolio_rebalancer.pages.target import target_page, TargetState
from portfolio_rebalancer.pages.history import history_page, HistoryState
from portfolio_rebalancer.pages.rebalance import rebalance_page, RebalanceState
from portfolio_rebalancer.pages.settings import settings_page, SettingsState

def layout(page_content: rx.Component) -> rx.Component:
    """The main layout of the app."""
    return require_auth(
        rx.vstack(
            navbar(),
            rx.container(
                page_content,
                padding="4",
                max_width="1200px"
            ),
            width="100%",
            min_height="100vh",
            background_color=rx.color("gray", 1)
        )
    )

def index() -> rx.Component:
    return layout(dashboard_page())

def target() -> rx.Component:
    return layout(target_page())

def history() -> rx.Component:
    return layout(history_page())
    
def rebalance() -> rx.Component:
    return layout(rebalance_page())
    
def settings() -> rx.Component:
    return layout(settings_page())

app = rx.App()
app.add_page(index, title="포트폴리오 대시보드", on_load=DashboardState.on_load)
app.add_page(target, route="/target", title="목표 비중 & 계좌 매핑", on_load=TargetState.on_load)
app.add_page(rebalance, route="/rebalance", title="리밸런싱", on_load=RebalanceState.on_load)
app.add_page(history, route="/history", title="매매 기록", on_load=HistoryState.on_load)
app.add_page(settings, route="/settings", title="설정", on_load=SettingsState.on_load)
