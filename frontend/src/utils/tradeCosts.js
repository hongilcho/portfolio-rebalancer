export function feePayload(row,isUS){
  if(!row.costsConfirmed)return {};
  const krw=Number(row.feesKrw ?? 0),usd=isUS?Number(row.feesUsd ?? 0):0;
  if(!Number.isFinite(krw)||!Number.isFinite(usd)||krw<0||usd<0||krw>1e12||usd>1e12)throw Error('수수료·세금은 0 이상 허용 범위의 금액으로 입력해주세요.');
  return {fees_krw:krw,fees_usd:usd};
}
export function remainingSellQuantity(row,rows,holdings){
  const held=Number(holdings.find(h=>String(h.asset_id)===String(row.assetId))?.quantity)||0;
  return Math.max(0,held-rows.filter(r=>r.id!==row.id&&String(r.accountId)===String(row.accountId)&&String(r.assetId)===String(row.assetId)).reduce((s,r)=>s+(Number(r.quantity)||0),0));
}
