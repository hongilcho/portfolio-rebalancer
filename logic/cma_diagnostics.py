"""Bounded, redacted NH balance diagnostics; independent of accounting code."""
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
import re

CASH_FIELDS=('dca','nxt_dd_dca','nxt2_dd_dca','drn_pbl_amt','nas_amt','tot_aet_amt','tot_eal_amt','tot_byn_amt','tot_eal_pls',
    'rba','int_ny_pmt_amt','ny_rdp_amt','ect_lga','lon_amt')


def _money(value):
    if value is None or isinstance(value,bool):return None
    try:
        number=Decimal(str(value))
        return str(number) if number.is_finite() and 0<=number<=Decimal('1e15') else None
    except (ValueError,InvalidOperation):return None


def _kind(value):
    if value is None:return 'null'
    if isinstance(value,bool):return 'boolean'
    if isinstance(value,dict):return 'object'
    if isinstance(value,list):return 'array'
    if isinstance(value,str):return 'string'
    if isinstance(value,(int,float)):return 'number'
    return 'other'


def balance_diagnostics(data,observed_at=None):
    """No raw text, IDs, names, credentials or unknown field values escape.

    Field names/types help discover the real contract without treating an
    unvalidated response or withdrawal limit as confirmed cash/interest.
    """
    result=dict(profile='NH_CMA_BALANCE_UNVERIFIED_V1',profile_verified=False,
        observed_at=(observed_at or datetime.now(timezone.utc)).isoformat(),
        response_type=_kind(data),business_code=None,prepared_completion_matches=False,
        cash_fields={},header_fields=[],rows=[],row_count=None,truncated=False)
    if not isinstance(data,dict):return result
    code=data.get('rsp_cd')
    if isinstance(code,str) and re.fullmatch(r'[0-9]{5}',code):result['business_code']=code
    result['prepared_completion_matches']=code=='00000' and data.get('rsp_msg')=='조회가 완료되었습니다.'
    header,rows=data.get('Output_0'),data.get('Output_1')
    result.update(header_type=_kind(header),rows_type=_kind(rows))
    if isinstance(header,dict):
        for name in CASH_FIELDS:
            value=_money(header.get(name))
            result['cash_fields'][name]=dict(present=name in header,valid=value is not None,value=value)
        names=[k for k in header if isinstance(k,str) and re.fullmatch(r'[a-z][a-z0-9_]{0,47}',k)]
        result['header_fields']=[dict(name=k,type=_kind(header[k])) for k in sorted(names)[:100]]
        result['truncated']=len(header)>100
    if isinstance(rows,list):
        result['row_count']=len(rows)
        result['truncated']=result['truncated'] or len(rows)>20
        for index,row in enumerate(rows[:20]):
            if not isinstance(row,dict):
                result['rows'].append(dict(index=index,type=_kind(row)));continue
            ticker,name=row.get('iem_cd'),row.get('iem_nm')
            cma=(isinstance(ticker,str) and ticker.startswith('NHKRCMA')) or (isinstance(name,str) and 'CMA' in name)
            rp=isinstance(ticker,str) and ticker.startswith('RP')
            result['rows'].append(dict(index=index,cma_marker=cma,rp_marker=rp,
                evaluation_krw=_money(row.get('eal_amt')),
                valuation_profit_krw=_money(row.get('eal_pls_amt')),
                quantity=_money(row.get('rsdl_qty')),integrated_quantity=_money(row.get('itg_bnc_qty'))))
    return result


def public_diagnostics(value):
    """Re-project the producer's output at the API boundary; drop extra data."""
    result=dict(profile='NH_CMA_BALANCE_UNVERIFIED_V1',profile_verified=False,
        observed_at=None,business_code=None,prepared_completion_matches=False,
        cash_fields={},header_fields=[],rows=[],row_count=None,truncated=True)
    if not isinstance(value,dict):return result
    try:
        stamp=datetime.fromisoformat(value.get('observed_at',''))
        if stamp.tzinfo is not None:result['observed_at']=stamp.isoformat()
    except (ValueError,TypeError):pass
    kinds={'null','boolean','object','array','string','number','other'}
    for key in ('response_type','header_type','rows_type'):
        if value.get(key) in kinds:result[key]=value[key]
    code=value.get('business_code')
    if isinstance(code,str) and re.fullmatch(r'[0-9]{5}',code):result['business_code']=code
    result['prepared_completion_matches']=value.get('prepared_completion_matches') is True
    result['truncated']=value.get('truncated') is not False
    for key in CASH_FIELDS:
        field=value.get('cash_fields',{}).get(key,{}) if isinstance(value.get('cash_fields'),dict) else {}
        if not isinstance(field,dict):continue
        amount=_money(field.get('value'))
        result['cash_fields'][key]=dict(present=field.get('present') is True,
            valid=field.get('valid') is True and amount is not None,value=amount)
    fields=value.get('header_fields')
    if isinstance(fields,list):
        for field in fields[:100]:
            if (isinstance(field,dict) and isinstance(field.get('name'),str)
                and re.fullmatch(r'[a-z][a-z0-9_]{0,47}',field['name']) and field.get('type') in kinds):
                result['header_fields'].append(dict(name=field['name'],type=field['type']))
    rows=value.get('rows')
    if isinstance(rows,list):
        for i,row in enumerate(rows[:20]):
            if not isinstance(row,dict):continue
            result['rows'].append(dict(index=i,cma_marker=row.get('cma_marker') is True,
                rp_marker=row.get('rp_marker') is True,evaluation_krw=_money(row.get('evaluation_krw')),
                quantity=_money(row.get('quantity')),integrated_quantity=_money(row.get('integrated_quantity'))))
    count=value.get('row_count')
    if type(count) is int and 0<=count<=100000:result['row_count']=count
    return result
