import {draftStorage} from '../../utils/tradeDraft';
import {executionRows} from '../../utils/investmentInput';
import React, { useEffect, useState, useRef } from 'react';
import { api } from '../../utils/api';
import {readPendingRequest,persistPendingRequest,clearPendingRequest,requireBookkeepingProtocol,singleSubmission} from '../../utils/bookkeepingRequest';
import { formatKRW, formatUSD } from '../../utils/formatters';
import { resolveUsdAccount } from '../../utils/usdAccountSelection';

const names = { OPENING: '시작 기준 등록', EXCHANGE_IN: '원화 → 달러 환전',
  EXCHANGE_OUT: '달러 → 원화 환전', DEPOSIT: '확인된 달러 입금', WITHDRAW: '달러 출금',
  RECONCILE: '현재 잔고 원가 대사', BUY: '달러 매수', SELL: '달러 매도대금' };
const localNow = () => new Date(Date.now() + 9 * 3600000).toISOString().slice(0, 16);
const rateText = rate => Number(rate || 0).toLocaleString('ko-KR', { minimumFractionDigits: 4, maximumFractionDigits: 4 });

export default function UsdLedgerPanel({ accounts, assets, ledgers, flows=[], onChanged, portfolioId, focused=false,active=true,onBusyChange,disabled=false,executionContext=null,inputScope='' }) {
  const storage=draftStorage(inputScope);
  const pendingKey=`manual-forex/v1/${portfolioId}`;
  const submitLock=useRef(false);
  const [pending,setPending]=useState(()=>readPendingRequest(pendingKey,storage));
  const [flowMode,setFlowMode]=useState('EXTERNAL');
  const [flowId,setFlowId]=useState('');
  const [duplicateConfirmed,setDuplicateConfirmed]=useState(false);
  const [open, setOpen] = useState(focused);
  const [accountId, setAccountId] = useState(String(executionContext?.step.account_id || accounts.find(a => Number(a.deposit_usd) > 0)?.id || accounts[0]?.id || ''));
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
  const locked=saving || disabled || Boolean(pending);
  const [message, setMessage] = useState('');
  useEffect(()=>{onBusyChange?.(saving || Boolean(pending),saving);},[saving,pending,onBusyChange]);
  const { accounts: scopedAccounts, account } = resolveUsdAccount(accounts, accountId, portfolioId);
  const activeAccountId = String(account?.id || '');
  const ledger = ledgers.find(s => String(s.account_id) === activeAccountId);
  const effectiveKind = ledger ? kind : 'OPENING';
  const usesAmounts = ['EXCHANGE_IN', 'EXCHANGE_OUT', 'DEPOSIT', 'WITHDRAW'].includes(effectiveKind);
  const exchange = ['EXCHANGE_IN', 'EXCHANGE_OUT'].includes(effectiveKind);
  const usesRate = ['OPENING', 'RECONCILE', 'DEPOSIT','WITHDRAW'].includes(effectiveKind);
  const matchingFlows=flows.filter(f=>!f.voided && String(f.account_id)===activeAccountId && f.currency==='USD'
    && String(f.event_date)===occurredAt.slice(0,10) && Number(f.native_amount)===Number(usd)
    && (Number(f.amount_krw)>0)===(effectiveKind==='DEPOSIT'));
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
    e?.preventDefault();
    return singleSubmission(submitLock,async()=>{

      if (!activeAccountId && !pending) return;
      try{await requireBookkeepingProtocol(api);}catch(error){setMessage(error.message);return;}
      let row;
      try{row=pending || {account_id:activeAccountId,payload:{request_id:crypto.randomUUID(),portfolio_id:portfolioId,
        kind:effectiveKind,occurred_at:`${occurredAt}:00+09:00`,usd_amount:Number(usd),
        krw_amount:Number(krw),rate:Number(rate),notes,flow_mode:flowMode,existing_flow_id:flowId || null,duplicate_confirmed:duplicateConfirmed}};
      if(!pending && executionContext){const [linked]=executionRows([{...row.payload,account_id:row.account_id,currency:'USD'}],executionContext);if(linked.execution)row.payload.execution=linked.execution;}
      }catch(error){setMessage(error.message);return;}
      try {persistPendingRequest(pendingKey,row,storage);}catch(error){setMessage(error.message);return;}
      setPending(row);setSaving(true);setMessage('');let recorded=false;
      try {
        const result=await api.recordUsdEvent(row.account_id,row.payload);recorded=true;
        clearPendingRequest(pendingKey,storage);setPending(null);
        setUsd('');setKrw('');setRate('');setNotes('');setFlowId('');setDuplicateConfirmed(false);
        await onChanged();setMessage(result.message);
      } catch(error) {
        if(recorded)setMessage('저장은 완료됐지만 화면 갱신에 실패했습니다. 다시 등록하지 말고 새로고침해주세요. '+error.message);
        else if(error.status && error.status<500 && ![401,403,429].includes(error.status)){clearPendingRequest(pendingKey,storage);setPending(null);setMessage(error.message);}
        else setMessage('저장 결과를 확인하지 못했습니다. 같은 요청의 결과를 다시 확인해주세요. '+error.message);
      } finally {setSaving(false);}
    });
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
      {pending && <div role="alert"><p>달러 기록의 저장 확인 중입니다. 계좌·금액을 바꾸지 않고 같은 요청으로 확인합니다.</p><button type="button" className="btn btn-primary" disabled={saving} onClick={submit}>같은 요청의 결과 다시 확인</button></div>}
      {ledger ? <div style={{ margin: '14px 0' }}>
        기록상 달러 <b>{formatUSD(ledger.usd_balance)}</b> · 평균 취득환율 <b>{rateText(ledger.average_rate)} 원</b>/달러
        <div>현재 계좌 달러 {formatUSD(ledger.actual_usd)} · 원화 취득원가 {formatKRW(ledger.cost_krw)}</div>
        {ledger.needs_reconciliation && <p role="alert" style={{ color: 'var(--color-loss)' }}>잔고 차이 {formatUSD(ledger.balance_difference)}: 실제 입출금을 확인한 뒤 ‘장부 확인 및 정정’에서 실제 잔고와 확인한 평균 취득환율을 등록해주세요. 대사 전에는 달러 매수·환전을 진행할 수 없습니다.</p>}
      </div> : <p>시작 달러 잔액: <b>{formatUSD(account?.deposit_usd || 0)}</b>. 마지막 환전환율을 시작 기준환율로 입력해주세요.</p>}
      <form onSubmit={submit}>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 12 }}>
          {ledger && !executionContext && <label>기록 종류<br /><select className="input-select" value={kind} disabled={locked} onChange={e => setKind(e.target.value)}>
            {Object.entries(names).filter(([key]) => !['OPENING', 'BUY', 'SELL', 'RECONCILE'].includes(key)).map(([key, name]) => <option key={key} value={key}>{name}</option>)}
          </select></label>}
          <label>실제 일시 (한국시간)<br /><input aria-label="환전 기록 일시" className="input-text" type="datetime-local" required value={occurredAt} disabled={locked} onChange={e => {setOccurredAt(e.target.value);setFlowId('');setDuplicateConfirmed(false);}} /></label>
          {['DEPOSIT','WITHDRAW'].includes(effectiveKind) && <><label>달러 입출금 구분<select className="input-select" disabled={locked} value={flowMode} onChange={e=>{setFlowMode(e.target.value);setFlowId('');setDuplicateConfirmed(false);}}><option value="EXTERNAL">외부 투자자금 · 잔고와 성과 함께 반영</option>{effectiveKind==='DEPOSIT' && <option value="INCOME">배당·이자 입금 · 투자 손익으로 반영</option>}<option value="ALREADY_RECORDED">기존 성과 입출금과 연결</option></select></label>{flowMode==='ALREADY_RECORDED' && <label>연결할 기존 달러 입출금<select className="input-select" required disabled={locked} value={flowId} onChange={e=>{setFlowId(e.target.value);const flow=matchingFlows.find(f=>f.id===e.target.value);if(flow)setRate(String(flow.exchange_rate));}}><option value="">날짜·금액이 같은 기록 선택</option>{matchingFlows.map(f=><option value={f.id} key={f.id}>{f.event_date} · {formatUSD(f.native_amount)} · 평가환율 {rateText(f.exchange_rate)}원</option>)}</select></label>}{flowMode==='EXTERNAL' && matchingFlows.length>0 && <label><input type="checkbox" disabled={locked} checked={duplicateConfirmed} onChange={e=>setDuplicateConfirmed(e.target.checked)}/>같은 날짜·금액의 기존 기록과 별개의 실제 입출금입니다.</label>}</>}
          {usesAmounts && <label>달러 금액<br /><input aria-label="환전 달러 금액" className="input-number" type="number" min="0.00000001" step="any" required value={usd} disabled={locked} onChange={e => {setUsd(e.target.value);setFlowId('');setDuplicateConfirmed(false);}} /></label>}
          {exchange && <label>{kind === 'EXCHANGE_IN' ? '실제 원화 지출액' : '실제 원화 수령액'}<br /><input aria-label="환전 원화 금액" className="input-number" type="number" min="0.01" step="any" required value={krw} disabled={locked} onChange={e => setKrw(e.target.value)} /></label>}
          {usesRate && <label>{effectiveKind === 'DEPOSIT' ? '입금 원가·평가 기준환율' : effectiveKind==='WITHDRAW'?'출금 당시 평가환율':'시작 기준환율'}<br /><input aria-label="달러 기준환율" className="input-number" type="number" min="0.01" step="any" required value={rate} disabled={locked} onChange={e => {setRate(e.target.value);setDuplicateConfirmed(false);}} /></label>}
          <label>메모<br /><input className="input-text" value={notes} maxLength={2000} disabled={locked} onChange={e => setNotes(e.target.value)} /></label>
        </div>
        {exchange && Number(usd) > 0 && <p>이번 환전환율: {(Number(krw) / Number(usd)).toFixed(4)}원/달러. 별도 비용이 있다면 실제 원화 총액에 포함해주세요.</p>}
        {effectiveKind === 'RECONCILE' && <p>현재 계좌 달러 전체의 확인한 평균 취득환율을 등록합니다. 현금 잔액과 종목 원가는 바꾸지 않습니다.</p>}
        {effectiveKind === 'DEPOSIT' && <p>실제 입금 달러 금액이 확인된 경우에만 등록하세요. 배당 추정값은 현금에 자동 반영하지 않습니다. 이미 잔고에 반영된 입금은 중복 등록하지 말고 장부 확인 및 정정을 이용하세요.</p>}
        <details className="history-help"><summary>입력 방법·달러 이체 안내</summary><p style={{ color: 'var(--text-secondary)' }}>같은 날짜는 등록 순서대로 계산합니다. 과거 기록을 고치려면 이후 기록부터 취소하세요. 계좌 간 달러 이동을 외부 입출금이나 배당으로 임의 등록하지 마세요. 양쪽 계좌의 원가와 성과 구분을 함께 확인해야 합니다.</p></details>
        <button className="btn btn-primary" type="submit" disabled={locked || !activeAccountId || (ledger?.needs_reconciliation && kind !== 'RECONCILE')}>{saving ? '저장 중…' : executionContext?'환전 내역 저장':names[effectiveKind]}</button>
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
