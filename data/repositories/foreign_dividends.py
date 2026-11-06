"""Confirmed USD dividend receipts share NH locks, transaction and audited undo.

No brokerage, quote fetching, schema changes, or historical data rewrites.
"""
from datetime import date
from logic.usd_cost import number,positive,receive
from data.repositories import forex


def record(db,c,pid,row):
    if row.get('external') or any(row.get(k) for k in ('execution','source_account_id','destination_account_id','existing_flow_id','counterparty_flow_id','cross_portfolio')):
        raise ValueError('배당은 외부 투자금이나 계좌 이체로 기록할 수 없습니다.')
    if row.get('tax_receipt_id'):
        return pay_tax(c,pid,row)
    aid,sid=row['account_id'],row['asset_id']
    c.execute('SELECT * FROM assets WHERE id=%s AND portfolio_id=%s',(sid,pid))
    asset=c.fetchone()
    if not asset or asset['market']!='US' or asset.get('is_deposit'):
        raise ValueError('현재 포트폴리오의 미국 상장 배당 종목을 선택해주세요.')
    ex=row.get('dividend_ex_date')
    if not ex or ex>row['event_date']:
        raise ValueError('중복 계산을 막기 위해 확인한 배당락일을 지정해주세요.')
    if row.get('reference_date') and row['reference_date']!=ex:
        raise ValueError('해외 배당의 계산 기준은 확인한 배당락일로 지정해주세요.')
    usd,rate=positive(row['usd_amount']),positive(row['receipt_rate'])
    tax=number(row.get('krw_tax') or 0)
    if tax<0 or tax!=tax.to_integral_value():raise ValueError('원화 세금은 0 이상의 원 단위 금액이어야 합니다.')
    if row.get('krw_amount'):raise ValueError('해외 배당은 실제 수령 달러와 원화 세금을 구분해주세요.')
    gross,foreign_tax,fee=(row.get(k) for k in ('gross_amount','tax_amount','fee_amount'))
    if any(v is None for v in (gross,foreign_tax,fee)) or any(number(v)<0 for v in (gross,foreign_tax,fee)) or abs(number(gross)-number(foreign_tax)-number(fee)-usd)>number('0.00000001'):
        raise ValueError('외화 배정금액·외화세액·수수료·실지급액이 맞지 않습니다.')
    c.execute("""SELECT id FROM nh_notice_items WHERE portfolio_id=%s AND account_id=%s
        AND kind='DIVIDEND' AND reversed_at IS NULL AND payload->>'asset_id'=%s
        AND payload->>'dividend_ex_date'=%s AND payload->>'tax_receipt_id' IS NULL""",(pid,aid,sid,ex))
    if c.fetchone():raise ValueError('이 종목·배당락일의 배당은 이미 반영했습니다. 기존 기록을 확인해주세요.')
    c.execute('SELECT manual_dividend_override FROM holdings WHERE account_id=%s AND asset_id=%s',(aid,sid))
    holding=c.fetchone()
    if holding and holding.get('manual_dividend_override') is not None:
        raise ValueError('수동 배당 보정이 있는 종목입니다. 기존 보정을 확인한 뒤 실제 배당을 연결해주세요.')
    if row.get('tax_cash_applied') and row.get('tax_already_reflected'):raise ValueError('원화 세금의 중복 차감을 선택할 수 없습니다.')
    delta=usd if row['apply_cash'] else number(0)
    event=None
    if delta:
        c.execute("SELECT id FROM usd_cash_events WHERE account_id=%s AND event_date=%s AND kind='DEPOSIT' AND usd_amount=%s AND reversed_at IS NULL",(aid,row['event_date'],usd))
        if c.fetchone():raise ValueError('같은 달러 입금 기록이 있습니다. 이미 잔고에 반영됨으로 선택해 중복 입금을 막아주세요.')
        c.execute('SELECT deposit_krw,deposit_usd FROM accounts WHERE id=%s',(aid,));account=c.fetchone()
        state=forex.load_state(c,aid)
        moment=forex.event_time(row.get('occurred_at') or row['event_date']+'T00:00:00+09:00')
        if state:forex.validate_state(state,account,moment)
        elif number(account['deposit_usd'] or 0)!=0:
            raise ValueError('기존 달러의 시작 기준환율을 먼저 등록해주세요. 배당 원가로 기존 달러 원가를 덮어쓰지 않습니다.')
        else:
            c.execute('SELECT id FROM usd_cash_events WHERE account_id=%s AND reversed_at IS NULL LIMIT 1',(aid,))
            if c.fetchone():raise ValueError('기존 달러 원가 장부를 먼저 확인해주세요.')
        before=forex.snapshot(state) if state else None
        balance,cost=receive(state['usd_balance'] if state else 0,state['cost_krw'] if state else 0,usd,usd*rate)
        if state:forex.save_state(c,aid,balance,cost,moment.date())
        else:c.execute('INSERT INTO usd_cash_state(account_id,usd_balance,cost_krw,last_event_date) VALUES(%s,%s,%s,%s)',(aid,balance,cost,str(moment.date())))
        c.execute('UPDATE accounts SET deposit_usd=%s WHERE id=%s',(balance,aid))
        after=forex.snapshot(dict(usd_balance=balance,cost_krw=cost,last_event_date=moment.date()))
        event=forex.append_event(db,c,aid,'DIVIDEND',moment,usd,usd*rate,rate,0,usd,before,after,'NH 해외 배당 · 입금일 평가환율',asset_id=None)
    # Cash confirmation is separate from recognition of the known dividend tax.
    paid=tax if row.get('tax_cash_applied') else number(0)
    if paid:c.execute('UPDATE accounts SET deposit_krw=deposit_krw-%s WHERE id=%s',(paid,aid))
    return dict(delta_krw=str(-paid),delta_usd=str(delta),usd_event_id=event,
        dividend_matched=True,income_classification='DIVIDEND',external_flow_created=False,
        krw_tax=str(tax),tax_paid=bool(row.get('tax_cash_applied') or row.get('tax_already_reflected')))


def pay_tax(c,pid,row):
    """Later tax debit is another audited NH batch, not another dividend income."""
    c.execute("SELECT * FROM nh_notice_items WHERE id=%s AND portfolio_id=%s AND account_id=%s AND kind='DIVIDEND' AND reversed_at IS NULL",(row['tax_receipt_id'],pid,row['account_id']))
    prior=c.fetchone()
    if not prior:raise ValueError('원화 세금을 연결할 배당 입금 기록을 찾을 수 없습니다.')
    payload=prior['payload']
    if payload.get('dividend_currency')!='USD' or payload.get('tax_receipt_id') or payload.get('asset_id')!=row['asset_id']:
        raise ValueError('원래 해외 배당 입금에만 세금 출금을 연결할 수 있습니다.')
    tax=number(payload.get('krw_tax') or 0)
    if tax<=0 or (payload.get('tax_cash_applied') or payload.get('tax_already_reflected')):raise ValueError('이미 처리했거나 출금할 원화 세금이 없습니다.')
    if row['event_date']<str(prior['event_date']):raise ValueError('세금 출금일은 배당 입금일보다 빠를 수 없습니다.')
    if not row['apply_cash'] or row.get('usd_amount') or not row.get('tax_cash_applied') or row.get('tax_already_reflected'):
        raise ValueError('세금 출금 확인은 원화 예수금에서만 반영합니다.')
    c.execute("SELECT id FROM nh_notice_items WHERE portfolio_id=%s AND payload->>'tax_receipt_id'=%s AND reversed_at IS NULL",(pid,prior['id']))
    if c.fetchone():raise ValueError('이 배당의 원화 세금 출금은 이미 반영했습니다.')
    c.execute('UPDATE accounts SET deposit_krw=deposit_krw-%s WHERE id=%s',(tax,row['account_id']))
    return dict(delta_krw=str(-tax),delta_usd='0',krw_tax=str(tax),tax_paid=True,tax_receipt_id=prior['id'],external_flow_created=False)
