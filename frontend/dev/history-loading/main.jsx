import React,{StrictMode,useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import '../../src/index.css';
import {api,holdingHistoryStore} from '../../src/utils/api';
import HoldingsPerformance from '../../src/components/Tab6Analysis/HoldingsPerformance';
let reads=0,revision=0,failNext=false;
api.getHoldingHistory=async(scope,includeCrypto)=>{
 reads++;
 await new Promise(resolve=>setTimeout(resolve,1500));
 if(failNext){failNext=false;throw new Error('합성 조회 실패');}
 const extra=scope==='all'&&includeCrypto?300000:0;
 return {rows:[-300000,-100000,200000,500000].map((v,i)=>({date:`2026-10-${27+i}`,status:'COMPLETE',profit_krw:v+revision*10000+extra,return_pct:(v+revision*10000+extra)/100000,cost_krw:10000000,value_krw:10000000+v+revision*10000+extra}))};
};
export default function Review(){
 const [quote,setQuote]=useState(0),[scope,setScope]=useState('all'),[includeCrypto,setIncludeCrypto]=useState(true),[visible,setVisible]=useState(true),[count,setCount]=useState(0);
 useEffect(()=>{const timer=setInterval(()=>{setQuote(v=>v+1);setCount(reads);},1000);return()=>clearInterval(timer);},[]);
 return <main style={{maxWidth:800,margin:'24px auto',padding:14}}><h2>그래프 갱신 검토</h2>
 <p>로컬 합성 데이터 전용 · 운영 DB·증권사 연결 없음 · 시세는 매초 변경되지만 과거 기록은 재사용합니다.</p>
 <div style={{display:'flex',gap:8,flexWrap:'wrap',marginBottom:16}}>
 <button className="btn btn-secondary" onClick={()=>setVisible(v=>!v)}>{visible?'다른 탭으로 이동':'그래프로 돌아오기'}</button>
 <button className="btn btn-secondary" onClick={()=>{revision++;holdingHistoryStore.invalidate();}}>장부 변경 모의 반영</button>
 <button className="btn btn-secondary" onClick={()=>{failNext=true;holdingHistoryStore.invalidate();}}>조회 실패 모의 실행</button>
 <button className="btn btn-secondary" onClick={()=>holdingHistoryStore.invalidate()}>기록 다시 확인</button>
 <select aria-label="포트폴리오" value={scope} onChange={e=>setScope(e.target.value)}><option value="all">전체 자산</option><option value="p">포트폴리오 A</option><option value="crypto">가상자산</option></select>
 <label><input type="checkbox" checked={includeCrypto} onChange={e=>setIncludeCrypto(e.target.checked)}/>가상자산 포함</label></div>
 <p role="status">현재 시세 갱신 {quote}회 · 과거 기록 요청 {count}회</p>
 {visible?<HoldingsPerformance scope={scope} includeCrypto={includeCrypto} current={{profit_krw:600000+quote*100,return_pct:6+quote*.001,cost_krw:10000000,value_krw:10600000+quote*100}}/>:<p>다른 탭을 보고 있습니다.</p>}
 </main>;
}
createRoot(document.getElementById('root')).render(<StrictMode><Review/></StrictMode>);
