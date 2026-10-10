// Development-only synthetic preview. No API client or application credentials.
import React,{useState} from 'react';
import {createRoot} from 'react-dom/client';
import ExecutionTab from '../../src/components/Tab8Execution/ExecutionTab';
import TradeBatchForm from '../../src/components/Tab4History/TradeBatchForm';
import {parseNhNotifications} from '../../src/utils/nhNotices';
import {investmentProgress} from '../../src/utils/investmentProgress';
import {formatKRW,formatUSD} from '../../src/utils/formatters';
import '../../src/index.css';
import '../../src/App.css';
import './preview.css';
if (!import.meta.env.DEV) throw new Error('Synthetic preview is development-only');
const accounts=[{id:'cma',account_type:'CMA',account_alias:'대표 CMA',portfolio_id:'synthetic'},
 {id:'isa',account_type:'ISA',account_alias:'국내 ETF ISA',portfolio_id:'synthetic'},
 {id:'us',account_type:'GENERAL',account_alias:'미국 ETF 직투',portfolio_id:'synthetic'}];
const assets=[{id:'bond',name:'국채 ETF 예시',ticker:'0085P0',market:'KR',allowed_accounts:['isa']},
 {id:'vt',name:'VT',ticker:'VT',market:'US',allowed_accounts:['us']}];
const steps=[
 {id:'fund',kind:'DEPOSIT',title:'대표 계좌에 투자금 준비',account_id:'cma',account_alias:'대표 CMA',currency:'KRW',target_amount:1150000,depends_on:[],instruction:'은행에서 실제 입금한 알림을 붙여넣어주세요.'},
 {id:'isa-transfer',kind:'TRANSFER',title:'ISA로 매수 자금 이동',account_id:'cma',account_alias:'대표 CMA',destination_alias:'국내 ETF ISA',currency:'KRW',target_amount:190000,depends_on:['fund']},
 {id:'us-transfer',kind:'TRANSFER',title:'미국 ETF 계좌로 자금 이동',account_id:'cma',account_alias:'대표 CMA',destination_alias:'미국 ETF 직투',currency:'KRW',target_amount:960000,depends_on:['fund']},
 {id:'domestic',kind:'BUY',title:'국내 ETF 매수',account_id:'isa',account_alias:'국내 ETF ISA',asset_id:'bond',asset_name:'국채 ETF 예시',currency:'KRW',target_quantity:20,depends_on:['isa-transfer'],instruction:'MTS에서 매수한 뒤, 체결 알림을 붙여넣어 기록해주세요.'},
 {id:'fx',kind:'EXCHANGE_IN',title:'달러 환전',account_id:'us',account_alias:'미국 ETF 직투',currency:'USD',target_amount:717.31,depends_on:['us-transfer'],instruction:'보유 달러를 고려해 필요한 금액만 환전하고 실제 결과를 기록해주세요.'},
 {id:'us-buy',kind:'BUY',title:'VT 매수',account_id:'us',account_alias:'미국 ETF 직투',asset_id:'vt',asset_name:'VT',currency:'USD',target_quantity:5,depends_on:['fx'],instruction:'체결 알림이 없으면 실제 체결 수량과 달러 단가를 직접 입력하세요.'}
];
function record(step, value, suffix='initial') {
 return {id:`sample/${step.id}/${suffix}`,step_id:step.id,kind:step.kind,account_id:step.account_id,asset_id:step.asset_id,
 currency:step.currency,quantity:['BUY','SELL'].includes(step.kind)?value:undefined,amount:['BUY','SELL'].includes(step.kind)?undefined:value,ledger_status:'RECORDED'};
}
function sample(scenario='domestic') {
 const done=scenario==='prepare'?0:scenario==='domestic'?3:scenario==='partial'?3:scenario==='fx'?4:scenario==='us'?5:6;
 const results=steps.slice(0,done).map(step=>record(step,step.target_quantity || step.target_amount));
 if(scenario==='partial')results.push(record(steps[3],7));
 return {id:'synthetic-cycle',name:'10월 정기 투자',portfolio_name:'장기 포트폴리오 예시',budget_krw:1150000,status:'ACTIVE',steps,results};
}
const messages={domestic:'[NH투자증권] 매수 주문체결 알림\n종목명 : 국채 ETF 예시\n종목코드 : 0085P0\n체결종류 : 매수 전량 체결\n체결수량 : 20주\n체결단가 : 9,320원(체결평균단가)\n주문번호 : 900001',
 fund:'[NH투자증권] 입금안내\n금액 1,150,000원\n[10/10 10:36]\n계좌번호 000-00-00***0\n예시은행 예시사용자',
 fx:'[NH투자증권] 환전내역 안내\n환전일자 : 10월 10일\n계좌명 : 예*시\n환전구분 : 외화매수\n통화명 : USD\n우대율 : 100%\n환율 : 1,338.33\n외화금액 : USD 717.31\n원화금액 : 959,997'};
export function InputPreview({step,draft,onDraft,onSave,onBack}) {
 const [method,setMethod]=useState(['TRANSFER'].includes(step.kind) || step.currency==='USD' && step.kind==='BUY'?'manual':'nh');
 const [text,setText]=useState('');
 const [error,setError]=useState('');
 const [confirmed,setConfirmed]=useState(false);
 const trade=['BUY','SELL'].includes(step.kind);
 const defaultRow=()=>({id:crypto.randomUUID(),accountId:step.account_id,assetId:step.asset_id || '',quantity:0,price:step.currency==='USD'?140:9320,exchangeRate:1338.33});
 const rows=draft?.rows || [defaultRow()];
 const events=draft?.events || [];
 const write=data=>{onDraft({...draft,...data});setConfirmed(false);setError('');};
 const addNotice=()=>{
  try {const parsed=parseNhNotifications(text,'2026-10-10');
   if(!text.trim() || parsed.some(row=>row.errors.length || row.kind!==step.kind))throw new Error('이 작업에 해당하는 알림을 확인해주세요.');
   if(trade && parsed.some(row=>row.ticker!==assets.find(a=>a.id===step.asset_id).ticker))throw new Error('계획한 종목과 다른 알림입니다.');
   if(trade)write({rows:[...rows.filter(r=>r.quantity>0),...parsed.map(row=>({...defaultRow(),quantity:row.quantity,price:row.price,brokerOrderNo:row.brokerOrderNo}))]});
   else write({events:[...events,...parsed.map(row=>({id:crypto.randomUUID(),value:step.currency==='USD'?row.usdAmount:row.krwAmount,krwAmount:row.krwAmount,eventDate:row.eventDate}))]});
   setText('');
  } catch(e){setError(e.message);}
 };
 const save=()=>{
  const values=trade?rows.filter(r=>r.quantity>0):events;
  if(!values.length || (trade && values.some(row=>row.accountId!==step.account_id || row.assetId!==step.asset_id || row.price<=0))){setError('계좌·종목·수량·단가를 확인해주세요.');return;}
  if(!confirmed){setError('체결일과 계좌, 금액 또는 수량을 확인하고 아래 항목에 체크해주세요.');return;}
  onSave(values.map((row,i)=>record(step,trade?row.quantity:row.value,crypto.randomUUID()+i)));onDraft({});onBack();
 };
 const update=(id,key,value)=>write({rows:rows.map(row=>row.id===id?{...row,[key]:value}:row)});
 return <div className="preview-shared-input">
  <div className="history-inline-choice"><button aria-pressed={method==='nh'} onClick={()=>setMethod('nh')} disabled={step.kind==='TRANSFER' || step.id==='us-buy'}>NH 알림 붙여넣기</button>
    <button aria-pressed={method==='manual'} onClick={()=>setMethod('manual')}>직접 입력</button></div>
  {method==='nh' && <div className="preview-notice"><label htmlFor="execution-message">알림톡 내용</label>
    <textarea id="execution-message" rows={6} value={text} onChange={e=>setText(e.target.value)} placeholder="NH 알림을 붙여넣어주세요."/>
    <div className="preview-notice-actions"><button className="btn btn-secondary" onClick={()=>setText(messages[step.id] || '')}>예시 알림 채우기</button>
    <button className="btn btn-primary" onClick={addNotice}>확인 목록에 추가</button></div></div>}
  <label className="preview-confirm"><input type="checkbox" checked={confirmed} onChange={e=>setConfirmed(e.target.checked)}/>2026-10-10 체결일과 계좌, 수량·금액을 확인했습니다.</label>
  {error && <p className="alert-banner alert-warning" role="alert">{error}</p>}
  {trade ? <TradeBatchForm focused tradeDate="2026-10-10" setTradeDate={()=>{}} buyRows={rows} sellRows={[]} assets={assets} accounts={accounts}
    updateBuyRow={update} removeBuyRow={id=>write({rows:rows.filter(r=>r.id!==id)})} addBuyRow={()=>write({rows:[...rows,defaultRow()]})}
    usdKrw={1338.33} usdLedgers={step.currency==='USD'?[{account_id:'us',average_rate:1338.33}]:[]}
    holdingsError={false} accountHoldingsMap={{}} updateSellRow={()=>{}} removeSellRow={()=>{}} addSellRow={()=>{}}
    handleSaveBatchTrades={save} savingBatch={false} disabled={false}/>
   : <><label className="form-label">{step.currency==='USD'?'실제 유입 달러':'실제 원화 금액'}</label>
    <input className="input-number" aria-label="실행 결과 금액" type="number" min="0" step={step.currency==='USD'?'.01':'1'} value={events[0]?.value || ''}
      onChange={e=>write({events:[{id:crypto.randomUUID(),value:Number(e.target.value),eventDate:'2026-10-10'}]})}/>
    <p>{events.map(row=>step.currency==='USD'?formatUSD(row.value):formatKRW(row.value)).join(' + ') || '입력한 내역이 없습니다.'}</p>
    <button className="btn btn-primary btn-block" disabled={!confirmed || !events.length || events.some(e=>e.value<=0)} onClick={save}>확인한 결과 기록</button></>}
 </div>;
}
export function Preview() {
 const [cycle,setCycle]=useState(()=>sample());
 const [drafts,setDrafts]=useState({});
 const [tab,setTab]=useState('execution');
 const [theme,setTheme]=useState('dark');
 const [scenario,setScenario]=useState('domestic');
 const next=investmentProgress(cycle).current?.step || steps[3];
 const save=results=>setCycle(old=>({...old,results:[...old.results,...results]}));
 const input=(step,onBack)=> <InputPreview key={step.id} step={step} draft={drafts[step.id]} onDraft={draft=>setDrafts(old=>({...old,[step.id]:draft}))} onSave={save} onBack={onBack}/>;
 return <div className="preview-frame">
  <aside className="preview-banner"><strong>화면 검토용 · 합성 데이터</strong><span>실제 계좌·장부·주문에 연결되지 않습니다.</span></aside>
  <header className="preview-header"><h1>포트폴리오 리밸런서</h1><button className="btn btn-secondary btn-sm" onClick={()=>{const t=theme==='dark'?'light':'dark';setTheme(t);document.documentElement.dataset.theme=t;}}>{theme==='dark'?'밝은 화면':'어두운 화면'}</button></header>
  <div className="preview-controls"><label>상황 선택<select value={scenario} onChange={e=>{setScenario(e.target.value);setCycle(sample(e.target.value));setDrafts({});}}>
    <option value="prepare">입금 준비</option><option value="domestic">국내 매수</option><option value="partial">국내 일부 체결</option><option value="fx">환전</option><option value="us">VT 직접 입력</option><option value="done">모두 완료</option></select></label>
    <button className="btn btn-secondary btn-sm" onClick={()=>setTab(tab==='execution'?'history':'execution')}>{tab==='execution'?'5. 기록 입력 확인':'8. 투자 실행으로'}</button></div>
  <div className="preview-section-label">{tab==='execution'?'8. 투자 실행':'5. 매매 및 입출금 기록'}</div>
  <main>{tab==='execution'?<ExecutionTab key={scenario} cycle={cycle} renderInput={input} renderExistingRecords={(step,back)=><div><p>같은 계좌·종목·방향의 기존 기록을 선택합니다. 새 거래를 만들지 않습니다.</p><label className="preview-confirm"><input type="checkbox" checked={Boolean(drafts[step.id]?.existing)} onChange={e=>setDrafts(old=>({...old,[step.id]:{...old[step.id],existing:e.target.checked}}))}/>{step.asset_name || step.title} · {step.account_alias} · 예시 기존 기록</label><button className="btn btn-primary" disabled={!drafts[step.id]?.existing} onClick={()=>{save([record(step,step.target_quantity || step.target_amount,'existing')]);setDrafts(old=>({...old,[step.id]:{}}));back();}}>선택한 기록 연결</button></div>} onCloseCycle={()=>setCycle(old=>({...old,status:'CLOSED'}))}/>
    :<section className="section-card execution-input"><header><div><h3>이번 투자 기록 입력</h3><p>{next.title} · {next.account_alias}</p></div></header>{input(next,()=>setTab('execution'))}</section>}</main>
 </div>;
}
createRoot(document.getElementById('root')).render(<Preview/>);
