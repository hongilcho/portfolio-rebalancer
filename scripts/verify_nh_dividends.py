"""Real PostgreSQL, synthetic-only NH dividend bookkeeping and reinvestment."""
import json
from pathlib import Path
from copy import deepcopy
from datetime import date
from concurrent.futures import ThreadPoolExecutor
import verify_maintenance_refactor as qa
qa.PORT=55475
qa.CLUSTER=(qa.ROOT/'backups/nh-dividends/cluster').resolve()
qa.EVIDENCE=qa.ROOT/'backups/nh-dividends'


def main():
    pg=qa.isolate();qa.pg=pg;ctx=qa.prepare(pg,'refactor_reads')
    from psycopg2.extras import Json
    from backend.routers.nh_notices import Batch,Row
    from data.repositories import nh_notices,snapshots,activity,holding_history,holdings
    from logic.dividend_calculator import calculate_holding_dividends
    from logic.portfolio_valuation import index_valuation_inputs
    from backend.valuation_service import evaluate_portfolio
    from data import workflow_schema
    with ctx.connect() as conn,conn.cursor() as c:
        # Exercise an existing deployment's original CHECK migration, twice.
        c.execute('ALTER TABLE nh_notice_items DROP CONSTRAINT nh_notice_items_kind_check')
        c.execute("ALTER TABLE nh_notice_items ADD CONSTRAINT nh_notice_items_kind_check CHECK(kind IN ('BUY','DEPOSIT','WITHDRAW','EXCHANGE_IN','KRW_ADJUST'))")
        workflow_schema.initialize(c);workflow_schema.initialize(c)
        for aid,number,kind,cash,sid,amount in [('isa','QA-ISA','ISA',10000,'tiger',40.2),('irp','QA-IRP','IRP',2000,'ace',44)]:
            c.execute("INSERT INTO accounts(id,account_no,account_alias,account_type,deposit_krw,portfolio_id) VALUES(%s,%s,%s,%s,%s,'default')",(aid,number,aid,kind,cash))
            c.execute("INSERT INTO assets(id,name,ticker,market,allowed_accounts,portfolio_id) VALUES(%s,%s,%s,'KR',%s,'default')",(sid,sid,sid.upper(),json.dumps([aid])))
            c.execute("INSERT INTO holdings(id,account_id,asset_id,quantity,avg_price,original_avg_price,first_buy_date) VALUES(%s,%s,%s,100,1000,1000,'2025-12-01')",('h-'+aid,aid,sid))
            c.execute("INSERT INTO trade_history(id,trade_date,account_id,asset_id,trade_type,quantity,price,currency,exchange_rate) VALUES(%s,'2025-12-01',%s,%s,'INIT',100,1000,'KRW',1)",('t-'+aid,aid,sid))
            c.execute('INSERT INTO market_cache(key,data) VALUES(%s,%s)',('div_KR_'+sid.upper(),Json([dict(date='2025-12-31',amount=amount)])))
        c.execute("INSERT INTO performance_tracking(portfolio_id,baseline_date,baseline_value,baseline_payload) VALUES('default','2025-12-01',212000,'{}')")
        c.execute("INSERT INTO performance_snapshots(portfolio_id,snapshot_date,value_krw,payload,record_kind) VALUES('default','2026-01-01',212000,%s,'close')",(Json({'holding_metrics':dict(status='COMPLETE',value_krw=212000,cost_krw=200000,profit_krw=8420,return_pct=4.21,version=1)}),))
        conn.commit()
    initial=qa.fingerprint(ctx)
    historical=holding_history.read(ctx,'default',False)
    def batch(rows,request):
        raw=snapshots.get_overview_batch_data(ctx,'default',cma_support=False)
        expected={a['id']:{k:a[k] for k in ('deposit_krw','deposit_usd')} for a in raw['accounts']}
        return Batch(request_id=request,confirmed=True,rows=rows,expected_cash=expected).model_dump(mode='json')
    def row(aid='isa',sid='tiger',**kw):
        data=dict(kind='DIVIDEND',account_id=aid,asset_id=sid,event_date='2026-01-02',reference_date='2026-01-01',dividend_ex_date='2025-12-31',krw_amount=4025,external=False,apply_cash=True,fingerprint='a'*64,gross_amount=4025,tax_amount=0)
        data.update(kw);return Row(**data)
    def fail(payload,text):
        payload=deepcopy(payload)
        for r in payload['rows']:r.update(fingerprint='f'*64,duplicate_confirmed=True)
        before=qa.fingerprint(ctx)
        try:nh_notices.commit(ctx,'default',payload)
        except ValueError as exc:assert text in str(exc),(text,str(exc))
        else:raise AssertionError('Unsafe receipt accepted')
        assert qa.fingerprint(ctx)==before
    rows=[row(),row('irp','ace',krw_amount=4433,gross_amount=None,tax_amount=None,fingerprint='b'*64)]
    payload=batch(rows,'receipt-batch-1');result=nh_notices.commit(ctx,'default',payload)
    protected=qa.fingerprint(ctx)
    assert nh_notices.commit(ctx,'default',payload)==result and qa.fingerprint(ctx)==protected
    after=snapshots.get_overview_batch_data(ctx,'default',cma_support=False)
    assert {a['id']:a['deposit_krw'] for a in after['accounts']}=={'isa':14025,'irp':6433}
    for table in initial:
        if table not in ('public.accounts','public.nh_notice_items','public.nh_notice_batches'):assert protected[table]==initial[table],table
    prices=[dict(id=s,price_krw=1000) for s in ('tiger','ace')]
    def evaluate(raw):
        cache=raw['dividend_cache']
        def calc(h,a,fx,account_type='',trades=None):return calculate_holding_dividends(h,a,fx,account_type,trades,cache['div_KR_'+a['ticker']]['data'])
        return evaluate_portfolio(raw['accounts'],raw['assets'],index_valuation_inputs(raw['holdings'],raw['trade_history'],prices),{s:1000 for s in ('tiger','ace')},1400,calculate_adjustment=calc)
    valued=evaluate(after);assert valued['kpi']['total_dividend_profit']==8458,valued['kpi']
    assert valued['kpi']['total_portfolio_eval']==220458
    assert holding_history.read(ctx,'default',False)==historical
    assert all(h.get('dividend_receipts') for h in holdings.get_all_holdings(ctx,'default'))
    journal=activity.read_page(ctx,'default',date(2026,1,1),date(2026,1,3))
    assert len(journal['items'])==2 and all(x['kind']=='DIVIDEND' and x['category']=='CASH' for x in journal['items'])
    fail(batch([row(event_date='2026-01-03',fingerprint='c'*64,duplicate_confirmed=True)],'duplicate-event'),'이미 반영')
    fail(batch([row(reference_date='2025-12-30',dividend_ex_date='2025-12-29')],'missing-event'),'공시 배당')
    fail(batch([row(reference_date='2026-01-01',asset_id='absent')],'foreign-asset'),'국내 상장')
    fail(batch([row(reference_date='2026-01-02',dividend_ex_date=None,tax_amount=1)],'invalid-tax'),'맞지')
    fresh=row(reference_date='2026-01-02',dividend_ex_date=None,event_date='2026-01-03')
    fail(batch([fresh,fresh],'within-batch-dup'),'이미 반영')
    reflected=nh_notices.commit(ctx,'default',batch([row(reference_date='2026-01-02',dividend_ex_date=None,apply_cash=False,fingerprint='e'*64)],'already-reflected'))
    assert snapshots.get_overview_batch_data(ctx,'default',cma_support=False)['accounts']==after['accounts']
    nh_notices.undo(ctx,'default',reflected['batch_id'])
    # Receipt is kept once even when reinvested shares are bought afterwards.
    buy=Row(kind='BUY',account_id='isa',asset_id='tiger',event_date='2026-01-03',quantity=4,price=1000,broker_order_no='99991',fingerprint='d'*64)
    traded=nh_notices.commit(ctx,'default',batch([buy],'reinvestment-1'))
    reinvested=snapshots.get_overview_batch_data(ctx,'default',cma_support=False)
    assert next(h for h in reinvested['holdings'] if h['account_id']=='isa')['quantity']==104
    assert evaluate(reinvested)['kpi']['total_dividend_profit']==8458
    assert evaluate(reinvested)['kpi']['total_portfolio_eval']==220458
    try:nh_notices.undo(ctx,'default',result['batch_id'])
    except ValueError as exc:assert '후속 거래' in str(exc)
    else:raise AssertionError('Unsafe earlier receipt undo allowed')
    nh_notices.undo(ctx,'default',traded['batch_id']);nh_notices.undo(ctx,'default',result['batch_id'])
    restored=qa.fingerprint(ctx)
    for table in initial:
        if table not in ('public.nh_notice_items','public.nh_notice_batches','public.trade_history'):assert restored[table]==initial[table],table
    assert evaluate(snapshots.get_overview_batch_data(ctx,'default',cma_support=False))['kpi']['total_dividend_profit']==8420
    # Two clients submit the same event with the same old cash. Exactly one wins.
    left=batch([row()],'concurrent-left');right=batch([row(fingerprint='e'*64)],'concurrent-right')
    def submit(data):
        try:return nh_notices.commit(ctx,'default',data)
        except ValueError:return None
    with ThreadPoolExecutor(max_workers=2) as executor:out=list(executor.map(submit,[left,right]))
    assert sum(v is not None for v in out)==1
    assert next(a for a in snapshots.get_overview_batch_data(ctx,'default',cma_support=False)['accounts'] if a['id']=='isa')['deposit_krw']==14025
    nh_notices.undo(ctx,'default',next(v for v in out if v)['batch_id'])
    # Late publication: link after reinvestment without changing cash or shares.
    from data.repositories.dividend_receipts import match
    pending=nh_notices.commit(ctx,'default',batch([row(dividend_ex_date=None)],'unmatched-receipt'))
    follow=nh_notices.commit(ctx,'default',batch([buy.model_copy(update={'broker_order_no':'99992'})],'late-reinvestment'))
    before_link=qa.fingerprint(ctx);notice=pending['items'][0]['id']
    request=dict(request_id='late-link-request',confirmed=True,ex_date='2025-12-31')
    linked=match(ctx,'default',notice,request)
    assert linked['cash_changed'] is False and match(ctx,'default',notice,request)==linked
    after_link=qa.fingerprint(ctx)
    for table in before_link:
        if table not in ('public.nh_notice_items','public.bookkeeping_requests'):assert before_link[table]==after_link[table],table
    assert evaluate(snapshots.get_overview_batch_data(ctx,'default',cma_support=False))['kpi']['total_dividend_profit']==8425
    assert holding_history.read(ctx,'default',False)==historical
    try:match(ctx,'default',notice,dict(request,request_id='wrong-late-link',ex_date='2025-12-30'))
    except ValueError as exc:assert '이미 확인한' in str(exc)
    else:raise AssertionError('Confirmed dividend link changed')
    assert qa.fingerprint(ctx)==after_link
    nh_notices.undo(ctx,'default',follow['batch_id']);nh_notices.undo(ctx,'default',pending['batch_id'])
    checks=dict(status='SYNTHETIC_POSTGRES_PASSED',old_constraint_upgraded_idempotently=True,
        payment_once_and_request_retry=True,concurrent_duplicate_blocked=True,changed_text_and_payment_date_duplicate_blocked=True,
        invalid_input_and_partial_batch_rolled_back=True,actual_net_replaces_estimate=True,reinvestment_preserves_total_value_and_dividend=True,
        receipt_undo_restores_cash_cost_quantity=True,unsafe_earlier_undo_blocked=True,already_reflected_does_not_add_cash=True,
        external_flows_unchanged=True,existing_period_and_historical_graph_unchanged=True,activity_includes_dividends=True,
        late_link_after_reinvestment_changes_no_cash_or_shares=True,production_access=False,broker_calls=0)
    qa.EVIDENCE.mkdir(parents=True,exist_ok=True);(qa.EVIDENCE/'postgres-result.json').write_text(json.dumps(checks,indent=2))
    print(json.dumps(checks))

if __name__=='__main__':main()
