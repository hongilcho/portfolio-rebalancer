import test from 'node:test';
import assert from 'node:assert/strict';
import {estimateFee,setFeePolicy,requireFeeProtocol} from '../src/utils/tradingFees.js';
import {previewNhNotices} from '../src/utils/nhNotices.js';
const day='2026-01-02',kr={market:'KR'},us={market:'US'},gold={market:'KR',ticker:'M04020000'};
const account={id:'a',fee_schedule:{KR:[{from:'2026-01-01',rate_pct:'0.0141639'}],US:[{from:'2026-01-01',rate_pct:'0.07'}],GOLD:[{from:'2026-01-01',rate_pct:'0.2',vat_included:false}]}};
test('domestic, US and gold estimates use exact decimal minor units',()=>{
 assert.equal(estimateFee(account,kr,day,46,216000).amount,1407);
 assert.equal(estimateFee(account,us,day,29,100.549).amount,2.04);
 assert.equal(estimateFee(account,gold,day,1,1000000).amount,2200);
});
test('zero, unset, future and changed policies are distinct',()=>{
 assert.equal(estimateFee(account,us,'2025-12-31',1,100),null);
 const v=setFeePolicy(account.fee_schedule,'US',{from:'2026-02-01',rate_pct:'0'});
 assert.equal(estimateFee({fee_schedule:v},us,'2026-02-02',1,100).amount,0);
 assert.equal(estimateFee({fee_schedule:v},us,day,1,100).amount,.07);
 const disabled=setFeePolicy(v,'US',{from:'2026-03-01',rate_pct:''});
 assert.equal(estimateFee({fee_schedule:disabled},us,'2026-03-02',1,100),null);
 assert.equal(account.fee_schedule.US.length,1);
});
test('NH preview applies fees and defers only provisional unaffordable costs',()=>{
 const row={id:'r',kind:'BUY',accountId:'a',assetId:'s',eventDate:day,quantity:46,price:216000,errors:[]};
 const ctx={[day]:{accounts:[{...account,deposit_krw:10000000,deposit_usd:0}]}};
 let preview=previewNhNotices([row],ctx,[],[{...kr,id:'s'}]);
 assert.equal(preview.balances.a.deposit_krw,62593);
 ctx[day].accounts[0].deposit_krw=9936000;
 preview=previewNhNotices([row],ctx,[],[{...kr,id:'s'}]);
 assert.equal(preview.balances.a.deposit_krw,0);assert.equal(preview.fees[0].deferred,true);
 assert.deepEqual(preview.errors,[]);
});
test('an older backend cannot silently drop configured automatic fees',async()=>{
 await assert.rejects(requireFeeProtocol({getBookkeepingCapabilities:async()=>({bookkeeping_protocol:1})},[account]),/백엔드/);
 await requireFeeProtocol({getBookkeepingCapabilities:async()=>({account_fees_protocol:1})},[account]);
 await requireFeeProtocol({},[{}]);
});
