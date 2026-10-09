export function normalizeCorrection(form){
  const result={...form};
  for(const k of ['amount','balance','usd_average_rate','quantity','avg_price','avg_price_usd','buy_fx_rate'])result[k]=Number(form[k] || 0);
  result.first_buy_date=form.first_buy_date || null;
  result.manual_dividend_override=form.manual_dividend_override===''?null:Number(form.manual_dividend_override);
  return result;
}

// Pending writes retain their exact id and proof until the server confirms a result.
export function restoreCorrection(raw){
  try {
    const r=JSON.parse(raw);
    if(!r || typeof r.request_id!=='string' || r.request_id.length<8 || !/^[a-f0-9]{64}$/.test(r.token) || r.confirmed!==true || !r.decisions || typeof r.decisions!=='object' || Array.isArray(r.decisions))return null;
    if(Object.values(r.decisions).some(v=>!['ERROR','NORMAL','UNKNOWN'].includes(v)))return null;
    if(r.review_id)return typeof r.review_id==='string'?r:null;
    if(!r.proposal || !['PAST_WITHDRAWAL','CASH','HOLDING'].includes(r.proposal.kind) || typeof r.proposal.account_id!=='string' || !r.proposal.account_id)return null;
    return r;
  }catch{return null;}
}

// A shared decision never fabricates evidence for an uncorrectable snapshot.
export function groupHistoryDecisions(history,choice){
  return Object.fromEntries(history.map(h=>[h.key,choice==='ALL' && h.can_correct?'ERROR':'UNKNOWN']));
}
export function correctionInputHint(form){
  if(!form.account_id)return '정정할 계좌를 선택해주세요.';
  if(!form.event_date)return '실제 발생일을 입력해주세요.';
  if(!form.reason || form.reason.trim().length<3)return '정정 사유를 3자 이상 입력해주세요.';
  if(form.kind==='PAST_WITHDRAWAL' && !(Number(form.amount)>0))return '누락된 출금액을 입력해주세요.';
  if(form.kind==='CASH' && (form.balance==='' || !Number.isFinite(Number(form.balance)) || Number(form.balance)<0))return '정정할 실제 예수금을 입력해주세요.';
  if(form.kind==='HOLDING' && (!form.asset_id || form.quantity==='' || !Number.isFinite(Number(form.quantity)) || Number(form.quantity)<0))return '종목과 실제 보유 수량을 입력해주세요.';
  return '';
}
