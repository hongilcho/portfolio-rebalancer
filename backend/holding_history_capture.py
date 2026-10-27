"""Daily enrichment on the existing scheduler. No brokerage or ledger writes."""
from datetime import timedelta
from time import monotonic
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
    def __init__(self,ctx,holdings=None,prices=None,status=None,repo=None):
        from data.repositories import holding_history
        from data.data_manager import get_crypto_holdings
        from logic.crypto_price_fetcher import get_crypto_prices,get_crypto_status
        self.ctx=ctx;self.holdings=holdings or get_crypto_holdings;self.prices=prices or get_crypto_prices
        self.status=status or get_crypto_status;self.repo=repo or holding_history;self.next_at=None
    def tick(self,now):
        day=now.astimezone(trading.KST).date()
        if not trading.is_session(day):return False
        cutoff=trading.cutoff(day)
        # Never turn a later live quote or today's holdings into an old record.
        if not cutoff<=now<=cutoff+timedelta(minutes=10) or (self.next_at and now<self.next_at):return False
        self.next_at=now+timedelta(minutes=1)
        if self.repo.crypto_exists(self.ctx,day):
            self.next_at=cutoff+timedelta(hours=12);return False
        started=monotonic()
        holdings=self.holdings();prices=self.prices();state=self.status()
        observed_at=now+timedelta(seconds=monotonic()-started)
        updated=state.get('updated_at')
        if not updated or state.get('stale') or state.get('refresh_failed') or state.get('refreshing'):return False
        # Cache timestamp is Unix seconds. Quotes before the cutoff are not a
        # same-time observation, even when their prices happen to be unchanged.
        if observed_at>cutoff+timedelta(minutes=10):return False
        if not cutoff.timestamp()<=float(updated)<=observed_at.timestamp()+5:return False
        metrics=crypto(holdings,prices)
        return self.repo.capture_crypto(self.ctx,day,observed_at,{'metrics':metrics,'holdings':holdings,
            'prices':prices,'quote_at':updated,'valuation_at':observed_at.isoformat(),'basis':'KRX_CLOSE_WINDOW_OBSERVATION'})
