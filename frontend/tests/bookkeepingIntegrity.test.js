import test from 'node:test';
import assert from 'node:assert/strict';
import React from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {createServer} from 'vite';
import {parseSync} from 'rolldown/experimental';
import {fileURLToPath} from 'node:url';
import {refreshBookkeeping} from '../src/utils/bookkeepingRefresh.js';
import {readPendingRequest,persistPendingRequest,clearPendingRequest,requireBookkeepingProtocol,singleSubmission} from '../src/utils/bookkeepingRequest.js';
import {writeTradeDraft,draftKey} from '../src/utils/tradeDraft.js';

const memory=()=>{const data=new Map();return {getItem:k=>data.get(k)??null,setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k)};};
test('a failed read cannot prevent the other bookkeeping views from refreshing',async()=>{
  const called=[];
  await assert.rejects(refreshBookkeeping({usd:async()=>{called.push('usd');throw new Error('offline');},
    overview:async()=>called.push('overview'),records:async()=>called.push('records')}),/usd/);
  assert.deepEqual(called.sort(),['overview','records','usd']);
});
test('pending financial requests survive reload and storage failure prevents an untracked send',()=>{
  const storage=memory(),request={account_id:'a',payload:{request_id:'request-123',usd_amount:100}};
  persistPendingRequest('p',request,storage);assert.deepEqual(readPendingRequest('p',storage),request);
  assert.throws(()=>persistPendingRequest('p',request,{setItem:()=>{throw new Error('blocked');}}),/임시 저장/);
  clearPendingRequest('p',storage);assert.equal(readPendingRequest('p',storage),null);
});
test('old backends are rejected before financial writes',async()=>{
  await assert.rejects(requireBookkeepingProtocol({getBookkeepingCapabilities:async()=>({})}),/요청은 보내지 않았/);
  await requireBookkeepingProtocol({getBookkeepingCapabilities:async()=>({bookkeeping_protocol:1})});
});
test('double click only enters one submission and failure releases the guard',async()=>{
  const lock={current:false};let finish,count=0;
  const action=()=>{count++;return new Promise(resolve=>{finish=resolve;});};
  const first=singleSubmission(lock,action);await singleSubmission(lock,action);
  assert.equal(count,1);finish();await first;
  await assert.rejects(singleSubmission(lock,async()=>{throw new Error('lost');}));
  assert.equal(lock.current,false);
});

const originals={storage:globalThis.localStorage,fetch:globalThis.fetch,window:globalThis.window};
globalThis.localStorage=memory();globalThis.fetch=()=>{throw new Error('No real IO in UI bookkeeping tests');};
const alerts=[];globalThis.window={alert:m=>alerts.push(m),confirm:()=>true};globalThis.alert=globalThis.window.alert;
const server=await createServer({root:fileURLToPath(new URL('../',import.meta.url)),logLevel:'error',cacheDir:'node_modules/.vite-test-integrity',
  server:{middlewareMode:true,watch:null,hmr:false,ws:false},plugins:[{name:'bookkeeping-control-fixtures',enforce:'pre',transform(source,id,options){
    if(!options?.ssr || !/(HistoryTab|UsdLedgerPanel|DepositLedgerPanel|ExternalCashFlowPanel|AssetEditor)\.jsx$/.test(id))return;
    const {program,errors}=parseSync(id,source);assert.equal(errors.length,0);const edits=[];
    const component=id.split('/').at(-1).replace('.jsx','');
    function walk(node){if(!node || typeof node!=='object')return;
      if(node.type==='VariableDeclarator' && node.id.type==='ArrayPattern' && node.init?.callee?.name==='useState'){
        const key=node.id.elements[0]?.name,arg=node.init.arguments[0];
        if(arg)edits.push({start:arg.start,end:arg.end,text:`(Object.hasOwn(globalThis.__bookSeeds['${component}']||{},'${key}')?globalThis.__bookSeeds['${component}'].${key}:(${source.slice(arg.start,arg.end)}))`});
      }
      if(node.type==='JSXAttribute' && ['onClick','onSubmit'].includes(node.name.name) && node.value?.expression){
        const e=node.value.expression,label=source.slice(e.start,e.end);
        edits.push({start:e.start,end:e.end,text:`(()=>{const callback=(${label});globalThis.__bookHandlers.push({component:'${component}',label:${JSON.stringify(label)},callback});return callback;})()`});
      }
      for(const value of Object.values(node))if(Array.isArray(value))value.forEach(walk);else if(value && typeof value==='object')walk(value);
    }
    walk(program);for(const e of edits.sort((a,b)=>b.start-a.start))source=source.slice(0,e.start)+e.text+source.slice(e.end);return source;
  }}]});
const accounts=[{id:'a',portfolio_id:'p',account_no:'QA-001',account_alias:'QA',deposit_usd:100,deposit_krw:1000000}];
const assets=[{id:'etf',portfolio_id:'p',name:'QA ETF',ticker:'QA',market:'KR',allowed_accounts:['a']}];
const payload={request_id:'manual-exact-1',portfolio_id:'p',trade_date:'2026-01-02',trades:[{account_id:'a',asset_id:'etf',trade_type:'BUY',quantity:1,price:100,currency:'KRW'}]};
try{
  const History=(await server.ssrLoadModule('/src/components/Tab4History/HistoryTab.jsx')).default;
  const Usd=(await server.ssrLoadModule('/src/components/Tab4History/UsdLedgerPanel.jsx')).default;
  const client=(await server.ssrLoadModule('/src/utils/api.js')).api;
  const render=(Component,props,seeds={})=>{globalThis.__bookSeeds=seeds;globalThis.__bookHandlers=[];return renderToStaticMarkup(React.createElement(Component,props));};
  const props={accounts,assets,currentPortfolioId:'p',priceMap:{},onSaved:async()=>{},performance:{data:null,busy:false,error:'',notice:'',run:async action=>action(),capture:async()=>{}}};
  test('restored manual request opens its retry controls and refresh failure cannot mislabel a saved trade',async()=>{
    globalThis.localStorage=memory();alerts.length=0;
    const row={id:'row',accountId:'a',assetId:'etf',quantity:1,price:100,exchangeRate:1};
    writeTradeDraft(globalThis.localStorage,'p',{tradeDate:'2026-01-02',buyRows:[row],sellRows:[],uncertainSubmission:true,pendingSubmission:payload});
    let overview=0,sends=0;
    client.getBookkeepingCapabilities=async()=>({bookkeeping_protocol:1});
    client.batchExecuteTrades=async body=>{assert.deepEqual(body,payload);sends++;return {message:'saved',results:[{index:0,success:true}]};};
    client.getUsdLedgers=async()=>{throw new Error('ledger read failed');};
    const html=render(History,{...props,onSaved:async()=>{overview++;}});
    assert.match(html,/aria-pressed="true"[^>]*>[\s\S]*?직접 입력/);
    assert.match(html,/같은 요청의 결과 다시 확인/);
    const retry=globalThis.__bookHandlers.find(h=>h.component==='HistoryTab' && h.label.includes('submitManual(pendingSubmission)'));
    await retry.callback();assert.equal(sends,1);assert.equal(overview,1);
    assert.equal(globalThis.localStorage.getItem(draftKey('p')),null);
    assert.ok(alerts.some(m=>m.includes('저장은 완료')));
  });
  test('lost FX response preserves one exact request and navigation returns directly to dollar retry',async()=>{
    globalThis.localStorage=memory();
    const request={account_id:'a',payload:{request_id:'fx-exact-retry',portfolio_id:'p',kind:'EXCHANGE_IN',occurred_at:'2026-01-02T09:00:00+09:00',usd_amount:10,krw_amount:13000,rate:0,notes:''}};
    persistPendingRequest('manual-forex/v1/p',request);
    const html=render(History,props);assert.match(html,/aria-pressed="true"[^>]*>[\s\S]*?달러 관리/);
    let calls=0;
    client.recordUsdEvent=async(aid,body)=>{assert.equal(aid,'a');assert.deepEqual(body,request.payload);calls++;throw new Error('lost response');};
    render(Usd,{accounts,assets,ledgers:[],portfolioId:'p',onChanged:async()=>{},focused:true});
    const retry=globalThis.__bookHandlers.find(h=>h.component==='UsdLedgerPanel' && h.label==='submit');
    await retry.callback();assert.deepEqual(readPendingRequest('manual-forex/v1/p'),request);
    client.recordUsdEvent=async()=>({message:'original result'});
    await retry.callback();assert.equal(readPendingRequest('manual-forex/v1/p'),null);assert.equal(calls,1);
  });
  test('several pending receipts lock edits but allow navigation to each retry',()=>{
    globalThis.localStorage=memory();
    persistPendingRequest('manual-funds/v1/p',{payload:{request_id:'funds-request'}});
    persistPendingRequest('manual-forex/v1/p',{account_id:'a',payload:{request_id:'forex-request'}});
    const html=render(History,props,{HistoryTab:{childBusy:{funds:true,usd:true},childWriting:{}}});
    assert.doesNotMatch(html,/id="history-record-tab"[^>]*disabled/);
    const methodButton=[...html.matchAll(/<button([^>]*)>([\s\S]*?)<\/button>/g)].filter(m=>['NH 알림 가져오기','직접 입력','달러 관리'].some(label=>m[2].endsWith(label)));
    assert.equal(methodButton.length,3);assert.ok(methodButton.every(m=>!m[1].includes('disabled')));
    assert.match(html,/<fieldset disabled="" class="workflow-form"/);
  });
  test('first manual cash input remains available before a performance baseline exists',()=>{
    globalThis.localStorage=memory();
    const html=render(History,{...props,performance:{...props.performance,data:{tracking:null,flows:[]}}},
      {HistoryTab:{method:'manual',manualKind:'funds'}});
    assert.match(html,/아직 성과 시작 기준이 없습니다/);
    assert.match(html,/외부 입출금 기록 저장/);
    assert.doesNotMatch(html,/<fieldset disabled="" class="workflow-form"/);
  });
  test('pending external cash and deposit corrections reopen their manual destination',()=>{
    for(const key of ['manual-funds/v1/p','manual-deposit/v1/p']){
      globalThis.localStorage=memory();persistPendingRequest(key,{payload:{request_id:'restore-request'}});
      const html=render(History,props);assert.match(html,/aria-pressed="true"[^>]*>[\s\S]*?직접 입력/);
      assert.match(html,/같은 요청의 결과 다시 확인/);
    }
  });
}finally{
  await server.close();
  for(const [name,value] of Object.entries({localStorage:originals.storage,fetch:originals.fetch,window:originals.window})){
    if(value===undefined)delete globalThis[name];else globalThis[name]=value;
  }
  delete globalThis.alert;delete globalThis.__bookSeeds;delete globalThis.__bookHandlers;
}
