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
        actual=float(receipt['krw_amount']);old=sum(d['net_amount'] for d in matches)
        net+=actual-old
        detail=dict(matches[0]) if matches else dict(ex_date=ex,amount_per_share=None,holding_quantity=None,gross_amount=None,tax_amount=None)
        actual_gross=receipt.get('gross_amount')
        if actual_gross is not None:
            gross+=float(actual_gross)-sum(float(d.get('gross_amount') or 0) for d in matches)
            detail['gross_amount']=float(actual_gross)
        else:detail['gross_amount']=None
        detail['tax_amount']=float(receipt['tax_amount']) if receipt.get('tax_amount') is not None else None
        detail.update(net_amount=actual,source='NH_RECEIPT',receipt_id=receipt.get('receipt_id'),
                      payment_date=receipt['event_date'],reference_date=receipt['reference_date'])
        details=[d for d in details if d['ex_date']!=ex]+[detail]
    if details==result['dividend_details']:return result
    return {**result,'total_dividend_profit':round(net,1),'total_gross_dividend_profit':round(gross,1),
            'dividend_details':sorted(details,key=lambda d:d['ex_date']),'dividend_count':len(details)}
