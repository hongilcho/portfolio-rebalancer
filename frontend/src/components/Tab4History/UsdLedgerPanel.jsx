import React, { useEffect, useState } from 'react';
import { api } from '../../utils/api';
import { formatKRW, formatUSD } from '../../utils/formatters';
import { resolveUsdAccount } from '../../utils/usdAccountSelection';

const names = { OPENING: '시작 기준 등록', EXCHANGE_IN: '원화 → 달러 환전',
  EXCHANGE_OUT: '달러 → 원화 환전', DEPOSIT: '확인된 달러 입금', WITHDRAW: '달러 출금',
  RECONCILE: '현재 잔고 원가 대사', BUY: '달러 매수', SELL: '달러 매도대금' };
const localNow = () => new Date(Date.now() + 9 * 3600000).toISOString().slice(0, 16);
const rateText = rate => Number(rate || 0).toLocaleString('ko-KR', { minimumFractionDigits: 4, maximumFractionDigits: 4 });

export default function UsdLedgerPanel({ accounts, assets, ledgers, onChanged, portfolioId, focused=false,active=true,onBusyChange,disabled=false }) {
  const [open, setOpen] = useState(focused);
  const [accountId, setAccountId] = useState(String(accounts.find(a => Number(a.deposit_usd) > 0)?.id || accounts[0]?.id || ''));
  const [kind, setKind] = useState('EXCHANGE_IN');
  const [occurredAt, setOccurredAt] = useState(localNow);
  const [usd, setUsd] = useState('');
  const [krw, setKrw] = useState('');
  const [rate, setRate] = useState('');
  const [notes, setNotes] = useState('');
  const [events, setEvents] = useState([]);
  const [eventsError, setEventsError] = useState('');
  const [eventsLoading, setEventsLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const locked=saving || disabled;
  const [message, setMessage] = useState('');
  useEffect(()=>{onBusyChange?.(saving);},[saving,onBusyChange]);
  const { accounts: scopedAccounts, account } = resolveUsdAccount(accounts, accountId, portfolioId);
  const activeAccountId = String(account?.id || '');
  const ledger = ledgers.find(s => String(s.account_id) === activeAccountId);
  const effectiveKind = ledger ? kind : 'OPENING';
  const usesAmounts = ['EXCHANGE_IN', 'EXCHANGE_OUT', 'DEPOSIT', 'WITHDRAW'].includes(effectiveKind);
  const exchange = ['EXCHANGE_IN', 'EXCHANGE_OUT'].includes(effectiveKind);
  const usesRate = ['OPENING', 'RECONCILE', 'DEPOSIT'].includes(effectiveKind);
  const visibleEvents = events.filter(e => String(e.account_id) === activeAccountId);
  const latest = visibleEvents.find(e => !e.reversed_at);

  useEffect(() => {
    setUsd(''); setKrw(''); setRate(''); setNotes(''); setMessage('');
  }, [activeAccountId]);

  useEffect(() => {
    let cancelled = false;
    setEvents([]);
    setEventsError('');
    if (!open || !activeAccountId || focused || !active) { setEventsLoading(false); return; }
    setEventsLoading(true);
    api.getUsdEvents(activeAccountId).then(res => {
      if (!cancelled) setEvents(res.events);
    }).catch(error => { if (!cancelled) setEventsError(error.message); })
      .finally(() => { if (!cancelled) setEventsLoading(false); });
    return () => { cancelled = true; };
  }, [open, activeAccountId, ledgers,focused,active]);

  const submit = async e => {
    e.preventDefault();
    if (!activeAccountId) return;
    setSaving(true);
    setMessage('');
    let recorded = false;
    try {
      await api.recordUsdEvent(activeAccountId, { kind: effectiveKind, occurred_at: `${occurredAt}:00+09:00`,
        usd_amount: Number(usd), krw_amount: Number(krw), rate: Number(rate), notes });
      recorded = true;
      setUsd(''); setKrw(''); setRate(''); setNotes('');
      await onChanged();
      setMessage('저장했습니다. 환전 후 달러 평균 취득환율이 매수에 적용됩니다.');
    } catch (error) { setMessage(recorded ? `저장은 완료됐지만 화면 갱신에 실패했습니다. 다시 등록하지 말고 새로고침해주세요. ${error.message}` : error.message); }
    finally { setSaving(false); }
  };
  const undo = async () => {
    if (!latest) return;
    setSaving(true);
    try {
      await api.undoUsdEvent(activeAccountId, latest.id);
      await onChanged();
      setMessage('가장 최근 기록을 취소했습니다. 취소 이력은 보존됩니다.');
    } catch (error) { setMessage(error.message); }
    finally { setSaving(false); }
  };

  return <section className={`section-card ${focused?'history-focused':''}`}>
    {focused?<div className="history-section-heading"><h3>달러 원가·환전 관리</h3><span className="history-muted">현재 잔고와 원가 기준</span></div>:<button type="button" className="btn btn-secondary" aria-expanded={open} onClick={() => setOpen(!open)}>
      💵 달러 원가·환전 관리 {open ? '접기' : '열기'}
    </button>}
    {open && <div style={{ marginTop: 16 }}>
      <p style={{ color: 'var(--text-secondary)' }}>계좌별 시작 잔액과 기준환율을 등록하면 이후 달러 매수에 평균 취득환율을 자동 적용합니다. 기존 보유분의 원가는 유지합니다.</p>
      <label>계좌 <select className="input-select" value={activeAccountId} disabled={locked} onChange={e => { setAccountId(e.target.value); setUsd(''); setKrw(''); setRate(''); setNotes(''); setMessage(''); }}>
        {scopedAccounts.map(a => <option key={a.id} value={a.id}>{a.account_alias} ({a.account_no})</option>)}
      </select></label>
      {ledger ? <div style={{ margin: '14px 0' }}>
        기록상 달러 <b>{formatUSD(ledger.usd_balance)}</b> · 평균 취득환율 <b>{rateText(ledger.average_rate)} 원</b>/달러
        <div>현재 계좌 달러 {formatUSD(ledger.actual_usd)} · 원화 취득원가 {formatKRW(ledger.cost_krw)}</div>
        {ledger.needs_reconciliation && <p role="alert" style={{ color: 'var(--color-loss)' }}>잔고 차이 {formatUSD(ledger.balance_difference)}: 실제 입출금을 확인한 뒤 ‘장부 확인 및 정정’에서 실제 잔고와 확인한 평균 취득환율을 등록해주세요. 대사 전에는 달러 매수·환전을 진행할 수 없습니다.</p>}
      </div> : <p>시작 달러 잔액: <b>{formatUSD(account?.deposit_usd || 0)}</b>. 마지막 환전환율을 시작 기준환율로 입력해주세요.</p>}
      <form onSubmit={submit}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
          {ledger && <label>기록 종류<br /><select className="input-select" value={kind} disabled={locked} onChange={e => setKind(e.target.value)}>
            {Object.entries(names).filter(([key]) => !['OPENING', 'BUY', 'SELL', 'RECONCILE'].includes(key)).map(([key, name]) => <option key={key} value={key}>{name}</option>)}
          </select></label>}
          <label>실제 일시 (한국시간)<br /><input aria-label="환전 기록 일시" className="input-text" type="datetime-local" required value={occurredAt} disabled={locked} onChange={e => setOccurredAt(e.target.value)} /></label>
          {usesAmounts && <label>달러 금액<br /><input aria-label="환전 달러 금액" className="input-number" type="number" min="0.00000001" step="any" required value={usd} disabled={locked} onChange={e => setUsd(e.target.value)} /></label>}
          {exchange && <label>{kind === 'EXCHANGE_IN' ? '실제 원화 지출액' : '실제 원화 수령액'}<br /><input aria-label="환전 원화 금액" className="input-number" type="number" min="0.01" step="any" required value={krw} disabled={locked} onChange={e => setKrw(e.target.value)} /></label>}
          {usesRate && <label>{effectiveKind === 'DEPOSIT' ? '입금 원가 기준환율' : '시작·대사 기준환율'}<br /><input aria-label="달러 기준환율" className="input-number" type="number" min="0.01" step="any" required value={rate} disabled={locked} onChange={e => setRate(e.target.value)} /></label>}
          <label>메모<br /><input className="input-text" value={notes} maxLength={2000} disabled={locked} onChange={e => setNotes(e.target.value)} /></label>
        </div>
        {exchange && Number(usd) > 0 && <p>이번 환전환율: {(Number(krw) / Number(usd)).toFixed(4)}원/달러. 별도 비용이 있다면 실제 원화 총액에 포함해주세요.</p>}
        {effectiveKind === 'RECONCILE' && <p>현재 계좌 달러 전체의 확인한 평균 취득환율을 등록합니다. 현금 잔액과 종목 원가는 바꾸지 않습니다.</p>}
        {effectiveKind === 'DEPOSIT' && <p>실제 입금 달러 금액이 확인된 경우에만 등록하세요. 배당 추정값은 현금에 자동 반영하지 않습니다. 이미 잔고에 반영된 입금은 중복 등록하지 말고 장부 확인 및 정정을 이용하세요.</p>}
        <details className="history-help"><summary>입력 방법·달러 이체 안내</summary><p style={{ color: 'var(--text-secondary)' }}>같은 날짜는 등록 순서대로 계산합니다. 과거 기록을 고치려면 이후 기록부터 취소하세요. 계좌 간 달러 이동은 출금·입금 양쪽을 기록하고 원가 기준환율을 유지하세요.</p></details>
        <button className="btn btn-primary" type="submit" disabled={locked || !activeAccountId || (ledger?.needs_reconciliation && kind !== 'RECONCILE')}>{saving ? '저장 중…' : names[effectiveKind]}</button>
      </form>
      {message && <p role="status">{message}</p>}
      {!focused && <>{eventsError && <p role="alert">기록 조회 실패: {eventsError}</p>}
      {eventsLoading ? <p>기록 조회 중…</p> : <>
        <button className="btn btn-secondary" type="button" disabled={locked || !latest || ledger?.needs_reconciliation} onClick={undo}>가장 최근 기록 취소</button>
        <div className="table-container" style={{ marginTop: 12 }}><table className="custom-table"><thead><tr><th>일시</th><th>종류·종목</th><th>달러</th><th>원화 기준금액</th><th>적용환율</th><th>처리 후 달러·평균환율</th><th>메모</th></tr></thead><tbody>
          {visibleEvents.map(event => <tr key={event.id} style={{ opacity: event.reversed_at ? .55 : 1 }}>
            <td>{event.occurred_at ? new Date(event.occurred_at).toLocaleString('ko-KR', { timeZone: 'Asia/Seoul' }) : `${event.event_date} (일자 기준)`}</td><td>{names[event.kind]}{event.asset_id ? ` · ${assets.find(a => String(a.id) === event.asset_id)?.ticker || event.asset_id}` : ''}{event.reversed_at ? ' (취소)' : ''}</td>
            <td>{formatUSD(event.usd_amount)}</td><td>{formatKRW(event.krw_amount)}</td><td>{rateText(event.fx_rate)}</td><td>{formatUSD(event.after_state.usd_balance)} · {rateText(Number(event.after_state.usd_balance) > 0 ? Number(event.after_state.cost_krw) / Number(event.after_state.usd_balance) : 0)}</td><td>{event.notes}</td>
          </tr>)}
        </tbody></table></div>
      </>}</>}
    </div>}
  </section>;
}
