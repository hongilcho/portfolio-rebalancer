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
export function executionRows(rows,context,confirmed) {
  if (!context) return rows;
  if (!confirmed) throw new Error('이번 투자에 연결할 입력임을 먼저 확인해주세요.');
  const linked=rows.map(row=>{
    const execution=matchingExecution(row,context);
    return execution?{...row,execution}:row;
  });
  if (!linked.some(row=>row.execution)) throw new Error('현재 입력의 계좌·종목·통화·방향이 투자 작업과 다릅니다. 확인하거나 5번에서 연결 없이 기록해주세요.');
  return linked;
}
export function executionNotices(rows,context,confirmed) {
  const facts=rows.map(row=>{
    const transfer=['DEPOSIT','WITHDRAW'].includes(row.kind) && row.external===false && !row.cross_portfolio;
    return {...row,kind:transfer?'TRANSFER':row.kind,currency:row.kind==='EXCHANGE_IN'?'USD':'KRW',
      account_id:transfer && row.kind==='DEPOSIT'?row.source_account_id:row.account_id,
      destination_account_id:transfer && row.kind==='DEPOSIT'?row.account_id:row.destination_account_id};
  });
  const linked=executionRows(facts,context,confirmed);
  return rows.map((row,i)=>linked[i].execution?{...row,execution:linked[i].execution}:row);
}
export async function requireInvestmentProtocol(client,payload) {
  const linked=payload?.execution || (payload?.trades || payload?.rows || []).some(row=>row.execution);
  if (!linked) return;
  try {if ((await client.getInvestmentCapabilities()).investment_protocol===1) return;} catch { /* Keep exact pending request. */ }
  throw new Error('백엔드의 투자 실행 지원 버전이 필요합니다. Render 배포 후 같은 요청으로 확인해주세요. 장부 요청은 보내지 않았습니다.');
}
