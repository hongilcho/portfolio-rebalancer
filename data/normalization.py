"""Pure account policies, ID generation and asset defaults; no database IO."""
import json
import uuid
from data.enums import AccountType

ACCOUNT_TYPES = {
    AccountType.GENERAL: {"annual_limit": 0, "tax_limit": 0, "max_risk_pct": 100},
    AccountType.PENSION: {"annual_limit": 18000000, "tax_limit": 6000000, "max_risk_pct": 100},
    AccountType.IRP: {"annual_limit": 18000000, "tax_limit": 9000000, "max_risk_pct": 70},
    AccountType.ISA: {"annual_limit": 20000000, "tax_limit": 0, "max_risk_pct": 100},
    AccountType.CMA: {"annual_limit": 0, "tax_limit": 0, "max_risk_pct": 100},
    AccountType.GOLD: {"annual_limit": 0, "tax_limit": 0, "max_risk_pct": 100},
}

ACCOUNT_TYPE_ALIASES = {
    "해외주식 일반계좌": AccountType.GENERAL,
    "국내주식 일반계좌": AccountType.GENERAL,
    "해외주식계좌": AccountType.GENERAL,
    "일반계좌": AccountType.GENERAL,
    "기본계좌": AccountType.GENERAL,
    "ISA 계좌": AccountType.ISA,
    "개인형 IRP": AccountType.IRP
}


def sanitize_account_names(acc_list: list) -> list:
    """계좌 이름 목록에서 공백을 제거하고 중복을 배제하여 정렬된 리스트로 반환합니다."""
    clean_set = set()
    for acc in acc_list:
        if acc is not None and str(acc).strip():
            clean_set.add(str(acc).strip())
    return sorted(list(clean_set))


def generate_id() -> str:
    """UUID4 32자리 16진수 고유 식별자 문자열을 생성합니다."""
    return uuid.uuid4().hex


def _normalize_asset(row):
    """Keep asset types/defaults identical for row and JSON batch readers."""
    r = dict(row)
    try:
        raw_accs = json.loads(r['allowed_accounts']) if r.get('allowed_accounts') else []
    except Exception:
        raw_accs = []
    r['allowed_accounts'] = sanitize_account_names(raw_accs)
    r['account_no'] = r.get('account_no') or ''
    r['is_risk_asset'] = bool(r.get('is_risk_asset', 1))
    r['is_active'] = bool(r.get('is_active', True) if r.get('is_active') is not None else True)
    r['is_deposit'] = bool(r.get('is_deposit', False))
    r['deposit_principal'] = float(r.get('deposit_principal') or 0.0)
    r['interest_rate'] = float(r.get('interest_rate') or 0.0)
    r['start_date'] = r.get('start_date') or ''
    r['maturity_date'] = r.get('maturity_date') or ''
    r['early_termination_rate'] = float(r.get('early_termination_rate') or 0.0)
    r['tax_rate'] = float(r.get('tax_rate') if r.get('tax_rate') is not None else 15.4)
    r['lock_rebalance_sell'] = bool(r.get('lock_rebalance_sell', True) if r.get('lock_rebalance_sell') is not None else True)
    r['include_in_rebalance'] = bool(r.get('include_in_rebalance', True) if r.get('include_in_rebalance') is not None else True)
    r['is_dividend_cost_deduct'] = bool(r.get('is_dividend_cost_deduct', False))
    return r
