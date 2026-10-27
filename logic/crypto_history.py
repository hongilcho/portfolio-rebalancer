"""Fixed 16:00 KST valuation. No DB, credentials or provider IO."""
from datetime import date, datetime, time, timedelta, timezone
import hashlib
import json
import math
from zoneinfo import ZoneInfo

from logic.holding_history import crypto
from logic.crypto_numbers import stored_real

KST = ZoneInfo('Asia/Seoul')
BASIS = 'UPBIT_KRW_1559_MINUTE_CLOSE'


def moment(value):
    result = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace('Z','+00:00'))
    if result.tzinfo is None:raise ValueError('시간대가 명시된 시각이 필요합니다.')
    return result


def cutoff(day):
    day = day if isinstance(day,date) else date.fromisoformat(str(day))
    return datetime.combine(day,time(16),KST)


def days(start,end):
    start=date.fromisoformat(str(start));end=date.fromisoformat(str(end))
    if not 0 <= (end-start).days <= 3660:raise ValueError('복원 기간을 확인해주세요.')
    return [start+timedelta(days=i) for i in range((end-start).days+1)]


def book(rows):
    result=[];seen=set()
    for row in rows:
        owner=row.get('owner','윤아');symbol=row['symbol'].upper()
        if owner not in ('홍일','윤아') or symbol not in ('BTC','ETH'):continue
        key=(owner,symbol)
        if key in seen:raise ValueError('중복된 가상자산 보유 정보입니다.')
        seen.add(key)
        qty=stored_real(row['quantity']);avg=stored_real(row['avg_price'])
        if not all(math.isfinite(n) and n>=0 for n in (qty,avg)):
            raise ValueError('가상자산 수량·원가를 확인해주세요.')
        result.append(dict(owner=owner,symbol=symbol,quantity=qty,avg_price=avg))
    return sorted(result,key=lambda r:(r['owner'],r['symbol']))


def fingerprint(rows):
    return hashlib.sha256(json.dumps(book(rows),ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def basis_event(rows,at,*,start=None,end=None):
    at=moment(at)
    event=dict(kind='CRYPTO_HOLDINGS_BASIS',at=at.isoformat(),holdings=book(rows),fingerprint=fingerprint(rows))
    if start is not None:
        interval=days(start,end)
        if interval[-1]>at.astimezone(KST).date():raise ValueError('미래까지 보유 불변을 확정할 수 없습니다.')
        event.update(confirmed_start=str(interval[0]),confirmed_through=str(interval[-1]),
                     confirmation='USER_CONFIRMED_UNCHANGED_QUANTITY_AND_COST')
    return event


def basis_at(events,day):
    target=cutoff(day)
    confirmed=[e for e in events if e.get('confirmed_start','9999')<=str(day)<=e.get('confirmed_through','')]
    candidates=confirmed or [e for e in events if moment(e['at'])<=target]
    if not candidates:return None
    chosen=max(candidates,key=lambda e:moment(e['at']))
    if fingerprint(chosen['holdings'])!=chosen['fingerprint']:raise ValueError('가상자산 계산 기준의 지문이 다릅니다.')
    if confirmed:
        for event in events:
            at=moment(event['at'])
            if cutoff(chosen['confirmed_start'])<=at<=cutoff(chosen['confirmed_through']) and event['fingerprint']!=chosen['fingerprint']:
                raise ValueError('보유 불변 확인과 실제 변경 이력이 다릅니다.')
    return chosen


def minute_quote(symbol,day,response):
    """Only the completed 15:59 candle; no later candle or stale fallback."""
    target=cutoff(day);start=target-timedelta(minutes=1)
    if not isinstance(response,list) or len(response)!=1:raise ValueError('오후 4시 기준 분봉이 없습니다.')
    row=response[0]
    if row.get('market')!='KRW-'+symbol or row.get('unit')!=1:raise ValueError('분봉 종목·단위가 다릅니다.')
    utc=datetime.fromisoformat(row['candle_date_time_utc']).replace(tzinfo=timezone.utc)
    local=datetime.fromisoformat(row['candle_date_time_kst']).replace(tzinfo=KST)
    stamp=float(row['timestamp'])/1000
    price=float(row['trade_price'])
    if utc!=start or local!=start or not start.timestamp()<=stamp<target.timestamp():
        raise ValueError('오후 4시 직전 분봉의 시각이 다릅니다.')
    if not math.isfinite(price) or price<=0:raise ValueError('유효한 분봉 가격이 필요합니다.')
    return dict(price=price,source='UPBIT',market=row['market'],candle_at=start.isoformat(),
                last_trade_at=datetime.fromtimestamp(stamp,timezone.utc).isoformat(),unit=1)


def record(rows,prices,day,*,source='RECORDED',basis_fingerprint=None):
    rows=book(rows)
    for symbol in {h['symbol'] for h in rows if h['quantity']>0}:
        quote=prices.get(symbol,{})
        start=cutoff(day)-timedelta(minutes=1)
        if (quote.get('candle_at')!=start.isoformat() or quote.get('source')!='UPBIT'
                or quote.get('market')!='KRW-'+symbol or quote.get('unit')!=1
                or not start<=moment(quote['last_trade_at'])<cutoff(day)):
            raise ValueError('고정 시각의 시세 근거가 없습니다.')
    metrics={**crypto(rows,prices),'source':source}
    return dict(metrics=metrics,holdings=rows,prices=prices,basis=BASIS,
                valuation_at=cutoff(day).isoformat(),holdings_fingerprint=basis_fingerprint or fingerprint(rows))


def restore(rows,quotes,start,end,confirmed_at):
    event=basis_event(rows,confirmed_at,start=start,end=end)
    records=[]
    for day in days(start,end):
        payload=record(rows,quotes.get(str(day),{}),day,source='RECONSTRUCTED',basis_fingerprint=event['fingerprint'])
        payload['confirmation']={k:event[k] for k in ('confirmed_start','confirmed_through','confirmation')}
        records.append(dict(date=str(day),payload=payload))
    return dict(version=1,basis=event,records=records)
