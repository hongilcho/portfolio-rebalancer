import os
import sys
import unittest
from dotenv import load_dotenv

load_dotenv()

# We must ensure the path is set up correctly
sys.path.insert(0, os.path.abspath(os.path.dirname(os.path.dirname(__file__))))

from data import data_manager

class TestTrade(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # We will use a single connection for the test
        cls.test_conn = data_manager.get_connection()
        
        # Override get_connection to always return our test connection
        cls.original_get_connection = data_manager.get_connection
        data_manager.get_connection = lambda: cls.test_conn
        
        # Override the wrapper's commit method to do nothing
        cls.original_commit = data_manager.PoolConnectionWrapper.commit
        data_manager.PoolConnectionWrapper.commit = lambda self: None
        
        # Override the wrapper's close method to do nothing (prevent putting it back multiple times)
        cls.original_close = data_manager.PoolConnectionWrapper.close
        data_manager.PoolConnectionWrapper.close = lambda self: None

    @classmethod
    def tearDownClass(cls):
        # Rollback all changes made during the tests
        cls.test_conn.rollback()
        # Restore commit
        data_manager.PoolConnectionWrapper.commit = cls.original_commit
        # Restore close
        data_manager.PoolConnectionWrapper.close = cls.original_close
        # Restore get_connection
        data_manager.get_connection = cls.original_get_connection
        # Return connection to pool
        cls.original_close(cls.test_conn)

    def test_add_buy(self):
        # 1. Get initial holdings for a test account and asset (e.g., account 1, asset 1)
        initial_holdings = data_manager.get_all_holdings()
        initial_qty = 0
        for h in initial_holdings:
            if int(h["account_id"]) == 1 and int(h["asset_id"]) == 1:
                initial_qty = float(h["quantity"])
                break
                
        # 1.5 Get initial account balance
        initial_accounts = data_manager.get_all_accounts()
        initial_dep_krw = 0.0
        initial_dep_usd = 0.0
        for a in initial_accounts:
            if int(a["id"]) == 1:
                initial_dep_krw = float(a["deposit_krw"])
                initial_dep_usd = float(a["deposit_usd"])
                break
                
        # 1.8 Get asset market type
        assets = data_manager.get_all_assets()
        market = "KR"
        for a in assets:
            if int(a["id"]) == 1:
                market = a["market"]
                break
                
        # 2. Execute a buy trade
        trade_qty = 10.0
        trade_price = 50000.0
        success, msg = data_manager.execute_trade("2026-08-09", 1, 1, "BUY", trade_qty, trade_price)
        self.assertTrue(success, f"Buy trade failed: {msg}")
        
        # 3. Check if holdings increased in the SAME transaction (since we are reusing the uncommitted test_conn)
        new_holdings = data_manager.get_all_holdings()
        new_qty = 0
        for h in new_holdings:
            if int(h["account_id"]) == 1 and int(h["asset_id"]) == 1:
                new_qty = float(h["quantity"])
                break
                
        self.assertEqual(new_qty, initial_qty + trade_qty, f"Quantity should increase by {trade_qty}")
        
        # 3.5 Check account balance
        new_accounts = data_manager.get_all_accounts()
        new_dep_krw = 0.0
        new_dep_usd = 0.0
        for a in new_accounts:
            if int(a["id"]) == 1:
                new_dep_krw = float(a["deposit_krw"])
                new_dep_usd = float(a["deposit_usd"])
                break
                
        trade_amount = trade_qty * trade_price
        if market == "US":
            self.assertEqual(new_dep_usd, initial_dep_usd - trade_amount, "USD deposit should decrease")
            self.assertEqual(new_dep_krw, initial_dep_krw, "KRW deposit should remain same")
        else:
            self.assertEqual(new_dep_krw, initial_dep_krw - trade_amount, "KRW deposit should decrease")
            self.assertEqual(new_dep_usd, initial_dep_usd, "USD deposit should remain same")
        
        # 4. Check if trade history was recorded
        history = data_manager.get_trade_history()
        # The history is ordered by date descending, so the newest should be at the top or at least exist
        found = False
        for t in history:
            if t["trade_type"] == "BUY" and t["quantity"] == 10.0 and t["price"] == 50000.0:
                found = True
                break
        self.assertTrue(found, "The BUY trade should be found in history")

    def test_add_sell(self):
        # We need an asset with enough quantity to sell
        # Let's forcibly give account 2, asset 2 some quantity for the sake of the test
        cursor = self.test_conn.cursor()
        cursor.execute("UPDATE holdings SET quantity = quantity + 20 WHERE account_id = '2' AND asset_id = '2'")
        # Do not commit! The override prevents it anyway.
        
        initial_holdings = data_manager.get_all_holdings()
        initial_qty = 0
        for h in initial_holdings:
            if int(h["account_id"]) == 2 and int(h["asset_id"]) == 2:
                initial_qty = float(h["quantity"])
                break
                
        # Get initial account balance
        initial_accounts = data_manager.get_all_accounts()
        initial_dep_krw = 0.0
        initial_dep_usd = 0.0
        for a in initial_accounts:
            if int(a["id"]) == 2:
                initial_dep_krw = float(a["deposit_krw"])
                initial_dep_usd = float(a["deposit_usd"])
                break
                
        # Get asset market type
        assets = data_manager.get_all_assets()
        market = "KR"
        for a in assets:
            if int(a["id"]) == 2:
                market = a["market"]
                break
                
        # Execute sell
        trade_qty = 5.0
        trade_price = 60000.0
        success, msg = data_manager.execute_trade("2026-08-09", 2, 2, "SELL", trade_qty, trade_price)
        self.assertTrue(success, f"Sell trade failed: {msg}")
        
        new_holdings = data_manager.get_all_holdings()
        new_qty = 0
        for h in new_holdings:
            if int(h["account_id"]) == 2 and int(h["asset_id"]) == 2:
                new_qty = float(h["quantity"])
                break
                
        self.assertEqual(new_qty, initial_qty - trade_qty, f"Quantity should decrease by {trade_qty}")
        
        # Check account balance
        new_accounts = data_manager.get_all_accounts()
        new_dep_krw = 0.0
        new_dep_usd = 0.0
        for a in new_accounts:
            if int(a["id"]) == 2:
                new_dep_krw = float(a["deposit_krw"])
                new_dep_usd = float(a["deposit_usd"])
                break
                
        trade_amount = trade_qty * trade_price
        if market == "US":
            self.assertEqual(new_dep_usd, initial_dep_usd + trade_amount, "USD deposit should increase")
            self.assertAlmostEqual(new_dep_usd, initial_dep_usd + trade_amount, places=2, msg="USD deposit should increase")
            self.assertAlmostEqual(new_dep_krw, initial_dep_krw, places=2, msg="KRW deposit should remain same")
        else:
            self.assertAlmostEqual(new_dep_krw, initial_dep_krw + trade_amount, places=2, msg="KRW deposit should increase")
            self.assertAlmostEqual(new_dep_usd, initial_dep_usd, places=2, msg="USD deposit should remain same")
        
        # Check history
        history = data_manager.get_trade_history()
        found = False
        for t in history:
            if t["trade_type"] == "SELL" and t["quantity"] == 5.0 and t["price"] == 60000.0:
                found = True
                break
        self.assertTrue(found, "The SELL trade should be found in history")

if __name__ == '__main__':
    unittest.main()
