"""Prepare request-local dividends before invoking pure valuation functions."""
from logic.portfolio_valuation import calculate_portfolio_summary


def evaluate_portfolio(accounts, assets, inputs, price_map, usd_krw, *, calculate_adjustment):
    """One adjustment per account/asset; never cache across requests or accounts."""
    asset_by_id = {str(asset['id']): asset for asset in assets}
    adjustments = {}
    for account in accounts:
        account_id = str(account['id'])
        for holding in inputs.holdings_by_account.get(account_id, []):
            asset_id = str(holding['asset_id'])
            key = (account_id, asset_id)
            adjustments[key] = calculate_adjustment(
                holding, asset_by_id.get(asset_id, {}), usd_krw,
                account_type=account['account_type'],
                trades=inputs.trades_by_holding.get(key),
            )
    return calculate_portfolio_summary(accounts, assets, inputs, adjustments, price_map, usd_krw)


def evaluate_portfolios(portfolios, accounts, assets, inputs, price_map, usd_krw, *, calculate_adjustment):
    """Share one batch index while keeping each portfolio's costs/taxes isolated."""
    accounts_by_pid, assets_by_pid = {}, {}
    for account in accounts:
        pid = str(account.get('portfolio_id') or 'default')
        accounts_by_pid.setdefault(pid, []).append(account)
    for asset in assets:
        pid = str(asset.get('portfolio_id') or 'default')
        assets_by_pid.setdefault(pid, []).append(asset)
    dashboards, errors = {}, []
    for portfolio in portfolios:
        pid = portfolio['id']
        try:
            dashboards[pid] = evaluate_portfolio(
                accounts_by_pid.get(pid, []), assets_by_pid.get(pid, []),
                inputs, price_map, usd_krw, calculate_adjustment=calculate_adjustment,
            )
        except Exception as error:
            errors.append(f"Error calculating overview for portfolio {pid}: {error}")
    return dashboards, errors, accounts_by_pid
