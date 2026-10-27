"""Read history without writing NAVs; crypto captures are insert-once."""
from psycopg2.extras import RealDictCursor,Json
from logic.holding_history import history

def read(ctx,scope,include_crypto=True):
    with ctx.connect() as conn,conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        c.execute('SELECT id,name FROM portfolios ORDER BY created_at,id');portfolios=[dict(r) for r in c.fetchall()]
        ids=[p['id'] for p in portfolios]
        if scope not in ('all','crypto') and scope not in ids:raise ValueError('포트폴리오를 찾을 수 없습니다.')
        crypto=[]
        if scope=='crypto' or (scope=='all' and include_crypto):
            c.execute("SELECT snapshot_date,valuation_at,jsonb_build_object('metrics',payload->'metrics','basis',payload->'basis') AS payload FROM portfolio_analytics.crypto_snapshots ORDER BY snapshot_date")
            crypto=[dict(r) for r in c.fetchall()]
        if scope=='crypto':
            conn.rollback()
            return {**history([],crypto,[],scope='crypto',include_crypto=True),'portfolios':portfolios}
        c.execute('''SELECT portfolio_id,snapshot_date,value_krw,
          CASE WHEN payload ? 'holding_metrics' THEN jsonb_build_object('holding_metrics',payload->'holding_metrics')
            ELSE payload END AS payload,record_kind,valuation_at FROM performance_snapshots
          WHERE portfolio_id=ANY(%s) ORDER BY snapshot_date''', (ids if scope=='all' else [scope],))
        snapshots=[dict(r) for r in c.fetchall()]
        c.execute("""SELECT l.portfolio_id,h->>'date' AS date FROM ledger_adjustments l
          CROSS JOIN LATERAL jsonb_array_elements(l.history) h
          WHERE l.reversed_at IS NULL AND h->>'decision'='UNKNOWN'""")
        uncertain={(r['portfolio_id'],r['date']) for r in c.fetchall()}
        for row in snapshots:
            if (row['portfolio_id'],str(row['snapshot_date'])) in uncertain:
                row['payload']={**row['payload'],'holding_metrics':{'status':'UNCONFIRMED','profit_krw':None,
                    'cost_krw':None,'return_pct':None,'warning':'장부 정정의 과거 기록 확인이 필요합니다.'}}
        # Reconstruction inputs stay private and never appear in the API response.
        c.execute('SELECT * FROM trade_history ORDER BY trade_date,trade_sequence,id');trades=[dict(r) for r in c.fetchall()]
        c.execute("SELECT key,data FROM market_cache WHERE key LIKE 'div_%%'")
        cache={r['key']:{'data':r['data']} for r in c.fetchall()}
        c.execute('SELECT result FROM bookkeeping_requests WHERE scope=ANY(%s) AND result IS NOT NULL ORDER BY sequence',
            (['realized-opening:'+pid for pid in (ids if scope=='all' else [scope])],))
        openings=[r['result'] for r in c.fetchall()]
        conn.rollback()
    result=history(snapshots,crypto,ids,include_crypto=include_crypto,scope=scope,
        reconstruction={'trade_history':trades,'dividend_cache':cache,'realized_openings':openings})
    result['portfolios']=portfolios
    return result

def crypto_exists(ctx,day):
    with ctx.connect() as conn,conn.cursor() as c:
        c.execute('SELECT 1 FROM portfolio_analytics.crypto_snapshots WHERE snapshot_date=%s',(day,))
        return c.fetchone() is not None

def capture_crypto(ctx,day,at,payload):
    with ctx.connect() as conn,conn.cursor() as c:
        c.execute('''INSERT INTO portfolio_analytics.crypto_snapshots(snapshot_date,valuation_at,payload)
          VALUES(%s,%s,%s) ON CONFLICT(snapshot_date) DO NOTHING''',(day,at,Json(payload)))
        saved=c.rowcount==1;conn.commit();return saved
