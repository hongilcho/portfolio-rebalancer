"""CMA cash-return observations and interest differences. No IO or estimates."""
from datetime import datetime, timezone, timedelta
from decimal import Decimal, InvalidOperation
import hashlib
import json

KST = timezone(timedelta(hours=9))
CHECK_TIMES = ((9, 0), (12, 0), (15, 40))


def amount(value):
    if isinstance(value, bool) or value is None:
        raise ValueError('CMA 금액이 누락되었거나 올바르지 않습니다.')
    try:
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError('CMA 금액을 확인해주세요.') from None
    if not result.is_finite() or abs(result) > Decimal('1e15'):
        raise ValueError('CMA 금액 범위를 확인해주세요.')
    return result


def moment(value):
    result = value if isinstance(value, datetime) else datetime.fromisoformat(value)
    if result.tzinfo is None:
        raise ValueError('한국 시간으로 확인 가능한 조회 시각이 필요합니다.')
    return result.astimezone(KST)


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(',', ':'),
                                    default=str).encode()).hexdigest()


def observe_balance(data, observed_at):
    """Keep cash distinct from sweep value/withdrawable cash, failing closed.

    The recognized completion envelope must be validated against the actual
    existing account before operations are enabled. No quantity-as-currency
    fallback and no inferred rate, tax or accrued-but-unpaid interest.
    """
    now = moment(observed_at)
    result = dict(observed_at=now.isoformat(), state='UNVERIFIED',
                  cash_krw=None, sweep_krw=None, total_krw=None, withdrawable_krw=None)
    try:
        if not isinstance(data, dict):
            return result
        head, rows = data.get('Output_0'), data.get('Output_1')
        if not isinstance(head, dict) or not isinstance(rows, list) or len(rows) > 1000:
            return result
        # Exact documented common completion text plus complete balance blocks.
        # This conservative profile is not a claim about all NH balance replies.
        if data.get('rsp_cd') not in ('00000','00166') or data.get('rsp_msg') != '조회가 완료되었습니다.':
            return result
        # A separately reported withdrawal limit is useful evidence, but is not
        # a verified account valuation or an interest/cash-return substitute.
        if head.get('drn_pbl_amt') is not None:
            withdrawable = amount(head['drn_pbl_amt'])
            if withdrawable < 0:
                return result
            result['withdrawable_krw'] = str(withdrawable)
        cash = amount(head.get('dca'))
        if cash < 0:
            return result
        result['cash_krw'] = str(cash)
        settlement_differs = head.get('nxt2_dd_dca') is not None and amount(head['nxt2_dd_dca']) != cash
        sweep = Decimal(0)
        sweep_present = False
        for row in rows:
            if not isinstance(row, dict):
                return result
            ticker, name = str(row.get('iem_cd') or ''), str(row.get('iem_nm') or '')
            if ticker.startswith('NHKRCMA') or 'CMA' in name:
                sweep_present = True
                value = amount(row.get('eal_amt'))
                if value < 0:
                    return result
                sweep += value
            elif ticker.startswith('RP') or amount(row.get('rsdl_qty', row.get('itg_bnc_qty', 0))) > 0:
                result['state'] = 'OTHER_ASSETS_UNVERIFIED'
                return result
        result.update(cash_krw=str(cash), sweep_krw=str(sweep), total_krw=str(cash+sweep))
        for key in ('nas_amt','tot_aet_amt'):
            if key in head and amount(head[key])!=cash+sweep:
                result['state']='TOTAL_UNVERIFIED'
                return result
        if any(amount(head.get(key,0))!=0 for key in ('rba','int_ny_pmt_amt','ny_rdp_amt','ect_lga','lon_amt')):
            result['state']='OTHER_ASSETS_UNVERIFIED'
            return result
        # The actual evening sweep time is unknown. State follows the returned
        # components at any hour; total_krw is only cash + identified CMA rows.
        if settlement_differs:
            result['state'] = 'SETTLEMENT_UNVERIFIED'
        elif sweep_present:
            result['state'] = 'AWAITING_CASH_RETURN'
        elif cash == 0:
            result['state'] = 'ZERO_UNVERIFIED'
        else:
            result['state'] = 'CASH_RETURNED'
        return result
    except (ValueError, TypeError, InvalidOperation):
        return result


def interest_preview(account, observation, now):
    now = moment(now)
    if account.get('account_type') != 'CMA':
        raise ValueError('CMA 계좌만 이자 확인을 지원합니다.')
    observed = moment(observation['observed_at'])
    if observed.date() != now.date() or not 0 <= (now-observed).total_seconds() <= 600:
        raise ValueError('당일 최근 CMA 조회로 다시 확인해주세요.')
    if observation.get('state') != 'CASH_RETURNED':
        raise ValueError('CMA 현금 반환을 확인하지 못했습니다. 기존 장부를 유지합니다.')
    book, cash = amount(account.get('deposit_krw')), amount(observation['cash_krw'])
    if book < 0:
        raise ValueError('현재 장부의 CMA 예수금을 확인해주세요.')
    delta = cash-book
    if delta < 0:
        raise ValueError('NH 잔고가 장부보다 작습니다. 출금·이체·조회 기준을 확인해주세요.')
    result=dict(status='INTEREST_CANDIDATE' if delta else 'NO_CHANGE',
                book_krw=str(book), broker_krw=str(cash), interest_krw=str(delta),
                event_date=observed.date().isoformat())
    proof=observation.get('reconciliation') or {}
    if proof.get('status')=='INITIAL_BALANCE_REVIEW':
        result.update(status='INITIAL_BALANCE_REVIEW',can_apply=False,
            paid_interest_krw=proof.get('paid_interest_krw'),prior_difference_krw=proof.get('prior_difference_krw'),
            source_start=proof.get('source_start'))
    elif proof.get('status')=='MATCHED':
        result.update(paid_items=proof.get('paid_items'),source_start=proof.get('source_start'))
    else:
        result.update(status=proof.get('status') or 'STATEMENT_REQUIRED',can_apply=False)
    return result


def stable_return(previous, current):
    if not previous or previous.get('state') != 'CASH_RETURNED' or current.get('state') != 'CASH_RETURNED':
        return False
    before, after = moment(previous['observed_at']), moment(current['observed_at'])
    return (before.date() == after.date() and 60 <= (after-before).total_seconds() <= 14400
            and previous.get('book_token') == current.get('book_token')
            and amount(previous['cash_krw']) == amount(current['cash_krw']))


def due_slot(now, completed_slots):
    now = moment(now)
    if now.hour >= 16:
        return None
    # At most one current slot after restart; never burst through missed slots.
    available = [i for i, (h, m) in enumerate(CHECK_TIMES) if (now.hour, now.minute) >= (h, m)]
    slot = available[-1] if available else None
    return slot if slot is not None and slot not in completed_slots else None
