import unittest
from datetime import datetime, timedelta, timezone
from qingmai.guardrails import validate_quote, decision_gate

class GuardrailTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,10,10,16,0,tzinfo=timezone.utc)
        self.quote={"source":"binance","price":"1.23","as_of":self.now.isoformat()}
    def test_valid_quote(self):
        self.assertEqual(validate_quote(self.quote,self.now),1.23)
    def test_missing_timestamp(self):
        with self.assertRaises(ValueError): validate_quote({"source":"binance","price":1.2},self.now)
    def test_stale_quote(self):
        self.quote["as_of"]=(self.now-timedelta(minutes=11)).isoformat()
        with self.assertRaises(ValueError): validate_quote(self.quote,self.now)
    def test_no_ledger(self):
        self.assertFalse(decision_gate(self.quote,False,self.now)["allow_paper_execution"])
    def test_no_negative_price(self):
        self.quote["price"]="-1"
        with self.assertRaises(ValueError): validate_quote(self.quote,self.now)

if __name__=="__main__": unittest.main()
