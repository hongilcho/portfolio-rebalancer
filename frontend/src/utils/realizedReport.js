const number = v => typeof v==='number' && Number.isFinite(v);
export function saleProfit(row) {
  if(number(row.net_profit_krw))return {amount:row.net_profit_krw,label:'확인된 순손익',kind:'confirmed'};
  if(number(row.estimated_net_profit_krw))return {amount:row.estimated_net_profit_krw,label:'예상 순손익',kind:'estimated'};
  return {amount:number(row.gross_profit_krw)?row.gross_profit_krw:null,label:'비용 전 손익',kind:'gross'};
}
export function knownTotal(rows,key) {
  if(!rows.length)return 0;
  const values=rows.map(r=>r[key]).filter(number);return values.length?values.reduce((a,b)=>a+b,0):null;
}
export function summarizeSales(rows) {
  const netRows=rows.map(r=>number(r.net_profit_krw)?r.net_profit_krw:r.estimated_net_profit_krw).filter(number);
  return {count:rows.length,gross:knownTotal(rows,'gross_profit_krw'),confirmed:knownTotal(rows,'net_profit_krw'),
    estimated:netRows.length===rows.length&&rows.length?netRows.reduce((a,b)=>a+b,0):null,
    pending:rows.filter(r=>r.status!=='CONFIRMED').length,basisMissing:rows.filter(r=>!number(r.gross_profit_krw)).length};
}
export function groupSales(rows,group='month') {
  const map=new Map();for(const row of rows){
    const key=['month','year'].includes(group)?row.trade_date.slice(0,group==='year'?4:7):String(group==='account'?row.account_id:row.asset_id);
    if(!map.has(key))map.set(key,{id:key,label:['month','year'].includes(group)?key:group==='account'?row.account_alias:row.asset_name,rows:[]});
    map.get(key).rows.push(row);
  }
  return [...map.values()].map(g=>({...g,...summarizeSales(g.rows)})).sort((a,b)=>['month','year'].includes(group)?b.id.localeCompare(a.id):(a.label||'').localeCompare(b.label||''));
}
export function saleDatePreset(kind,now=new Date()) {
  const today=new Date(now.getTime()+9*3600000).toISOString().slice(0,10);
  return kind==='month'?{start_date:today.slice(0,7)+'-01',end_date:today}:kind==='year'?{start_date:today.slice(0,4)+'-01-01',end_date:today}:{start_date:'',end_date:''};
}
