import test from 'node:test';
import assert from 'node:assert/strict';
import {tradeFormLookups,updateTradeRow} from '../src/utils/tradeForm.js';
const assets=[{id:'kr',market:'KR',allowed_accounts:['a','a']},{id:'us',market:'US',allowed_accounts:['a']}];
const context={assets,usdPriceMap:{us:101.5},priceMap:{kr:9320,us:140000},usdKrw:1400};
const row={id:'r',accountId:'a',assetId:'kr',quantity:2,price:9000,exchangeRate:1300,costsConfirmed:true,feesKrw:10,feesUsd:1,importSource:'NAMUH_KAKAO'};
test('untouched rows preserve identity and ordinary numeric edits preserve price, rate, source and explicit fees',()=>{
 assert.equal(updateTradeRow(row,'other','quantity',3,context),row);
 const next=updateTradeRow(row,'r','quantity',0,context);assert.deepEqual(next,{...row,quantity:0});assert.equal(row.quantity,2);
});
test('both directions use the same native/default price and preserve the user exchange rate',()=>{
 assert.deepEqual(updateTradeRow(row,'r','assetId','us',context),{...row,assetId:'us',price:101.5,costsConfirmed:false,feesKrw:0,feesUsd:0});
 const fallback=updateTradeRow({...row,exchangeRate:0},'r','assetId','us',{...context,usdPriceMap:{}});
 assert.equal(fallback.price,100);assert.equal(fallback.exchangeRate,1400);
 const domestic=updateTradeRow(row,'r','assetId','kr',context);assert.equal(domestic.price,9320);assert.equal(domestic.exchangeRate,1);
});
test('account change clears only the existing fee confirmation fields without silently changing the selected asset',()=>{
 assert.deepEqual(updateTradeRow(row,'r','accountId','b',context),{...row,accountId:'b',costsConfirmed:false,feesKrw:0,feesUsd:0});
});
test('form indexes preserve first match and asset order and do not duplicate repeated allowed accounts',()=>{
 const lookup=tradeFormLookups([...assets,{...assets[1],name:'later duplicate'}],[{id:'a',name:'first'},{id:'a',name:'last'}],[{account_id:'a',average_rate:1300},{account_id:'a',average_rate:1400}]);
 assert.equal(lookup.accounts.get('a').name,'first');assert.equal(lookup.assets.get('us'),assets[1]);assert.equal(lookup.ledgers.get('a').average_rate,1300);
 assert.deepEqual(lookup.allowedByAccount.get('a').map(a=>a.id),['kr','us','us']);
});
