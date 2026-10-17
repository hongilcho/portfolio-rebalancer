"""Immutable analysis openings. Never a purchase, cash movement or holding edit."""
from datetime import datetime
from decimal import Decimal
import hashlib
import json
from zoneinfo import ZoneInfo

SCOPE='realized-opening:'
HOLDING_FIELDS=('quantity','avg_price','avg_price_usd','original_avg_price',
                'original_avg_price_usd','buy_fx_rate','first_buy_date')
TRADE_FIELDS=('id','trade_date','trade_type','quantity','price','currency','exchange_rate',
              'cash_delta_krw','cash_delta_usd','trade_costs','accounting_basis')


def plain(value):
    if isinstance(value,dict):return {k:plain(v) for k,v in value.items()}
    if isinstance(value,(list,tuple)):return [plain(v) for v in value]
    if isinstance(value,(int,float,Decimal)) and not isinstance(value,bool):
        n=Decimal(str(value));assert n.is_finite()
        return format(n.normalize(),'f')
    if value is None or isinstance(value,(str,bool)):return value
    return str(value)


def digest(value):
    return hashlib.sha256(json.dumps(plain(value),sort_keys=True,separators=(',',':')).encode()).hexdigest()


def trade_fingerprint(t):
    values={k:t.get(k) for k in TRADE_FIELDS}
    for k in ('trade_costs','accounting_basis'):
        if isinstance(values[k],str):values[k]=json.loads(values[k])
    return digest(values)


def coverage(trades):return {str(t['id']):trade_fingerprint(t) for t in trades}


def active(receipts):
    positions={}
    for result in receipts:
        if isinstance(result,str):result=json.loads(result)
        if not result:continue
        if result.get('kind')=='REALIZED_OPENING':
            for p in result['positions']:positions[(str(p['account_id']),str(p['asset_id']))]=p
        elif result.get('kind')=='REALIZED_OPENING_REVOKED':
            positions={k:p for k,p in positions.items() if p['id']!=result['baseline_id']}
    return list(positions.values())


def validity(opening,trades):
    now=coverage(trades);covered=opening['covered_trades']
    if any(now.get(k)!=v for k,v in covered.items()):
        return '기준 확정 전 매매 기록이 변경되어 계산 기준 재확인이 필요합니다.'
    if any(str(t['id']) not in covered and str(t['trade_date'])<opening['date'] for t in trades):
        return '기준일보다 앞선 거래가 추가되어 계산 기준 재확인이 필요합니다.'
    return ''


def token(holding,trades):
    return digest({'holding':{k:holding.get(k) for k in HOLDING_FIELDS},'trades':coverage(trades)})


def create(pid,holding,trades,request_id,now=None):
    moment=now or datetime.now(ZoneInfo('Asia/Seoul'))
    if any(t['trade_type']=='SELL' for t in trades):
        raise ValueError('기존 매도 내역이 있는 종목은 과거 실현손익을 보존하기 위한 별도 검토가 필요합니다.')
    qty=Decimal(str(holding['quantity']))
    krw=Decimal(str(holding.get('original_avg_price') or holding.get('avg_price') or 0))
    usd=Decimal(str(holding.get('original_avg_price_usd') or holding.get('avg_price_usd') or 0))
    if not all(n.is_finite() for n in (qty,krw,usd)) or qty<=0 or krw<=0 or usd<0 or (holding.get('market')=='US' and usd<=0):
        raise ValueError('보유 수량과 현재 장부의 원가를 확인해주세요.')
    return dict(id=request_id+'/'+str(holding['account_id'])+'/'+str(holding['asset_id']),
        portfolio_id=pid,account_id=str(holding['account_id']),asset_id=str(holding['asset_id']),
        date=moment.date().isoformat(),confirmed_at=moment.isoformat(),quantity=str(qty),avg_krw=str(krw),
        avg_usd=str(usd),first_buy_date=holding.get('first_buy_date') or None,
        covered_trades=coverage(trades),source='CONFIRMED_BOOK',costs_confirmed=False)
