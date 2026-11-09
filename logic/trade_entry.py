"""Pure validation and position arithmetic for manual trade entry.

SQL, row locks, deduplication and transaction ownership remain in the repository.
This is deliberately separate from replay: INIT rounding and historical rules
are not interchangeable between the two existing paths.
"""
import json
import re
from datetime import date


def validate_trade_day(trade_date, today):
    day = date.fromisoformat(str(trade_date))
    if day.isoformat() != str(trade_date) or day > today:
        raise ValueError('실제 체결일은 오늘까지의 올바른 날짜여야 합니다.')


def selected_asset_currency(asset, account_id, currency):
    if not asset or asset['portfolio_id'] != asset['account_portfolio'] or asset['is_deposit']:
        raise ValueError('계좌와 같은 포트폴리오의 주식·ETF·금 종목을 선택해주세요.')
    allowed = asset['allowed_accounts'] or []
    if isinstance(allowed, str): allowed = json.loads(allowed)
    if str(account_id) not in map(str, allowed):
        raise ValueError('이 계좌에 허용된 종목이 아닙니다.')
    is_us = asset['market'] == 'US'
    currency = currency or ('USD' if is_us else 'KRW')
    if currency != ('USD' if is_us else 'KRW'):
        raise ValueError('미국 종목은 달러 단가, 국내 종목은 원화 단가로 입력해주세요.')
    return is_us, currency


def validate_notice_fields(import_source, broker_order_no, trade_type, currency, quantity, trade_date):
    if import_source != 'NAMUH_KAKAO' or not re.fullmatch(r'[0-9]{1,10}', broker_order_no or ''):
        raise ValueError('가져오기 출처 또는 주문번호를 확인해주세요.')
    if trade_type not in ('BUY', 'SELL') or currency != 'KRW' or quantity != int(quantity):
        raise ValueError('체결 메시지 가져오기는 국내 원화 매수·매도만 지원합니다.')
    if date.fromisoformat(trade_date).isoformat() != trade_date:
        raise ValueError('체결일을 확인해주세요.')


def validate_notice_asset(imported_asset, account_id):
    if not imported_asset or imported_asset['market'] != 'KR' or imported_asset['is_deposit'] or imported_asset['portfolio_id'] != imported_asset['account_portfolio']:
        raise ValueError('계좌와 같은 포트폴리오의 국내 종목을 선택해주세요.')
    allowed = imported_asset['allowed_accounts'] or []
    if isinstance(allowed, str):
        allowed = json.loads(allowed)
    if str(account_id) not in map(str, allowed):
        raise ValueError('이 계좌에 허용된 종목이 아닙니다.')


def position_after_trade(row, trade_type, quantity, price, currency, exchange_rate, is_us):
    """Return (quantity, KRW average, USD average, acquisition FX).

    Callers handle missing-position sales before this function, preserving their
    current error and transaction behavior. Inputs are never mutated.
    """
    if row:
        curr_qty = float(row['quantity'] or 0.0)
        curr_avg_price = float(row['avg_price'] or 0.0)
        curr_avg_usd = float(row.get('avg_price_usd') or 0.0)
        curr_buy_fx = float(row.get('buy_fx_rate') or 0.0)
        if curr_buy_fx == 0.0 and curr_avg_usd > 0 and curr_avg_price > 0:
            curr_buy_fx = curr_avg_price / curr_avg_usd

        if trade_type == 'INIT':
            new_qty = quantity
            if is_us or currency == 'USD':
                new_avg_usd = price
                new_buy_fx = exchange_rate
                new_avg_price = round(new_avg_usd * new_buy_fx, 2)
            else:
                new_avg_price = price
                new_avg_usd = 0.0
                new_buy_fx = 0.0
        elif trade_type == 'BUY':
            new_qty = curr_qty + quantity
            if new_qty > 0:
                if is_us or currency == 'USD':
                    c_usd_0 = curr_qty * curr_avg_usd
                    c_krw_0 = c_usd_0 * curr_buy_fx
                    c_usd_new = quantity * price
                    c_krw_new = c_usd_new * exchange_rate

                    total_c_usd = c_usd_0 + c_usd_new
                    total_c_krw = c_krw_0 + c_krw_new

                    new_avg_usd = total_c_usd / new_qty
                    new_buy_fx = (total_c_krw / total_c_usd) if total_c_usd > 0 else exchange_rate
                    new_avg_price = total_c_krw / new_qty
                else:
                    new_avg_price = ((curr_qty * curr_avg_price) + (quantity * price)) / new_qty
                    new_avg_usd = 0.0
                    new_buy_fx = 0.0
            else:
                new_avg_price = price
                new_avg_usd = price if (is_us or currency == 'USD') else 0.0
                new_buy_fx = exchange_rate if (is_us or currency == 'USD') else 0.0
        else: # SELL
            if quantity > curr_qty + 1e-9:
                raise ValueError("매도할 보유 수량이 부족합니다.")
            new_qty = curr_qty - quantity
            new_avg_price = curr_avg_price
            new_avg_usd = curr_avg_usd
            new_buy_fx = curr_buy_fx
            if new_qty <= 0:
                new_qty = 0.0
                new_avg_price = 0.0
                new_avg_usd = 0.0
                new_buy_fx = 0.0

    else:
        new_qty = quantity
        if is_us or currency == 'USD':
            new_avg_usd = price
            new_buy_fx = exchange_rate
            new_avg_price = round(price * exchange_rate, 2)
        else:
            new_avg_price = price
            new_avg_usd = 0.0
            new_buy_fx = 0.0
    return new_qty, new_avg_price, new_avg_usd, new_buy_fx
