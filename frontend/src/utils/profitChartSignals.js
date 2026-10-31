// Presentation only. Preserve original values, missing observations and axis bounds.
export const profitTone=value=>typeof value!=='number'||!Number.isFinite(value)?'unknown':value>0?'profit':value<0?'loss':'zero';
export const profitColor=value=>({profit:'var(--color-profit)',loss:'var(--color-loss)',zero:'var(--text-secondary)',unknown:'var(--text-secondary)'})[profitTone(value)];
export const profitLabel=value=>({profit:'이익',loss:'손실',zero:'손익분기',unknown:'확인 필요'})[profitTone(value)];
export function signedProfit(value,metric){
  if(!Number.isFinite(value))return '기록 부족';
  const absolute=Math.abs(value),sign=value<0?'−':value>0?'+':'';
  if(metric==='return_pct')return absolute>0&&absolute<.005?`${sign}0.01% 미만`:`${sign}${absolute.toFixed(2)}%`;
  return absolute>0&&absolute<.5?`${sign}1원 미만`:`${sign}${Math.round(absolute).toLocaleString('ko-KR')}원`;
}
export function splitProfitSegment(from,to){
  if(![from.x,from.value,to.x,to.value].every(Number.isFinite))return [];
  if(from.value*to.value<0){
    const fraction=Math.abs(from.value)/(Math.abs(from.value)+Math.abs(to.value));
    const crossing={x:from.x+(to.x-from.x)*fraction,value:0};
    return [{from,to:crossing,color:profitColor(from.value)},{from:crossing,to,color:profitColor(to.value)}];
  }
  return [{from,to,color:profitColor(from.value||to.value)}];
}
export function zeroReference(low,high,metric,values){
  if(metric==='value_krw'||!Number.isFinite(low)||!Number.isFinite(high)||high<=low||!values.some(Number.isFinite))return null;
  const label=metric==='return_pct'?'0%':'0원';
  if(low<=0&&high>=0)return {position:'inside',label:`손익분기점 ${label}`};
  return high<0?{position:'above',label:`↑ ${label} 기준선은 위 · 표시 구간 전체 손실`}
    :{position:'below',label:`↓ ${label} 기준선은 아래 · 표시 구간 전체 이익`};
}
