import React,{StrictMode,useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import '../../src/index.css';
import {api,ledgerReadStore} from '../../src/utils/api';
import RealizedGainsPanel from '../../src/components/Tab6Analysis/RealizedGainsPanel';
import HistoryTab from '../../src/components/Tab4History/HistoryTab';
const reads={usd:0,holdings:0,realized:0};let revision=0,fail=false;
for(const name of Object.keys(api))api[name]=async()=>{throw new Error('합성 검토에서는 저장·외부 연결을 실행하지 않습니다.');};
const wait=()=>new Promise(resolve=>setTimeout(resolve,1800));
api.getUsdLedgers=async()=>{reads.usd++;await wait();if(fail)throw Error('합성 조회 실패');return {ledgers:[{account_id:'a',usd_balance:1000+revision*10,average_rate:1338.33,cost_krw:(1000+revision*10)*1338.33}]};};
api.getAllHoldings=async()=>{reads.holdings++;await wait();if(fail)throw Error('합성 조회 실패');return {holdings:[{account_id:'a',asset_id:'vt',asset_name:'합성 VT',market:'US',quantity:5-revision,avg_price_usd:100}]};};
api.getRealizedGains=async()=>{reads.realized++;await wait();if(fail)throw Error('합성 조회 실패');return {summary:{gross_profit_krw:10000+revision*1000,confirmed_net_profit_krw:null,pending_count:1},sales:[{trade_id:'synthetic',asset_name:'합성 VT',account_alias:'검토 계좌',trade_date:'2026-10-30',quantity:1,gross_profit_krw:10000+revision*1000,status:'COSTS_PENDING',currency:'USD'}],periods:[],warnings:[]};};
export default function Review(){
 const [tick,setTick]=useState(0),[mounted,setMounted]=useState(true),[active,setActive]=useState(true);
 useEffect(()=>{const timer=setInterval(()=>setTick(n=>n+1),1000);return()=>clearInterval(timer);},[]);
 const accounts=[{id:'a',account_no:'QA-LOCAL',account_alias:'검토 계좌',account_type:'GENERAL',portfolio_id:'p',deposit_usd:1000,deposit_krw:100000}];
 const assets=[{id:'vt',ticker:'VT',name:'합성 VT',market:'US',portfolio_id:'p',allowed_accounts:['a']}];
 return <main style={{maxWidth:1000,margin:'24px auto',padding:14}}><h2>시세와 장부 조회 분리 검토</h2><p>합성 자료 전용 · 운영 DB·증권사 연결 없음 · 저장 버튼은 실제 요청을 보내지 않습니다.</p>
 <div style={{display:'flex',gap:8,flexWrap:'wrap'}}>
 <button className="btn btn-secondary" onClick={()=>setMounted(v=>!v)}>{mounted?'화면 닫기':'화면 다시 열기'}</button>
 <button className="btn btn-secondary" onClick={()=>setActive(v=>!v)}>{active?'입력 화면 비활성화':'입력 화면 활성화'}</button>
 <button className="btn btn-secondary" onClick={()=>{fail=false;revision=Math.min(3,revision+1);ledgerReadStore.invalidate();}}>매도·환전 반영 모의</button>
 <button className="btn btn-secondary" onClick={()=>{fail=true;ledgerReadStore.invalidate();}}>조회 실패 모의</button>
 <button className="btn btn-secondary" onClick={()=>{fail=false;ledgerReadStore.invalidate();}}>조회 복구</button></div>
 <p role="status">시세 갱신 {tick}회 · 달러 원가 {reads.usd}회 · 보유 수량 {reads.holdings}회 · 실현손익 {reads.realized}회</p>
 {mounted&&<><RealizedGainsPanel portfolioId="p" accounts={accounts} assets={assets}/><h3>8번·5번 공통 체결 입력 · 합성 예시</h3><div hidden={!active}><HistoryTab accounts={accounts} assets={assets} currentPortfolioId="p" pricesData={{prices:[{id:'vt',price_usd:100+tick*.01}]}} priceMap={{vt:133833+tick}} usdKrw={1338.33} embedded active={active} inputScope="ledger-read-review" executionContext={{cycle_id:'review-only',step:{id:'step',kind:'SELL',asset_id:'vt',account_id:'a',currency:'USD',quantity:1}}}/></div></>}
 </main>;
}
createRoot(document.getElementById('root')).render(<StrictMode><Review/></StrictMode>);
