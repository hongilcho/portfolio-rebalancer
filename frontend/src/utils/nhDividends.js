// Dividend payment dates and reference dates are distinct from ex-dividend dates.
const money=text=>/^(?:\d+|\d{1,3}(?:,\d{3})*)$/.test(text||'')?Number(text.replaceAll(',','')):NaN;
const value=(raw,label)=>raw.match(new RegExp('^\\s*(?:\\d+[.)]\\s*)?'+label+'\\s*:\\s*(.+?)\\s*$','m'))?.[1]||'';
const day=text=>{const m=text.match(/^(\d{4})[.-](\d{1,2})[.-](\d{1,2})\s*$/);return m?`${m[1]}-${m[2].padStart(2,'0')}-${m[3].padStart(2,'0')}`:'';};
const valid=d=>/^\d{4}-\d{2}-\d{2}$/.test(d)&&Number.isFinite(Date.parse(d+'T00:00:00Z'))&&new Date(d+'T00:00:00Z').toISOString().slice(0,10)===d;
const amount=(raw,label)=>{const s=value(raw,label);return s?money(s.replace(/\s*원\s*$/,'')):null;};
export function parseNhDividend(raw,anchor){
 if(/^\[NH투자증권\]\s*해외증권\s*권리발생\s*안내/.test(raw)){
  const errors=[],asset=value(raw,'종목'),ticker=asset.match(/^\[([A-Z0-9.-]+)\]/)?.[1]||'';
  const usdAmount=amountForeign(raw,'외화실지급액'),grossAmount=amountForeign(raw,'외화배정금액'),taxAmount=amountForeign(raw,'외화세액'),feeAmount=amountForeign(raw,'수수료');
  const krwTax=amount(raw,'원화세액'),accountMask=raw.match(/^\s*([\d*-]+)\s+.+?님\s*금일/m)?.[1]?.replaceAll('-','')||'';
  if(value(raw,'권리유형')!=='배당'||value(raw,'통화코드')!=='USD'||amountForeign(raw,'주식배정수량')!==0)errors.push('USD 현금 배당 알림만 지원합니다. 주식배당·다른 권리는 직접 확인해주세요.');
  if(!ticker||![usdAmount,grossAmount,taxAmount,feeAmount].every(v=>Number.isFinite(v)&&v>=0)||usdAmount<=0||Math.abs(grossAmount-taxAmount-feeAmount-usdAmount)>1e-8)errors.push('외화 배정금액·세금·수수료·실지급액을 확인해주세요.');
  if(!Number.isSafeInteger(krwTax)||krwTax<0)errors.push('원화 세금을 확인해주세요.');
  return {kind:'DIVIDEND',dividendCurrency:'USD',assetName:asset.replace(/^\[[^\]]+\]\s*/,''),ticker,accountMask,eventDate:anchor,referenceDate:anchor,dividendPaymentDate:anchor,
    usdAmount,krwAmount:0,grossAmount,taxAmount,feeAmount,krwTax,taxCashApplied:false,external:false,errors};
 }

 if(!/^\[NH투자증권\]\s*(?:퇴직연금\s*)?분배금\s*입금\s*안내/.test(raw))return null;
 const assetName=value(raw,'종목명'),referenceDate=day(value(raw,'기준일')),eventDate=day(value(raw,'입금일'));
 const accountMask=(value(raw,'계좌번호').split(/\s/)[0]||raw.match(/^\s*([\d*-]+)\s+.+?님\s*계좌로/m)?.[1]||'').replaceAll('-','');
 const grossAmount=amount(raw,'세전금액'),taxAmount=amount(raw,'세금합계');
 const krwAmount=amount(raw,'세후금액')??amount(raw,'분배금');
 const errors=[];
 if(!assetName)errors.push('알림의 배당 종목명을 확인해주세요.');
 if(!valid(referenceDate)||!valid(eventDate)||referenceDate>eventDate)errors.push('배당 기준일과 입금일을 확인해주세요.');
 if(!Number.isSafeInteger(krwAmount)||krwAmount<=0)errors.push('실제 입금된 원화 배당금을 확인해주세요.');
 if(grossAmount!==null&&(!Number.isSafeInteger(grossAmount)||grossAmount<krwAmount))errors.push('세전금액을 확인해주세요.');
 if(taxAmount!==null&&(!Number.isSafeInteger(taxAmount)||taxAmount<0||(grossAmount!==null&&grossAmount-taxAmount!==krwAmount)))errors.push('세전·세후금액과 세금합계가 맞지 않습니다.');
 return {kind:'DIVIDEND',assetName,referenceDate,eventDate,dividendPaymentDate:eventDate,accountMask,krwAmount,grossAmount,taxAmount,external:false,errors};
}
const amountForeign=(raw,label)=>{const s=value(raw,label).replaceAll(',','').trim();return /^\d+(?:\.\d+)?$/.test(s)?Number(s):NaN;};
const fundName=name=>String(name||'').normalize('NFKC').replace(/^(미래에셋|한국투자|삼성자산운용)\s*/,'').replace(/증권상장지수투자신탁.*$/,'').replace(/\([^)]*\)/g,'').replace(/[\s·_-]/g,'').toUpperCase();
export function resolveDividendAsset(row,assets,pid){
 const name=fundName(row.assetName),scoped=assets.filter(a=>(!a.portfolio_id||String(a.portfolio_id)===String(pid))&&a.market===(row.dividendCurrency==='USD'?'US':'KR')&&!a.is_deposit&&a.ticker!=='M04020000');
 if(row.dividendCurrency==='USD'){const found=scoped.filter(a=>a.ticker?.trim().toUpperCase()===row.ticker);return found.length===1?String(found[0].id):'';}
 const exact=scoped.filter(a=>fundName(a.name)===name);
 const matches=exact.length?exact:scoped.filter(a=>{const n=fundName(a.name);return n.length>=6&&name.includes(n);});
 return matches.length===1?String(matches[0].id):'';
}
export function dividendCandidates(row,context){return (context?.dividend_events||[]).filter(d=>String(d.asset_id)===row.assetId&&d.ex_date<=row.referenceDate).sort((a,b)=>b.ex_date.localeCompare(a.ex_date));}
export function chosenDividendDate(row,context){
 if(row.dividendExDate!==undefined)return row.dividendExDate||null;
 const candidates=dividendCandidates(row,context).filter(d=>Date.parse(row.referenceDate)-Date.parse(d.ex_date)<=14*86400000);
 return candidates.length===1?candidates[0].ex_date:null;
}
export function sameDividend(a,b){return a.kind==='DIVIDEND'&&b.kind==='DIVIDEND'&&a.accountId===b.accountId&&a.assetId===b.assetId&&a.referenceDate===b.referenceDate;}
