import React, { useState } from 'react';
import { api } from '../../utils/api';
import { parseNamuhMessages, resolveNamuhDraft, validateNamuhDraft } from '../../utils/namuhMessage';

export default function NamuhMessageImport({ accounts, assets, portfolioId, tradeDate, buyRows, onAppend, disabled }) {
  const [open, setOpen] = useState(false);
  const [text, setText] = useState('');
  const [drafts, setDrafts] = useState([]);
  const [saved, setSaved] = useState([]);
  const [checkedDate, setCheckedDate] = useState('');
  const [confirmedDate, setConfirmedDate] = useState('');
  const [acknowledged, setAcknowledged] = useState([]);
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');
  const scopedAccounts = accounts.filter(a => !a.portfolio_id || String(a.portfolio_id) === String(portfolioId));
  const scopedAssets = assets.filter(a => !a.portfolio_id || String(a.portfolio_id) === String(portfolioId));
  const analyse = async () => {
    setMessage(''); setDrafts([]); setConfirmedDate(''); setAcknowledged([]);
    const parsed = parseNamuhMessages(text);
    if (!parsed.length) { setMessage('체결 메시지를 붙여넣어주세요.'); return; }
    setLoading(true);
    try {
      const result = await api.getTrades({ portfolio_id: portfolioId, start_date: tradeDate, end_date: tradeDate });
      setSaved(result.trades || []);
      setCheckedDate(tradeDate);
      setDrafts(parsed.map(p => resolveNamuhDraft(p, accounts, assets, portfolioId)));
    } catch { setMessage('기존 거래를 조회하지 못했습니다. 중복 확인을 위해 다시 시도해주세요.'); }
    finally { setLoading(false); }
  };
  const update = (i, key, value) => {
    setDrafts(prev => prev.map((d, index) => index === i ? { ...d, [key]: value } : d));
    setAcknowledged([]);
  };
  const checks = drafts.map(d => validateNamuhDraft(d, tradeDate, accounts, assets, portfolioId, buyRows, saved));
  const duplicateOrders = drafts.some((d, i) => d.accountId && drafts.some((other, j) => j < i && other.accountId === d.accountId && other.brokerOrderNo === d.brokerOrderNo));
  const ready = drafts.length > 0 && checkedDate === tradeDate && confirmedDate === tradeDate && !duplicateOrders
    && checks.every((c, i) => !c.errors.length && (!c.manualDuplicate || acknowledged.includes(i)));
  const append = () => {
    if (!ready) return;
    try {
      onAppend(drafts);
      setMessage(`${drafts.length}건을 매수 입력란에 추가했습니다. 장부 반영은 아래 일괄 저장 버튼으로 결정하세요.`);
      setText(''); setDrafts([]); setConfirmedDate(''); setAcknowledged([]);
    } catch (error) { setMessage(error.message); }
  };
  return <div className="section-card">
    <button type="button" className="btn btn-secondary" aria-expanded={open} onClick={() => setOpen(!open)}>카카오톡 체결 메시지 가져오기 {open ? '접기' : '열기'}</button>
    {open && <div style={{ marginTop: 12 }} inert={disabled || loading || undefined}>
      <p>NH투자증권 국내 주식·ETF 매수 전량 체결 알림을 붙여넣으세요. 여러 건을 붙이거나 반복해서 가져올 수 있습니다. 추가한 행은 일괄 저장 전까지 장부에 반영되지 않습니다.</p>
      <label>체결 메시지<textarea aria-label="체결 메시지" className="input-text" rows={8} maxLength={30000} style={{ width: '100%', boxSizing: 'border-box' }} value={text} onChange={e => { setText(e.target.value); setDrafts([]); setMessage(''); }} /></label>
      <button type="button" className="btn btn-secondary" onClick={analyse}>{loading ? '기존 거래 확인 중…' : '내용 확인'}</button>
      {checkedDate !== tradeDate && drafts.length > 0 && <p role="alert">체결일이 바뀌었습니다. 내용 확인을 다시 눌러주세요.</p>}
      {drafts.map((d, i) => <div className="trade-row-card" key={i} style={{ marginTop: 12 }}>
        <b>{i + 1}. {d.assetName || d.ticker} · 주문 {d.brokerOrderNo || '확인 불가'}</b>
        <p>메시지 계좌 {d.accountMask} · 매수 {Number.isFinite(d.quantity) ? d.quantity : '?'}주 · 체결단가 {Number.isFinite(d.price) ? d.price.toLocaleString('ko-KR') : '?'}원</p>
        <label>가져올 계좌<select aria-label={`메시지 ${i + 1} 계좌`} className="input-select" value={d.accountId} onChange={e => update(i, 'accountId', e.target.value)}><option value="">계좌 선택</option>{scopedAccounts.map(a => <option key={a.id} value={a.id}>[{a.account_type}] {a.account_alias}</option>)}</select></label>
        {d.accountWarning && <p>{d.accountWarning}</p>}
        <label>가져올 종목<select aria-label={`메시지 ${i + 1} 종목`} className="input-select" value={d.assetId} onChange={e => update(i, 'assetId', e.target.value)}><option value="">종목 선택</option>{scopedAssets.filter(a => a.market === 'KR' && !a.is_deposit && String(a.ticker).toUpperCase() === d.ticker).map(a => <option key={a.id} value={a.id}>{a.name} ({a.ticker})</option>)}</select></label>
        {!d.messageDate && <p>메시지에 체결일자가 없습니다. 화면에서 선택한 {tradeDate}로 가져옵니다.</p>}
        {checks[i].errors.map(error => <p role="alert" key={error}>{error}</p>)}
        {checks[i].manualDuplicate && !checks[i].errors.length && <label><input type="checkbox" checked={acknowledged.includes(i)} onChange={e => setAcknowledged(prev => e.target.checked ? [...prev, i] : prev.filter(n => n !== i))} />동일한 계좌·종목·수량·단가 기록이 있습니다. 별도 매수임을 확인했습니다.</label>}
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => { setDrafts(prev => prev.filter((_, index) => index !== i)); setAcknowledged([]); }}>이번 가져오기에서 제외</button>
      </div>)}
      {duplicateOrders && <p role="alert">이번 메시지에 같은 계좌의 주문번호가 중복됩니다. 중복된 메시지를 제외해주세요.</p>}
      {drafts.length > 0 && <><label style={{ display: 'block', margin: '12px 0' }}><input type="checkbox" checked={confirmedDate === tradeDate} onChange={e => setConfirmedDate(e.target.checked ? tradeDate : '')} />체결일 {tradeDate}와 가져올 계좌·내용을 확인했습니다.</label><button type="button" className="btn btn-primary" disabled={!ready} onClick={append}>매수 입력란에 {drafts.length}건 추가</button></>}
      {message && <p role="status">{message}</p>}
    </div>}
  </div>;
}
