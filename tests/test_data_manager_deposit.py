import pytest
from unittest.mock import patch, MagicMock
from data_manager import execute_trade

@patch('data_manager.get_connection')
def test_execute_trade_deposit_update(mock_get_connection):
    # Mocking DB connection and cursor
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_connection.return_value = mock_conn

    # 1. Test BUYing KR asset (should deduct from deposit_krw)
    # Mock sequence for BUY:
    # execute_trade does:
    # - INSERT trade_history
    # - SELECT market FROM assets -> return KR
    # - SELECT deposit FROM accounts -> return 19000 krw, 0 usd
    # - UPDATE accounts
    # - SELECT holdings -> return None (no holdings yet)
    # - INSERT holdings
    mock_cursor.fetchone.side_effect = [
        {'market': 'KR'}, # asset market
        {'deposit_krw': 19000.0, 'deposit_usd': 0.0}, # account balance
        None # holdings lookup
    ]

    success, msg = execute_trade('2026-01-01', 'acc_1', 'ast_1', 'BUY', 3, 5000.0)
    
    assert success is True
    
    # Check if accounts update was called with correct new deposit
    # 19000 - (3 * 5000) = 4000
    update_acc_call = [call for call in mock_cursor.execute.call_args_list if 'UPDATE accounts' in call[0][0]]
    assert len(update_acc_call) == 1
    assert update_acc_call[0][0][1] == (4000.0, 0.0, 'acc_1')


    # 2. Test SELLing US asset (should add to deposit_usd)
    mock_cursor.reset_mock()
    mock_cursor.fetchone.side_effect = [
        {'market': 'US'}, # asset market
        {'deposit_krw': 1000.0, 'deposit_usd': 50.0}, # account balance
        {'quantity': 10, 'avg_price': 10.0} # holdings lookup (selling 5)
    ]

    success, msg = execute_trade('2026-01-01', 'acc_1', 'ast_2', 'SELL', 5, 12.0)
    
    assert success is True
    
    # Check if accounts update was called with correct new deposit
    # 50 + (5 * 12) = 110
    update_acc_call = [call for call in mock_cursor.execute.call_args_list if 'UPDATE accounts' in call[0][0]]
    assert len(update_acc_call) == 1
    assert update_acc_call[0][0][1] == (1000.0, 110.0, 'acc_1')
