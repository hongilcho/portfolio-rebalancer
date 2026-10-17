"""Reconcile a complete paid-interest statement against scoped booked movements.

No rate estimates, cash-gap inference, IO, or production NH profile guesses.
The live profile registry is deliberately empty until actual contracts are read.
"""
from collections import Counter
from decimal import Decimal
from logic.cma_interest import amount,fingerprint,moment,confirmed_balance
from logic import cma_policy


def reconcile(statement,ledger,*,pid,aid,book_token,book_cash,observation,booked_income=None):
    result={'status':'STATEMENT_REQUIRED'}
    if not isinstance(statement,dict):return result
    if statement.get('profile') not in cma_policy.VALIDATED_STATEMENT_PROFILES:
        return {'status':'PROFILE_UNVERIFIED'}
    try:
        from datetime import date
        now=moment(observation['observed_at']);day=now.date().isoformat();start=statement.get('start_date')
        if (statement.get('portfolio_id')!=pid or statement.get('account_id')!=aid
            or statement.get('currency')!='KRW' or statement.get('complete') is not True
            or statement.get('interest_posting_final') is not True
            or moment(statement['as_of'])!=now or not isinstance(start,str) or not start<=day
            or not 0<=(now.date()-date.fromisoformat(start)).days<=30):
            return {'status':'STATEMENT_INCOMPLETE'}
        if not isinstance(ledger,list) or not isinstance(statement.get('events'),list) or len(statement['events'])>1000 or len(ledger)>1000:
            return {'status':'STATEMENT_INCOMPLETE'}
        bank_moves=[];book_moves=[];refs=set();interest=Decimal(0);by_day={}
        for row in statement['events']:
            ref=row['reference_hash'];value=amount(row['amount_krw'])
            if (not isinstance(ref,str) or len(ref)!=64 or any(c not in '0123456789abcdef' for c in ref)
                or ref in refs or not start<=row.get('event_date','')<=day or value<=0):
                return {'status':'STATEMENT_INCOMPLETE'}
            refs.add(ref)
            if row['kind']=='PAID_INTEREST':
                interest+=value;by_day[row['event_date']]=by_day.get(row['event_date'],Decimal(0))+value
            elif row['kind'] in ('DEPOSIT','WITHDRAW'):bank_moves.append((row['event_date'],row['kind'],value))
            else:return {'status':'UNSUPPORTED_TRANSACTION'}
        ids=set()
        for row in ledger:
            if row['id'] in ids or not start<=row.get('event_date','')<=day or row.get('kind') not in ('DEPOSIT','WITHDRAW'):
                return {'status':'LEDGER_UNVERIFIED'}
            ids.add(row['id']);value=amount(row['amount_krw'])
            if value<=0:return {'status':'LEDGER_UNVERIFIED'}
            book_moves.append((row['event_date'],row['kind'],value))
        if Counter(bank_moves)!=Counter(book_moves):return {'status':'MOVEMENT_MISMATCH'}
        net=sum((v if k=='DEPOSIT' else -v for _,k,v in book_moves),Decimal(0))
        opening,closing=amount(statement['opening_cash_krw']),amount(statement['closing_cash_krw'])
        if opening<0 or closing!=confirmed_balance(observation) or opening+net+interest!=closing:
            return {'status':'STATEMENT_BALANCE_MISMATCH'}
        breakdown={}
        fields=('gross_interest_krw','withheld_tax_krw','interest_fees_krw')
        if any(k in statement for k in fields):
            values=[amount(statement.get(k)) for k in fields]
            if min(values)<0 or values[0]-values[1]-values[2]!=interest:
                return {'status':'INTEREST_POSTING_UNVERIFIED'}
            breakdown={k:str(v) for k,v in zip(fields,values)}
        booked={}
        for row in booked_income or []:
            d=str(row['event_date']);value=amount(row['amount_krw'])
            if d in booked or row.get('reversed_at') or value<=0 or by_day.get(d)!=value:
                return {'status':'BOOKED_INTEREST_MISMATCH'}
            booked[d]=value
        pending=[dict(event_date=d,amount_krw=str(v)) for d,v in sorted(by_day.items()) if d not in booked]
        daily=statement.get('daily_interest')
        if daily is not None:
            amounts={}
            for item in daily:
                d=item['event_date'];v=amount(item['amount_krw'])
                if (d in amounts or not start<=d<=day or v<0
                    or min(amount(item[k]) for k in fields)<0
                    or amount(item[fields[0]])-amount(item[fields[1]])-amount(item[fields[2]])!=v
                    or by_day.get(d,Decimal(0))!=v):return {'status':'INTEREST_POSTING_UNVERIFIED'}
                amounts[d]=v
            if {d:v for d,v in amounts.items() if v}!=by_day:return {'status':'INTEREST_POSTING_UNVERIFIED'}
            if breakdown and any(sum((amount(i[k]) for i in daily),Decimal(0))!=amount(breakdown[k]) for k in fields):
                return {'status':'INTEREST_POSTING_UNVERIFIED'}
            pending=[dict(i) for i in daily if i['event_date'] not in booked and amount(i['amount_krw'])>0]
        unpaid=interest-sum(booked.values(),Decimal(0))
        if daily is not None:
            breakdown={k:str(sum((amount(i[k]) for i in pending),Decimal(0))) for k in fields}
        result=dict(profile=statement['profile'],portfolio_id=pid,account_id=aid,
            book_token=book_token,event_date=day,observed_at=now.isoformat(),
            source_start=start,paid_items=pending,paid_interest_krw=str(unpaid),closing_cash_krw=str(closing),
            statement_digest=fingerprint(statement),ledger_digest=fingerprint(ledger),**breakdown)
        if opening!=amount(book_cash)-net-sum(booked.values(),Decimal(0)) or closing-amount(book_cash)!=unpaid:
            return dict(result,status='INITIAL_BALANCE_REVIEW',
                prior_difference_krw=str(closing-amount(book_cash)-unpaid))
        return dict(result,status='MATCHED')
    except (KeyError,ValueError,TypeError,ArithmeticError):return {'status':'STATEMENT_INCOMPLETE'}


def require_receipt(receipt,*,pid,aid,token,observation,delta):
    _require_receipt(receipt,pid=pid,aid=aid,token=token,observation=observation,delta=delta,status='MATCHED')


def require_initial_receipt(receipt,*,pid,aid,token,observation,delta):
    _require_receipt(receipt,pid=pid,aid=aid,token=token,observation=observation,delta=delta,status='INITIAL_BALANCE_REVIEW')


def _require_receipt(receipt,*,pid,aid,token,observation,delta,status):
    if not isinstance(receipt,dict) or receipt.get('status')!=status:
        raise ValueError('은행 이자 명세와 입출금 대조가 완료되지 않아 자동 반영하지 않습니다.')
    if (receipt.get('profile') not in cma_policy.VALIDATED_STATEMENT_PROFILES
        or receipt.get('portfolio_id')!=pid or receipt.get('account_id')!=aid
        or receipt.get('book_token')!=token
        or receipt.get('event_date')!=moment(observation['observed_at']).date().isoformat()
        or receipt.get('observed_at')!=moment(observation['observed_at']).isoformat()
        or amount(receipt.get('paid_interest_krw'))!=delta
        or amount(receipt.get('closing_cash_krw'))!=confirmed_balance(observation)):
        raise ValueError('현재 계좌·장부에 일치하는 검증된 이자 명세가 필요합니다.')
