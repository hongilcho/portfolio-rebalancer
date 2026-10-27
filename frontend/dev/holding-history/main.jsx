import React,{useState} from 'react';
import {createRoot} from 'react-dom/client';
import '../../src/index.css';
import HoldingsPerformance from '../../src/components/Tab6Analysis/HoldingsPerformance';
import PerformanceChart from '../../src/components/Tab6Analysis/PerformanceChart';
import fixture from './synthetic.json';
import {holdingValue} from '../../src/utils/holdingHistory';
export default function Review(){
  const [scope,setScope]=useState('all'),[include,setInclude]=useState(true),[mobile,setMobile]=useState(false);
  const report=fixture[scope==='all'?(include?'all':'without_crypto'):scope];
  const current=fixture.current[scope==='all'?(include?'all':'without_crypto'):scope];
  const components=fixture.components.filter(c=>include||c.id!=='crypto').map(c=>({...c,metrics:fixture.current[c.id]}));
  return <main style={{maxWidth:mobile?390:1000,margin:'24px auto',padding:12}}>
    <p style={{color:'var(--text-secondary)',fontSize:'.85rem'}}>로컬 합성 예시 · 실제 장부·운영 DB·증권사 연결 없음</p>
    <h2>자산 현황과 연결되는 손익 추이</h2>
    <div style={{display:'flex',gap:8,flexWrap:'wrap',marginBottom:16}}>
      {[['all','전체 자산 종합 요약'],['p','장기 포트폴리오'],['q','일반투자']].map(([id,label])=><button key={id} className={`btn ${scope===id?'btn-primary':'btn-secondary'}`} onClick={()=>setScope(id)}>{label}</button>)}
      <button className="btn btn-secondary" onClick={()=>setMobile(!mobile)}>{mobile?'넓게 보기':'모바일 폭으로 보기'}</button>
      {scope==='all'&&<label style={{padding:8}}><input type="checkbox" checked={include} onChange={e=>setInclude(e.target.checked)}/>가상자산 포함</label>}
    </div>
    <section className="section-card" style={{display:'grid',gridTemplateColumns:'repeat(auto-fit,minmax(140px,1fr))',gap:16}}>
      {[['profit_krw','배당 포함 보유자산 손익'],['return_pct','보유자산 수익률'],['value_krw','총평가액 · 예수금 포함']].map(([key,label])=><div key={key}><small>{label}</small><p style={{fontWeight:800,fontSize:'1.25rem',marginTop:8}}>{holdingValue(current[key],key)}</p></div>)}
    </section>
    <HoldingsPerformance key={`${scope}-${include}`} scope={scope} current={current} initialData={report} components={scope==='all'?components:[]} includeCrypto={include}/>
    <details className="section-card"><summary>기준일 이후 운용 성과 · 기존 그래프 유지</summary><PerformanceChart baselineDate="2026-10-05" dailyReports={fixture.period} reports={[]}/></details>
  </main>;
}
createRoot(document.getElementById('root')).render(<Review/>);
