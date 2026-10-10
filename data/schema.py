"""Existing startup schema, migration lock and deposit cleanup. Explicit IO only."""
from datetime import datetime
from data.repository_context import RepositoryContext
from data.usd_schema import initialize as initialize_usd_ledger
from data.workflow_schema import initialize as initialize_workflow
from data.security_schema import initialize as initialize_security
from data.investment_schema import initialize as initialize_execution

def init_db(db: RepositoryContext, schema_initializer=None):
    """
    PostgreSQL 데이터베이스 테이블 스키마 및 인덱스를 초기화하고 필요한 마이그레이션을 적용합니다.
    
    Render 등의 분산/멀티 프로세스 배포 환경에서 여러 Uvicorn 워커가 동시에
    DDL을 실행하여 발생할 수 있는 교착 상태(Deadlock)를 방지하기 위해
    PostgreSQL Advisory Lock(424242)을 사용하여 단 1개의 워커만 스키마 초기화를 수행하도록 보장합니다.
    """
    conn = db.connect()
    cursor = conn.cursor()
    
    # Transaction-scoped locks also work through Supavisor transaction pooling.
    # Wait for another initializer rather than serving against an old schema.
    try:
        cursor.execute("SET LOCAL lock_timeout = '30s'")
        cursor.execute("SELECT pg_advisory_xact_lock(424242)")
        if schema_initializer is None:
            _do_init_db_schema(db, conn, cursor)
        else:
            schema_initializer(conn, cursor)
    except Exception:
        conn.rollback()
        # Missing columns must prevent startup, not fail later during a trade.
        raise
    finally:
        conn.close()


def _do_init_db_schema(db: RepositoryContext, conn, cursor):
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
    try:
        cursor.execute("ALTER TABLE accounts ALTER COLUMN deposit_krw TYPE DOUBLE PRECISION")
        cursor.execute("ALTER TABLE accounts ALTER COLUMN deposit_usd TYPE DOUBLE PRECISION")
    except Exception:
        pass
    
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
    # Preserve every existing stored value; future KRW principal entries retain won units.
    cursor.execute("""DO $$ BEGIN
        IF EXISTS(SELECT 1 FROM information_schema.columns WHERE table_schema=current_schema()
            AND table_name='assets' AND column_name='deposit_principal' AND data_type='real') THEN
            ALTER TABLE assets ALTER COLUMN deposit_principal TYPE DOUBLE PRECISION;
        END IF;
    END $$""")
    cursor.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS interest_rate REAL DEFAULT 0.0")
    cursor.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS start_date TEXT DEFAULT ''")
    cursor.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS maturity_date TEXT DEFAULT ''")
    cursor.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS early_termination_rate REAL DEFAULT 0.0")
    cursor.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS tax_rate REAL DEFAULT 15.4")
    cursor.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS lock_rebalance_sell BOOLEAN DEFAULT TRUE")
    cursor.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS account_no TEXT DEFAULT ''")
    cursor.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS include_in_rebalance BOOLEAN DEFAULT TRUE")
    cursor.execute("ALTER TABLE assets ADD COLUMN IF NOT EXISTS is_dividend_cost_deduct BOOLEAN DEFAULT FALSE")

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
    cursor.execute("ALTER TABLE holdings ADD COLUMN IF NOT EXISTS original_avg_price REAL DEFAULT 0.0")
    cursor.execute("ALTER TABLE holdings ADD COLUMN IF NOT EXISTS original_avg_price_usd REAL DEFAULT 0.0")
    cursor.execute("ALTER TABLE holdings ADD COLUMN IF NOT EXISTS first_buy_date TEXT DEFAULT ''")
    cursor.execute("ALTER TABLE holdings ADD COLUMN IF NOT EXISTS manual_dividend_override REAL DEFAULT NULL")
    try:
        cursor.execute("ALTER TABLE holdings ALTER COLUMN quantity TYPE DOUBLE PRECISION")
        cursor.execute("ALTER TABLE holdings ALTER COLUMN avg_price TYPE DOUBLE PRECISION")
        cursor.execute("ALTER TABLE holdings ALTER COLUMN original_avg_price TYPE DOUBLE PRECISION")
    except Exception:
        pass
    try:
        cursor.execute('''
            UPDATE holdings 
            SET buy_fx_rate = ROUND((avg_price / avg_price_usd)::numeric, 2)
            WHERE (buy_fx_rate IS NULL OR buy_fx_rate = 0.0) 
              AND avg_price_usd > 0 AND avg_price > 0
        ''')
        cursor.execute('''
            UPDATE holdings 
            SET original_avg_price = avg_price 
            WHERE (original_avg_price IS NULL OR original_avg_price = 0.0) AND avg_price > 0
        ''')
        cursor.execute('''
            UPDATE holdings 
            SET original_avg_price_usd = avg_price_usd 
            WHERE (original_avg_price_usd IS NULL OR original_avg_price_usd = 0.0) AND avg_price_usd > 0
        ''')
    except Exception as e:
        print(f"buy_fx_rate/original_price migration note: {e}")


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
    
    # NULL means the historical settlement currency is unknown. Never guess it.
    cursor.execute("ALTER TABLE trade_history ADD COLUMN IF NOT EXISTS cash_delta_krw DOUBLE PRECISION")
    cursor.execute("ALTER TABLE trade_history ADD COLUMN IF NOT EXISTS cash_delta_usd DOUBLE PRECISION")
    cursor.execute("ALTER TABLE trade_history ADD COLUMN IF NOT EXISTS trade_sequence BIGSERIAL")
    # Imported order identity shares the trade transaction and deletion lifecycle.
    cursor.execute("ALTER TABLE trade_history ADD COLUMN IF NOT EXISTS import_source TEXT")
    cursor.execute("ALTER TABLE trade_history ADD COLUMN IF NOT EXISTS broker_order_no TEXT")
    cursor.execute('''CREATE UNIQUE INDEX IF NOT EXISTS trade_history_import_order_unique
        ON trade_history (account_id, trade_date, import_source, broker_order_no)
        WHERE import_source IS NOT NULL AND broker_order_no IS NOT NULL''')

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

    initialize_usd_ledger(cursor)
    initialize_workflow(cursor)
    initialize_security(cursor)
    initialize_execution(cursor)
    conn.commit()
    clean_deposit_shadow_accounts(db)


def clean_deposit_shadow_accounts(db: RepositoryContext):
    """Retired compatibility hook: startup must never delete financial records.

    Old deposit shadow accounts may still contain real balances or history.
    Preserve them; explicit audited bookkeeping handles any correction instead.
    """
    return None
