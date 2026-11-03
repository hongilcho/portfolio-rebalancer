import test from 'node:test';
import assert from 'node:assert/strict';
import {parseNhNotifications,resolveNhNotice,noticeApiRow,previewNhNotices,validateNhNotice,readNoticeDraft,writeNoticeDraft} from '../src/utils/nhNotices.js';
import {chosenDividendDate} from '../src/utils/nhDividends.js';
const ordinary=`[NH투자증권] 분배금 입금 안내
2050228***8 조*일 님 계좌로 분배금 입금 안내 드립니다.
1. 종목명 : 미래에셋 TIGER 미국배당다우존스증권상장지수투자신탁(주식)
2. 기준일 : 2026.10.30
3. 세전금액 : 4,025원
  세후금액 :4,025원
  세금합계 : 0원
4. 입금일: 2026.11.03
자세한 내용은 관리 영업점(8:00~17:00)로 문의주시기 바랍니다.
나무: https://link.mynamuh.com/mkrj06`;
const pension=`[NH투자증권]퇴직연금 분배금 입금안내
계좌번호 : 212-03-52***1
조*일님 계좌로 분배금 입금안내 드립니다.
1. 종목명 : ACE 미국30년국채액티브
2. 기준일 : 2026-10-30
3. 분배금 : 4,433원
4. 입금일 : 2026-11-03
※퇴직연금DC/IRP상담:☎1544-6060`;
const accounts=[{id:'isa',account_no:'20502280008',portfolio_id:'p'},{id:'irp',account_no:'21203520001',portfolio_id:'p'}];
const assets=[{id:'tiger',name:'TIGER 미국배당다우존스',ticker:'QA1',market:'KR',portfolio_id:'p'},{id:'ace',name:'ACE 미국30년국채액티브',ticker:'QA2',market:'KR',portfolio_id:'p'}];
const resolve=text=>resolveNhNotice(parseNhNotifications(text,'2026-11-03')[0],accounts,assets,'p');
const ctx={accounts:accounts.map(a=>({...a,deposit_krw:0,deposit_usd:0})),dividend_events:[{asset_id:'tiger',ex_date:'2026-10-29',amount_per_share:40.2}],notices:[]};

test('both supplied formats preserve payment date, reference date and actual net amount',()=>{
 const rows=parseNhNotifications(ordinary+'\n'+pension,'2026-11-03');
 assert.deepEqual(rows.map(r=>r.kind),['DIVIDEND','DIVIDEND']);assert.ok(rows.every(r=>r.errors.length===0));
 assert.deepEqual(rows.map(r=>r.krwAmount),[4025,4433]);assert.equal(rows[0].grossAmount,4025);assert.equal(rows[0].taxAmount,0);
 assert.equal(rows[1].grossAmount,null);assert.equal(rows[1].taxAmount,null);assert.ok(rows.every(r=>r.referenceDate==='2026-10-30'&&r.eventDate==='2026-11-03'));
});
test('masked accounts and long legal fund name resolve uniquely without crossing portfolios',()=>{
 assert.equal(resolve(ordinary).accountId,'isa');assert.equal(resolve(ordinary).assetId,'tiger');assert.equal(resolve(pension).accountId,'irp');assert.equal(resolve(pension).assetId,'ace');
 assert.equal(resolveNhNotice(parseNhNotifications(ordinary,'2026-11-03')[0],accounts,assets,'other').assetId,'');
 assert.equal(resolveNhNotice(parseNhNotifications(ordinary,'2026-11-03')[0],accounts,[...assets,{...assets[0],id:'other'}],'p').assetId,'');
});
test('bad date, amounts and tax mismatch block review rather than becoming zero',()=>{
 for(const text of [ordinary.replace('2026.10.30','2026.02.30'),ordinary.replace('4,025원','4,000원'),ordinary.replace('세후금액 :4,025원','세후금액 :?원')])assert.ok(parseNhNotifications(text,'2026-11-03')[0].errors.length);
});
test('reference date is never silently substituted for ex date; only one recent candidate is suggested',()=>{
 const row=resolve(ordinary);assert.equal(chosenDividendDate(row,ctx),'2026-10-29');
 assert.equal(chosenDividendDate(row,{}),null);assert.equal(chosenDividendDate(row,{dividend_events:[...ctx.dividend_events,{asset_id:'tiger',ex_date:'2026-10-28'}]}),null);
 assert.equal(chosenDividendDate({...row,dividendExDate:''},ctx),null);
});
test('receipt increases cash once without external flow and stale old negative cash can be corrected',()=>{
 const row={...resolve(ordinary),fingerprint:'a'.repeat(64)};const input={'2026-11-03':ctx};const before=structuredClone(ctx);
 assert.equal(previewNhNotices([row],input).balances.isa.deposit_krw,4025);assert.deepEqual(ctx,before);
 const api=noticeApiRow(row,ctx);assert.equal(api.external,false);assert.equal(api.dividend_ex_date,'2026-10-29');assert.equal(api.reference_date,'2026-10-30');assert.equal(api.gross_amount,4025);
 assert.equal(previewNhNotices([{...row,applyCash:false}],input).balances.isa.deposit_krw,0);
 const negative={...ctx,accounts:ctx.accounts.map(a=>({...a,deposit_krw:-5000}))};assert.deepEqual(previewNhNotices([row],{'2026-11-03':negative}).errors,[]);
});
test('duplicate event cannot bypass validation with a changed message or explicit duplicate permission',()=>{
 const row={...resolve(ordinary),duplicateConfirmed:true};
 assert.ok(validateNhNotice(row,ctx,accounts,assets,'p',[],[{...row,fingerprint:'other'}]).errors.some(e=>e.includes('基準')||e.includes('기준일')));
 assert.ok(validateNhNotice({...row,eventDate:'2026-11-04'},ctx,accounts,assets,'p',[],[]).errors.length);
});
test('dividend drafts restore without exposing raw notice text in API payload',()=>{
 const row={...resolve(ordinary),id:'d',fingerprint:'a'.repeat(64)};let saved='';const storage={setItem:(_,v)=>saved=v,getItem:()=>saved,removeItem:()=>saved=''};
 assert.equal(writeNoticeDraft('p',{rows:[row]},storage),true);assert.equal(readNoticeDraft('p',storage).rows[0].kind,'DIVIDEND');
 assert.equal('raw' in noticeApiRow(row,ctx),false);
});
