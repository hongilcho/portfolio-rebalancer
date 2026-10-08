// Parse only the observed NH full-buy format. No network or clipboard access.
const normalize = text => String(text || '').normalize('NFKC').replace(/\r\n?/g, '\n').replace(/[\u200b-\u200d\ufeff]/g, '').trim();
const fields = ['계좌번호', '종목명', '종목코드', '체결종류', '체결수량', '체결단가', '주문번호', '체결일자'];
function field(text, label) {
  const next = fields.join('|');
  return text.match(new RegExp(`${label}\\s*[:：]\\s*([\\s\\S]*?)(?=\\n\\s*(?:${next})\\s*[:：]|$)`))?.[1]?.trim() || '';
}
const scope = (items, portfolioId) => items.filter(item => !item.portfolio_id || String(item.portfolio_id) === String(portfolioId));
export const orderKey = (row, date) => row.importSource && row.brokerOrderNo && row.accountId
  ? `${date}|${row.accountId}|${row.brokerOrderNo}` : '';

export function parseNamuhMessages(raw) {
  let text = normalize(raw);
  for (const label of fields) text = text.replace(new RegExp(label.split('').join('\\s*') + '\\s*[:：]', 'g'), `${label}:`);
  if (!text) return [];
  const blocks = text.split(/(?=\[NH투자증권\])/).map(s => s.trim()).filter(Boolean);
  return blocks.map(block => {
    const errors = [];
    const kind = field(block, '체결종류').replace(/\s/g, '');
    if (!block.startsWith('[NH투자증권]') || !/매수주문체결알림/.test(block.replace(/\s/g, '')) || kind !== '매수전량체결')
      errors.push('현재는 NH투자증권 국내 매수 전량 체결 알림만 지원합니다. 부분 체결·매도 알림은 직접 입력해주세요.');
    const accountMask = field(block, '계좌번호').split(/\s/)[0].replace(/[^0-9*]/g, '');
    // Missing account information is corrected by an explicit account selection.
    const ticker = field(block, '종목코드').replace(/\s/g, '').toUpperCase();
    if (!/^[0-9A-Z]{6}$/.test(ticker)) errors.push('국내 종목코드 6자리를 확인해주세요.');
    const quantityText = field(block, '체결수량');
    const priceText = field(block, '체결단가');
    const quantity = /^(?:\d+|\d{1,3}(?:,\d{3})+)\s*주$/.test(quantityText) ? Number(quantityText.replace(/[,\s주]/g, '')) : NaN;
    const price = /^(?:\d+|\d{1,3}(?:,\d{3})+)(?:\.\d+)?\s*원(?:\s*\(체결평균단가\))?$/.test(priceText)
      ? Number(priceText.match(/^[\d,.]+/)[0].replace(/,/g, '')) : NaN;
    if (!Number.isSafeInteger(quantity) || quantity <= 0) errors.push('체결수량을 읽지 못했습니다.');
    if (!Number.isFinite(price) || price <= 0) errors.push('원화 체결단가를 읽지 못했습니다.');
    const brokerOrderNo = field(block, '주문번호');
    if (!/^\d{1,10}$/.test(brokerOrderNo)) errors.push('주문번호를 읽지 못했습니다.');
    const dateText = field(block, '체결일자');
    const date = dateText.replace(/[.\-/\s]/g, '');
    let messageDate = '';
    if (dateText) {
      messageDate = /^\d{8}$/.test(date) ? `${date.slice(0,4)}-${date.slice(4,6)}-${date.slice(6)}` : '';
      const timestamp = Date.parse(`${messageDate}T00:00:00Z`);
      if (!Number.isFinite(timestamp) || new Date(timestamp).toISOString().slice(0,10) !== messageDate) errors.push('체결일자 형식을 확인해주세요.');
    }
    return { ticker, assetName: field(block, '종목명').replace(/\s+/g, ' '), accountMask,
      brokerOrderNo, quantity, price, messageDate, errors };
  });
}

export function resolveNamuhDraft(parsed, accounts, assets, portfolioId) {
  const matches = scope(accounts, portfolioId).filter(account => {
    const number = String(account.account_no || '').replace(/\D/g, '');
    return /^[0-9*]{11}$/.test(parsed.accountMask) && /[0-9]/.test(parsed.accountMask) && number.length === parsed.accountMask.length && [...parsed.accountMask].every((c, i) => c === '*' || c === number[i]);
  });
  const accountId = matches.length === 1 ? String(matches[0].id) : '';
  const candidates = scope(assets, portfolioId).filter(a => a.market === 'KR' && !a.is_deposit && String(a.ticker).toUpperCase() === parsed.ticker);
  return { ...parsed, accountId, assetId: candidates.length === 1 ? String(candidates[0].id) : '',
    accountWarning: matches.length !== 1 ? '계좌를 하나로 확인할 수 없습니다. 직접 선택해주세요.' : '' };
}

export function validateNamuhDraft(draft, date, accounts, assets, portfolioId, pending, saved) {
  const errors = [...draft.errors];
  const account = scope(accounts, portfolioId).find(a => String(a.id) === draft.accountId);
  const asset = scope(assets, portfolioId).find(a => String(a.id) === draft.assetId);
  if (!account) errors.push('계좌를 선택해주세요.');
  if (!asset || asset.market !== 'KR' || asset.is_deposit || String(asset.ticker).toUpperCase() !== draft.ticker)
    errors.push('해당 종목코드의 등록된 국내 종목을 선택해주세요. 종목 등록이 필요하면 자산 관리에서 먼저 등록하세요.');
  if (asset && !(asset.allowed_accounts || []).map(String).includes(draft.accountId)) errors.push('이 계좌에 허용된 종목이 아닙니다.');
  if (draft.messageDate && draft.messageDate !== date) errors.push('메시지의 체결일자가 선택한 체결일과 다릅니다. 다른 날짜의 거래는 따로 가져오세요.');
  const key = orderKey({ ...draft, importSource: 'NAMUH_KAKAO' }, date);
  if (key && pending.some(row => orderKey(row, date) === key)) errors.push('이미 입력 대기 중인 주문입니다.');
  if (saved.some(t => t.import_source === 'NAMUH_KAKAO' && String(t.account_id) === draft.accountId && t.trade_date === date && t.broker_order_no === draft.brokerOrderNo)) errors.push('이미 장부에 저장된 주문입니다.');
  const manualDuplicate = saved.some(t => String(t.account_id) === draft.accountId && String(t.asset_id) === draft.assetId && t.trade_date === date && t.trade_type === 'BUY' && Number(t.quantity) === draft.quantity && Number(t.price) === draft.price)
    || pending.some(r => r.accountId === draft.accountId && r.assetId === draft.assetId && r.quantity === draft.quantity && r.price === draft.price);
  return { errors, manualDuplicate };
}

export function appendNamuhRows(existing, drafts, date, idFactory = () => crypto.randomUUID()) {
  const rows = existing.filter(r => r.assetId || r.quantity || r.price || r.importSource);
  const keys = new Set(rows.map(r => orderKey(r, date)).filter(Boolean));
  for (const draft of drafts) {
    const key = orderKey({ ...draft, importSource: 'NAMUH_KAKAO' }, date);
    if (keys.has(key)) throw new Error('같은 주문이 중복 선택되었습니다.');
    keys.add(key);
    rows.push({ id: idFactory(), accountId: draft.accountId, assetId: draft.assetId, quantity: draft.quantity,
      price: draft.price, exchangeRate: 1, importSource: 'NAMUH_KAKAO', brokerOrderNo: draft.brokerOrderNo, importDate: date });
  }
  return rows;
}
