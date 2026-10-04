"""Single SQL snapshot readers for overview and rebalancing."""
import json
from typing import Dict, Any
from data.normalization import sanitize_account_names, _normalize_asset
from data.repository_context import RepositoryContext

def get_rebalance_batch_data(db: RepositoryContext, portfolio_id: str) -> Dict[str, Any]:
    """Read one portfolio's calculation inputs in one consistent SQL snapshot.

    Rebalancing needs raw quantities/costs, so trade dates and dividend history
    are deliberately absent from this read.
    """
    sql = """
    SELECT json_build_object(
        'accounts', COALESCE((
            SELECT json_agg(acc ORDER BY acc.account_alias ASC)
            FROM accounts acc WHERE acc.portfolio_id = %s
        ), '[]'::json),
        'assets', COALESCE((
            SELECT json_agg(ast ORDER BY ast.name ASC)
            FROM assets ast WHERE ast.portfolio_id = %s
        ), '[]'::json),
        'holdings', COALESCE((SELECT json_agg(rows) FROM (
            SELECT h.*, a.name as asset_name, a.ticker, a.market, a.is_risk_asset,
                   a.is_deposit, a.deposit_principal, a.interest_rate,
                   a.start_date, a.maturity_date, a.tax_rate, a.lock_rebalance_sell,
                   a.is_dividend_cost_deduct, acc.account_alias, acc.account_type
            FROM holdings h
            JOIN assets a ON h.asset_id = a.id
            JOIN accounts acc ON h.account_id = acc.id
            WHERE acc.portfolio_id = %s
        ) rows), '[]'::json)
    );
    """
    conn = db.connect()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, (portfolio_id, portfolio_id, portfolio_id))
        raw = cursor.fetchone()[0]
    finally:
        conn.close()
    raw['assets'] = [_normalize_asset(r) for r in raw['assets']]
    # Preserve the previous account-by-account aggregation order.
    by_account = {}
    for holding in raw['holdings']:
        by_account.setdefault(str(holding['account_id']), []).append(holding)
    raw['holdings'] = [h for account in raw['accounts']
                       for h in by_account.get(str(account['id']), [])]
    return raw


def get_overview_batch_data(db: RepositoryContext) -> Dict[str, Any]:
    """
    전체 포트폴리오 요약에 필요한 모든 테이블(portfolios, accounts, assets, holdings, crypto_holdings)을
    단 1회의 PostgreSQL 네트워크 왕복(single round-trip)으로 고속 조회
    """
    sql = """
    SELECT json_build_object(
        'portfolios', COALESCE((SELECT json_agg(p ORDER BY p.is_default DESC, p.created_at ASC) FROM portfolios p), '[]'::json),
        'accounts', COALESCE((SELECT json_agg(acc ORDER BY acc.account_alias ASC) FROM accounts acc), '[]'::json),
        'assets', COALESCE((SELECT json_agg(ast ORDER BY ast.name ASC) FROM assets ast), '[]'::json),
        'holdings', COALESCE((SELECT json_agg(h) FROM (
            SELECT h.*, a.name as asset_name, a.ticker, a.market, a.is_risk_asset,
                   a.is_deposit, a.deposit_principal, a.interest_rate, a.start_date, a.maturity_date, a.tax_rate, a.lock_rebalance_sell,
                   a.is_dividend_cost_deduct,
                   acc.account_alias, acc.account_type,
                   (
                       SELECT 
                           CASE 
                               WHEN EXISTS (
                                   SELECT 1 FROM trade_history t0 
                                   WHERE t0.account_id = h.account_id 
                                     AND t0.asset_id = h.asset_id 
                                     AND t0.trade_date <= '2000-01-01'
                               ) THEN '2026-07-01'
                               ELSE MIN(t.trade_date)
                           END
                       FROM trade_history t 
                       WHERE t.account_id = h.account_id 
                         AND t.asset_id = h.asset_id
                   ) as min_trade_date
            FROM holdings h
            JOIN assets a ON h.asset_id = a.id
            JOIN accounts acc ON h.account_id = acc.id
        ) h), '[]'::json),
        'crypto_holdings', COALESCE((SELECT json_agg(c) FROM crypto_holdings c), '[]'::json),
        'trade_history', COALESCE((SELECT json_agg(t ORDER BY t.trade_date ASC, t.id ASC) FROM trade_history t), '[]'::json),
        'dividend_cache', COALESCE((
            SELECT json_object_agg(mc.key, json_build_object(
                'data', mc.data,
                'age_seconds', EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - mc.updated_at))
            )) FROM market_cache mc
            WHERE mc.key IN (
                SELECT 'div_' || a.market || '_' || UPPER(TRIM(a.ticker))
                FROM assets a JOIN holdings h ON h.asset_id = a.id
                WHERE NOT COALESCE(a.is_deposit, FALSE)
                  AND COALESCE(a.ticker, '') NOT IN ('', '-', '없음', 'M04020000')
            )
        ), '{}'::json)
    );
    """
    conn = db.connect()
    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        row = cursor.fetchone()
        raw = row[0] if row else {}
    finally:
        conn.close()

    # Asset 후처리 (JSON 문자열 파싱 및 데이터 타입 정제)
    processed_assets = []
    for r in raw.get('assets', []):
        try:
            raw_accs = json.loads(r['allowed_accounts']) if r.get('allowed_accounts') and isinstance(r['allowed_accounts'], str) else (r.get('allowed_accounts') or [])
        except Exception:
            raw_accs = []
        r['allowed_accounts'] = sanitize_account_names(raw_accs)
        r['account_no'] = r.get('account_no') or ''
        r['is_risk_asset'] = bool(r.get('is_risk_asset', 1))
        r['is_active'] = bool(r.get('is_active', True) if r.get('is_active') is not None else True)
        r['is_deposit'] = bool(r.get('is_deposit', False))
        r['deposit_principal'] = float(r.get('deposit_principal') or 0.0)
        r['interest_rate'] = float(r.get('interest_rate') or 0.0)
        r['start_date'] = r.get('start_date') or ''
        r['maturity_date'] = r.get('maturity_date') or ''
        r['early_termination_rate'] = float(r.get('early_termination_rate') or 0.0)
        r['tax_rate'] = float(r.get('tax_rate') if r.get('tax_rate') is not None else 15.4)
        r['lock_rebalance_sell'] = bool(r.get('lock_rebalance_sell', True) if r.get('lock_rebalance_sell') is not None else True)
        r['include_in_rebalance'] = bool(r.get('include_in_rebalance', True) if r.get('include_in_rebalance') is not None else True)
        r['is_dividend_cost_deduct'] = bool(r.get('is_dividend_cost_deduct', False))
        processed_assets.append(r)
    raw['assets'] = processed_assets
    return raw
