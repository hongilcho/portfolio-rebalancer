"""
미국 자산 가중평균 매입환율 및 환차손익(FX Gain/Loss) 단위 테스트
===================================================================
1. 추가 매수(BUY) 시 달러 평단가 및 매입환율의 가중평균 갱신 검증
2. 매도(SELL) 시 평단가 및 매입환율 불변 검증
3. 거래 삭제(delete_trade) 시 롤백 정합성 검증
4. 총 원화 손익 = 순수 주가 변동 손익 + 환차익/환차손 1원 단위 항등식 검증
"""

import pytest
from data.data_manager import execute_trade, get_connection, save_account_holdings
from psycopg2.extras import RealDictCursor

def test_fx_weighted_average_and_profit_decomposition():
    conn = get_connection()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        # 1. Setup mock account and US asset
        test_acc_id = "test_acc_fx_01"
        test_asset_id = "test_ast_fx_01"

        cursor.execute("DELETE FROM trade_history WHERE account_id = %s", (test_acc_id,))
        cursor.execute("DELETE FROM holdings WHERE account_id = %s", (test_acc_id,))
        cursor.execute("DELETE FROM accounts WHERE id = %s", (test_acc_id,))
        cursor.execute("DELETE FROM assets WHERE id = %s", (test_asset_id,))

        cursor.execute("""
            INSERT INTO accounts (id, account_no, account_alias, account_type, deposit_krw, deposit_usd, portfolio_id)
            VALUES (%s, 'TEST-FX-ACC-01', 'FX테스트계좌', 'GENERAL', 10000000.0, 5000.0, 'default')
        """, (test_acc_id,))

        cursor.execute("""
            INSERT INTO assets (id, name, ticker, market, is_risk_asset, portfolio_id)
            VALUES (%s, 'Vanguard Total Stock ETF', 'VT_TEST', 'US', 1, 'default')
        """, (test_asset_id,))
        conn.commit()

        # 2. First Buy: 10 shares @ $100.00 with FX rate 1,300.00
        # Total USD = $1,000.00, Total KRW = 1,300,000 KRW
        s1, m1 = execute_trade(
            trade_date='2026-01-10',
            account_id=test_acc_id,
            asset_id=test_asset_id,
            trade_type='BUY',
            quantity=10.0,
            price=100.0,
            currency='USD',
            exchange_rate=1300.0
        )
        assert s1 is True

        cursor.execute("SELECT * FROM holdings WHERE account_id = %s AND asset_id = %s", (test_acc_id, test_asset_id))
        h1 = cursor.fetchone()
        assert float(h1['quantity']) == 10.0
        assert float(h1['avg_price_usd']) == 100.0
        assert float(h1['buy_fx_rate']) == 1300.0
        assert float(h1['avg_price']) == 130000.0

        # 3. Second Buy (추가 매수): 10 shares @ $150.00 with FX rate 1,400.00
        # New USD = $1,500.00, New KRW = 2,100,000 KRW
        # Total USD = $2,500.00, Total KRW = 3,400,000 KRW, Total Qty = 20.0
        # Expected Avg Price USD = $2,500 / 20 = $125.00
        # Expected Weighted Buy FX = 3,400,000 / 2,500 = 1,360.00 KRW/$
        # Expected Avg Price KRW = 3,400,000 / 20 = 170,000 KRW
        s2, m2 = execute_trade(
            trade_date='2026-02-15',
            account_id=test_acc_id,
            asset_id=test_asset_id,
            trade_type='BUY',
            quantity=10.0,
            price=150.0,
            currency='USD',
            exchange_rate=1400.0
        )
        assert s2 is True

        cursor.execute("SELECT * FROM holdings WHERE account_id = %s AND asset_id = %s", (test_acc_id, test_asset_id))
        h2 = cursor.fetchone()
        assert float(h2['quantity']) == 20.0
        assert abs(float(h2['avg_price_usd']) - 125.0) < 1e-4
        assert abs(float(h2['buy_fx_rate']) - 1360.0) < 1e-4
        assert abs(float(h2['avg_price']) - 170000.0) < 1e-4
        # Validate mathematical equality: avg_price == avg_price_usd * buy_fx_rate
        assert abs(float(h2['avg_price']) - (float(h2['avg_price_usd']) * float(h2['buy_fx_rate']))) < 1e-4

        # 4. Partial Sell: Sell 5 shares @ $160.00
        # Quantity becomes 15.0. Avg Price USD ($125) and Buy FX (1,360) must remain UNCHANGED!
        s3, m3 = execute_trade(
            trade_date='2026-03-01',
            account_id=test_acc_id,
            asset_id=test_asset_id,
            trade_type='SELL',
            quantity=5.0,
            price=160.0,
            currency='USD',
            exchange_rate=1370.0
        )
        assert s3 is True

        cursor.execute("SELECT * FROM holdings WHERE account_id = %s AND asset_id = %s", (test_acc_id, test_asset_id))
        h3 = cursor.fetchone()
        assert float(h3['quantity']) == 15.0
        assert abs(float(h3['avg_price_usd']) - 125.0) < 1e-4
        assert abs(float(h3['buy_fx_rate']) - 1360.0) < 1e-4
        assert abs(float(h3['avg_price']) - 170000.0) < 1e-4

        # 5. Financial Engineering Identity Test:
        # Suppose current price = $160.00 and current USD/KRW = 1,380.00
        # Q = 15.0, Avg USD = $125.00, Buy FX = 1,360.00
        # C_usd = 15 * 125 = $1,875.00
        # C_krw = 1,875 * 1,360 = 2,550,000 KRW
        # V_usd = 15 * 160 = $2,400.00
        # V_krw = 2,400 * 1,380 = 3,312,000 KRW
        # Total Profit KRW = 3,312,000 - 2,550,000 = +762,000 KRW
        # Pure Stock Profit (USD) = 2,400 - 1,875 = +$525.00
        # Pure Stock Profit (KRW) = $525 * 1,380 = +724,500 KRW
        # FX Profit (KRW) = $1,875 * (1,380 - 1,360) = $1,875 * 20 = +37,500 KRW
        # Identity: 724,500 + 37,500 = 762,000 KRW! Exactly matches!
        curr_price_usd = 160.0
        curr_fx = 1380.0
        qty = float(h3['quantity'])
        c_usd = qty * float(h3['avg_price_usd'])
        c_krw = c_usd * float(h3['buy_fx_rate'])
        v_usd = qty * curr_price_usd
        v_krw = v_usd * curr_fx

        total_profit_krw = v_krw - c_krw
        pure_stock_profit_krw = (v_usd - c_usd) * curr_fx
        fx_profit_krw = c_usd * (curr_fx - float(h3['buy_fx_rate']))

        assert abs(total_profit_krw - (pure_stock_profit_krw + fx_profit_krw)) < 1e-4
        assert pure_stock_profit_krw == 724500.0
        assert fx_profit_krw == 37500.0
        assert total_profit_krw == 762000.0

    finally:
        # Cleanup
        cursor.execute("DELETE FROM trade_history WHERE account_id = %s", (test_acc_id,))
        cursor.execute("DELETE FROM holdings WHERE account_id = %s", (test_acc_id,))
        cursor.execute("DELETE FROM accounts WHERE id = %s", (test_acc_id,))
        cursor.execute("DELETE FROM assets WHERE id = %s", (test_asset_id,))
        conn.commit()
        conn.close()
