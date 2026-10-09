import test from 'node:test';
import assert from 'node:assert/strict';
import {groupHistoryDecisions,correctionInputHint} from '../src/utils/ledgerCorrection.js';
test('shared correction preserves unavailable evidence and supports explicit uncertainty',()=>{
  const history=[{key:'baseline',can_correct:true},{key:'close',can_correct:false}];
  assert.deepEqual(groupHistoryDecisions(history,'ALL'),{baseline:'ERROR',close:'UNKNOWN'});
  assert.deepEqual(groupHistoryDecisions(history,'UNKNOWN'),{baseline:'UNKNOWN',close:'UNKNOWN'});
  assert.deepEqual(groupHistoryDecisions(history,'DETAIL'),{baseline:'UNKNOWN',close:'UNKNOWN'});
});
test('automatic preview waits for necessary inputs and accepts zero target balances',()=>{
  const form={account_id:'qa',event_date:'2026-09-30',reason:'QA correction',kind:'PAST_WITHDRAWAL',amount:1000000};
  assert.equal(correctionInputHint(form),'');
  assert.ok(correctionInputHint({...form,amount:''}));
  assert.ok(correctionInputHint({...form,reason:'a'}));
  assert.equal(correctionInputHint({...form,kind:'CASH',balance:0}),'');
  assert.ok(correctionInputHint({...form,kind:'CASH',balance:''}));
  assert.equal(correctionInputHint({...form,kind:'HOLDING',asset_id:'asset',quantity:0}),'');
});
