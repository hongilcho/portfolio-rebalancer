"""Cash-excluded holding-return levels, using the dashboard's valuation engine.

No provider IO, no changes to existing NAV or period-return definitions.
"""
import math
from datetime import date
from backend.valuation_service import evaluate_portfolio
from logic.portfolio_valuation import index_valuation_inputs
from logic.dividend_calculator import dividend_lookup_key, calculate_holding_dividends
from logic.trade_accounting import trade_sort_key

VERSION=1

def number(value):
    n=float(value)
    if not math.isfinite(n):raise ValueError('유효한 평가 근거가 필요합니다.')
    return n

def from_kpi(kpi):
    cost=number(kpi['total_stock_buy'])
    return {'version':VERSION,'value_krw':number(kpi['total_portfolio_eval']),
        'cost_krw':cost,'profit_krw':number(kpi['total_stock_profit']),
        'return_pct':number(kpi['total_stock_return']) if cost>0 else None,
        'dividend_krw':number(kpi.get('total_dividend_profit',0)),'status':'COMPLETE'}

def quantity_matches(holding,trades):
    qty=0.0
    for t in sorted(trades,key=trade_sort_key):
        if t['trade_type']=='INIT':qty=float(t['quantity'])
        elif t['trade_type']=='BUY':qty+=float(t['quantity'])
        elif t['trade_type']=='SELL':qty-=float(t['quantity'])
    return abs(qty-float(holding['quantity']))<1e-6

def financial(ledger,prices,fx,day,*,reconstructed=False):
    """Persist frozen dividend inputs for new records; old ones require evidence.

    A current dividend cache/history may reconstruct an old holding only if the
    dated transactions reconcile with its frozen quantity. Never apply today's
    quantity, cost, manual dividend override, or a later valuation to an old day.
    """
    try:
        if not isinstance(ledger,dict) or not isinstance(prices,dict):raise ValueError('당시 장부 기록 부족')
        if not isinstance(ledger.get('dividend_cache',{}),dict):raise ValueError('당시 배당 기록 부족')
        day=str(day);fx=number(fx)
        if fx<=0:raise ValueError('환율 기록 부족')
        assets=ledger['assets'];accounts=ledger['accounts'];holdings=ledger['holdings']
        trades=[t for t in ledger.get('trade_history',[]) if str(t['trade_date'])[:10]<=day]
        price_rows=[{'id':p['id'],'price_usd':p.get('price_native',0)} for p in prices.values()]
        price_map={k:number(v['price_krw']) for k,v in prices.items()}
        for h in holdings:
            if float(h.get('quantity') or 0)>0 and price_map.get(h['asset_id'],0)<=0:
                raise ValueError('당시 시세 기록 부족')
        def adjustment(h,a,usd_krw,account_type='',trades=None):
            key=dividend_lookup_key(a);records=[]
            if key and float(h.get('quantity') or 0)>0 and h.get('manual_dividend_override') in (None,''):
                row=ledger.get('dividend_cache',{}).get(f'div_{key[1]}_{key[0].upper()}')
                if not row or not isinstance(row.get('data'),list):raise ValueError('당시 배당 근거 부족')
                records=[d for d in row['data'] if str(d['date'])[:10]<=day]
                if reconstructed and float(h.get('quantity') or 0)>0 and not quantity_matches(h,trades or []):
                    raise ValueError('당시 보유 수량과 매매 이력 대조 필요')
            return calculate_holding_dividends(h,a,usd_krw,account_type,trades,records)
        result=evaluate_portfolio(accounts,assets,index_valuation_inputs(holdings,trades,price_rows),price_map,fx,calculate_adjustment=adjustment)
        return {**from_kpi(result['kpi']),'source':'RECONSTRUCTED' if reconstructed else 'RECORDED'}
    except (KeyError,TypeError,ValueError,OverflowError):
        return {'version':VERSION,'status':'UNAVAILABLE','value_krw':None,'cost_krw':None,
            'profit_krw':None,'return_pct':None,'warning':'당시 원가·시세·배당 근거가 충분하지 않습니다.'}

def crypto(holdings,prices):
    # Same owner/symbol universe as /api/crypto/summary and the overview KPI.
    cost=value=0.0
    for h in holdings:
        if h.get('owner','윤아') not in ('홍일','윤아') or h['symbol'].upper() not in ('BTC','ETH'):continue
        qty=number(h['quantity']);avg=number(h['avg_price'])
        if qty<0 or avg<0:raise ValueError('가상자산 장부 확인 필요')
        price=number(prices.get(h['symbol'].upper(),{}).get('price',0))
        if qty>0 and price<=0:raise ValueError('가상자산 시세 누락')
        cost+=qty*avg;value+=qty*price
    return {'version':VERSION,'status':'COMPLETE','source':'RECORDED','value_krw':value,
        'cost_krw':cost,'profit_krw':value-cost,'return_pct':(value-cost)/cost*100 if cost>0 else None}

def combine(parts):
    if not parts or any(p.get('status')!='COMPLETE' for p in parts):
        known_value=(sum(number(p['value_krw']) for p in parts)
            if parts and all(p.get('value_krw') is not None for p in parts) else None)
        return {'status':'UNAVAILABLE','value_krw':known_value,'cost_krw':None,'profit_krw':None,'return_pct':None,
            'warning':'일부 구성 자산의 같은 날짜 기록이 없습니다.'}
    cost=sum(number(p['cost_krw']) for p in parts);profit=sum(number(p['profit_krw']) for p in parts)
    return {'status':'COMPLETE','value_krw':sum(number(p['value_krw']) for p in parts),
        'cost_krw':cost,'profit_krw':profit,'return_pct':profit/cost*100 if cost>0 else None,
        'source':'RECONSTRUCTED' if any(p.get('source')=='RECONSTRUCTED' for p in parts) else 'RECORDED'}

def history(financial_rows,crypto_rows,portfolio_ids,*,include_crypto=False,scope='all',reconstruction=None):
    by_day={};ids=list(portfolio_ids) if scope=='all' else [scope]
    for s in financial_rows:
        pid=s['portfolio_id'];day=str(s['snapshot_date'])
        if pid not in ids:continue
        payload=s.get('payload') or {};m=payload.get('holding_metrics')
        if not m:
            ledger=payload.get('ledger') or {k:payload[k] for k in ('accounts','assets','holdings') if k in payload}
            if reconstruction:
                ledger={**ledger,'trade_history':ledger.get('trade_history',reconstruction.get('trade_history',[])),
                    'dividend_cache':ledger.get('dividend_cache',reconstruction.get('dividend_cache',{}))}
            prices=payload.get('prices',{})
            if isinstance(prices,list):
                prices={p['id']:{**p,'price_krw':p.get('price_krw',p.get('price',0))} for p in prices}
            m=financial(ledger,prices,(payload.get('fx') or {}).get('rate',payload.get('usd_krw',0)),day,reconstructed=True)
        by_day.setdefault(day,{})[pid]={**m,'value_krw':s.get('value_krw',m.get('value_krw')),
            'record_kind':s.get('record_kind'),'valuation_at':s.get('valuation_at')}
    for row in crypto_rows:
        day=str(row['snapshot_date'])
        by_day.setdefault(day,{})['crypto']=row['payload']['metrics']
    rows=[]
    if by_day:
        from logic.close_calendar import sessions
        dates=set(by_day)|{str(d) for d in sessions(date.fromisoformat(min(by_day)),date.fromisoformat(max(by_day)))}
    else:dates=set()
    required=ids+(['crypto'] if include_crypto and scope=='all' else [])
    for day in sorted(dates):
        missing={'status':'UNAVAILABLE','value_krw':None,'cost_krw':None,'profit_krw':None,'return_pct':None,
            'warning':'해당 날짜의 평가 기록이 없습니다.'}
        components={k:by_day.get(day,{}).get(k,dict(missing)) for k in required}
        total=combine(list(components.values())) if scope=='all' else dict(components[scope])
        rows.append({'date':day,**total,'components':components})
    return {'scope':scope,'include_crypto':include_crypto,'rows':rows,'metric_version':VERSION}
