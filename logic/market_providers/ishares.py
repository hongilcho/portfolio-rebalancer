"""Bounded public issuer fallback for SGOV. Pure parser, no DB or cash writes."""
from datetime import date,datetime,timezone,timedelta
from html import unescape
import json,math,re
from curl_cffi import requests

SGOV_URL='https://www.ishares.com/us/products/314116/ishares-0-3-month-treasury-bond-etf-sgov'

def parse_distributions(text):
    if len(text)>4_000_000:raise ValueError('Issuer response too large')
    text=unescape(text)
    columns={}
    for name in ('exDate','payableDate','totalDistribution'):
        matches=list(re.finditer(r'"'+name+r'"\s*:\s*(\{)',text))
        candidates=[]
        for m in matches:
            try:
                column=json.JSONDecoder().raw_decode(text[m.start(1):])[0]
                if column.get('fullName')=='performance.distributions.table.'+name:candidates.append(column['value'])
            except (ValueError,KeyError,TypeError):continue
        if len(candidates)!=1:raise ValueError('Issuer distribution structure changed')
        columns[name]=candidates[0]
    if not columns['exDate'] or len({len(v) for v in columns.values()})!=1:raise ValueError('Incomplete issuer columns')
    records={}
    for ex,pay,amount in zip(columns['exDate'],columns['payableDate'],columns['totalDistribution']):
        ex=datetime.strptime(str(ex),'%Y%m%d').date().isoformat()
        pay=datetime.strptime(str(pay),'%Y%m%d').date().isoformat()
        amount=float(amount)
        if not math.isfinite(amount) or amount<0 or pay<ex or ex in records:raise ValueError('Invalid issuer distribution')
        if amount==0:continue  # Historical zero distributions are not cash dividends.
        records[ex]=dict(date=ex,amount=amount,payment_date=pay,source='ISHARES')
    return sorted(records.values(),key=lambda d:d['date'])

def fetch_sgov():
    response=requests.get(SGOV_URL,impersonate='chrome',timeout=6)
    response.raise_for_status()
    return parse_distributions(response.text)

def incomplete(ticker,market,records,today=None):
    # SGOV is a known monthly payer; do not infer schedules for arbitrary assets.
    if ticker.upper()!='SGOV' or market!='US':return False
    today=today or (datetime.now(timezone.utc)+timedelta(hours=9)).date()
    dates=[date.fromisoformat(d['date']) for d in records if d.get('date') and d['date']<=today.isoformat()]
    recent=sorted(d for d in dates if (today-d).days<=120)
    return not dates or (today-max(dates)).days>45 or any((b-a).days>45 for a,b in zip(recent,recent[1:]))

def reconcile_sgov(yahoo,issuer,today=None):
    today=today or (datetime.now(timezone.utc)+timedelta(hours=9)).date()
    merged={d['date']:d for d in yahoo if d['date']<=today.isoformat()}
    merged.update({d['date']:d for d in issuer if d['date']<=today.isoformat()})
    records=sorted(merged.values(),key=lambda d:d['date'])
    if incomplete('SGOV','US',records,today):raise ValueError('Recent monthly SGOV dividend is missing')
    return records
