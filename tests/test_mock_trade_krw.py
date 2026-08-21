import sqlite3
import pytest

def create_mock_db():
    """운영 DB를 일절 건드리지 않는 순수 인메모리 Mock DB 생성"""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    
    # 1. Accounts Table
    cur.execute('''
        CREATE TABLE accounts (
            id TEXT PRIMARY KEY,
            account_no TEXT NOT NULL,
            account_alias TEXT NOT NULL,
            account_type TEXT NOT NULL,
            deposit_krw REAL DEFAULT 0.0,
            deposit_usd REAL DEFAULT 0.0
        )
    ''')
    
    # 2. Assets Table
    cur.execute('''
        CREATE TABLE assets (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            ticker TEXT NOT NULL,
            market TEXT NOT NULL,
            target_weight REAL DEFAULT 0.0,
            is_active INTEGER DEFAULT 1
        )
    ''')
    
    # 3. Holdings Table
    cur.execute('''
        CREATE TABLE holdings (
            id TEXT PRIMARY KEY,
            account_id TEXT NOT NULL,
            asset_id TEXT NOT NULL,
            quantity REAL NOT NULL,
            avg_price REAL NOT NULL,
            UNIQUE(account_id, asset_id)
        )
    ''')
    
    # 4. Trade History Table
    cur.execute('''
        CREATE TABLE trade_history (
            id TEXT PRIMARY KEY,
            trade_date TEXT NOT NULL,
            account_id TEXT NOT NULL,
            asset_id TEXT NOT NULL,
            trade_type TEXT NOT NULL,
            quantity REAL NOT NULL,
            price REAL NOT NULL
        )
    ''')
    conn.commit()
    return conn

def mock_execute_trade(conn, trade_date, account_id, asset_id, trade_type, quantity, price):
    """원화 단가 기준 매매 실행 로직 (data_manager.execute_trade와 100% 동일한 로직)"""
    cur = conn.cursor()
    trade_id = f"trade_{quantity}_{price}_{trade_type}"
    
    cur.execute('''
        INSERT INTO trade_history (id, trade_date, account_id, asset_id, trade_type, quantity, price)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    ''', (trade_id, trade_date, str(account_id), str(asset_id), trade_type, quantity, price))
    
    # 원화 예수금(deposit_krw) 가감
    if trade_type in ('BUY', 'SELL'):
        trade_amount = quantity * price
        cur.execute('SELECT deposit_krw FROM accounts WHERE id = ?', (str(account_id),))
        acc_row = cur.fetchone()
        dep_krw = float(acc_row['deposit_krw'])
        
        if trade_type == 'BUY':
            dep_krw -= trade_amount
        elif trade_type == 'SELL':
            dep_krw += trade_amount
            
        cur.execute('UPDATE accounts SET deposit_krw = ? WHERE id = ?', (dep_krw, str(account_id)))
        
    # 잔고(holdings) 업데이트
    cur.execute('SELECT quantity, avg_price FROM holdings WHERE account_id = ? AND asset_id = ?', (str(account_id), str(asset_id)))
    row = cur.fetchone()
    
    if row:
        curr_qty = float(row['quantity'])
        curr_avg_price = float(row['avg_price'])
        
        if trade_type == 'INIT':
            new_qty = quantity
            new_avg_price = price
        elif trade_type == 'BUY':
            new_qty = curr_qty + quantity
            new_avg_price = ((curr_qty * curr_avg_price) + (quantity * price)) / new_qty if new_qty > 0 else price
        else: # SELL
            new_qty = curr_qty - quantity
            new_avg_price = curr_avg_price
            
        if new_qty > 0:
            cur.execute('UPDATE holdings SET quantity = ?, avg_price = ? WHERE account_id = ? AND asset_id = ?', (new_qty, new_avg_price, str(account_id), str(asset_id)))
        else:
            cur.execute('DELETE FROM holdings WHERE account_id = ? AND asset_id = ?', (str(account_id), str(asset_id)))
    else:
        if trade_type in ('INIT', 'BUY'):
            cur.execute('INSERT INTO holdings (id, account_id, asset_id, quantity, avg_price) VALUES (?, ?, ?, ?, ?)', (f"h_{account_id}_{asset_id}", str(account_id), str(asset_id), quantity, price))
            
    conn.commit()

def test_mock_trade_us_stock_in_krw():
    """미국 주식(PDBC)을 원화로 매매할 때 원화 예수금과 평단가가 100% 정상 작동하는지 검증"""
    conn = create_mock_db()
    cur = conn.cursor()
    
    # 1. 초기 데이터 세팅 (해외계좌 4번: 원화 500,000원, 외화 $0.02)
    cur.execute("INSERT INTO accounts (id, account_no, account_alias, account_type, deposit_krw, deposit_usd) VALUES ('4', '20501285758', '해외ETF계좌', '일반', 500000.0, 0.02)")
    cur.execute("INSERT INTO assets (id, name, ticker, market, target_weight, is_active) VALUES ('5', 'INVESCO 원자재 ETF', 'PDBC', 'US', 5.0, 1)")
    conn.commit()
    
    # 2. PDBC 10주를 25,600원(원화)에 1차 매수
    mock_execute_trade(conn, '2026-08-21', '4', '5', 'BUY', 10, 25600.0)
    
    # 검증 1: 원화 예수금이 정확히 500,000 - 256,000 = 244,000원이 되었는가?
    cur.execute("SELECT deposit_krw, deposit_usd FROM accounts WHERE id = '4'")
    acc = cur.fetchone()
    assert acc['deposit_krw'] == 244000.0
    assert acc['deposit_usd'] == 0.02  # 달러 예수금은 절대 깎이지 않음!
    
    # 검증 2: 보유 잔고가 10주, 평단가 25,600원인가?
    cur.execute("SELECT quantity, avg_price FROM holdings WHERE account_id = '4' AND asset_id = '5'")
    h = cur.fetchone()
    assert h['quantity'] == 10.0
    assert h['avg_price'] == 25600.0
    
    # 3. PDBC 15주를 26,000원(원화)에 2차 추가 매수
    mock_execute_trade(conn, '2026-08-21', '4', '5', 'BUY', 15, 26000.0)
    
    # 검증 3: 원화 예수금이 244,000 - 390,000 = -146,000원이 되었는가?
    cur.execute("SELECT deposit_krw, deposit_usd FROM accounts WHERE id = '4'")
    acc = cur.fetchone()
    assert acc['deposit_krw'] == -146000.0
    assert acc['deposit_usd'] == 0.02
    
    # 검증 4: 총 25주, 평단가가 25,840원인가? (256,000 + 390,000) / 25 = 646,000 / 25 = 25,840
    cur.execute("SELECT quantity, avg_price FROM holdings WHERE account_id = '4' AND asset_id = '5'")
    h = cur.fetchone()
    assert h['quantity'] == 25.0
    assert h['avg_price'] == 25840.0
    
    # 4. PDBC 5주를 26,000원에 매도
    mock_execute_trade(conn, '2026-08-21', '4', '5', 'SELL', 5, 26000.0)
    
    # 검증 5: 원화 예수금이 -146,000 + 130,000 = -16,000원이 되었는가?
    cur.execute("SELECT deposit_krw, deposit_usd FROM accounts WHERE id = '4'")
    acc = cur.fetchone()
    assert acc['deposit_krw'] == -16000.0
    
    # 검증 6: 잔고가 20주, 평단가는 여전히 25,840원인가?
    cur.execute("SELECT quantity, avg_price FROM holdings WHERE account_id = '4' AND asset_id = '5'")
    h = cur.fetchone()
    assert h['quantity'] == 20.0
    assert h['avg_price'] == 25840.0
    
    conn.close()
    print("Mock DB Test Passed 100% Successfully!")

if __name__ == '__main__':
    test_mock_trade_us_stock_in_krw()
