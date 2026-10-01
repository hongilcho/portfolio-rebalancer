-- ========================================================
-- Portfolio Rebalancer — Development Database Schema & Seed Data
-- ========================================================
-- 이 스크립트는 로컬 PostgreSQL 또는 신규 Supabase 인스턴스에서
-- 개인 금융 정보를 제외하고 즉시 개발 및 테스트를 수행할 수 있도록
-- 최신 DDL 스키마와 가짜(Dummy) 샘플 데이터를 프로비저닝합니다.

-- 1. 포트폴리오 테이블 (portfolios)
CREATE TABLE IF NOT EXISTS portfolios (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT DEFAULT '',
    is_default BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 2. 계좌 테이블 (accounts)
CREATE TABLE IF NOT EXISTS accounts (
    id TEXT PRIMARY KEY,
    account_no TEXT NOT NULL UNIQUE,
    account_alias TEXT NOT NULL,
    account_type TEXT NOT NULL,
    deposit_krw DOUBLE PRECISION DEFAULT 0.0,
    deposit_usd DOUBLE PRECISION DEFAULT 0.0,
    annual_limit REAL DEFAULT 0.0,
    tax_limit REAL DEFAULT 0.0,
    priority INTEGER DEFAULT 99,
    limit_preference TEXT DEFAULT 'ANNUAL',
    current_year_deposit REAL DEFAULT 0.0,
    last_updated_year INTEGER DEFAULT 2026,
    is_limit_exhausted BOOLEAN DEFAULT FALSE,
    portfolio_id TEXT DEFAULT 'default' REFERENCES portfolios(id) ON DELETE CASCADE,
    notes TEXT
);

-- 3. 자산 테이블 (assets)
CREATE TABLE IF NOT EXISTS assets (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    ticker TEXT NOT NULL,
    market TEXT NOT NULL CHECK(market IN ('KR', 'US')),
    target_weight REAL DEFAULT 0.0,
    allowed_accounts TEXT DEFAULT '[]',
    is_risk_asset INTEGER DEFAULT 1,
    is_active BOOLEAN DEFAULT TRUE,
    is_deposit BOOLEAN DEFAULT FALSE,
    deposit_principal REAL DEFAULT 0.0,
    interest_rate REAL DEFAULT 0.0,
    start_date TEXT DEFAULT '',
    maturity_date TEXT DEFAULT '',
    early_termination_rate REAL DEFAULT 0.0,
    tax_rate REAL DEFAULT 15.4,
    lock_rebalance_sell BOOLEAN DEFAULT TRUE,
    account_no TEXT DEFAULT '',
    include_in_rebalance BOOLEAN DEFAULT TRUE,
    is_dividend_cost_deduct BOOLEAN DEFAULT FALSE,
    portfolio_id TEXT DEFAULT 'default' REFERENCES portfolios(id) ON DELETE CASCADE,
    notes TEXT
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_assets_portfolio_ticker ON assets (portfolio_id, ticker);

-- 4. 보유종목 테이블 (holdings)
CREATE TABLE IF NOT EXISTS holdings (
    id TEXT PRIMARY KEY,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    quantity DOUBLE PRECISION DEFAULT 0.0,
    avg_price DOUBLE PRECISION DEFAULT 0.0,
    avg_price_usd REAL DEFAULT 0.0,
    buy_fx_rate REAL DEFAULT 0.0,
    original_avg_price DOUBLE PRECISION DEFAULT 0.0,
    original_avg_price_usd REAL DEFAULT 0.0,
    first_buy_date TEXT DEFAULT '',
    manual_dividend_override REAL DEFAULT NULL,
    UNIQUE(account_id, asset_id)
);

-- 5. 매매거래 이력 테이블 (trade_history)
CREATE TABLE IF NOT EXISTS trade_history (
    id TEXT PRIMARY KEY,
    trade_date TEXT NOT NULL,
    account_id TEXT NOT NULL REFERENCES accounts(id) ON DELETE CASCADE,
    asset_id TEXT NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
    trade_type TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    currency TEXT DEFAULT 'KRW',
    exchange_rate REAL DEFAULT 1.0,
    notes TEXT
);

-- 6. 가상자산 테이블 (crypto_holdings)
CREATE TABLE IF NOT EXISTS crypto_holdings (
    id TEXT PRIMARY KEY,
    owner TEXT NOT NULL DEFAULT '윤아',
    symbol TEXT NOT NULL,
    name TEXT NOT NULL,
    quantity REAL DEFAULT 0.0,
    avg_price REAL DEFAULT 0.0,
    notes TEXT,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    portfolio_id TEXT DEFAULT 'default' REFERENCES portfolios(id) ON DELETE CASCADE,
    UNIQUE (owner, symbol)
);

-- 7. 시장 시세 및 배당 영구 캐시 테이블 (market_cache)
CREATE TABLE IF NOT EXISTS market_cache (
    key TEXT PRIMARY KEY,
    data JSONB NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

-- ========================================================
-- 가짜 샘플 데이터 (Development Mock Data) 삽입
-- ========================================================

-- [포트폴리오]
INSERT INTO portfolios (id, name, description, is_default)
VALUES 
    ('default', '메인 포트폴리오', '기본 올웨더 자산배분 포트폴리오', TRUE),
    ('sub_test', '테스트 서브 포트폴리오', '신규 전략 검증용 서브 포트폴리오', FALSE)
ON CONFLICT (id) DO NOTHING;

-- [계좌 (5개 표준 계좌)]
INSERT INTO accounts (id, account_no, account_alias, account_type, deposit_krw, deposit_usd, annual_limit, tax_limit, priority, portfolio_id)
VALUES 
    ('dev_acc_isa', '212-02-000001', '개발용 ISA', 'ISA', 2500000.0, 0.0, 20000000.0, 0.0, 3, 'default'),
    ('dev_acc_pension', '205-02-000002', '개발용 연금저축', '연금', 1200000.0, 0.0, 18000000.0, 6000000.0, 2, 'default'),
    ('dev_acc_irp', '212-03-000003', '개발용 IRP', 'IRP', 900000.0, 0.0, 18000000.0, 9000000.0, 1, 'default'),
    ('dev_acc_cma', '212-01-000004', '개발용 CMA', 'CMA', 15000000.0, 0.0, 0.0, 0.0, 5, 'default'),
    ('dev_acc_us', '205-01-000005', '해외ETF 직투계좌', '일반', 500000.0, 1200.0, 0.0, 0.0, 99, 'default')
ON CONFLICT (id) DO NOTHING;

-- [자산 (주식, 채권, 배당, 금, 정기예금, 미국직투)]
INSERT INTO assets (id, name, ticker, market, target_weight, is_risk_asset, is_deposit, deposit_principal, interest_rate, start_date, maturity_date, portfolio_id)
VALUES 
    ('dev_ast_nasdaq', 'KODEX 미국나스닥100', '379810', 'KR', 25.0, 1, FALSE, 0, 0, '', '', 'default'),
    ('dev_ast_schd', 'TIGER 미국배당다우존스', '458730', 'KR', 25.0, 1, FALSE, 0, 0, '', '', 'default'),
    ('dev_ast_bond30', 'ACE 미국30년국채액티브', '476760', 'KR', 20.0, 0, FALSE, 0, 0, '', '', 'default'),
    ('dev_ast_gold', 'KRX 금99.99_1kg', 'M04020000', 'KR', 10.0, 0, FALSE, 0, 0, '', '', 'default'),
    ('dev_ast_dep', '신한 정기예금(1년)', 'DEP-DEV01', 'KR', 10.0, 0, TRUE, 10000000.0, 3.6, '2026-01-01', '2027-01-01', 'default'),
    ('dev_ast_vt', 'Vanguard Total World Stock ETF', 'VT', 'US', 10.0, 1, FALSE, 0, 0, '', '', 'default')
ON CONFLICT (id) DO NOTHING;

-- [보유 종목 (계좌별 잔고)]
INSERT INTO holdings (id, account_id, asset_id, quantity, avg_price, avg_price_usd, buy_fx_rate, original_avg_price, original_avg_price_usd)
VALUES 
    -- ISA 계좌 보유
    ('h_isa_nasdaq', 'dev_acc_isa', 'dev_ast_nasdaq', 50.0, 27500.0, 0.0, 0.0, 27500.0, 0.0),
    ('h_isa_schd', 'dev_acc_isa', 'dev_ast_schd', 80.0, 15200.0, 0.0, 0.0, 15200.0, 0.0),
    ('h_isa_bond30', 'dev_acc_isa', 'dev_ast_bond30', 100.0, 8950.0, 0.0, 0.0, 8950.0, 0.0),

    -- 연금저축 계좌 보유
    ('h_pen_nasdaq', 'dev_acc_pension', 'dev_ast_nasdaq', 100.0, 28000.0, 0.0, 0.0, 28000.0, 0.0),
    ('h_pen_schd', 'dev_acc_pension', 'dev_ast_schd', 100.0, 15300.0, 0.0, 0.0, 15300.0, 0.0),
    ('h_pen_bond30', 'dev_acc_pension', 'dev_ast_bond30', 80.0, 9050.0, 0.0, 0.0, 9050.0, 0.0),

    -- IRP 계좌 보유 (안전자산 30% 보장 규제 충족)
    ('h_irp_bond30', 'dev_acc_irp', 'dev_ast_bond30', 150.0, 9100.0, 0.0, 0.0, 9100.0, 0.0),
    ('h_irp_nasdaq', 'dev_acc_irp', 'dev_ast_nasdaq', 30.0, 27800.0, 0.0, 0.0, 27800.0, 0.0),
    ('h_irp_schd', 'dev_acc_irp', 'dev_ast_schd', 50.0, 15150.0, 0.0, 0.0, 15150.0, 0.0),

    -- 해외 직투 계좌 보유 (미국 주식, 달러 평단가 및 매입환율)
    ('h_us_vt', 'dev_acc_us', 'dev_ast_vt', 50.0, 151800.0, 110.0, 1380.0, 151800.0, 110.0)
ON CONFLICT (id) DO NOTHING;

-- [매매 기록 (trade_history — 시계열 배당 추적 지원용)]
INSERT INTO trade_history (id, trade_date, account_id, asset_id, trade_type, quantity, price, currency, exchange_rate, notes)
VALUES 
    -- 2000-01-01 (인셉션 스냅샷 INIT -> 시스템 상에서 2026-07-01 인셉션으로 자동 매핑됨)
    ('th_01', '2000-01-01', 'dev_acc_isa', 'dev_ast_nasdaq', 'INIT', 50.0, 27500.0, 'KRW', 1.0, '초기 잔고'),
    ('th_02', '2000-01-01', 'dev_acc_isa', 'dev_ast_schd', 'INIT', 80.0, 15200.0, 'KRW', 1.0, '초기 잔고'),
    ('th_03', '2000-01-01', 'dev_acc_isa', 'dev_ast_bond30', 'INIT', 100.0, 8950.0, 'KRW', 1.0, '초기 잔고'),
    ('th_04', '2000-01-01', 'dev_acc_pension', 'dev_ast_nasdaq', 'INIT', 100.0, 28000.0, 'KRW', 1.0, '초기 잔고'),
    ('th_05', '2000-01-01', 'dev_acc_pension', 'dev_ast_schd', 'INIT', 100.0, 15300.0, 'KRW', 1.0, '초기 잔고'),
    ('th_06', '2000-01-01', 'dev_acc_pension', 'dev_ast_bond30', 'INIT', 80.0, 9050.0, 'KRW', 1.0, '초기 잔고'),
    ('th_07', '2000-01-01', 'dev_acc_irp', 'dev_ast_bond30', 'INIT', 150.0, 9100.0, 'KRW', 1.0, '초기 잔고'),
    ('th_08', '2000-01-01', 'dev_acc_irp', 'dev_ast_nasdaq', 'INIT', 30.0, 27800.0, 'KRW', 1.0, '초기 잔고'),
    ('th_09', '2000-01-01', 'dev_acc_irp', 'dev_ast_schd', 'INIT', 50.0, 15150.0, 'KRW', 1.0, '초기 잔고'),
    ('th_10', '2000-01-01', 'dev_acc_us', 'dev_ast_vt', 'INIT', 50.0, 110.0, 'USD', 1380.0, '초기 잔고')
ON CONFLICT (id) DO NOTHING;

-- [가상자산 샘플 데이터]
INSERT INTO crypto_holdings (id, owner, symbol, name, quantity, avg_price)
VALUES 
    ('crypto_hongil_btc', '홍일', 'BTC', '비트코인', 0.05, 85000000.0),
    ('crypto_hongil_eth', '홍일', 'ETH', '이더리움', 0.5, 4000000.0),
    ('crypto_yoona_btc', '윤아', 'BTC', '비트코인', 0.02, 88000000.0),
    ('crypto_yoona_eth', '윤아', 'ETH', '이더리움', 0.3, 4100000.0)
ON CONFLICT (id) DO NOTHING;
