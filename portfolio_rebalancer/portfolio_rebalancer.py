"""Welcome to Reflex! This file outlines the steps to create a basic app."""

import reflex as rx
from rxconfig import config

from portfolio_rebalancer.state import AppState
from portfolio_rebalancer.auth import require_auth
from portfolio_rebalancer.components.navbar import navbar

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
    return layout(
        rx.vstack(
            rx.heading("1단계 대시보드 (준비 중)"),
            rx.text("이곳에 보유 종목 현황이 표시될 예정입니다.")
        )
    )

app = rx.App()
app.add_page(index, title="포트폴리오 대시보드", on_load=AppState.on_load)
