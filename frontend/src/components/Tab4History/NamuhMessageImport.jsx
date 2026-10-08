import React,{useEffect,useState} from 'react';
import {api} from '../../utils/api';
import {kstToday} from '../../utils/depositMaturities';
import {formatKRW,formatUSD} from '../../utils/formatters';
import {parseNhNotifications,noticeFingerprint,resolveNhNotice,flowCandidates,chosenFlow,validateNhNotice,
  noticeApiRow,previewNhNotices,readNoticeDraft,writeNoticeDraft,validNoticeDate,isCashNotice,peerAccount} from '../../utils/nhNotices';

const names={BUY:'매수 체결',DEPOSIT:'원화 입금',WITHDRAW:'원화 출금',EXCHANGE_IN:'원화 → 달러 환전'};
export default function NamuhMessageImport({accounts,assets,portfolioId,tradeDate,buyRows=[],disabled,ledgers=[],onChanged,focused=false,active=true,onBusyChange}) {
  const [initial]=useState(()=>readNoticeDraft(portfolioId));
  const [open,setOpen]=useState(focused || Boolean(initial?.rows.length));
  const [text,setText]=useState('');
  const [rows,setRows]=useState(initial?.rows || []);
  const [requestId,setRequestId]=useState(initial?.requestId || crypto.randomUUID());
  const [pendingPayload,setPendingPayload]=useState(initial?.pendingPayload || null);
  const [contexts,setContexts]=useState({});
  const [confirmed,setConfirmed]=useState(false);
  const [loading,setLoading]=useState(false);
  const [saving,setSaving]=useState(false);
  const [message,setMessage]=useState('');
  const [contextError,setContextError]=useState('');
  const [storageError,setStorageError]=useState(false);
  const [reload,setReload]=useState(0);
  useEffect(()=>{onBusyChange?.(saving);},[saving,onBusyChange]);
  const scopedAccounts=accounts.filter(a=>!a.portfolio_id || String(a.portfolio_id)===String(portfolioId));
  const allAccounts=[...accounts,...Object.values(contexts).flatMap(c=>c.transfer_accounts || []).filter(a=>!accounts.some(original=>String(original.id)===String(a.id)))].filter((a,i,all)=>all.findIndex(b=>String(b.id)===String(a.id))===i);
  const dates=[...new Set([tradeDate,...rows.map(r=>r.eventDate)])].filter(validNoticeDate).sort();
  const dateKey=dates.join('/');
  useEffect(()=>{setStorageError(!writeNoticeDraft(portfolioId,{rows,requestId,pendingPayload}));},[portfolioId,rows,requestId,pendingPayload]);
  useEffect(()=>{
    let cancelled=false;
    if (!open || !active) return;
    setContextError('');setLoading(true);setConfirmed(false);
    Promise.all(dateKey.split('/').map(day=>api.getNhNoticeContext(portfolioId,day).then(data=>[day,data])))
      .then(entries=>{if(!cancelled)setContexts(Object.fromEntries(entries));})
      .catch(error=>{if(!cancelled)setContextError(error.message);})
      .finally(()=>{if(!cancelled)setLoading(false);});
    return()=>{cancelled=true;};
  },[portfolioId,open,active,dateKey,reload]);
  const edit=(index,key,value)=>{
    setRows(previous=>previous.map((row,i)=>i!==index?row:{...row,
      ...(key==='movement'?{external:value==='EXTERNAL',crossPortfolio:value==='CROSS',sourceAccountId:'',destinationAccountId:'',flowId:undefined,counterpartyFlowId:undefined}:{[key]:value}),
      ...(['accountId','eventDate','sourceAccountId','destinationAccountId'].includes(key)?{flowId:undefined,counterpartyFlowId:undefined}:{}),
      ...(key==='accountId'?{accountWarning:''}:{}),
      ...(key!=='duplicateConfirmed'?{duplicateConfirmed:false}:{})}));setConfirmed(false);
  };
  const add=async()=>{
    setMessage('');setSaving(true);
    try{
      const parsed=parseNhNotifications(text,tradeDate);
      if(!parsed.length)throw new Error('NH 알림을 붙여넣어주세요.');
      if(rows.length+parsed.length>50)throw new Error('한 번에 최대 50건까지 확인할 수 있습니다.');
      const added=[];
      for(const row of parsed){
        const resolved=resolveNhNotice(row,accounts,assets,portfolioId,[...rows,...added]);
        const {raw,...data}=resolved;
        const pastCash=isCashNotice(data) && data.eventDate<kstToday();
        added.push({...data,...(pastCash?{applyCash:false}:{}),id:crypto.randomUUID(),fingerprint:await noticeFingerprint(raw)});
      }
      setRows(previous=>[...previous,...added]);setText('');setConfirmed(false);
    }catch(error){setMessage(error.message);}
    finally{setSaving(false);}
  };
  const checks=rows.map((row,i)=>validateNhNotice(row,contexts[row.eventDate],accounts,assets,portfolioId,buyRows,rows.slice(0,i)));
  const preview=previewNhNotices(rows,contexts,ledgers || []);
  const ready=rows.length>0 && confirmed && !loading && !contextError && !checks.some(c=>c.errors.length) && !preview.errors.length;
  const persist=(data)=>setStorageError(!writeNoticeDraft(portfolioId,data));
  const save=async()=>{
    if(!confirmed || (!pendingPayload && !ready))return;
    const payload=pendingPayload || {request_id:requestId,confirmed:true,expected_cash:preview.expected,rows:rows.map(row=>noticeApiRow(row,contexts[row.eventDate]))};
    setSaving(true);setMessage('');setPendingPayload(payload);persist({rows,requestId,pendingPayload:payload});
    let recorded=false;
    try{
      const result=await api.commitNhNotices(portfolioId,payload);
      recorded=true;setRows([]);setPendingPayload(null);setConfirmed(false);setRequestId(crypto.randomUUID());
      persist({rows:[]});setReload(n=>n+1);
      setMessage(`${result.notice_count ?? rows.length}건의 알림을 장부에 반영했습니다.`);
      await onChanged();
      const refreshed=await Promise.allSettled((result.performance_portfolios || []).filter(p=>p!==portfolioId).map(p=>api.capturePerformance(p)));
      if(refreshed.some(r=>r.status==='rejected'))setMessage('장부 반영은 완료됐습니다. 상대 포트폴리오의 종가 기록 갱신은 해당 포트폴리오에서 다시 확인해주세요.');
    }catch(error){
      if(!recorded && error.status && error.status<500){setPendingPayload(null);persist({rows,requestId,pendingPayload:null});setConfirmed(false);setReload(n=>n+1);}
      setMessage(recorded?'저장은 완료됐지만 화면 갱신에 실패했습니다. 다시 등록하지 말고 새로고침해주세요.':error.message);
    }finally{setSaving(false);}
  };
  const undo=async id=>{
    if(!window.confirm('이 알림 묶음의 입출금·이체·환전·매수를 모두 되돌릴까요? 이전 기준과 취소 이력은 보존됩니다.'))return;
    setSaving(true);
    try{const result=await api.undoNhNotices(portfolioId,id);await Promise.allSettled((result.performance_portfolios || []).filter(p=>p!==portfolioId).map(p=>api.capturePerformance(p)));setReload(n=>n+1);setMessage('알림 묶음을 취소하고 이전 잔고·원가를 복원했습니다.');await onChanged();}
    catch(error){setMessage(error.message);}
    finally{setSaving(false);}
  };
  const move=(index,delta)=>{setRows(previous=>{const next=[...previous];[next[index],next[index+delta]]=[next[index+delta],next[index]];return next;});setConfirmed(false);};
  const batches=contexts[tradeDate]?.batches || [];
  return <section className={`section-card workflow-panel ${focused?'history-focused history-notices':''}`}>
    {focused?<div className="history-section-heading"><h3>NH 알림 붙여넣기</h3><span className="history-muted">입력 → 확인 → 반영</span></div>:<button type="button" className="btn btn-secondary" aria-expanded={open} onClick={()=>setOpen(!open)}>NH 알림 가져오기 · 매수 / 입출금 / 이체 / 환전 {open?'접기':'열기'}</button>}
    {open && <div>
      <p className="history-muted">여러 알림을 붙여넣거나 반복해서 목록에 추가한 뒤 함께 반영하세요.</p>
      <fieldset disabled={disabled || saving || Boolean(pendingPayload)} style={{border:0,padding:0}}>
        <label>NH 카카오톡 알림<textarea aria-label="NH 알림" className="input-text" rows={focused?4:7} maxLength={30000} style={{width:'100%',boxSizing:'border-box'}} value={text} onChange={e=>setText(e.target.value)} /></label>
        <button type="button" className="btn btn-secondary" onClick={add}>알림을 확인 목록에 추가</button>
        {focused && rows.length>0 && <div className="history-section-heading history-review-heading"><h3>반영할 알림</h3><span className="history-kind">{rows.length}건 · 미반영</span></div>}
        {rows.map((row,i)=>{
          const context=contexts[row.eventDate],matches=flowCandidates(row,context),flow=chosenFlow(row,context);
          return <div className={focused?"history-notice-row":"trade-row-card"} key={row.id} style={{marginTop:12}}>
            <b>{i+1}. {names[row.kind]}{row.assetName?` · ${row.assetName}`:''}</b>
            <p>{row.kind==='BUY'?`${row.quantity}주 × ${formatKRW(row.price)} · 주문 ${row.brokerOrderNo || '확인 불가'}`:
              isCashNotice(row)?formatKRW(row.krwAmount):`${formatKRW(row.krwAmount)} → ${formatUSD(row.usdAmount)} · 고시환율 ${row.quotedRate}`}</p>
            {row.kind==='WITHDRAW' && Number.isFinite(row.reportedAvailableKrw) && <small>알림의 출금가능금액 {formatKRW(row.reportedAvailableKrw)} · 참고값이며 잔고를 덮어쓰지 않습니다.</small>}
            {focused && <div className="history-row-context">{accounts.find(a=>String(a.id)===row.accountId)?.account_alias || '계좌 선택 필요'} · {row.eventDate} · 미반영</div>}
            <details className={focused?'history-notice-details':''} open={!focused || checks[i].errors.length>0 || undefined}>
            <summary>계좌·날짜·반영 방식 확인 / 수정</summary>
            <div className="history-notice-fields">
            <label>계좌 <select aria-label={`알림 ${i+1} 계좌`} className="input-select" value={row.accountId} onChange={e=>edit(i,'accountId',e.target.value)}><option value="">계좌 선택</option>{scopedAccounts.map(a=><option key={a.id} value={a.id}>{a.account_alias} ({a.account_no})</option>)}</select></label>
            {row.accountWarning && <p>{row.accountWarning}</p>}
            <label>적용 날짜 <input aria-label={`알림 ${i+1} 날짜`} type="date" className="input-text" value={row.eventDate} onChange={e=>edit(i,'eventDate',e.target.value)} /></label>
            <small>{row.occurredAt?`알림 시각 ${row.occurredAt.slice(11,16)}`:'알림에 시각 없음 · 같은 날짜는 목록 순서대로 반영합니다.'}</small>
            {row.kind==='BUY' && <label>종목 <select aria-label={`알림 ${i+1} 종목`} className="input-select" value={row.assetId} onChange={e=>edit(i,'assetId',e.target.value)}><option value="">종목 선택</option>{assets.filter(a=>a.market==='KR' && !a.is_deposit && String(a.ticker).toUpperCase()===row.ticker && (!a.portfolio_id || String(a.portfolio_id)===String(portfolioId))).map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select></label>}
            {isCashNotice(row) && <>
              <label>입출금 구분 <select aria-label={`알림 ${i+1} 입출금 구분`} className="input-select" value={row.external?'EXTERNAL':row.crossPortfolio?'CROSS':'INTERNAL'} onChange={e=>edit(i,'movement',e.target.value)}><option value="EXTERNAL">{row.kind==='WITHDRAW'?'앱 밖으로 출금':'외부 투자금 입금'}</option><option value="INTERNAL">같은 포트폴리오 안의 계좌 이체</option><option value="CROSS">포트폴리오 간 이체</option></select></label>
              {!row.external && <label>{row.kind==='DEPOSIT'?'출금':'입금'} 상대 계좌 <select aria-label={`알림 ${i+1} 이체 상대 계좌`} className="input-select" value={peerAccount(row) || ''} onChange={e=>edit(i,row.kind==='DEPOSIT'?'sourceAccountId':'destinationAccountId',e.target.value)}><option value="">상대 계좌 선택</option>{allAccounts.filter(a=>String(a.id)!==row.accountId && (row.crossPortfolio?String(a.portfolio_id)!==String(portfolioId):!a.portfolio_id || String(a.portfolio_id)===String(portfolioId))).map(a=><option key={a.id} value={a.id}>{a.portfolio_name?`${a.portfolio_name} · `:''}{a.account_alias}</option>)}</select></label>}
              <label>예수금 반영 <select aria-label={`알림 ${i+1} 예수금 반영`} className="input-select" value={row.applyCash?'APPLY':'REFLECTED'} onChange={e=>edit(i,'applyCash',e.target.value==='APPLY')}><option value="APPLY">{row.external?`예수금에도 ${row.kind==='WITHDRAW'?'출금':'입금'} 반영`:'양쪽 예수금에 이체 반영'}</option><option value="REFLECTED">{row.external?'잔고에 이미 반영됨 · 기록만 저장':'양쪽 잔고에 이미 반영됨 · 기록만 저장'}</option></select></label>
              {(row.external || row.crossPortfolio) && matches.length>0 && <label>성과 입출금 기록 <select aria-label={`알림 ${i+1} 입금 연결`} className="input-select" value={flow===null?'NEW':flow} onChange={e=>edit(i,'flowId',e.target.value)}><option value="">연결할 기록 선택</option>{matches.map(f=><option key={f.id} value={f.id}>기존 {formatKRW(Math.abs(Number(f.amount_krw)))} {row.kind==='WITHDRAW'?'출금':'입금'}에 연결{f.cash_handled?' · 이미 처리됨':''}</option>)}<option value="NEW">별도 입출금 · 새 기록</option></select><small>기존 기록을 연결하면 성과 입출금을 중복 생성하지 않습니다.</small></label>}
              {row.crossPortfolio && flowCandidates(row,context,true).length>0 && <label>상대 포트폴리오 성과 기록 <select className="input-select" value={chosenFlow(row,context,true) ?? 'NEW'} onChange={e=>edit(i,'counterpartyFlowId',e.target.value)}><option value="">연결할 기록 선택</option>{flowCandidates(row,context,true).map(f=><option key={f.id} value={f.id}>기존 {formatKRW(Math.abs(Number(f.amount_krw)))} 입출금에 연결{f.cash_handled?' · 이미 처리됨':''}</option>)}<option value="NEW">별도 입출금 · 새 기록</option></select></label>}
              {context?.trackings?.[portfolioId] && row.eventDate<context.trackings[portfolioId].baseline_date && <small>성과 기준일 이전 기록입니다. 과거 이력만 남기며 기준일 이후 수익률에는 반영하지 않습니다. 누락된 출금이 현재 잔고에 남아 있다면 아래 ‘장부 확인 및 정정’의 ‘과거 출금 누락’을 이용하세요.</small>}
              {row.crossPortfolio && <small>양쪽 기록은 함께 저장·취소됩니다. 상대 계좌가 앱에 없으면 ‘앱 밖으로 출금’으로 기록하세요.</small>}
            </>}
            </div></details>
            {checks[i].errors.map(error=><p role="alert" key={error}>{error}</p>)}
            {checks[i].duplicate && <label><input type="checkbox" checked={Boolean(row.duplicateConfirmed)} onChange={e=>edit(i,'duplicateConfirmed',e.target.checked)} />기존 기록과 별개의 거래임을 확인했습니다.</label>}
            <div className="history-row-actions"><button type="button" className="btn btn-secondary btn-sm" disabled={i===0} onClick={()=>move(i,-1)}>위로</button>{' '}
            <button type="button" className="btn btn-secondary btn-sm" disabled={i===rows.length-1} onClick={()=>move(i,1)}>아래로</button>{' '}
            <button type="button" className="btn btn-secondary btn-sm" onClick={()=>{setRows(previous=>previous.filter(r=>r.id!==row.id));setConfirmed(false);}}>목록에서 제외</button></div>
          </div>;
        })}
      </fieldset>
      {rows.length>0 && <>
        <div className="history-balance-preview"><h4>반영 후 예상 잔고</h4>
        {Object.entries(preview.balances).map(([id,cash])=><p key={id}>{allAccounts.find(a=>String(a.id)===id)?.account_alias} · 원화 {formatKRW(cash.deposit_krw)} · 달러 {formatUSD(cash.deposit_usd)}{preview.costs[id]?.balance>0 && ` · 달러 평균 취득환율 ${(preview.costs[id].cost/preview.costs[id].balance).toFixed(4)}`}</p>)}
        </div>
        {preview.errors.map(error=><p role="alert" key={error}>{error}</p>)}
        <div className="history-confirm-footer"><label className="history-check"><input type="checkbox" disabled={saving || disabled} checked={confirmed} onChange={e=>setConfirmed(e.target.checked)} />계좌·날짜·순서·금액과 예상 잔고를 확인했습니다.</label>
        <button type="button" className="btn btn-primary" disabled={saving || disabled || !confirmed || (!pendingPayload && !ready)} onClick={save}>{saving?'반영 중…':pendingPayload?'동일 요청의 저장 결과 다시 확인':`확인한 알림 ${rows.length}건 장부에 일괄 반영`}</button></div>
        {!pendingPayload && !ready && <p>위의 확인 항목을 해결하고 최종 확인을 체크하면 반영할 수 있습니다.</p>}
      </>}
      {loading && <p>기존 기록·계좌 잔고 확인 중…</p>}
      {contextError && <p role="alert">조회 실패: {contextError} <button type="button" className="btn btn-secondary" onClick={()=>setReload(n=>n+1)}>다시 조회</button></p>}
      {pendingPayload && <p role="alert">저장 결과가 확정될 때까지 목록을 수정하지 않습니다. 같은 요청으로 다시 확인하면 중복 반영하지 않습니다.</p>}
      {storageError && <p role="alert">임시 저장을 사용할 수 없습니다. 저장 결과 확인 전에는 이 화면을 닫지 마세요.</p>}
      {message && <p role="status">{message}</p>}
      {!focused && <details><summary>알림 반영 이력·묶음 취소</summary>{batches.map(batch=><p key={batch.id}>{new Date(batch.created_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'})} · {batch.result.items?.length || 0}건 {batch.reversed_at?'(취소됨)':<button type="button" className="btn btn-secondary btn-sm" disabled={saving} onClick={()=>undo(batch.id)}>이 묶음 취소</button>}</p>)}</details>}
      <details><summary>지원 범위·기록 안내</summary><p>국내 매수 전량 체결, 원화 입출금·계좌 이체, USD 외화매수 알림을 지원합니다. 부분 체결·달러 매도 환전은 직접 입력해주세요. 과거 입출금은 기본으로 기록만 저장하므로 예수금이 중복 반영되지 않는지 확인하세요. 연도가 없는 알림은 화면의 체결 날짜 연도로 해석하므로 과거 알림은 적용 날짜를 확인하세요. 등록 전 목록은 이 기기에 30일간 임시 저장됩니다. 환전 원가는 실제 원화 지출액으로 계산하고 고시환율도 보존합니다. 한 묶음에서 오류가 나면 전부 반영하지 않습니다.</p></details>
    </div>}
  </section>;
}
