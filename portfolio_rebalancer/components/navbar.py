import reflex as rx

def navbar() -> rx.Component:
    """The navigation bar component."""
    return rx.hstack(
        rx.hstack(
            rx.heading("📈 포트폴리오 매니저", size="5", margin_right="4"),
            rx.link(rx.button("대시보드", variant="ghost"), href="/"),
            rx.link(rx.button("목표 비중", variant="ghost"), href="/target"),
            rx.link(rx.button("리밸런싱", variant="ghost"), href="/rebalance"),
            rx.link(rx.button("매매 기록", variant="ghost"), href="/history"),
            rx.link(rx.button("설정", variant="ghost"), href="/settings"),
            spacing="4",
            align_items="center",
        ),
        rx.spacer(),
        rx.color_mode.button(),
        
        width="100%",
        padding="4",
        border_bottom=f"1px solid {rx.color('gray', 3)}",
        align_items="center",
    )
