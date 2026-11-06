import React,{useRef,useState} from 'react';
import {api} from '../../utils/api';
import {kstToday} from '../../utils/depositMaturities';
import {formatKRW} from '../../utils/formatters';
export default function ForeignDividendTax({item,portfolioId,disabled,onChanged,onBusyChange}){
 const [day,setDay]=useState(kstToday()),[confirmed,setConfirmed]=useState(false),[error,setError]=useState(''),[saving,setSaving]=useState(false);
 const pending=useRef(null);
 const detail=item.detail;
 if(detail.dividend_currency!=='USD'||detail.tax_receipt_id||!Number(detail.krw_tax))return null;
 if(detail.tax_paid)return <p>원화 세금 {formatKRW(Number(detail.krw_tax))} · 출금 확인 완료</p>;
 const save=async()=>{
  if(saving||!confirmed)return;setSaving(true);onBusyChange?.(true);setError('');
  try{
   if(!pending.current){
    const context=await api.getNhNoticeContext(portfolioId,day),account=context.accounts.find(a=>String(a.id)===String(item.account_id));
    if(!account)throw new Error('현재 계좌 잔고를 확인할 수 없습니다.');
    pending.current={request_id:crypto.randomUUID(),confirmed:true,expected_cash:{[item.account_id]:{deposit_krw:Number(account.deposit_krw),deposit_usd:Number(account.deposit_usd)}},rows:[{kind:'DIVIDEND',dividend_currency:'USD',account_id:item.account_id,asset_id:detail.asset_id,event_date:day,external:false,apply_cash:true,tax_cash_applied:true,tax_receipt_id:item.id.replace(/^NOTICE:/,'')}]};
   }
   await api.commitNhNotices(portfolioId,pending.current);pending.current=null;await onChanged();
  }catch(e){if(e.status&&e.status<500&&![401,403,429].includes(e.status))pending.current=null;setError(e.message);}
  finally{setSaving(false);onBusyChange?.(false);}
 };
 return <div className="history-help"><p>원화 세금 {formatKRW(Number(detail.krw_tax))} · 예수금 차감 대기. 배당 손익에서는 이미 제외되어 있습니다.</p><label>실제 출금일<input className="input-text" type="date" min={item.event_date} max={kstToday()} disabled={disabled||saving||Boolean(pending.current)} value={day} onChange={e=>setDay(e.target.value)}/></label><label><input type="checkbox" disabled={disabled||saving} checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>MTS에서 이 세금이 실제 출금된 것을 확인했습니다.</label><button className="btn btn-primary btn-sm" disabled={disabled||saving||!confirmed} onClick={save}>{saving?'반영 중…':'확인한 원화 세금 출금 반영'}</button>{error&&<p role="alert">{error}</p>}</div>;
}
