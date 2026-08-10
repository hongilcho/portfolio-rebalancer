import pytest
from unittest.mock import patch, MagicMock
from data.data_manager import apply_transfer_plan

@patch('data.data_manager.get_connection')
def test_apply_transfer_plan(mock_get_connection):
    # Mocking DB connection and cursor
    mock_conn = MagicMock()
    mock_cursor = MagicMock()
    mock_conn.cursor.return_value = mock_cursor
    mock_get_connection.return_value = mock_conn

    # Dummy transfer plan
    tr_plan = [
        {
            "account_id": "acc_1",
            "type": "DEPOSIT",
            "amount": 500000.0,
            "msg": "Test deposit"
        },
        {
            "account_id": "acc_2",
            "type": "WITHDRAW",
            "amount": 200000.0,
            "msg": "Test withdraw"
        }
    ]

    # Mock fetchone for the two accounts
    # acc_1 current deposit: 1000000.0
    # acc_2 current deposit: 500000.0
    mock_cursor.fetchone.side_effect = [
        [1000000.0],
        [500000.0]
    ]

    # Run the function
    success, msg = apply_transfer_plan(tr_plan)
    
    # Verify success
    assert success is True
    assert msg == "이체 지시서가 실제 계좌 예수금에 모두 반영되었습니다."

    # Verify UPDATE statements
    update_calls = [call for call in mock_cursor.execute.call_args_list if 'UPDATE accounts' in call[0][0]]
    assert len(update_calls) == 2
    
    # 1. acc_1 DEPOSIT 500k -> 1.5M
    assert update_calls[0][0][1] == (1500000.0, 'acc_1')
    
    # 2. acc_2 WITHDRAW 200k -> 300k
    assert update_calls[1][0][1] == (300000.0, 'acc_2')
    
    # Verify commit
    mock_conn.commit.assert_called_once()
