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
                padding="6", # Responsive padding removed due to syntax error
                max_width="1200px",
                width="100%",
            ),
            width="100%",
            min_height="100vh",
            background=rx.color("gray", 2)
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

style = {
    "font_family": "'Pretendard', 'Inter', sans-serif",
    rx.card: {
        "box_shadow": "0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)",
        "transition": "all 0.2s ease-in-out",
        "_hover": {
            "transform": "translateY(-2px)",
            "box_shadow": "0 10px 15px -3px rgb(0 0 0 / 0.1), 0 4px 6px -4px rgb(0 0 0 / 0.1)",
        }
    }
}

app = rx.App(
    theme=rx.theme(
        appearance="light",
        has_background=True,
        radius="large",
        accent_color="indigo",
        gray_color="slate",
    ),
    style=style,
    stylesheets=[
        "https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css",
    ],
)
app.add_page(index, title="포트폴리오 대시보드", on_load=DashboardState.on_load)
app.add_page(target, route="/target", title="목표 비중 & 계좌 매핑", on_load=TargetState.on_load)
app.add_page(rebalance, route="/rebalance", title="리밸런싱", on_load=RebalanceState.on_load)
app.add_page(history, route="/history", title="매매 기록", on_load=HistoryState.on_load)
app.add_page(settings, route="/settings", title="설정", on_load=SettingsState.on_load)
