import test from 'node:test';
import assert from 'node:assert/strict';
import {dividendGroups} from '../src/utils/dividendDetails.js';
test('keeps account and currency boundaries, original dates and computed/reflected amounts separate',()=>{
  const accounts=[{id:'a',account_alias:'ISA',holdings:[{asset_id:'x',asset_name:'ETF',market:'KR',dividend_profit_krw:100,
    dividend_details:[{ex_date:'2026-02-01',net_amount:60},{ex_date:'2026-01-01',net_amount:40}]}]},
    {id:'b',holdings:[{asset_id:'x',market:'US',dividend_profit_usd:8,dividend_details:[{ex_date:'2026-02-01',net_amount:5}]}]}];
  const [kr,us]=dividendGroups(accounts); assert.equal(kr.calculated,100); assert.equal(kr.adjusted,false);
  assert.equal(kr.details[0].ex_date,'2026-01-01'); assert.equal(accounts[0].holdings[0].dividend_details[0].ex_date,'2026-02-01');
  assert.equal(us.currency,'USD'); assert.equal(us.adjusted,true); assert.equal(us.reflected,8);
});
test('manual adjustment without detail remains visible, deposits and no-dividend holdings are excluded',()=>{
  const result=dividendGroups([{id:'a',holdings:[{asset_id:'x',dividend_profit_krw:100}, {asset_id:'y',is_deposit:true,dividend_profit_krw:50}, {asset_id:'z'}]}]);
  assert.equal(result.length,1); assert.equal(result[0].calculated,0); assert.equal(result[0].adjusted,true);
});
