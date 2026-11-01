"""Read history without writing NAVs; crypto captures are insert-once."""
from psycopg2.extras import RealDictCursor,Json
from logic.holding_history import history
from logic.dividend_calculator import dividend_lookup_key

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
          WHERE l.reversed_at IS NULL AND h->>'decision'='UNKNOWN'
            AND l.portfolio_id=ANY(%s)""", (ids if scope=='all' else [scope],))
        uncertain={(r['portfolio_id'],r['date']) for r in c.fetchall()}
        for row in snapshots:
            if (row['portfolio_id'],str(row['snapshot_date'])) in uncertain:
                row['payload']={**row['payload'],'holding_metrics':{'status':'UNCONFIRMED','profit_krw':None,
                    'cost_krw':None,'return_pct':None,'warning':'장부 정정의 과거 기록 확인이 필요합니다.'}}
        # Frozen metrics require no replay inputs. Legacy days retain ALL earlier
        # trades in this scope: a graph's visible range is never a cost-basis cutoff.
        trades=[];cache={};openings=[]
        legacy=[r for r in snapshots if not (r.get('payload') or {}).get('holding_metrics')]
        if legacy:
            selected=ids if scope=='all' else [scope]
            c.execute('''SELECT t.* FROM trade_history t JOIN accounts a ON a.id=t.account_id
                WHERE a.portfolio_id=ANY(%s) ORDER BY t.trade_date,t.trade_sequence,t.id''', (selected,))
            trades=[dict(r) for r in c.fetchall()]
            keys=set()
            for row in legacy:
                payload=row.get('payload') or {};ledger=payload.get('ledger') or payload
                for asset in ledger.get('assets',[]):
                    key=dividend_lookup_key(asset)
                    if key:keys.add(f'div_{key[1]}_{key[0].upper()}')
            c.execute('SELECT key,data FROM market_cache WHERE key=ANY(%s)', (sorted(keys),))
            cache={r['key']:{'data':r['data']} for r in c.fetchall()}
            c.execute('SELECT result FROM bookkeeping_requests WHERE scope=ANY(%s) AND result IS NOT NULL ORDER BY sequence',
                (['realized-opening:'+pid for pid in selected],))
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
