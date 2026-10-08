"""Read-only, scoped activity pages. Financial writes stay in their repositories."""
from psycopg2.extras import RealDictCursor

# Each physical NH-linked contribution/conversion/trade appears once.
# Source timestamps are optional: old trades have dates but no reliable time.
ACTIVITY = '''WITH activity AS (
 SELECT 'TRADE:'||t.id AS id,'TRADE'::text AS category,t.trade_date::text AS event_date,
   t.account_id,a.account_alias,t.trade_type AS kind,
   CASE WHEN t.currency='USD' OR ast.market='US' THEN 'USD' ELSE 'KRW' END AS currency,
   (t.quantity*t.price)::numeric AS amount,ast.name AS description,FALSE AS cancelled,
   n.batch_id,NULL::timestamptz AS order_at,
   jsonb_build_object('trade_id',t.id,'asset_id',t.asset_id,'ticker',ast.ticker,'quantity',t.quantity,
     'price',t.price,'exchange_rate',t.exchange_rate,'broker_order_no',t.broker_order_no,'notes',t.notes) AS detail
 FROM trade_history t JOIN accounts a ON a.id=t.account_id LEFT JOIN assets ast ON ast.id=t.asset_id
 LEFT JOIN nh_notice_items n ON n.linked_trade_id=t.id AND n.reversed_at IS NULL
 WHERE a.portfolio_id=%(pid)s AND t.trade_type<>'INIT'
 UNION ALL
 SELECT 'FLOW:'||f.id,'CASH',f.event_date::text,f.account_id,COALESCE(a.account_alias,'삭제된 계좌'),
   CASE WHEN f.amount_krw>0 THEN 'DEPOSIT' ELSE 'WITHDRAW' END,f.currency,f.native_amount,
   CASE WHEN n.payload->>'transfer'='true' THEN '포트폴리오 간 이체' ELSE '외부 투자자금' END,f.voided,n.batch_id,f.recorded_at,
   jsonb_build_object('flow_id',f.id,'exchange_rate',f.exchange_rate,'amount_krw',f.amount_krw,'notes',f.notes,
     'occurred_at',n.payload->>'occurred_at','reported_available_krw',n.payload->>'reported_available_krw','peer_account',peer.account_alias,'cash_linked',n.id IS NOT NULL,'cash_applied',n.payload->>'apply_cash'='true','can_restore',NOT EXISTS(SELECT 1 FROM nh_notice_items x WHERE x.performance_flow_id=f.id AND (x.reversed_at IS NULL OR x.result->>'created_flow'='true')))
 FROM performance_flows f LEFT JOIN accounts a ON a.id=f.account_id
 LEFT JOIN nh_notice_items n ON n.performance_flow_id=f.id AND n.reversed_at IS NULL
 LEFT JOIN accounts peer ON peer.id=n.payload->>'peer_account_id'
 WHERE f.portfolio_id=%(pid)s
 UNION ALL
 SELECT 'USD:'||e.id,'USD',e.event_date::text,e.account_id,a.account_alias,e.kind,'USD',e.usd_amount,
   '달러 원가·환전',e.reversed_at IS NOT NULL,n.batch_id,e.recorded_at,
   jsonb_build_object('usd_event_id',e.id,'krw_amount',e.krw_amount,'fx_rate',e.fx_rate,'occurred_at',e.occurred_at,
     'balance',e.after_state->>'usd_balance','cost_krw',e.after_state->>'cost_krw','notes',e.notes)
 FROM usd_cash_events e JOIN accounts a ON a.id=e.account_id
 LEFT JOIN nh_notice_items n ON n.linked_usd_event_id=e.id AND n.reversed_at IS NULL
 WHERE a.portfolio_id=%(pid)s AND e.kind NOT IN ('BUY','SELL')
 UNION ALL
 SELECT 'NOTICE:'||n.id,CASE WHEN n.kind='KRW_ADJUST' THEN 'ADJUST' ELSE 'CASH' END,
   n.event_date::text,n.account_id,COALESCE(a.account_alias,'삭제된 계좌'),
   CASE WHEN n.kind='KRW_ADJUST' THEN 'KRW_ADJUST' WHEN n.payload->>'external'='false' AND COALESCE(n.payload->>'transfer','false')='false' THEN 'INTERNAL_TRANSFER' ELSE n.kind END,'KRW',
   (n.payload->>'krw_amount')::numeric,CASE WHEN n.payload->>'transfer'='true' THEN '포트폴리오 간 이체' ELSE '원화 입출금·잔고' END,n.reversed_at IS NOT NULL,
   CASE WHEN n.reversed_at IS NULL THEN n.batch_id END,b.created_at,
   jsonb_build_object('source_account',src.account_alias,'destination_account',dest.account_alias,'peer_account',peer.account_alias,'cash_applied',n.payload->>'apply_cash'='true','notes',n.payload->>'notes',
     'occurred_at',n.payload->>'occurred_at','reported_available_krw',n.payload->>'reported_available_krw','delta_krw',n.result->>'delta_krw','previous_batch_id',n.batch_id)
 FROM nh_notice_items n JOIN nh_notice_batches b ON b.id=n.batch_id
 LEFT JOIN accounts a ON a.id=n.account_id LEFT JOIN accounts src ON src.id=n.payload->>'source_account_id'
 LEFT JOIN accounts dest ON dest.id=n.payload->>'destination_account_id' LEFT JOIN accounts peer ON peer.id=n.payload->>'peer_account_id'
 WHERE n.portfolio_id=%(pid)s AND (n.kind='KRW_ADJUST' OR (n.kind IN ('DEPOSIT','WITHDRAW') AND n.performance_flow_id IS NULL))
 UNION ALL
 SELECT 'CANCELLED_BUY:'||n.id,'TRADE',n.event_date::text,n.account_id,COALESCE(a.account_alias,'삭제된 계좌'),
   'BUY','KRW',(n.payload->>'quantity')::numeric*(n.payload->>'price')::numeric,COALESCE(ast.name,'삭제된 종목'),
   TRUE,NULL,b.created_at,jsonb_build_object('quantity',n.payload->>'quantity','price',n.payload->>'price',
     'broker_order_no',n.payload->>'broker_order_no','asset_id',n.payload->>'asset_id','previous_batch_id',n.batch_id)
 FROM nh_notice_items n JOIN nh_notice_batches b ON b.id=n.batch_id LEFT JOIN accounts a ON a.id=n.account_id
 LEFT JOIN assets ast ON ast.id=n.payload->>'asset_id'
 WHERE n.portfolio_id=%(pid)s AND n.kind='BUY' AND n.reversed_at IS NOT NULL
) '''


def read_page(ctx,pid,start,end,account=None,category=None,include_cancelled=False,page=1,page_size=20,asset=None):
    if start>end:raise ValueError('조회 시작일은 종료일보다 늦을 수 없습니다.')
    if category not in (None,'TRADE','CASH','USD','ADJUST'):raise ValueError('기록 종류를 확인해주세요.')
    if not 1<=page<=100000 or not 1<=page_size<=100:raise ValueError('조회 페이지를 확인해주세요.')
    params=dict(pid=pid,start=str(start),end=str(end))
    where=['event_date >= %(start)s','event_date <= %(end)s']
    if account:where.append('account_id=%(account)s');params['account']=account
    if asset:where.append("detail->>'asset_id'=%(asset)s");params['asset']=asset
    if category:where.append('category=%(category)s');params['category']=category
    if not include_cancelled:where.append('NOT cancelled')
    filtered=' WHERE '+' AND '.join(where)
    conn=ctx.connect()
    try:
        c=conn.cursor(cursor_factory=RealDictCursor)
        c.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY')
        c.execute(ACTIVITY+'SELECT COUNT(*) AS total FROM activity'+filtered,params)
        total=c.fetchone()['total'];pages=max(1,(total+page_size-1)//page_size);page=min(page,pages)
        params.update(limit=page_size,offset=(page-1)*page_size)
        c.execute(ACTIVITY+'SELECT * FROM activity'+filtered+' ORDER BY event_date DESC,order_at DESC NULLS LAST,id DESC LIMIT %(limit)s OFFSET %(offset)s',params)
        return dict(items=c.fetchall(),total=total,page=page,pages=pages,page_size=page_size)
    finally:conn.close()
