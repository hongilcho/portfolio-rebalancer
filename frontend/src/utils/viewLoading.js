/** Start independent visible reads together, sharing the existing history store. */
export function startSummaryAndHistory(loadSummary, historyResource) {
  const summary = loadSummary();
  // The store owns the history error state; a failed graph cannot hide summary.
  void Promise.resolve(historyResource.refresh()).catch(() => {});
  return summary;
}

export function performanceViewActive(activeTab, executionInput) {
  return activeTab === 'tab4' || activeTab === 'tab6'
    || (activeTab === 'tab8' && Boolean(executionInput));
}
