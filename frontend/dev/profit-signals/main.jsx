import React,{useState} from 'react';
import {createRoot} from 'react-dom/client';
import '../../src/index.css';
import HoldingsPerformance from '../../src/components/Tab6Analysis/HoldingsPerformance';
import PerformanceChart from '../../src/components/Tab6Analysis/PerformanceChart';
const examples={mixed:[-1200000,-900000,-500000,200000,600000,400000,800000],loss:[-1200000,-1050000,-850000,-780000,-630000,-600000,-530000],profit:[4000000,4010000,4040000,4020000,4060000,4050000,4070000],zero:[0,0,0,0,0,0,0],missing:[null,null,null,null,null,null,null]};
export default function Review(){
 const [scenario,setScenario]=useState('mixed'),[mobile,setMobile]=useState(false),[scope,setScope]=useState('p'),[period,setPeriod]=useState(false);
 const values=examples[scenario],cost=100000000;
 const rows=values.map((profit,i)=>({date:`2026-10-${24+i}`,status:profit===null?'UNAVAILABLE':'COMPLETE',source:'RECORDED',profit_krw:profit,return_pct:profit===null?null:profit/cost*100,cost_krw:cost,value_krw:profit===null?null:cost+profit,components:{p:{profit_krw:profit,return_pct:profit===null?null:profit/cost*100,value_krw:profit===null?null:cost+profit},q:{profit_krw:profit===null?null:100000,return_pct:profit===null?null:2,value_krw:5100000}}}));
 const displayRows=scope==='all'?rows.map(r=>({...r,cost_krw:cost+5000000,profit_krw:r.profit_krw===null?null:r.profit_krw+100000,return_pct:r.profit_krw===null?null:(r.profit_krw+100000)/(cost+5000000)*100,value_krw:r.value_krw===null?null:r.value_krw+5100000})):rows;
 const current={...displayRows.at(-1)};
 const daily=rows.map(r=>({...r,kind:'일',label:r.date,profit:r.profit_krw,return_pct:r.return_pct,record_kind:'close',previous_close_date:`2026-10-${Number(r.date.slice(-2))-1}`,start:'2026-10-05',end:r.date}));
 return <main style={{maxWidth:mobile?390:940,margin:'20px auto',padding:12}}>
  <p style={{fontSize:'.8rem',color:'var(--text-secondary)'}}>로컬 합성 예시 · 운영 DB·증권사 연결 없음</p><h2>손익을 한눈에 구분하는 그래프</h2>
  <div style={{display:'flex',gap:8,flexWrap:'wrap',marginBottom:16}}>
   <label>예시 <select aria-label="예시 상황" className="input-select" value={scenario} onChange={e=>setScenario(e.target.value)}>{[['mixed','손실 → 이익'],['loss','전 구간 손실'],['profit','전 구간 이익 · 작은 변화'],['zero','손익분기'],['missing','기록 부족']].map(([v,l])=><option key={v} value={v}>{l}</option>)}</select></label>
   <button className="btn btn-secondary" onClick={()=>setMobile(!mobile)}>{mobile?'넓게 보기':'모바일 폭으로 보기'}</button>
   <button className="btn btn-secondary" onClick={()=>setPeriod(!period)}>{period?'보유자산 그래프 보기':'기간 성과 그래프 보기'}</button>
   {!period&&<label>화면 <select aria-label="검토 화면" className="input-select" value={scope} onChange={e=>setScope(e.target.value)}><option value="p">개별 포트폴리오</option><option value="all">전체 자산 · 구성별 비교</option><option value="crypto">가상자산</option></select></label>}
  </div>
  {period?<PerformanceChart key={scenario} dailyReports={daily} baselineDate="2026-10-05" reports={[]}/>:<HoldingsPerformance key={`${scope}-${scenario}`} scope={scope} initialData={{rows:displayRows}} current={current} components={scope==='all'?[{id:'p',name:'포트폴리오 A'},{id:'q',name:'포트폴리오 B'}]:[]}/>}
 </main>;
}
createRoot(document.getElementById('root')).render(<Review/>);
