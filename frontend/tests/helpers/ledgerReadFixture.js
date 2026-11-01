// Preserve existing loaded-view SSR fixtures after their state moved into a hook.
export function ledgerReadFixtureEdit(node, source, seed) {
  if (node.type !== 'CallExpression' || node.callee?.name !== 'useLedgerRead') return null;
  const kind = node.arguments[0]?.value;
  const key = kind === 'usd' ? 'usdLedgers' : kind === 'holdings' ? 'accountHoldingsMap' : null;
  if (!key) return null;
  const data = kind === 'usd' ? `{ledgers:${seed}.${key}}` : `{holdings:Object.values(${seed}.${key}).flat()}`;
  return {start:node.start,end:node.end,text:`(Object.hasOwn(${seed},'${key}') ? {data:${data},loading:false,stale:false,error:'',refresh:async()=>{}} : (${source.slice(node.start,node.end)}))`};
}
