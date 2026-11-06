"""Read-only presentation metadata from an already calculated realized report."""
def recent_sales(report, accounts, assets, limit=3):
    names = {str(a['id']): a.get('account_alias', '') for a in accounts}
    titles = {str(a['id']): a.get('name', '') for a in assets}
    keys = ('trade_id','trade_date','account_id','asset_id','quantity','status',
            'gross_profit_krw','net_profit_krw','estimated_net_profit_krw')
    return [{**{k: row.get(k) for k in keys},
             'account_alias': names.get(str(row['account_id']), ''),
             'asset_name': titles.get(str(row['asset_id']), '')}
            for row in report.get('sales', [])[:limit]]
