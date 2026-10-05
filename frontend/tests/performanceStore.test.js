import test from 'node:test';
import assert from 'node:assert/strict';
import { createPerformanceStore } from '../src/utils/performanceStore.js';

const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };
const active = () => ({ tracking: { revision: 1 }, flows: [], snapshots: [], reports: [] });

test('viewing an unregistered portfolio does not create a baseline or capture', async () => {
  const calls = [];
  const store = createPerformanceStore('first', {
    getPerformance: async pid => { calls.push(pid); return { tracking: null }; },
    capturePerformance: () => { throw new Error('must not capture'); },
  });
  store.setEnabled(true);
  assert.equal(await store.refresh(), true);
  assert.deepEqual(calls, ['first']);
  assert.equal(store.getSnapshot().data.tracking, null);
});

test('viewing registered performance is read-only and never overwrites a close', async () => {
  const calls = [];
  const store = createPerformanceStore('first', {
    getPerformance: async pid => { calls.push(`get:${pid}`); return active(); },
    capturePerformance: async pid => { calls.push(`capture:${pid}`); return { saved: true }; },
  });
  store.setEnabled(true);
  await store.refresh();
  assert.deepEqual(calls, ['get:first']);
  assert.equal(store.getSnapshot().busy, false);
  assert.equal(store.getSnapshot().notice, '');
});

test('user changes wait for the preceding read; its older response cannot erase new flows', async () => {
  const gate = deferred();
  const entered = deferred();
  let flows = [];
  let reads = 0;
  const calls = [];
  const store = createPerformanceStore('first', {
    getPerformance: async () => {
      reads++;
      if (reads === 1) { entered.resolve(); await gate.promise; }
      return { ...active(), flows: [...flows] };
    },
    capturePerformance: async () => { calls.push('capture'); return { saved: true }; },
  });
  store.setEnabled(true);
  const refresh = store.refresh();
  await entered.promise;
  const mutation = store.run(async () => { calls.push('add'); flows = [{ id: 'new-flow' }]; });
  assert.equal(store.getSnapshot().busy, true);
  gate.resolve();
  await Promise.all([refresh, mutation]);
  assert.deepEqual(calls, ['add']);
  assert.deepEqual(store.getSnapshot().data.flows, flows);
  assert.equal(store.getSnapshot().busy, false);
});

test('switching portfolios discards a late old read and stops its pending capture', async () => {
  const gate = deferred();
  const entered = deferred();
  let captures = 0;
  const old = createPerformanceStore('old', {
    getPerformance: async () => { entered.resolve(); return gate.promise; },
    capturePerformance: async () => { captures++; return { saved: true }; },
  });
  old.setEnabled(true);
  const task = old.refresh();
  await entered.promise;
  old.setEnabled(false);
  const next = createPerformanceStore('next', { getPerformance: async pid => ({ tracking: null, scope: pid }) });
  next.setEnabled(true);
  await next.refresh();
  gate.resolve(active());
  await task;
  assert.equal(captures, 0);
  assert.equal(old.getSnapshot().data, null);
  assert.equal(next.getSnapshot().data.scope, 'next');
});

test('rejected changes refresh current records and release the busy state for retry', async () => {
  const store = createPerformanceStore('first', { getPerformance: async () => active() });
  store.setEnabled(true);
  assert.equal(await store.run(async () => { throw new Error('다른 화면에서 기록이 변경됨'); }), false);
  assert.match(store.getSnapshot().error, /기록이 변경됨/);
  assert.equal(store.getSnapshot().data.tracking.revision, 1);
  assert.equal(store.getSnapshot().busy, false);
  assert.equal(await store.run(async () => {}), true);
  assert.equal(store.getSnapshot().error, '');
});

test('explicit close retry retains its warning and the previously recorded evaluation', async () => {
  const data = { ...active(), snapshots: [{ value_krw: 100 }] };
  const store = createPerformanceStore('first', {
    getPerformance: async () => data,
    capturePerformance: async () => ({ saved: false, message: '시세 갱신 중' }),
  });
  store.setEnabled(true);
  await store.run(store.capture);
  assert.equal(store.getSnapshot().notice, '시세 갱신 중');
  assert.equal(store.getSnapshot().data.snapshots[0].value_krw, 100);
});
