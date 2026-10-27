"""Read-only corroboration of legacy frozen books, never ledger repair.

Confirmed openings validate quantities only. Their costs and today's holding
fields are never substituted into a historical valuation or dividend receipt.
"""
from collections import defaultdict
from datetime import date, timedelta
import math

from logic.realized_opening import active, validity
from logic.trade_accounting import trade_sort_key


def pair(row):
    return str(row['account_id']), str(row['asset_id'])


def quantity(row):
    value = float(row['quantity'])
    if not math.isfinite(value) or value < 0:
        raise ValueError('보유 수량 근거 확인 필요')
    return value


def delta(rows):
    if any(t['trade_type'] not in ('BUY', 'SELL') for t in rows):
        return None  # Never reverse an INIT across an unknown reset boundary.
    return sum(quantity(t) * (1 if t['trade_type'] == 'BUY' else -1) for t in rows)


def with_dividend_start(holding, trades):
    """Mirror overview's MIN(trade_date)/legacy sentinel convention, on a copy."""
    result = dict(holding)
    if str(result.get('min_trade_date') or '')[:10] <= '2000-01-01':
        earliest = min((str(t['trade_date'])[:10] for t in trades), default='')
        if earliest:
            result['min_trade_date'] = '2026-07-01' if earliest <= '2000-01-01' else earliest
    return result


def dividend_start(holding):
    first = str(holding.get('first_buy_date') or '')[:10]
    if not first or first <= '2000-01-01':
        first = str(holding.get('min_trade_date') or '')[:10]
    return first if first > '2000-01-01' else ''


def dividend_quantity(trades, ex_date):
    """Same end-of-INIT-day interpretation as the existing dividend engine."""
    prior = sorted((t for t in trades if str(t['trade_date'])[:10] < ex_date), key=trade_sort_key)
    resets = [t for t in prior if t['trade_type'] == 'INIT']
    if resets:
        reset = resets[-1]
        changes = delta([t for t in prior if str(t['trade_date'])[:10] > str(reset['trade_date'])[:10]])
        return None if changes is None else quantity(reset) + changes
    return delta(prior)


def purchase_history_quantity(trades, ex_date):
    """Corroborate legacy EOD resets against actual cumulative BUY/SELL rows.

    An INIT is not discarded merely because it looks old. Every included reset
    must equal that day's independently replayed purchases minus sales. A true
    opening position with missing purchases, or a conflicting reset, fails.
    """
    days = defaultdict(list)
    for trade in trades:
        if str(trade['trade_date'])[:10] < ex_date:
            days[str(trade['trade_date'])[:10]].append(trade)
    balance = 0.0
    for day in sorted(days):
        resets = []
        for trade in sorted(days[day],key=trade_sort_key):
            kind = trade['trade_type']
            if kind == 'INIT':resets.append(trade)
            elif kind in ('BUY','SELL'):
                balance += quantity(trade) * (1 if kind=='BUY' else -1)
                if balance < -1e-6:return None
            else:return None
        if any(abs(quantity(t)-balance) >= 1e-6 for t in resets):return None
    return balance


class Evidence:
    def __init__(self, snapshots=(), trades=(), receipts=()):
        self.trades = defaultdict(list)
        self.books = {}
        for trade in trades:
            self.trades[pair(trade)].append(trade)
        for snapshot in snapshots:
            payload = snapshot.get('payload') or {}
            if (payload.get('holding_metrics') or {}).get('status') == 'UNCONFIRMED':
                continue
            ledger = payload.get('ledger', payload)
            for holding in ledger.get('holdings', []):
                self.books[(str(snapshot['snapshot_date']), pair(holding))] = holding
        self.openings = {pair(p): p for p in active(receipts)}

    def expected(self, holding, day):
        """Independent quantity, with no intervening reset or conflicting proof."""
        key = pair(holding)
        rows = self.trades[key]
        candidates = []
        opening = self.openings.get(key)
        if opening and not validity(opening, rows):
            covered = opening['covered_trades']
            if day < opening['date']:
                between = [t for t in rows if str(t['id']) in covered
                           and day < str(t['trade_date'])[:10] <= opening['date']]
                change = delta(between)
                if change is not None:
                    candidates.append(quantity(opening) - change)
            else:
                later = [t for t in rows if str(t['id']) not in covered
                         and str(t['trade_date'])[:10] <= day]
                # Date-only data cannot order a new trade against same-day confirmation.
                change = None if any(str(t['trade_date'])[:10] <= opening['date'] for t in later) else delta(later)
                if change is not None:
                    candidates.append(quantity(opening) + change)

        resets = [t for t in rows if t['trade_type'] == 'INIT' and str(t['trade_date'])[:10] > day]
        if resets:
            reset_day = min(str(t['trade_date'])[:10] for t in resets)
            same_day = [t for t in resets if str(t['trade_date'])[:10] == reset_day]
            book = self.books.get((reset_day, key))
            # Duplicate identical legacy resets are corroboration, not extra shares.
            if book and all(abs(quantity(t) - quantity(book)) < 1e-6 for t in same_day):
                between = [t for t in rows if t['trade_type'] != 'INIT'
                           and day < str(t['trade_date'])[:10] <= reset_day]
                change = delta(between)
                if change is not None:
                    candidates.append(quantity(book) - change)
        if not candidates or any(not math.isfinite(q) or q < 0 for q in candidates):
            return None
        if any(abs(q - candidates[0]) >= 1e-6 for q in candidates):
            raise ValueError('확정 기준과 저장 수량의 근거가 서로 다릅니다.')
        return candidates[0]

    def supports(self, holding, trades, records, day):
        expected = self.expected(holding, day)
        if expected is None or abs(expected - quantity(holding)) >= 1e-6:
            return False
        # Endpoint agreement alone cannot certify a dividend's earlier quantity.
        # Check every relevant ex-date against independent evidence as well.
        for record in records:
            ex_date = str(record['date'])[:10]
            previous = (date.fromisoformat(ex_date) - timedelta(days=1)).isoformat()
            known = self.expected(holding, previous)
            calculated = dividend_quantity(trades, ex_date)
            if known is None:
                # Earlier dividends can have a complete ordinary purchase
                # history, with redundant EOD INITs, before the frozen books.
                # Verify those records; never substitute a later quantity.
                known = purchase_history_quantity(trades,ex_date)
            if known is None or calculated is None or abs(known - calculated) >= 1e-6:
                return False
        return True
