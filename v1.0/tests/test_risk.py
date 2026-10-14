import unittest
from qingmai.risk import size_position, verify_ledger, realized_nav

class RiskTests(unittest.TestCase):
    def test_size_respects_cap(self):
        p=size_position(1000,100,95)
        self.assertLessEqual(p["notional"],300)
        self.assertLessEqual(p["stop_loss_budget_ex_fees"],10)
    def test_reject_high_leverage(self):
        with self.assertRaises(ValueError):size_position(1000,100,95,leverage=2)
    def test_reject_nonfinite(self):
        with self.assertRaises(ValueError):size_position(1000,float("nan"),90)
    def test_duplicate_trade(self):
        x={"mode":"paper_only","initial_equity":1000,"account_id":"A","trades":[{"trade_id":"1"},{"trade_id":"1"}]}
        with self.assertRaises(ValueError):verify_ledger(x)
    def test_nav_costs(self):
        x={"mode":"paper_only","initial_equity":1000,"account_id":"A","trades":[],"realized_pnl":20,"fees_paid":2,"funding_paid":1}
        self.assertEqual(realized_nav(x),1017)

if __name__=="__main__":unittest.main()
