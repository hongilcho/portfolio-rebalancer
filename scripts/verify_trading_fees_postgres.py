"""Actual PostgreSQL transactions, on a disposable loopback synthetic cluster."""
import os,sys,json,subprocess,socket,uuid
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
os.environ['REALIZED_QA_PG_BIN']=os.environ['FEES_QA_PG_BIN']
# Reuse the existing isolated PostgreSQL harness, not its realized-gains tests.
from scripts import verify_realized_postgres as qa
from data.repositories import trades,forex,ledger_adjustments,accounts
from backend.routers.ledger_adjustments import Proposal
from psycopg2.extras import Json
qa.PORT=55446;qa.DB='fees_synthetic'
qa.settings.update(port=qa.PORT,dbname=qa.DB,user='fees_qa')
qa.RUN=ROOT/'backups/local_validation'/('fees_'+uuid.uuid4().hex)
q=qa.query;ctx=qa.ctx

def main():
    with socket.socket() as s:assert s.connect_ex(('127.0.0.1',qa.PORT))!=0,'Isolated QA port occupied'
    qa.RUN.mkdir(parents=True);cluster=qa.RUN/'cluster';pw=qa.RUN/'password';pw.write_text(qa.settings['password'],encoding='ascii')
    env={k:v for k,v in os.environ.items() if not k.startswith('PG')};flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    report=dict(status='failed',production_connections=0,broker_calls=0,checks=[]);started=False
    def passed(name):report['checks'].append(name);print('PASS:',name,flush=True)
    def batch(rid,kind='BUY',qty=10,price=10000,asset='kr',currency='KRW'):
        return trades.execute_batch(ctx,dict(portfolio_id='p',request_id=rid,trade_date='2026-01-03',trades=[dict(account_id='a',asset_id=asset,trade_type=kind,quantity=qty,price=price,currency=currency,exchange_rate=1350 if currency=='USD' else 1)]))
    def finance():return [q('SELECT * FROM '+t+' ORDER BY 1') for t in ('holdings','accounts','trade_history','performance_snapshots','performance_flows','usd_cash_state','usd_cash_events')]
    try:
        with (qa.RUN/'init.log').open('wb') as out:
            subprocess.run([str(qa.BIN/'initdb.exe'),'-D',str(cluster),'-U',qa.settings['user'],'-A','scram-sha-256','--pwfile',str(pw),'--encoding=UTF8','--locale=C'],env=env,stdout=out,stderr=out,creationflags=flags,check=True)
        pw.unlink()
        subprocess.run([str(qa.BIN/'pg_ctl.exe'),'-D',str(cluster),'-l',str(qa.RUN/'server.log'),'-o',f'-h 127.0.0.1 -p {qa.PORT}','-w','start'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags,check=True)
        started=True;admin=qa.guarded(**{**qa.settings,'dbname':'postgres'});admin.autocommit=True
        with admin.cursor() as c:
            c.execute('CREATE DATABASE '+qa.DB)
            for role in ('anon','authenticated','service_role'):c.execute('CREATE ROLE '+role+' NOLOGIN')
        admin.close();qa.schema.init_db(ctx)
        q("INSERT INTO portfolios(id,name) VALUES('p','Synthetic fee QA')")
        q("INSERT INTO accounts(id,account_no,account_alias,account_type,portfolio_id,deposit_krw,deposit_usd) VALUES('a','SYNTHETIC','합성 일반계좌','종합매매','p',1000000,1000)")
        q("INSERT INTO assets(id,name,ticker,market,allowed_accounts,portfolio_id) VALUES('kr','Synthetic ETF','QA-KR','KR','[\"a\"]','p'),('us','Synthetic US ETF','VT','US','[\"a\"]','p'),('gold','Synthetic gold','M04020000','KR','[\"a\"]','p')")
        q('ALTER TABLE accounts DROP COLUMN fee_schedule');before=finance();qa.schema.init_db(ctx);qa.schema.init_db(ctx)
        assert q('SELECT fee_schedule FROM accounts WHERE id=%s',('a',))==[({},)]
        assert [x for x in finance()[0]]==[x for x in before[0]]
        assert q('SELECT deposit_krw,deposit_usd FROM accounts WHERE id=%s',('a',))==[(1000000.0,1000.0)]
        passed('additive repeated migration preserves cash, holdings and legacy history')
        policy={'KR':[{'from':'2026-01-01','rate_pct':'0.0141639'}],'US':[{'from':'2026-01-01','rate_pct':'0.07'}],'GOLD':[{'from':'2026-01-01','rate_pct':'0.2','vat_included':False}]}
        ok,msg=accounts.update_account(ctx,'a','SYNTHETIC','합성 일반계좌','종합매매',None,None,0,0,fee_schedule=policy);assert ok,msg
        assert q('SELECT fee_schedule FROM accounts WHERE id=%s',('a',))[0][0]['US'][0]['rate_pct']=='0.07'
        passed('account settings persist three fee policies without changing balances')
        with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:batch('same-auto-fee-request'),range(2)))
        assert results[0]==results[1] and q('SELECT count(*) FROM trade_history')==[(1,)]
        assert q('SELECT deposit_krw FROM accounts WHERE id=%s',('a',))==[(899986.0,)]
        passed('concurrent duplicate request charges principal and estimated fee once')
        saved=q('SELECT trade_costs FROM trade_history')[0][0]
        q('UPDATE accounts SET fee_schedule=%s WHERE id=%s',(Json({}),'a'))
        assert q('SELECT trade_costs FROM trade_history')[0][0]==saved
        q('UPDATE accounts SET fee_schedule=%s WHERE id=%s',(Json(policy),'a'))
        passed('later policy changes do not rewrite stored rates or costs')
        batch('sell-all','SELL',10,11000);assert q('SELECT quantity FROM holdings WHERE asset_id=%s',('kr',))==[(0.0,)]
        r=qa.realized.read(ctx,'p');assert r['sales'][0]['net_profit_krw'] is None and r['sales'][0]['gross_profit_krw']==10000
        passed('full liquidation retains history and never labels estimates as confirmed net profit')
        before=finance();conn=ctx.connect()
        ok,msg=trades.execute_trade(ctx,'2026-01-04','a','kr','BUY',1,100,'KRW',1,transaction=conn);assert ok,msg
        conn.rollback();conn.close();assert finance()==before
        passed('caller rollback restores principal, fee, holdings and trade audit')
        ok,msg=forex.record_cash_event(ctx,'a','OPENING','2026-01-02T00:00:00+09:00',rate=1350);assert ok,msg
        batch('usd-buy','BUY',2,100,'us','USD')
        assert q('SELECT deposit_usd FROM accounts WHERE id=%s',('a',))==[(799.86,)]
        assert float(q('SELECT usd_balance FROM usd_cash_state')[0][0])==799.86
        passed('US commission updates cash and average-cost USD pool atomically')
        usd_id=q("SELECT id FROM trade_history WHERE asset_id='us'")[0][0]
        ok,msg=trades.delete_trades(ctx,[usd_id]);assert ok,msg
        assert q('SELECT deposit_usd FROM accounts WHERE id=%s',('a',))==[(1000.0,)]
        passed('USD trade cancellation restores original fee and cost pool')
        krw=q('SELECT deposit_krw FROM accounts WHERE id=%s',('a',))[0][0]
        batch('gold-buy','BUY',1,10000,'gold');after=q('SELECT deposit_krw FROM accounts WHERE id=%s',('a',))[0][0]
        assert krw-after==10022
        passed('gold commission includes configured fee VAT exactly once')
        q('UPDATE accounts SET deposit_krw=100 WHERE id=%s',('a',));batch('tight-cash','BUY',1,100)
        assert q('SELECT deposit_krw FROM accounts WHERE id=%s',('a',))==[(0.0,)]
        # Fee is 0 on a 100 KRW order; use a larger explicit policy to test deferral.
        q('UPDATE accounts SET deposit_krw=10000,fee_schedule=%s WHERE id=%s',(Json({'KR':[{'from':'2026-01-01','rate_pct':'1'}]}),'a'))
        batch('deferred-fee','BUY',1,10000)
        assert q('SELECT deposit_krw FROM accounts WHERE id=%s',('a',))==[(0.0,)]
        assert q('SELECT trade_costs FROM trade_history ORDER BY trade_sequence DESC LIMIT 1')[0][0]['status']=='DEFERRED'
        passed('estimated fee shortage preserves a real fill and never makes cash negative')
        protected=lambda:[q('SELECT * FROM '+t+' ORDER BY 1') for t in ('holdings','trade_history','performance_snapshots','performance_flows')]
        before=protected();preview=ledger_adjustments.settlement_preview(ctx,'p','a','USD',999.97,'BALANCE_SETTLEMENT','합성 잔돈 대조')
        p=Proposal(**preview['proposal']).model_dump(mode='json')
        req=dict(request_id='settle-once',proposal=p,token=preview['token'],decisions={},confirmed=True)
        ident=ledger_adjustments.commit(ctx,'p',req)['id'];assert ledger_adjustments.commit(ctx,'p',req)['id']==ident
        assert protected()==before and q('SELECT deposit_usd FROM accounts WHERE id=%s',('a',))==[(999.97,)]
        assert float(q('SELECT cost_krw FROM usd_cash_state')[0][0])==1349959.5
        passed('settlement preserves trades, positions, saved performance and external flows; retry is idempotent')
        assert ledger_adjustments.undo(ctx,'p',ident)['reversed']
        assert q('SELECT deposit_usd FROM accounts WHERE id=%s',('a',))==[(1000.0,)]
        passed('audited settlement cancellation restores cash and USD cost')
        preview=ledger_adjustments.settlement_preview(ctx,'p','a','USD',999.98,'COST_SETTLEMENT','합성 비용 대조')
        req.update(request_id='stale-settle',proposal=preview['proposal'],token=preview['token'])
        q('UPDATE accounts SET deposit_krw=1 WHERE id=%s',('a',))
        try:ledger_adjustments.commit(ctx,'p',req)
        except ValueError as exc:assert '변경' in str(exc)
        else:raise AssertionError('stale preview accepted')
        passed('intervening financial changes reject stale settlement previews')
        report['status']='passed';report['check_count']=len(report['checks'])
    finally:
        if pw.exists():pw.unlink()
        if started:
            result=subprocess.run([str(qa.BIN/'pg_ctl.exe'),'-D',str(cluster),'-m','fast','-w','stop'],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,creationflags=flags)
            report['isolated_cluster_stopped']=result.returncode==0
        (ROOT/'docs/trading-fees-postgres-evidence.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        print(json.dumps(report,ensure_ascii=False),flush=True)

if __name__=='__main__':main()
