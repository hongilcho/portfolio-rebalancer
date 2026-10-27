export function holdingCurrent(kpi,overview=false){
  if(!kpi)return null;
  const cost=overview?kpi.total_buy:kpi.total_stock_buy;
  const profit=overview?kpi.total_profit:kpi.total_stock_profit;
  const value=overview?kpi.total_eval:kpi.total_portfolio_eval;
  const rate=overview?kpi.total_profit_pct:kpi.total_stock_return;
  if(![cost,profit,value].every(v=>typeof v==='number'&&Number.isFinite(v)))return null;
  return {cost_krw:cost,profit_krw:profit,value_krw:value,return_pct:cost>0&&Number.isFinite(rate)?rate:null,status:'COMPLETE'};
}

export function holdingSeries(rows,current,{range='90',period='day',now=new Date()}={}){
  // Preserve incomplete observations so neither the chart nor aggregation can
  // silently bridge a missing component/date with today's position.
  const day=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Seoul',year:'numeric',month:'2-digit',day:'2-digit'}).format(now);
  const threshold=new Date(`${day}T00:00:00+09:00`).getTime()-Number(range)*86400000;
  let result=rows.filter(r=>range==='all'||new Date(`${r.date}T00:00:00+09:00`).getTime()>=threshold)
    .map(r=>({...r,key:r.date,label:r.date})).sort((a,b)=>a.date.localeCompare(b.date));
  if(period!=='day'){
    const grouped=new Map();for(const r of result)grouped.set(r.date.slice(0,period==='month'?7:4),r);
    result=[...grouped.values()];
  }
  if(current)result.push({...current,date:day,key:'current',label:'현재',current:true});
  return result;
}

export function holdingValue(value,metric){
  if(typeof value!=='number'||!Number.isFinite(value))return '기록 부족';
  return metric==='return_pct'?`${Math.abs(value)<.005?'0.00':value.toFixed(2)}%`:
    `${Math.round(value).toLocaleString('ko-KR')}원`;
}

export function holdingDomain(rows,metric,breakdown=false){
  const values=rows.flatMap(r=>[r[metric],...(breakdown?Object.values(r.components||{}).map(c=>c[metric]):[])])
    .filter(v=>typeof v==='number'&&Number.isFinite(v));
  if(!values.length)return [-1,1];
  const low=Math.min(...values),high=Math.max(...values),pad=Math.max((high-low)*.15,Math.max(Math.abs(low),Math.abs(high))*.005,metric==='return_pct'?.02:1);
  return [low-pad,high+pad];
}

export function holdingSegments(rows,metric,key=null){
  const segments=[];
  for(let i=1;i<rows.length;i++){
    const a=key?rows[i-1].components?.[key]:rows[i-1],b=key?rows[i].components?.[key]:rows[i];
    if([a?.[metric],b?.[metric]].every(v=>typeof v==='number'&&Number.isFinite(v)))
      segments.push({from:i-1,to:i,live:!!rows[i].current});
  }return segments;
}
