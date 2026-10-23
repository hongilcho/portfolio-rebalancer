import React,{useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import '../../src/index.css';
import AccountFees from '../../src/components/Tab5Settings/AccountFees';
import TradeCosts from '../../src/components/Tab4History/TradeCosts';
import CashSettlementPanel from '../../src/components/Tab4History/CashSettlementPanel';
import {feePayload} from '../../src/utils/tradeCosts';
import {api} from '../../src/utils/api';
import {formatKRW,formatUSD} from '../../src/utils/formatters';
async function request(path,body){
 const r=await fetch('http://127.0.0.1:8144'+path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)});
 const data=await r.json();if(!r.ok)throw Object.assign(Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail)),{status:r.status});return data;
}
api.getLedgerAccount=(pid,aid)=>request(`/api/ledger-adjustments/${pid}/account/${aid}`);
api.previewCashSettlement=(pid,body)=>request(`/api/ledger-adjustments/${pid}/settlement-preview`,body);
api.commitLedgerCorrection=(pid,body)=>request(`/api/ledger-adjustments/${pid}`,body);
export default function Review(){
 const [data,setData]=useState(null),[policy,setPolicy]=useState({}),[tab,setTab]=useState('settings'),[message,setMessage]=useState('');
 const [row,setRow]=useState({assetId:'ast',quantity:1,price:216000,costsConfirmed:false}),[kind,setKind]=useState('BUY'),[busy,setBusy]=useState(false);
 const load=async()=>{const v=await request('/dev/state');setData(v);setPolicy(v.accounts[0].fee_schedule);};
 useEffect(()=>{load().catch(e=>setMessage(e.message));},[]);
 const edit=(key,value)=>setRow(r=>({...r,[key]:value}));
 const act=async fn=>{setBusy(true);try{await fn();await load();}catch(e){setMessage(e.message);}finally{setBusy(false);}};
 if(!data)return <main style={{padding:24}}>예행 화면 준비 중… {message}</main>;
 const a=data.accounts[0],asset=data.assets.find(a=>a.id===row.assetId),us=asset?.market==='US';
 return <main className="fee-review"><header><span className="fee-review-badge">로컬 합성 데이터 · 운영 연결 없음</span><h1>거래 비용을 자동으로,<br/>잔돈 차이는 가끔 한 번에.</h1><p>계좌에서 요율을 한 번 설정하면 매매마다 자동 반영합니다.</p></header>
 <section className="fee-review-cash"><div><small>합성 일반계좌 · 원화</small><strong>{formatKRW(a.deposit_krw)}</strong></div><div><small>달러 예수금</small><strong>{formatUSD(a.deposit_usd)}</strong></div></section>
 <nav className="fee-review-nav">{[['settings','계좌 수수료 설정'],['trade','매매 입력'],['settle','예수금 차이 정산']].map(([key,name])=><button key={key} className={`btn ${tab===key?'btn-primary':'btn-secondary'}`} onClick={()=>{setTab(key);setMessage('');}}>{name}</button>)}</nav>
 {tab==='settings'&&<section className="section-card"><h2>합성 일반계좌 · 수수료</h2><AccountFees value={policy} onChange={setPolicy}/><button className="btn btn-primary btn-block" disabled={busy} onClick={()=>act(async()=>{await request('/dev/policy',policy);setMessage('합성 계좌의 수수료 설정을 저장했습니다.');})}>수수료 설정 저장</button></section>}
 {tab==='trade'&&<section className="section-card fee-demo-trade"><h2>체결 결과 입력</h2><p>매수·매도는 합성 장부에만 기록됩니다. 초기 예수금 원화 100만원 · 달러 $1,000</p>
   <label>거래<select className="input-select" value={kind} onChange={e=>setKind(e.target.value)}><option value="BUY">매수</option><option value="SELL">매도</option></select></label>
   <label>종목<select className="input-select" value={row.assetId} onChange={e=>setRow({assetId:e.target.value,quantity:1,price:e.target.value==='us'?100.549:e.target.value==='gold'?150000:216000,costsConfirmed:false})}>{data.assets.map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select></label>
   <label>수량<input className="input-number" type="number" min="1" value={row.quantity} onChange={e=>edit('quantity',e.target.value)}/></label>
   <label>{us?'달러 체결단가':'원화 체결단가'}<input className="input-number" type="number" min="0" step="any" value={row.price} onChange={e=>edit('price',e.target.value)}/></label>
   <TradeCosts row={row} isUS={us} tradeType={kind} account={a} asset={asset} day={data.day} onChange={edit}/>
   <button className="btn btn-primary btn-block" disabled={busy} onClick={()=>act(async()=>{await request('/api/trades/batch',{portfolio_id:'p',request_id:crypto.randomUUID(),trade_date:data.day,trades:[{account_id:'acc',asset_id:row.assetId,trade_type:kind,quantity:Number(row.quantity),price:Number(row.price),currency:us?'USD':'KRW',exchange_rate:us?1350:1,...feePayload(row,us)}]});setMessage('합성 매매와 비용을 장부에 기록했습니다.');})}>합성 장부에 기록</button>
 </section>}
 {tab==='settle'&&<CashSettlementPanel portfolioId="p" accounts={data.accounts} onChanged={load}/>}
 {message&&<p className="fee-review-message" role="status">{message}</p>}
 <details className="section-card"><summary>이번 예행의 저장 기록 {data.trades.length}건</summary>{data.trades.map(t=>{const c=typeof t.trade_costs==='string'?JSON.parse(t.trade_costs):t.trade_costs;return <p key={t.id}>{data.assets.find(a=>a.id===t.asset_id)?.name} · {t.quantity}주 · 비용 {t.currency==='USD'?formatUSD(c?.usd):formatKRW(c?.krw)} · {c?.status==='ESTIMATED'?'자동 추정':c?.status==='DEFERRED'?'비용 정산 대기':'확인 비용'}</p>;})}</details>
 <button className="btn btn-secondary" disabled={busy} onClick={()=>act(async()=>{await request('/dev/reset',{});localStorage.removeItem('cash-settlement/pending/v1/p');setMessage('합성 예행을 초기화했습니다.');})}>합성 예행 처음부터 시작</button>
 </main>;
}
createRoot(document.getElementById('root')).render(<Review/>);
