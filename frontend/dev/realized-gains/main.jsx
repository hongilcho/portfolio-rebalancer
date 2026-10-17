import React,{useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import '../../src/index.css';
import RealizedGainsPanel from '../../src/components/Tab6Analysis/RealizedGainsPanel';
import TradeBatchForm from '../../src/components/Tab4History/TradeBatchForm';
import {feePayload} from '../../src/utils/tradeCosts';
import {formatKRW,formatUSD} from '../../src/utils/formatters';

const BASE=import.meta.env.VITE_API_BASE_URL||'http://127.0.0.1:8132';
async function request(path,body){const r=await fetch(BASE+path,body?{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body)}:{});const data=await r.json();if(!r.ok)throw Object.assign(Error(typeof data.detail==='string'?data.detail:JSON.stringify(data.detail)),{status:r.status});return data;}
const blank=()=>({id:crypto.randomUUID(),accountId:'acc',assetId:'',quantity:0,price:0,exchangeRate:1400});
const previewClient={getRealizedGains:(pid,params)=>request('/api/trades/realized?'+new URLSearchParams({portfolio_id:pid,...params}))};
export default function Review(){
  const [data,setData]=useState(null),[revision,setRevision]=useState(0),[buyRows,setBuys]=useState([blank()]),[sellRows,setSells]=useState([blank()]);
  const [day,setDay]=useState('2026-10-17'),[error,setError]=useState(''),[busy,setBusy]=useState(false);
  const load=async()=>{setData(await request('/dev/state'));setRevision(n=>n+1);};
  useEffect(()=>{load().catch(e=>setError(e.message));},[]);
  const update=setter=>(id,k,v)=>setter(rows=>rows.map(r=>r.id!==id?r:{...r,[k]:v,...(k==='assetId'?{price:v==='vt'?120:12000,costsConfirmed:false}:{})}));
  async function save(){setBusy(true);setError('');try{
    const rows=[...buyRows.map(r=>({...r,kind:'BUY'})),...sellRows.map(r=>({...r,kind:'SELL'}))].filter(r=>r.assetId&&r.quantity>0&&r.price>0);
    if(!rows.length)throw Error('종목·수량·단가를 입력해주세요.');
    await request('/api/trades/batch',{portfolio_id:'p',request_id:crypto.randomUUID(),trade_date:day,trades:rows.map(r=>({account_id:r.accountId,asset_id:r.assetId,trade_type:r.kind,quantity:r.quantity,price:r.price,currency:r.assetId==='vt'?'USD':'KRW',exchange_rate:r.assetId==='vt'?r.exchangeRate:1,...feePayload(r,r.assetId==='vt')}))});
    setBuys([blank()]);setSells([blank()]);await load();
  }catch(e){setError(e.message);}finally{setBusy(false);}}
  if(!data)return <main style={{padding:24}}>합성 검토 화면 준비 중… {error}</main>;
  const holdings=Object.fromEntries(data.accounts.map(a=>[a.id,data.holdings.filter(h=>h.account_id===a.id)]));
  return <main style={{maxWidth:1040,margin:'0 auto',padding:'20px 12px'}}>
    <section className="section-card"><h1 style={{fontSize:'1.4rem'}}>실현손익 · 전량 매도 이력</h1><p>합성 예시입니다. 운영 DB·증권사와 연결되지 않습니다.</p><p>{data.legacy_mode?'과거 잔고와 매수 이력의 중복을 일회성으로 보완한 합성 예시입니다. 수량·원가·예수금·과거 매매는 유지됩니다.':'국내 ETF 전량 매도 후 재매수, VT 일부 매도 예시입니다. 전량 매도·재매수를 입력하거나 최근 기록을 취소해보세요.'}</p><button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={async()=>{await request('/dev/reset',{});setBuys([blank()]);setSells([blank()]);await load();}}>합성 예시로 초기화</button>
      {data.accounts.map(a=><p key={a.id}>{a.account_alias} · 예수금 {formatKRW(a.deposit_krw)} / {formatUSD(a.deposit_usd)} · {data.holdings.filter(h=>h.account_id===a.id&&h.quantity>0).map(h=>`${h.asset_name} ${h.quantity}주`).join(', ')||'보유 종목 없음'}</p>)}</section>
    {data.legacy_mode&&<p>세 종목의 장부 기준은 합성 예시를 만들 때 한 번 등록했습니다. 일반 화면에는 등록·취소 버튼이 없으며, 이후 매매는 기존 입력 화면을 사용합니다.</p>}
    <RealizedGainsPanel portfolioId="p" accounts={data.accounts} assets={data.assets} revision={revision} client={previewClient}/>
    {error&&<p role="alert">{error}</p>}
    <details className="section-card"><summary>5번 탭 매매 입력 화면 · 합성 거래 직접 시험</summary>
      <TradeBatchForm focused tradeDate={day} setTradeDate={setDay} buyRows={buyRows} sellRows={sellRows} assets={data.assets} accounts={data.accounts} usdKrw={1400} accountHoldingsMap={holdings} usdLedgers={[]}
        updateBuyRow={update(setBuys)} updateSellRow={update(setSells)} addBuyRow={()=>setBuys(r=>[...r,blank()])} addSellRow={()=>setSells(r=>[...r,blank()])} removeBuyRow={id=>setBuys(r=>r.filter(x=>x.id!==id))} removeSellRow={id=>setSells(r=>r.filter(x=>x.id!==id))} handleSaveBatchTrades={save} savingBatch={busy}/>
    </details>
    <details className="section-card"><summary>합성 장부 기록 · 최근 기록 취소</summary>{data.trades.map(t=><p key={t.id}>{t.trade_date} · {t.trade_type} · {t.asset_id} {t.quantity}주 × {t.price} <button type="button" className="btn btn-secondary btn-sm" disabled={busy} onClick={async()=>{try{await request('/dev/undo/'+t.id,{});await load();}catch(e){setError(e.message);}}}>이 합성 기록 취소</button></p>)}</details>
  </main>;
}
createRoot(document.getElementById('root')).render(<Review/>);
