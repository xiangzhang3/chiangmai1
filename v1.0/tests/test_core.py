import unittest
from qingmai.core import pct, oi_change, volume_acceleration, classify, PaperAccount

class RadarTests(unittest.TestCase):
    def test_pct(self): self.assertAlmostEqual(pct(110,100),10)
    def test_oi_quantity(self): self.assertAlmostEqual(oi_change({"sumOpenInterest":"120"},{"sumOpenInterest":"100"}),20)
    def test_volume_acceleration(self): self.assertAlmostEqual(volume_acceleration(100,200),6)
    def test_pre_move(self): self.assertEqual(classify(1,8,6,1.2),"PRE_MOVE")
    def test_ignition(self): self.assertEqual(classify(4,8,6,1.2),"IGNITION")
    def test_missing_data(self): self.assertEqual(classify(1,None,6,1.2),"UNVERIFIED")
    def test_paper_profit(self):
        a=PaperAccount("A");a.open("STRKUSDT","long",100,1);a.close(1.1)
        self.assertEqual(a.stats()["closed_trades"],1)
        self.assertGreater(a.stats()["net_pnl"],0)
    def test_reject_duplicate(self):
        a=PaperAccount("A");a.open("STRKUSDT","long",100,1)
        with self.assertRaises(ValueError): a.open("BTCUSDT","short",1,1)

if __name__ == "__main__": unittest.main()
