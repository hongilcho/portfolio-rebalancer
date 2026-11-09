import {parseNamuhMessages,resolveNamuhDraft,validateNamuhDraft} from './namuhMessage.js';
import {estimateFee} from './tradingFees.js';
import {parseNhDividend,resolveDividendAsset,chosenDividendDate,sameDividend} from './nhDividends.js';

const normalized = text => String(text || '').normalize('NFKC').replace(/\r\n?/g,'\n').replace(/[\u200b-\u200d\ufeff]/g,'').trim();
export const validNoticeDate = day => /^\d{4}-\d{2}-\d{2}$/.test(day || '') && Number.isFinite(Date.parse(day+'T00:00:00Z'))
  && new Date(day+'T00:00:00Z').toISOString().slice(0,10) === day;
const amount = text => /^(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?$/.test(text || '') ? Number(text.replaceAll(',','')) : NaN;
const field = (block,label) => block.match(new RegExp('^\\s*'+label+'\\s*:\\s*(.+?)\\s*$','m'))?.[1] || '';
const dayOf = (year,month,day) => `${year}-${String(month).padStart(2,'0')}-${String(day).padStart(2,'0')}`;

function parseUsBuy(raw,anchor) {
  const errors=[];
  const ticker=field(raw,'종목명').match(/^\(([A-Z0-9.-]+)\s+US\)/i)?.[1]?.toUpperCase() || '';
  const assetName=field(raw,'종목명').replace(/^\([^)]*\)\s*/,'');
  const accountMask=(raw.match(/^.*?님[ \t]+([\d*-]+)[ \t]*$/m)?.[1] || '').replaceAll('-','');
  const stamp=field(raw,'주문일자').match(/^(?:(\d{4})년\s*)?(\d{1,2})월\s*(\d{1,2})일$/);
  const eventDate=stamp?dayOf(stamp[1] || anchor.slice(0,4),stamp[2],stamp[3]):anchor;
  const quantity=amount(field(raw,'체결수량').match(/^([\d,]+)\s*주$/)?.[1]);
  const ordered=amount(field(raw,'주문수량').match(/^([\d,]+)\s*주$/)?.[1]);
  const price=amount(field(raw,'체결가격'));
  if (field(raw,'매매구분')!=='매수' || field(raw,'거래국가')!=='미국' || field(raw,'거래통화')!=='USD')
    errors.push('해외 체결은 미국 상장 종목의 USD 매수 알림을 지원합니다.');
  if (!ticker) errors.push('종목명 앞의 미국 종목코드를 확인해주세요.');
  if (!stamp || !validNoticeDate(eventDate)) errors.push('알림의 주문일자를 읽지 못했습니다.');
  if (!Number.isSafeInteger(quantity) || quantity<=0 || quantity!==ordered)
    errors.push('주문수량과 체결수량이 같은 전량 체결 알림을 확인해주세요.');
  if (!Number.isFinite(price) || price<=0) errors.push('달러 체결가격을 확인해주세요.');
  return {kind:'BUY',tradeCurrency:'USD',ticker,assetName,accountMask,eventDate,
    messageMonthDay:eventDate.slice(5),messageDate:stamp?.[1]?eventDate:'',quantity,price,errors};
}

export const isTradeNotice=row=>row.kind==='BUY' || row.kind==='SELL';

export function parseNhNotifications(text,anchor) {
  return normalized(text).split(/(?=\[NH투자증권\])/).map(s=>s.replace(/^\s*[-─]{3,}\s*$/gm,'').trim()).filter(Boolean).map(raw=>{
    const common={raw,eventDate:anchor,occurredAt:null,external:true,applyCash:true,duplicateConfirmed:false,accountId:'',assetId:'',accountMask:'',errors:[]};
    const dividend=parseNhDividend(raw,anchor);
    if(dividend)return {...common,...dividend};
    if (/^\[NH투자증권\]\s*(입금|출금)안내/.test(raw)) {
      const kind=/^\[NH투자증권\]\s*출금안내/.test(raw)?'WITHDRAW':'DEPOSIT';
      const stamp=raw.match(/\[(\d{1,2})\/(\d{1,2})\s+(\d{2}):(\d{2})\]/);
      const eventDate=stamp?dayOf(anchor.slice(0,4),stamp[1],stamp[2]):anchor;
      const krwAmount=amount(raw.match(/^\s*금액\s+([\d,.]+)\s*원\s*$/m)?.[1]);
      const accountMask=(raw.match(/^\s*계좌번호\s*:?[ \t]*([0-9*-]+)\s*$/m)?.[1] || '').replaceAll('-','');
      const errors=[];
      if (!Number.isFinite(krwAmount) || krwAmount<=0) errors.push('입출금 원화 금액을 확인해주세요.');
      if (!stamp || !validNoticeDate(eventDate) || Number(stamp[3])>23 || Number(stamp[4])>59) errors.push('입출금 날짜·시각을 읽지 못했습니다. 직접 입력으로 확인해주세요.');
      return {...common,kind,krwAmount,accountMask,eventDate,messageMonthDay:eventDate.slice(5),
        reportedAvailableKrw:kind==='WITHDRAW'?amount(field(raw,'출금가능금액').replace(/\s*원$/,'')):null,
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
    if (/^\[NH투자증권\]\s*해외주식\s*체결집계\s*내역\s*안내/.test(raw))
      return {...common,...parseUsBuy(raw,anchor)};
    const parsed=parseNamuhMessages(raw)[0];
    return {...common,...parsed,kind:parsed?.tradeType || 'BUY',eventDate:parsed?.messageDate || anchor};
  });
}

export async function noticeFingerprint(raw) {
  const bytes=await crypto.subtle.digest('SHA-256',new TextEncoder().encode(normalized(raw)));
  return [...new Uint8Array(bytes)].map(v=>v.toString(16).padStart(2,'0')).join('');
}

export function resolveNhNotice(parsed,accounts,assets,pid,previous=[]) {
  const resolved=resolveNamuhDraft({...parsed,ticker:parsed.ticker || ''},accounts,assets,pid);
  if(parsed.kind==='DIVIDEND')return {...resolved,assetId:resolveDividendAsset(parsed,assets,pid)};
  if (parsed.kind==='EXCHANGE_IN' && !resolved.accountId) {
    const prior=[...previous].reverse().find(r=>r.kind==='DEPOSIT' && r.eventDate===parsed.eventDate && r.accountId);
    if (prior) return {...resolved,accountId:prior.accountId,accountWarning:'앞선 입금 계좌를 추천했습니다. 환전 계좌가 맞는지 확인해주세요.'};
  }
  return resolved;
}

export const isCashNotice=row=>['DEPOSIT','WITHDRAW'].includes(row.kind);
export const peerAccount=row=>row.kind==='DEPOSIT'?row.sourceAccountId:row.destinationAccountId;
export const cashSign=row=>row.kind==='WITHDRAW'?-1:1;
export function flowCandidates(row,context,counterparty=false) {
  const aid=counterparty?peerAccount(row):row.accountId;
  const signed=row.krwAmount*cashSign(row)*(counterparty?-1:1);
  return ((counterparty?context?.transfer_flows:context?.flows) || []).filter(f=>!f.voided && String(f.account_id)===aid && f.currency==='KRW'
    && Number(f.amount_krw)===signed && (!f.event_date || f.event_date===row.eventDate));
}
export function chosenFlow(row,context,counterparty=false) {
  if (!row.external && !row.crossPortfolio) return null;
  const explicit=counterparty?row.counterpartyFlowId:row.flowId;
  if (explicit!==undefined) return explicit==='NEW'?null:explicit;
  const matches=flowCandidates(row,context,counterparty);
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
  if (isTradeNotice(row)) {
    const check=validateNamuhDraft(row,row.eventDate,accounts,assets,pid,pending,context?.trades || []);
    errors.push(...check.errors);
    duplicate=check.manualDuplicate;
    const sameAccountDay=r=>r.accountId===row.accountId && r.eventDate===row.eventDate;
    if (row.brokerOrderNo && earlier.some(r=>sameAccountDay(r) && r.brokerOrderNo===row.brokerOrderNo)) errors.push('목록에 같은 주문번호가 있습니다.');
    if (row.tradeCurrency==='USD' && earlier.some(r=>sameAccountDay(r) && r.tradeCurrency==='USD' &&
      r.assetId===row.assetId && r.quantity===row.quantity && r.price===row.price)) errors.push('목록에 같은 미국 주식 체결이 있습니다.');
  } else if(row.kind==='DIVIDEND') {
    const asset=assets.find(a=>String(a.id)===row.assetId&&(!a.portfolio_id||String(a.portfolio_id)===String(pid)));
    if(!asset||asset.market!==(row.dividendCurrency==='USD'?'US':'KR')||asset.is_deposit||asset.ticker==='M04020000')errors.push('배당을 지급한 종목과 상장 시장을 확인해주세요.');
    if(row.dividendCurrency!=='USD' && (!validNoticeDate(row.referenceDate)||row.referenceDate>row.eventDate||row.dividendPaymentDate!==row.eventDate))errors.push('알림의 기준일·입금일을 확인해주세요.');
    if(row.dividendCurrency==='USD'){
      if(!validNoticeDate(chosenDividendDate(row,context))||chosenDividendDate(row,context)>row.eventDate)errors.push('확인한 배당락일을 입력해주세요.');
      if(!(Number(row.receiptRate??context?.dividend_rate)>0))errors.push('입금일 평가환율을 확인해주세요.');
      if(!(row.usdAmount>0))errors.push('실수령 달러를 확인해주세요.');
    } else if(!Number.isSafeInteger(row.krwAmount)||row.krwAmount<=0)errors.push('실수령 배당금을 확인해주세요.');
    if(row.dividendCurrency==='USD' && (earlier.some(r=>r.kind==='DIVIDEND'&&r.accountId===row.accountId&&r.assetId===row.assetId&&chosenDividendDate(r,context)===chosenDividendDate(row,context)) || (context?.dividend_receipts||[]).some(n=>String(n.account_id)===row.accountId&&n.payload.asset_id===row.assetId&&n.payload.dividend_ex_date===chosenDividendDate(row,context)&&!n.payload.tax_receipt_id)))errors.push('이 배당락일의 배당을 이미 반영했습니다.');
    if(earlier.some(r=>sameDividend(r,row))||(context?.notices||[]).some(n=>n.payload?.kind==='DIVIDEND'&&String(n.account_id)===row.accountId&&n.payload.asset_id===row.assetId&&n.payload.reference_date===row.referenceDate))errors.push('이 종목·기준일의 배당이 이미 목록이나 장부에 있습니다.');
  } else if (isCashNotice(row)) {
    const all=context?.transfer_accounts || accounts;
    const peer=all.find(a=>String(a.id)===peerAccount(row));
    if (!row.external && (!peer || peerAccount(row)===row.accountId || Boolean(row.crossPortfolio)!==Boolean(peer?.portfolio_id && String(peer.portfolio_id)!==String(pid)))) errors.push('이체 구분에 맞는 상대 계좌를 선택해주세요.');
    for (const counterparty of row.crossPortfolio?[false,true]:[false]) {
      const matches=flowCandidates(row,context,counterparty),flow=chosenFlow(row,context,counterparty);
      if (flow==='') errors.push('연결할 기존 입출금 기록을 선택해주세요.');
      if (flow && matches.find(f=>f.id===flow)?.cash_handled) errors.push('이 입출금은 이미 예수금 반영 여부를 처리했습니다.');
      if (!flow && matches.length && (row.external || row.crossPortfolio)) duplicate=true;
    }
    const touched=[row.accountId,...(!row.external?[peerAccount(row)]:[])];
    if (row.applyCash && touched.some(aid=>{
      const account=all.find(a=>String(a.id)===aid);
      const t=context?.trackings?.[account?.portfolio_id || pid];
      return t && row.eventDate<t.baseline_date;
    })) errors.push('성과 기준일 이전 거래는 잔고에 이미 반영됨 · 기록만 저장으로 등록해주세요.');
    if (row.crossPortfolio && (context?.notices || []).some(n=>n.payload?.transfer && n.payload.peer_account_id===peerAccount(row) && Number(n.payload.krw_amount)===row.krwAmount)) duplicate=true;
  } else if (row.kind==='EXCHANGE_IN') {
    duplicate=(context?.exchanges || []).some(e=>String(e.account_id)===row.accountId && Number(e.usd_amount)===row.usdAmount && Number(e.krw_amount)===row.krwAmount);
  }
  const repeated=row.fingerprint && ((context?.notices || []).some(n=>String(n.account_id)===row.accountId && n.fingerprint===row.fingerprint)
    || earlier.some(r=>r.accountId===row.accountId && r.eventDate===row.eventDate && r.fingerprint===row.fingerprint));
  if (repeated && row.tradeCurrency==='USD') errors.push('같은 미국 주식 알림을 이미 가져왔습니다.');
  else duplicate=duplicate || Boolean(repeated);
  if (duplicate && !row.duplicateConfirmed) errors.push('동일한 내용이 있습니다. 별도 거래일 때만 중복 확인을 선택해주세요.');
  return {errors:[...new Set(errors)],duplicate};
}

export function noticeApiRow(row,context) {
  const occurrence=row.occurredAt ? row.eventDate+row.occurredAt.slice(10):null;
  const foreign=row.kind==='DIVIDEND'&&row.dividendCurrency==='USD';
  return {...(foreign?{dividend_currency:'USD',fee_amount:row.feeAmount,krw_tax:row.krwTax,tax_cash_applied:Boolean(row.taxCashApplied),tax_already_reflected:Boolean(row.taxAlreadyReflected),receipt_rate:Number(row.receiptRate??context?.dividend_rate)}:{}),...(row.kind==='DIVIDEND'?{reference_date:foreign?chosenDividendDate(row,context):row.referenceDate,dividend_ex_date:chosenDividendDate(row,context),gross_amount:row.grossAmount??null,tax_amount:row.taxAmount??null}:{}),kind:row.kind,account_id:row.accountId,event_date:row.eventDate,occurred_at:occurrence,
    source_account_id:row.sourceAccountId || null,destination_account_id:row.destinationAccountId || null,cross_portfolio:Boolean(row.crossPortfolio),counterparty_flow_id:row.crossPortfolio?chosenFlow(row,context,true):null,external:row.external,apply_cash:row.applyCash,
    existing_flow_id:isCashNotice(row)?chosenFlow(row,context):null,duplicate_confirmed:Boolean(row.duplicateConfirmed),
    fingerprint:row.fingerprint,asset_id:row.assetId || '',quantity:row.quantity || 0,price:row.price || 0,
    reported_available_krw:Number.isFinite(row.reportedAvailableKrw)?row.reportedAvailableKrw:null,broker_order_no:row.brokerOrderNo || '',...(row.tradeCurrency==='USD'?{trade_currency:'USD'}:{}),krw_amount:row.krwAmount || 0,usd_amount:row.usdAmount || 0,quoted_rate:row.quotedRate || 0};
}

export function previewNhNotices(rows,contexts,ledgers=[],assets=[]) {
  const expected={},balances={},costs={},errors=[],fees=[];
  for (const row of rows) {
    for (const aid of [row.accountId,...(!row.external && peerAccount(row)?[peerAccount(row)]:[])].filter(Boolean)) {
      if (balances[aid]) continue;
      const ctx=contexts[row.eventDate];
      const acc=[...(ctx?.accounts || []),...(ctx?.transfer_accounts || [])].find(a=>String(a.id)===aid);
      if (!acc) {errors.push('계좌 잔고 조회를 기다려주세요.');continue;}
      expected[aid]={deposit_krw:Number(acc.deposit_krw),deposit_usd:Number(acc.deposit_usd)};
      balances[aid]={...expected[aid]};
      const state=ledgers.find(s=>String(s.account_id)===aid);
      if (state) costs[aid]={balance:Number(state.usd_balance),cost:Number(state.cost_krw),needsReconciliation:state.needs_reconciliation,lastDate:String(state.last_event_date)};
    }
    const cash=balances[row.accountId];
    if (!cash) continue;
    if (row.errors?.length) continue;
    if (isTradeNotice(row)) {
      const usd=row.tradeCurrency==='USD';
      const currency=usd?'deposit_usd':'deposit_krw';
      const amount=row.quantity*row.price;
      const account=contexts[row.eventDate]?.accounts?.find(a=>String(a.id)===row.accountId);
      const asset=assets.find(a=>String(a.id)===row.assetId)||{market:usd?'US':'KR',ticker:row.ticker};
      const fee=estimateFee(account,asset,row.eventDate,row.quantity,row.price);
      const state=costs[row.accountId];
      if(usd){
        if(!state)errors.push('달러 시작 기준환율을 먼저 등록해주세요.');
        else if(state.needsReconciliation || Math.abs(state.balance-cash.deposit_usd)>0.00001)errors.push('달러 잔고·원가 차이를 먼저 확인해주세요.');
        else if(row.eventDate<state.lastDate)errors.push('기존 달러 기록보다 이전 날짜의 매수입니다. 날짜·등록 순서를 확인해주세요.');
        else if(state.cost<=0 || state.balance<=0)errors.push('달러 취득원가와 예수금을 확인해주세요.');
        if(cash.deposit_usd+1e-8<amount)errors.push('매수에 필요한 달러 예수금이 부족합니다.');
      }
      cash[currency]+=(row.kind==='SELL'?1:-1)*amount;
      if(fee){
        const deferred=cash[currency]+(usd?1e-8:0)<fee.amount;
        if(!deferred)cash[currency]-=fee.amount;
        fees.push({id:row.id,...fee,deferred});
      }
      if(usd && state?.balance>0 && cash.deposit_usd>=-1e-8){
        state.cost*=Math.max(0,cash.deposit_usd)/state.balance;
        state.balance=Math.max(0,cash.deposit_usd);
        state.lastDate=row.eventDate;
      }
    }
    if(row.kind==='DIVIDEND'&&row.dividendCurrency==='USD'){
      if(row.applyCash){
        if(!costs[row.accountId] && cash.deposit_usd===0)costs[row.accountId]={balance:0,cost:0,lastDate:row.eventDate};
        const state=costs[row.accountId];
        if(!state)errors.push('기존 달러의 시작 기준환율을 먼저 등록해주세요.');
        else if(state.needsReconciliation)errors.push('달러 잔고·원가 차이를 먼저 확인해주세요.');
        else if(row.eventDate<state.lastDate)errors.push('기존 달러 기록 이후 날짜로 입력해주세요. 과거 누락은 장부 정정으로 확인해주세요.');
        else{state.balance+=row.usdAmount;state.cost+=row.usdAmount*Number(row.receiptRate??contexts[row.eventDate]?.dividend_rate);state.lastDate=row.eventDate;}
        cash.deposit_usd+=row.usdAmount;
      }
      if(row.taxCashApplied)cash.deposit_krw-=row.krwTax;
    } else if(row.kind==='DIVIDEND'&&row.applyCash)cash.deposit_krw+=row.krwAmount;
    if (isCashNotice(row) && row.applyCash) {
      cash.deposit_krw+=cashSign(row)*row.krwAmount;
      if (!row.external && balances[peerAccount(row)]) balances[peerAccount(row)].deposit_krw-=cashSign(row)*row.krwAmount;
    }
    if (row.kind==='EXCHANGE_IN') {
      if (!costs[row.accountId] && cash.deposit_usd===0) {
        costs[row.accountId]={balance:0,cost:0,needsReconciliation:false,lastDate:row.eventDate};
      }
      const cost=costs[row.accountId];
      if (!cost) errors.push('환전 계좌의 달러 시작 기준환율을 먼저 등록해주세요.');
      else if (cost.needsReconciliation) errors.push('달러 잔고·원가 차이를 먼저 확인해주세요.');
      else if (row.eventDate < cost.lastDate) errors.push('기존 달러 기록보다 이전 날짜의 환전입니다. 날짜·등록 순서를 확인해주세요.');
      else {cost.balance+=row.usdAmount;cost.cost+=row.krwAmount;cost.lastDate=row.eventDate;}
      cash.deposit_krw-=row.krwAmount;cash.deposit_usd+=row.usdAmount;
    }
    if (row.kind!=='DIVIDEND' && row.kind!=='SELL' && row.tradeCurrency!=='USD' && [row.accountId,...(!row.external?[peerAccount(row)]:[])].some(aid=>balances[aid]?.deposit_krw < -0.000001) && !(isCashNotice(row) && !row.applyCash)) errors.push('처리 순서상 원화가 부족합니다. 입금 알림을 먼저 배치하거나 원화 잔고를 확인해주세요.');
  }
  return {expected,balances,costs,fees,errors:[...new Set(errors)]};
}

const key=pid=>`nh-notice-draft/v1/${pid}`;
export function readNoticeDraft(pid,storage) {
  try {
    const data=JSON.parse((storage || globalThis.localStorage).getItem(key(pid)));
    if (data && Date.now()-data.savedAt < 30*86400000 && data.rows?.length<=50 && data.rows.every(r=>r && ['BUY','SELL','DEPOSIT','WITHDRAW','EXCHANGE_IN','DIVIDEND'].includes(r.kind) && typeof r.id==='string' && validNoticeDate(r.eventDate) && typeof r.accountId==='string' && Array.isArray(r.errors))) return data;
  } catch { /* optional local drafts */ }
  return null;
}
export function writeNoticeDraft(pid,data,storage) {
  try {storage=storage || globalThis.localStorage;if(data.rows.length)storage.setItem(key(pid),JSON.stringify({...data,savedAt:Date.now()}));else storage.removeItem(key(pid));return true;}
  catch{return false;}
}
