"""Bounded NH CMA reads through the app's existing client. No orders or writes.

Contracts: NH official /openapi-docs/{common,krstock}/openapi.json.
Raw bank rows stay in process; public views exclude account/customer information.
HTTP success and pagination completeness do not certify accounting semantics.
"""
from datetime import date,datetime,timezone
from decimal import Decimal,InvalidOperation
import hashlib
import json
import re
import time
import requests

ORIGIN='https://api.nhplug.com:8443'
BALANCE='/krstock/inquiry/v1/balance'
TRANSACTIONS='/common/inquiry/v1/totalTransaction'
MOVEMENTS='/common/inquiry/v1/depositWithdrawal'
PATHS=frozenset((BALANCE,TRANSACTIONS,MOVEMENTS))
MAX_PAGES=3
MAX_ROWS=1000
MAX_BYTES=2*1024*1024
CONTINUE_CODES={'00165','00218'}
KNOWN_MESSAGES=frozenset(('조회가 완료되었습니다.','조회가 완료되었습니다','조회가 계속됩니다.',
    '조회할 자료가 없습니다.','조회할 데이터가 없습니다.','정상처리 되었습니다.'))


class CMAReadError(ValueError):pass


def _number(value):
    if value is None or isinstance(value,bool):return None
    try:
        n=Decimal(str(value))
        return str(n) if n.is_finite() and abs(n)<=Decimal('1e15') else None
    except (ValueError,InvalidOperation):return None


def status(data):
    if not isinstance(data,dict):return None,None
    msg=data.get('message') if isinstance(data.get('message'),dict) else {}
    return data.get('rsp_cd',msg.get('code')),data.get('rsp_msg',msg.get('msg'))


def _public_status(data):
    code,message=status(data)
    return dict(code=code if isinstance(code,str) and re.fullmatch(r'[A-Za-z0-9_]{1,20}',code) else None,
        recognized_message=message if isinstance(message,str) and message in KNOWN_MESSAGES else None,
        message_sha256=hashlib.sha256(message.encode()).hexdigest() if isinstance(message,str) else None)


def _next(data,headers):
    headers={str(k).lower():str(v).strip() for k,v in headers.items()}
    cursor=headers.get('cts','');flag=headers.get('cts_flag','').upper()
    if flag not in ('','Y','N'):raise CMAReadError('PAGINATION_FLAG_UNVERIFIED')
    if len(cursor)>4096 or any(ord(c)<32 or ord(c)>126 for c in cursor):raise CMAReadError('PAGINATION_KEY_UNVERIFIED')
    code,_=status(data)
    continuation=flag=='Y' or (flag!='N' and code in CONTINUE_CODES)
    if continuation and not cursor:raise CMAReadError('PAGINATION_KEY_MISSING')
    # A nonempty key without an explicit end or documented continuation is
    # ambiguous. Do not silently call a partial history complete.
    if cursor and not flag and code not in CONTINUE_CODES:raise CMAReadError('PAGINATION_END_UNVERIFIED')
    return (cursor,flag) if continuation else (None,None)


def snapshot(client,account_no,start_date,end_date,*,post=None,clock=None):
    """Read complete bounded histories first, balance last, no retries.

    Resolves the already-running client's token/cache and common throttle.
    Never constructs an NH client, extracts its token, or takes order paths.
    """
    start,end=date.fromisoformat(start_date),date.fromisoformat(end_date)
    if not 0<=(end-start).days<=31:raise CMAReadError('DATE_RANGE_UNVERIFIED')
    number=str(account_no).replace('-','')
    if not re.fullmatch(r'[0-9]{11}',number):raise CMAReadError('ACCOUNT_UNVERIFIED')
    if client.base_url!=ORIGIN:raise CMAReadError('NH_ORIGIN_UNVERIFIED')
    token=client.get_access_token()
    if not token:raise CMAReadError('EXISTING_AUTH_UNAVAILABLE')
    post=post or requests.post
    begun=time.monotonic();calls=0
    common=dict(act_no=number,iqr_tp_cd='1',iqr_sta_dt=start.strftime('%Y%m%d'),iqr_end_dt=end.strftime('%Y%m%d'))
    inputs={TRANSACTIONS:dict(common,iqr_rge_cd='2',iem_llf_cd='00',act_trd_dtl_cd='00'),
        MOVEMENTS:dict(common,act_trd_dtl_cd='01'),
        BALANCE:dict(act_no=number,bnc_bse_cd='1',ltg_aot_dit_cd='9',aet_bse='2',qut_dit_cd='UNT')}
    result=dict(start_date=start_date,end_date=end_date,complete=False,queries={},nh_calls=0)
    try:
        for path in (TRANSACTIONS,MOVEMENTS,BALANCE):
            rows=[];seen=set();cursor=flag=None;pages=[]
            for _ in range(MAX_PAGES):
                if time.monotonic()-begun>45:raise CMAReadError('READ_DEADLINE')
                headers={'Content-Type':'application/json;charset=utf-8','Authorization':'Bearer '+token,
                    'x-client-id':client.app_key,'x-client-secret':client.app_secret}
                if cursor:headers['cts']=cursor
                if flag:headers['cts_flag']=flag
                client._throttle();calls+=1
                response=post(ORIGIN+path,headers=headers,json={'Input_0':inputs[path]},
                    timeout=(5,8),verify=True,allow_redirects=False)
                if response.status_code!=200:raise CMAReadError('NH_HTTP_'+str(response.status_code))
                if len(response.content)>MAX_BYTES:raise CMAReadError('RESPONSE_TOO_LARGE')
                data=response.json()
                if not isinstance(data,dict):raise CMAReadError('RESPONSE_SHAPE_UNVERIFIED')
                pages.append(dict(data=data,status=_public_status(data)))
                block=data.get('Output_0')
                if path!=BALANCE:
                    if not isinstance(block,list) or any(not isinstance(row,dict) for row in block):
                        raise CMAReadError('HISTORY_BLOCK_UNVERIFIED')
                    rows.extend(block)
                    if len(rows)>MAX_ROWS:raise CMAReadError('HISTORY_TOO_LARGE')
                cursor,flag=_next(data,response.headers)
                if not cursor:break
                if path==BALANCE:raise CMAReadError('BALANCE_PARTIAL')
                if cursor in seen:raise CMAReadError('PAGINATION_REPEATED')
                seen.add(cursor)
            else:raise CMAReadError('PAGINATION_LIMIT')
            result['queries'][path]=dict(pages=pages,rows=rows,complete=True)
        result.update(complete=True,observed_at=(clock or (lambda:datetime.now(timezone.utc)))().isoformat())
        return result
    except CMAReadError:raise
    except Exception:raise CMAReadError('NH_READ_UNAVAILABLE') from None
    finally:
        result['nh_calls']=calls;token=None


def public_snapshot(value):
    """Only contract-defined amounts/dates/transaction descriptions leave process."""
    from logic.cma_diagnostics import balance_diagnostics,public_diagnostics
    result=dict(complete=value.get('complete') is True,observed_at=value.get('observed_at'),
        start_date=value.get('start_date'),end_date=value.get('end_date'),nh_calls=value.get('nh_calls'),queries={})
    for path in PATHS:
        query=value.get('queries',{}).get(path,{})
        out=dict(complete=query.get('complete') is True,pages=[p['status'] for p in query.get('pages',[])],rows=[])
        if path==BALANCE:
            pages=query.get('pages',[])
            if pages:out['balance']=public_diagnostics(balance_diagnostics(pages[-1]['data'],datetime.fromisoformat(value['observed_at'])))
        else:
            for row in query.get('rows',[])[:MAX_ROWS]:
                safe={key:_number(row.get(key)) for key in ('trd_amt','trd_af_dca','int_amt','tax_sum','trd_orn_fee','rvb_odu_fee','trd_qty','trd_uit_pr','trd_af_bnc_qty') if key in row}
                for key in ('trd_dt','ral_trd_dt','rgs_dt'):
                    safe[key]=row[key] if isinstance(row.get(key),str) and re.fullmatch('[0-9]{8}',row[key]) else None
                for key in ('sps_cd_krl_anm','act_trd_tp_nm'):
                    text=row.get(key)
                    safe[key]=text if isinstance(text,str) and re.fullmatch(r'[가-힣A-Za-z /()._-]{1,50}',text) else None
                safe['currency']=row.get('cur_cd') if row.get('cur_cd') in ('KRW','USD') else None
                code=row.get('cur_cd')
                safe['currency_code']=code.strip() if isinstance(code,str) and re.fullmatch(r'[A-Za-z0-9 ]{0,5}',code) else None
                safe['currency_present']='cur_cd' in row
                safe['cma_code_marker']=isinstance(row.get('iem_cd'),str) and row['iem_cd'].startswith('NHKRCMA')
                safe['cma_marker']=str(row.get('iem_cd','')).startswith('NHKRCMA') or 'CMA' in str(row.get('iem_nm',''))
                instrument=row.get('iem_cd')
                safe['instrument_hash']=hashlib.sha256(instrument.encode()).hexdigest() if isinstance(instrument,str) and instrument else None
                out['rows'].append(safe)
        result['queries'][path]=out
    return result
