import pytest
from unittest.mock import patch, MagicMock
from data.data_manager import execute_trade

@patch('data.data_manager.get_connection')
def test_execute_trade_deposit_update(mock_get_connection):
    # Mocking DB connection and cursor
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_connection.return_value = mock_conn

    # 1. Test BUY (should deduct from deposit_krw)
    mock_cursor.fetchone.side_effect = [
        {'deposit_krw': 19000.0}, # account balance
        None # holdings lookup
    ]

    success, msg = execute_trade('2026-01-01', 'acc_1', 'ast_1', 'BUY', 3, 5000.0)
    assert success is True
    
    # Check if accounts update was called with correct new deposit: 19000 - (3 * 5000) = 4000
    update_acc_call = [call for call in mock_cursor.execute.call_args_list if 'UPDATE accounts' in call[0][0]]
    assert len(update_acc_call) == 1
    assert update_acc_call[0][0][1] == (4000.0, 'acc_1')

    # 2. Test SELL (should add to deposit_krw)
    mock_cursor.reset_mock()
    mock_cursor.fetchone.side_effect = [
        {'deposit_krw': 10000.0}, # account balance
        {'quantity': 10, 'avg_price': 25000.0} # holdings lookup (selling 5 at 26000)
    ]

    success, msg = execute_trade('2026-01-01', 'acc_1', 'ast_2', 'SELL', 5, 26000.0)
    assert success is True
    
    # Check if accounts update was called with correct new deposit: 10000 + (5 * 26000) = 140000
    update_acc_call = [call for call in mock_cursor.execute.call_args_list if 'UPDATE accounts' in call[0][0]]
    assert len(update_acc_call) == 1
    assert update_acc_call[0][0][1] == (140000.0, 'acc_1')
