"""Asset CRUD and deposit attributes persistence."""
import json
import math
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
    transaction=None,
    bookkeeping_write=False,
):
    conn = transaction if transaction is not None else db.connect()
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
        if is_deposit and not bookkeeping_write:
            raise ValueError('예금 등록은 5번 탭의 예금 장부에서 처리해주세요.')
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

        if transaction is None: conn.commit()
        db.invalidate()
        return True, "성공적으로 추가되었습니다."
    except psycopg2.IntegrityError:
        if transaction is None: conn.rollback()
        return False, f"이미 존재하는 티커/종목코드입니다: {ticker}"
    except Exception as e:
        if transaction is None: conn.rollback()
        return False, str(e)
    finally:
        if transaction is None: conn.close()


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
    transaction=None,
    bookkeeping_write=False,
):
    conn = transaction if transaction is not None else db.connect()
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
        cursor.execute('SELECT portfolio_id FROM assets WHERE id=%s',(str(asset_id),))
        ref=cursor.fetchone()
        if not ref: raise ValueError('종목을 찾을 수 없습니다.')
        pid=ref['portfolio_id'] if isinstance(ref,dict) else ref[0]
        cursor.execute('SELECT id FROM portfolios WHERE id=%s FOR UPDATE',(pid,))
        lookup=conn.cursor(cursor_factory=RealDictCursor)
        lookup.execute('SELECT * FROM assets WHERE id=%s FOR UPDATE',(str(asset_id),))
        current=lookup.fetchone()
        for table in ('holdings','trade_history'):
            lookup.execute(f'SELECT 1 FROM {table} WHERE asset_id=%s LIMIT 1',(str(asset_id),))
            if lookup.fetchone() and (market!=current['market'] or bool(is_deposit)!=bool(current['is_deposit']) or ticker.strip().upper()!=current['ticker']):
                raise ValueError('보유·거래 이력이 있는 종목의 시장·종류·종목코드는 변경할 수 없습니다.')
        if not bookkeeping_write:
            if bool(is_deposit)!=bool(current['is_deposit']):
                raise ValueError('예금 종류 변경은 5번 탭 예금 장부를 이용해주세요.')
            if current['is_deposit']:
                protected=dict(deposit_principal=deposit_principal,interest_rate=interest_rate,
                    start_date=start_date,maturity_date=maturity_date,
                    early_termination_rate=early_termination_rate,tax_rate=tax_rate)
                if any(str(v or 0)!=str(current.get(k) or 0) if k in ('start_date','maturity_date') else not math.isclose(float(v or 0),float(current.get(k) or 0),abs_tol=1e-5,rel_tol=1e-7) for k,v in protected.items()):
                    raise ValueError('예금 원금·계약 조건은 5번 탭 예금 장부에서 사유와 함께 변경해주세요.')
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

        if transaction is None: conn.commit()
        db.invalidate()
        return True, "성공적으로 수정되었습니다."
    except Exception as e:
        if transaction is None: conn.rollback()
        return False, str(e)
    finally:
        if transaction is None: conn.close()


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
        cursor.execute('SELECT portfolio_id FROM assets WHERE id=%s',(str(asset_id),))
        ref=cursor.fetchone()
        if not ref: raise ValueError('종목을 찾을 수 없습니다.')
        pid=ref['portfolio_id'] if isinstance(ref,dict) else ref[0]
        cursor.execute('SELECT id FROM portfolios WHERE id=%s FOR UPDATE',(pid,))
        cursor.execute('SELECT is_deposit,deposit_principal FROM assets WHERE id=%s FOR UPDATE',(str(asset_id),))
        row=cursor.fetchone()
        is_deposit,principal=(row['is_deposit'],row['deposit_principal']) if isinstance(row,dict) else row
        if is_deposit and abs(float(principal or 0))>1e-9:
            raise ValueError('원금이 있는 예금은 삭제할 수 없습니다. 5번 탭 예금 장부를 이용해주세요.')
        for table in ('holdings','trade_history','usd_cash_events'):
            cursor.execute(f'SELECT 1 FROM {table} WHERE asset_id=%s LIMIT 1',(str(asset_id),))
            if cursor.fetchone(): raise ValueError('보유·거래 이력이 있는 종목은 영구 삭제할 수 없습니다. 보관 기능을 이용해주세요.')
        cursor.execute("SELECT request_id FROM bookkeeping_requests WHERE scope=%s LIMIT 1",('deposit:'+str(asset_id),))
        if cursor.fetchone(): raise ValueError('예금 장부 이력이 있는 종목은 영구 삭제할 수 없습니다.')
        cursor.execute('DELETE FROM assets WHERE id=%s',(str(asset_id),))
        conn.commit()
        db.invalidate()
        return True, "종목이 성공적으로 삭제되었습니다."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()
