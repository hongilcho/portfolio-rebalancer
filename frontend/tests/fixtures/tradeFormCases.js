const noop=()=>{};
const accounts=[{id:'kr',account_type:'ISA',account_alias:'합성 ISA'},{id:'us',account_type:'GENERAL',account_alias:'합성 USD'}];
const assets=[{id:'bond',name:'합성 채권',market:'KR',allowed_accounts:['kr'],ticker:'QA001'},
 {id:'vt',name:'합성 VT',market:'US',allowed_accounts:['us'],ticker:'VT'}];
const buyRows=[{id:'b1',accountId:'kr',assetId:'bond',quantity:3,price:100,exchangeRate:1},
 {id:'b2',accountId:'us',assetId:'vt',quantity:2,price:101.5,exchangeRate:1300}];
const sellRows=[{id:'s1',accountId:'kr',assetId:'bond',quantity:1,price:110,exchangeRate:1},
 {id:'s2',accountId:'us',assetId:'vt',quantity:.5,price:110,exchangeRate:1400}];
const base={tradeDate:'2026-10-30',accounts,assets,buyRows,sellRows,usdKrw:1400,
 accountHoldingsMap:{kr:[{asset_id:'bond',asset_name:'합성 채권',quantity:8}],us:[{asset_id:'vt',asset_name:'합성 VT',quantity:5.5}]},
 usdLedgers:[{account_id:'us',average_rate:1338.33,usd_balance:1000}],
 setTradeDate:noop,updateBuyRow:noop,updateSellRow:noop,removeBuyRow:noop,removeSellRow:noop,addBuyRow:noop,addSellRow:noop,handleSaveBatchTrades:noop};
export const tradeFormCases=[['two-columns',base],['focused-buy',{...base,focused:true}],
 ['sell-task-stale',{...base,focused:true,executionStep:{kind:'SELL'},balancesPending:true}],
 ['locked',{...base,disabled:true}]];
