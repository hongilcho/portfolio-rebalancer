import reflex as rx

config = rx.Config(
    app_name="portfolio_rebalancer",
    plugins=[
        rx.plugins.SitemapPlugin(),
        rx.plugins.TailwindV4Plugin(),
    ]
)