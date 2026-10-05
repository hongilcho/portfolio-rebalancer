export function dividendGroups(accounts) {
  return accounts.flatMap(a => (a.holdings || []).filter(h => !h.is_deposit
    && ((h.dividend_details || []).length || Number(h.dividend_profit_krw) || Number(h.dividend_profit_usd)))
    .map(h => {
      const currency = h.market === 'US' || h.is_us ? 'USD' : 'KRW';
      const details = [...(h.dividend_details || [])].sort((x,y) => String(x.ex_date).localeCompare(String(y.ex_date)));
      const calculated = details.reduce((sum,d) => sum + Number(d.net_amount || 0), 0);
      const reflected = Number(currency === 'USD' ? h.dividend_profit_usd : h.dividend_profit_krw) || 0;
      return { key:`${a.id}/${h.asset_id}`, accountId:String(a.id), assetId:String(h.asset_id), account:a.account_alias,
        name:h.asset_name, currency, details, calculated, reflected,
        adjusted: Math.abs(calculated - reflected) > (currency === 'USD' ? 0.02 : 1) };
    }));
}
