"""Opt-in CMA checks; reuse the EXISTING NH process/client/cache only."""
from datetime import datetime, timezone
import logging
import os
import threading
from logic.cma_interest import amount, due_slot, moment, stable_return
from data.repositories import cma
from logic import cma_policy

log = logging.getLogger(__name__)


def enabled():
    return os.getenv('CMA_INTEREST_ENABLED','0') == '1'


def existing_nh_balance(pid, aid, *, start_date=None):
    from data.data_manager import get_all_accounts
    from data.nh_api import nh_api_client
    from data.cma_nh import snapshot,BALANCE
    from logic.cma_interest import observe_balance
    from logic.cma_statement import normalize
    from datetime import timedelta
    account = next((a for a in get_all_accounts(portfolio_id=pid) if str(a['id']) == aid), None)
    if not account or account.get('account_type') != 'CMA':
        raise ValueError('현재 포트폴리오의 CMA 계좌를 확인해주세요.')
    day=moment(datetime.now(timezone.utc)).date()
    from datetime import date
    start=date.fromisoformat(start_date) if start_date else day
    if not 0<=(day-start).days<=30:raise ValueError('CMA 미확인 기간이 30일을 넘었습니다. 기존 명세를 검토해주세요.')
    data=snapshot(nh_api_client,account['account_no'],(start-timedelta(days=1)).isoformat(),day.isoformat())
    balance=data['queries'][BALANCE]['pages'][-1]['data']
    evidence=observe_balance(balance,moment(data['observed_at']))
    evidence['statement']=normalize(data,evidence,pid=pid,aid=aid,start_date=start.isoformat())
    return evidence


def poll(db, pid, aid, *, provider=existing_nh_balance):
    book = cma.read_book(db,pid,aid)
    evidence = provider(pid,aid,start_date=book.get('source_start')) if provider is existing_nh_balance else provider(pid,aid)
    receipt=cma.reconciliation_for(db,pid,aid,book,evidence)
    return cma.record_observation(db,pid,aid,evidence,book['book_token'],reconciliation=receipt)


class DailyCMA:
    def __init__(self, db, *, provider=existing_nh_balance, clock=lambda:datetime.now(timezone.utc), repo=cma):
        self.db,self.provider,self.clock,self.repo = db,provider,clock,repo

    def tick(self):
        now = moment(self.clock())
        if due_slot(now,set()) is None:
            return []
        results = []
        for policy in self.repo.policies(self.db):
            aid,pid = policy['account_id'],policy['portfolio_id']
            checks = self.repo.check_slots(self.db,aid,now.date())
            if any(r['state'] in ('APPLIED','NO_CHANGE') for r in checks):
                continue
            slot = due_slot(now,{r['slot'] for r in checks})
            if slot is None or not self.repo.claim_check(self.db,aid,now.date(),slot):
                continue
            state = 'CHECK_FAILED'
            try:
                book = self.repo.read_book(self.db,pid,aid)
                evidence = self.provider(pid,aid,start_date=book.get('source_start')) if self.provider is existing_nh_balance else self.provider(pid,aid)
                receipt=self.repo.reconciliation_for(self.db,pid,aid,book,evidence)
                obs = self.repo.record_observation(self.db,pid,aid,evidence,book['book_token'],reconciliation=receipt)
                state = obs['state']
                if state == 'CASH_RETURNED':
                    proposal = self.repo.preview(self.db,pid,aid,obs['id'],self.clock())
                    previous = self.repo.previous_observation(self.db,aid,obs['id'])
                    state = 'AWAITING_STABLE_RETURN'
                    if stable_return(previous,obs):
                        state = 'NO_CHANGE' if amount(proposal['interest_krw']) == 0 else 'REVIEW_INTEREST'
                        if proposal.get('can_apply') is False:state=proposal['status']
                        if policy['auto_apply'] and not cma_policy.writes_enabled():state='WRITE_DISABLED_REVIEW'
                        if state=='NO_CHANGE' and receipt.get('status')!='MATCHED':state='STATEMENT_REQUIRED'
                        if state == 'REVIEW_INTEREST' and policy['auto_apply'] and policy['movements_confirmed']:
                            if not cma_policy.writes_enabled():
                                state='WRITE_DISABLED_REVIEW'
                            elif not cma_policy.automatic_ready() or receipt.get('status')!='MATCHED':
                                state='STATEMENT_REQUIRED'
                            elif any(amount(item['amount_krw'])>amount(policy['max_auto_interest']) for item in receipt.get('paid_items',[])) or (not receipt.get('paid_items') and amount(proposal['interest_krw']) > amount(policy['max_auto_interest'])):
                                state = 'AUTO_LIMIT_REVIEW'
                            else:
                                self.repo.commit(self.db,pid,dict(request_id=f'CMA-DAY-{aid}-{now.date()}',
                                    account_id=aid,observation_id=obs['id'],book_token=obs['book_token'],
                                    interest_krw=proposal['interest_krw'],confirmed_movements=True,automatic=True),self.clock())
                                state = 'APPLIED'
            except Exception:
                state = 'CHECK_FAILED_REVIEW'
            self.repo.finish_check(self.db,aid,now.date(),slot,state)
            results.append(dict(account_id=aid,slot=slot,state=state))
        return results


def start_scheduler():
    stop = threading.Event()
    if not enabled():
        return stop,None
    from backend.routers.plans import context
    worker = DailyCMA(context())
    def loop():
        while not stop.is_set():
            try:
                worker.tick()
            except Exception:
                log.warning('CMA check deferred; existing ledger retained')
            stop.wait(30)
    thread = threading.Thread(target=loop,name='cma-income',daemon=True)
    thread.start()
    return stop,thread
