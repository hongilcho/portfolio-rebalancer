import React,{useState} from 'react';
import {createRoot} from 'react-dom/client';
import '../../src/index.css';
import {api} from '../../src/utils/api';
import {parseNhNotifications,resolveNhNotice,noticeFingerprint,writeNoticeDraft} from '../../src/utils/nhNotices';
import NamuhMessageImport from '../../src/components/Tab4History/NamuhMessageImport';
import DividendDetails from '../../src/components/Tab6Analysis/DividendDetails';
import ActivityHistory from '../../src/components/Tab4History/ActivityHistory';
const pid='qa-dividend';
const messages=`[NH투자증권] 분배금 입금 안내
2050228***8 조*일 님 계좌로 분배금 입금 안내 드립니다.
1. 종목명 : 미래에셋 TIGER 미국배당다우존스증권상장지수투자신탁(주식)
2. 기준일 : 2026.10.30
3. 세전금액 : 4,025원
  세후금액 :4,025원
  세금합계 : 0원
4. 입금일: 2026.11.03

[NH투자증권]퇴직연금 분배금 입금안내
계좌번호 : 212-03-52***1
조*일님 계좌로 분배금 입금안내 드립니다.
1. 종목명 : ACE 미국30년국채액티브
2. 기준일 : 2026-10-30
3. 분배금 : 4,433원
4. 입금일 : 2026-11-03`;
const initialAccounts=[{id:'isa',account_no:'20502280008',account_alias:'검토용 ISA',account_type:'ISA',deposit_krw:2000,deposit_usd:0,portfolio_id:pid},
 {id:'irp',account_no:'21203520001',account_alias:'검토용 IRP',account_type:'IRP',deposit_krw:500,deposit_usd:0,portfolio_id:pid}];
const assets=[{id:'tiger',name:'TIGER 미국배당다우존스',ticker:'QA1',market:'KR',portfolio_id:pid,allowed_accounts:['isa']},
 {id:'ace',name:'ACE 미국30년국채액티브',ticker:'QA2',market:'KR',portfolio_id:pid,allowed_accounts:['irp']}];
let accounts=[],items=[],batches=[],counter=0;
for(const key of Object.keys(api))api[key]=async()=>{throw Error('이 화면은 운영 서버나 증권사에 연결하지 않습니다.');};
api.getBookkeepingCapabilities=async()=>({bookkeeping_protocol:1,account_fees_protocol:1,nh_dividend_protocol:1});
api.getNhNoticeContext=async(_,day)=>({accounts:structuredClone(accounts),transfer_accounts:[],flows:[],notices:structuredClone(items.filter(n=>!n.reversed_at&&n.event_date===day)),trades:[],exchanges:[],batches:structuredClone(batches),dividend_events:assets.map((a,i)=>({asset_id:a.id,ex_date:'2026-10-29',amount_per_share:i?44.3:40.2}))});
api.commitNhNotices=async(_,payload)=>{
 const prior=batches.find(b=>b.request_id===payload.request_id);if(prior)return prior.result;
 if(payload.rows.some(r=>items.some(n=>!n.reversed_at&&n.account_id===r.account_id&&n.payload.asset_id===r.asset_id&&n.payload.reference_date===r.reference_date)))throw Error('이미 반영한 배당입니다.');
 const id='local-'+(++counter),before=structuredClone(accounts);
 for(const row of payload.rows){if(row.kind!=='DIVIDEND')throw Error('이 예시는 배당 입금만 지원합니다.');if(row.apply_cash)accounts.find(a=>a.id===row.account_id).deposit_krw+=row.krw_amount;
 items.push({id:'notice-'+(++counter),batch_id:id,kind:'DIVIDEND',account_id:row.account_id,event_date:row.event_date,fingerprint:row.fingerprint,payload:structuredClone(row),result:{dividend_matched:Boolean(row.dividend_ex_date)},reversed_at:null});}
 const result={batch_id:id,notice_count:payload.rows.length,performance_portfolios:[]};batches.unshift({id,request_id:payload.request_id,result,before,created_at:new Date().toISOString()});return result;
};
api.undoNhNotices=async(_,id)=>{const batch=batches.find(b=>b.id===id);accounts=structuredClone(batch.before);for(const n of items.filter(n=>n.batch_id===id))n.reversed_at=new Date().toISOString();batch.reversed_at=new Date().toISOString();return {reversed:true,performance_portfolios:[]};};
api.getActivity=async(_,query)=>{const rows=items.filter(n=>query.include_cancelled||!n.reversed_at).map(n=>({id:'NOTICE:'+n.id,category:'CASH',kind:'DIVIDEND',account_id:n.account_id,account_alias:accounts.find(a=>a.id===n.account_id).account_alias,event_date:n.event_date,currency:'KRW',amount:n.payload.krw_amount,description:'배당·분배금 입금',cancelled:Boolean(n.reversed_at),batch_id:n.reversed_at?null:n.batch_id,
 detail:{...n.payload,dividend_matched:n.result.dividend_matched,cash_applied:n.payload.apply_cash,asset_id:n.payload.asset_id}}));return {items:rows,total:rows.length,page:1,page_size:20,pages:1};};
api.matchDividendReceipt=async(_,id,payload)=>{const n=items.find(n=>n.id===id);n.payload.dividend_ex_date=payload.ex_date;n.result.dividend_matched=true;return {linked:true,cash_changed:false};};
async function reset(){accounts=structuredClone(initialAccounts);items=[];batches=[];
 const rows=[];for(const parsed of parseNhNotifications(messages,'2026-11-03')){const {raw,...row}=resolveNhNotice(parsed,accounts,assets,pid);rows.push({...row,id:crypto.randomUUID(),fingerprint:await noticeFingerprint(raw)});}
 writeNoticeDraft(pid,{rows,requestId:crypto.randomUUID(),pendingPayload:null});}
export default function Review(){const [version,setVersion]=useState(0),[mount,setMount]=useState(0);
 const shown=accounts.map((a,i)=>{const actual=items.find(n=>!n.reversed_at&&n.account_id===a.id&&n.payload.dividend_ex_date);const estimated=i?4430:4020;const amount=actual?actual.payload.krw_amount:estimated;
 return {...a,holdings:[{asset_id:assets[i].id,asset_name:assets[i].name,market:'KR',dividend_profit_krw:amount,dividend_details:[{ex_date:'2026-10-29',holding_quantity:100,amount_per_share:i?44.3:40.2,gross_amount:actual?actual.payload.gross_amount:estimated,tax_amount:actual?actual.payload.tax_amount:0,net_amount:amount,...(actual?{source:'NH_RECEIPT',payment_date:actual.event_date}:{})}]}]};});
 return <main style={{maxWidth:1100,margin:'24px auto',padding:16}}><h2>NH 배당·분배금 입금 확인</h2><p>합성 계좌 전용 · 운영 DB·증권사 연결 없음 · 아래 반영·취소는 이 예시 안에서만 동작합니다.</p>
 <button className="btn btn-secondary" onClick={async()=>{await reset();setMount(n=>n+1);setVersion(n=>n+1);}}>두 알림 예시로 다시 시작</button>
 <div className="section-card" style={{marginTop:16}}>{accounts.map(a=><p key={a.id}><strong>{a.account_alias}</strong> · 예수금 {a.deposit_krw.toLocaleString('ko-KR')}원</p>)}<p>외부 투자금 기록: 0건 · 수량·매입단가 변경 없음</p></div>
 <NamuhMessageImport key={mount} accounts={accounts} assets={assets} portfolioId={pid} tradeDate="2026-11-03" ledgers={[]} focused active onChanged={async()=>setVersion(n=>n+1)}/>
 <DividendDetails accounts={shown}/><h3>5번 탭 기록 조회 예시</h3><ActivityHistory portfolioId={pid} accounts={accounts} assets={assets} active revision={version} onChanged={async()=>setVersion(n=>n+1)}/>
 </main>;
}
reset().then(()=>createRoot(document.getElementById('root')).render(<Review/>));
