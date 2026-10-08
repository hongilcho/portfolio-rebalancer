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
