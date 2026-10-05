"""Daily closing valuation worker; no changes to accounts, trades or live prices."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
import logging
import os
import threading
from backend.performance_valuation import current_nav
from data import data_manager as dm
from data.repository_context import RepositoryContext
from data.repositories import close_jobs
from logic import close_calendar as trading
from logic.closing_prices import ClosingPrices, held_assets, CloseUnavailable

log = logging.getLogger(__name__)


def enabled():
    return os.getenv('PERFORMANCE_CLOSE_SCHEDULER_ENABLED', '1').lower() not in ('0', 'false', 'off')


def context():
    return RepositoryContext(dm.get_connection, dm.generate_id, dm.clear_all_caches)


def clock():
    return datetime.now(timezone.utc)


class ClosePerformance:
    def __init__(self, ctx=None, prices=None, read_ledger=None, now=None, jobs=None):
        self.ctx = ctx or context()
        self.prices = prices or ClosingPrices()
        self.read_ledger = read_ledger or dm.get_rebalance_batch_data
        self.now = now or clock
        self.jobs = jobs or close_jobs

    def schedule(self, now, pid=None):
        today = now.astimezone(trading.KST).date()
        end = today if trading.is_session(today) and now >= trading.cutoff(today) else today-timedelta(days=1)
        for track in self.jobs.tracking(self.ctx):
            if pid and track['portfolio_id'] != pid:
                continue
            start = track['close_started_on']
            if track.get('last_job_date'):
                start = max(start, track['last_job_date']+timedelta(days=1))
            days = [d for d in trading.sessions(start, end) if trading.cutoff(d) >= track['created_at']]
            self.jobs.schedule(self.ctx, track['portfolio_id'], days, today)

    def collect(self, job):
        day = job['snapshot_date']
        now = self.now()
        today = now.astimezone(trading.KST).date()
        inputs = job.get('inputs') or {}
        if day != today and ('ledger' not in inputs or 'fx' not in inputs):
            self.jobs.fail(self.ctx, job, now, '당시 장부·환율이 없어 과거 종가 평가액을 만들지 않습니다.', missed=True)
            return False
        if 'ledger' not in inputs:
            inputs = {'ledger': self.read_ledger(job['portfolio_id']), 'ledger_at': now.isoformat(),
                      'valuation_at': trading.cutoff(day).isoformat(),
                      'previous_close_date': trading.previous_session(day).isoformat(), 'prices': {}}
            self.jobs.progress(self.ctx, job, inputs, self.now())
        if 'fx' not in inputs:
            inputs['fx'] = self.prices.exchange_rate(now)
            self.jobs.progress(self.ctx, job, inputs, self.now())
        fx = inputs['fx']['rate']
        missing = [a for a in held_assets(inputs['ledger']) if a['id'] not in inputs['prices']]
        errors = []
        # Small bounded pool; successes survive a provider failure/restart.
        with ThreadPoolExecutor(max_workers=4) as pool:
            pending = {pool.submit(self.prices.asset, a, day, fx): a for a in missing}
            for future in as_completed(pending):
                asset = pending[future]
                try:
                    inputs['prices'][asset['id']] = future.result()
                    self.jobs.progress(self.ctx, job, inputs, self.now())
                except close_jobs.LeaseLost:
                    raise
                except Exception:
                    errors.append(asset.get('name') or asset['id'])
        if errors:
            raise CloseUnavailable('종가 미수집: '+', '.join(errors)+' · 5분 뒤 재시도합니다.')
        value = current_nav(inputs['ledger'], {k: v['price_krw'] for k, v in inputs['prices'].items()}, fx)
        self.jobs.finish(self.ctx, job, value, inputs, self.now())
        return True

    def tick(self, pid=None):
        self.schedule(self.now(), pid)
        saved = False
        # Bound one cycle; the next poll resumes remaining portfolios/days.
        for _ in range(8):
            job = self.jobs.claim(self.ctx, self.now(), pid)
            if not job:
                break
            try:
                saved = self.collect(job) or saved
            except close_jobs.LeaseLost:
                log.info('Closing worker lease handed off')
            except CloseUnavailable as exc:
                self.jobs.fail(self.ctx, job, self.now(), str(exc))
            except Exception:
                # Never persist DB URLs or provider exception text containing keys.
                log.warning('Closing collection failed; retry scheduled', exc_info=False)
                self.jobs.fail(self.ctx, job, self.now(), '종가 수집·저장에 실패했습니다. 5분 뒤 재시도합니다.')
        return saved

    def request(self, pid):
        now = self.now()
        day = now.astimezone(trading.KST).date()
        self.schedule(now, pid)
        if not trading.is_session(day) or now < trading.cutoff(day):
            return {'saved': False, 'message': '오늘은 휴장일이거나 종가 기록 예정 시각 전입니다. 기존 기록을 유지합니다.'}
        ready = self.jobs.request_today(self.ctx, pid, day, now, self.read_ledger(pid))
        saved = self.tick(pid) if ready else False
        return {'saved': saved, 'message': '종가 기록을 완료했습니다.' if saved else
                '종가 수집 상태를 확인해주세요. 오후 4시 이후 등록한 시작 기준은 다음 거래일부터 기록합니다.'}


def schedule_info(now=None):
    now = now or clock()
    day = now.astimezone(trading.KST).date()
    for offset in range(15):
        candidate = day+timedelta(days=offset)
        if trading.is_session(candidate) and trading.cutoff(candidate) > now:
            return {'enabled': enabled(), 'timezone': 'Asia/Seoul', 'next_at': trading.cutoff(candidate).isoformat()}
    return {'enabled': enabled(), 'timezone': 'Asia/Seoul', 'next_at': None}


def start_scheduler():
    stop = threading.Event()
    if not enabled():
        return stop, None
    def loop():
        worker = ClosePerformance()
        while not stop.is_set():
            try:
                worker.tick()
            except Exception:
                log.warning('Closing scheduler will retry on next poll', exc_info=False)
            stop.wait(30)
    thread = threading.Thread(target=loop, name='performance-close', daemon=True)
    thread.start()
    return stop, thread
