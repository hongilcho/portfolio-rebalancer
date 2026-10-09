"""Trade execution, reversal and transfers; no nested connection leases."""
import math
import json
import re
from datetime import date, datetime
from typing import Tuple
from psycopg2.extras import RealDictCursor
from logic.trade_accounting import cash_movement, replay_holding
from data.repository_context import RepositoryContext
from data.repositories import forex, bookkeeping

def execute_trade(
    db: RepositoryContext,
    trade_date,
    account_id,
    asset_id,
    trade_type,
    quantity,
    price,
    currency=None,
    exchange_rate=None,
    import_source=None,
    broker_order_no=None,
    transaction=None,
):
    if not all(math.isfinite(v) and v > 0 for v in (quantity, price)):
        return False, "수량과 단가는 0보다 커야 합니다."
        
    if trade_type not in ('INIT', 'BUY', 'SELL') or currency not in (None, 'KRW', 'USD'):
        return False, "거래 유형 또는 통화를 확인해주세요."
    conn = transaction if transaction is not None else db.connect()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    new_trade_id = db.new_id()
    try:
        day = date.fromisoformat(str(trade_date))
        if day.isoformat() != str(trade_date) or day > datetime.now(forex.KST).date():
            raise ValueError('실제 체결일은 오늘까지의 올바른 날짜여야 합니다.')
        cursor.execute("""SELECT a.market,a.is_deposit,a.allowed_accounts,a.portfolio_id,
            c.portfolio_id AS account_portfolio FROM assets a
            JOIN accounts c ON c.id=%s WHERE a.id=%s""", (str(account_id),str(asset_id)))
        asset = cursor.fetchone()
        if not asset or asset['portfolio_id'] != asset['account_portfolio'] or asset['is_deposit']:
            raise ValueError('계좌와 같은 포트폴리오의 주식·ETF·금 종목을 선택해주세요.')
        allowed = asset['allowed_accounts'] or []
        if isinstance(allowed, str): allowed = json.loads(allowed)
        if str(account_id) not in map(str, allowed):
            raise ValueError('이 계좌에 허용된 종목이 아닙니다.')
        is_us = asset['market'] == 'US'
        currency = currency or ('USD' if is_us else 'KRW')
        if currency != ('USD' if is_us else 'KRW'):
            raise ValueError('미국 종목은 달러 단가, 국내 종목은 원화 단가로 입력해주세요.')

        # Lock before reading balances; deletion takes the same account lock.
        cursor.execute('SELECT deposit_krw, deposit_usd FROM accounts WHERE id = %s FOR UPDATE', (str(account_id),))
        acc_row = cursor.fetchone()
        if not acc_row:
            raise ValueError("존재하지 않는 계좌입니다.")
        cursor.execute('''SELECT t.trade_date FROM ledger_adjustments l JOIN trade_history t ON t.id=l.trade_id
            WHERE l.account_id=%s AND t.asset_id=%s AND l.reversed_at IS NULL''',(str(account_id),str(asset_id)))
        if any(str(trade_date)<str(r['trade_date']) for r in cursor.fetchall()):
            raise ValueError('보유 원가 정정 이전 날짜의 매매는 새로 입력할 수 없습니다. 정정 기준과 실제 거래 순서를 확인해주세요.')
        if import_source is not None or broker_order_no is not None:
            if import_source != 'NAMUH_KAKAO' or not re.fullmatch(r'[0-9]{1,10}', broker_order_no or ''):
                raise ValueError('가져오기 출처 또는 주문번호를 확인해주세요.')
            if trade_type != 'BUY' or currency != 'KRW' or quantity != int(quantity):
                raise ValueError('체결 메시지 가져오기는 국내 원화 매수만 지원합니다.')
            if date.fromisoformat(trade_date).isoformat() != trade_date:
                raise ValueError('체결일을 확인해주세요.')
            cursor.execute('''SELECT a.market, a.is_deposit, a.ticker, a.allowed_accounts,
                a.portfolio_id, c.portfolio_id AS account_portfolio FROM assets a
                JOIN accounts c ON c.id=%s WHERE a.id=%s''', (str(account_id), str(asset_id)))
            imported_asset = cursor.fetchone()
            if not imported_asset or imported_asset['market'] != 'KR' or imported_asset['is_deposit'] or imported_asset['portfolio_id'] != imported_asset['account_portfolio']:
                raise ValueError('계좌와 같은 포트폴리오의 국내 종목을 선택해주세요.')
            allowed = imported_asset['allowed_accounts'] or []
            if isinstance(allowed, str):
                allowed = json.loads(allowed)
            if str(account_id) not in map(str, allowed):
                raise ValueError('이 계좌에 허용된 종목이 아닙니다.')
            cursor.execute('''SELECT id FROM trade_history WHERE account_id=%s AND trade_date=%s
                AND import_source=%s AND broker_order_no=%s''', (str(account_id), trade_date, import_source, broker_order_no))
            if cursor.fetchone():
                raise ValueError('이미 장부에 저장된 주문입니다. 기존 기록을 확인해주세요.')
        dep_krw = float(acc_row.get('deposit_krw') or 0.0)
        dep_usd = float(acc_row.get('deposit_usd') or 0.0)
        state = forex.load_state(cursor, account_id)
        if state:
            cursor.execute('SELECT market FROM assets WHERE id = %s', (str(asset_id),))
            asset = cursor.fetchone()
            if asset and asset['market'] == 'US':
                if currency != 'USD':
                    raise ValueError('달러 원가 추적 계좌의 미국 자산은 달러 단가로 입력해주세요.')
                if trade_type == 'SELL' and (exchange_rate is None or not math.isfinite(float(exchange_rate)) or float(exchange_rate) <= 0):
                    raise ValueError('매도대금 수취기준환율을 입력해주세요.')
                forex.execute_managed_trade(db, cursor, account_id, asset_id, new_trade_id,
                                            state, acc_row, trade_date, trade_type, quantity, price, exchange_rate)
                if transaction is None: conn.commit()
                return True, '계좌 달러 평균환율로 매매 기록과 원가를 저장했습니다.'
            if currency == 'USD':
                raise ValueError('달러 원가 추적 계좌에서는 미국 자산에만 달러 거래를 등록할 수 있습니다.')
        if currency == 'USD':
            if exchange_rate is None:
                raise ValueError('미국 종목은 확인한 매입환율을 입력하거나 달러 원가 추적을 먼저 시작해주세요.')
            exchange_rate = float(exchange_rate)
        else:
            exchange_rate = 1.0
        if not math.isfinite(exchange_rate) or exchange_rate <= 0:
            raise ValueError("매입환율은 양수여야 합니다.")
        if not math.isfinite(quantity * price * exchange_rate) or quantity * price * exchange_rate > 1e18:
            raise ValueError("거래 금액이 허용 범위를 초과합니다.")
        cursor.execute('SELECT * FROM trade_history WHERE account_id=%s AND asset_id=%s',
                       (str(account_id),str(asset_id)))
        prior_trades = cursor.fetchall()
        backdated = any(str(t['trade_date']) > str(trade_date) for t in prior_trades)
        if backdated:
            if any(t['trade_type'] != 'INIT' and (t.get('cash_delta_krw') is None or t.get('cash_delta_usd') is None) for t in prior_trades):
                raise ValueError('과거 기록의 결제 정보가 부족합니다. 5번 탭 장부 정정으로 현재 보유 기준을 먼저 확인해주세요.')
            cursor.execute('SELECT * FROM holdings WHERE account_id=%s AND asset_id=%s',
                           (str(account_id),str(asset_id)))
            old_holding = cursor.fetchone() or {}
            rebuilt = replay_holding(prior_trades)
            current = (float(old_holding.get('quantity') or 0),
                       float(old_holding.get('original_avg_price') or old_holding.get('avg_price') or 0),
                       float(old_holding.get('original_avg_price_usd') or old_holding.get('avg_price_usd') or 0),
                       float(old_holding.get('buy_fx_rate') or 0))
            fields=1 if abs(current[0])<1e-9 else 4
            if any(not math.isclose(a,b,abs_tol=1e-5,rel_tol=1e-6) for a,b in zip(rebuilt[:fields],current[:fields])):
                raise ValueError('매매 이력과 현재 보유 원가가 다릅니다. 5번 탭 장부 정정으로 기준을 확인해주세요.')
        delta_krw, delta_usd = cash_movement(
            trade_type, quantity, price, currency, exchange_rate, dep_krw, dep_usd
        )
        cursor.execute("""
            INSERT INTO trade_history (id, trade_date, account_id, asset_id, trade_type, quantity, price, currency, exchange_rate, cash_delta_krw, cash_delta_usd)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (new_trade_id, trade_date, str(account_id), str(asset_id), trade_type, quantity, price, currency, exchange_rate, delta_krw, delta_usd))
        if import_source:
            cursor.execute('UPDATE trade_history SET import_source=%s, broker_order_no=%s WHERE id=%s',
                           (import_source, broker_order_no, new_trade_id))
        if trade_type in ('BUY', 'SELL'):
            cursor.execute("""
                UPDATE accounts SET deposit_krw = %s, deposit_usd = %s WHERE id = %s
            """, (dep_krw + delta_krw, dep_usd + delta_usd, str(account_id)))

        if backdated:
            cursor.execute('SELECT * FROM trade_history WHERE account_id=%s AND asset_id=%s',
                           (str(account_id),str(asset_id)))
            qty,avg_krw,avg_usd,fx = replay_holding(cursor.fetchall())
            cursor.execute("""INSERT INTO holdings
                (id,account_id,asset_id,quantity,avg_price,avg_price_usd,buy_fx_rate,original_avg_price,original_avg_price_usd)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)
                ON CONFLICT(account_id,asset_id) DO UPDATE SET quantity=EXCLUDED.quantity,
                    avg_price=EXCLUDED.avg_price,avg_price_usd=EXCLUDED.avg_price_usd,
                    buy_fx_rate=EXCLUDED.buy_fx_rate,original_avg_price=EXCLUDED.original_avg_price,
                    original_avg_price_usd=EXCLUDED.original_avg_price_usd""",
                (db.new_id(),str(account_id),str(asset_id),qty,avg_krw,avg_usd,fx,avg_krw,avg_usd))
            if transaction is None: conn.commit()
            return True, '거래일 순서로 보유 수량·원가를 재계산하고 매매를 저장했습니다.'

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
                if quantity > curr_qty + 1e-9:
                    raise ValueError("매도할 보유 수량이 부족합니다.")
                new_qty = curr_qty - quantity
                new_avg_price = curr_avg_price
                new_avg_usd = curr_avg_usd
                new_buy_fx = curr_buy_fx
                if new_qty <= 0:
                    new_qty = 0.0
                    new_avg_price = 0.0
                    new_avg_usd = 0.0
                    new_buy_fx = 0.0
                    
            if trade_type in ('BUY', 'INIT'):
                cursor.execute('''
                    UPDATE holdings
                    SET quantity = %s, avg_price = %s, avg_price_usd = %s, buy_fx_rate = %s,
                        original_avg_price = %s, original_avg_price_usd = %s
                    WHERE account_id = %s AND asset_id = %s
                ''', (new_qty, new_avg_price, new_avg_usd, new_buy_fx, new_avg_price, new_avg_usd, str(account_id), str(asset_id)))
            else:
                cursor.execute('''
                    UPDATE holdings
                    SET quantity = %s, avg_price = %s, avg_price_usd = %s, buy_fx_rate = %s
                    WHERE account_id = %s AND asset_id = %s
                ''', (new_qty, new_avg_price, new_avg_usd, new_buy_fx, str(account_id), str(asset_id)))
            
        else:
            if trade_type in ('BUY', 'INIT'):
                new_h_id = db.new_id()
                if is_us or currency == 'USD':
                    new_avg_usd = price
                    new_buy_fx = exchange_rate
                    new_avg_price = round(price * exchange_rate, 2)
                else:
                    new_avg_price = price
                    new_avg_usd = 0.0
                    new_buy_fx = 0.0
                cursor.execute('''
                    INSERT INTO holdings (id, account_id, asset_id, quantity, avg_price, avg_price_usd, buy_fx_rate, original_avg_price, original_avg_price_usd)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ''', (new_h_id, str(account_id), str(asset_id), quantity, new_avg_price, new_avg_usd, new_buy_fx, new_avg_price, new_avg_usd))
            else:
                if transaction is None: conn.rollback()
                return False, "매도할 보유 잔고가 없습니다."
                
        if transaction is None: conn.commit()
        return True, "매매 기록 및 잔고 업데이트가 완료되었습니다."
    except Exception as e:
        if transaction is None: conn.rollback()
        return False, str(e)
    finally:
        if transaction is None: conn.close()


def get_trade_history(db: RepositoryContext, portfolio_id: str = None):
    conn = db.connect()
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


def delete_trades(db: RepositoryContext, trade_ids, transaction=None):
    """Reverse recorded cash movements and replay holdings in one transaction.

    Legacy BUY/SELL rows without cash deltas require reconciliation first.
    Account locks are taken in stable order before locking transaction rows.
    """
    ids = [str(tid) for tid in trade_ids]
    if not ids:
        return False, "삭제할 거래를 선택해주세요."
    if len(ids) != len(set(ids)):
        return False, "중복된 거래 ID가 있습니다."
    placeholders = ', '.join(['%s'] * len(ids))
    conn = transaction if transaction is not None else db.connect()
    cursor = conn.cursor(cursor_factory=RealDictCursor)
    try:
        cursor.execute(f"SELECT id, account_id FROM trade_history WHERE id IN ({placeholders})", tuple(ids))
        references = cursor.fetchall()
        if len(references) != len(ids):
            raise ValueError("존재하지 않는 매매 기록이 있습니다.")
        account_ids = sorted({r['account_id'] for r in references})
        acc_placeholders = ', '.join(['%s'] * len(account_ids))
        cursor.execute(f"SELECT id FROM accounts WHERE id IN ({acc_placeholders}) ORDER BY id FOR UPDATE", tuple(account_ids))
        if len(cursor.fetchall()) != len(account_ids):
            raise ValueError("존재하지 않는 계좌입니다.")
        cursor.execute(f"SELECT * FROM trade_history WHERE id IN ({placeholders}) FOR UPDATE", tuple(ids))
        selected = cursor.fetchall()
        if len(selected) != len(ids):
            raise ValueError("이미 삭제된 매매 기록이 있습니다.")
        for trade in selected:
            cursor.execute('SELECT trade_id,after_state FROM ledger_adjustments WHERE account_id=%s AND reversed_at IS NULL',(trade['account_id'],))
            for correction in cursor.fetchall():
                checkpoint=correction['after_state']
                if isinstance(checkpoint,str):checkpoint=json.loads(checkpoint)
                if correction['trade_id']==trade['id'] or trade['trade_sequence']<=checkpoint['trade_sequence']:
                    raise ValueError('장부 정정 이전의 매매 또는 정정 기준 기록은 삭제할 수 없습니다. 정정부터 취소하거나 새 정정으로 처리해주세요.')
        if transaction is None:
            cursor.execute(f'SELECT id FROM nh_notice_items WHERE linked_trade_id IN ({placeholders}) AND reversed_at IS NULL', tuple(ids))
            if cursor.fetchone():
                raise ValueError('NH 알림으로 반영한 매수는 알림 가져오기의 반영 이력에서 묶음 취소해주세요.')
        cursor.execute(f'SELECT * FROM usd_cash_events WHERE trade_id IN ({placeholders}) AND reversed_at IS NULL ORDER BY sequence DESC', tuple(ids))
        managed = cursor.fetchall()
        managed_ids = {event['trade_id'] for event in managed}
        for trade in selected:
            if trade['id'] not in managed_ids and forex.enabled(cursor, trade['account_id']):
                cursor.execute('SELECT market FROM assets WHERE id = %s', (trade['asset_id'],))
                asset = cursor.fetchone()
                if asset and asset['market'] == 'US':
                    raise ValueError('달러 추적 시작 이전의 미국 자산 기록은 현재 원가의 기준입니다. 삭제할 수 없습니다.')
        for event in managed:
            forex.reverse_latest(cursor, event['account_id'], event['id'])
        selected = [trade for trade in selected if trade['id'] not in managed_ids]
        if not selected:
            if transaction is None: conn.commit()
            return True, '매매를 취소하고 달러·보유 원가를 복원했습니다.'
        ids = [trade['id'] for trade in selected]
        placeholders = ', '.join(['%s'] * len(ids))
        for trade in selected:
            if trade['trade_type'] != 'INIT' and (
                trade.get('cash_delta_krw') is None or trade.get('cash_delta_usd') is None
            ):
                raise ValueError("기존 거래의 결제 통화·예수금 변동 기록이 없습니다. 잔고 대사 후 삭제해주세요.")
        if transaction is None:
            for aid,asset_id in sorted({(t['account_id'],t['asset_id']) for t in selected}):
                cursor.execute('SELECT * FROM trade_history WHERE account_id=%s AND asset_id=%s',(aid,asset_id))
                rebuilt=replay_holding(cursor.fetchall())
                cursor.execute('SELECT * FROM holdings WHERE account_id=%s AND asset_id=%s',(aid,asset_id))
                h=cursor.fetchone() or {}
                current=(float(h.get('quantity') or 0),float(h.get('original_avg_price') or h.get('avg_price') or 0),
                         float(h.get('original_avg_price_usd') or h.get('avg_price_usd') or 0),float(h.get('buy_fx_rate') or 0))
                fields=1 if abs(current[0])<1e-9 else 4
                if any(not math.isclose(a,b,abs_tol=1e-5,rel_tol=1e-6) for a,b in zip(rebuilt[:fields],current[:fields])):
                    raise ValueError('거래 이력만으로 현재 보유 원가를 복원할 수 없습니다. 5번 탭 장부 정정으로 확인해주세요.')
        cursor.execute(f"DELETE FROM trade_history WHERE id IN ({placeholders})", tuple(ids))
        for trade in selected:
            if trade['trade_type'] != 'INIT':
                cursor.execute("""
                    UPDATE accounts
                    SET deposit_krw = deposit_krw - %s, deposit_usd = deposit_usd - %s
                    WHERE id = %s
                """, (trade['cash_delta_krw'], trade['cash_delta_usd'], trade['account_id']))
        cursor.execute(f"SELECT deposit_krw, deposit_usd FROM accounts WHERE id IN ({acc_placeholders})", tuple(account_ids))
        if any(float(a.get('deposit_krw') or 0) < -1e-9 or float(a.get('deposit_usd') or 0) < -1e-9
               for a in cursor.fetchall()):
            raise ValueError("삭제 후 예수금이 부족합니다. 관련 거래 또는 현재 잔고를 확인해주세요.")
        pairs = sorted({(t['account_id'], t['asset_id']) for t in selected})
        for account_id, asset_id in pairs:
            cursor.execute("""
                SELECT t.*, a.market FROM trade_history t
                JOIN assets a ON t.asset_id = a.id
                WHERE t.account_id = %s AND t.asset_id = %s
            """, (account_id, asset_id))
            qty, avg_krw, avg_usd, buy_fx = replay_holding(cursor.fetchall())
            if qty > 0:
                cursor.execute("""
                    INSERT INTO holdings (id, account_id, asset_id, quantity, avg_price, avg_price_usd, buy_fx_rate, original_avg_price, original_avg_price_usd)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                    ON CONFLICT(account_id, asset_id) DO UPDATE SET
                        quantity = EXCLUDED.quantity,
                        avg_price = EXCLUDED.avg_price,
                        avg_price_usd = EXCLUDED.avg_price_usd,
                        buy_fx_rate = EXCLUDED.buy_fx_rate,
                        original_avg_price = EXCLUDED.avg_price,
                        original_avg_price_usd = EXCLUDED.avg_price_usd
                """, (db.new_id(), account_id, asset_id, qty, avg_krw, avg_usd, buy_fx, avg_krw, avg_usd))
            else:
                # Keep optional first-buy-date and dividend overrides for a future
                # undo/re-entry, and let quantity filters hide the closed position.
                cursor.execute("""
                    UPDATE holdings SET quantity = 0, avg_price = 0, avg_price_usd = 0,
                        buy_fx_rate = 0, original_avg_price = 0, original_avg_price_usd = 0
                    WHERE account_id = %s AND asset_id = %s
                """, (account_id, asset_id))
        if transaction is None: conn.commit()
        return True, "매매 기록이 삭제되었으며 예수금·수량·매입원가가 복원되었습니다."
    except Exception as e:
        if transaction is None: conn.rollback()
        return False, str(e)
    finally:
        if transaction is None: conn.close()


def apply_transfer_plan(db: RepositoryContext, transfer_plan: list) -> Tuple[bool, str]:
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
        
    conn = db.connect()
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


def execute_batch(db, payload):
    """Manual rows commit together. A lost response can retry the exact receipt."""
    conn = db.connect()
    try:
        c = conn.cursor(cursor_factory=RealDictCursor)
        scope = 'trades:' + payload['portfolio_id']
        existing = bookkeeping.begin(c,scope,payload['request_id'],payload)
        if existing is not None:
            ids=existing.get('trade_ids',[])
            if ids:
                marks=','.join(['%s']*len(ids))
                c.execute(f'SELECT id FROM trade_history WHERE id IN ({marks})',tuple(ids))
                if len(c.fetchall())!=len(ids):
                    existing={**existing,'message':'이미 저장한 요청입니다. 일부 또는 전체 매매는 이후 취소되어 추가 반영하지 않았습니다.'}
            conn.rollback()
            return existing
        from data.repositories.nh_notices import lock_scope
        ids = sorted({row['account_id'] for row in payload['trades']})
        lock_scope(c,payload['portfolio_id'],ids)
        results = []
        trade_ids = []
        for index,row in enumerate(payload['trades']):
            ok,message = execute_trade(db,trade_date=payload['trade_date'],transaction=conn,**row)
            if not ok:
                raise ValueError(f'{index+1}번째 거래: {message} 이번 묶음은 모두 미반영입니다.')
            c.execute('SELECT id FROM trade_history WHERE account_id=%s ORDER BY trade_sequence DESC LIMIT 1',(row['account_id'],))
            trade_ids.append(c.fetchone()['id'])
            results.append(dict(index=index,success=True,message=message))
        result = dict(success=True,success_count=len(results),errors=[],results=results,trade_ids=trade_ids,
                      message=f'{len(results)}건의 매매를 함께 저장했습니다.')
        bookkeeping.finish(c,scope,payload['request_id'],result)
        conn.commit()
        db.invalidate()
        return result
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()
