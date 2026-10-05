"""Stable database API for routes, services and existing tools.

SQL lives in data.repositories and data.schema; pool ownership lives in
data.connection. Dependencies are bound at call time so tools/tests can
supply an isolated connection and deterministic IDs without changing callers.
Importing this module neither opens a pool nor runs schema initialization.
"""
from typing import Optional, Dict, Any, List, Tuple
from data import connection, schema
from data.enums import AccountType
from data.normalization import (
    ACCOUNT_TYPES, ACCOUNT_TYPE_ALIASES, generate_id, sanitize_account_names,
    _normalize_asset,
)
from data.repository_context import RepositoryContext
from data.repositories import (
    portfolios, accounts, assets, holdings, trades, crypto, snapshots, market_cache, forex,
)

PoolConnectionWrapper = connection.PoolConnectionWrapper
get_connection_pool = connection.get_connection_pool


def get_connection() -> PoolConnectionWrapper:
    return connection.get_connection(pool_provider=get_connection_pool)


def get_usd_ledgers(portfolio_id=None):
    return forex.get_ledgers(_context(), portfolio_id)


def get_usd_events(account_id=None):
    return forex.get_events(_context(), account_id)


def record_usd_event(account_id, kind, occurred_at, usd_amount=0, krw_amount=0, rate=0, notes=''):
    return forex.record_cash_event(_context(), account_id, kind, occurred_at, usd_amount, krw_amount, rate, notes)


def undo_usd_event(account_id, event_id):
    return forex.undo_event(_context(), account_id, event_id)


def clear_all_caches():
    # Legacy hook: cache lifetimes/invalidation are owned by market services.
    pass


def _context():
    return RepositoryContext(
        get_connection, generate_id, clear_all_caches, _exchange_rate,
    )


def _exchange_rate():
    # Resolve only when a trade omits its USD rate. Repositories do not import
    # backend services or fetch prices; the previous fallback stays unchanged.
    from backend.services import market_service
    return market_service.usd_krw or 1380.0


def init_db():
    return schema.init_db(_context(), schema_initializer=_do_init_db_schema)


def _do_init_db_schema(conn, cursor):
    return schema._do_init_db_schema(_context(), conn, cursor)


def clean_deposit_shadow_accounts():
    return schema.clean_deposit_shadow_accounts(_context())


def get_portfolios():
    return portfolios.get_portfolios(_context())


def get_portfolio(portfolio_id: str):
    return portfolios.get_portfolio(_context(), portfolio_id)


def create_portfolio(name: str, description: str = ""):
    return portfolios.create_portfolio(_context(), name, description)


def update_portfolio(portfolio_id: str, name: str, description: str = ""):
    return portfolios.update_portfolio(_context(), portfolio_id, name, description)


def delete_portfolio(portfolio_id: str):
    return portfolios.delete_portfolio(_context(), portfolio_id)


def get_all_accounts(portfolio_id: str = None):
    return accounts.get_all_accounts(_context(), portfolio_id)


def add_account(
    account_no,
    account_alias,
    account_type,
    deposit_krw=0.0,
    deposit_usd=0.0,
    annual_limit=0.0,
    tax_limit=0.0,
    notes='',
    priority=99,
    limit_preference='ANNUAL',
    current_year_deposit=0.0,
    portfolio_id='default',
):
    return accounts.add_account(
        _context(),
        account_no,
        account_alias,
        account_type,
        deposit_krw,
        deposit_usd,
        annual_limit,
        tax_limit,
        notes,
        priority,
        limit_preference,
        current_year_deposit,
        portfolio_id,
    )


def update_account(
    account_id,
    account_no,
    account_alias,
    account_type,
    deposit_krw,
    deposit_usd,
    annual_limit,
    tax_limit,
    notes='',
    priority=99,
    limit_preference='ANNUAL',
    current_year_deposit=0.0,
):
    return accounts.update_account(
        _context(),
        account_id,
        account_no,
        account_alias,
        account_type,
        deposit_krw,
        deposit_usd,
        annual_limit,
        tax_limit,
        notes,
        priority,
        limit_preference,
        current_year_deposit,
    )


def update_account_settings(account_id, priority, limit_preference, current_year_deposit):
    return accounts.update_account_settings(
        _context(),
        account_id,
        priority,
        limit_preference,
        current_year_deposit,
    )


def update_account_limit_exhausted(account_id, is_exhausted: bool):
    return accounts.update_account_limit_exhausted(_context(), account_id, is_exhausted)


def update_account_priorities(priority_map):
    return accounts.update_account_priorities(_context(), priority_map)


def delete_account(account_id):
    return accounts.delete_account(_context(), account_id)


def get_all_assets(portfolio_id: str = None):
    return assets.get_all_assets(_context(), portfolio_id)


def add_asset(
    name,
    ticker,
    market,
    target_weight,
    allowed_accounts=None,
    is_risk_asset=True,
    is_active=True,
    notes='',
    portfolio_id='default',
    is_deposit=False,
    deposit_principal=0.0,
    interest_rate=0.0,
    start_date='',
    maturity_date='',
    early_termination_rate=0.0,
    tax_rate=15.4,
    lock_rebalance_sell=True,
    account_id=None,
    account_no='',
    include_in_rebalance=True,
    is_dividend_cost_deduct=False,
):
    return assets.add_asset(
        _context(),
        name,
        ticker,
        market,
        target_weight,
        allowed_accounts,
        is_risk_asset,
        is_active,
        notes,
        portfolio_id,
        is_deposit,
        deposit_principal,
        interest_rate,
        start_date,
        maturity_date,
        early_termination_rate,
        tax_rate,
        lock_rebalance_sell,
        account_id,
        account_no,
        include_in_rebalance,
        is_dividend_cost_deduct,
    )


def update_asset(
    asset_id,
    name,
    ticker,
    market,
    target_weight,
    allowed_accounts,
    is_risk_asset=True,
    is_active=True,
    notes='',
    is_deposit=False,
    deposit_principal=0.0,
    interest_rate=0.0,
    start_date='',
    maturity_date='',
    early_termination_rate=0.0,
    tax_rate=15.4,
    lock_rebalance_sell=True,
    account_id=None,
    account_no='',
    include_in_rebalance=True,
    is_dividend_cost_deduct=False,
):
    return assets.update_asset(
        _context(),
        asset_id,
        name,
        ticker,
        market,
        target_weight,
        allowed_accounts,
        is_risk_asset,
        is_active,
        notes,
        is_deposit,
        deposit_principal,
        interest_rate,
        start_date,
        maturity_date,
        early_termination_rate,
        tax_rate,
        lock_rebalance_sell,
        account_id,
        account_no,
        include_in_rebalance,
        is_dividend_cost_deduct,
    )


def toggle_asset_active(asset_id, is_active: bool):
    return assets.toggle_asset_active(_context(), asset_id, is_active)


def delete_asset(asset_id):
    return assets.delete_asset(_context(), asset_id)


def get_holdings_by_account(account_id):
    return holdings.get_holdings_by_account(_context(), account_id)


def get_all_holdings(portfolio_id: str = None):
    return holdings.get_all_holdings(_context(), portfolio_id)


def save_account_holdings(account_id, holdings_data):
    return holdings.save_account_holdings(_context(), account_id, holdings_data)


def sync_account_with_api(account_id, api_data):
    return holdings.sync_account_with_api(_context(), account_id, api_data)


def execute_trade(
    trade_date,
    account_id,
    asset_id,
    trade_type,
    quantity,
    price,
    currency=None,
    exchange_rate=None,
):
    return trades.execute_trade(
        _context(),
        trade_date,
        account_id,
        asset_id,
        trade_type,
        quantity,
        price,
        currency,
        exchange_rate,
    )


def get_trade_history(portfolio_id: str = None):
    return trades.get_trade_history(_context(), portfolio_id)


def delete_trades(trade_ids):
    return trades.delete_trades(_context(), trade_ids)


def apply_transfer_plan(transfer_plan: list) -> Tuple[bool, str]:
    return trades.apply_transfer_plan(_context(), transfer_plan)


def get_crypto_holdings(owner: Optional[str] = None):
    return crypto.get_crypto_holdings(_context(), owner)


def save_crypto_holding(symbol: str, quantity: float, avg_price: float, owner: str = "홍일", notes: str = ""):
    return crypto.save_crypto_holding(_context(), symbol, quantity, avg_price, owner, notes)


def get_rebalance_batch_data(portfolio_id: str) -> Dict[str, Any]:
    return snapshots.get_rebalance_batch_data(_context(), portfolio_id)


def get_overview_batch_data() -> Dict[str, Any]:
    return snapshots.get_overview_batch_data(_context())


def save_market_cache(key: str, data: Any) -> bool:
    return market_cache.save_market_cache(_context(), key, data)


def get_market_cache(key: str) -> Tuple[Optional[Any], float]:
    return market_cache.get_market_cache(_context(), key)


def delete_trade(trade_id):
    return delete_trades([trade_id])


if __name__ == "__main__":
    init_db()
    print("PostgreSQL Database sanitized and initialized!")
