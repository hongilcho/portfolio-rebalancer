import test from 'node:test';
import assert from 'node:assert/strict';
import {parseNhNotifications,resolveNhNotice,validateNhNotice,noticeApiRow,previewNhNotices,chosenFlow,readNoticeDraft,writeNoticeDraft} from '../src/utils/nhNotices.js';

const deposit=`[NH투자증권] 입금안내
금액 960,000원
[10/08 10:36]
계좌번호 123-45-67***1
테스트은행 사용자`;
const exchange=`[NH투자증권] 환전내역 안내
환전일자 : 10월 08일
계좌명 : 테*트
환전구분 : 외화매수
통화명 : USD
우대율 : 100%
환율 : 1,338.33
외화금액 : USD 717.31
원화금액 : 959,997`;
const buy=`[NH투자증권] 매수 주문체결 알림
종목명 : ACE 미국10년국채액티브
종목코드 : 0085P0
체결종류 : 매수 전량 체결
체결수량 : 20주
체결단가 : 9,320 원(체결평균단가)
주문번호 : 42954`;
const accounts=[{id:'acc',account_no:'12345671231',portfolio_id:'p'}];
const assets=[{id:'asset',ticker:'0085P0',market:'KR',portfolio_id:'p',allowed_accounts:['acc']}];
const context={accounts:[{id:'acc',deposit_krw:4,deposit_usd:10}],flows:[{id:'old',account_id:'acc',event_date:'2026-10-08',amount_krw:960000,currency:'KRW',voided:false}],trades:[],notices:[],exchanges:[]};
const resolve=(text)=>resolveNhNotice(parseNhNotifications(text,'2026-10-08')[0],accounts,assets,'p');

test('given deposit and exchange formats retain real amounts, unknown exchange time and quoted rate',()=>{
  const rows=parseNhNotifications(deposit+'\n-------------\n'+exchange,'2026-10-08');
  assert.deepEqual(rows.map(r=>r.kind),['DEPOSIT','EXCHANGE_IN']);
  assert.ok(rows.every(r=>r.errors.length===0));
  assert.equal(rows[0].krwAmount,960000);assert.equal(rows[0].occurredAt,'2026-10-08T10:36:00+09:00');
  assert.equal(rows[1].usdAmount,717.31);assert.equal(rows[1].krwAmount,959997);assert.equal(rows[1].quotedRate,1338.33);
  assert.equal(rows[1].occurredAt,null);
});
test('missing buy account is correctable by manual selection without clearing other safety checks',()=>{
  const row=resolve(buy);
  assert.equal(row.accountId,'');assert.deepEqual(row.errors,[]);
  assert.ok(validateNhNotice(row,context,accounts,assets,'p',[],[]).errors.includes('계좌를 선택해주세요.'));
  row.accountId='acc';
  assert.deepEqual(validateNhNotice(row,context,accounts,assets,'p',[],[]).errors,[]);
  const invalid=resolve(buy.replace('매수 전량','매수 일부'));invalid.accountId='acc';
  assert.ok(validateNhNotice(invalid,context,accounts,assets,'p',[],[]).errors.length);
});
test('account matching cannot cross portfolios or silently choose an ambiguous mask',()=>{
  assert.equal(resolve(deposit).accountId,'acc');
  assert.equal(resolveNhNotice(parseNhNotifications(deposit,'2026-10-08')[0],accounts,assets,'other').accountId,'');
  assert.equal(resolveNhNotice(parseNhNotifications(deposit,'2026-10-08')[0],[...accounts,{...accounts[0],id:'second'}],assets,'p').accountId,'');
});
test('existing flow is linked, deposit precedes exchange, and average cost uses actual spend',()=>{
  const d={...resolve(deposit),fingerprint:'a'.repeat(64)};
  const e={...resolveNhNotice(parseNhNotifications(exchange,'2026-10-08')[0],accounts,assets,'p',[d]),fingerprint:'b'.repeat(64)};
  assert.equal(e.accountId,'acc');assert.match(e.accountWarning,/추천/);
  assert.equal(chosenFlow(d,context),'old');assert.equal(noticeApiRow(d,context).existing_flow_id,'old');
  assert.equal(noticeApiRow(e,context).occurred_at,null);
  const preview=previewNhNotices([d,e],{'2026-10-08':context},[{account_id:'acc',usd_balance:10,cost_krw:13000,last_event_date:'2026-10-05',needs_reconciliation:false}]);
  assert.equal(preview.balances.acc.deposit_krw,7);assert.equal(preview.balances.acc.deposit_usd,727.31);
  assert.equal(preview.costs.acc.cost,972997);assert.deepEqual(preview.errors,[]);
  assert.equal(preview.expected.acc.deposit_krw,4);
  assert.ok(previewNhNotices([e,d],{'2026-10-08':context},[]).errors.length);
});
test('already reflected cash is not added again, and handled flows block duplicate linking',()=>{
  const row={...resolve(deposit),applyCash:false};
  assert.equal(previewNhNotices([row],{'2026-10-08':context}).balances.acc.deposit_krw,4);
  const handled={...context,flows:[{...context.flows[0],cash_handled:true}]};
  assert.ok(validateNhNotice(row,handled,accounts,assets,'p',[],[]).errors.some(e=>e.includes('이미')));
});
test('duplicate notifications and exchange amounts warn, exact buy orders remain blocked',()=>{
  const row={...resolve(exchange),accountId:'acc',fingerprint:'b'.repeat(64)};
  const ctx={...context,exchanges:[{account_id:'acc',usd_amount:717.31,krw_amount:959997}]};
  assert.equal(validateNhNotice(row,ctx,accounts,assets,'p',[],[]).duplicate,true);
  assert.deepEqual(validateNhNotice({...row,duplicateConfirmed:true},ctx,accounts,assets,'p',[],[]).errors,[]);
  const bought={...resolve(buy),accountId:'acc'};
  assert.ok(validateNhNotice(bought,{...context,trades:[{account_id:'acc',trade_date:'2026-10-08',import_source:'NAMUH_KAKAO',broker_order_no:'42954'}]},accounts,assets,'p',[],[]).errors.length);
});
test('bad amounts, unsupported currencies/directions and impossible calendar dates are rejected',()=>{
  for(const text of [deposit.replace('960,000','96,00'),exchange.replace('외화매수','외화매도'),exchange.replaceAll('USD','JPY'),exchange.replace('10월 08일','02월 30일')])
    assert.ok(parseNhNotifications(text,'2026-10-08')[0].errors.length);
  const historic=resolve(deposit);historic.eventDate='2025-10-08';
  assert.deepEqual(validateNhNotice(historic,context,accounts,assets,'p',[],[]).errors,[]);
  assert.equal(noticeApiRow(historic,context).occurred_at,'2025-10-08T10:36:00+09:00');
});
test('internal transfer subtracts the source, while external flows can be record-only',()=>{
  const row={...resolve(deposit),external:false,sourceAccountId:'source'};
  const ctx={...context,accounts:[...context.accounts,{id:'source',deposit_krw:960000,deposit_usd:0}]};
  const result=previewNhNotices([row],{'2026-10-08':ctx});
  assert.equal(result.balances.source.deposit_krw,0);assert.equal(result.balances.acc.deposit_krw,960004);
  assert.equal(noticeApiRow(row,ctx).existing_flow_id,null);
});
test('pending exact request survives refresh, is scoped, expires, and empty save clears it',()=>{
  const map=new Map(),storage={getItem:k=>map.get(k),setItem:(k,v)=>map.set(k,v),removeItem:k=>map.delete(k)};
  const data={rows:[{...resolve(deposit),id:'draft-id'}],requestId:'request',pendingPayload:{request_id:'request',rows:[{test:true}]}};
  assert.ok(writeNoticeDraft('p',data,storage));assert.deepEqual(readNoticeDraft('p',storage).pendingPayload,data.pendingPayload);
  assert.equal(readNoticeDraft('other',storage),null);
  writeNoticeDraft('p',{rows:[]},storage);assert.equal(readNoticeDraft('p',storage),null);
});

test('withdrawal parses the transaction amount separately from available withdrawal balance',()=>{
  const withdrawal=`[NH투자증권] 출금안내
금액 1,000,000원
[09/30 13:16]
계좌번호 123-45-67***1
테스트은행 사용자
출금가능금액 : 38,239,177원
----`;
  const r=resolve(withdrawal);
  assert.equal(r.kind,'WITHDRAW');assert.equal(r.krwAmount,1000000);
  assert.equal(r.reportedAvailableKrw,38239177);assert.equal(r.eventDate,'2026-09-30');
  assert.equal(r.occurredAt,'2026-09-30T13:16:00+09:00');assert.equal(r.accountId,'acc');
  assert.deepEqual(r.errors,[]);
  const ctx={...context,accounts:[{id:'acc',deposit_krw:1000004,deposit_usd:10}],flows:[{id:'withdrawn',account_id:'acc',currency:'KRW',event_date:'2026-09-30',amount_krw:-1000000}]};
  assert.equal(chosenFlow(r,ctx),'withdrawn');assert.equal(noticeApiRow(r,ctx).existing_flow_id,'withdrawn');
  assert.equal(previewNhNotices([r],{'2026-09-30':ctx}).balances.acc.deposit_krw,4);
  assert.equal(previewNhNotices([{...r,applyCash:false}],{'2026-09-30':ctx}).balances.acc.deposit_krw,1000004);
});

test('pre-baseline cash messages can be saved as history but cannot change current cash',()=>{
  const r={...resolve(deposit),eventDate:'2026-09-30',messageMonthDay:'09-30',applyCash:false};
  const ctx={...context,flows:[],trackings:{p:{baseline_date:'2026-10-05'}}};
  assert.deepEqual(validateNhNotice(r,ctx,accounts,assets,'p',[],[]).errors,[]);
  assert.ok(validateNhNotice({...r,applyCash:true},ctx,accounts,assets,'p',[],[]).errors.some(e=>e.includes('기준일 이전')));
});

test('cross portfolio withdrawal previews equal and opposite movements and links both flows',()=>{
  const r={kind:'WITHDRAW',accountId:'acc',eventDate:'2026-10-08',destinationAccountId:'peer',external:false,crossPortfolio:true,krwAmount:1000000,applyCash:true,errors:[]};
  const ctx={...context,accounts:[{id:'acc',deposit_krw:1000004,deposit_usd:10}],flows:[{id:'out',account_id:'acc',currency:'KRW',amount_krw:-1000000}],
    transfer_accounts:[...accounts,{id:'peer',portfolio_id:'pool',account_alias:'Pool',deposit_krw:100,deposit_usd:0}],transfer_flows:[{id:'in',account_id:'peer',currency:'KRW',amount_krw:1000000}]};
  assert.deepEqual(validateNhNotice(r,ctx,accounts,assets,'p',[],[]).errors,[]);
  const preview=previewNhNotices([r],{'2026-10-08':ctx});
  assert.equal(preview.balances.acc.deposit_krw,4);assert.equal(preview.balances.peer.deposit_krw,1000100);assert.deepEqual(preview.errors,[]);
  assert.equal(preview.expected.peer.deposit_krw,100);
  const api=noticeApiRow(r,ctx);assert.equal(api.destination_account_id,'peer');assert.equal(api.existing_flow_id,'out');assert.equal(api.counterparty_flow_id,'in');
  assert.ok(validateNhNotice({...r,crossPortfolio:false},ctx,accounts,assets,'p',[],[]).errors.length);
  assert.equal(previewNhNotices([{...r,applyCash:false}],{'2026-10-08':ctx}).balances.peer.deposit_krw,100);
});
