"""Dated money-weighted period returns; no fabricated historical valuations."""
from collections import defaultdict
from datetime import date, timedelta
import calendar
import math
from logic.close_calendar import last_session


def money_weighted_return(start, end, start_value, end_value, flows):
    """Solve XIRR in period-growth space, returning period %, never annualizing.

    Reject nonconventional multi-sign cashflows rather than selecting an
    arbitrary root. Same-day flows use a date convention, not intraday timing.
    """
    days = (end-start).days
    if days <= 0 or start_value <= 0:
        return None, '기간이 하루 이상이고 시작 평가액이 양수여야 합니다.'
    if not flows:
        return (end_value / start_value - 1) * 100, ''
    amounts = defaultdict(float)
    amounts[start] -= start_value
    amounts[end] += end_value
    for f in flows:
        amounts[f['event_date']] -= float(f['amount_krw'])
    ordered = sorted((d,v) for d,v in amounts.items() if abs(v)>1e-8)
    signs = [v>0 for _,v in ordered]
    changes = sum(a!=b for a,b in zip(signs, signs[1:]))
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
    closing_dates={s['snapshot_date'] for s in snapshots if s.get('record_kind')=='close'}
    baseline_dates={s['snapshot_date'] for s in snapshots if s.get('record_kind')=='baseline'}
    close_start=tracking.get('close_started_on')
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
        # Closing history uses the actual last KRX session at a boundary. It
        # does not fill a missing trading day with an earlier available value.
        complete=None
        boundary = (date(int(label[:4]),int(label[5:]),calendar.monthrange(int(label[:4]),int(label[5:]))[1])
                    if kind=='월' else date(int(label),12,31))
        if close_start and end>=close_start and last_session(end)>=baseline:
            expected_end=last_session(end)
            if expected_end>=close_start:
                end=expected_end
            if not partial and start>=close_start:
                start=max(baseline,last_session(start))
            complete=last_session(boundary)<=latest
        sv=float(tracking['baseline_value']) if partial else values.get(start)
        ev=values.get(end)
        if close_start and end>=close_start and end not in closing_dates:
            # A baseline/old query may be present on a date whose close failed.
            ev=None
        baseline_boundary=start==baseline and start in baseline_dates
        if baseline_boundary and not partial:
            sv=float(tracking['baseline_value'])
        if not partial and close_start and start>=close_start and start not in closing_dates and not baseline_boundary:
            sv=None
        row={'kind':kind,'label':label,'start':start,'end':end,'partial':partial,
             'start_value':sv,'end_value':ev,'profit':None,'return_pct':None,'warning':'',
             'period_complete':complete}
        if sv is None or ev is None:
            missing=[str(d) for d,v in ((start,sv),(end,ev)) if v is None]
            row['warning']='경계일 평가액 없음: '+', '.join(missing)
        else:
            included=[f for f in active if start < f['event_date'] <= end or (partial and f['event_date']==start)]
            net=sum(float(f['amount_krw']) for f in included)
            row['net_flow']=net
            row['flow_count']=len(included)
            row['profit']=ev-sv-net
            rate,warning=money_weighted_return(start,end,sv,ev,included)
            # Absent external flows default to zero; recorded edits apply immediately.
            row['return_pct']=rate
            row['warning']=warning
        result.append(row)
    return result


def report_daily(tracking, snapshots, flows):
    """Cumulative performance from the registered baseline on recorded dates.

    Missing dates stay absent. Daily points are NOT one-day returns, and cash
    contributions are subtracted from profit and dated for money-weighted return.
    """
    if not tracking or not snapshots:
        return []
    baseline = tracking['baseline_date']
    start_value = float(tracking['baseline_value'])
    active = sorted((f for f in flows if not f['voided'] and f['event_date'] >= baseline),
                    key=lambda f: f['event_date'])
    included, result = [], []
    flow_index, net = 0, 0.0
    for snapshot in sorted(snapshots, key=lambda s: s['snapshot_date']):
        end = snapshot['snapshot_date']
        if end < baseline:
            continue
        while flow_index < len(active) and active[flow_index]['event_date'] <= end:
            f = active[flow_index]
            included.append(f)
            net += float(f['amount_krw'])
            flow_index += 1
        end_value = float(snapshot['value_krw'])
        if end == baseline and not included and end_value == start_value:
            rate, warning = 0.0, ''
        else:
            rate, warning = money_weighted_return(baseline, end, start_value, end_value, included)
        result.append({'kind': '일', 'label': end.isoformat(), 'start': baseline, 'end': end,
                       'partial': True, 'start_value': start_value, 'end_value': end_value,
                       'value_krw': end_value, 'net_flow': net, 'flow_count': len(included),
                       'profit': end_value - start_value - net,
                       'return_pct': rate, 'warning': warning,
                       'recorded_at': snapshot.get('recorded_at'),
                       'record_kind': snapshot.get('record_kind', 'legacy_view'),
                       'previous_close_date': snapshot.get('previous_close_date'),
                       'valuation_at': snapshot.get('valuation_at'),
                       'ledger_at': snapshot.get('ledger_at'), 'fx':snapshot.get('fx'),
                       'closes':snapshot.get('closes')})
    return result
