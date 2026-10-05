import test from 'node:test';
import assert from 'node:assert/strict';
import { parseNamuhMessages, resolveNamuhDraft, validateNamuhDraft, appendNamuhRows } from '../src/utils/namuhMessage.js';

const message = `[NH투자증권]퇴직연금 매수 주문체결 알림
계좌번호 : 212-03-52**** 테스트
종 목 명 : ACE 미국10년국채액티브
종목코드 : 0085P0
체결종류 : 매수 전량 체결
체결수량 : 1주
체결단가 : 9,320 원(체결평균단가)
주문번호 : 42954`;
const accounts = [{ id: 'acc', account_no: '212-03-521234', portfolio_id: 'p' }];
const assets = [{ id: 'asset', ticker: '0085P0', market: 'KR', allowed_accounts: ['acc'], portfolio_id: 'p' }];
const parse = text => parseNamuhMessages(text)[0];
const draft = text => resolveNamuhDraft(parse(text), accounts, assets, 'p');
const validate = (d, pending = [], saved = []) => validateNamuhDraft(d, '2026-10-05', accounts, assets, 'p', pending, saved);

test('observed masked retirement full-buy message preserves actual price and alphanumeric ticker', () => {
  const d = draft(message);
  assert.deepEqual(d.errors, []);
  assert.equal(d.accountId, 'acc'); assert.equal(d.assetId, 'asset');
  assert.equal(d.quantity, 1); assert.equal(d.price, 9320); assert.equal(d.brokerOrderNo, '42954');
  assert.equal(d.messageDate, ''); assert.equal(d.accountMask, '2120352****');
  assert.deepEqual(validate(d).errors, []);
});
test('handles copied CRLF, wrapped labels/names and full width colon', () => {
  const d = draft(message.replaceAll('\n','\r\n').replace('종목코드 :', '종 목 코 드：').replace('액티브','액티\r\n브'));
  assert.deepEqual(d.errors, []); assert.equal(d.price, 9320);
});
test('repeat import appends rows without replacing manual entries or using live prices', () => {
  const manual = { id:'manual', accountId:'acc', assetId:'asset', quantity:3, price:10000 };
  const a = appendNamuhRows([manual], [draft(message)], '2026-10-05', () => 'one');
  const b = appendNamuhRows(a, [draft(message.replace('42954','42955'))], '2026-10-05', () => 'two');
  assert.equal(b.length, 3); assert.equal(b[0], manual); assert.equal(b[1].price, 9320); assert.equal(b[2].brokerOrderNo,'42955');
  assert.equal(b[1].importDate, '2026-10-05');
});
test('removes initial empty placeholder and splits several complete messages', () => {
  assert.equal(parseNamuhMessages(message+'\n\n'+message.replace('42954','42955')).length,2);
  assert.equal(appendNamuhRows([{id:'empty',quantity:0,price:0,assetId:''}], [draft(message)], '2026-10-05', ()=>'one').length,1);
});
test('rejects sell, partial, USD prices, zero quantity, missing order and wrong code', () => {
  for (const text of [message.replaceAll('매수','매도'), message.replace('전량','일부'), message.replace('9,320 원','9.32 USD'), message.replace('1주','0주'), message.replace('주문번호 : 42954',''), message.replace('0085P0','VT')])
    assert.ok(parse(text).errors.length, text);
});
test('rejects malformed comma grouping instead of silently changing the amount', () => {
  for (const price of ['9,,320', '93,20', ',9320']) assert.ok(parse(message.replace('9,320', price)).errors.length);
  assert.ok(parse(message.replace('1주', '1,,000주')).errors.length);
  assert.equal(parse(message.replace('1주', '1,000주')).quantity, 1000);
  assert.equal(parse(message.replace('9,320', '9320')).price, 9320);
});
test('ambiguous and cross portfolio accounts are never automatically selected', () => {
  const p = parse(message);
  assert.equal(resolveNamuhDraft(p, [...accounts, {id:'other',account_no:'21203525678',portfolio_id:'p'}], assets,'p').accountId,'');
  assert.equal(resolveNamuhDraft(p, accounts, assets,'other').accountId,'');
  assert.equal(resolveNamuhDraft(p, accounts, assets,'other').assetId,'');
});
test('unknown assets and disallowed accounts require correction', () => {
  assert.ok(validate({...draft(message),assetId:''}).errors.length);
  assert.ok(validateNamuhDraft(draft(message),'2026-10-05',accounts,[{...assets[0],allowed_accounts:[]}],'p',[],[]).errors.length);
});
test('duplicate pending or saved order is rejected, ordinary identical trade warns only', () => {
  const d = draft(message); const rows = appendNamuhRows([], [d], '2026-10-05', ()=>'one');
  assert.ok(validate(d, rows).errors.some(e=>e.includes('입력 대기')));
  assert.throws(()=>appendNamuhRows(rows,[d],'2026-10-05'), /중복/);
  const saved = [{ account_id:'acc', asset_id:'asset',trade_type:'BUY',trade_date:'2026-10-05',quantity:1,price:9320 }];
  assert.equal(validate(d, [],saved).manualDuplicate,true); assert.deepEqual(validate(d,[],saved).errors,[]);
  assert.ok(validate(d,[],[{...saved[0],import_source:'NAMUH_KAKAO',broker_order_no:'42954'}]).errors.some(e=>e.includes('장부')));
});
test('explicit dates are validated and cannot be imported into another day', () => {
  assert.equal(draft(message+'\n체결일자 : 2026.10.04').messageDate,'2026-10-04');
  assert.ok(validate(draft(message+'\n체결일자 : 2026.10.04')).errors.some(e=>e.includes('체결일자')));
  for (const date of ['2026-02-30','2026-99-99','nonsense']) assert.ok(parse(message+'\n체결일자 : '+date).errors.length);
});
