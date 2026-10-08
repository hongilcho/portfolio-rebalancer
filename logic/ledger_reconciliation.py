"""Pure correction previews. Historical errors are confirmed per saved record."""
from copy import deepcopy
import hashlib,json


def serial(value):
    return json.loads(json.dumps(value,default=str))


def digest(value):
    return hashlib.sha256(json.dumps(serial(value),sort_keys=True,separators=(',',':')).encode()).hexdigest()


def ledger(payload):
    if not isinstance(payload,dict):return {}
    book=payload.get('ledger',payload)
    return book if isinstance(book,dict) else {}


def adjustment_delta(proposal,before):
    if proposal['kind']=='HOLDING':
        old=next((h for h in before['holdings'] if h['asset_id']==proposal['asset_id']),{})
        return float(proposal['quantity'])-float(old.get('quantity') or 0)
    key='deposit_usd' if proposal['currency']=='USD' else 'deposit_krw'
    if proposal['kind']=='PAST_WITHDRAWAL': return -float(proposal['amount'])
    return float(proposal['balance'])-float(before['cash'][key] or 0)


def correct_payload(payload,proposal,delta):
    if not isinstance(payload,dict):return None,'당시 장부 기록이 없어 자동 보정할 수 없습니다.'
    p=deepcopy(serial(payload));book=ledger(p)
    if proposal['kind']=='HOLDING':
        rows=book.get('holdings',[])
        h=next((h for h in rows if h.get('account_id')==proposal['account_id'] and h.get('asset_id')==proposal['asset_id']),None)
        if h is None: return None,'당시 보유 수량 기록이 없어 자동 보정할 수 없습니다.'
        q=float(h.get('quantity') or 0)+delta
        price=p.get('prices',{})
        if isinstance(price,list): price={v['id']:v for v in price}
        quote=price.get(proposal['asset_id'],{})
        value=quote.get('price_krw') if isinstance(quote,dict) else quote
        if q<0 or value is None: return None,'당시 수량·종가 기록이 부족합니다.'
        h['quantity']=q;change=delta*float(value)
    else:
        account=next((a for a in book.get('accounts',[]) if a.get('id')==proposal['account_id']),None)
        if not account: return None,'당시 계좌 예수금 기록이 없어 자동 보정할 수 없습니다.'
        key='deposit_usd' if proposal['currency']=='USD' else 'deposit_krw'
        balance=float(account.get(key) or 0)+delta
        if balance<0: return None,'보정하면 당시 예수금이 음수가 됩니다.'
        account[key]=balance
        fx=p.get('fx',{}).get('rate',p.get('usd_krw')) if proposal['currency']=='USD' else 1
        if fx is None: return None,'당시 환율이 없습니다.'
        change=delta*float(fx)
    p['ledger_correction']=dict(event_date=proposal['event_date'],reason=proposal['reason'])
    return (p,change),''


def history_plan(proposal,before,tracking,snapshots,keys=None):
    delta=adjustment_delta(proposal,before)
    if abs(delta)<1e-9 or not tracking:return []
    day=str(proposal['event_date']);baseline=str(tracking['baseline_date']);out=[]
    records=[]
    if day<=baseline:records.append(('baseline',baseline,tracking['baseline_value'],tracking['baseline_payload']))
    records.extend((str(s['snapshot_date']),str(s['snapshot_date']),s['value_krw'],s['payload']) for s in snapshots if str(s['snapshot_date'])>=day)
    for key,day,value,payload in records:
        if keys is not None and key not in keys: continue
        book=ledger(payload)
        if proposal['kind']=='HOLDING':
            source=next((h.get('quantity') for h in book.get('holdings',[]) if h.get('account_id')==proposal['account_id'] and h.get('asset_id')==proposal['asset_id']),None)
        else:
            field='deposit_usd' if proposal['currency']=='USD' else 'deposit_krw'
            source=next((a.get(field) for a in book.get('accounts',[]) if a.get('id')==proposal['account_id']),None)
        fixed,error=correct_payload(payload,proposal,delta)
        out.append(dict(key=key,date=day,value=float(value),corrected_value=float(value)+fixed[1] if fixed else None,
                        recorded_amount=source,can_correct=bool(fixed) and float(value)+fixed[1]>=0,error=error or ('평가액이 음수가 됩니다.' if fixed and float(value)+fixed[1]<0 else '')))
    return out


def mask_uncertain(result,adjustments):
    baseline_unknown=False;dates=set()
    baseline=str((result.get('tracking') or {}).get('baseline_date',''))
    for a in adjustments:
        for h in a.get('history',[]):
            if h['decision']=='UNKNOWN':
                if h['key']=='baseline':baseline_unknown=True
                else:dates.add(h['key'])
    for r in result.get('reports',[])+result.get('daily_reports',[]):
        uncertain=(baseline_unknown and (r.get('partial') or str(r['start'])==baseline)) or str(r['start']) in dates or str(r['end']) in dates
        if uncertain:
            r.update(profit=None,return_pct=None,warning='장부 정정의 과거 평가 기록 확인이 필요합니다.',ledger_unconfirmed=True)
    result['ledger_unconfirmed']=baseline_unknown or bool(dates)
    return result
