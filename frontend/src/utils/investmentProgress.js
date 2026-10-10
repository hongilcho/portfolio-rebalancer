// Presentation only. Server-side bookkeeping remains the authority for balances.
const positive = value => Number.isFinite(Number(value)) && Number(value) > 0;
const tradeKinds = new Set(['BUY', 'SELL']);

export function investmentStepProgress(step, results = []) {
  const trades = tradeKinds.has(step.kind);
  const target = Number(trades ? step.target_quantity : step.target_amount);
  const seen = new Set();
  const linked = results.filter(result => {
    if (!result.id || seen.has(result.id) || result.step_id !== step.id || result.voided
      || result.kind !== step.kind || result.account_id !== step.account_id || result.currency !== step.currency
      || (trades && result.asset_id !== step.asset_id)) return false;
    seen.add(result.id);
    return true;
  });
  const recorded = linked.filter(result => result.ledger_status === 'RECORDED');
  const valueOf = result => Number(trades ? result.quantity : result.amount);
  const invalid = recorded.some(result => !positive(valueOf(result)));
  const value = recorded.reduce((sum, result) => sum + (positive(valueOf(result)) ? valueOf(result) : 0), 0);
  const excluded = step.status === 'EXCLUDED';
  const review = invalid || !positive(target) || linked.some(result => result.ledger_status !== 'RECORDED') || Boolean(step.review_required);
  const complete = !excluded && !review && (step.satisfied_by_existing_cash === true || value >= target - 1e-7);
  return { step, target, value, remaining: Math.max(0, target - value), excess: Math.max(0, value - target),
    recorded, excluded, review, complete, partial: value > 0 && !complete };
}

export function investmentProgress(cycle) {
  const steps = (cycle?.steps || []).map(step => investmentStepProgress(step, cycle?.results || []));
  const byId = new Map(steps.map(progress => [progress.step.id, progress]));
  for (const progress of steps) {
    progress.ready = !['CLOSED','PAUSED'].includes(cycle?.status) && !progress.complete && !progress.excluded && !progress.review
      && (progress.step.depends_on || []).every(id => byId.get(id)?.complete);
  }
  const complete = steps.filter(item => item.complete);
  const remaining = steps.filter(item => !item.complete && !item.excluded);
  const current = cycle?.status === 'CLOSED' || cycle?.status === 'PAUSED' ? null : remaining.find(item => item.ready);
  return { steps, complete, remaining, current, ready: remaining.filter(item => item.ready),
    review: remaining.filter(item => item.review), total: steps.filter(item => !item.excluded).length };
}
