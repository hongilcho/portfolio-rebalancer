"""One statement supplies one consistent history snapshot; valuation stays pure.

All earlier acquisitions are retained. Dividend eligibility is still defined by
Python's existing helper, rather than a second policy written in SQL.
"""
from datetime import datetime
from logic.holding_history import history
from logic.dividend_calculator import dividend_lookup_key

HISTORY_SQL = """
WITH selected AS (
    SELECT id FROM portfolios WHERE %(scope)s='all' OR id=%(scope)s
), uncertain AS (
    SELECT DISTINCT l.portfolio_id,h->>'date' AS date
    FROM ledger_adjustments l CROSS JOIN LATERAL jsonb_array_elements(l.history) h
    WHERE l.reversed_at IS NULL AND h->>'decision'='UNKNOWN'
      AND l.portfolio_id IN (SELECT id FROM selected)
), snapshots AS (
    SELECT portfolio_id,snapshot_date,value_krw,
      CASE WHEN payload ? 'holding_metrics'
        THEN jsonb_build_object('holding_metrics',payload->'holding_metrics') ELSE payload END AS payload,
      record_kind,valuation_at
    FROM performance_snapshots WHERE portfolio_id IN (SELECT id FROM selected)
), replay_needed AS (
    SELECT EXISTS (
        SELECT 1 FROM snapshots s WHERE
        (s.payload->'holding_metrics' IS NULL OR s.payload->'holding_metrics' IN
            ('null'::jsonb,'{}'::jsonb,'[]'::jsonb,'false'::jsonb,'0'::jsonb,'""'::jsonb))
        AND NOT EXISTS (SELECT 1 FROM uncertain u WHERE u.portfolio_id=s.portfolio_id
                        AND u.date=s.snapshot_date::text)
    ) AS needed
)
SELECT json_build_object(
    'portfolios',COALESCE((SELECT json_agg(p ORDER BY p.created_at,p.id) FROM
        (SELECT id,name,created_at FROM portfolios) p),'[]'::json),
    'snapshots',COALESCE((SELECT json_agg(s ORDER BY s.snapshot_date) FROM snapshots s),'[]'::json),
    'uncertain',COALESCE((SELECT json_agg(u) FROM uncertain u),'[]'::json),
    'crypto',COALESCE((SELECT json_agg(c ORDER BY c.snapshot_date) FROM (
        SELECT snapshot_date,valuation_at,
            jsonb_build_object('metrics',payload->'metrics','basis',payload->'basis') AS payload
        FROM portfolio_analytics.crypto_snapshots
        WHERE %(scope)s='crypto' OR (%(scope)s='all' AND %(include_crypto)s)
    ) c),'[]'::json),
    'trades',COALESCE((SELECT json_agg(t ORDER BY t.trade_date,t.trade_sequence,t.id) FROM (
        SELECT t.* FROM trade_history t JOIN accounts a ON a.id=t.account_id
        WHERE a.portfolio_id IN (SELECT id FROM selected) AND (SELECT needed FROM replay_needed)
    ) t),'[]'::json),
    'cache',COALESCE((SELECT json_object_agg(key,json_build_object('data',data))
        FROM market_cache WHERE key LIKE 'div_%%' AND (SELECT needed FROM replay_needed)),'{}'::json),
    'openings',COALESCE((SELECT json_agg(b.result ORDER BY b.sequence) FROM bookkeeping_requests b
        WHERE b.scope IN (SELECT 'realized-opening:'||id FROM selected)
          AND b.result IS NOT NULL AND (SELECT needed FROM replay_needed)),'[]'::json)
)
"""


def build_response(raw, scope, include_crypto):
    """Adapt JSON transport types, then use the unchanged history engine."""
    portfolios = [{'id': p['id'], 'name': p['name']} for p in raw['portfolios']]
    ids = [p['id'] for p in portfolios]
    if scope not in ('all', 'crypto') and scope not in ids:
        raise ValueError('포트폴리오를 찾을 수 없습니다.')

    snapshots = raw['snapshots']
    coins = raw['crypto']
    for row in snapshots + coins:
        if row.get('valuation_at') is not None:
            # psycopg returned datetime before batching. Keep that type so the
            # existing crypto str(datetime) and financial JSON stay identical.
            row['valuation_at'] = datetime.fromisoformat(row['valuation_at'])
    uncertain = {(u['portfolio_id'], u['date']) for u in raw['uncertain']}
    for row in snapshots:
        if (row['portfolio_id'], row['snapshot_date']) in uncertain:
            row['payload'] = {
                **(row.get('payload') or {}),
                'holding_metrics': {
                    'status': 'UNCONFIRMED', 'profit_krw': None, 'cost_krw': None,
                    'return_pct': None,
                    'warning': '장부 정정의 과거 기록 확인이 필요합니다.',
                },
            }
    if scope == 'crypto':
        return {**history([], coins, [], scope='crypto', include_crypto=True),
                'portfolios': portfolios}

    legacy = [r for r in snapshots if not (r.get('payload') or {}).get('holding_metrics')]
    keys = set()
    for row in legacy:
        payload = row.get('payload') or {}
        ledger = payload.get('ledger') or payload
        for asset in ledger.get('assets', []):
            key = dividend_lookup_key(asset)
            if key:
                keys.add(f'div_{key[1]}_{key[0].upper()}')
    # Eligibility remains in one Python policy. The SQL fetches existing cache
    # rows together; only the required keys reach valuation. Never fetch quotes.
    cache = {key: value for key, value in raw['cache'].items() if key in keys}
    result = history(
        snapshots, coins, ids, include_crypto=include_crypto, scope=scope,
        reconstruction={'trade_history': raw['trades'], 'dividend_cache': cache,
                        'realized_openings': raw['openings']},
    )
    result['portfolios'] = portfolios
    return result


def read(ctx, scope, include_crypto=True):
    with ctx.connect() as conn, conn.cursor() as cursor:
        cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        cursor.execute(HISTORY_SQL, {'scope': scope, 'include_crypto': bool(include_crypto)})
        raw = cursor.fetchone()[0]
        conn.rollback()
    return build_response(raw, scope, include_crypto)
