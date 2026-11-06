import test from 'node:test';
import assert from 'node:assert/strict';
import {parseNhNotifications,resolveNhNotice,noticeApiRow,previewNhNotices,validateNhNotice} from '../src/utils/nhNotices.js';
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
const accounts=[{id:'a',account_no:'20505280008',portfolio_id:'p',deposit_krw:20000,deposit_usd:70.44}];
const assets=[{id:'s',name:'SGOV',ticker:'SGOV',market:'US',portfolio_id:'p'}];
const context={accounts,dividend_rate:1355.2,dividend_events:[{asset_id:'s',ex_date:'2026-11-02',amount_per_share:.328581}],notices:[]};
const row=()=>({...resolveNhNotice(parseNhNotifications(message,'2026-11-06')[0],accounts,assets,'p'),id:'r',fingerprint:'a'.repeat(64)});
const ledgers=[{account_id:'a',usd_balance:70.44,cost_krw:70.44*1340,last_event_date:'2026-11-05'}];
test('NH foreign rights parses currency, exact net, both taxes and fees; no stock rights accepted',()=>{
 const r=row();assert.equal(r.accountId,'a');assert.equal(r.assetId,'s');assert.equal(r.dividendCurrency,'USD');assert.equal(r.usdAmount,41.4);assert.equal(r.krwTax,8540);assert.equal(r.taxCashApplied,false);assert.deepEqual(r.errors,[]);
 assert.ok(parseNhNotifications(message.replace('주식배정수량 : 0','주식배정수량 : 1'),'2026-11-06')[0].errors.length);
 assert.ok(parseNhNotifications(message.replace('외화세액 : 0.00','외화세액 : 2.00'),'2026-11-06')[0].errors.length);
});
test('preview adds actual USD and moving-average cost, pending tax leaves KRW cash alone',()=>{
 const r=row(),before=structuredClone(ledgers);const preview=previewNhNotices([r],{'2026-11-06':context},ledgers,assets);
 assert.deepEqual(preview.errors,[]);assert.ok(Math.abs(preview.balances.a.deposit_usd-111.84)<1e-10);assert.equal(preview.balances.a.deposit_krw,20000);
 assert.equal(preview.costs.a.cost,70.44*1340+41.4*1355.2);assert.deepEqual(ledgers,before);
 const api=noticeApiRow(r,context);assert.equal(api.dividend_ex_date,'2026-11-02');assert.equal(api.reference_date,'2026-11-02');assert.equal(api.receipt_rate,1355.2);assert.equal(api.external,false);assert.equal(api.tax_cash_applied,false);
});
test('confirmed KRW debit and already-reflected USD can be selected independently',()=>{
 const r={...row(),taxCashApplied:true,applyCash:false};const preview=previewNhNotices([r],{'2026-11-06':context},ledgers,assets);
 assert.equal(preview.balances.a.deposit_usd,70.44);assert.equal(preview.balances.a.deposit_krw,11460);assert.equal(preview.costs.a.cost,70.44*1340);
});
test('missing public event requires explicit ex-date; duplicate on another payment day is blocked',()=>{
 const r=row();const missing={...context,dividend_events:[]};assert.ok(validateNhNotice(r,missing,accounts,assets,'p',[],[]).errors.some(e=>e.includes('배당락일')));
 r.dividendExDate='2026-11-02';assert.deepEqual(validateNhNotice(r,missing,accounts,assets,'p',[],[]).errors,[]);
 const duplicate={...context,dividend_receipts:[{account_id:'a',payload:{asset_id:'s',dividend_ex_date:'2026-11-02'}}]};
 assert.ok(validateNhNotice(r,duplicate,accounts,assets,'p',[],[]).errors.some(e=>e.includes('이미 반영')));
});
