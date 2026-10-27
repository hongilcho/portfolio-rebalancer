"""Generate synthetic review input with production pure aggregators; no IO except files."""
import json,sys
from datetime import date,timedelta
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from logic.holding_history import history,combine
from logic.close_calendar import is_session

def metric(cost,profit,cash=0):
    return {'version':1,'status':'COMPLETE','source':'RECORDED','cost_krw':cost,'profit_krw':profit,
        'return_pct':profit/cost*100,'value_krw':cost+profit+cash}

def main():
    snapshots=[];coins=[];period=[];start=date(2026,10,5)
    for offset in range(23):
        day=start+timedelta(days=offset)
        if offset and not is_session(day):continue
        a=metric(100000000,5000000+offset*36000+(offset%3)*12000,2000000)
        b=metric(15000000,-1500000+offset*28000,400000)
        c=metric(7000000,800000+offset*7000)
        for pid,m in [('p',a),('q',b)]:
            snapshots.append({'portfolio_id':pid,'snapshot_date':day.isoformat(),'record_kind':'baseline' if not offset else 'close','payload':{'holding_metrics':m}})
        # Deliberate single-date crypto gap proves incomplete totals stay absent.
        if offset!=9:coins.append({'snapshot_date':day.isoformat(),'payload':{'metrics':c}})
        period.append({'label':day.isoformat(),'kind':'일','start':start.isoformat(),'end':day.isoformat(),
            'profit':offset*36000,'return_pct':offset*.034,'value_krw':a['value_krw'],'net_flow':0,'flow_count':0,
            'record_kind':'baseline' if not offset else 'close'})
    live={'p':metric(100000000,5900000,2000000),'q':metric(15000000,-810000,400000),'crypto':metric(7000000,1040000)}
    live['all']=combine([live['p'],live['q'],live['crypto']]);live['without_crypto']=combine([live['p'],live['q']])
    result={s:history(snapshots,coins,['p','q'],scope=s,include_crypto=True) for s in ['p','q','all']}
    result.update(without_crypto=history(snapshots,coins,['p','q']),current=live,period=period,
        components=[{'id':'p','name':'장기 포트폴리오'},{'id':'q','name':'일반투자'},{'id':'crypto','name':'가상자산'}])
    path=ROOT/'frontend/dev/holding-history/synthetic.json';path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf8')
    print('Synthetic review generated; production connections=0; external calls=0')
if __name__=='__main__':main()
