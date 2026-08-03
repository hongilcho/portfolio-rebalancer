import os
import json
import uuid
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
import streamlit as st

# 사용자 정의 6가지 표준 계좌 유형
ACCOUNT_TYPES = {
    "종합매매": {"annual_limit": 0, "tax_limit": 0, "max_risk_pct": 100},
    "CMA": {"annual_limit": 0, "tax_limit": 0, "max_risk_pct": 100},
    "연금저축계좌": {"annual_limit": 15000000, "tax_limit": 6000000, "max_risk_pct": 100},
    "ISA": {"annual_limit": 20000000, "tax_limit": 0, "max_risk_pct": 100},
    "금현물": {"annual_limit": 0, "tax_limit": 0, "max_risk_pct": 100},
    "IRP": {"annual_limit": 3000000, "tax_limit": 3000000, "max_risk_pct": 70}
}

ACCOUNT_NAME_MAP = {
    "ISA 계좌": "ISA",
    "개인형 IRP": "IRP",
    "해외주식 일반계좌": "종합매매",
    "국내주식 일반계좌": "종합매매",
    "해외주식계좌": "종합매매",
    "일반계좌": "종합매매",
    "기본계좌": "종합매매"
}

def get_connection():
    try:
        pg_url = st.secrets["SUPABASE_URL"]
    except FileNotFoundError:
        # Fallback if secrets.toml isn't loaded (e.g. running outside Streamlit)
        import toml
        secrets_path = os.path.join(os.path.dirname(__file__), ".streamlit", "secrets.toml")
        with open(secrets_path, "r", encoding="utf-8") as f:
            secrets = toml.load(f)
            pg_url = secrets["SUPABASE_URL"]
            
    conn = psycopg2.connect(pg_url)
    return conn

def sanitize_account_names(acc_list):
    clean_set = set()
    for acc in acc_list:
        if str(acc).isdigit():
            clean_set.add(str(acc))
    return sorted(list(clean_set))

def generate_id():
    return uuid.uuid4().hex

def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    
    # Postgres schema setup
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
            notes TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS assets (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            ticker TEXT NOT NULL UNIQUE,
            market TEXT NOT NULL CHECK(market IN ('KR', 'US')),
            target_weight REAL DEFAULT 0.0,
            allowed_accounts TEXT DEFAULT '[]',
            is_risk_asset INTEGER DEFAULT 1,
            notes TEXT
        )
    ''')

    cursor.execute('''
        CREATE TABLE IF NOT EXISTS holdings (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            asset_id TEXT NOT NULL,
            quantity REAL DEFAULT 0.0,
            avg_price REAL DEFAULT 0.0,
            FOREIGN KEY (account_id) REFERENCES accounts(id) ON DELETE CASCADE,
            FOREIGN KEY (asset_id) REFERENCES assets(id) ON DELETE CASCADE,
            UNIQUE(account_id, asset_id)
        )
    ''')

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
    
    # 누적 납입금액 초기화
    current_year = datetime.now().year
    cursor.execute("SELECT id, last_updated_year FROM accounts")
    for row in cursor.fetchall():
        if row[1] and row[1] < current_year:
            cursor.execute("UPDATE accounts SET current_year_deposit = 0.0, last_updated_year = %s WHERE id = %s", (current_year, row[0]))

    conn.commit()
    conn.close()

# ---------------------------------------------------------
# Accounts CRUD
# ---------------------------------------------------------
def get_all_accounts():
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM accounts ORDER BY account_alias ASC")
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def add_account(account_no, account_alias, account_type, deposit_krw=0.0, deposit_usd=0.0, annual_limit=0.0, tax_limit=0.0, notes="", priority=99, limit_preference="ANNUAL", current_year_deposit=0.0):
    conn = get_connection()
    cursor = conn.cursor()
    new_id = generate_id()
    try:
        cursor.execute('''
            INSERT INTO accounts (id, account_no, account_alias, account_type, deposit_krw, deposit_usd, annual_limit, tax_limit, notes, priority, limit_preference, current_year_deposit)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        ''', (new_id, account_no.strip(), account_alias.strip(), account_type, deposit_krw, deposit_usd, annual_limit, tax_limit, notes, priority, limit_preference, current_year_deposit))
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
def get_all_assets():
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute("SELECT * FROM assets ORDER BY name ASC")
    rows = []
    for r in cursor.fetchall():
        r = dict(r)
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
    new_id = generate_id()
    try:
        allowed_json = json.dumps(clean_accs, ensure_ascii=False)
        cursor.execute('''
            INSERT INTO assets (id, name, ticker, market, target_weight, allowed_accounts, is_risk_asset, notes)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
        ''', (new_id, name, ticker.strip().upper(), market, target_weight, allowed_json, 1 if is_risk_asset else 0, notes))
        conn.commit()
        return True, "성공적으로 추가되었습니다."
    except psycopg2.IntegrityError:
        conn.rollback()
        return False, f"이미 존재하는 티커/종목코드입니다: {ticker}"
    except Exception as e:
        conn.rollback()
        return False, str(e)
    finally:
        conn.close()

def update_asset(asset_id, name, ticker, market, target_weight, allowed_accounts, is_risk_asset=True, notes=""):
    clean_accs = sanitize_account_names(allowed_accounts)
    conn = get_connection()
    cursor = conn.cursor()
    try:
        allowed_json = json.dumps(clean_accs, ensure_ascii=False)
        cursor.execute('''
            UPDATE assets
            SET name = %s, ticker = %s, market = %s, target_weight = %s, allowed_accounts = %s, is_risk_asset = %s, notes = %s
            WHERE id = %s
        ''', (name, ticker.strip().upper(), market, target_weight, allowed_json, 1 if is_risk_asset else 0, notes, str(asset_id)))
        conn.commit()
        return True, "성공적으로 수정되었습니다."
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
        cursor.execute("DELETE FROM assets WHERE id = %s", (str(asset_id),))
        conn.commit()
        return True, "성공적으로 삭제되었습니다."
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
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute('''
        SELECT h.*, a.name as asset_name, a.ticker, a.market, a.is_risk_asset
        FROM holdings h
        JOIN assets a ON h.asset_id = a.id
        WHERE h.account_id = %s
    ''', (str(account_id),))
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def get_all_holdings():
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute('''
        SELECT h.*, a.name as asset_name, a.ticker, a.market, a.is_risk_asset, acc.account_alias, acc.account_type
        FROM holdings h
        JOIN assets a ON h.asset_id = a.id
        JOIN accounts acc ON h.account_id = acc.id
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

def save_account_holdings(account_id, holdings_data):
    try:
        today_str = datetime.now().strftime('%Y-%m-%d')
        for item in holdings_data:
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
    if quantity <= 0 or price <= 0:
        return False, "수량과 단가는 0보다 커야 합니다."
        
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    new_trade_id = generate_id()
    try:
        cursor.execute('''
            INSERT INTO trade_history (id, trade_date, account_id, asset_id, trade_type, quantity, price)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        ''', (new_trade_id, trade_date, str(account_id), str(asset_id), trade_type, quantity, price))
        
        cursor.execute('''
            SELECT quantity, avg_price FROM holdings 
            WHERE account_id = %s AND asset_id = %s
        ''', (str(account_id), str(asset_id)))
        
        row = cursor.fetchone()
        
        if row:
            curr_qty = float(row['quantity'])
            curr_avg_price = float(row['avg_price'])
            
            if trade_type == 'INIT':
                new_qty = quantity
                new_avg_price = price
            elif trade_type == 'BUY':
                new_qty = curr_qty + quantity
                if new_qty > 0:
                    new_avg_price = ((curr_qty * curr_avg_price) + (quantity * price)) / new_qty
                else:
                    new_avg_price = price
            else: # SELL
                new_qty = curr_qty - quantity
                new_avg_price = curr_avg_price
                if new_qty <= 0:
                    new_qty = 0
                    new_avg_price = 0.0
                    
            cursor.execute('''
                UPDATE holdings
                SET quantity = %s, avg_price = %s
                WHERE account_id = %s AND asset_id = %s
            ''', (new_qty, new_avg_price, str(account_id), str(asset_id)))
            
        else:
            if trade_type in ('BUY', 'INIT'):
                new_h_id = generate_id()
                cursor.execute('''
                    INSERT INTO holdings (id, account_id, asset_id, quantity, avg_price)
                    VALUES (%s, %s, %s, %s, %s)
                ''', (new_h_id, str(account_id), str(asset_id), quantity, price))
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

def get_trade_history():
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    cursor.execute('''
        SELECT t.*, a.account_alias, a.account_type, ast.name as asset_name, ast.ticker
        FROM trade_history t
        JOIN accounts a ON t.account_id = a.id
        JOIN assets ast ON t.asset_id = ast.id
        WHERE t.trade_type != 'INIT'
        ORDER BY t.trade_date DESC, t.id DESC
    ''')
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]

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
            SELECT trade_type, quantity, price 
            FROM trade_history 
            WHERE account_id = %s AND asset_id = %s 
            ORDER BY trade_date ASC, id ASC
        ''', (account_id, asset_id))
        
        remaining_trades = cursor.fetchall()
        
        new_qty = 0.0
        new_avg_price = 0.0
        
        for t in remaining_trades:
            t_type = t['trade_type']
            t_qty = float(t['quantity'])
            t_price = float(t['price'])
            
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
                    
        if new_qty > 0:
            cursor.execute('''
                INSERT INTO holdings (id, account_id, asset_id, quantity, avg_price)
                VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT(account_id, asset_id) DO UPDATE SET
                    quantity = EXCLUDED.quantity,
                    avg_price = EXCLUDED.avg_price
            ''', (generate_id(), account_id, asset_id, new_qty, new_avg_price))
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

if __name__ == "__main__":
    init_db()
    print("PostgreSQL Database sanitized and initialized!")
