export function planProgress(plan, lineNo) {
  const line = plan.payload.trade_plan[lineNo];
  const links = plan.links.filter(l => l.line_no === lineNo);
  const quantity = links.reduce((n,l) => n+Number(l.quantity),0);
  const amount = links.reduce((n,l) => n+Number(l.quantity)*Number(l.price)*(l.currency === 'USD' ? Number(l.exchange_rate) : 1),0);
  return {links,quantity,amount,remaining:Math.max(0,Number(line.qty)-quantity),excess:Math.max(0,quantity-Number(line.qty))};
}

export function planCandidates(plan, lineNo, candidates) {
  const line = plan.payload.trade_plan[lineNo];
  return candidates.filter(t => Number(t.trade_sequence)>Number(plan.cutoff) && t.account_id===line.account_id && t.asset_id===line.asset_id && t.trade_type===line.type);
}
