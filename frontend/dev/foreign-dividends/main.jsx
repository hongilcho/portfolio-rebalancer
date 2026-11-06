import React,{useState} from 'react';
import {createRoot} from 'react-dom/client';
import '../../src/index.css';
import {api} from '../../src/utils/api';
import {parseNhNotifications,resolveNhNotice,noticeFingerprint,writeNoticeDraft,previewNhNotices} from '../../src/utils/nhNotices';
import NamuhMessageImport from '../../src/components/Tab4History/NamuhMessageImport';
import ActivityHistory from '../../src/components/Tab4History/ActivityHistory';
import DividendDetails from '../../src/components/Tab6Analysis/DividendDetails';
import {formatKRW,formatUSD} from '../../src/utils/formatters';
const pid='qa-foreign',day='2026-11-06',rate=1355.2;
const message=`[NH투자증권] 해외증권 권리발생 안내
2050528***8 조*일님 금일 권리 지급 안내 드립니다.
1. 종목 : [SGOV] 아이셰어즈 0-3개월 미국 국채 ETF
2. 권리유형 : 배당
3. 통화코드 : USD
4. 외화배정금액 : 41.40
5. 주식배정수량 : 0
6. 외화세액 : 0.00
7. 수수료 : 0.00
8. 외화실지급액 : 41.40
9. 원화세액 : 8,540원`;
const initial=[{id:'a',account_no:'20505280008',account_alias:'예시 유동성 계좌',account_type:'일반',portfolio_id:pid,deposit_krw:20000,deposit_usd:70.44}];
const assets=[{id:'s',ticker:'SGOV',name:'iShares 0-3M Treasury Bond',market:'US',portfolio_id:pid}];
let accounts=structuredClone(initial),ledger={account_id:'a',usd_balance:70.44,cost_krw:70.44*1340,last_event_date:'2026-11-05'},items=[],requests={},counter=0;
for(const key of Object.keys(api))api[key]=async()=>{throw Error('운영 서버·증권사 연결이 차단된 합성 예시입니다.');};
const context=()=>({accounts:structuredClone(accounts),dividend_rate:rate,transfer_accounts:[],flows:[],notices:structuredClone(items),dividend_receipts:structuredClone(items),trades:[],exchanges:[],batches:[],dividend_events:[{asset_id:'s',ex_date:'2026-11-02',amount_per_share:.328581}]});
api.getBookkeepingCapabilities=async()=>({bookkeeping_protocol:1,account_fees_protocol:1,nh_dividend_protocol:1,foreign_dividend_protocol:1});
api.getNhNoticeContext=async()=>context();
api.commitNhNotices=async(_,payload)=>{
 if(requests[payload.request_id])return requests[payload.request_id];
 for(const row of payload.rows){
  if(row.tax_receipt_id){const parent=items.find(n=>n.id===row.tax_receipt_id);if(!parent||parent.taxPaid)throw Error('이미 처리했거나 연결할 배당이 없습니다.');accounts[0].deposit_krw-=parent.payload.krw_tax;parent.taxPaid=true;}
  else{
   if(items.some(n=>n.payload.dividend_ex_date===row.dividend_ex_date&&!n.payload.tax_receipt_id))throw Error('이미 반영한 배당입니다.');
   const draft={id:'preview',kind:'DIVIDEND',dividendCurrency:'USD',accountId:'a',eventDate:row.event_date,external:false,applyCash:row.apply_cash,usdAmount:row.usd_amount,receiptRate:row.receipt_rate,krwTax:row.krw_tax,taxCashApplied:row.tax_cash_applied};
   const check=previewNhNotices([draft],{[day]:context()},[ledger],assets);if(check.errors.length)throw Error(check.errors.join(' '));
   accounts[0]={...accounts[0],...check.balances.a};ledger={...ledger,usd_balance:check.costs.a.balance,cost_krw:check.costs.a.cost,last_event_date:day};
  }
  items.push({id:'notice-'+(++counter),account_id:'a',event_date:row.event_date,payload:row,taxPaid:row.tax_cash_applied||row.tax_already_reflected,fingerprint:row.fingerprint});
 }
 const result={notice_count:payload.rows.length,performance_portfolios:[]};requests[payload.request_id]=result;return result;
};
api.getActivity=async()=>({total:items.length,page:1,pages:1,items:items.map(n=>({id:'NOTICE:'+n.id,account_id:'a',account_alias:accounts[0].account_alias,event_date:n.event_date,kind:'DIVIDEND',category:'CASH',currency:n.payload.tax_receipt_id?'KRW':'USD',amount:n.payload.tax_receipt_id?-8540:n.payload.usd_amount,description:n.payload.tax_receipt_id?'해외 배당 원화 세금 출금':'SGOV 배당 입금',cancelled:false,detail:{...n.payload,quantity:undefined,price:undefined,tax_paid:n.taxPaid,dividend_matched:!n.payload.tax_receipt_id,reference_date:n.payload.dividend_ex_date}})).reverse()});
async function prepare(){const parsed=resolveNhNotice(parseNhNotifications(message,day)[0],accounts,assets,pid);writeNoticeDraft(pid,{rows:[{...parsed,id:'example',fingerprint:await noticeFingerprint(message)}],requestId:crypto.randomUUID()});}
await prepare();
export default function App(){
 const [revision,setRevision]=useState(0),[view,setView]=useState('input');const changed=async()=>setRevision(n=>n+1);
 const received=items.find(n=>!n.payload.tax_receipt_id),net=received?(41.4*rate-8540)/rate:0;
 const display=received?[{...accounts[0],holdings:[{asset_id:'s',asset_name:'SGOV',market:'US',dividend_profit_usd:net,dividend_profit_krw:net*rate,dividend_details:[{ex_date:'2026-11-02',holding_quantity:126,amount_per_share:.328581,gross_amount:41.4,tax_amount:0,net_amount:41.4,krw_tax:8540,source:'NH_RECEIPT',payment_date:day}]}]}]:[];
 return <main style={{maxWidth:900,margin:'0 auto',padding:16}}><h1>해외 배당 · 로컬 검토</h1><p>합성 예시 전용 · 운영 DB·증권사 연결 없음. 화면 저장은 메모리에서만 수행하며, 실제 회계 경로는 별도 PostgreSQL에서 검증했습니다.</p>
 <div className="section-card"><h3>현재 장부 · 예시 유동성 계좌</h3><p>달러 <strong>{formatUSD(accounts[0].deposit_usd)}</strong> · 원화 <strong>{formatKRW(accounts[0].deposit_krw)}</strong></p><p>평균 취득환율 <strong>{(ledger.cost_krw/ledger.usd_balance).toFixed(4)}원/달러</strong></p><small>자료 보완 예시: Yahoo 9/1 이후 누락 → iShares 11/2 배당 $0.328581 확인</small></div>
 <div style={{display:'flex',gap:8,flexWrap:'wrap',margin:'12px 0'}}><button className="btn btn-secondary" onClick={()=>setView('input')}>5번 · 배당 알림 입력</button><button className="btn btn-secondary" onClick={()=>setView('records')}>5번 · 기록 조회 / 세금 확인</button><button className="btn btn-secondary" onClick={()=>setView('dividends')}>7번 · 배당 손익</button><button className="btn btn-secondary" onClick={async()=>{accounts=structuredClone(initial);ledger={account_id:'a',usd_balance:70.44,cost_krw:70.44*1340,last_event_date:'2026-11-05'};items=[];requests={};await prepare();setRevision(n=>n+1);setView('input');}}>예시 처음부터</button></div>
 {view==='input'&&<NamuhMessageImport key={'input-'+revision} focused accounts={accounts} assets={assets} portfolioId={pid} tradeDate={day} ledgers={[ledger]} onChanged={changed}/>}
 {view==='records'&&<ActivityHistory portfolioId={pid} accounts={accounts} assets={assets} active revision={revision} onChanged={changed}/>}
 {view==='dividends'&&<DividendDetails accounts={display}/>}
 </main>;
}
createRoot(document.getElementById('root')).render(<App/>);
