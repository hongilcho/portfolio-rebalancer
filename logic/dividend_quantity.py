"""One immutable trade timeline for dividend ex-dates; no IO or book changes."""
from bisect import bisect_left
from itertools import groupby
from logic.trade_accounting import trade_sort_key


class DividendQuantityIndex:
    def __init__(self, trades):
        self.days, self.quantities = [], []
        self.initial_terms, self.initial_counts = [], []
        self.first_reset = None
        self.cutoffs = {}
        quantity = 0.0
        ordered = sorted(trades, key=trade_sort_key)
        for day, group in groupby(ordered, key=lambda t: str(t.get('trade_date', ''))):
            rows = list(group)
            resets = [t for t in rows if t.get('trade_type') == 'INIT']
            if resets:
                if self.first_reset is None: self.first_reset = len(self.days)
                # Existing INIT semantics mean an end-of-day snapshot: ignore
                # same-day BUY/SELL, including multiple legacy INIT rows.
                quantity = float(resets[-1].get('quantity') or 0.0)
            else:
                for trade in rows:
                    kind = trade.get('trade_type')
                    if kind in ('BUY', 'SELL'):
                        value = float(trade.get('quantity') or 0.0) * (1 if kind == 'BUY' else -1)
                        quantity += value
                        if self.first_reset is None: self.initial_terms.append(value)
            self.initial_counts.append(len(self.initial_terms))
            self.days.append(day)
            self.quantities.append(quantity)

    def before(self, ex_date):
        if ex_date not in self.cutoffs:
            index = bisect_left(self.days, ex_date) - 1
            if index < 0: value = 0.0
            elif self.first_reset is None or index < self.first_reset:
                # Python's builtin sum has different float accumulation than +=.
                # Retain its exact pre-INIT result, once per distinct ex-date.
                value = sum(self.initial_terms[:self.initial_counts[index]])
            else: value = self.quantities[index]
            self.cutoffs[ex_date] = max(0.0, value)
        return self.cutoffs[ex_date]


class DividendHistoryContext:
    """Only one history() call owns this cache; sources remain unchanged."""
    def __init__(self):
        self.sources = {}

    def index(self, trades, account_id, asset_id):
        token = id(trades)
        if token not in self.sources:
            groups = {}
            for trade in trades:
                key = str(trade.get('account_id', '')), str(trade.get('asset_id', ''))
                groups.setdefault(key, []).append(trade)
            self.sources[token] = (trades, groups, {})  # Hold reference against id reuse.
        _, groups, indexes = self.sources[token]
        key = str(account_id), str(asset_id)
        if key not in indexes: indexes[key] = DividendQuantityIndex(groups.get(key, []))
        return indexes[key]
