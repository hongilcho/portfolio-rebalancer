// Integer decimal arithmetic keeps the preview aligned with the backend.
export const feeLabels={KR:'한국상장 상품',US:'미국상장 상품',GOLD:'금현물'};
function fraction(value){
  const s=String(value);if(!/^\d+(?:\.\d+)?$/.test(s))throw Error('수수료 계산 값을 확인해주세요.');
  const [a,b='']=s.split('.');return [BigInt(a+b),10n**BigInt(b.length)];
}
export function feeCategory(asset){return asset?.is_deposit?null:asset?.ticker==='M04020000'?'GOLD':asset?.market==='US'?'US':'KR';}
export function estimateFee(account,asset,day,quantity,price){
  try{
    const category=feeCategory(asset),schedule=typeof account?.fee_schedule==='string'?JSON.parse(account.fee_schedule):account?.fee_schedule;
    const policy=[...(schedule?.[category]||[])].filter(e=>e.from<=day).sort((a,b)=>a.from.localeCompare(b.from)).at(-1);
    if(!policy || Number(quantity)<=0 || Number(price)<=0)return null;
    const [q,qd]=fraction(quantity),[p,pd]=fraction(price),[r,rd]=fraction(policy.rate_pct);
    const scale=category==='US'?100n:1n,vat=category==='GOLD'&&!policy.vat_included;
    const minor=q*p*r*scale*(vat?11n:1n)/(qd*pd*rd*100n*(vat?10n:1n));
    return {amount:Number(minor)/Number(scale),currency:category==='US'?'USD':'KRW',policy,category};
  }catch{return null;}
}
export function setFeePolicy(value,category,entry){
  const schedule=typeof value==='string'?JSON.parse(value):value||{};
  const entries=(schedule[category]||[]).filter(e=>e.from!==entry.from);
  entries.push({...entry,rate_pct:entry.rate_pct===''?null:entry.rate_pct});
  return {...schedule,[category]:entries.sort((a,b)=>a.from.localeCompare(b.from))};
}

export async function requireFeeProtocol(api,accounts=[]){
  const configured=accounts.some(a=>{
    const value=typeof a?.fee_schedule==='string'?JSON.parse(a.fee_schedule):a?.fee_schedule;
    return value&&Object.values(value).some(entries=>entries.length>0);
  });
  if(configured && (await api.getBookkeepingCapabilities()).account_fees_protocol!==1)
    throw Error('백엔드가 계좌별 자동 수수료를 지원하지 않습니다. 백엔드 버전을 맞춘 뒤 다시 저장해주세요.');
}
