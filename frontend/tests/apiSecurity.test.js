import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer} from 'vite';
import {fileURLToPath} from 'node:url';

const memory=()=>{const data=new Map();return {getItem:k=>data.get(k)??null,setItem:(k,v)=>data.set(k,v),removeItem:k=>data.delete(k),get length(){return data.size;},key:i=>[...data.keys()][i]};};
const original={fetch:globalThis.fetch,sessionStorage:globalThis.sessionStorage,localStorage:globalThis.localStorage};
globalThis.sessionStorage=memory();globalThis.localStorage=memory();
const server=await createServer({root:fileURLToPath(new URL('../',import.meta.url)),envDir:false,logLevel:'error',
  cacheDir:'node_modules/.vite-test-security',server:{middlewareMode:true,watch:null,hmr:false,ws:false}});
try {
  const session=await server.ssrLoadModule('/src/utils/authSession.js');
  const {api}=await server.ssrLoadModule('/src/utils/api.js');
  const login=token=>({access_token:token,expires_at:Math.floor(Date.now()/1000)+3600,success:true});
  await test('old UI flag does not authenticate; login validates and saves a real session',async()=>{
    session.clearAuthSession();globalThis.localStorage.setItem('portfolio_auth','true');
    assert.equal(session.getAuthSession(),null);
    let sends=0;
    globalThis.fetch=async(url,options)=>{
      sends++;assert.ok(url.endsWith('/api/auth/verify'));
      assert.equal(options.headers.Authorization,undefined);
      return {ok:true,json:async()=>({success:true})};
    };
    await assert.rejects(api.verifyPassword('synthetic'),/백엔드 배포/);
    assert.equal(session.getAuthSession(),null);
    globalThis.fetch=async()=>({ok:true,json:async()=>login('signed-synthetic')});
    await api.verifyPassword('synthetic');assert.equal(sends,1);
    assert.equal(session.getAuthSession().access_token,'signed-synthetic');
    assert.equal(globalThis.localStorage.getItem('portfolio_auth'),null);
  });
  await test('read, write, cancel and ZIP download carry auth only in headers',async()=>{
    session.saveAuthSession(login('header-only-synthetic'));const methods=[];
    globalThis.fetch=async(url,options)=>{
      assert.equal(options.headers.Authorization,'Bearer header-only-synthetic');
      assert.ok(!url.includes('header-only-synthetic'));methods.push(options.method||'GET');
      return {ok:true,json:async()=>({success:true}),blob:async()=>new Blob(['PK synthetic zip'])};
    };
    await api.getAccounts('p');await api.createPortfolio('synthetic');
    await api.batchDeleteTrades(['qa']);
    const blob=await api.downloadBackup();assert.ok((await blob.text()).startsWith('PK'));
    assert.deepEqual(methods,['GET','POST','DELETE','GET']);
  });
  await test('401 requires login but preserves exact pending receipt and trade draft',async()=>{
    session.saveAuthSession(login('expires-on-server'));let events=0;
    const stop=session.onAuthExpired(()=>events++);
    globalThis.localStorage.setItem('manual-forex/v1/p',JSON.stringify({payload:{request_id:'exact-pending'}}));
    globalThis.localStorage.setItem('portfolio_trade_draft_v1_p','keep-draft');
    globalThis.sessionStorage.setItem('portfolio_dashboard_v2_p','cached-financial-view');
    globalThis.fetch=async()=>({ok:false,status:401,json:async()=>({detail:'expired'})});
    await assert.rejects(api.recordUsdEvent('a',{request_id:'exact-pending'}),e=>e.status===401);
    assert.equal(events,1);assert.equal(session.getAuthSession(),null);
    assert.equal(globalThis.localStorage.getItem('portfolio_trade_draft_v1_p'),'keep-draft');
    assert.equal(JSON.parse(globalThis.localStorage.getItem('manual-forex/v1/p')).payload.request_id,'exact-pending');
    assert.equal(globalThis.sessionStorage.getItem('portfolio_dashboard_v2_p'),null);
    session.saveAuthSession(login('new-session'));
    globalThis.fetch=async(url,options)=>{assert.equal(JSON.parse(options.body).request_id,'exact-pending');return {ok:true,json:async()=>({success:true})};};
    await api.recordUsdEvent('a',{request_id:'exact-pending'});stop();
  });
  await test('a late old 401 cannot discard a newer login',async()=>{
    session.saveAuthSession(login('old-session'));let release;
    globalThis.fetch=()=>new Promise(resolve=>release=resolve);
    const old=api.getAccounts('p');
    session.saveAuthSession(login('newer-session'));
    release({ok:false,status:401,json:async()=>({detail:'old expired'})});
    await assert.rejects(old,e=>e.status===401);
    assert.equal(session.getAuthSession().access_token,'newer-session');
  });
  await test('expired local session sends no request; unavailable storage permits in-memory session',async()=>{
    session.clearAuthSession();globalThis.sessionStorage.setItem('portfolio_api_session_v1',JSON.stringify({access_token:'old',expires_at:1}));
    let calls=0;globalThis.fetch=async()=>{calls++;throw new Error('must not send');};
    await assert.rejects(api.getAccounts('p'),e=>e.status===401);assert.equal(calls,0);
    globalThis.sessionStorage={getItem:()=>{throw new Error('blocked');},setItem:()=>{throw new Error('blocked');},removeItem:()=>{}};
    session.saveAuthSession(login('in-memory'));assert.equal(session.getAuthSession().access_token,'in-memory');
    session.clearAuthSession();
  });
  await test('session expiry before the app subscribes still requests login',()=>{
    session.clearAuthSession();let calls=0;
    const stop=session.onAuthExpired(()=>calls++);
    assert.equal(calls,1);stop();
  });
} finally {
  await server.close();
  for(const [key,value] of Object.entries(original)) {if(value===undefined)delete globalThis[key];else globalThis[key]=value;}
}
