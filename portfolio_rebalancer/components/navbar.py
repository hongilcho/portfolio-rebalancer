import reflex as rx

def navbar() -> rx.Component:
    """The navigation bar component."""
    return rx.hstack(
        rx.hstack(
            rx.heading("📈 포트폴리오 매니저", size="5", margin_right="4"),
            rx.hstack(
                rx.link(rx.button("대시보드", variant="ghost", size="2"), href="/"),
                rx.link(rx.button("목표 비중", variant="ghost", size="2"), href="/target"),
                rx.link(rx.button("리밸런싱", variant="ghost", size="2"), href="/rebalance"),
                rx.link(rx.button("매매 기록", variant="ghost", size="2"), href="/history"),
                rx.link(rx.button("설정", variant="ghost", size="2"), href="/settings"),
                spacing="2",
                flex_wrap="wrap",
            ),
            align_items="center",
            flex_wrap="wrap",
            spacing="4"
        ),
        rx.spacer(),
        rx.color_mode.button(),
        
        width="100%",
        padding="4",
        border_bottom=f"1px solid {rx.color('gray', 4, alpha=True)}",
        align_items="center",
        background=rx.color("gray", 1, alpha=True),
        backdrop_filter="blur(10px)",
        position="sticky",
        top="0",
        z_index="1000",
    )
