// Map actual journal inputs to a reviewed workflow snapshot. No cash formulas.
export const canTransferOut = account => !['ISA','IRP','PENSION','연금','퇴직'].some(label=>String(account.account_type || '').toUpperCase().includes(label));
export const executionContextKey = context => context ? [context.portfolio_id,context.cycle_id,context.revision,context.step.id].join('/') : '';
const same = (a,b) => String(a || '')===String(b || '');
export function matchingExecution(row,context) {
  if (!context || row.apply_cash===false) return;
  const matches=step=>step.status!=='EXCLUDED' && same(step.account_id,row.account_id) && step.currency===row.currency
    && step.kind===row.kind && (!['BUY','SELL'].includes(row.kind) || same(step.asset_id,row.asset_id))
    && (row.kind!=='TRANSFER' || same(step.destination_account_id,row.destination_account_id));
  const chosen=matches(context.step)?context.step:null;
  const candidates=(context.steps || [context.step]).filter(matches);
  const step=chosen || (candidates.length===1?candidates[0]:null);
  if (step) return {cycle_id:context.cycle_id,step_id:step.id,revision:context.revision};
}
export function executionRows(rows,context) {
  if (!context) return rows;
  // An input opened for one task must not quietly save a different trade.
  const selected = {...context, steps:[context.step]};
  return rows.map(row=>{
    const execution=matchingExecution(row,selected);
    if (!execution) throw new Error('선택한 작업의 계좌·종목·통화·방향과 다릅니다. 내용을 수정하거나 5번에서 별도 거래로 기록해주세요.');
    return {...row,execution};
  });
}
export function executionNotices(rows,context) {
  const facts=rows.map(row=>{
    const transfer=['DEPOSIT','WITHDRAW'].includes(row.kind) && row.external===false && !row.cross_portfolio;
    return {...row,kind:transfer?'TRANSFER':row.kind,currency:row.kind==='EXCHANGE_IN'?'USD':'KRW',
      account_id:transfer && row.kind==='DEPOSIT'?row.source_account_id:row.account_id,
      destination_account_id:transfer && row.kind==='DEPOSIT'?row.account_id:row.destination_account_id};
  });
  const linked=executionRows(facts,context);
  return rows.map((row,i)=>linked[i].execution?{...row,execution:linked[i].execution}:row);
}
export async function requireInvestmentProtocol(client,payload) {
  const linked=payload?.execution || (payload?.trades || payload?.rows || []).some(row=>row.execution);
  if (!linked) return;
  try {if ((await client.getInvestmentCapabilities()).investment_protocol===1) return;} catch { /* Keep exact pending request. */ }
  throw new Error('백엔드의 투자 실행 지원 버전이 필요합니다. Render 배포 후 같은 요청으로 확인해주세요. 장부 요청은 보내지 않았습니다.');
}

// Reference price only; the user still records the actual fill price.
export function executionReferencePrice(step,priceMap={},prices=[],usdKrw=0) {
  if(!step || !['BUY','SELL'].includes(step.kind))return 0;
  const positive=value=>Number.isFinite(Number(value)) && Number(value)>0;
  const krw=priceMap[String(step.asset_id)];
  if(step.currency==='USD'){
    const native=prices.find(p=>String(p.id)===String(step.asset_id))?.price_usd;
    if(positive(native))return Number(native);
    if(positive(krw) && positive(usdKrw))return Number((Number(krw)/Number(usdKrw)).toFixed(2));
  }else if(positive(krw))return Number(krw);
  return positive(step.estimated_price)?Number(step.estimated_price):0;
}

export function seedExecutionPrice(rows,step,referencePrice,{pending=false}={}) {
  if(pending || !step || !Number.isFinite(referencePrice) || referencePrice<=0)return rows;
  return rows.map(row=>!row.importSource && Number(row.price)===0
    && same(row.accountId,step.account_id) && same(row.assetId,step.asset_id)
    ? {...row,price:referencePrice}:row);
}
