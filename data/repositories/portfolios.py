"""Portfolio CRUD; each write retains its existing transaction."""
from psycopg2.extras import RealDictCursor
from data.repository_context import RepositoryContext

def get_portfolios(db: RepositoryContext):
    conn = db.connect()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("SELECT * FROM portfolios ORDER BY is_default DESC, created_at ASC")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"Error fetching portfolios: {e}")
        return []
    finally:
        conn.close()


def get_portfolio(db: RepositoryContext, portfolio_id: str):
    conn = db.connect()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("SELECT * FROM portfolios WHERE id = %s", (portfolio_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def create_portfolio(db: RepositoryContext, name: str, description: str = ""):
    if not name or not name.strip():
        return False, "포트폴리오 이름을 입력해주세요.", None
    conn = db.connect()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    new_id = db.new_id()
    try:
        cursor.execute('''
            INSERT INTO portfolios (id, name, description, is_default)
            VALUES (%s, %s, %s, FALSE)
            RETURNING *
        ''', (new_id, name.strip(), description.strip() if description else ""))
        row = cursor.fetchone()
        conn.commit()
        return True, "포트폴리오가 성공적으로 생성되었습니다.", dict(row) if row else None
    except Exception as e:
        conn.rollback()
        return False, str(e), None
    finally:
        conn.close()


def update_portfolio(db: RepositoryContext, portfolio_id: str, name: str, description: str = ""):
    if not name or not name.strip():
        return False, "포트폴리오 이름을 입력해주세요."
    conn = db.connect()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE portfolios
            SET name = %s, description = %s, updated_at = CURRENT_TIMESTAMP
            WHERE id = %s
        ''', (name.strip(), description.strip() if description else "", portfolio_id))
        conn.commit()
        return True, "포트폴리오 정보가 성공적으로 수정되었습니다."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()


def delete_portfolio(db: RepositoryContext, portfolio_id: str):
    if portfolio_id == 'default':
        return False, "기본 포트폴리오는 삭제할 수 없습니다."
    conn = db.connect()
    cursor = conn.cursor()
    try:
        # Check if portfolio has accounts or assets
        cursor.execute("SELECT COUNT(*) FROM accounts WHERE portfolio_id = %s", (portfolio_id,))
        acc_cnt = cursor.fetchone()[0]
        cursor.execute("SELECT COUNT(*) FROM assets WHERE portfolio_id = %s", (portfolio_id,))
        ast_cnt = cursor.fetchone()[0]
        
        if acc_cnt > 0 or ast_cnt > 0:
            return False, f"포트폴리오에 등록된 계좌({acc_cnt}개) 또는 종목({ast_cnt}개)이 있어 삭제할 수 없습니다. 먼저 계좌와 종목을 삭제해주세요."
            
        cursor.execute("DELETE FROM portfolios WHERE id = %s", (portfolio_id,))
        conn.commit()
        return True, "포트폴리오가 성공적으로 삭제되었습니다."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()
