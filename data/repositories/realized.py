"""Portfolio-scoped, read-only realized sale and closed-position reports."""
from collections import defaultdict
from psycopg2.extras import RealDictCursor
from logic.realized_gains import calculate
from logic.dividend_calculator import calculate_holding_dividends_from_history, get_dividend_tax_rate, dividend_lookup_key


def enrich(trades, holdings, accounts, assets, cache=None, baselines=(), **filters):
    accounts={str(a['id']):a for a in accounts}; assets={str(a['id']):a for a in assets}
    scoped=[]; histories=defaultdict(list)
    for t in trades:
        a=accounts.get(str(t['account_id']));s=assets.get(str(t['asset_id']))
        if not a or not s or s.get('is_deposit'):continue
        row={**t,'account_alias':a.get('account_alias',a['id']),'asset_name':s['name'],
             'ticker':s.get('ticker',''),'market':s.get('market','KR')}
        scoped.append(row);histories[(str(a['id']),str(s['id']))].append(row)
    baselines=[p for p in baselines if p['account_id'] in accounts and p['asset_id'] in assets]
    result=calculate(scoped, holdings, baselines=baselines, **filters)
    result['openings']=[{k:p[k] for k in ('id','account_id','asset_id','date','quantity')} for p in baselines]
    opening_pairs={(p['account_id'],p['asset_id']):p for p in baselines}
    overrides={(str(h['account_id']),str(h['asset_id'])):h['manual_dividend_override']
               for h in holdings if h.get('manual_dividend_override') is not None}
    for p in result['periods']:
        a,s=accounts[p['account_id']],assets[p['asset_id']]
        p.update(asset_name=s['name'],ticker=s.get('ticker',''),account_alias=a.get('account_alias',a['id']))
        key=dividend_lookup_key(s)
        entry=(cache or {}).get(f'div_{key[1]}_{key[0]}') if key else None
        records=entry.get('data') if isinstance(entry,dict) else None
        p.update(dividend_currency='USD' if s.get('market')=='US' else 'KRW',
                 dividend_amount=None,dividend_source='NOT_AVAILABLE')
        if (p['account_id'],p['asset_id']) in overrides:
            # A lifetime override has no per-period allocation information.
            p['dividend_source']='MANUAL_UNALLOCATED'
            continue
        start=p.get('calculation_start_date') or p['start_date']
        if not isinstance(records,list) or not start:continue
        div_history=histories[(p['account_id'],p['asset_id'])]
        b=opening_pairs.get((p['account_id'],p['asset_id']))
        if b:
            from logic.realized_opening import validity
            if validity(b,div_history):continue
            div_history=[dict(id='opening',trade_date=b['date'],trade_type='BUY',quantity=b['quantity'])]+[
                t for t in div_history if str(t['id']) not in b['covered_trades']]
            p['dividend_scope']='SINCE_CONFIRMED_BASELINE'
        details=calculate_holding_dividends_from_history(div_history,records,
            tax_rate=get_dividend_tax_rate(a.get('account_type',''),s.get('market','KR')),is_us=s.get('market')=='US')
        p['dividend_amount']=sum(d['net_amount'] for d in details['history']
            if d['ex_date']>start and (not p['end_date'] or d['ex_date']<=p['end_date']))
        p['dividend_source']='CACHED_CALCULATION'
    return result


def read(db, pid, **filters):
    with db.connect() as conn,conn.cursor(cursor_factory=RealDictCursor) as c:
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        c.execute('SELECT * FROM accounts WHERE portfolio_id=%s',(pid,));accounts=c.fetchall()
        c.execute('SELECT * FROM assets WHERE portfolio_id=%s',(pid,));assets=c.fetchall()
        c.execute('''SELECT t.* FROM trade_history t JOIN accounts a ON a.id=t.account_id
                     WHERE a.portfolio_id=%s''',(pid,));trades=c.fetchall()
        c.execute('''SELECT h.* FROM holdings h JOIN accounts a ON a.id=h.account_id
                     WHERE a.portfolio_id=%s''',(pid,));holdings=c.fetchall()
        keys=[]
        for asset in assets:
            key=dividend_lookup_key(asset)
            if key:keys.append(f'div_{key[1]}_{key[0]}')
        c.execute('SELECT key,data FROM market_cache WHERE key=ANY(%s)',(keys,))
        cache={r['key']:{'data':r['data']} for r in c.fetchall()}
        from data.repositories.realized_openings import load
        baselines=load(c,pid)
    return enrich(trades,holdings,accounts,assets,cache,baselines=baselines,**filters)
