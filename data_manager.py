import sqlite3
import os
import json
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), 'data', 'portfolio.db')

# 사용자 정의 6가지 표준 계좌 유형
ACCOUNT_TYPES = {
    "종합매매": {"annual_limit": 0, "tax_limit": 0, "max_risk_pct": 100},
    "CMA": {"annual_limit": 0, "tax_limit": 0, "max_risk_pct": 100},
    "연금저축계좌": {"annual_limit": 15000000, "tax_limit": 6000000, "max_risk_pct": 100},
    "ISA": {"annual_limit": 20000000, "tax_limit": 0, "max_risk_pct": 100},
    "금현물": {"annual_limit": 0, "tax_limit": 0, "max_risk_pct": 100},
    "IRP": {"annual_limit": 3000000, "tax_limit": 3000000, "max_risk_pct": 70}  # IRP 위험자산 70% 제한
}

# 옛 이름 -> 신규 6종 계좌 유형 매핑 정제 규칙
ACCOUNT_NAME_MAP = {
    "ISA 계좌": "ISA",
    "개인형 IRP": "IRP",
    "해외주식 일반계좌": "종합매매",
    "국내주식 일반계좌": "종합매매",
    "해외주식계좌": "종합매매",
    "일반계좌": "종합매매",
    "기본계좌": "종합매매"
}

DEFAULT_MAPPINGS = {
    "458250": {"allowed": ["ISA", "연금저축계좌", "IRP", "종합매매"], "is_risk": 0},
    "133690": {"allowed": ["ISA", "연금저축계좌", "IRP", "종합매매"], "is_risk": 1},
    "411060": {"allowed": ["ISA", "연금저축계좌", "금현물", "종합매매"], "is_risk": 1},
    "371460": {"allowed": ["ISA", "연금저축계좌", "IRP", "종합매매"], "is_risk": 1},
    "PDBC": {"allowed": ["종합매매"], "is_risk": 1}
}

def get_connection():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def sanitize_account_names(acc_list):
    """자산별 가능 계좌를 개별 계좌 고유 ID 단위로 변환 및 저장"""
    clean_set = set()
    for acc in acc_list:
        if str(acc).isdigit():
            clean_set.add(str(acc))
    return sorted(list(clean_set))

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # 1. Accounts Table 마이그레이션
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='accounts'")
    if cursor.fetchone():
        cursor.execute("PRAGMA table_info(accounts)")
        columns = [col['name'] for col in cursor.fetchall()]
        if 'account_no' not in columns:
            cursor.execute("DROP TABLE accounts")
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS accounts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
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
            notes TEXT
        )
    ''')
    
    cursor.execute("PRAGMA table_info(accounts)")
    columns = [col['name'] for col in cursor.fetchall()]
    if 'annual_limit' not in columns:
        cursor.execute("ALTER TABLE accounts ADD COLUMN annual_limit REAL DEFAULT 0.0")
        cursor.execute("ALTER TABLE accounts ADD COLUMN tax_limit REAL DEFAULT 0.0")
        
        # 기본값 마이그레이션
        cursor.execute("SELECT id, account_type FROM accounts")
        for row in cursor.fetchall():
            acc_type = row['account_type']
            type_info = ACCOUNT_TYPES.get(acc_type, {})
            a_limit = type_info.get("annual_limit", 0)
            t_limit = type_info.get("tax_limit", 0)
            cursor.execute("UPDATE accounts SET annual_limit = ?, tax_limit = ? WHERE id = ?", (a_limit, t_limit, row['id']))
            
    if 'priority' not in columns:
        cursor.execute("ALTER TABLE accounts ADD COLUMN priority INTEGER DEFAULT 99")
        cursor.execute("ALTER TABLE accounts ADD COLUMN limit_preference TEXT DEFAULT 'ANNUAL'")
        cursor.execute("ALTER TABLE accounts ADD COLUMN current_year_deposit REAL DEFAULT 0.0")
        cursor.execute("ALTER TABLE accounts ADD COLUMN last_updated_year INTEGER DEFAULT 2026")
        
    # 해가 바뀌었을 경우 누적 납입금액 초기화
    current_year = datetime.now().year
    cursor.execute("SELECT id, last_updated_year FROM accounts")
    for row in cursor.fetchall():
        if row['last_updated_year'] and row['last_updated_year'] < current_year:
            cursor.execute("UPDATE accounts SET current_year_deposit = 0.0, last_updated_year = ? WHERE id = ?", (current_year, row['id']))

    
    cursor.execute("SELECT COUNT(*) as count FROM accounts")
    if cursor.fetchone()['count'] == 0:
        sample_accounts = [
            ("110-123-456789", "내 메인 ISA", "ISA", 2500000.0, 0.0, 20000000.0, 0.0, "절세 주력 계좌"),
            ("220-987-654321", "연금저축 1호", "연금저축계좌", 1000000.0, 0.0, 15000000.0, 6000000.0, "노후 대비 연금"),
            ("330-111-222333", "퇴직 연금 IRP", "IRP", 500000.0, 0.0, 3000000.0, 3000000.0, "세액공제 및 위험자산 70% 관리"),
            ("440-555-666777", "해외주식 종합매매", "종합매매", 500000.0, 1500.0, 0.0, 0.0, "PDBC 및 해외 직투 계좌")
        ]
        cursor.executemany('''
            INSERT INTO accounts (account_no, account_alias, account_type, deposit_krw, deposit_usd, annual_limit, tax_limit, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ''', sample_accounts)
        
    # 2. Assets Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS assets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            ticker TEXT NOT NULL UNIQUE,
            market TEXT NOT NULL CHECK(market IN ('KR', 'US')),
            target_weight REAL DEFAULT 0.0,
            allowed_accounts TEXT DEFAULT '[]',
            is_risk_asset INTEGER DEFAULT 1,
            notes TEXT
        )
    ''')
    
    cursor.execute("PRAGMA table_info(assets)")
    columns = [col['name'] for col in cursor.fetchall()]
    if 'is_risk_asset' not in columns:
        cursor.execute("ALTER TABLE assets ADD COLUMN is_risk_asset INTEGER DEFAULT 1")
        
        
    cursor.execute("SELECT COUNT(*) as count FROM assets")
    if cursor.fetchone()['count'] == 0:
        default_assets = [
            ("ACE 미국30년국채액티브(H)", "458250", "KR", 20.0, json.dumps(["ISA", "연금저축계좌", "IRP", "종합매매"], ensure_ascii=False), 0, "채권형 안전자산"),
            ("KODEX 미국나스닥100", "133690", "KR", 25.0, json.dumps(["ISA", "연금저축계좌", "IRP", "종합매매"], ensure_ascii=False), 1, "미국 기술주 (위험자산)"),
            ("KRX 금99.99_1kg (ACE KRX금현물)", "411060", "KR", 15.0, json.dumps(["ISA", "연금저축계좌", "금현물", "종합매매"], ensure_ascii=False), 1, "원자재/금 (위험자산)"),
            ("TIGER 미국배당다우존스", "371460", "KR", 25.0, json.dumps(["ISA", "연금저축계좌", "IRP", "종합매매"], ensure_ascii=False), 1, "배당 성과 (위험자산)"),
            ("INVESCO 원자재 파생 ETF", "PDBC", "US", 15.0, json.dumps(["종합매매"], ensure_ascii=False), 1, "미국 원자재 ETF (위험자산, 연금/ISA 불가)")
        ]
        cursor.executemany('''
            INSERT INTO assets (name, ticker, market, target_weight, allowed_accounts, is_risk_asset, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', default_assets)

    # 3. Holdings Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS holdings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            account_id INTEGER NOT NULL,
            asset_id INTEGER NOT NULL,
            quantity REAL DEFAULT 0.0,
            avg_price REAL DEFAULT 0.0,
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
            FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE,
            UNIQUE(account_id, asset_id)
        )
    ''')
    # 4. Trade History Table
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS trade_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            trade_date TEXT NOT NULL,
            account_id INTEGER NOT NULL,
            asset_id INTEGER NOT NULL,
            trade_type TEXT NOT NULL,
            quantity REAL NOT NULL,
            price REAL NOT NULL,
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
            FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()
    conn.close()

# ---------------------------------------------------------
# Accounts CRUD
# ---------------------------------------------------------
def get_all_accounts():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM accounts ORDER BY id ASC")
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def add_account(account_no, account_alias, account_type, deposit_krw=0.0, deposit_usd=0.0, annual_limit=0.0, tax_limit=0.0, notes="", priority=99, limit_preference="ANNUAL", current_year_deposit=0.0):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            INSERT INTO accounts (account_no, account_alias, account_type, deposit_krw, deposit_usd, annual_limit, tax_limit, notes, priority, limit_preference, current_year_deposit)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (account_no.strip(), account_alias.strip(), account_type, deposit_krw, deposit_usd, annual_limit, tax_limit, notes, priority, limit_preference, current_year_deposit))
        conn.commit()
        return True, "계좌가 성공적으로 추가되었습니다."
    except sqlite3.IntegrityError:
        return False, f"이미 존재하는 계좌번호입니다: {account_no}"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def update_account(account_id, account_no, account_alias, account_type, deposit_krw, deposit_usd, annual_limit, tax_limit, notes="", priority=99, limit_preference="ANNUAL", current_year_deposit=0.0):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE accounts
            SET account_no = ?, account_alias = ?, account_type = ?, deposit_krw = ?, deposit_usd = ?, annual_limit = ?, tax_limit = ?, notes = ?, priority = ?, limit_preference = ?, current_year_deposit = ?
            WHERE id = ?
        ''', (account_no.strip(), account_alias.strip(), account_type, deposit_krw, deposit_usd, annual_limit, tax_limit, notes, priority, limit_preference, current_year_deposit, account_id))
        conn.commit()
        return True, "계좌 정보가 성공적으로 수정되었습니다."
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def update_account_settings(account_id, priority, limit_preference, current_year_deposit):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute('''
            UPDATE accounts
            SET priority = ?, limit_preference = ?, current_year_deposit = ?
            WHERE id = ?
        ''', (priority, limit_preference, current_year_deposit, account_id))
        conn.commit()
        return True, "계좌 상세 설정이 업데이트되었습니다."
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def update_account_priorities(priority_map):
    """priority_map: dict of {account_id: priority_integer}"""
    conn = get_connection()
    cursor = conn.cursor()
    try:
        for acc_id, prio in priority_map.items():
            cursor.execute("UPDATE accounts SET priority = ? WHERE id = ?", (prio, acc_id))
        conn.commit()
        return True
    except Exception as e:
        return False
    finally:
        conn.close()

def delete_account(account_id):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM holdings WHERE account_id = ?", (account_id,))
        cursor.execute("DELETE FROM accounts WHERE id = ?", (account_id,))
        conn.commit()
        return True, "계좌 및 보유 내역이 삭제되었습니다."
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

# ---------------------------------------------------------
# Assets Helpers (With automatic Account Name Sanitization)
# ---------------------------------------------------------
def get_all_assets():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM assets ORDER BY id ASC")
    rows = []
    for row in cursor.fetchall():
        r = dict(row)
        try:
            raw_accs = json.loads(r['allowed_accounts']) if r['allowed_accounts'] else []
        except Exception:
            raw_accs = []
        r['allowed_accounts'] = sanitize_account_names(raw_accs)
        r['is_risk_asset'] = bool(r.get('is_risk_asset', 1))
        rows.append(r)
    conn.close()
    return rows

def add_asset(name, ticker, market, target_weight, allowed_accounts=None, is_risk_asset=True, notes=""):
    if allowed_accounts is None:
        allowed_accounts = []
    clean_accs = sanitize_account_names(allowed_accounts)
    conn = get_connection()
    cursor = conn.cursor()
    try:
        allowed_json = json.dumps(clean_accs, ensure_ascii=False)
        cursor.execute('''
            INSERT INTO assets (name, ticker, market, target_weight, allowed_accounts, is_risk_asset, notes)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (name, ticker.strip().upper(), market, target_weight, allowed_json, 1 if is_risk_asset else 0, notes))
        conn.commit()
        return True, "성공적으로 추가되었습니다."
    except sqlite3.IntegrityError:
        return False, f"이미 존재하는 티커/종목코드입니다: {ticker}"
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def update_asset(asset_id, name, ticker, market, target_weight, allowed_accounts, is_risk_asset=True, notes=""):
    print(f"[DEBUG] update_asset called for {name}, is_risk_asset={is_risk_asset}")
    clean_accs = sanitize_account_names(allowed_accounts)
    conn = get_connection()
    cursor = conn.cursor()
    try:
        allowed_json = json.dumps(clean_accs, ensure_ascii=False)
        cursor.execute('''
            UPDATE assets
            SET name = ?, ticker = ?, market = ?, target_weight = ?, allowed_accounts = ?, is_risk_asset = ?, notes = ?
            WHERE id = ?
        ''', (name, ticker.strip().upper(), market, target_weight, allowed_json, 1 if is_risk_asset else 0, notes, asset_id))
        conn.commit()
        return True, "성공적으로 수정되었습니다."
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

def delete_asset(asset_id):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        cursor.execute("DELETE FROM holdings WHERE asset_id = ?", (asset_id,))
        cursor.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
        conn.commit()
        return True, "성공적으로 삭제되었습니다."
    except Exception as e:
        return False, str(e)
    finally:
        conn.close()

# ---------------------------------------------------------
# Holdings Helpers
# ---------------------------------------------------------
def get_holdings_by_account(account_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT h.*, a.name as asset_name, a.ticker, a.market, a.is_risk_asset
        FROM holdings h
        JOIN assets a ON h.asset_id = a.id
        WHERE h.account_id = ?
    ''', (account_id,))
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def get_all_holdings():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT h.*, a.name as asset_name, a.ticker, a.market, a.is_risk_asset, acc.account_alias, acc.account_type
        FROM holdings h
        JOIN assets a ON h.asset_id = a.id
        JOIN accounts acc ON h.account_id = acc.id
    ''')
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def save_account_holdings(account_id, holdings_data):
    try:
        from datetime import datetime
        today_str = datetime.now().strftime('%Y-%m-%d')
        
        for item in holdings_data:
            # INIT trade를 발행하여 장부 이정표를 세움
            # execute_trade 내부에서 INIT 타입일 경우 holdings 덮어쓰기를 자동으로 수행함
            success, msg = execute_trade(today_str, account_id, item['asset_id'], 'INIT', item['quantity'], item['avg_price'])
            if not success:
                return False, f"보정 실패: {msg}"
                
        return True, "보유 내역이 성공적으로 장부에 보정 기록되었습니다."
    except Exception as e:
        return False, str(e)

# ---------------------------------------------------------
# Trade History & Execution
# ---------------------------------------------------------
def execute_trade(trade_date, account_id, asset_id, trade_type, quantity, price):
    """
    매매 기록을 trade_history 테이블에 남기고, holdings 테이블의 수량/평단가를 업데이트합니다.
    """
    if quantity <= 0 or price <= 0:
        return False, "수량과 단가는 0보다 커야 합니다."
        
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # 1. trade_history 기록
        cursor.execute('''
            INSERT INTO trade_history (trade_date, account_id, asset_id, trade_type, quantity, price)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (trade_date, account_id, asset_id, trade_type, quantity, price))
        
        # 2. 현재 holdings 조회
        cursor.execute('''
            SELECT quantity, avg_price FROM holdings 
            WHERE account_id = ? AND asset_id = ?
        ''', (account_id, asset_id))
        
        row = cursor.fetchone()
        
        if row:
            curr_qty = row['quantity']
            curr_avg_price = row['avg_price']
            
            if trade_type == 'INIT':
                new_qty = quantity
                new_avg_price = price
            elif trade_type == 'BUY':
                new_qty = curr_qty + quantity
                # 매수 시 가중평균
                if new_qty > 0:
                    new_avg_price = ((curr_qty * curr_avg_price) + (quantity * price)) / new_qty
                else:
                    new_avg_price = price
            else: # SELL
                new_qty = curr_qty - quantity
                new_avg_price = curr_avg_price # 매도시 평단가 유지
                
                if new_qty <= 0:
                    new_qty = 0
                    new_avg_price = 0.0
                    
            cursor.execute('''
                UPDATE holdings
                SET quantity = ?, avg_price = ?
                WHERE account_id = ? AND asset_id = ?
            ''', (new_qty, new_avg_price, account_id, asset_id))
            
        else:
            if trade_type in ('BUY', 'INIT'):
                cursor.execute('''
                    INSERT INTO holdings (account_id, asset_id, quantity, avg_price)
                    VALUES (?, ?, ?, ?)
                ''', (account_id, asset_id, quantity, price))
            else:
                return False, "매도할 보유 잔고가 없습니다."
                
        conn.commit()
        return True, "매매 기록 및 잔고 업데이트가 완료되었습니다."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()

def get_trade_history():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute('''
        SELECT t.*, a.account_alias, a.account_type, ast.name as asset_name, ast.ticker
        FROM trade_history t
        JOIN accounts a ON t.account_id = a.id
        JOIN assets ast ON t.asset_id = ast.id
        WHERE t.trade_type != 'INIT'
        ORDER BY t.trade_date DESC, t.id DESC
    ''')
    rows = [dict(row) for row in cursor.fetchall()]
    conn.close()
    return rows

def delete_trade(trade_id):
    conn = get_connection()
    cursor = conn.cursor()
    try:
        # 1. Get trade info
        cursor.execute("SELECT account_id, asset_id FROM trade_history WHERE id = ?", (trade_id,))
        row = cursor.fetchone()
        if not row:
            return False, "존재하지 않는 매매 기록입니다."
        
        account_id = row['account_id']
        asset_id = row['asset_id']
        
        # 2. Delete trade
        cursor.execute("DELETE FROM trade_history WHERE id = ?", (trade_id,))
        
        # 3. Recalculate holdings for this account_id, asset_id
        cursor.execute('''
            SELECT trade_type, quantity, price 
            FROM trade_history 
            WHERE account_id = ? AND asset_id = ? 
            ORDER BY trade_date ASC, id ASC
        ''', (account_id, asset_id))
        
        remaining_trades = cursor.fetchall()
        
        new_qty = 0.0
        new_avg_price = 0.0
        
        for t in remaining_trades:
            t_type = t['trade_type']
            t_qty = t['quantity']
            t_price = t['price']
            
            if t_type == 'INIT':
                new_qty = t_qty
                new_avg_price = t_price
            elif t_type == 'BUY':
                next_qty = new_qty + t_qty
                if next_qty > 0:
                    new_avg_price = ((new_qty * new_avg_price) + (t_qty * t_price)) / next_qty
                else:
                    new_avg_price = t_price
                new_qty = next_qty
            else: # SELL
                new_qty -= t_qty
                if new_qty <= 0:
                    new_qty = 0.0
                    new_avg_price = 0.0
                    
        # Update holdings
        if new_qty > 0:
            cursor.execute('''
                INSERT INTO holdings (account_id, asset_id, quantity, avg_price)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(account_id, asset_id) DO UPDATE SET
                    quantity = excluded.quantity,
                    avg_price = excluded.avg_price
            ''', (account_id, asset_id, new_qty, new_avg_price))
        else:
            # If no quantity left, delete the holdings record
            cursor.execute('''
                DELETE FROM holdings 
                WHERE account_id = ? AND asset_id = ?
            ''', (account_id, asset_id))
            
        conn.commit()
        return True, "매매 기록이 삭제되었으며, 평단가가 정상적으로 롤백되었습니다."
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()

if __name__ == "__main__":
    init_db()
    print("Database sanitized and initialized!")
