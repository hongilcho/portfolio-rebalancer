"""Account balances, limits and settings persistence."""
import psycopg2
from psycopg2.extras import RealDictCursor
from data.repository_context import RepositoryContext

def get_all_accounts(db: RepositoryContext, portfolio_id: str = None):
    conn = db.connect()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        if portfolio_id:
            cursor.execute("SELECT * FROM accounts WHERE portfolio_id = %s ORDER BY account_alias ASC", (portfolio_id,))
        else:
            cursor.execute("SELECT * FROM accounts ORDER BY account_alias ASC")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def add_account(
    db: RepositoryContext,
    account_no,
    account_alias,
    account_type,
    deposit_krw=0.0,
    deposit_usd=0.0,
    annual_limit=0.0,
    tax_limit=0.0,
    notes='',
    priority=99,
    limit_preference='ANNUAL',
    current_year_deposit=0.0,
    portfolio_id='default',
):
    conn = db.connect()
    cursor = conn.cursor()
    new_id = db.new_id()
    target_pid = portfolio_id or "default"
    try:
        cursor.execute('''
            INSERT INTO accounts (id, account_no, account_alias, account_type, deposit_krw, deposit_usd, annual_limit, tax_limit, notes, priority, limit_preference, current_year_deposit, portfolio_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (new_id, account_no.strip(), account_alias.strip(), account_type, deposit_krw, deposit_usd, annual_limit, tax_limit, notes, priority, limit_preference, current_year_deposit, target_pid))
        conn.commit()
        return True, "계좌가 성공적으로 추가되었습니다."
    except psycopg2.IntegrityError:
        conn.rollback()
        return False, f"이미 존재하는 계좌번호입니다: {account_no}"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def update_account(
    db: RepositoryContext,
    account_id,
    account_no,
    account_alias,
    account_type,
    deposit_krw,
    deposit_usd,
    annual_limit,
    tax_limit,
    notes='',
    priority=99,
    limit_preference='ANNUAL',
    current_year_deposit=0.0,
):
    conn = db.connect()
    cursor = conn.cursor()
    try:
        cursor.execute('SELECT deposit_krw,deposit_usd FROM accounts WHERE id=%s FOR UPDATE',(str(account_id),))
        current=cursor.fetchone()
        if not current:raise ValueError('계좌를 찾을 수 없습니다.')
        for supplied,old in zip((deposit_krw,deposit_usd),([current['deposit_krw'],current['deposit_usd']] if isinstance(current,dict) else current)):
            if supplied is not None and abs(float(supplied)-float(old or 0))>1e-6:
                raise ValueError('예수금은 4번 탭의 장부 정정 또는 입출금 기록으로 변경해주세요.')
        cursor.execute('''
            UPDATE accounts
            SET account_no = %s, account_alias = %s, account_type = %s, annual_limit = %s, tax_limit = %s, notes = %s, priority = %s, limit_preference = %s, current_year_deposit = %s
            WHERE id = %s
        ''', (account_no.strip(), account_alias.strip(), account_type, annual_limit, tax_limit, notes, priority, limit_preference, current_year_deposit, str(account_id)))
        conn.commit()
        return True, "계좌 정보가 성공적으로 수정되었습니다."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def update_account_settings(
    db: RepositoryContext,
    account_id,
    priority,
    limit_preference,
    current_year_deposit,
):
    conn = db.connect()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE accounts
            SET priority = %s, limit_preference = %s, current_year_deposit = %s
            WHERE id = %s
        ''', (priority, limit_preference, current_year_deposit, str(account_id)))
        conn.commit()
        return True, "계좌 상세 설정이 업데이트되었습니다."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def update_account_limit_exhausted(db: RepositoryContext, account_id, is_exhausted: bool):
    conn = db.connect()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE accounts SET is_limit_exhausted = %s WHERE id = %s", (is_exhausted, str(account_id)))
        conn.commit()
        return True, "한도 소진 상태가 성공적으로 변경되었습니다."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def update_account_priorities(db: RepositoryContext, priority_map):
    conn = db.connect()
    cursor = conn.cursor()
    try:
        for acc_id, prio in priority_map.items():
            cursor.execute("UPDATE accounts SET priority = %s WHERE id = %s", (prio, str(acc_id)))
        conn.commit()
        return True
    except Exception as e:
        conn.rollback()
        return False
    finally:
        conn.close()


def delete_account(db: RepositoryContext, account_id):
    conn = db.connect()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM holdings WHERE account_id = %s", (str(account_id),))
        cursor.execute("DELETE FROM accounts WHERE id = %s", (str(account_id),))
        conn.commit()
        return True, "계좌 및 보유 내역이 삭제되었습니다."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()
