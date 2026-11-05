import React,{useState} from 'react';
import {createRoot} from 'react-dom/client';
import '../../src/index.css';
import {api} from '../../src/utils/api';
import CmaIncomePanel from '../../src/components/Tab4History/CmaIncomePanel';
import CashSettlementPanel from '../../src/components/Tab4History/CashSettlementPanel';
const pid='synthetic-cma-review',aid='qa-cma';
const scenarios={gap:'잔고 차이 · 이자 미확인',interest:'지급 이자 확인 완료',zero:'전액 이체 후 0원 조회',matched:'잔고 일치',waiting:'상품 잔고 확인 중'};
let scenario='gap',cash=3000086,interestTotal=1000,journal=[],saved=new Map();
const account=()=>({id:aid,account_alias:'예시 CMA',account_type:'CMA',deposit_krw:cash,deposit_usd:0});
for(const k of Object.keys(api))api[k]=async()=>{throw Error('이 화면은 운영 서버·증권사에 연결하지 않습니다.');};
api.getCmaIncome=async()=>({enabled:true,writes_enabled:true,automatic_ready:true,accounts:[{...account(),enabled:false}],income:[],checks:[],openings:[],interest_total_krw:interestTotal});
api.observeCma=async()=>({id:'qa-observation',observed_at:new Date().toISOString(),state:scenario==='zero'?'ZERO_UNVERIFIED':scenario==='waiting'?'AWAITING_CASH_RETURN':'CASH_RETURNED',cash_krw:scenario==='zero'||scenario==='waiting'?'0':String(cash+(scenario==='gap'?2412:scenario==='interest'?188:0)),sweep_krw:scenario==='waiting'?String(cash):'0',total_krw:scenario==='zero'?'0':String(cash+(scenario==='gap'?2412:scenario==='interest'?188:0)),withdrawable_krw:'0',reconciliation:{status:scenario==='interest'?'MATCHED':'STATEMENT_REQUIRED'}});
api.previewCmaIncome=async()=>({observation_id:'qa-observation',book_token:'a'.repeat(64),book_krw:String(cash),broker_krw:String(cash+(scenario==='gap'?2412:scenario==='interest'?188:0)),interest_krw:scenario==='interest'?'188':scenario==='gap'?'2412':'0',can_apply:scenario==='interest',status:scenario==='interest'?'REVIEW_INTEREST':'STATEMENT_REQUIRED'});
api.applyCmaIncome=async(_,req)=>{if(saved.has(req.request_id))return saved.get(req.request_id);cash+=188;interestTotal+=188;journal.push('이자 188원 반영');const r={interest_krw:'188'};saved.set(req.request_id,r);return r;};
api.getLedgerAccount=async()=>({state:{cash:{deposit_krw:cash,deposit_usd:0},state:null}});
api.previewCashSettlement=async(_,req)=>({proposal:{kind:req.classification,account_id:aid,event_date:'2026-11-05',currency:'KRW',balance:req.balance,amount:0,usd_average_rate:0,asset_id:'',quantity:0,avg_price:0,avg_price_usd:0,buy_fx_rate:0,first_buy_date:null,manual_dividend_override:null,reason:req.reason},before:{cash:{deposit_krw:cash,deposit_usd:0}},delta:req.balance-cash,token:'b'.repeat(64)});
api.commitLedgerCorrection=async(_,req)=>{if(saved.has(req.request_id))return saved.get(req.request_id);cash=req.proposal.balance;journal.push('잔고 차이 정정 이력 저장');const r={id:'qa-correction',saved:true};saved.set(req.request_id,r);return r;};
export default function Review(){const [mount,setMount]=useState(0),[revision,setRevision]=useState(0),[request,setRequest]=useState(null),[input,setInput]=useState(false);
 const changed=async()=>setRevision(v=>v+1);
 const reset=next=>{scenario=next;cash=next==='matched'?0:3000086;interestTotal=1000;journal=[];saved=new Map();localStorage.removeItem('cash-settlement/pending/v1/'+pid);setRequest(null);setInput(false);setMount(v=>v+1);setRevision(v=>v+1);};
 const controls=<><p>합성 예시 전용 · 운영 DB·NH 연결 없음 · 아래 동작은 이 화면에서만 적용됩니다.</p><div style={{display:'flex',gap:8,flexWrap:'wrap',margin:'16px 0'}}>{Object.entries(scenarios).map(([key,label])=><button className="btn btn-secondary" key={key} onClick={()=>reset(key)}>{label}</button>)}</div></>;
 return <main style={{maxWidth:960,margin:'24px auto',padding:16}}><h2>CMA 잔고 확인 · 화면 검토</h2>{controls}<p>예시 장부 잔고 <strong>{cash.toLocaleString('ko-KR')}원</strong> · 이력 {journal.length}건</p>
 {input&&<div className="section-card" role="status"><strong>NH 알림·이체 입력으로 돌아왔습니다.</strong><p>입력 중인 알림은 유지됩니다. 이 예시에서는 이체를 실제로 실행하지 않습니다.</p></div>}
 <CashSettlementPanel key={'settlement'+mount} portfolioId={pid} accounts={[account()]} reviewRequest={request} onReturnToInput={()=>setInput(true)} onChanged={changed}/>
 <CmaIncomePanel key={'cma'+mount} portfolioId={pid} revision={revision} onChanged={changed} onReviewBalance={r=>setRequest({...r,key:crypto.randomUUID()})} onReturnToInput={()=>setInput(true)}/>
 <p style={{fontSize:13,color:'var(--text-secondary)'}}>기본 화면에는 비교 금액과 다음 행동만 표시하고, 상세 근거·이력·설정은 펼쳐서 확인합니다.</p>
 </main>;
}
const params=new URLSearchParams(location.search);
createRoot(document.getElementById('root')).render(params.has('mobile')?<main style={{maxWidth:500,margin:'16px auto'}}><h2>모바일 화면 예시 · 390px</h2><a href="./index.html">데스크톱 예시로</a><iframe title="CMA 모바일 화면" src="./index.html?frame=1" style={{display:'block',width:390,maxWidth:'100%',height:1000,border:'1px solid #334155',borderRadius:14,marginTop:16}}/></main>:<Review/>);
