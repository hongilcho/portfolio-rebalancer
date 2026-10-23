import React,{useEffect,useState} from 'react';
import {api} from '../../utils/api';
import {formatKRW,formatUSD,getProfitColor} from '../../utils/formatters';

const amount=v=>v==null?'확인 필요':formatKRW(v);
const names={CONFIRMED:'비용 확인 완료',COSTS_PENDING:'비용 확인 전',BASIS_PENDING:'원가 확인 필요'};
const knownSum=(rows,key)=>{const values=rows.map(r=>r[key]).filter(v=>v!=null);return values.length||!rows.length?values.reduce((s,v)=>s+v,0):null;};
export default function RealizedGainsPanel({portfolioId,accounts=[],assets=[],revision=0,initialData=null,client=api}){
  const [data,setData]=useState(initialData),[error,setError]=useState(''),[loading,setLoading]=useState(false);
  const [filters,setFilters]=useState({start_date:'',end_date:'',account_id:'',asset_id:''});
  const [view,setView]=useState('sales'),[page,setPage]=useState(1),[refresh,setRefresh]=useState(0);
  useEffect(()=>{
    if(initialData)return;let cancelled=false;setLoading(true);setError('');setData(null);
    const params=Object.fromEntries(Object.entries(filters).filter(([,v])=>v));
    client.getRealizedGains(portfolioId,params).then(d=>{if(!cancelled)setData(d);}).catch(e=>{if(!cancelled)setError(e.message);}).finally(()=>{if(!cancelled)setLoading(false);});
    return()=>{cancelled=true;};
  },[portfolioId,filters,revision,refresh,initialData,client]);
  const change=(k,v)=>{setFilters(f=>({...f,[k]:v}));setPage(1);};
  const sales=data?.sales||[],periods=(data?.periods||[]).filter(p=>view!=='closed'||p.status==='CLOSED');
  const stats=view==='sales'?data?.summary:{gross_profit_krw:knownSum(periods,'gross_profit_krw'),confirmed_net_profit_krw:knownSum(periods,'confirmed_net_profit_krw'),pending_count:periods.reduce((n,p)=>n+p.pending_count,0)};
  const list=view==='sales'?sales:periods,pages=Math.max(1,Math.ceil(list.length/20)),current=Math.min(page,pages);
  return <section className="section-card realized-report" aria-label="실현손익과 매도 이력">
    <h3>실현손익 · 매도 완료 이력</h3>
    <p className="history-muted">매도로 확정된 가격 차이와 비용을 확인합니다. 예수금·총자산에 손익을 다시 더하지 않습니다.</p>
    <div className="history-filters">
      <label>매도 시작일<input className="input-text" type="date" disabled={view!=='sales'} value={filters.start_date} onChange={e=>change('start_date',e.target.value)}/></label>
      <label>매도 종료일<input className="input-text" type="date" disabled={view!=='sales'} value={filters.end_date} onChange={e=>change('end_date',e.target.value)}/></label>
      <label>계좌<select className="input-select" value={filters.account_id} onChange={e=>change('account_id',e.target.value)}><option value="">전체 계좌</option>{accounts.map(a=><option key={a.id} value={a.id}>{a.account_alias}</option>)}</select></label>
      <label>종목<select className="input-select" value={filters.asset_id} onChange={e=>change('asset_id',e.target.value)}><option value="">전체 종목</option>{assets.filter(a=>!a.is_deposit).map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
      <button className="btn btn-secondary btn-sm" type="button" onClick={()=>setRefresh(n=>n+1)}>다시 조회</button>
    </div>
    {error&&<p role="alert">{error}</p>}{loading&&<p role="status">손익 조회 중…</p>}
    {data&&<>
      <div style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(150px,1fr))',gap:12,margin:'16px 0'}}>
        <div><small>{view==='closed'?'전량 매도 완료분':'계산 가능한 매도손익'} · 비용 전</small><p style={{color:getProfitColor(stats.gross_profit_krw)}}>{amount(stats.gross_profit_krw)}</p></div>
        <div><small>비용 확인 완료분 · 순손익</small><p>{amount(stats.confirmed_net_profit_krw)}</p></div>
        <div><small>추가 확인</small><p>{stats.pending_count}건</p></div>
      </div>
      <div className="history-inline-choice">{[['sales','매도별 손익'],['closed','전량 매도 완료'],['periods','전체 보유기간']].map(([id,label])=><button key={id} className="btn btn-secondary btn-sm" type="button" aria-pressed={view===id} onClick={()=>{setView(id);setPage(1);}}>{label}</button>)}</div>
      {view!=='sales'&&<p className="history-muted">보유기간 이력은 전체 기간 기준입니다. 전량 매도 후 재매수하면 새로운 보유기간으로 표시합니다.</p>}
      {!list.length&&<p className="history-empty">조건에 해당하는 {view==='sales'?'매도':'보유기간'} 기록이 없습니다.</p>}
      <div className="history-record-list">{list.slice((current-1)*20,current*20).map(r=>view==='sales'?<article className="history-record" key={r.trade_id}>
        <div className="history-record-summary"><time>{r.trade_date}</time><div className="history-record-identity"><strong>{r.asset_name}</strong><span>{r.account_alias} · {r.quantity}주</span></div><strong style={{color:getProfitColor(r.net_profit_krw??r.estimated_net_profit_krw??r.gross_profit_krw)}}>{amount(r.net_profit_krw??r.estimated_net_profit_krw??r.gross_profit_krw)}<small style={{display:'block'}}>{r.estimated_net_profit_krw!=null?'수수료 반영 예상 · 세금 등 미확인':names[r.status]}</small></strong></div>
        <details className="history-record-detail"><summary>매도 원가·비용 상세</summary><div className="history-record-detail-body">
          <p>매도대금 {amount(r.proceeds_krw)} · 배분 취득원가 {amount(r.cost_basis_krw)}</p>
          <p>매도 비용 {amount(r.sale_cost_krw)} · 배분 매입 비용 {amount(r.allocated_buy_cost_krw)}</p>
          <p>비용 전 손익 {amount(r.gross_profit_krw)} · 순손익 {amount(r.net_profit_krw)}</p>
          {r.estimated_net_profit_krw!=null&&<p>수수료 반영 예상 순손익 {amount(r.estimated_net_profit_krw)} · 실제 결제 비용으로 확정된 값은 아닙니다.</p>}
          {r.currency==='USD'&&<><p>달러 가격 손익 {r.price_profit_usd==null?'확인 필요':formatUSD(r.price_profit_usd)} · 매도일 환율 {r.exchange_rate}</p><p>원화 환산 손익 중 환율 효과 {amount(r.fx_profit_krw)} · 매도 후 달러 현금의 환차손익은 별도입니다.</p></>}
          {r.status!=='CONFIRMED'&&<p>미확인 비용이나 원가를 0으로 확정하지 않았습니다. 표시 손익은 확인 가능한 범위입니다.</p>}
        </div></details>
      </article>:<article className="history-record" key={r.id}>
        <div className="history-record-summary"><div className="history-record-identity"><strong>{r.asset_name}</strong><span>{r.account_alias} · {r.status==='CLOSED'?'전량 매도 완료':r.status==='OPEN'?`${r.remaining_quantity}주 보유 중`:'기록 확인 필요'}</span><span className="realized-range"><span>{r.start_date||'시작일 미확인'}</span><span>~</span><span>{r.end_date||'현재'}</span></span></div><strong>{amount(r.gross_profit_krw)}<small style={{display:'block'}}>실현 매도손익 · 비용 전</small></strong></div>
        {r.calculation_start_date&&<small>실현손익 계산 기준 {r.calculation_start_date} · 실제 매수 시작일과 별도</small>}
        <details className="history-record-detail"><summary>배당·보유기간 상세</summary><div className="history-record-detail-body"><p>순손익 확인분 {amount(r.confirmed_net_profit_krw)} · 확인 필요 {r.pending_count}건</p><p>배당 {r.dividend_amount==null?'확인 필요':r.dividend_currency==='USD'?formatUSD(r.dividend_amount):formatKRW(r.dividend_amount)}{r.dividend_source==='CACHED_CALCULATION'?' · 저장된 배당 공시와 보유 이력의 계산값':''}</p>{r.dividend_scope==='SINCE_CONFIRMED_BASELINE'&&<p>이 보유기간의 배당은 계산 기준 확정 이후 확인 가능한 범위입니다. 기존 누적 배당은 변경하지 않습니다.</p>}{r.dividend_source==='MANUAL_UNALLOCATED'&&<p>기존 수동 배당금은 보존됩니다. 보유기간별 배분 근거가 없어 여기에는 나누어 표시하지 않습니다.</p>}<p>배당은 매도손익에 중복 합산하지 않습니다. 매도 후 늦게 지급되는 배당도 해당 배당락일의 보유 이력으로 확인합니다.</p>{r.basis_adjusted&&<p>장부 시작 기준·원가 정정이 포함된 보유기간입니다.</p>}{r.status==='CLOSED'&&<p>종목·거래 이력은 보존됩니다. 목표비중과 리밸런싱 포함 여부는 별도로 유지됩니다.</p>}</div></details>
      </article>)}</div>
      {pages>1&&<div className="history-pagination"><span>{current} / {pages}</span><button className="btn btn-secondary btn-sm" disabled={current===1} onClick={()=>setPage(current-1)}>이전</button><button className="btn btn-secondary btn-sm" disabled={current===pages} onClick={()=>setPage(current+1)}>다음</button></div>}
      {data.warnings.length>0&&<details className="history-help"><summary>원가·이력 확인 안내 {data.warnings.length}건</summary><p>계산 근거를 추가로 확인해야 하는 기록입니다. 현재 보유가 맞는 경우 기존 장부를 임의로 수정하지 말고 별도 점검해주세요.</p>{data.warnings.map((w,i)=><p key={i}>{accounts.find(a=>String(a.id)===w.account_id)?.account_alias||w.account_id} · {assets.find(a=>String(a.id)===w.asset_id)?.name||w.asset_id} · {w.reason}</p>)}</details>}
      {data.openings?.length>0&&<details className="history-help"><summary>과거 이력 보완 내역 {data.openings.length}종목</summary><p>원래 이력은 보존하고 확인한 장부 수량·원가를 승계했습니다. 과거 매입 비용은 확인된 것으로 간주하지 않습니다.</p>{data.openings.map(p=><p key={p.id}>{assets.find(a=>String(a.id)===p.asset_id)?.name||p.asset_id} · {p.date} · 당시 {p.quantity}주</p>)}</details>}
      <details className="history-help"><summary>계산 기준</summary><p>계좌·종목별 이동평균 원가를 사용합니다. 매입·매도 비용의 확인 여부를 구분하며, 세금 신고용 계산과 다를 수 있습니다. 기간 필터는 매도일을 기준으로 하며 매수 원가는 전체 이력에서 계산합니다. 보유자산 수익률·기간 성과 그래프의 분모는 바꾸지 않습니다.</p></details>
    </>}
  </section>;
}
