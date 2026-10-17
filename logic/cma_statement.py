"""Reconcile posted CMA interest, actual principal and the bank cash chain."""
from collections import Counter
from decimal import Decimal
from logic.cma_interest import amount,fingerprint,moment
from logic import cma_policy

PROFILE='NH_COMMON_CMA_PAID_V1'
# Observed on 2026-10-15 through the existing NH app connection.
PAID_CMA_LABELS=frozenset(('발행어음일괄매도',))
SWEEP_CMA_LABELS=frozenset(('발행어음일괄매수',))
MOVEMENT_LABELS={}
TOTAL='/common/inquiry/v1/totalTransaction'
MOVES='/common/inquiry/v1/depositWithdrawal'
BALANCE='/krstock/inquiry/v1/balance'


def _day(value):
    from datetime import datetime
    if not isinstance(value,str) or len(value)!=8:raise ValueError('date')
    return datetime.strptime(value,'%Y%m%d').date().isoformat()


def normalize(snapshot,observation,*,pid,aid,start_date=None):
    """Blank/KRW currency is accepted only with exact domestic bank cash math.

    The observed domestic history has blank cur_cd. Quantities are never money;
    actual trade amount, interest, tax and after-cash must conserve KRW cash.
    """
    if PROFILE not in cma_policy.VALIDATED_STATEMENT_PROFILES:return {'status':'PROFILE_UNVERIFIED'}
    try:
        from datetime import date
        observed=moment(observation['observed_at']);day=observed.date().isoformat()
        start_date=start_date or day
        if (snapshot.get('complete') is not True or moment(snapshot['observed_at'])!=observed
            or snapshot['end_date']!=day or observation.get('state')!='CASH_RETURNED'
            or not snapshot['start_date']<=start_date<=day
            or not 0<=(observed.date()-date.fromisoformat(start_date)).days<=30):
            return {'status':'STATEMENT_INCOMPLETE'}
        queries=snapshot['queries']
        for path in (TOTAL,MOVES,BALANCE):
            q=queries[path]
            if q.get('complete') is not True or not q.get('pages'):return {'status':'STATEMENT_INCOMPLETE'}
            for page in q['pages']:
                body=page['data']
                if not isinstance(body,dict):return {'status':'STATEMENT_INCOMPLETE'}
                block=body.get('message') or {}
                if not isinstance(block,dict):return {'status':'STATEMENT_INCOMPLETE'}
                signature=(body.get('rsp_cd',block.get('code')),body.get('rsp_msg',block.get('msg')))
                if signature not in {('00166','조회가 완료되었습니다.'),('00165','조회가 계속됩니다.'),('00218','조회가 계속됩니다.')}:
                    return {'status':'BUSINESS_STATUS_UNVERIFIED'}
        events=[];movement_index={};bank_moves=Counter();matched=Counter()
        for index,row in enumerate(queries[MOVES]['rows']):
            event_date=_day(row['trd_dt'])
            if not snapshot['start_date']<=event_date<=day:return {'status':'STATEMENT_INCOMPLETE'}
            kind={'입금':'DEPOSIT','출금':'WITHDRAW'}.get(row.get('act_trd_tp_nm')) or MOVEMENT_LABELS.get(row.get('sps_cd_krl_anm'))
            if kind not in ('DEPOSIT','WITHDRAW'):return {'status':'MOVEMENT_TYPE_UNVERIFIED'}
            value=amount(row['trd_amt']);after=amount(row['trd_af_dca'])
            if value<=0 or after<0:return {'status':'MOVEMENT_TYPE_UNVERIFIED'}
            key=(event_date,row['sps_cd_krl_anm'],value,after)
            if key in movement_index and movement_index[key]!=kind:return {'status':'MOVEMENT_TYPE_UNVERIFIED'}
            movement_index[key]=kind;bank_moves[key]+=1
            if event_date>=start_date:
                events.append(dict(kind=kind,event_date=event_date,amount_krw=str(value),
                    reference_hash=fingerprint(dict(day=event_date,index=index,kind=kind,amount=str(value),after=str(after)))))
        cash=None;positions={};opening=None;last_date=snapshot['start_date'];final_redemption=False
        gross_total=tax_total=fee_total=Decimal(0);daily={}
        for index,row in enumerate(queries[TOTAL]['rows']):
            event_date=_day(row['trd_dt'])
            if not last_date<=event_date<=day:return {'status':'STATEMENT_INCOMPLETE'}
            last_date=event_date
            if row.get('cur_cd') not in ('','KRW'):return {'status':'UNSUPPORTED_TRANSACTION'}
            gross=amount(row['int_amt']);tax=amount(row['tax_sum']);fee=amount(row['trd_orn_fee']);overdue=amount(row['rvb_odu_fee'])
            value=amount(row['trd_amt']);after=amount(row['trd_af_dca'])
            if min(gross,tax,fee,overdue,value,after)<0 or overdue:return {'status':'UNSUPPORTED_TRANSACTION'}
            label=row.get('sps_cd_krl_anm');code=row.get('iem_cd')
            cma=isinstance(code,str) and code.startswith('NHKRCMA')
            redeem=False;buy=False
            if cma:
                if label in PAID_CMA_LABELS:
                    if (value<=gross or tax+fee>gross or amount(row['trd_af_bnc_qty'])!=0 or amount(row['trd_qty'])<=0):
                        return {'status':'INTEREST_POSTING_UNVERIFIED'}
                    principal=value-gross;delta=value-tax-fee;redeem=True
                    if code in positions and positions[code]!=principal:return {'status':'PRINCIPAL_MISMATCH'}
                    positions.setdefault(code,principal)
                elif label in SWEEP_CMA_LABELS and not (gross or tax or fee) and value>0 and amount(row['trd_af_bnc_qty'])>0:
                    delta=-value;buy=True
                else:return {'status':'INTEREST_POSTING_UNVERIFIED'}
            else:
                if gross or tax or fee:return {'status':'UNSUPPORTED_TRANSACTION'}
                key=(event_date,label,value,after);kind=movement_index.get(key)
                if kind is None:return {'status':'BANK_HISTORY_MISMATCH'}
                matched[key]+=1;delta=value if kind=='DEPOSIT' else -value
            before=after-delta
            if before<0 or (cash is not None and cash!=before):return {'status':'BANK_CASH_CHAIN_MISMATCH'}
            if event_date>=start_date and opening is None:opening=before+sum(positions.values(),Decimal(0))
            if redeem:positions.pop(code)
            if buy:positions[code]=positions.get(code,Decimal(0))+value
            cash=after
            if redeem and event_date>=start_date:
                if event_date==day:final_redemption=True
                gross_total+=gross;tax_total+=tax;fee_total+=fee
                item=daily.setdefault(event_date,dict(gross=Decimal(0),tax=Decimal(0),fees=Decimal(0)))
                item['gross']+=gross;item['tax']+=tax;item['fees']+=fee
                if gross-tax-fee:
                    events.append(dict(kind='PAID_INTEREST',event_date=event_date,amount_krw=str(gross-tax-fee),
                        reference_hash=fingerprint(dict(day=event_date,index=index,code=code,gross=str(gross),tax=str(tax),fee=str(fee),after=str(after)))))
        if matched!=bank_moves:return {'status':'BANK_HISTORY_MISMATCH'}
        if not final_redemption or opening is None:return {'status':'INTEREST_POSTING_UNVERIFIED'}
        closing=amount(observation['cash_krw'])
        if cash!=closing or sum(positions.values(),Decimal(0))!=0:return {'status':'STATEMENT_BALANCE_MISMATCH'}
        net=sum((amount(e['amount_krw'])*(1 if e['kind']=='DEPOSIT' else -1) for e in events if e['kind']!='PAID_INTEREST'),Decimal(0))
        if opening+net+gross_total-tax_total-fee_total!=closing:return {'status':'STATEMENT_BALANCE_MISMATCH'}
        return dict(profile=PROFILE,portfolio_id=pid,account_id=aid,currency='KRW',complete=True,
            interest_posting_final=True,start_date=start_date,as_of=observed.isoformat(),events=events,
            opening_cash_krw=str(opening),closing_cash_krw=str(closing),gross_interest_krw=str(gross_total),
            withheld_tax_krw=str(tax_total),interest_fees_krw=str(fee_total),
            daily_interest=[dict(event_date=d,amount_krw=str(v['gross']-v['tax']-v['fees']),
                gross_interest_krw=str(v['gross']),withheld_tax_krw=str(v['tax']),interest_fees_krw=str(v['fees']))
                for d,v in sorted(daily.items())],opening_basis='posted_bank_principal_and_cash_chain')
    except (KeyError,ValueError,TypeError,ArithmeticError):return {'status':'STATEMENT_INCOMPLETE'}
