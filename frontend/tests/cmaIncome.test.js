import test from 'node:test';
import assert from 'node:assert/strict';
import {cmaIncomeRequest,cmaInitialInterestRequest,cmaStateLabel,cmaCheckAlerts} from '../src/utils/cmaIncome.js';
import {persistPendingRequest,readPendingRequest} from '../src/utils/bookkeepingRequest.js';

test('CMA request only applies confirmed interest delta, never subtracts the recorded withdrawal',()=>{
  const preview={observation_id:'obs',book_token:'a'.repeat(64),book_krw:'4800000',broker_krw:'4800123',interest_krw:'123'};
  const request=cmaIncomeRequest('cma',preview,true,'request-123');
  assert.equal(request.interest_krw,'123');assert.equal(request.confirmed_movements,true);
  assert.equal('withdrawal' in request,false);assert.equal('automatic' in request,false);
});
test('missing confirmation, zero and invalid interest cannot become a write',()=>{
  for(const value of ['0','-200000','NaN'])assert.throws(()=>cmaIncomeRequest('cma',{observation_id:'obs',book_token:'x',interest_krw:value},true,'request-123'));
  assert.throws(()=>cmaIncomeRequest('cma',{observation_id:'obs',book_token:'x',interest_krw:'123'},false,'request-123'));
  assert.throws(()=>cmaIncomeRequest('cma',{observation_id:'obs',book_token:'x',interest_krw:'123',can_apply:false},true,'request-123'));
});
test('exact pending CMA request survives reload without generating a second income request',()=>{
  const map=new Map(),storage={getItem:k=>map.get(k),setItem:(k,v)=>map.set(k,v)};
  const payload={request_id:'request-123',observation_id:'obs',interest_krw:'123'};
  persistPendingRequest('cma/p',{payload},storage);
  assert.deepEqual(readPendingRequest('cma/p',storage).payload,payload);
});

test('initial request posts only the prior interest and requires separate acknowledgment',()=>{
  const p={observation_id:'o',book_token:'a'.repeat(64),status:'INITIAL_BALANCE_REVIEW',
    interest_krw:'37810',paid_interest_krw:'2355',prior_difference_krw:'35455'};
  const req=cmaInitialInterestRequest('cma',p,true,'입출금을 대조했고 이전 차액은 누적 이자입니다.','initial-id');
  assert.equal(req.initial_interest_krw,'35455');assert.equal('interest_krw' in req,false);
  assert.equal('event_date' in req,false);assert.equal(req.confirmed_initial_interest,true);
  assert.throws(()=>cmaInitialInterestRequest('cma',p,false,'입출금과 이전 이자를 대조했습니다.','id'));
  assert.throws(()=>cmaInitialInterestRequest('cma',p,true,'짧음','id'));
  assert.throws(()=>cmaInitialInterestRequest('cma',{...p,prior_difference_krw:'-1'},true,'입출금과 이전 이자를 대조했습니다.','id'));
});
test('cash zero and sweep statuses clearly retain the ledger',()=>{
  assert.match(cmaStateLabel('NIGHT_TRANSITION'),/장부 유지/);
  assert.match(cmaStateLabel('ZERO_UNVERIFIED'),/반환 확인 대기/);
  assert.match(cmaStateLabel('CHECK_FAILED_REVIEW'),/반영 이력 확인/);
});

test('daily failures and missing checks are visible, successful or opted-out accounts stay quiet',()=>{
  const now=new Date('2026-10-15T17:00:00+09:00');
  const accounts=[{id:'a',account_alias:'CMA',enabled:true}];
  assert.equal(cmaCheckAlerts({accounts,checks:[]},now).length,1);
  assert.equal(cmaCheckAlerts({accounts:[{...accounts[0],enabled:false}],checks:[]},now).length,0);
  const check={account_id:'a',event_date:'2026-10-15',slot:2,state:'CHECK_FAILED_REVIEW'};
  assert.match(cmaCheckAlerts({accounts,checks:[check]},now)[0],/이력 확인/);
  assert.equal(cmaCheckAlerts({accounts,checks:[{...check,state:'APPLIED'}]},now).length,0);
  assert.equal(cmaCheckAlerts({accounts,checks:[{...check,state:'NO_CHANGE'}]},now).length,0);
});

test('a first pending return has time for a later slot and stale checking is surfaced',()=>{
  const now=new Date('2026-10-15T09:15:00+09:00');
  const accounts=[{id:'a',account_alias:'CMA',enabled:true}],base={account_id:'a',event_date:'2026-10-15',slot:0};
  assert.equal(cmaCheckAlerts({accounts,checks:[{...base,state:'AWAITING_STABLE_RETURN'}]},now).length,0);
  assert.equal(cmaCheckAlerts({accounts,checks:[{...base,state:'CHECKING',updated_at:'2026-10-15T09:00:00+09:00'}]},now).length,1);
});
