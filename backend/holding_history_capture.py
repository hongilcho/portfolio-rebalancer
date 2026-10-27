"""Daily enrichment on the existing scheduler. No brokerage or ledger writes."""
from datetime import timedelta
from logic.holding_history import financial,crypto
from logic import close_calendar as trading

def ledger(pid):
    from data.data_manager import get_overview_batch_data
    batch=get_overview_batch_data()
    accounts=[a for a in batch['accounts'] if a['portfolio_id']==pid];aids={a['id'] for a in accounts}
    return {'accounts':accounts,'assets':[a for a in batch['assets'] if a['portfolio_id']==pid],
        'holdings':[h for h in batch['holdings'] if h['account_id'] in aids],
        'trade_history':[t for t in batch['trade_history'] if t['account_id'] in aids],
        'dividend_cache':batch.get('dividend_cache',{})}

def enrich(inputs,day):
    return {**inputs,'holding_metrics':financial(inputs['ledger'],inputs['prices'],inputs['fx']['rate'],day)}

class CryptoCapture:
    def __init__(self,ctx,provider=None,repo=None):
        from data.repositories import crypto_history
        from logic.market_providers.crypto_history import UpbitHistory
        self.ctx=ctx;self.provider=provider or UpbitHistory();self.repo=repo or crypto_history;self.next_at=None;self.retry_after={}

    def tick(self,now):
        from logic import crypto_history as policy
        if self.next_at and now<self.next_at:return False
        self.next_at=now+timedelta(minutes=1)
        state=self.repo.state(self.ctx);current=policy.fingerprint(state['holdings'])
        if not state['events']:
            state['events']=[self.repo.observe(self.ctx,current,now)]
        if state['events'][-1]['fingerprint']!=current:
            raise ValueError('가상자산 보유 변경 이력 확인이 필요합니다.')
        day=now.astimezone(trading.KST).date()
        end=day if now>=policy.cutoff(day) else day-timedelta(days=1)
        start=min(e.get('confirmed_start',policy.moment(e['at']).astimezone(trading.KST).date().isoformat()) for e in state['events'])
        if start>str(end):return False
        # One missing day per pass, including weekends; restart-safe and bounded.
        for target in policy.days(start,end):
            if str(target) in state['dates']:continue
            if self.retry_after.get(target,now)>now:continue
            seed=policy.basis_at(state['events'],target)
            if not seed:continue
            symbols={h['symbol'] for h in seed['holdings'] if h['quantity']>0}
            try:
                quotes=self.provider.prices(target,symbols)
                source='RECORDED' if target==day else 'RECONSTRUCTED'
                payload=policy.record(seed['holdings'],quotes,target,source=source,basis_fingerprint=seed['fingerprint'])
                return self.repo.capture(self.ctx,target,payload,current)
            except Exception:
                self.retry_after[target]=now+timedelta(minutes=10)
                raise  # The outer scheduler logs privately; other days can proceed.
        return False
