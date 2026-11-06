"""Replace a confirmed estimate once; cash is accounted for separately."""
from copy import deepcopy


def apply_receipts(result,holding):
    receipts=holding.get('dividend_receipts') or []
    if not receipts or holding.get('manual_dividend_override') is not None:return result
    start=result['first_buy_date'];as_of=holding.get('dividend_as_of','9999-12-31')
    details=deepcopy(result['dividend_details']);net=result['total_dividend_profit'];gross=result['total_gross_dividend_profit']
    for receipt in receipts:
        ex=receipt.get('dividend_ex_date')
        if not ex or (start and ex<start) or receipt['event_date']>as_of:continue
        matches=[d for d in details if d['ex_date']==ex]
        # Keep a previously confirmed event even if the provider temporarily loses it.
        foreign=receipt.get('dividend_currency')=='USD'
        actual=float(receipt['usd_amount'] if foreign else receipt['krw_amount']);old=sum(d['net_amount'] for d in matches)
        net+=actual-old
        detail=dict(matches[0]) if matches else dict(ex_date=ex,amount_per_share=None,holding_quantity=None,gross_amount=None,tax_amount=None)
        actual_gross=receipt.get('gross_amount')
        if actual_gross is not None:
            gross+=float(actual_gross)-sum(float(d.get('gross_amount') or 0) for d in matches)
            detail['gross_amount']=float(actual_gross)
        else:detail['gross_amount']=None
        detail['tax_amount']=float(receipt['tax_amount']) if receipt.get('tax_amount') is not None else None
        if foreign:detail.update(krw_tax=float(receipt.get('krw_tax') or 0),foreign_fee=float(receipt.get('fee_amount') or 0),receipt_rate=float(receipt['receipt_rate']),currency='USD')
        detail.update(net_amount=actual,source='NH_RECEIPT',receipt_id=receipt.get('receipt_id'),
                      payment_date=receipt['event_date'],reference_date=receipt['reference_date'])
        details=[d for d in details if d['ex_date']!=ex]+[detail]
    if details==result['dividend_details']:return result
    extra={'dividend_tax_krw':sum(d.get('krw_tax',0) for d in details)} if any('krw_tax' in d for d in details) else {}
    places=4 if any(d.get('currency')=='USD' for d in details) else 1
    return {**result,**extra,'total_dividend_profit':round(net,places),'total_gross_dividend_profit':round(gross,places),
            'dividend_details':sorted(details,key=lambda d:d['ex_date']),'dividend_count':len(details)}
