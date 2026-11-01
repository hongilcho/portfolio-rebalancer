/** Pure input helpers. Do not change funding, fee or draft persistence rules. */
function firstBy(items, field) {
  const result=new Map();
  for(const item of items){const key=String(item[field]);if(!result.has(key))result.set(key,item);}
  return result;
}
export function tradeFormLookups(assets, accounts, ledgers) {
  const allowedByAccount=new Map();
  for(const asset of assets)for(const accountId of new Set((asset.allowed_accounts || []).map(String))){
    if(!allowedByAccount.has(accountId))allowedByAccount.set(accountId,[]);
    allowedByAccount.get(accountId).push(asset);
  }
  return {assets:firstBy(assets,'id'),accounts:firstBy(accounts,'id'),ledgers:firstBy(ledgers,'account_id'),allowedByAccount};
}
export function updateTradeRow(row,id,field,value,{assets,usdPriceMap,priceMap,usdKrw}) {
  if(row.id!==id)return row;
  const updated={...row,[field]:value};
  if(field==='assetId'||field==='accountId'){updated.costsConfirmed=false;updated.feesKrw=0;updated.feesUsd=0;}
  if(field==='assetId'&&value){
    const asset=assets.find(a=>String(a.id)===String(value));
    if(asset?.market==='US'){
      updated.price=usdPriceMap[String(value)] || (priceMap[String(value)]?Number((priceMap[String(value)]/(usdKrw||1380)).toFixed(2)):0);
      updated.exchangeRate=row.exchangeRate||usdKrw;
    }else{updated.price=priceMap[String(value)]||0;updated.exchangeRate=1.0;}
  }
  return updated;
}
