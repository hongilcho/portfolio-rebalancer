import test from 'node:test';
import assert from 'node:assert/strict';
import { readTradeDraft, writeTradeDraft, remainingTradeRows, draftKey } from '../src/utils/tradeDraft.js';
const row = {id:'one', accountId:'acc', assetId:'ast', quantity:2, price:9320, exchangeRate:1, importSource:'NAMUH_KAKAO', brokerOrderNo:'42954',importDate:'2026-10-05'};
const draft = {tradeDate:'2026-10-05', buyRows:[row], sellRows:[], uncertainSubmission:true};
const memory = () => { const map = new Map(); return {getItem:k=>map.get(k)||null,setItem:(k,v)=>map.set(k,v),removeItem:k=>map.delete(k)}; };
test('local draft restores date, imported identity and uncertain submission only within its portfolio', () => {
  const s = memory(); assert.ok(writeTradeDraft(s,'p',draft));
  assert.deepEqual(readTradeDraft(s,'p').buyRows,[row]); assert.equal(readTradeDraft(s,'p').uncertainSubmission,true);
  assert.equal(readTradeDraft(s,'other'),null);
});
test('expired, corrupt and invalid financial input cannot restore; storage failures are safe', () => {
  const s=memory(); writeTradeDraft(s,'p',draft); assert.equal(readTradeDraft(s,'p',Date.now()+31*86400000),null);
  s.setItem(draftKey('p'),'bad json'); assert.equal(readTradeDraft(s,'p'),null);
  writeTradeDraft(s,'p',{...draft,buyRows:[{...row,price:-1}]}); assert.equal(readTradeDraft(s,'p'),null);
  assert.equal(writeTradeDraft({setItem:()=>{throw Error();}},'p',draft),false);
});
test('partial success removes only confirmed rows and completely saved input clears the persisted draft', () => {
  const failed={...row,id:'two'}; const result=remainingTradeRows([row,failed],[],[row,failed],[{index:0,success:true},{index:1,success:false}]);
  assert.deepEqual(result.buyRows,[failed]); const s=memory(); writeTradeDraft(s,'p',draft);
  writeTradeDraft(s,'p',{...draft,buyRows:[],sellRows:[]}); assert.equal(readTradeDraft(s,'p'),null);
});
