import reflex as rx
from portfolio_rebalancer.state import AppState

def login_screen() -> rx.Component:
    """The login screen component."""
    return rx.center(
        rx.card(
            rx.vstack(
                rx.heading("🔒 포트폴리오 매니저", size="7", text_align="center", margin_bottom="2"),
                rx.text("접속을 위해 암호를 입력해 주세요.", size="3", color="gray", margin_bottom="4"),
                
                rx.hstack(
                    rx.input(
                        placeholder="비밀번호",
                        type="password",
                        value=AppState.password_input,
                        on_change=AppState.set_password_input,
                        on_key_down=AppState.check_password_on_enter,
                        width="100%"
                    ),
                    rx.button(
                        "로그인", 
                        on_click=AppState.check_password,
                        color_scheme="blue"
                    ),
                    width="100%"
                ),
                rx.cond(
                    AppState.login_failed,
                    rx.text("😕 비밀번호가 일치하지 않습니다.", color="red", size="2"),
                    rx.box()
                ),
                align_items="center",
                width="100%",
                padding="6"
            ),
            size="4",
            width="400px",
            box_shadow="lg"
        ),
        height="100vh",
        background_color=rx.color("gray", 2)
    )

def require_auth(page_content: rx.Component) -> rx.Component:
    """Wrapper that shows either the login screen or the actual page."""
    return rx.cond(
        AppState.password_correct,
        page_content,
        login_screen()
    )
