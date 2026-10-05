"""Decimal arithmetic for an explicitly initialized USD cash cost pool."""
from decimal import Decimal


def number(value):
    result = Decimal(str(value))
    if not result.is_finite():
        raise ValueError('금액과 환율은 유한한 숫자여야 합니다.')
    return result


def positive(value):
    result = number(value)
    if result <= 0:
        raise ValueError('금액과 환율은 0보다 커야 합니다.')
    return result


def average(usd, cost):
    usd, cost = number(usd), number(cost)
    return cost / usd if usd > 0 else Decimal(0)


def receive(usd, cost, amount, krw_cost):
    amount, krw_cost = positive(amount), positive(krw_cost)
    return number(usd) + amount, number(cost) + krw_cost


def spend(usd, cost, amount):
    usd, cost, amount = number(usd), number(cost), positive(amount)
    if amount > usd + Decimal('0.00000001'):
        raise ValueError('달러 예수금이 부족합니다. 실제 환전 후 환전 기록을 먼저 등록해주세요.')
    assigned = amount * average(usd, cost)
    remaining = max(Decimal(0), usd - amount)
    return remaining, max(Decimal(0), cost - assigned) if remaining else Decimal(0), assigned
