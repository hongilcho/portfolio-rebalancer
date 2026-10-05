"""Dated money-weighted period returns; no fabricated historical valuations."""
from collections import defaultdict
from datetime import date, timedelta
import calendar
import math


def money_weighted_return(start, end, start_value, end_value, flows):
    """Solve XIRR in period-growth space, returning period %, never annualizing.

    Reject nonconventional multi-sign cashflows rather than selecting an
    arbitrary root. Same-day flows use a date convention, not intraday timing.
    """
    days = (end-start).days
    if days <= 0 or start_value <= 0:
        return None, '기간이 하루 이상이고 시작 평가액이 양수여야 합니다.'
    amounts = defaultdict(float)
    amounts[start] -= start_value
    amounts[end] += end_value
    for f in flows:
        amounts[f['event_date']] -= float(f['amount_krw'])
    ordered = sorted((d,v) for d,v in amounts.items() if abs(v)>1e-8)
    signs = [v>0 for _,v in ordered]
    changes = sum(a!=b for a,b in zip(signs, signs[1:]))
    if end_value==0 and not flows:
        return -100.0, ''
    if not ordered or ordered[0][1]>=0 or changes!=1:
        return None, '입출금 부호가 여러 번 바뀌거나 해가 확정되지 않아 수익률을 표시하지 않습니다.'
    scale=max(abs(v) for _,v in ordered)
    def residual(x):
        return sum((v/scale)*math.exp(-x*(d-start).days/days) for d,v in ordered)
    lo,hi=-20.0,20.0
    if residual(lo)*residual(hi)>0:
        return None, '안정적으로 계산할 수 있는 수익률 범위를 벗어났습니다.'
    for _ in range(120):
        mid=(lo+hi)/2
        if residual(mid)>0:
            lo=mid
        else:
            hi=mid
    rate=math.expm1((lo+hi)/2)*100
    return (0.0 if abs(rate)<1e-10 else rate), ''


def report_periods(tracking, snapshots, flows):
    if not tracking or not snapshots:
        return []
    baseline=tracking['baseline_date']
    latest=max(s['snapshot_date'] for s in snapshots)
    values={s['snapshot_date']:float(s['value_krw']) for s in snapshots}
    active=[f for f in flows if not f['voided']]
    periods=[]
    first=date(baseline.year,baseline.month,1)
    month=first
    while month<=latest:
        last=date(month.year,month.month,calendar.monthrange(month.year,month.month)[1])
        start=max(baseline,month-timedelta(days=1))
        end=min(last,latest)
        periods.append(('월',month.strftime('%Y-%m'),start,end,month==first))
        month=last+timedelta(days=1)
    for year in range(baseline.year,latest.year+1):
        start=max(baseline,date(year-1,12,31))
        end=min(date(year,12,31),latest)
        periods.append(('연',str(year),start,end,year==baseline.year))
    result=[]
    for kind,label,start,end,partial in periods:
        sv=float(tracking['baseline_value']) if partial else values.get(start)
        ev=values.get(end)
        row={'kind':kind,'label':label,'start':start,'end':end,'partial':partial,
             'start_value':sv,'end_value':ev,'profit':None,'return_pct':None,'warning':''}
        if sv is None or ev is None:
            missing=[str(d) for d,v in ((start,sv),(end,ev)) if v is None]
            row['warning']='경계일 평가액 없음: '+', '.join(missing)
        else:
            included=[f for f in active if start < f['event_date'] <= end or (partial and f['event_date']==start)]
            net=sum(float(f['amount_krw']) for f in included)
            row['net_flow']=net
            row['profit']=ev-sv-net
            rate,warning=money_weighted_return(start,end,sv,ev,included)
            confirmed=(tracking['confirmed_revision']==tracking['revision'] and tracking['confirmed_through'] is not None and tracking['confirmed_through']>=end)
            row['return_pct']=rate if confirmed else None
            row['warning']=warning if confirmed else '해당 기간의 외부 입출금 기록 확인이 필요합니다.'
        result.append(row)
    return result
