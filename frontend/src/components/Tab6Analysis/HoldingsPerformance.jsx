import React,{useEffect,useId,useState,useRef} from 'react';
import {api} from '../../utils/api';
import {holdingSeries,holdingValue,holdingDomain,holdingSegments} from '../../utils/holdingHistory';
import './HoldingsPerformance.css';

export default function HoldingsPerformance({scope,current,components=[],includeCrypto=false,revision,initialData}){
  const [data,setData]=useState(initialData||null),[error,setError]=useState('');
  const [metric,setMetric]=useState('profit_krw'),[range,setRange]=useState('90'),[period,setPeriod]=useState('day');
  const [selected,setSelected]=useState(null),[breakdown,setBreakdown]=useState(false);
  const heading=useId();
  const chartRef=useRef(null),[chartWidth,setChartWidth]=useState(600);
  useEffect(()=>{
    let active=true;
    if(initialData){setData(initialData);return ()=>{active=false;};}
    setData(null);setError('');setSelected(null);
    api.getHoldingHistory(scope,includeCrypto).then(r=>{if(active)setData(r);}).catch(()=>{if(active)setError('과거 기록을 불러오지 못했습니다. 현재 값은 아래에 표시합니다.');});
    return ()=>{active=false;};
  },[scope,includeCrypto,revision,initialData]);
  const live=current?{...current,components:Object.fromEntries(components.filter(c=>c.metrics).map(c=>[c.id,c.metrics]))}:null;
  const rows=holdingSeries(data?.rows||[],live,{range,period});
  const hasRows=rows.length>0;
  useEffect(()=>{
    if(!chartRef.current)return;
    const observer=new ResizeObserver(entries=>setChartWidth(Math.max(280,Math.round(entries[0].contentRect.width))));
    observer.observe(chartRef.current);return ()=>observer.disconnect();
  },[hasRows]);
  const choice=rows.find(r=>r.key===selected)||rows.at(-1);
  const index=rows.indexOf(choice),[low,high]=holdingDomain(rows,metric,breakdown);
  const left=68,right=chartWidth-14,top=22,bottom=210;
  const x=i=>rows.length>1?left+i/(rows.length-1)*(right-left):(left+right)/2;
  const y=v=>bottom-(v-low)/(high-low)*(bottom-top);
  const val=(r,key)=>key?r.components?.[key]?.[metric]:r[metric];
  const colors=['#a5b4fc','#34d399','#fbbf24','#f472b6'];
  function choosePointer(e){
    const bounds=e.currentTarget.getBoundingClientRect();
    const position=(e.clientX-bounds.left)/bounds.width*chartWidth;
    setSelected(rows[Math.max(0,Math.min(rows.length-1,Math.round((position-left)/(right-left)*(rows.length-1))))]?.key);
  }
  const curves=[{id:null,name:'전체',color:'var(--accent-primary)'},...(breakdown?components.map((c,i)=>({...c,color:colors[i%colors.length]})):[])];
  return <section className="section-card holdings-trend" aria-labelledby={heading}>
    <div className="holdings-trend-title"><h3 id={heading}>{scope==='all'?'전체 자산 손익 추이':'보유자산 손익 추이'}</h3><span className="badge">현황과 같은 기준</span></div>
    <div className="holdings-trend-options" role="group" aria-label="손익 추이 항목">
      {[['profit_krw','손익'],['return_pct','수익률'],['value_krw','평가액']].map(([key,label])=><button type="button" className={`btn btn-sm ${metric===key?'btn-primary':'btn-secondary'}`} aria-pressed={metric===key} key={key} onClick={()=>setMetric(key)}>{label}</button>)}
      <label>범위 <select value={range} onChange={e=>setRange(e.target.value)}><option value="30">최근 30일</option><option value="90">최근 90일</option><option value="all">전체</option></select></label>
      <label>간격 <select value={period} onChange={e=>setPeriod(e.target.value)}><option value="day">일별</option><option value="month">월말</option><option value="year">연말</option></select></label>
    </div>
    {components.length>1&&<label className="holdings-breakdown"><input type="checkbox" checked={breakdown} onChange={e=>setBreakdown(e.target.checked)}/>구성별 추이 함께 보기</label>}
    {error&&<p role="status">{error}</p>}
    {!data&&!initialData&&!error&&<p role="status">과거 기록 조회 중…</p>}
    {!rows.length?<p>아직 평가 기록이 없습니다. 종가 수집 후 추이가 표시됩니다.</p>:<>
      <svg ref={chartRef} viewBox={`0 0 ${chartWidth} 250`} className="holdings-trend-svg" role="group" aria-label="보유자산 손익 연결선 그래프" tabIndex={0}
        onPointerDown={choosePointer} onKeyDown={e=>{if(['ArrowLeft','ArrowRight','Home','End'].includes(e.key)){e.preventDefault();const next=e.key==='Home'?0:e.key==='End'?rows.length-1:Math.max(0,Math.min(rows.length-1,index+(e.key==='ArrowLeft'?-1:1)));setSelected(rows[next].key);}}}>
        {[0,.5,1].map(t=>{const v=low+(high-low)*t;return <g key={t}><line x1={left} x2={right} y1={y(v)} y2={y(v)} stroke="var(--border-color)"/><text x={left-8} y={y(v)+4} textAnchor="end" fill="var(--text-secondary)" fontSize="11">{metric==='return_pct'?v.toFixed(1)+'%':Math.abs(v)>=10000?(v/10000).toFixed(1)+'만':Math.round(v)}</text></g>;})}
        {curves.map(curve=><g key={curve.id||'total'}>{holdingSegments(rows,metric,curve.id).map(s=><line key={s.to} x1={x(s.from)} x2={x(s.to)} y1={y(val(rows[s.from],curve.id))} y2={y(val(rows[s.to],curve.id))} stroke={curve.color} strokeWidth={curve.id?1.6:2.8} strokeDasharray={s.live?'5 4':undefined}/>)}</g>)}
        {rows.map((r,i)=>{const v=r[metric];return typeof v==='number'&&<circle key={r.key} cx={x(i)} cy={y(v)} r={choice?.key===r.key?5:3} fill={r.current?'var(--bg-card)':'var(--accent-primary)'} stroke="var(--accent-primary)" strokeWidth="2"><title>{r.label} {holdingValue(v,metric)}</title></circle>;})}
        {rows.filter((r,i)=>i===0||i===rows.length-1||(i<rows.length-2&&i%Math.max(1,Math.ceil(rows.length/4))===0)).map(r=><text key={r.key} x={x(rows.indexOf(r))} y={235} textAnchor={r===rows[0]?'start':r===rows.at(-1)?'end':'middle'} fill="var(--text-secondary)" fontSize="11">{r.current?'현재':r.date.slice(5).replace('-','/')}</text>)}
      </svg>
      {breakdown&&<div className="holdings-trend-legend">{curves.map(c=><span key={c.id||'total'} style={{color:c.color}}>● {c.name}</span>)}</div>}
      {choice&&<div className="holdings-selected" aria-live="polite"><div><strong>{choice.current?'현재 · 조회 시점':choice.date}</strong><strong>{holdingValue(choice[metric],metric)}</strong></div>
        <small>{choice.current?'현황 카드와 같은 값 · 종가 확정 전':choice.source==='RECONSTRUCTED'?'저장된 당시 장부·시세와 확인 가능한 배당 이력으로 재계산':choice.status==='COMPLETE'?'종가 기준 기록':'일부 기록 부족 · 합산하지 않음'}</small>
        <div className="holdings-trend-controls"><button className="btn btn-secondary btn-sm" disabled={index<=0} onClick={()=>setSelected(rows[index-1].key)}>이전</button><button className="btn btn-secondary btn-sm" disabled={index>=rows.length-1} onClick={()=>setSelected(rows[index+1].key)}>다음</button></div>
        <details><summary>선택한 기록 상세</summary><p>매입원가 {holdingValue(choice.cost_krw,'cost_krw')} · 손익 {holdingValue(choice.profit_krw,'profit_krw')} · 수익률 {holdingValue(choice.return_pct,'return_pct')}</p>{Object.entries(choice.components||{}).map(([id,c])=><p key={id}>{components.find(p=>p.id===id)?.name||id}: {holdingValue(c.profit_krw,'profit_krw')} / {holdingValue(c.return_pct,'return_pct')}</p>)}{choice.warning&&<p>{choice.warning}</p>}</details>
      </div>}
      <details className="holdings-history-table"><summary>날짜별 표 보기</summary><div className="table-container"><table className="custom-table"><thead><tr><th>날짜</th><th>손익</th><th>수익률</th><th>평가액</th></tr></thead><tbody>{rows.map(r=><tr key={r.key}><td>{r.label}</td><td>{holdingValue(r.profit_krw,'profit_krw')}</td><td>{holdingValue(r.return_pct,'return_pct')}</td><td>{holdingValue(r.value_krw,'value_krw')}</td></tr>)}</tbody></table></div></details>
    </>}
    <details><summary>계산 기준·기록 범위</summary><p>손익은 현재 보유자산의 평가손익과 세후 배당 합계, 수익률은 그 손익을 보유자산 매입원가로 나눈 값입니다. 예수금은 평가액에만 포함됩니다. 실현 매도손익·현금 이자·미확정 비용을 여기에 임의로 합치지 않습니다.</p><p>매수·매도 시 보유 구성과 원가가 바뀔 수 있습니다. 기간 투자성과와 다른 지표이며, 월말·연말도 해당 시점의 보유자산 손익입니다. 기록되지 않은 과거 값을 현재 잔고로 채우지 않습니다.</p><p>국내 정규장 종가·확인 가능한 최근 미국 정규장 종가를 사용합니다. 가상자산은 같은 KRX 기록일 마감 수집 구간의 관측값이며 휴장일 별도 수집은 하지 않습니다. 일부 자산의 같은 날짜 기록이 없으면 전체 합계는 표시하지 않습니다. ‘현재’는 조회 시점 값으로, 확정 종가 기록과 구분합니다.</p></details>
  </section>;
}
