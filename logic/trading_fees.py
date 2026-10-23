"""Versioned account fees. Estimates are never broker-confirmed costs."""
from datetime import date
from decimal import Decimal, ROUND_DOWN
import json

CATEGORIES=('KR','US','GOLD')

def decimal(value):
    try:value=Decimal(str(value))
    except Exception as exc:raise ValueError('수수료 계산 값을 확인해주세요.') from exc
    if not value.is_finite():raise ValueError('수수료는 유한한 숫자여야 합니다.')
    return value

def schedule(value):
    if isinstance(value,str):value=json.loads(value)
    if not isinstance(value,dict) or set(value)-set(CATEGORIES):raise ValueError('수수료 설정 형식을 확인해주세요.')
    out={}
    for category,entries in value.items():
        if not isinstance(entries,list) or len(entries)>100:raise ValueError('수수료 적용 이력을 확인해주세요.')
        clean=[];days=set()
        for e in entries:
            if not isinstance(e,dict) or not {'from','rate_pct'}<=set(e):raise ValueError('수수료 적용일과 요율을 입력해주세요.')
            day=str(e['from']);rate=decimal(e['rate_pct']) if e['rate_pct'] is not None else None
            if date.fromisoformat(day).isoformat()!=day or day in days:raise ValueError('수수료 적용일을 확인해주세요.')
            if rate is not None and not 0<=rate<=10:raise ValueError('수수료율은 0~10% 범위로 입력해주세요.')
            included=e.get('vat_included',True)
            if not isinstance(included,bool):raise ValueError('부가세 포함 여부를 확인해주세요.')
            note=e.get('note','')
            if not isinstance(note,str) or len(note)>200:raise ValueError('수수료 메모는 200자까지 입력해주세요.')
            clean.append({'from':day,'rate_pct':str(rate) if rate is not None else None,'vat_included':included,'note':note})
            days.add(day)
        out[category]=sorted(clean,key=lambda e:e['from'])
    return out

def category(asset):
    if asset.get('is_deposit'):return None
    if asset.get('ticker')=='M04020000':return 'GOLD'
    return 'US' if asset.get('market')=='US' else 'KR'

def estimate(value,asset,day,quantity,price):
    key=category(asset)
    entries=[e for e in schedule(value or {}).get(key,[]) if e['from']<=str(day)]
    if not entries:return None
    policy=entries[-1]
    if policy['rate_pct'] is None:return None
    gross=decimal(quantity)*decimal(price)
    fee=gross*decimal(policy['rate_pct'])/100
    if key=='GOLD' and not policy['vat_included']:fee*=Decimal('1.10')
    unit=Decimal('.01') if key=='US' else Decimal('1')
    fee=fee.quantize(unit,rounding=ROUND_DOWN)
    return dict(krw=str(fee if key!='US' else 0),usd=str(fee if key=='US' else 0),
                status='ESTIMATED',category=key,policy=policy,rounding='DOWN',unit=str(unit),gross=str(gross))


def plan_summary(lines,accounts,assets,day,fx):
    accounts={str(a['id']):a for a in accounts};assets={str(a['id']):a for a in assets}
    total=Decimal(0);missing=0
    for line in lines:
        account=accounts.get(str(line['account_id']),{});asset=assets.get(str(line['asset_id']),{})
        usd=asset.get('market')=='US';price=decimal(line['price'])/(decimal(fx) if usd else 1)
        fee=estimate(account.get('fee_schedule') or {},asset,day,abs(decimal(line['qty'])),price)
        if fee:total+=decimal(fee['krw'])+decimal(fee['usd'])*decimal(fx)
        else:missing+=1
    return dict(estimated_fee_krw=float(total),unconfigured_count=missing)
