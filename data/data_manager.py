"""
데이터베이스 영속성 및 트랜잭션 관리 모듈 (Data Manager)
=========================================================
Supabase PostgreSQL 데이터베이스와 연동하여 포트폴리오, 계좌, 자산, 보유종목,
거래내역, 가상자산 포트폴리오 및 시세 캐시의 CRUD 및 트랜잭션을 관리합니다.

핵심 아키텍처 및 안전성 원칙:
1. 커넥션 풀링(ThreadedConnectionPool):
   - 최소 1개 ~ 최대 20개의 스레드 안전 커넥션을 풀링하여 동시성 처리 성능 극대화.
2. PoolConnectionWrapper 및 Context Manager:
   - `with get_connection() as conn:` 구문을 지원하여 예외 발생 시 자동 롤백 및 풀 반납 보장.
3. PostgreSQL Advisory Lock(424242):
   - 분산/다중 워커 기동 시 스키마 초기화(`init_db`) 간 DDL 경합 및 Deadlock 방지.
4. 멀티 포트폴리오 격리:
   - 모든 계좌, 자산, 보유종목 쿼리에 `portfolio_id` 필터를 적용하여 완벽한 데이터 격리 보장.
"""

import os
import json
import uuid
import threading
import psycopg2
from psycopg2 import pool
from psycopg2.extras import RealDictCursor
from datetime import datetime
from typing import Optional, Dict, Any, List, Tuple
from backend.config import SUPABASE_URL

# 사용자 정의 6가지 표준 계좌 유형
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

_connection_pool = None
_pool_lock = threading.Lock()

def get_connection_pool():
    """
    PostgreSQL ThreadedConnectionPool 단일 인스턴스를 반환합니다. (스레드 안전)
    """
    global _connection_pool
    if _connection_pool is None:
        with _pool_lock:
            if _connection_pool is None:
                pg_url = os.getenv("SUPABASE_URL") or SUPABASE_URL
                if not pg_url:
                    raise ValueError("SUPABASE_URL 환경 변수가 설정되지 않았습니다.")
                _connection_pool = psycopg2.pool.ThreadedConnectionPool(1, 20, pg_url)
    return _connection_pool

class PoolConnectionWrapper:
    """
    psycopg2 커넥션을 감싸는 래퍼 클래스
    
    Python Context Manager 프로토콜(__enter__, __exit__)을 지원하며,
    close() 호출 시 물리적 연결을 끊지 않고 풀(pool)로 안전하게 반납합니다.
    """
    def __init__(self, pool_obj, conn):
        self.pool = pool_obj
        self.conn = conn
        self._closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            try:
                self.rollback()
            except Exception:
                pass
        self.close()

    def cursor(self, *args, **kwargs):
        return self.conn.cursor(*args, **kwargs)
        
    def commit(self):
        self.conn.commit()
        
    def rollback(self):
        self.conn.rollback()
        
    def close(self):
        # close 호출 시 진짜로 연결을 끊지 않고 풀에 반환 (중복 close 방지)
        if not self._closed:
            self._closed = True
            try:
                self.pool.putconn(self.conn)
            except Exception:
                pass

def get_connection() -> PoolConnectionWrapper:
    """
    커넥션 풀로부터 활성 PostgreSQL 연결을 대여하여 PoolConnectionWrapper로 반환합니다.
    with 구문과 함께 사용하는 것을 권장합니다.
    """
    pool_obj = get_connection_pool()
    conn = pool_obj.getconn()
    return PoolConnectionWrapper(pool_obj, conn)

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

def init_db():
    """
    PostgreSQL 데이터베이스 테이블 스키마 및 인덱스를 초기화하고 필요한 마이그레이션을 적용합니다.
    
    Render 등의 분산/멀티 프로세스 배포 환경에서 여러 Uvicorn 워커가 동시에
    DDL을 실행하여 발생할 수 있는 교착 상태(Deadlock)를 방지하기 위해
    PostgreSQL Advisory Lock(424242)을 사용하여 단 1개의 워커만 스키마 초기화를 수행하도록 보장합니다.
    """
    conn = get_connection()
    cursor = conn.cursor()
    
    # Render 및 다중 Uvicorn 워커 환경에서 DDL 락 경합 및 Deadlock 방지 (PostgreSQL Advisory Lock)
    acquired = False
    try:
        cursor.execute("SELECT pg_try_advisory_lock(424242)")
        res = cursor.fetchone()
        acquired = bool(res and res[0])
        if not acquired:
            print("Another worker is initializing DB schema. Skipping init_db.")
            conn.close()
            return
    except Exception as e:
        print(f"Advisory lock check skipped: {e}")

    try:
        _do_init_db_schema(conn, cursor)
    except Exception as e:
        conn.rollback()
        print(f"Schema initialization warning (ignoring deadlock/race): {e}")
    finally:
        if acquired:
            try:
                cursor.execute("SELECT pg_advisory_unlock(424242)")
                conn.commit()
            except Exception:
                pass
        conn.close()

def _do_init_db_schema(conn, cursor):
    # Postgres schema setup
    # 0. Portfolios table setup
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS portfolios (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            description TEXT DEFAULT '',
            is_default BOOLEAN DEFAULT FALSE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    cursor.execute('''
        INSERT INTO portfolios (id, name, description, is_default)
        VALUES ('default', '메인 포트폴리오', '기본 자산배분 포트폴리오', TRUE)
        ON CONFLICT (id) DO NOTHING
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            id TEXT PRIMARY KEY,
            account_no TEXT NOT NULL UNIQUE,
            account_alias TEXT NOT NULL,
            account_type TEXT NOT NULL,
            deposit_krw REAL DEFAULT 0.0,
            deposit_usd REAL DEFAULT 0.0,
            annual_limit REAL DEFAULT 0.0,
            tax_limit REAL DEFAULT 0.0,
            priority INTEGER DEFAULT 99,
            limit_preference TEXT DEFAULT 'ANNUAL',
            current_year_deposit REAL DEFAULT 0.0,
            last_updated_year INTEGER DEFAULT 2026,
            is_limit_exhausted BOOLEAN DEFAULT FALSE,
            notes TEXT
        )
    ''')
    cursor.execute("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS is_limit_exhausted BOOLEAN DEFAULT FALSE")
    cursor.execute("ALTER TABLE accounts ADD COLUMN IF NOT EXISTS portfolio_id TEXT DEFAULT 'default' REFERENCES portfolios(id)")
    cursor.execute("UPDATE accounts SET portfolio_id = 'default' WHERE portfolio_id IS NULL")
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS assets (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            ticker TEXT NOT NULL,
            market TEXT NOT NULL CHECK(market IN ('KR', 'US')),
            target_weight REAL DEFAULT 0.0,
            allowed_accounts TEXT DEFAULT '[]',
            is_risk_asset INTEGER DEFAULT 1,
            is_active BOOLEAN DEFAULT TRUE,
            notes TEXT
        )
    ''')
    cursor.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS is_active BOOLEAN DEFAULT TRUE")
    cursor.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS portfolio_id TEXT DEFAULT 'default' REFERENCES portfolios(id)")
    cursor.execute("UPDATE assets SET portfolio_id = 'default' WHERE portfolio_id IS NULL")
    cursor.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS is_deposit BOOLEAN DEFAULT FALSE")
    cursor.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS deposit_principal REAL DEFAULT 0.0")
    cursor.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS interest_rate REAL DEFAULT 0.0")
    cursor.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS start_date TEXT DEFAULT ''")
    cursor.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS maturity_date TEXT DEFAULT ''")
    cursor.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS early_termination_rate REAL DEFAULT 0.0")
    cursor.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS tax_rate REAL DEFAULT 15.4")
    cursor.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS lock_rebalance_sell BOOLEAN DEFAULT TRUE")
    cursor.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS account_no TEXT DEFAULT ''")
    cursor.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS include_in_rebalance BOOLEAN DEFAULT TRUE")

    try:
        cursor.execute('''
            DO $$
            BEGIN
                IF EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'assets_ticker_key') THEN
                    ALTER TABLE assets DROP CONSTRAINT assets_ticker_key;
                END IF;
            END $$;
        ''')
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_assets_portfolio_ticker ON assets (portfolio_id, ticker)")
    except Exception as e:
        print(f"Index migration note: {e}")

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS holdings (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            asset_id TEXT NOT NULL,
            quantity REAL DEFAULT 0.0,
            avg_price REAL DEFAULT 0.0,
            avg_price_usd REAL DEFAULT 0.0,
            buy_fx_rate REAL DEFAULT 0.0,
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
            FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE,
            UNIQUE(account_id, asset_id)
        )
    ''')
    cursor.execute("ALTER TABLE holdings ADD COLUMN IF NOT EXISTS avg_price_usd REAL DEFAULT 0.0")
    cursor.execute("ALTER TABLE holdings ADD COLUMN IF NOT EXISTS buy_fx_rate REAL DEFAULT 0.0")
    try:
        cursor.execute('''
            UPDATE holdings 
            SET buy_fx_rate = ROUND((avg_price / avg_price_usd)::numeric, 2)
            WHERE (buy_fx_rate IS NULL OR buy_fx_rate = 0.0) 
              AND avg_price_usd > 0 AND avg_price > 0
        ''')
    except Exception as e:
        print(f"buy_fx_rate migration note: {e}")


    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trade_history (
            id TEXT PRIMARY KEY,
            trade_date TEXT NOT NULL,
            account_id TEXT NOT NULL,
            asset_id TEXT NOT NULL,
            trade_type TEXT NOT NULL,
            quantity REAL NOT NULL,
            price REAL NOT NULL,
            currency TEXT DEFAULT 'KRW',
            exchange_rate REAL DEFAULT 1.0,
            notes TEXT,
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
            FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS crypto_holdings (
            id TEXT PRIMARY KEY,
            owner TEXT NOT NULL DEFAULT '윤아',
            symbol TEXT NOT NULL,
            name TEXT NOT NULL,
            quantity REAL DEFAULT 0.0,
            avg_price REAL DEFAULT 0.0,
            notes TEXT,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE (owner, symbol)
        )
    ''')
    
    # 마이그레이션: owner 컬럼 부재 시 추가
    cursor.execute('''
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM information_schema.columns 
                WHERE table_name = 'crypto_holdings' AND column_name = 'owner'
            ) THEN
                ALTER TABLE crypto_holdings ADD COLUMN owner TEXT NOT NULL DEFAULT '윤아';
            END IF;
        END $$;
    ''')

    # 마이그레이션: 기존 단일 UNIQUE (symbol) 제약조건 해제 및 복합 UNIQUE (owner, symbol) 설정
    cursor.execute('''
        DO $$
        BEGIN
            IF EXISTS (
                SELECT 1 FROM pg_constraint 
                WHERE conrelid = 'crypto_holdings'::regclass 
                AND conname = 'crypto_holdings_symbol_key'
            ) THEN
                ALTER TABLE crypto_holdings DROP CONSTRAINT crypto_holdings_symbol_key;
            END IF;
            IF NOT EXISTS (
                SELECT 1 FROM pg_constraint 
                WHERE conrelid = 'crypto_holdings'::regclass 
                AND conname = 'crypto_holdings_owner_symbol_key'
            ) THEN
                ALTER TABLE crypto_holdings ADD CONSTRAINT crypto_holdings_owner_symbol_key UNIQUE (owner, symbol);
            END IF;
        END $$;
    ''')

    # 기존 단일 레코드 id 리네이밍 및 윤아 소유자 보장
    cursor.execute('''
        UPDATE crypto_holdings 
        SET id = 'crypto_yoona_' || LOWER(symbol), owner = '윤아' 
        WHERE id IN ('crypto_btc', 'crypto_eth');
    ''')

    # 기본 레코드 프로비저닝 (홍일, 윤아)
    cursor.execute('''
        INSERT INTO crypto_holdings (id, owner, symbol, name, quantity, avg_price)
        VALUES 
            ('crypto_hongil_btc', '홍일', 'BTC', '비트코인', 0.0, 0.0),
            ('crypto_hongil_eth', '홍일', 'ETH', '이더리움', 0.0, 0.0),
            ('crypto_yoona_btc', '윤아', 'BTC', '비트코인', 0.0, 0.0),
            ('crypto_yoona_eth', '윤아', 'ETH', '이더리움', 0.0, 0.0)
        ON CONFLICT (owner, symbol) DO NOTHING;
    ''')

    # 시장 시세 및 환율 영구 캐시 테이블 (서버 재부팅 및 Render 슬립 해제 시 0초 콜드스타트 보장)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS market_cache (
            key TEXT PRIMARY KEY,
            data JSONB NOT NULL,
            updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # 누적 납입금액 초기화
    current_year = datetime.now().year
    cursor.execute("SELECT id, last_updated_year FROM accounts")
    for row in cursor.fetchall():
        if row[1] and row[1] < current_year:
            cursor.execute("UPDATE accounts SET current_year_deposit = 0.0, last_updated_year = %s WHERE id = %s", (current_year, row[0]))

    conn.commit()
    clean_deposit_shadow_accounts()

def clean_deposit_shadow_accounts():
    """
    정기예금은 계좌가 아닌 '순수 자산(Pure Asset)'이므로,
    기존에 임시로 자동 생성되었던 accounts(정기예금 유형 또는 DEP- 계좌) 및 holdings 레코드를 DB에서 완전 정리.
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # 1. 정기예금 또는 DEP- 형태의 가상 계좌 조회
        cursor.execute("SELECT id FROM accounts WHERE account_type = '정기예금' OR account_no LIKE 'DEP-%'")
        shadow_acc_ids = [str(r[0]) for r in cursor.fetchall()]
        
        if shadow_acc_ids:
            cursor.execute("DELETE FROM holdings WHERE account_id = ANY(%s)", (shadow_acc_ids,))
            cursor.execute("DELETE FROM trade_history WHERE account_id = ANY(%s)", (shadow_acc_ids,))
            cursor.execute("DELETE FROM accounts WHERE id = ANY(%s)", (shadow_acc_ids,))
            
        cursor.execute('''
            UPDATE assets 
            SET allowed_accounts = '[]'
            WHERE is_deposit = TRUE
        ''')
        cursor.execute('''
            UPDATE assets
            SET account_no = ''
            WHERE is_deposit = TRUE AND account_no LIKE 'DEP-%'
        ''')
        conn.commit()
        clear_all_caches()
    except Exception as e:
        conn.rollback()
        print(f"Error cleaning deposit shadow accounts: {e}")
    finally:
        conn.close()

# ---------------------------------------------------------
# Portfolios CRUD
# ---------------------------------------------------------
def get_portfolios():
    conn = get_connection()
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

def get_portfolio(portfolio_id: str):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("SELECT * FROM portfolios WHERE id = %s", (portfolio_id,))
        row = cursor.fetchone()
        return dict(row) if row else None
    finally:
        conn.close()

def create_portfolio(name: str, description: str = ""):
    if not name or not name.strip():
        return False, "포트폴리오 이름을 입력해주세요.", None
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    new_id = generate_id()
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

def update_portfolio(portfolio_id: str, name: str, description: str = ""):
    if not name or not name.strip():
        return False, "포트폴리오 이름을 입력해주세요."
    conn = get_connection()
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

def delete_portfolio(portfolio_id: str):
    if portfolio_id == 'default':
        return False, "기본 포트폴리오는 삭제할 수 없습니다."
    conn = get_connection()
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

# ---------------------------------------------------------
# Accounts CRUD
# ---------------------------------------------------------
def get_all_accounts(portfolio_id: str = None):
    conn = get_connection()
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

def add_account(account_no, account_alias, account_type, deposit_krw=0.0, deposit_usd=0.0, annual_limit=0.0, tax_limit=0.0, notes="", priority=99, limit_preference="ANNUAL", current_year_deposit=0.0, portfolio_id="default"):
    conn = get_connection()
    cursor = conn.cursor()
    new_id = generate_id()
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

def update_account(account_id, account_no, account_alias, account_type, deposit_krw, deposit_usd, annual_limit, tax_limit, notes="", priority=99, limit_preference="ANNUAL", current_year_deposit=0.0):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE accounts
            SET account_no = %s, account_alias = %s, account_type = %s, deposit_krw = %s, deposit_usd = %s, annual_limit = %s, tax_limit = %s, notes = %s, priority = %s, limit_preference = %s, current_year_deposit = %s
            WHERE id = %s
        ''', (account_no.strip(), account_alias.strip(), account_type, deposit_krw, deposit_usd, annual_limit, tax_limit, notes, priority, limit_preference, current_year_deposit, str(account_id)))
        conn.commit()
        return True, "계좌 정보가 성공적으로 수정되었습니다."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()

def update_account_settings(account_id, priority, limit_preference, current_year_deposit):
    conn = get_connection()
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

def update_account_limit_exhausted(account_id, is_exhausted: bool):
    conn = get_connection()
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

def update_account_priorities(priority_map):
    conn = get_connection()
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

def delete_account(account_id):
    conn = get_connection()
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

# ---------------------------------------------------------
# Assets Helpers
# ---------------------------------------------------------
def get_all_assets(portfolio_id: str = None):
    conn = get_connection()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        if portfolio_id:
            cursor.execute("SELECT * FROM assets WHERE portfolio_id = %s ORDER BY name ASC", (portfolio_id,))
        else:
            cursor.execute("SELECT * FROM assets ORDER BY name ASC")
        rows = []
        for r in cursor.fetchall():
            r = dict(r)
            try:
                raw_accs = json.loads(r['allowed_accounts']) if r['allowed_accounts'] else []
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
            rows.append(r)
        return rows
    finally:
        conn.close()

def add_asset(name, ticker, market, target_weight, allowed_accounts=None, is_risk_asset=True, is_active=True, notes="", portfolio_id="default",
              is_deposit=False, deposit_principal=0.0, interest_rate=0.0, start_date="", maturity_date="",
              early_termination_rate=0.0, tax_rate=15.4, lock_rebalance_sell=True, account_id=None, account_no="",
              include_in_rebalance=True):
    conn = get_connection()
    cursor = conn.cursor()
    new_id = generate_id()
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
                include_in_rebalance
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (
            new_id, name, ticker.strip().upper(), market, target_weight, allowed_json,
            1 if is_risk_asset else 0, is_active, notes, target_pid,
            is_deposit, float(deposit_principal or 0.0), float(interest_rate or 0.0),
            str(start_date or ''), str(maturity_date or ''), float(early_termination_rate or 0.0),
            float(tax_rate if tax_rate is not None else 15.4), lock_rebalance_sell,
            clean_acc_no if is_deposit else '',
            bool(include_in_rebalance)
        ))

        conn.commit()
        clear_all_caches()
        return True, "성공적으로 추가되었습니다."
    except psycopg2.IntegrityError:
        conn.rollback()
        return False, f"이미 존재하는 티커/종목코드입니다: {ticker}"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()

def update_asset(asset_id, name, ticker, market, target_weight, allowed_accounts, is_risk_asset=True, is_active=True, notes="",
                 is_deposit=False, deposit_principal=0.0, interest_rate=0.0, start_date="", maturity_date="",
                 early_termination_rate=0.0, tax_rate=15.4, lock_rebalance_sell=True, account_id=None, account_no="",
                 include_in_rebalance=True):
    conn = get_connection()
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
                account_no = %s, include_in_rebalance = %s
            WHERE id = %s
        ''', (
            name, ticker.strip().upper(), market, target_weight, allowed_json,
            1 if is_risk_asset else 0, is_active, notes,
            is_deposit, float(deposit_principal or 0.0), float(interest_rate or 0.0),
            str(start_date or ''), str(maturity_date or ''), float(early_termination_rate or 0.0),
            float(tax_rate if tax_rate is not None else 15.4), lock_rebalance_sell,
            clean_acc_no if is_deposit else '',
            bool(include_in_rebalance),
            str(asset_id)
        ))

        conn.commit()
        clear_all_caches()
        return True, "성공적으로 수정되었습니다."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()

def toggle_asset_active(asset_id, is_active: bool):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("UPDATE assets SET is_active = %s WHERE id = %s", (is_active, str(asset_id)))
        conn.commit()
        clear_all_caches()
        status_str = "활성화" if is_active else "비활성화(보관)"
        return True, f"종목이 성공적으로 {status_str}되었습니다."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()

def delete_asset(asset_id):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM holdings WHERE asset_id = %s", (str(asset_id),))
        cursor.execute("DELETE FROM trade_history WHERE asset_id = %s", (str(asset_id),))
        cursor.execute("DELETE FROM assets WHERE id = %s", (str(asset_id),))

        conn.commit()
        clear_all_caches()
        return True, "종목이 성공적으로 삭제되었습니다."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()

# ---------------------------------------------------------
# Holdings Helpers
# ---------------------------------------------------------
def get_holdings_by_account(account_id):
    conn = get_connection()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute('''
            SELECT h.*, a.name as asset_name, a.ticker, a.market, a.is_risk_asset,
                   a.is_deposit, a.deposit_principal, a.interest_rate, a.start_date, a.maturity_date, a.tax_rate, a.lock_rebalance_sell
            FROM holdings h
            JOIN assets a ON h.asset_id = a.id
            WHERE h.account_id = %s
        ''', (str(account_id),))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def get_all_holdings():
    conn = get_connection()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute('''
            SELECT h.*, a.name as asset_name, a.ticker, a.market, a.is_risk_asset,
                   a.is_deposit, a.deposit_principal, a.interest_rate, a.start_date, a.maturity_date, a.tax_rate, a.lock_rebalance_sell,
                   acc.account_alias, acc.account_type
            FROM holdings h
            JOIN assets a ON h.asset_id = a.id
            JOIN accounts acc ON h.account_id = acc.id
        ''')
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def clear_all_caches():
    pass

def save_account_holdings(account_id, holdings_data):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        today_str = datetime.now().strftime('%Y-%m-%d')
        for item in holdings_data:
            aid = str(item['asset_id'])
            qty = float(item.get('quantity', 0.0))
            avg_p = float(item.get('avg_price', 0.0))
            avg_p_usd = float(item.get('avg_price_usd', 0.0))
            buy_fx = float(item.get('buy_fx_rate', 0.0))
            
            if qty < 0 or avg_p < 0 or avg_p_usd < 0 or buy_fx < 0:
                conn.rollback()
                return False, "수량, 평단가 및 매입환율은 0 이상이어야 합니다."

            # 미국 자산 또는 달러 평단가가 있는 경우 상호 일치 보정
            if avg_p_usd > 0:
                if buy_fx > 0:
                    avg_p = round(avg_p_usd * buy_fx, 2)
                elif avg_p > 0:
                    buy_fx = round(avg_p / avg_p_usd, 2)
                
            cursor.execute("SELECT id FROM holdings WHERE account_id = %s AND asset_id = %s", (str(account_id), aid))
            row = cursor.fetchone()
            
            if qty <= 0:
                if row:
                    cursor.execute("DELETE FROM holdings WHERE id = %s", (row[0],))
            else:
                if row:
                    cursor.execute("UPDATE holdings SET quantity = %s, avg_price = %s, avg_price_usd = %s, buy_fx_rate = %s WHERE id = %s", (qty, avg_p, avg_p_usd, buy_fx, row[0]))
                else:
                    new_h_id = generate_id()
                    cursor.execute("INSERT INTO holdings (id, account_id, asset_id, quantity, avg_price, avg_price_usd, buy_fx_rate) VALUES (%s, %s, %s, %s, %s, %s, %s)", (new_h_id, str(account_id), aid, qty, avg_p, avg_p_usd, buy_fx))
                    
                new_trade_id = generate_id()
                trade_price = avg_p_usd if avg_p_usd > 0 else avg_p
                trade_curr = 'USD' if avg_p_usd > 0 else 'KRW'
                trade_fx = buy_fx if buy_fx > 0 else 1.0
                cursor.execute('''
                    INSERT INTO trade_history (id, trade_date, account_id, asset_id, trade_type, quantity, price, currency, exchange_rate)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (new_trade_id, today_str, str(account_id), aid, 'INIT', qty, trade_price, trade_curr, trade_fx))
                
        conn.commit()
        return True, "보유 내역이 성공적으로 저장되었습니다."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()

def sync_account_with_api(account_id, api_data):
    if not api_data:
        return False, "API 데이터가 없습니다."
        
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # 0. Migration: Fix gold ticker if it was set to '없음'
        cursor.execute("UPDATE assets SET ticker = 'M04020000' WHERE name LIKE '%금%' AND ticker = '없음'")
        
        # 1. Update deposit
        deposit_krw = api_data.get('deposit_krw', 0.0)
        deposit_usd = api_data.get('deposit_usd', 0.0)
        
        # We need to update deposit_usd if it exists in api_data. Since it might not exist for gold account, we only update it if present.
        if 'deposit_usd' in api_data:
            cursor.execute("UPDATE accounts SET deposit_krw = %s, deposit_usd = %s WHERE id = %s", (deposit_krw, deposit_usd, str(account_id)))
        else:
            cursor.execute("UPDATE accounts SET deposit_krw = %s WHERE id = %s", (deposit_krw, str(account_id)))
        
        # 2. Get asset mapping
        cursor.execute("SELECT id, ticker FROM assets")
        asset_map = {row[1]: row[0] for row in cursor.fetchall()}
        
        # 3. Get existing holdings to zero out removed assets
        cursor.execute("SELECT asset_id FROM holdings WHERE account_id = %s", (str(account_id),))
        existing_asset_ids = {row[0] for row in cursor.fetchall()}
        
        holdings = api_data.get('holdings', [])
        incoming_asset_ids = set()
        
        # 4. Insert or update incoming holdings
        today_str = datetime.now().strftime('%Y-%m-%d')
        for h in holdings:
            ticker = h['ticker']
            if ticker in asset_map:
                aid = asset_map[ticker]
                incoming_asset_ids.add(aid)
                qty = float(h['quantity'])
                avg_p = float(h['avg_price'])
                
                # Check if exists
                cursor.execute("SELECT id FROM holdings WHERE account_id = %s AND asset_id = %s", (str(account_id), aid))
                row = cursor.fetchone()
                if row:
                    cursor.execute("UPDATE holdings SET quantity = %s, avg_price = %s WHERE id = %s", (qty, avg_p, row[0]))
                else:
                    new_h_id = generate_id()
                    cursor.execute("INSERT INTO holdings (id, account_id, asset_id, quantity, avg_price) VALUES (%s, %s, %s, %s, %s)", (new_h_id, str(account_id), aid, qty, avg_p))
                    
                # Also log an INIT trade to trade_history to reflect the manual sync
                new_t_id = generate_id()
                cursor.execute('''
                    INSERT INTO trade_history (id, trade_date, account_id, asset_id, trade_type, quantity, price)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (new_t_id, today_str, str(account_id), aid, 'INIT', qty, avg_p))
                
        # 5. Delete holdings that are no longer in the account (protecting deposits)
        cursor.execute("SELECT id FROM assets WHERE is_deposit = TRUE")
        deposit_asset_ids = {row[0] for row in cursor.fetchall()}
        to_delete_ids = (existing_asset_ids - incoming_asset_ids) - deposit_asset_ids
        for z_id in to_delete_ids:
            cursor.execute("DELETE FROM holdings WHERE account_id = %s AND asset_id = %s", (str(account_id), z_id))
            
        conn.commit()
        return True, "API를 통한 잔고 및 예수금 동기화가 완료되었습니다."
    except Exception as e:
        conn.rollback()
        return False, f"동기화 중 오류 발생: {str(e)}"
    finally:
        conn.close()

# ---------------------------------------------------------
# Trade History & Execution
# ---------------------------------------------------------
def execute_trade(trade_date, account_id, asset_id, trade_type, quantity, price, currency=None, exchange_rate=None):
    if quantity <= 0 or price <= 0:
        return False, "수량과 단가는 0보다 커야 합니다."
        
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    new_trade_id = generate_id()
    try:
        is_us = (currency == 'USD') or (exchange_rate is not None and float(exchange_rate) > 1.0)
        if currency is None:
            currency = 'USD' if is_us else 'KRW'

        if is_us or currency == 'USD':
            if exchange_rate is None or float(exchange_rate) <= 1.0:
                try:
                    from backend.services.market_service import get_usd_krw
                    exchange_rate = get_usd_krw() or 1380.0
                except Exception:
                    exchange_rate = 1380.0
            else:
                exchange_rate = float(exchange_rate)
        else:
            exchange_rate = 1.0

        cursor.execute('''
            INSERT INTO trade_history (id, trade_date, account_id, asset_id, trade_type, quantity, price, currency, exchange_rate)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (new_trade_id, trade_date, str(account_id), str(asset_id), trade_type, quantity, price, currency, exchange_rate))
        
        # 현금 잔고(예수금) 업데이트 로직
        if trade_type in ('BUY', 'SELL'):
            if is_us or currency == 'USD':
                cursor.execute('SELECT deposit_krw, deposit_usd FROM accounts WHERE id = %s', (str(account_id),))
                acc_row = cursor.fetchone()
                if acc_row:
                    dep_krw = float(acc_row.get('deposit_krw') or 0.0)
                    dep_usd = float(acc_row.get('deposit_usd') or 0.0)
                    trade_amt_usd = quantity * price
                    trade_amt_krw = trade_amt_usd * exchange_rate
                    if trade_type == 'BUY':
                        if dep_usd >= trade_amt_usd:
                            dep_usd -= trade_amt_usd
                        else:
                            dep_krw -= trade_amt_krw
                    else: # SELL
                        if dep_usd > 0:
                            dep_usd += trade_amt_usd
                        else:
                            dep_krw += trade_amt_krw
                    cursor.execute('''
                        UPDATE accounts
                        SET deposit_krw = %s, deposit_usd = %s
                        WHERE id = %s
                    ''', (dep_krw, dep_usd, str(account_id)))
            else:
                trade_amount = quantity * price
                cursor.execute('SELECT deposit_krw FROM accounts WHERE id = %s', (str(account_id),))
                acc_row = cursor.fetchone()
                if acc_row:
                    dep_krw = float(acc_row['deposit_krw'])
                    if trade_type == 'BUY':
                        dep_krw -= trade_amount
                    elif trade_type == 'SELL':
                        dep_krw += trade_amount
                    cursor.execute('''
                        UPDATE accounts
                        SET deposit_krw = %s
                        WHERE id = %s
                    ''', (dep_krw, str(account_id)))
                    
        cursor.execute('''
            SELECT quantity, avg_price, avg_price_usd, buy_fx_rate FROM holdings 
            WHERE account_id = %s AND asset_id = %s
        ''', (str(account_id), str(asset_id)))
        
        row = cursor.fetchone()
        
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
                new_qty = curr_qty - quantity
                new_avg_price = curr_avg_price
                new_avg_usd = curr_avg_usd
                new_buy_fx = curr_buy_fx
                if new_qty <= 0:
                    new_qty = 0.0
                    new_avg_price = 0.0
                    new_avg_usd = 0.0
                    new_buy_fx = 0.0
                    
            cursor.execute('''
                UPDATE holdings
                SET quantity = %s, avg_price = %s, avg_price_usd = %s, buy_fx_rate = %s
                WHERE account_id = %s AND asset_id = %s
            ''', (new_qty, new_avg_price, new_avg_usd, new_buy_fx, str(account_id), str(asset_id)))
            
        else:
            if trade_type in ('BUY', 'INIT'):
                new_h_id = generate_id()
                if is_us or currency == 'USD':
                    new_avg_usd = price
                    new_buy_fx = exchange_rate
                    new_avg_price = round(price * exchange_rate, 2)
                else:
                    new_avg_price = price
                    new_avg_usd = 0.0
                    new_buy_fx = 0.0
                cursor.execute('''
                    INSERT INTO holdings (id, account_id, asset_id, quantity, avg_price, avg_price_usd, buy_fx_rate)
                    VALUES (%s, %s, %s, %s, %s, %s, %s)
                ''', (new_h_id, str(account_id), str(asset_id), quantity, new_avg_price, new_avg_usd, new_buy_fx))
            else:
                conn.rollback()
                return False, "매도할 보유 잔고가 없습니다."
                
        conn.commit()
        return True, "매매 기록 및 잔고 업데이트가 완료되었습니다."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()

def get_trade_history(portfolio_id: str = None):
    conn = get_connection()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        if portfolio_id:
            cursor.execute('''
                SELECT t.*, a.account_alias, a.account_type, ast.name as asset_name, ast.ticker, ast.market
                FROM trade_history t
                JOIN accounts a ON t.account_id = a.id
                JOIN assets ast ON t.asset_id = ast.id
                WHERE t.trade_type != 'INIT' AND a.portfolio_id = %s
                ORDER BY t.trade_date DESC, t.id DESC
            ''', (portfolio_id,))
        else:
            cursor.execute('''
                SELECT t.*, a.account_alias, a.account_type, ast.name as asset_name, ast.ticker, ast.market
                FROM trade_history t
                JOIN accounts a ON t.account_id = a.id
                JOIN assets ast ON t.asset_id = ast.id
                WHERE t.trade_type != 'INIT'
                ORDER BY t.trade_date DESC, t.id DESC
            ''')
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()

def delete_trade(trade_id):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute("SELECT account_id, asset_id FROM trade_history WHERE id = %s", (str(trade_id),))
        row = cursor.fetchone()
        if not row:
            return False, "존재하지 않는 매매 기록입니다."
        
        account_id = row['account_id']
        asset_id = row['asset_id']
        
        cursor.execute("DELETE FROM trade_history WHERE id = %s", (str(trade_id),))
        
        cursor.execute('''
            SELECT t.trade_type, t.quantity, t.price, t.currency, t.exchange_rate, a.market
            FROM trade_history t
            JOIN assets a ON t.asset_id = a.id
            WHERE t.account_id = %s AND t.asset_id = %s 
            ORDER BY t.trade_date ASC, t.id ASC
        ''', (account_id, asset_id))
        
        remaining_trades = cursor.fetchall()
        
        new_qty = 0.0
        new_avg_price = 0.0
        new_avg_usd = 0.0
        new_buy_fx = 0.0
        
        for t in remaining_trades:
            t_type = t['trade_type']
            t_qty = float(t['quantity'])
            t_price = float(t['price'])
            t_curr = t.get('currency') or ('USD' if t.get('market') == 'US' else 'KRW')
            t_fx = float(t.get('exchange_rate') or 1.0)
            is_t_us = (t_curr == 'USD' or t.get('market') == 'US')
            
            if t_type == 'INIT':
                new_qty = t_qty
                if is_t_us:
                    new_avg_usd = t_price
                    new_buy_fx = t_fx
                    new_avg_price = round(new_avg_usd * new_buy_fx, 2)
                else:
                    new_avg_price = t_price
                    new_avg_usd = 0.0
                    new_buy_fx = 0.0
            elif t_type == 'BUY':
                next_qty = new_qty + t_qty
                if next_qty > 0:
                    if is_t_us:
                        c_usd_0 = new_qty * new_avg_usd
                        c_krw_0 = c_usd_0 * new_buy_fx
                        c_usd_new = t_qty * t_price
                        c_krw_new = c_usd_new * t_fx
                        total_c_usd = c_usd_0 + c_usd_new
                        total_c_krw = c_krw_0 + c_krw_new
                        new_avg_usd = total_c_usd / next_qty
                        new_buy_fx = (total_c_krw / total_c_usd) if total_c_usd > 0 else t_fx
                        new_avg_price = total_c_krw / next_qty
                    else:
                        new_avg_price = ((new_qty * new_avg_price) + (t_qty * t_price)) / next_qty
                        new_avg_usd = 0.0
                        new_buy_fx = 0.0
                else:
                    new_avg_price = t_price
                    new_avg_usd = t_price if is_t_us else 0.0
                    new_buy_fx = t_fx if is_t_us else 0.0
                new_qty = next_qty
            else: # SELL
                new_qty -= t_qty
                if new_qty <= 0:
                    new_qty = 0.0
                    new_avg_price = 0.0
                    new_avg_usd = 0.0
                    new_buy_fx = 0.0
                    
        if new_qty > 0:
            cursor.execute('''
                INSERT INTO holdings (id, account_id, asset_id, quantity, avg_price, avg_price_usd, buy_fx_rate)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(account_id, asset_id) DO UPDATE SET
                    quantity = EXCLUDED.quantity,
                    avg_price = EXCLUDED.avg_price,
                    avg_price_usd = EXCLUDED.avg_price_usd,
                    buy_fx_rate = EXCLUDED.buy_fx_rate
            ''', (generate_id(), account_id, asset_id, new_qty, new_avg_price, new_avg_usd, new_buy_fx))
        else:
            cursor.execute('''
                DELETE FROM holdings 
                WHERE account_id = %s AND asset_id = %s
            ''', (account_id, asset_id))
            
        conn.commit()
        return True, "매매 기록이 삭제되었으며, 평단가가 정상적으로 롤백되었습니다."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()

def apply_transfer_plan(transfer_plan: list) -> Tuple[bool, str]:
    """
    리밸런싱 이체 지시서(transfer_plan)에 명시된 금액을 각 계좌의 예수금(deposit_krw)에 즉시 반영합니다.
    
    원자적(Atomic) 트랜잭션으로 처리되어, 도중 하나라도 오류가 발생할 경우 자동 롤백됩니다.

    Args:
        transfer_plan (list): 계좌 ID(account_id), 이체유형(type: DEPOSIT/WITHDRAW), 금액(amount) 목록

    Returns:
        Tuple[bool, str]: (성공 여부, 결과 또는 오류 메시지)
    """
    if not transfer_plan:
        return True, "반영할 이체 내역이 없습니다."
        
    conn = get_connection()
    cursor = conn.cursor()
    try:
        for tr in transfer_plan:
            acc_id = str(tr['account_id'])
            amount = float(tr['amount'])
            
            # Fetch current deposit
            cursor.execute("SELECT deposit_krw FROM accounts WHERE id = %s", (acc_id,))
            row = cursor.fetchone()
            if not row:
                continue
                
            curr_deposit = float(row[0])
            if tr['type'] == 'DEPOSIT':
                new_deposit = curr_deposit + amount
            elif tr['type'] == 'WITHDRAW':
                new_deposit = curr_deposit - amount
            else:
                continue
                
            # Update deposit
            cursor.execute("UPDATE accounts SET deposit_krw = %s WHERE id = %s", (new_deposit, acc_id))
            
        conn.commit()
        return True, "이체 지시서가 실제 계좌 예수금에 모두 반영되었습니다."
    except Exception as e:
        conn.rollback()
        return False, f"이체 내역 반영 중 오류가 발생했습니다: {str(e)}"
    finally:
        conn.close()
# ---------------------------------------------------------
# Crypto Holdings (Bitcoin & Ethereum)
# ---------------------------------------------------------
def get_crypto_holdings(owner: Optional[str] = None):
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        if owner:
            cursor.execute("SELECT * FROM crypto_holdings WHERE owner = %s ORDER BY symbol ASC", (owner,))
        else:
            cursor.execute("SELECT * FROM crypto_holdings ORDER BY owner ASC, symbol ASC")
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    except Exception as e:
        print(f"Error fetching crypto holdings: {e}")
        return []
    finally:
        conn.close()

def save_crypto_holding(symbol: str, quantity: float, avg_price: float, owner: str = "홍일", notes: str = ""):
    conn = get_connection()
    cursor = conn.cursor()
    owner_clean = owner.strip() if owner else "홍일"
    sym_clean = symbol.strip().upper()
    owner_tag = "hongil" if owner_clean == "홍일" else ("yoona" if owner_clean == "윤아" else owner_clean.lower())
    record_id = f"crypto_{owner_tag}_{sym_clean.lower()}"
    coin_name = '비트코인' if sym_clean == 'BTC' else ('이더리움' if sym_clean == 'ETH' else sym_clean)

    try:
        cursor.execute('''
            INSERT INTO crypto_holdings (id, owner, symbol, name, quantity, avg_price, notes, updated_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (owner, symbol) DO UPDATE SET
                quantity = EXCLUDED.quantity,
                avg_price = EXCLUDED.avg_price,
                notes = EXCLUDED.notes,
                updated_at = EXCLUDED.updated_at
        ''', (
            record_id,
            owner_clean,
            sym_clean,
            coin_name,
            max(0.0, float(quantity)),
            max(0.0, float(avg_price)),
            notes or "",
            datetime.now()
        ))
        conn.commit()
        return True, f"[{owner_clean}] {sym_clean} 보유 정보가 성공적으로 저장되었습니다."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()

def get_overview_batch_data() -> Dict[str, Any]:
    """
    전체 포트폴리오 요약에 필요한 모든 테이블(portfolios, accounts, assets, holdings, crypto_holdings)을
    단 1회의 PostgreSQL 네트워크 왕복(single round-trip)으로 고속 조회
    """
    sql = """
    SELECT json_build_object(
        'portfolios', COALESCE((SELECT json_agg(p ORDER BY p.is_default DESC, p.created_at ASC) FROM portfolios p), '[]'::json),
        'accounts', COALESCE((SELECT json_agg(acc ORDER BY acc.account_alias ASC) FROM accounts acc), '[]'::json),
        'assets', COALESCE((SELECT json_agg(ast ORDER BY ast.name ASC) FROM assets ast), '[]'::json),
        'holdings', COALESCE((SELECT json_agg(h) FROM (
            SELECT h.*, a.name as asset_name, a.ticker, a.market, a.is_risk_asset,
                   a.is_deposit, a.deposit_principal, a.interest_rate, a.start_date, a.maturity_date, a.tax_rate, a.lock_rebalance_sell,
                   acc.account_alias, acc.account_type
            FROM holdings h
            JOIN assets a ON h.asset_id = a.id
            JOIN accounts acc ON h.account_id = acc.id
        ) h), '[]'::json),
        'crypto_holdings', COALESCE((SELECT json_agg(c) FROM crypto_holdings c), '[]'::json)
    );
    """
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute(sql)
        row = cursor.fetchone()
        raw = row[0] if row else {}
    finally:
        conn.close()

    # Asset 후처리 (JSON 문자열 파싱 및 데이터 타입 정제)
    processed_assets = []
    for r in raw.get('assets', []):
        try:
            raw_accs = json.loads(r['allowed_accounts']) if r.get('allowed_accounts') and isinstance(r['allowed_accounts'], str) else (r.get('allowed_accounts') or [])
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
        processed_assets.append(r)
    raw['assets'] = processed_assets
    return raw

def save_market_cache(key: str, data: Any) -> bool:
    """
    지속성 시장 데이터/시세/환율 캐시 저장 (JSONB 포맷)
    PostgreSQL의 market_cache 테이블에 저장하여 서버 재시작 및 배포 후에도 즉시 복구 가능하게 함.
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO market_cache (key, data, updated_at)
            VALUES (%s, %s, CURRENT_TIMESTAMP)
            ON CONFLICT (key) DO UPDATE
            SET data = EXCLUDED.data, updated_at = CURRENT_TIMESTAMP
        """, (key, json.dumps(data)))
        conn.commit()
        return True
    except Exception as e:
        print(f"Error saving market cache for {key}: {e}")
        return False
    finally:
        conn.close()

def get_market_cache(key: str) -> Tuple[Optional[Any], float]:
    """
    지속성 시장 데이터/시세/환율 캐시 조회
    Returns:
        (data, age_in_seconds): 캐시 데이터와 생성 후 경과 시간(초). 없으면 (None, 999999.0)
    """
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT data, EXTRACT(EPOCH FROM (CURRENT_TIMESTAMP - updated_at)) as age_seconds
            FROM market_cache WHERE key = %s
        """, (key,))
        row = cursor.fetchone()
        if row:
            raw_data = row[0]
            parsed = json.loads(raw_data) if isinstance(raw_data, str) else raw_data
            age = float(row[1]) if row[1] is not None else 0.0
            return parsed, age
    except Exception as e:
        print(f"Error getting market cache for {key}: {e}")
    finally:
        conn.close()
    return None, 999999.0

if __name__ == "__main__":
    init_db()
    print("PostgreSQL Database sanitized and initialized!")

