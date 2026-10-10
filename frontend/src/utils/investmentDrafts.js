import {draftStorage,readTradeDraft} from './tradeDraft.js';
import {readNoticeDraft} from './nhNotices.js';
import {readPendingRequest} from './bookkeepingRequest.js';
// Even a completed task can have a committed request whose response was lost.
export function pendingInvestmentSteps(cycle,portfolioId) {
  if(!cycle)return [];
  return cycle.steps.filter(step=>{
    const storage=draftStorage(`execution/${cycle.id}/${step.id}`);
    return Boolean(readTradeDraft(storage,portfolioId)?.pendingSubmission
      || readNoticeDraft(portfolioId,storage)?.pendingPayload
      || ['manual-transfer','manual-funds','manual-forex'].some(kind=>readPendingRequest(`${kind}/v1/${portfolioId}`,storage)));
  });
}
