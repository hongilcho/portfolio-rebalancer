import React,{useEffect,useState} from 'react';
import {api} from '../../utils/api';
import {formatKRW,formatUSD} from '../../utils/formatters';
import {parseNhNotifications,noticeFingerprint,resolveNhNotice,flowCandidates,chosenFlow,validateNhNotice,
  noticeApiRow,previewNhNotices,readNoticeDraft,writeNoticeDraft,validNoticeDate} from '../../utils/nhNotices';

const names={BUY:'매수 체결',DEPOSIT:'원화 입금',EXCHANGE_IN:'원화 → 달러 환전'};
export default function NamuhMessageImport({accounts,assets,portfolioId,tradeDate,buyRows=[],disabled,ledgers=[],onChanged}) {
  const [initial]=useState(()=>readNoticeDraft(portfolioId));
  const [open,setOpen]=useState(Boolean(initial?.rows.length));
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
  const scopedAccounts=accounts.filter(a=>!a.portfolio_id || String(a.portfolio_id)===String(portfolioId));
  const dates=[...new Set([tradeDate,...rows.map(r=>r.eventDate)])].filter(validNoticeDate).sort();
  const dateKey=dates.join('/');
  useEffect(()=>{setStorageError(!writeNoticeDraft(portfolioId,{rows,requestId,pendingPayload}));},[portfolioId,rows,requestId,pendingPayload]);
  useEffect(()=>{
    let cancelled=false;
    if (!open) return;
    setContextError('');setLoading(true);setConfirmed(false);
    Promise.all(dateKey.split('/').map(day=>api.getNhNoticeContext(portfolioId,day).then(data=>[day,data])))
      .then(entries=>{if(!cancelled)setContexts(Object.fromEntries(entries));})
      .catch(error=>{if(!cancelled)setContextError(error.message);})
      .finally(()=>{if(!cancelled)setLoading(false);});
    return()=>{cancelled=true;};
  },[portfolioId,open,dateKey,reload]);
  const edit=(index,key,value)=>{
    setRows(previous=>previous.map((row,i)=>i===index?{...row,[key]:value,
      ...(key==='accountId'||key==='eventDate'||key==='external'?{flowId:undefined}:{}),
      ...(key==='accountId'?{accountWarning:''}:{}),
      ...(key!=='duplicateConfirmed'?{duplicateConfirmed:false}:{})}:row));setConfirmed(false);
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
        added.push({...data,id:crypto.randomUUID(),fingerprint:await noticeFingerprint(raw)});
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
      setMessage(`${result.items.length}건을 장부에 반영했습니다.`);
      await onChanged();
    }catch(error){
      if(!recorded && error.status && error.status<500){setPendingPayload(null);persist({rows,requestId,pendingPayload:null});setConfirmed(false);setReload(n=>n+1);}
      setMessage(recorded?'저장은 완료됐지만 화면 갱신에 실패했습니다. 다시 등록하지 말고 새로고침해주세요.':error.message);
    }finally{setSaving(false);}
  };
  const undo=async id=>{
    if(!window.confirm('이 알림 묶음의 입금·환전·매수를 모두 되돌릴까요? 이전 기준과 취소 이력은 보존됩니다.'))return;
    setSaving(true);
    try{await api.undoNhNotices(portfolioId,id);setReload(n=>n+1);setMessage('알림 묶음을 취소하고 이전 잔고·원가를 복원했습니다.');await onChanged();}
    catch(error){setMessage(error.message);}
    finally{setSaving(false);}
  };
  const move=(index,delta)=>{setRows(previous=>{const next=[...previous];[next[index],next[index+delta]]=[next[index+delta],next[index]];return next;});setConfirmed(false);};
  const batches=contexts[tradeDate]?.batches || [];
  return <section className="section-card workflow-panel">
    <button type="button" className="btn btn-secondary" aria-expanded={open} onClick={()=>setOpen(!open)}>NH 알림 가져오기 · 매수 / 입금 / 환전 {open?'접기':'열기'}</button>
    {open && <div>
      <p>여러 알림을 함께 붙이거나 반복해서 목록에 추가하세요. 계좌·날짜·처리 순서와 예상 잔고를 확인한 뒤 한 번에 장부에 반영합니다.</p>
      <fieldset disabled={disabled || saving || Boolean(pendingPayload)} style={{border:0,padding:0}}>
        <label>NH 카카오톡 알림<textarea aria-label="NH 알림" className="input-text" rows={7} maxLength={30000} style={{width:'100%',boxSizing:'border-box'}} value={text} onChange={e=>setText(e.target.value)} /></label>
        <button type="button" className="btn btn-secondary" onClick={add}>알림을 확인 목록에 추가</button>
        {rows.map((row,i)=>{
          const context=contexts[row.eventDate],matches=flowCandidates(row,context),flow=chosenFlow(row,context);
          return <div className="trade-row-card" key={row.id} style={{marginTop:12}}>
            <b>{i+1}. {names[row.kind]}{row.assetName?` · ${row.assetName}`:''}</b>
            <p>{row.kind==='BUY'?`${row.quantity}주 × ${formatKRW(row.price)} · 주문 ${row.brokerOrderNo || '확인 불가'}`:
              row.kind==='DEPOSIT'?formatKRW(row.krwAmount):`${formatKRW(row.krwAmount)} → ${formatUSD(row.usdAmount)} · 고시환율 ${row.quotedRate}`}</p>
            <label>계좌 <select aria-label={`알림 ${i+1} 계좌`} className="input-select" value={row.accountId} onChange={e=>edit(i,'accountId',e.target.value)}><option value="">계좌 선택</option>{scopedAccounts.map(a=><option key={a.id} value={a.id}>{a.account_alias} ({a.account_no})</option>)}</select></label>
            {row.accountWarning && <p>{row.accountWarning}</p>}
            <label>적용 날짜 <input aria-label={`알림 ${i+1} 날짜`} type="date" className="input-text" value={row.eventDate} onChange={e=>edit(i,'eventDate',e.target.value)} /></label>
            <small>{row.occurredAt?`알림 시각 ${row.occurredAt.slice(11,16)}`:'알림에 시각 없음 · 같은 날짜는 목록 순서대로 반영합니다.'}</small>
            {row.kind==='BUY' && <label>종목 <select aria-label={`알림 ${i+1} 종목`} className="input-select" value={row.assetId} onChange={e=>edit(i,'assetId',e.target.value)}><option value="">종목 선택</option>{assets.filter(a=>a.market==='KR' && !a.is_deposit && String(a.ticker).toUpperCase()===row.ticker && (!a.portfolio_id || String(a.portfolio_id)===String(portfolioId))).map(a=><option key={a.id} value={a.id}>{a.name}</option>)}</select></label>}
            {row.kind==='DEPOSIT' && <>
              <label>입금 구분 <select className="input-select" value={row.external?'EXTERNAL':'INTERNAL'} onChange={e=>edit(i,'external',e.target.value==='EXTERNAL')}><option value="EXTERNAL">외부 투자금 입금</option><option value="INTERNAL">포트폴리오 내부 계좌 이체</option></select></label>
              {!row.external && <label>출금 계좌 <select className="input-select" value={row.sourceAccountId || ''} onChange={e=>edit(i,'sourceAccountId',e.target.value)}><option value="">출금 계좌 선택</option>{scopedAccounts.filter(a=>String(a.id)!==row.accountId).map(a=><option key={a.id} value={a.id}>{a.account_alias}</option>)}</select></label>}
              {row.external && <label>예수금 반영 <select aria-label={`알림 ${i+1} 예수금 반영`} className="input-select" value={row.applyCash?'APPLY':'REFLECTED'} onChange={e=>edit(i,'applyCash',e.target.value==='APPLY')}><option value="APPLY">예수금에도 입금 반영</option><option value="REFLECTED">잔고에 이미 반영됨 · 입금 기록만</option></select></label>}
              {row.external && matches.length>0 && <label>성과 입금 기록 <select aria-label={`알림 ${i+1} 입금 연결`} className="input-select" value={flow===null?'NEW':flow} onChange={e=>edit(i,'flowId',e.target.value)}><option value="">연결할 기록 선택</option>{matches.map(f=><option key={f.id} value={f.id}>기존 {formatKRW(Number(f.amount_krw))} 입금에 연결{f.cash_handled?' · 이미 처리됨':''}</option>)}<option value="NEW">별도 입금 · 새 기록</option></select><small>기존 기록을 연결하면 성과 입금을 중복 생성하지 않습니다.</small></label>}
            </>}
            {checks[i].errors.map(error=><p role="alert" key={error}>{error}</p>)}
            {checks[i].duplicate && <label><input type="checkbox" checked={Boolean(row.duplicateConfirmed)} onChange={e=>edit(i,'duplicateConfirmed',e.target.checked)} />기존 기록과 별개의 거래임을 확인했습니다.</label>}
            <button type="button" className="btn btn-secondary btn-sm" disabled={i===0} onClick={()=>move(i,-1)}>위로</button>{' '}
            <button type="button" className="btn btn-secondary btn-sm" disabled={i===rows.length-1} onClick={()=>move(i,1)}>아래로</button>{' '}
            <button type="button" className="btn btn-secondary btn-sm" onClick={()=>{setRows(previous=>previous.filter(r=>r.id!==row.id));setConfirmed(false);}}>목록에서 제외</button>
          </div>;
        })}
      </fieldset>
      {rows.length>0 && <>
        <h4>반영 후 예상 잔고</h4>
        {Object.entries(preview.balances).map(([id,cash])=><p key={id}>{accounts.find(a=>String(a.id)===id)?.account_alias} · 원화 {formatKRW(cash.deposit_krw)} · 달러 {formatUSD(cash.deposit_usd)}{preview.costs[id]?.balance>0 && ` · 달러 평균 취득환율 ${(preview.costs[id].cost/preview.costs[id].balance).toFixed(4)}`}</p>)}
        {preview.errors.map(error=><p role="alert" key={error}>{error}</p>)}
        <label><input type="checkbox" disabled={saving || disabled} checked={confirmed} onChange={e=>setConfirmed(e.target.checked)} />계좌·날짜·순서·금액과 예상 잔고를 확인했습니다.</label>
        <button type="button" className="btn btn-primary" disabled={saving || disabled || !confirmed || (!pendingPayload && !ready)} onClick={save}>{saving?'반영 중…':pendingPayload?'동일 요청의 저장 결과 다시 확인':`확인한 알림 ${rows.length}건 장부에 일괄 반영`}</button>
        {!pendingPayload && !ready && <p>위의 확인 항목을 해결하고 최종 확인을 체크하면 반영할 수 있습니다.</p>}
      </>}
      {loading && <p>기존 기록·계좌 잔고 확인 중…</p>}
      {contextError && <p role="alert">조회 실패: {contextError} <button type="button" className="btn btn-secondary" onClick={()=>setReload(n=>n+1)}>다시 조회</button></p>}
      {pendingPayload && <p role="alert">저장 결과가 확정될 때까지 목록을 수정하지 않습니다. 같은 요청으로 다시 확인하면 중복 반영하지 않습니다.</p>}
      {storageError && <p role="alert">임시 저장을 사용할 수 없습니다. 저장 결과 확인 전에는 이 화면을 닫지 마세요.</p>}
      {message && <p role="status">{message}</p>}
      <details><summary>알림 반영 이력·묶음 취소</summary>{batches.map(batch=><p key={batch.id}>{new Date(batch.created_at).toLocaleString('ko-KR',{timeZone:'Asia/Seoul'})} · {batch.result.items?.length || 0}건 {batch.reversed_at?'(취소됨)':<button type="button" className="btn btn-secondary btn-sm" disabled={saving} onClick={()=>undo(batch.id)}>이 묶음 취소</button>}</p>)}</details>
      <details><summary>지원 범위·기록 안내</summary><p>국내 매수 전량 체결, 원화 입금, USD 외화매수 알림을 지원합니다. 출금·부분 체결·달러 매도 환전은 직접 입력해주세요. 연도가 없는 알림은 화면의 체결 날짜 연도로 해석하므로 과거 알림은 적용 날짜를 확인하세요. 등록 전 목록은 이 기기에 30일간 임시 저장됩니다. 환전 원가는 실제 원화 지출액으로 계산하고 고시환율도 보존합니다. 한 묶음에서 오류가 나면 전부 반영하지 않습니다.</p></details>
    </div>}
  </section>;
}
