"""NH cash dividends: existing journal, scoped atomic cash, no external flow."""
from datetime import date
from logic.usd_cost import number,positive

# Correlated inside the existing holdings SELECT, never one query per position.
HOLDING_RECEIPTS_SQL = """(SELECT json_agg(n.payload || jsonb_build_object('receipt_id',n.id) ORDER BY n.sequence)
    FROM nh_notice_items n WHERE n.account_id=h.account_id AND n.portfolio_id=acc.portfolio_id
      AND n.kind='DIVIDEND' AND n.reversed_at IS NULL
      AND n.payload->>'asset_id'=h.asset_id AND n.payload->>'tax_receipt_id' IS NULL) AS dividend_receipts"""


def normalize(holding):
    row=dict(holding)
    if not row.get('dividend_receipts'):row.pop('dividend_receipts',None)
    return row


def record(db,c,pid,row):
    if row.get('dividend_currency')=='USD':
        from data.repositories.foreign_dividends import record as foreign
        return foreign(db,c,pid,row)
    if row.get('tax_receipt_id') or row.get('krw_tax') or row.get('fee_amount') or row.get('tax_cash_applied') or row.get('tax_already_reflected') or row.get('receipt_rate'):
        raise ValueError('원화 배당에는 해외 배당 처리 항목을 지정할 수 없습니다.')
    aid,asset_id=row['account_id'],row['asset_id']
    if (row.get('external') or row.get('execution') or row.get('source_account_id')
        or row.get('destination_account_id') or row.get('existing_flow_id')
        or row.get('counterparty_flow_id') or row.get('cross_portfolio')):
        raise ValueError('배당은 외부 투자금이나 계좌 이체로 기록할 수 없습니다.')
    c.execute('SELECT * FROM assets WHERE id=%s AND portfolio_id=%s',(asset_id,pid))
    asset=c.fetchone()
    if not asset or asset['market']!='KR' or asset.get('is_deposit') or asset.get('ticker')=='M04020000':
        raise ValueError('현재 포트폴리오의 국내 상장 배당 종목을 선택해주세요.')
    reference=row.get('reference_date')
    if not reference:raise ValueError('알림의 배당 기준일을 확인해주세요.')
    if date.fromisoformat(reference)>date.fromisoformat(row['event_date']):
        raise ValueError('입금일은 배당 기준일보다 빠를 수 없습니다.')
    net=positive(row['krw_amount'])
    if net!=net.to_integral_value():raise ValueError('원화 배당금은 원 단위로 입력해주세요.')
    gross,tax=row.get('gross_amount'),row.get('tax_amount')
    if gross is not None:
        gross=number(gross)
        if gross<net or gross!=gross.to_integral_value():raise ValueError('세전금액을 확인해주세요.')
    if tax is not None:
        tax=number(tax)
        if tax<0 or tax!=tax.to_integral_value() or (gross is not None and gross-tax!=net):
            raise ValueError('세전·세후금액과 세금합계가 맞지 않습니다.')
    ex_date=row.get('dividend_ex_date')
    # Business identity is independent of whitespace, message fingerprint and payment date.
    c.execute("""SELECT id FROM nh_notice_items WHERE portfolio_id=%s AND account_id=%s
        AND kind='DIVIDEND' AND reversed_at IS NULL AND payload->>'asset_id'=%s
        AND (payload->>'reference_date'=%s OR (%s IS NOT NULL AND payload->>'dividend_ex_date'=%s))""",
        (pid,aid,asset_id,reference,ex_date,ex_date))
    if c.fetchone():raise ValueError('이 종목·기준일의 배당은 이미 반영했습니다. 기존 기록을 먼저 확인해주세요.')
    if ex_date:validate_link(c,aid,asset,reference,ex_date)
    delta=net if row['apply_cash'] else number(0)
    if delta:c.execute('UPDATE accounts SET deposit_krw=deposit_krw+%s WHERE id=%s',(delta,aid))
    return dict(delta_krw=str(delta),delta_usd='0',dividend_matched=bool(ex_date),
                income_classification='DIVIDEND',external_flow_created=False)


def validate_link(c,aid,asset,reference,ex_date):
    asset_id=asset['id']
    if ex_date>reference:raise ValueError('연결할 배당락일이 기준일보다 늦습니다.')
    key='div_KR_'+asset['ticker'].strip().upper()
    c.execute('SELECT data FROM market_cache WHERE key=%s',(key,));cache=c.fetchone()
    records=(cache or {}).get('data') or []
    if not isinstance(records,list) or not any(d.get('date')==ex_date for d in records):
        raise ValueError('연결할 공시 배당 내역이 변경되었습니다. 다시 확인해주세요.')
    c.execute('SELECT manual_dividend_override FROM holdings WHERE account_id=%s AND asset_id=%s',(aid,asset_id))
    holding=c.fetchone()
    if holding and holding['manual_dividend_override'] is not None:
        raise ValueError('수동 배당 보정이 설정된 종목입니다. 손익 연결 없이 입금만 기록하거나 기존 보정을 먼저 확인해주세요.')


def match(db,pid,notice_id,request):
    """Confirm a late publication without touching cash or rewriting old snapshots."""
    from psycopg2.extras import Json,RealDictCursor
    from data.repositories import nh_notices,bookkeeping
    conn=db.connect()
    try:
        c=conn.cursor(cursor_factory=RealDictCursor)
        c.execute("SELECT account_id FROM nh_notice_items WHERE id=%s AND portfolio_id=%s AND kind='DIVIDEND'",(notice_id,pid))
        item=c.fetchone()
        if not item:raise ValueError('현재 포트폴리오의 배당 입금 기록을 찾을 수 없습니다.')
        aid=item['account_id'];nh_notices.lock_scope(c,pid,[aid])
        c.execute('SELECT * FROM nh_notice_items WHERE id=%s FOR UPDATE',(notice_id,));item=c.fetchone()
        if item['reversed_at']:raise ValueError('취소한 배당 입금에는 연결할 수 없습니다.')
        scope='dividend-match:'+pid
        saved=bookkeeping.begin(c,scope,request['request_id'],dict(request,notice_id=notice_id))
        if saved is not None:conn.rollback();return saved
        row=item['payload'];ex_date=request['ex_date'];previous=row.get('dividend_ex_date')
        if previous and previous!=ex_date:raise ValueError('이미 확인한 배당 연결을 임의로 바꿀 수 없습니다.')
        c.execute('SELECT * FROM assets WHERE id=%s AND portfolio_id=%s',(row['asset_id'],pid));asset=c.fetchone()
        if not asset:raise ValueError('배당 종목 정보를 확인해주세요.')
        if not previous:
            validate_link(c,aid,asset,row['reference_date'],ex_date)
            c.execute("""SELECT id FROM nh_notice_items WHERE portfolio_id=%s AND account_id=%s AND kind='DIVIDEND'
                AND reversed_at IS NULL AND id<>%s AND payload->>'asset_id'=%s AND payload->>'dividend_ex_date'=%s""",(pid,aid,notice_id,row['asset_id'],ex_date))
            if c.fetchone():raise ValueError('다른 입금 기록에 이미 연결된 배당입니다.')
            c.execute('UPDATE nh_notice_items SET payload=%s,result=%s WHERE id=%s',
                (Json(dict(row,dividend_ex_date=ex_date)),Json(dict(item['result'],dividend_matched=True)),notice_id))
        result=dict(linked=True,notice_id=notice_id,ex_date=ex_date,previous_ex_date=previous,cash_changed=False)
        bookkeeping.finish(c,scope,request['request_id'],result)
        conn.commit();db.invalidate();return result
    except Exception:conn.rollback();raise
    finally:conn.close()
