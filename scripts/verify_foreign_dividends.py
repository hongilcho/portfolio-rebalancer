"""Offline synthetic PostgreSQL: foreign dividend -> tax -> reinvestment -> undo.

Requires only this worktree's fresh loopback cluster on 55476. No config/broker IO.
"""
from copy import deepcopy
from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
import json
import verify_maintenance_refactor as qa
qa.PORT=55476
qa.CLUSTER=(qa.ROOT/'backups/foreign-dividends/cluster').resolve()
qa.EVIDENCE=qa.ROOT/'backups/foreign-dividends'


def main():
    pg=qa.isolate();qa.pg=pg;ctx=qa.prepare(pg,'refactor_reads')
    from psycopg2.extras import Json,RealDictCursor
    from backend.routers.nh_notices import Batch,Row
    from data.repositories import nh_notices,snapshots,trades,activity
    from logic.dividend_calculator import calculate_holding_dividends
    from logic.holding_valuation import dividend_profits
    with ctx.connect() as conn,conn.cursor() as c:
        c.execute("INSERT INTO accounts(id,account_no,account_alias,account_type,deposit_krw,deposit_usd,portfolio_id) VALUES('usd','QA-USD','Synthetic USD','일반',20000,70.44,'default')")
        c.execute("INSERT INTO assets(id,name,ticker,market,allowed_accounts,portfolio_id) VALUES('sgov','SGOV','SGOV','US','[\"usd\"]','default')")
        c.execute("INSERT INTO holdings(id,account_id,asset_id,quantity,avg_price,avg_price_usd,original_avg_price,original_avg_price_usd,buy_fx_rate,first_buy_date) VALUES('h','usd','sgov',126,134000,100,134000,100,1340,'2026-10-01')")
        c.execute("INSERT INTO trade_history(id,trade_date,account_id,asset_id,trade_type,quantity,price,currency,exchange_rate) VALUES('init','2026-10-01','usd','sgov','INIT',126,100,'USD',1340)")
        c.execute("INSERT INTO usd_cash_state(account_id,usd_balance,cost_krw,last_event_date) VALUES('usd',70.44,94389.6,'2026-11-05')")
        c.execute("INSERT INTO performance_tracking(portfolio_id,baseline_date,baseline_value,baseline_payload) VALUES('default','2026-10-05',17000000,'{}')")
        c.execute("INSERT INTO performance_snapshots(portfolio_id,snapshot_date,value_krw,payload,record_kind) VALUES('default','2026-11-05',17100000,'{}','close')")
        conn.commit()
    def sql(query,params=()):
        with ctx.connect() as conn,conn.cursor(cursor_factory=RealDictCursor) as c:c.execute(query,params);return c.fetchall()
    def batch(rows,request):
        a=sql("SELECT deposit_krw,deposit_usd FROM accounts WHERE id='usd'")[0]
        return Batch(request_id=request,confirmed=True,rows=rows,expected_cash={'usd':dict(a)}).model_dump(mode='json')
    def row(**changes):
        data=dict(kind='DIVIDEND',dividend_currency='USD',account_id='usd',asset_id='sgov',event_date='2026-11-06',reference_date='2026-11-02',dividend_ex_date='2026-11-02',usd_amount=41.4,gross_amount=41.4,tax_amount=0,fee_amount=0,krw_tax=8540,receipt_rate=1355.2,external=False,apply_cash=True)
        data.update(changes);return Row(**data)
    def fail(rows,text):
        payload=batch(rows,'failed-'+ctx.new_id());before=qa.fingerprint(ctx)
        try:nh_notices.commit(ctx,'default',payload)
        except ValueError as e:assert text in str(e),(text,str(e))
        else:raise AssertionError('Unsafe receipt accepted')
        assert qa.fingerprint(ctx)==before
    def actual():
        raw=snapshots.get_overview_batch_data(ctx,'default',cma_support=False)
        h=raw['holdings'][0];s=raw['assets'][0]
        c=calculate_holding_dividends(h,s,1355.2,'일반',raw['trade_history'],[dict(date='2026-11-02',amount=.328581)])
        return c,dividend_profits(c,h['quantity'],True,1355.2)
    initial=qa.fingerprint(ctx)
    payload=batch([row()],'foreign-receipt-1');saved=nh_notices.commit(ctx,'default',payload)
    protected=qa.fingerprint(ctx);assert nh_notices.commit(ctx,'default',payload)==saved and qa.fingerprint(ctx)==protected
    state=sql("SELECT * FROM usd_cash_state WHERE account_id='usd'")[0]
    assert state['usd_balance']==Decimal('111.84') and state['cost_krw']==Decimal('150494.88'),state
    assert sql("SELECT deposit_krw,deposit_usd FROM accounts WHERE id='usd'")[0]==dict(deposit_krw=20000,deposit_usd=111.84)
    for table in initial:
        if table not in ('public.accounts','public.usd_cash_state','public.usd_cash_events','public.nh_notice_items','public.nh_notice_batches'):assert initial[table]==protected[table],table
    c,profit=actual();assert c['total_dividend_profit']==41.4 and abs(profit[0]-47565.28)<.001
    page=activity.read_page(ctx,'default',date(2026,11,1),date(2026,11,6))
    assert len(page['items'])==1 and page['items'][0]['currency']=='USD' and float(page['items'][0]['amount'])==41.4
    fail([row(event_date='2026-11-07',duplicate_confirmed=True)],'미래') if date.today()<date(2026,11,7) else None
    fail([row(duplicate_confirmed=True)],'이미 반영')
    fail([row(dividend_ex_date=None)],'배당락일')
    fail([row(asset_id='wrong')],'미국 상장')
    fail([row(usd_amount=1,dividend_ex_date='2026-10-01',reference_date='2026-10-01')],'맞지')
    # Two receipt rows cannot partially commit an otherwise successful first row.
    nh_notices.undo(ctx,'default',saved['batch_id'])
    fail([row(),row(duplicate_confirmed=True)],'이미 반영')
    saved=nh_notices.commit(ctx,'default',batch([row()],'foreign-receipt-2'))
    mean=sql("SELECT cost_krw/usd_balance AS rate FROM usd_cash_state WHERE account_id='usd'")[0]['rate']
    ok,msg=trades.execute_trade(ctx,'2026-11-06','usd','sgov','BUY',1,100.46,'USD',9999)
    assert ok,msg
    buy=sql("SELECT id,exchange_rate FROM trade_history WHERE trade_type='BUY'")[0]
    assert abs(Decimal(str(buy['exchange_rate']))-mean)<Decimal('.000001')
    assert actual()[0]['total_dividend_profit']==41.4
    try:nh_notices.undo(ctx,'default',saved['batch_id'])
    except ValueError as e:assert '후속 거래' in str(e)
    else:raise AssertionError('Earlier dividend was undone over a later purchase')
    tax=Row(kind='DIVIDEND',dividend_currency='USD',account_id='usd',asset_id='sgov',event_date='2026-11-06',external=False,apply_cash=True,tax_cash_applied=True,tax_receipt_id=saved['items'][0]['id'])
    tax_payload=batch([tax],'foreign-tax-1');tax_saved=nh_notices.commit(ctx,'default',tax_payload)
    after_tax=qa.fingerprint(ctx);assert nh_notices.commit(ctx,'default',tax_payload)==tax_saved and qa.fingerprint(ctx)==after_tax
    assert sql("SELECT deposit_krw FROM accounts WHERE id='usd'")[0]['deposit_krw']==11460
    assert actual()[0]['total_dividend_profit']==41.4 and abs(actual()[1][0]-47565.28)<.001
    fail([tax],'이미 반영')
    nh_notices.undo(ctx,'default',tax_saved['batch_id'])
    ok,msg=trades.delete_trades(ctx,[buy['id']]);assert ok,msg
    nh_notices.undo(ctx,'default',saved['batch_id'])
    restored=qa.fingerprint(ctx)
    for name in ('public.accounts','public.holdings','public.usd_cash_state','public.performance_snapshots','public.performance_tracking','public.performance_flows'):assert initial[name]==restored[name],name
    # Concurrent distinct requests for the same business dividend: only one may win.
    left=batch([row()],'concurrent-foreign-1');right=batch([row()],'concurrent-foreign-2')
    def submit(data):
        try:return nh_notices.commit(ctx,'default',data)
        except ValueError:return None
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(submit,[left,right]))
    assert sum(r is not None for r in results)==1
    nh_notices.undo(ctx,'default',next(r for r in results if r)['batch_id'])
    # Debit confirmed now, versus already reflected, never both or duplicated.
    now=nh_notices.commit(ctx,'default',batch([row(tax_cash_applied=True)],'paid-immediately'))
    assert sql("SELECT deposit_krw FROM accounts WHERE id='usd'")[0]['deposit_krw']==11460
    nh_notices.undo(ctx,'default',now['batch_id'])
    reflected=nh_notices.commit(ctx,'default',batch([row(apply_cash=False,tax_already_reflected=True)],'already-in-book'))
    assert sql("SELECT deposit_krw,deposit_usd FROM accounts WHERE id='usd'")[0]==dict(deposit_krw=20000,deposit_usd=70.44)
    nh_notices.undo(ctx,'default',reflected['batch_id'])
    result=dict(status='SYNTHETIC_POSTGRES_PASSED',production_access=False,external_calls=0,orders=0,
        dividend_cash_and_average_cost_atomic=True,actual_currency_tax_once=True,tax_pending_paid_reflected=True,
        reinvestment_uses_new_average=True,public_estimate_replaced_once=True,activity_not_duplicated=True,
        same_request_retry_and_concurrent_duplicate_blocked=True,rollback_and_undo_restore_cash_cost_holdings=True,
        original_trades_and_period_performance_preserved=True)
    (qa.EVIDENCE/'postgres-result.json').write_text(json.dumps(result,indent=2),encoding='utf8');print(json.dumps(result))

if __name__=='__main__':main()
