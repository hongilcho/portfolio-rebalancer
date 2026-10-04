"""Asset CRUD and deposit attributes persistence."""
import json
import uuid
import psycopg2
from psycopg2.extras import RealDictCursor
from data.normalization import sanitize_account_names, _normalize_asset
from data.repository_context import RepositoryContext

def get_all_assets(db: RepositoryContext, portfolio_id: str = None):
    conn = db.connect()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        if portfolio_id:
            cursor.execute("SELECT * FROM assets WHERE portfolio_id = %s ORDER BY name ASC", (portfolio_id,))
        else:
            cursor.execute("SELECT * FROM assets ORDER BY name ASC")
        return [_normalize_asset(r) for r in cursor.fetchall()]
    finally:
        conn.close()


def add_asset(
    db: RepositoryContext,
    name,
    ticker,
    market,
    target_weight,
    allowed_accounts=None,
    is_risk_asset=True,
    is_active=True,
    notes='',
    portfolio_id='default',
    is_deposit=False,
    deposit_principal=0.0,
    interest_rate=0.0,
    start_date='',
    maturity_date='',
    early_termination_rate=0.0,
    tax_rate=15.4,
    lock_rebalance_sell=True,
    account_id=None,
    account_no='',
    include_in_rebalance=True,
    is_dividend_cost_deduct=False,
):
    conn = db.connect()
    cursor = conn.cursor()
    new_id = db.new_id()
    target_pid = portfolio_id or "default"
    clean_acc_no = (account_no or '').strip()

    if is_deposit:
        is_risk_asset = False
        market = 'KR'
        if not ticker or ticker.strip() in ['', '없음', '-']:
            ticker = f"DEP-{uuid.uuid4().hex[:6].upper()}"
        allowed_accounts = []
        account_id = None

    if allowed_accounts is None:
        allowed_accounts = []
    clean_accs = sanitize_account_names(allowed_accounts)

    try:
        allowed_json = json.dumps(clean_accs, ensure_ascii=False)
        cursor.execute('''
            INSERT INTO assets (
                id, name, ticker, market, target_weight, allowed_accounts, is_risk_asset, is_active, notes, portfolio_id,
                is_deposit, deposit_principal, interest_rate, start_date, maturity_date, early_termination_rate, tax_rate, lock_rebalance_sell, account_no,
                include_in_rebalance, is_dividend_cost_deduct
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            new_id, name, ticker.strip().upper(), market, target_weight, allowed_json,
            1 if is_risk_asset else 0, is_active, notes, target_pid,
            is_deposit, float(deposit_principal or 0.0), float(interest_rate or 0.0),
            str(start_date or ''), str(maturity_date or ''), float(early_termination_rate or 0.0),
            float(tax_rate if tax_rate is not None else 15.4), lock_rebalance_sell,
            clean_acc_no if is_deposit else '',
            bool(include_in_rebalance),
            bool(is_dividend_cost_deduct)
        ))

        conn.commit()
        db.invalidate()
        return True, "성공적으로 추가되었습니다."
    except psycopg2.IntegrityError:
        conn.rollback()
        return False, f"이미 존재하는 티커/종목코드입니다: {ticker}"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def update_asset(
    db: RepositoryContext,
    asset_id,
    name,
    ticker,
    market,
    target_weight,
    allowed_accounts,
    is_risk_asset=True,
    is_active=True,
    notes='',
    is_deposit=False,
    deposit_principal=0.0,
    interest_rate=0.0,
    start_date='',
    maturity_date='',
    early_termination_rate=0.0,
    tax_rate=15.4,
    lock_rebalance_sell=True,
    account_id=None,
    account_no='',
    include_in_rebalance=True,
    is_dividend_cost_deduct=False,
):
    conn = db.connect()
    cursor = conn.cursor()
    clean_acc_no = (account_no or '').strip()

    if is_deposit:
        is_risk_asset = False
        market = 'KR'
        if not ticker or ticker.strip() in ['', '없음', '-']:
            ticker = f"DEP-{str(asset_id)[:6].upper()}"
        allowed_accounts = []
        account_id = None

    clean_accs = sanitize_account_names(allowed_accounts)
    try:
        allowed_json = json.dumps(clean_accs, ensure_ascii=False)
        cursor.execute('''
            UPDATE assets
            SET name = %s, ticker = %s, market = %s, target_weight = %s, allowed_accounts = %s,
                is_risk_asset = %s, is_active = %s, notes = %s,
                is_deposit = %s, deposit_principal = %s, interest_rate = %s, start_date = %s,
                maturity_date = %s, early_termination_rate = %s, tax_rate = %s, lock_rebalance_sell = %s,
                account_no = %s, include_in_rebalance = %s, is_dividend_cost_deduct = %s
            WHERE id = %s
        ''', (
            name, ticker.strip().upper(), market, target_weight, allowed_json,
            1 if is_risk_asset else 0, is_active, notes,
            is_deposit, float(deposit_principal or 0.0), float(interest_rate or 0.0),
            str(start_date or ''), str(maturity_date or ''), float(early_termination_rate or 0.0),
            float(tax_rate if tax_rate is not None else 15.4), lock_rebalance_sell,
            clean_acc_no if is_deposit else '',
            bool(include_in_rebalance),
            bool(is_dividend_cost_deduct),
            str(asset_id)
        ))

        conn.commit()
        db.invalidate()
        return True, "성공적으로 수정되었습니다."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def toggle_asset_active(db: RepositoryContext, asset_id, is_active: bool):
    conn = db.connect()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE assets SET is_active = %s WHERE id = %s", (is_active, str(asset_id)))
        conn.commit()
        db.invalidate()
        status_str = "활성화" if is_active else "비활성화(보관)"
        return True, f"종목이 성공적으로 {status_str}되었습니다."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def delete_asset(db: RepositoryContext, asset_id):
    conn = db.connect()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM holdings WHERE asset_id = %s", (str(asset_id),))
        cursor.execute("DELETE FROM trade_history WHERE asset_id = %s", (str(asset_id),))
        cursor.execute("DELETE FROM assets WHERE id = %s", (str(asset_id),))

        conn.commit()
        db.invalidate()
        return True, "종목이 성공적으로 삭제되었습니다."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()
