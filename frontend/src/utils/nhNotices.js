import {parseNamuhMessages,resolveNamuhDraft,validateNamuhDraft} from './namuhMessage.js';

const normalized = text => String(text || '').normalize('NFKC').replace(/\r\n?/g,'\n').replace(/[\u200b-\u200d\ufeff]/g,'').trim();
export const validNoticeDate = day => /^\d{4}-\d{2}-\d{2}$/.test(day || '') && Number.isFinite(Date.parse(day+'T00:00:00Z'))
  && new Date(day+'T00:00:00Z').toISOString().slice(0,10) === day;
const amount = text => /^(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?$/.test(text || '') ? Number(text.replaceAll(',','')) : NaN;
const field = (block,label) => block.match(new RegExp('^\\s*'+label+'\\s*:\\s*(.+?)\\s*$','m'))?.[1] || '';
const dayOf = (year,month,day) => `${year}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`;

export function parseNhNotifications(text,anchor) {
  return normalized(text).split(/(?=\[NH투자증권\])/).map(s=>s.replace(/^\s*[-─]{3,}\s*$/gm,'').trim()).filter(Boolean).map(raw=>{
    const common={raw,eventDate:anchor,occurredAt:null,external:true,applyCash:true,duplicateConfirmed:false,accountId:'',assetId:'',accountMask:'',errors:[]};
    if (/^\[NH투자증권\]\s*입금안내/.test(raw)) {
      const stamp=raw.match(/\[(\d{1,2})\/(\d{1,2})\s+(\d{2}):(\d{2})\]/);
      const eventDate=stamp?dayOf(anchor.slice(0,4),stamp[1],stamp[2]):anchor;
      const krwAmount=amount(raw.match(/^\s*금액\s+([\d,.]+)\s*원\s*$/m)?.[1]);
      const accountMask=(raw.match(/^\s*계좌번호\s*:?[ \t]*([0-9*-]+)\s*$/m)?.[1] || '').replaceAll('-','');
      const errors=[];
      if (!Number.isFinite(krwAmount) || krwAmount<=0) errors.push('입금 원화 금액을 확인해주세요.');
      if (!stamp || !validNoticeDate(eventDate) || Number(stamp[3])>23 || Number(stamp[4])>59) errors.push('입금 날짜·시각을 읽지 못했습니다. 직접 입력으로 확인해주세요.');
      return {...common,kind:'DEPOSIT',krwAmount,accountMask,eventDate,messageMonthDay:eventDate.slice(5),
        occurredAt:stamp?`${eventDate}T${stamp[3]}:${stamp[4]}:00+09:00`:null,errors};
    }
    if (/^\[NH투자증권\]\s*환전내역 안내/.test(raw)) {
      const stamp=field(raw,'환전일자').match(/^(?:(\d{4})년\s*)?(\d{1,2})월\s*(\d{1,2})일$/);
      const eventDate=stamp?dayOf(stamp[1] || anchor.slice(0,4),stamp[2],stamp[3]):anchor;
      const usdAmount=amount(field(raw,'외화금액').match(/^USD\s+([\d,.]+)$/)?.[1]);
      const krwAmount=amount(field(raw,'원화금액').replace(/\s*원$/,''));
      const quotedRate=amount(field(raw,'환율'));
      const errors=[];
      if (field(raw,'환전구분')!=='외화매수' || field(raw,'통화명')!=='USD') errors.push('현재는 원화 → USD 외화매수 알림만 지원합니다.');
      if (!stamp || !validNoticeDate(eventDate)) errors.push('환전 날짜를 읽지 못했습니다.');
      if (![usdAmount,krwAmount,quotedRate].every(v=>Number.isFinite(v) && v>0)) errors.push('환전 달러 금액·원화 지출액·환율을 확인해주세요.');
      return {...common,kind:'EXCHANGE_IN',usdAmount,krwAmount,quotedRate,eventDate,messageMonthDay:eventDate.slice(5),errors};
    }
    const parsed=parseNamuhMessages(raw)[0];
    return {...common,...parsed,kind:'BUY',eventDate:parsed?.messageDate || anchor};
  });
}

export async function noticeFingerprint(raw) {
  const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(normalized(raw)));
  return [...new Uint8Array(bytes)].map(v=>v.toString(16).padStart(2,'0')).join('');
}

export function resolveNhNotice(parsed,accounts,assets,pid,previous=[]) {
  const resolved=resolveNamuhDraft({...parsed,ticker:parsed.ticker || ''},accounts,assets,pid);
  if (parsed.kind==='EXCHANGE_IN' && !resolved.accountId) {
    const prior=[...previous].reverse().find(r=>r.kind==='DEPOSIT' && r.eventDate===parsed.eventDate && r.accountId);
    if (prior) return {...resolved,accountId:prior.accountId,accountWarning:'앞선 입금 계좌를 추천했습니다. 환전 계좌가 맞는지 확인해주세요.'};
  }
  return resolved;
}

export function flowCandidates(row,context) {
  return (context?.flows || []).filter(f=>!f.voided && String(f.account_id)===row.accountId && f.currency==='KRW'
    && Number(f.amount_krw)===row.krwAmount);
}
export function chosenFlow(row,context) {
  if (!row.external) return null;
  if (row.flowId!==undefined) return row.flowId==='NEW'?null:row.flowId;
  const matches=flowCandidates(row,context);
  return matches.length===1?matches[0].id:matches.length?'':null;
}

export function validateNhNotice(row,context,accounts,assets,pid,pending,earlier) {
  const errors=[...(row.errors || [])];
  const scoped=accounts.filter(a=>!a.portfolio_id || String(a.portfolio_id)===String(pid));
  if (!scoped.some(a=>String(a.id)===row.accountId)) errors.push('계좌를 선택해주세요.');
  if (!validNoticeDate(row.eventDate)) errors.push('적용 날짜를 확인해주세요.');
  if (row.messageMonthDay && row.eventDate.slice(5)!==row.messageMonthDay) errors.push('알림의 월·일과 적용 날짜가 다릅니다.');
  if (!context) errors.push('기존 기록·잔고 조회를 기다려주세요.');
  let duplicate=false;
  if (row.kind==='BUY') {
    const check=validateNamuhDraft(row,row.eventDate,accounts,assets,pid,pending,context?.trades || []);
    errors.push(...check.errors);
    duplicate=check.manualDuplicate;
    if (earlier.some(r=>r.kind==='BUY' && r.accountId===row.accountId && r.eventDate===row.eventDate && r.brokerOrderNo===row.brokerOrderNo)) errors.push('목록에 같은 주문번호가 있습니다.');
  } else if (row.kind==='DEPOSIT') {
    if (!row.external && (!scoped.some(a=>String(a.id)===row.sourceAccountId) || row.sourceAccountId===row.accountId || !row.applyCash)) errors.push('내부 이체의 출금 계좌를 선택해주세요.');
    const matches=flowCandidates(row,context),flow=chosenFlow(row,context);
    if (flow==='') errors.push('연결할 기존 입금 기록을 선택해주세요.');
    if (flow && matches.find(f=>f.id===flow)?.cash_handled) errors.push('이 입금은 이미 예수금 반영 여부를 처리했습니다.');
    if (!flow && matches.length && row.external) duplicate=true;
  } else if (row.kind==='EXCHANGE_IN') {
    duplicate=(context?.exchanges || []).some(e=>String(e.account_id)===row.accountId && Number(e.usd_amount)===row.usdAmount && Number(e.krw_amount)===row.krwAmount);
  }
  duplicate=duplicate || (context?.notices || []).some(n=>String(n.account_id)===row.accountId && n.fingerprint===row.fingerprint)
    || earlier.some(r=>r.accountId===row.accountId && r.eventDate===row.eventDate && r.fingerprint===row.fingerprint);
  if (duplicate && !row.duplicateConfirmed) errors.push('동일한 내용이 있습니다. 별도 거래일 때만 중복 확인을 선택해주세요.');
  return {errors:[...new Set(errors)],duplicate};
}

export function noticeApiRow(row,context) {
  const occurrence=row.occurredAt ? row.eventDate+row.occurredAt.slice(10):null;
  return {kind:row.kind,account_id:row.accountId,event_date:row.eventDate,occurred_at:occurrence,
    source_account_id:row.sourceAccountId || null,external:row.external,apply_cash:row.applyCash,
    existing_flow_id:row.kind==='DEPOSIT'?chosenFlow(row,context):null,duplicate_confirmed:Boolean(row.duplicateConfirmed),
    fingerprint:row.fingerprint,asset_id:row.assetId || '',quantity:row.quantity || 0,price:row.price || 0,
    broker_order_no:row.brokerOrderNo || '',krw_amount:row.krwAmount || 0,usd_amount:row.usdAmount || 0,quoted_rate:row.quotedRate || 0};
}

export function previewNhNotices(rows,contexts,ledgers=[]) {
  const expected={},balances={},costs={},errors=[];
  for (const row of rows) {
    for (const aid of [row.accountId,...(!row.external && row.sourceAccountId?[row.sourceAccountId]:[])].filter(Boolean)) {
      if (balances[aid]) continue;
      const acc=contexts[row.eventDate]?.accounts.find(a=>String(a.id)===aid);
      if (!acc) {errors.push('계좌 잔고 조회를 기다려주세요.');continue;}
      expected[aid]={deposit_krw:Number(acc.deposit_krw),deposit_usd:Number(acc.deposit_usd)};
      balances[aid]={...expected[aid]};
      const state=ledgers.find(s=>String(s.account_id)===aid);
      if (state) costs[aid]={balance:Number(state.usd_balance),cost:Number(state.cost_krw),needsReconciliation:state.needs_reconciliation,lastDate:String(state.last_event_date)};
    }
    const cash=balances[row.accountId];
    if (!cash) continue;
    if (row.errors?.length) continue;
    if (row.kind==='BUY') cash.deposit_krw-=row.quantity*row.price;
    if (row.kind==='DEPOSIT' && row.applyCash) {
      cash.deposit_krw+=row.krwAmount;
      if (!row.external && balances[row.sourceAccountId]) balances[row.sourceAccountId].deposit_krw-=row.krwAmount;
    }
    if (row.kind==='EXCHANGE_IN') {
      const cost=costs[row.accountId];
      if (!cost) errors.push('환전 계좌의 달러 시작 기준환율을 먼저 등록해주세요.');
      else if (cost.needsReconciliation) errors.push('달러 잔고·원가 차이를 먼저 확인해주세요.');
      else if (row.eventDate < cost.lastDate) errors.push('기존 달러 기록보다 이전 날짜의 환전입니다. 날짜·등록 순서를 확인해주세요.');
      else {cost.balance+=row.usdAmount;cost.cost+=row.krwAmount;cost.lastDate=row.eventDate;}
      cash.deposit_krw-=row.krwAmount;cash.deposit_usd+=row.usdAmount;
    }
    if (Object.values(balances).some(b=>b.deposit_krw < -0.000001)) errors.push('처리 순서상 원화가 부족합니다. 입금 알림을 먼저 배치하거나 원화 잔고를 확인해주세요.');
  }
  return {expected,balances,costs,errors:[...new Set(errors)]};
}

const key=pid=>`nh-notice-draft/v1/${pid}`;
export function readNoticeDraft(pid,storage) {
  try {
    const data=JSON.parse((storage || globalThis.localStorage).getItem(key(pid)));
    if (data && Date.now()-data.savedAt < 30*86400000 && data.rows?.length<=50 && data.rows.every(r=>r && ['BUY','DEPOSIT','EXCHANGE_IN'].includes(r.kind) && typeof r.id==='string' && validNoticeDate(r.eventDate) && typeof r.accountId==='string' && Array.isArray(r.errors))) return data;
  } catch { /* optional local drafts */ }
  return null;
}
export function writeNoticeDraft(pid,data,storage) {
  try {storage=storage || globalThis.localStorage;if(data.rows.length)storage.setItem(key(pid),JSON.stringify({...data,savedAt:Date.now()}));else storage.removeItem(key(pid));return true;}
  catch{return false;}
}
