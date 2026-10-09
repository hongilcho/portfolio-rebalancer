import test from 'node:test';
import assert from 'node:assert/strict';
import {parseNhNotifications,resolveNhNotice,noticeApiRow} from '../src/utils/nhNotices.js';
import {isHistoricalWithdrawal,withdrawalCorrectionDraft,matchesWithdrawalCorrection,settleCorrectionRows,settleStoredCorrection} from '../src/utils/withdrawalCorrection.js';
const message=`[NH투자증권] 출금안내
금액 1,000,000원
[09/30 13:16]
계좌번호 212-01-52***1
우리은행 황윤아
출금가능금액 : 38,239,177원`;
const accounts=[{id:'cma',portfolio_id:'p',account_no:'212-01-521231',account_alias:'QA CMA'}];
const context={trackings:{p:{baseline_date:'2026-10-05'}}};
const row={...resolveNhNotice(parseNhNotifications(message,'2026-10-09')[0],accounts,[],'p'),id:'notice-1',fingerprint:'a'.repeat(64)};

test('the supplied message transfers its date, selected account and actual withdrawal into a correction draft',()=>{
  assert.equal(row.accountId,'cma');assert.equal(row.eventDate,'2026-09-30');assert.equal(row.krwAmount,1000000);
  const draft=withdrawalCorrectionDraft(row,context,accounts,'p');
  assert.equal(draft.proposal.account_id,'cma');assert.equal(draft.proposal.event_date,'2026-09-30');assert.equal(draft.proposal.amount,1000000);
  assert.equal(draft.proposal.kind,'PAST_WITHDRAWAL');assert.equal(draft.proposal.currency,'KRW');
  assert.equal(draft.source.reportedAvailableKrw,38239177);assert.ok(!Object.hasOwn(draft.proposal,'balance'));
  assert.match(draft.proposal.reason,/13:16/);
});
test('unknown, cross-portfolio and internal accounts never create a correction draft; post-baseline withdrawals keep their ordinary path',()=>{
  assert.equal(withdrawalCorrectionDraft({...row,accountId:''},context,accounts,'p'),null);
  assert.equal(withdrawalCorrectionDraft(row,context,[{...accounts[0],portfolio_id:'other'}],'p'),null);
  assert.equal(withdrawalCorrectionDraft({...row,external:false},context,accounts,'p'),null);
  assert.ok(!isHistoricalWithdrawal({...row,eventDate:'2026-10-09'},context,'p'));
});
test('only the confirmed matching correction removes its source, keeps other pending messages, and can be repeated safely',()=>{
  const draft=withdrawalCorrectionDraft(row,context,accounts,'p');
  const other={...row,id:'notice-2',fingerprint:'b'.repeat(64),krwAmount:2000000};
  const result={source:draft.source,proposal:draft.proposal};
  assert.deepEqual(settleCorrectionRows([row,other],result),[other]);assert.deepEqual(settleCorrectionRows([other],result),[other]);
  assert.equal(matchesWithdrawalCorrection(draft.source,{...draft.proposal,amount:2000000}),false);
  assert.deepEqual(settleCorrectionRows([row],{...result,proposal:{...draft.proposal,account_id:'wrong'}}),[row]);
  assert.deepEqual(settleCorrectionRows([row],{...result,proposal:{...draft.proposal,event_date:'2026-10-01'}}),[row]);
});
test('cancelled correction restores the choice without changing cash or discarding the message',()=>{
  const draft=withdrawalCorrectionDraft(row,context,accounts,'p');
  const next=settleCorrectionRows([{...row,historicalCashChoice:'CORRECTION'}],{source:draft.source,cancelled:true});
  assert.equal(next.length,1);assert.equal(next[0].applyCash,false);assert.equal(next[0].historicalCashChoice,undefined);
});
test('successful correction removes persisted source before reload and never rewrites an uncertain ordinary submission',()=>{
  const draft=withdrawalCorrectionDraft(row,context,accounts,'p');
  const memory=new Map();const storage={getItem:k=>memory.get(k),setItem:(k,v)=>memory.set(k,v),removeItem:k=>memory.delete(k)};
  const key='nh-notice-draft/v1/p';const saved={rows:[row],requestId:'QA-ordinary',savedAt:Date.now()};
  storage.setItem(key,JSON.stringify(saved));
  assert.equal(settleStoredCorrection({source:draft.source,proposal:draft.proposal},storage),true);assert.equal(storage.getItem(key),undefined);
  storage.setItem(key,JSON.stringify({...saved,pendingPayload:{request_id:'QA-unsure'}}));
  assert.equal(settleStoredCorrection({source:draft.source,proposal:draft.proposal},storage),false);assert.equal(JSON.parse(storage.getItem(key)).rows.length,1);
});
test('already-reflected historical withdrawal is recorded with no cash change',()=>{
  const record=noticeApiRow({...row,applyCash:false,historicalCashChoice:'REFLECTED'},context);
  assert.equal(record.apply_cash,false);assert.equal(record.krw_amount,1000000);assert.equal(record.event_date,'2026-09-30');
});
