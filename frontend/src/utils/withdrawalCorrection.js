import {readNoticeDraft,writeNoticeDraft,validNoticeDate} from './nhNotices.js';

export function isHistoricalWithdrawal(row,context,pid){
  const baseline=context?.trackings?.[pid]?.baseline_date;
  return row.kind==='WITHDRAW' && row.external && baseline && validNoticeDate(row.eventDate) && row.eventDate<baseline;
}

export function withdrawalCorrectionDraft(row,context,accounts,pid){
  if(!isHistoricalWithdrawal(row,context,pid) || row.errors?.length || !Number.isFinite(row.krwAmount) || row.krwAmount<=0)return null;
  const account=accounts.find(a=>String(a.id)===row.accountId && (!a.portfolio_id || String(a.portfolio_id)===String(pid)));
  if(!account)return null;
  return {
    source:{portfolioId:pid,rowId:row.id,fingerprint:row.fingerprint,accountId:row.accountId,eventDate:row.eventDate,amount:row.krwAmount,reportedAvailableKrw:row.reportedAvailableKrw},
    proposal:{kind:'PAST_WITHDRAWAL',account_id:row.accountId,event_date:row.eventDate,currency:'KRW',amount:row.krwAmount,
      reason:`NH 출금 알림 누락 보정 (${row.eventDate}${row.occurredAt?' '+row.occurredAt.slice(11,16):''})`},
  };
}

export function matchesWithdrawalCorrection(source,proposal){
  return Boolean(source && proposal && proposal.kind==='PAST_WITHDRAWAL' && proposal.currency==='KRW' &&
    proposal.account_id===source.accountId && proposal.event_date===source.eventDate && Number(proposal.amount)===source.amount);
}

export function settleCorrectionRows(rows,result){
  if(!result?.source || (!result.cancelled && !matchesWithdrawalCorrection(result.source,result.proposal)))return rows;
  return rows.flatMap(row=>{
    const source=result.source;
    const same=(row.id===source.rowId || (source.fingerprint && row.fingerprint===source.fingerprint)) && row.kind==='WITHDRAW' &&
      row.accountId===source.accountId && row.eventDate===source.eventDate && row.krwAmount===source.amount;
    if(!same)return [row];
    return result.cancelled?[{...row,historicalCashChoice:undefined,applyCash:false}]:[];
  });
}

// Remove a confirmed source synchronously before clearing the idempotent pending
// correction request, so a reload cannot re-submit it as an ordinary withdrawal.
export function settleStoredCorrection(result,storage){
  const draft=readNoticeDraft(result.source.portfolioId,storage);
  if(!draft)return true;
  if(draft.pendingPayload)return false;
  return writeNoticeDraft(result.source.portfolioId,{...draft,rows:settleCorrectionRows(draft.rows,result)},storage);
}
