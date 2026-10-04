"""Raw balances, manual snapshots and broker synchronization. No market IO."""
from datetime import datetime
from psycopg2.extras import RealDictCursor
from data.repository_context import RepositoryContext

def get_holdings_by_account(db: RepositoryContext, account_id):
    conn = db.connect()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute('''
            SELECT h.*, a.name as asset_name, a.ticker, a.market, a.is_risk_asset,
                   a.is_deposit, a.deposit_principal, a.interest_rate, a.start_date, a.maturity_date, a.tax_rate, a.lock_rebalance_sell,
                   a.is_dividend_cost_deduct,
                   acc.account_type, acc.account_alias,
                   (
                       SELECT 
                           CASE 
                               WHEN EXISTS (
                                   SELECT 1 FROM trade_history t0 
                                   WHERE t0.account_id = h.account_id 
                                     AND t0.asset_id = h.asset_id 
                                     AND t0.trade_date <= '2000-01-01'
                               ) THEN '2026-07-01'
                               ELSE MIN(t.trade_date)
                           END
                       FROM trade_history t 
                       WHERE t.account_id = h.account_id 
                         AND t.asset_id = h.asset_id
                   ) as min_trade_date
            FROM holdings h
            JOIN assets a ON h.asset_id = a.id
            JOIN accounts acc ON h.account_id = acc.id
            WHERE h.account_id = %s
        ''', (str(account_id),))
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_all_holdings(db: RepositoryContext, portfolio_id: str = None):
    conn = db.connect()
    try:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        sql = '''
            SELECT h.*, a.name as asset_name, a.ticker, a.market, a.is_risk_asset,
                   a.is_deposit, a.deposit_principal, a.interest_rate, a.start_date, a.maturity_date, a.tax_rate, a.lock_rebalance_sell,
                   a.is_dividend_cost_deduct,
                   acc.account_alias, acc.account_type
            FROM holdings h
            JOIN assets a ON h.asset_id = a.id
            JOIN accounts acc ON h.account_id = acc.id
        '''
        if portfolio_id:
            cursor.execute(sql + ' WHERE acc.portfolio_id = %s', (portfolio_id,))
        else:
            cursor.execute(sql)
        rows = cursor.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def save_account_holdings(db: RepositoryContext, account_id, holdings_data):
    conn = db.connect()
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

            original_avg_p = float(item.get('original_avg_price') or 0.0)
            if original_avg_p <= 0:
                original_avg_p = avg_p
            original_avg_p_usd = float(item.get('original_avg_price_usd') or 0.0)
            if original_avg_p_usd <= 0:
                original_avg_p_usd = avg_p_usd
            cursor.execute("SELECT id, first_buy_date FROM holdings WHERE account_id = %s AND asset_id = %s", (str(account_id), aid))
            row = cursor.fetchone()

            first_buy_date = str(item.get('first_buy_date') or '').strip()
            if not first_buy_date and row and row[1]:
                first_buy_date = str(row[1]).strip()

            manual_div = item.get('manual_dividend_override')
            if manual_div is not None and str(manual_div).strip() != '':
                manual_div = float(manual_div)
            else:
                manual_div = None

            if 'is_dividend_cost_deduct' in item and item['is_dividend_cost_deduct'] is not None:
                cursor.execute("UPDATE assets SET is_dividend_cost_deduct = %s WHERE id = %s", (bool(item['is_dividend_cost_deduct']), aid))
            
            if qty <= 0:
                if row:
                    cursor.execute("DELETE FROM holdings WHERE id = %s", (row[0],))
            else:
                if row:
                    cursor.execute("""
                        UPDATE holdings 
                        SET quantity = %s, avg_price = %s, avg_price_usd = %s, buy_fx_rate = %s,
                            original_avg_price = %s, original_avg_price_usd = %s, first_buy_date = %s,
                            manual_dividend_override = %s
                        WHERE id = %s
                    """, (qty, avg_p, avg_p_usd, buy_fx, original_avg_p, original_avg_p_usd, first_buy_date, manual_div, row[0]))
                else:
                    new_h_id = db.new_id()
                    cursor.execute("""
                        INSERT INTO holdings (
                            id, account_id, asset_id, quantity, avg_price, avg_price_usd, buy_fx_rate,
                            original_avg_price, original_avg_price_usd, first_buy_date, manual_dividend_override
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    """, (new_h_id, str(account_id), aid, qty, avg_p, avg_p_usd, buy_fx, original_avg_p, original_avg_p_usd, first_buy_date, manual_div))
                    
                new_trade_id = db.new_id()
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


def sync_account_with_api(db: RepositoryContext, account_id, api_data):
    if not api_data:
        return False, "API 데이터가 없습니다."
        
    conn = db.connect()
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
                avg_p_usd = float(h.get('avg_price_usd', 0.0))
                buy_fx = float(h.get('buy_fx_rate', 0.0))
                
                # Check if exists
                cursor.execute("SELECT id FROM holdings WHERE account_id = %s AND asset_id = %s", (str(account_id), aid))
                row = cursor.fetchone()
                if row:
                    if avg_p_usd > 0:
                        cursor.execute("UPDATE holdings SET quantity = %s, avg_price = %s, original_avg_price = %s, avg_price_usd = %s, original_avg_price_usd = %s, buy_fx_rate = %s WHERE id = %s", (qty, avg_p, avg_p, avg_p_usd, avg_p_usd, buy_fx, row[0]))
                    else:
                        cursor.execute("UPDATE holdings SET quantity = %s, avg_price = %s, original_avg_price = %s WHERE id = %s", (qty, avg_p, avg_p, row[0]))
                else:
                    new_h_id = db.new_id()
                    cursor.execute("INSERT INTO holdings (id, account_id, asset_id, quantity, avg_price, original_avg_price, avg_price_usd, original_avg_price_usd, buy_fx_rate) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)", (new_h_id, str(account_id), aid, qty, avg_p, avg_p, avg_p_usd, avg_p_usd, buy_fx))
                    
                # Upsert INIT trade to trade_history to reflect the sync without creating endless duplicates
                cursor.execute('''
                    SELECT id FROM trade_history 
                    WHERE account_id = %s AND asset_id = %s AND trade_type = 'INIT' AND trade_date = %s
                ''', (str(account_id), aid, today_str))
                init_row = cursor.fetchone()
                if init_row:
                    cursor.execute('''
                        UPDATE trade_history SET quantity = %s, price = %s WHERE id = %s
                    ''', (qty, avg_p, init_row[0]))
                else:
                    new_t_id = db.new_id()
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
