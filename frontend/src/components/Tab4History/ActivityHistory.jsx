import React,{useEffect,useState} from 'react';
import {Search,ChevronLeft,ChevronRight,RotateCcw} from 'lucide-react';
import {api} from '../../utils/api';
import {formatKRW,formatUSD} from '../../utils/formatters';
import {kstToday} from '../../utils/depositMaturities';
import {recentMonths,recordAmount} from '../../utils/activityHistory';

const kindNames={PAST_WITHDRAWAL:'과거 출금 누락 정정',CASH:'예수금 정정',HOLDING:'보유 수량·원가 정정',BUY:'매수',SELL:'매도',DEPOSIT:'입금',WITHDRAW:'출금',EXCHANGE_IN:'원화 → 달러',EXCHANGE_OUT:'달러 → 원화',OPENING:'달러 시작 기준',RECONCILE:'달러 원가 조정',KRW_ADJUST:'원화 잔고 조정',INTERNAL_TRANSFER:'원화 내부 이체'};
export default function ActivityHistory({portfolioId,accounts,assets=[],active,revision=0,onChanged,onBusyChange,onReviewCorrection}){
  const [filters,setFilters]=useState(()=>({start_date:recentMonths(kstToday()),end_date:kstToday(),account_id:'',category:'',asset_id:'',include_cancelled:false}));
  const [page,setPage]=useState(1),[data,setData]=useState(null),[loading,setLoading]=useState(false),[saving,setSaving]=useState(false),[error,setError]=useState(''),[message,setMessage]=useState(''),[reload,setReload]=useState(0);
  const [selectedTrades,setSelectedTrades]=useState([]);
  useEffect(()=>{onBusyChange?.(saving);},[saving,onBusyChange]);
  useEffect(()=>{
    if(!active)return;let cancelled=false;
    setData(null);setSelectedTrades([]);setError('');setLoading(true);
    if(!filters.start_date || !filters.end_date || filters.start_date>filters.end_date){setError('조회 시작일·종료일을 확인해주세요.');setLoading(false);return()=>{cancelled=true;};}
    const query={start_date:filters.start_date,end_date:filters.end_date,page,page_size:20,include_cancelled:filters.include_cancelled};
    if(filters.account_id)query.account_id=filters.account_id;if(filters.category)query.category=filters.category;
    if(filters.asset_id)query.asset_id=filters.asset_id;
    api.getActivity(portfolioId,query).then(result=>{if(!cancelled)setData(result);})
      .catch(e=>{if(!cancelled)setError(e.message);}).finally(()=>{if(!cancelled)setLoading(false);});
    return()=>{cancelled=true;};
  },[portfolioId,active,filters,page,revision,reload]);
  const filter=(key,value)=>{setFilters(old=>({...old,[key]:value,...(key==='category'?{asset_id:''}:{})}));setPage(1);setMessage('');};
  const cancel=async item=>{
    const restore=item.cancelled && item.category==='CASH' && item.detail.can_restore;
    const prompt=item.batch_id?'같은 알림 묶음의 입출금·이체·환전·매수를 함께 취소합니다. 이후 잔고 변경이 있으면 취소가 거절될 수 있습니다.':restore?'이 입출금 성과 기록을 복원할까요? 예수금은 변경하지 않습니다.':item.category==='TRADE'?'매매를 취소하고 예수금·수량·원가를 되돌릴까요?':item.category==='CASH'?'외부 입출금 성과 기록을 취소할까요? 예수금은 변경하지 않습니다.':'이 현금·원가 기록을 취소하고 이전 상태로 되돌릴까요?';
    if(!window.confirm(prompt))return;
    setSaving(true);setError('');setMessage('');let recorded=false;
    try{
      if(item.batch_id){const result=await api.undoNhNotices(portfolioId,item.batch_id);await Promise.allSettled((result.performance_portfolios || []).filter(p=>p!==portfolioId).map(p=>api.capturePerformance(p)));}
      else if(item.category==='TRADE')await api.batchDeleteTrades([item.detail.trade_id]);
      else if(item.category==='CASH')await api.voidPerformanceFlow(portfolioId,item.detail.flow_id,!restore);
      else if(item.category==='USD')await api.undoUsdEvent(item.account_id,item.detail.usd_event_id);
      else if(item.detail.correction_id)await api.undoLedgerCorrection(portfolioId,item.detail.correction_id);
      recorded=true;setMessage(restore?'입출금 성과 기록을 복원했습니다.':'기록을 취소했습니다.');setReload(n=>n+1);await onChanged();
    }catch(e){setError(recorded?'처리는 완료됐지만 화면 갱신에 실패했습니다. 다시 처리하지 말고 새로고침해주세요.':e.message);}
    finally{setSaving(false);}
  };
  const cancelSelected=async()=>{
    const ids=selectedTrades.filter(id=>data?.items.some(r=>r.category==='TRADE' && !r.cancelled && !r.batch_id && r.detail.trade_id===id));
    if(!ids.length || !window.confirm(`선택한 매매 ${ids.length}건을 함께 취소하고 예수금·수량·원가를 되돌릴까요?`))return;
    setSaving(true);setError('');setMessage('');let recorded=false;
    try{await api.batchDeleteTrades(ids);recorded=true;setSelectedTrades([]);setReload(n=>n+1);setMessage(`${ids.length}건의 매매를 취소했습니다.`);await onChanged();}
    catch(e){setError(recorded?'취소는 완료됐지만 화면 갱신에 실패했습니다. 새로고침해주세요.':e.message);}
    finally{setSaving(false);}
  };
  return <section className="section-card history-records" aria-label="과거 기록 조회">
    <div className="history-section-heading"><h3><Search size={18}/>기록 조회</h3><span className="history-muted">최신 날짜순 · 페이지당 20건</span></div>
    <fieldset className="history-filters" disabled={saving}>
      <label>시작일<input className="input-text" aria-label="기록 조회 시작일" type="date" required value={filters.start_date} max={filters.end_date} onChange={e=>filter('start_date',e.target.value)}/></label>
      <label>종료일<input className="input-text" aria-label="기록 조회 종료일" type="date" required value={filters.end_date} min={filters.start_date} onChange={e=>filter('end_date',e.target.value)}/></label>
      <label>계좌<select className="input-select" aria-label="기록 조회 계좌" value={filters.account_id} onChange={e=>filter('account_id',e.target.value)}><option value="">전체 계좌</option>{accounts.map(a=><option key={a.id} value={a.id}>{a.account_alias}</option>)}</select></label>
      <label>기록 종류<select className="input-select" aria-label="기록 조회 종류" value={filters.category} onChange={e=>filter('category',e.target.value)}><option value="">전체 기록</option><option value="TRADE">매매</option><option value="CASH">외부 입출금·내부 이체</option><option value="USD">달러 원가·환전</option><option value="ADJUST">장부 정정</option></select></label>
      <label className="history-check"><input type="checkbox" checked={filters.include_cancelled} onChange={e=>filter('include_cancelled',e.target.checked)}/>취소 기록 포함</label>
      <button type="button" className="btn btn-secondary btn-sm" onClick={()=>setReload(n=>n+1)}><RotateCcw size={14}/>다시 조회</button>
    </fieldset>
    {filters.category==='TRADE' && <details className="history-help"><summary>추가 필터 · 종목</summary><label>종목 <select className="input-select" aria-label="기록 조회 종목" disabled={saving} value={filters.asset_id} onChange={e=>filter('asset_id',e.target.value)}><option value="">전체 종목</option>{assets.map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select></label></details>}
    {selectedTrades.length>0 && <div className="history-selected-strip"><span>이 페이지의 매매 {selectedTrades.length}건 선택</span><button type="button" className="btn btn-secondary btn-sm" disabled={saving || loading} onClick={cancelSelected}>선택한 매매 함께 취소</button><button type="button" className="btn btn-secondary btn-sm" disabled={saving} onClick={()=>setSelectedTrades([])}>선택 해제</button></div>}
    {error && <p className="history-error" role="alert">{error}</p>}{message && <p className="history-success" role="status">{message}</p>}
    {loading?<p className="history-muted" role="status">기록 조회 중…</p>:data && <>
      <p className="history-muted">선택한 기간 · {data.total}건</p>
      {data.items.length===0?<div className="history-empty">선택한 조건의 기록이 없습니다.</div>:<div className="history-record-list">{data.items.map(item=>{
        const d=item.detail || {},canCancel=!item.cancelled && (item.batch_id || ['TRADE','USD','CASH'].includes(item.category) || item.detail?.correction_id);
        return <article key={item.id} className={`history-record ${item.cancelled?'is-cancelled':''}`}>
          <div className="history-record-summary"><time>{item.event_date}</time><div className="history-record-identity"><span className="history-kind">{kindNames[item.kind] || item.kind}</span><strong>{item.account_alias}</strong><span className="history-muted">{item.description}</span>{item.cancelled && <span className="history-kind">취소됨</span>}</div><strong className="history-record-amount">{recordAmount(item)}</strong></div>
          <details className="history-record-detail"><summary>상세 기록{item.batch_id?' · 알림 묶음':''}</summary><div className="history-record-detail-body">
            {d.correction_id && <>{!item.cancelled && d.history_pending && <button className="btn btn-secondary btn-sm" disabled={saving} onClick={()=>onReviewCorrection?.(d.correction_id)}>남은 과거 평가 기록 확인</button>}<p>등록 시각 {new Date(d.created_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'})}</p><p>원화 예수금 {formatKRW(Number(d.before_cash.deposit_krw))} → {formatKRW(Number(d.after_cash.deposit_krw))} · 달러 {formatUSD(Number(d.before_cash.deposit_usd))} → {formatUSD(Number(d.after_cash.deposit_usd))}</p>{d.proposal.kind==='HOLDING' && <p>수량 {(d.before_holdings.find(h=>h.asset_id===d.proposal.asset_id)?.quantity ?? 0)} → {d.proposal.quantity} · 확인한 단가 {d.proposal.avg_price_usd || d.proposal.avg_price} · 매입환율 {d.proposal.buy_fx_rate || '해당 없음'}</p>}{d.history_pending && <p>과거 평가 기록 미확정 · 입력 화면의 ‘장부 확인 및 정정’에서 남은 기록을 확인해주세요.</p>}</>}
            {d.quantity!=null && <p>수량 {d.quantity} · 단가 {item.currency==='USD'?formatUSD(Number(d.price)):formatKRW(Number(d.price))}{d.ticker?` · ${d.ticker}`:''}</p>}
            {(d.fx_rate || d.exchange_rate) && <p>적용환율 {Number(d.fx_rate || d.exchange_rate).toLocaleString('ko-KR',{maximumFractionDigits:8})}원</p>}
            {d.reported_available_krw!=null && <p>알림의 출금가능금액 {formatKRW(Number(d.reported_available_krw))} · 참고값</p>}{d.occurred_at && <p>실제 일시 {new Date(d.occurred_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'})}</p>}
            {d.balance!=null && <p>처리 후 달러 {formatUSD(Number(d.balance))} · 원화 취득원가 {formatKRW(Number(d.cost_krw))}</p>}
            {d.source_account && <p>출금 계좌: {d.source_account}</p>}{d.destination_account && <p>입금 계좌: {d.destination_account}</p>}{d.peer_account && <p>이체 상대 계좌: {d.peer_account}</p>}{item.category==='CASH' && !d.flow_id && d.cash_applied===false && <p>과거 이력만 저장 · 예수금 변경 없음</p>}{d.broker_order_no && <p>주문번호 {d.broker_order_no}</p>}
            {d.notes && <p>{d.notes}</p>}{item.category==='CASH' && d.flow_id && <p>{d.cash_linked?(d.cash_applied?'성과 기록·예수금 함께 반영':'NH 알림 연결 · 성과 기록만'):'성과 계산용 입출금 기록'} · {formatKRW(Number(d.amount_krw))}</p>}
            {item.batch_id && <p>같은 알림 묶음의 입출금·이체·환전·매수는 함께 취소됩니다. 묶음 ID: {item.batch_id.slice(0,8)}</p>}
            {canCancel && item.category==='TRADE' && !item.batch_id && <label className="history-check"><input type="checkbox" disabled={saving} checked={selectedTrades.includes(d.trade_id)} onChange={e=>setSelectedTrades(old=>e.target.checked?[...old,d.trade_id]:old.filter(id=>id!==d.trade_id))}/>여러 매매를 함께 취소할 목록에 선택</label>}
            {(canCancel || (item.cancelled && d.can_restore)) && <button type="button" className="btn btn-secondary btn-sm" disabled={saving} onClick={()=>cancel(item)}>{item.cancelled?'성과 기록 복원':item.batch_id?'이 알림 묶음 취소':'이 기록 취소'}</button>}
          </div></details>
        </article>;
      })}</div>}
      <div className="history-pagination"><span className="history-muted">{data.page} / {data.pages} 페이지</span><div><button type="button" className="btn btn-secondary btn-sm" disabled={saving || loading || data.page<=1} onClick={()=>setPage(data.page-1)}><ChevronLeft size={14}/>이전</button><button type="button" className="btn btn-secondary btn-sm" disabled={saving || loading || data.page>=data.pages} onClick={()=>setPage(data.page+1)}>다음<ChevronRight size={14}/></button></div></div>
    </>}
  </section>;
}
