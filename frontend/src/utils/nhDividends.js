// Dividend payment dates and reference dates are distinct from ex-dividend dates.
const money=text=>/^(?:\d+|\d{1,3}(?:,\d{3})*)$/.test(text||'')?Number(text.replaceAll(',','')):NaN;
const value=(raw,label)=>raw.match(new RegExp('^\\s*(?:\\d+[.)]\\s*)?'+label+'\\s*:\\s*(.+?)\\s*$','m'))?.[1]||'';
const day=text=>{const m=text.match(/^(\d{4})[.-](\d{1,2})[.-](\d{1,2})\s*$/);return m?`${m[1]}-${m[2].padStart(2,'0')}-${m[3].padStart(2,'0')}`:'';};
const valid=d=>/^\d{4}-\d{2}-\d{2}$/.test(d)&&Number.isFinite(Date.parse(d+'T00:00:00Z'))&&new Date(d+'T00:00:00Z').toISOString().slice(0,10)===d;
const amount=(raw,label)=>{const s=value(raw,label);return s?money(s.replace(/\s*원\s*$/,'')):null;};
export function parseNhDividend(raw){
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
const fundName=name=>String(name||'').normalize('NFKC').replace(/^(미래에셋|한국투자|삼성자산운용)\s*/,'').replace(/증권상장지수투자신탁.*$/,'').replace(/\([^)]*\)/g,'').replace(/[\s·_-]/g,'').toUpperCase();
export function resolveDividendAsset(row,assets,pid){
 const name=fundName(row.assetName),scoped=assets.filter(a=>(!a.portfolio_id||String(a.portfolio_id)===String(pid))&&a.market==='KR'&&!a.is_deposit&&a.ticker!=='M04020000');
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
