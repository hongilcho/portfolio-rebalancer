"""Repeatable CPU-only benchmarks; deterministic synthetic data, no network/DB."""
from datetime import date,timedelta
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import socket
import statistics
import sys
import time
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
for key in list(os.environ):
    if key.startswith(('AWS_','NAMUH_','SUPABASE_','PG')):os.environ.pop(key)
os.environ.update(PORTFOLIO_LOAD_CONFIG_FILES='0',SUPABASE_URL='',NAMUH_APP_KEY='',NAMUH_APP_SECRET='',PERFORMANCE_CLOSE_SCHEDULER_ENABLED='0',CMA_INTEREST_ENABLED='0')
def blocked(*args,**kwargs):raise RuntimeError('No network/DB in synthetic CPU benchmark')
socket.socket.connect=blocked
import psycopg2
psycopg2.connect=blocked
from logic.dividend_calculator import calculate_holding_dividends_from_history
from logic.dividend_quantity import DividendQuantityIndex
spec=importlib.util.spec_from_file_location('legacy_dividends',ROOT/'tests/fixtures/legacy_dividend_history.py')
legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy)


def measure(fn,repeats=5):
    values=[];result=None
    for _ in range(repeats):
        start=time.perf_counter();result=fn();values.append((time.perf_counter()-start)*1000)
    digest=hashlib.sha256(json.dumps(result,sort_keys=True).encode()).hexdigest()
    return {'median_ms':round(statistics.median(values),3),'sha256':digest}


def dividends():
    base=date(2024,1,1)
    trades=[dict(id='opening',trade_date=str(base),trade_type='INIT',quantity=100)]
    trades += [dict(id=str(i),trade_date=str(base+timedelta(days=i)),trade_type='BUY' if i%3 else 'SELL',quantity=.25 if i%3 else .1) for i in range(1,1000)]
    records=[dict(date=str(base+timedelta(days=i)),amount=.1234) for i in range(20,1000,20)]
    def run(indexed):
        index=DividendQuantityIndex(trades) if indexed else None
        output=[]
        for cut in range(500,620):
            day=str(base+timedelta(days=cut))
            rows=[t for t in trades if t['trade_date']<=day];divs=[d for d in records if d['date']<=day]
            fn=calculate_holding_dividends_from_history if indexed else legacy.calculate_holding_dividends_from_history
            output.append(fn(rows,divs,tax_rate=.15,is_us=True,**({'quantity_index':index} if indexed else {})))
        return output
    before=measure(lambda:run(False));after=measure(lambda:run(True))
    assert before['sha256']==after['sha256'],'Dividend result changed'
    return {'trades':len(trades),'observations':120,'before':before,'after':after,'sorts_before':120,'sorts_after':1}


def rebalance():
    from logic.rebalance_calculator import calculate_rebalancing_plan
    spec = importlib.util.spec_from_file_location('rebalance_cases', ROOT/'tests/test_rebalance_stages.py')
    cases = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cases)
    case = cases.synthetic_case(91, asset_count=80, account_count=24)
    case['scenario'] = 'PERIODIC'
    before = measure(lambda:cases._legacy.calculate_rebalancing_plan(**case))
    after = measure(lambda:calculate_rebalancing_plan(**case))
    assert before['sha256'] == after['sha256'], 'Rebalance result changed'
    return {'assets':80, 'accounts':24, 'holdings':len(case['holdings']),
            'before':before, 'after':after}


def main():
    report={'environment':'CPU-only synthetic, not production latency','dividends':dividends(),'rebalance':rebalance()}
    output=ROOT/'backups/maintenance-refactor/cpu-results.json';output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report))
if __name__=='__main__':main()
