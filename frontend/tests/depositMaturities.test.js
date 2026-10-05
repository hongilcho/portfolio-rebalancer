import test from 'node:test';
import assert from 'node:assert/strict';
import {depositMaturities} from '../src/utils/depositMaturities.js';
const asset={id:'a',name:'예금',is_deposit:true,start_date:'2025-10-05',maturity_date:'2026-10-05',deposit_principal:1000000,interest_rate:4,tax_rate:15.4};
const account={id:'c',account_alias:'은행',holdings:[{asset_id:'a',is_deposit:true,quantity:1}]};
test('registered maturity estimates preserve existing 365-day interest and flooring policy',()=>{
  const [item]=depositMaturities([asset],[account],'2026-10-05');
  assert.equal(item.daysLeft,0); assert.equal(item.expectedAmount,1033840);
  assert.equal(depositMaturities([asset],[account],'2026-10-06')[0].daysLeft,-1);
});
test('unknown/invalid dates never generate a payout estimate and closed deposits are excluded',()=>{
  assert.equal(depositMaturities([{...asset,maturity_date:'2026-02-30'}],[account])[0].expectedAmount,null);
  assert.equal(depositMaturities([{...asset,start_date:'2027-01-01'}],[account])[0].expectedAmount,null);
  assert.deepEqual(depositMaturities([{...asset,deposit_principal:0}],[account]),[]);
});
test('standalone pure deposits need no holdings and are never counted twice across accounts',()=>{
  assert.equal(depositMaturities([{...asset,account_no:'은행 예금'}],[])[0].account,'은행 예금');
  assert.equal(depositMaturities([asset],[account,{...account,id:'other'}]).length,1);
  assert.equal(depositMaturities([asset],[{...account,holdings:[]}]).length,1);
  assert.deepEqual(depositMaturities([{...asset,is_deposit:false}],[account]),[]);
});
