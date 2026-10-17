"""Synthetic flat-pilot tests. No exchange connections or historical fills."""
from copy import deepcopy
from argparse import Namespace
import json
from pathlib import Path
import tempfile
import unittest
from test_ui_candidate import record,NOW,iso
from test_paper import state
from qingmai.market import HOUR
from qingmai.paper import initialize_prospective_jct,activate_timeframe_trial
from qingmai.ui_pilot import assess_pilot,process_pilot
from qingmai.__main__ import run_ui_pilot


def candidate():
    r=record();r["candles_4h"]=[]
    for label,close in (("2026/10/10 01:00","99.00"),("2026/10/10 05:00","100.00")):
        r["candles_4h"].append({"source_url":"https://www.binance.com/en/futures/KAIAUSDT","selected_symbol":"KAIAUSDT","period":"4h",
            "observed_at":iso(NOW-30_000),"capture_started_at":iso(NOW-31_000),"raw_ui_time_label":label,
            "open":"99.00","high":"101.00","low":"98.00","close":close})
    return r


def configured():
    return activate_timeframe_trial(initialize_prospective_jct(state(),NOW-60_000),NOW-50_000)


class UIPilotTests(unittest.TestCase):
    def test_invalid_input_is_not_echoed_in_audit(self):
        r=candidate();r["quotes"][0]["last_price"]="SYNTHETIC_PRIVATE_MARKER"
        output,event=process_pilot(configured(),r,NOW)
        self.assertNotIn("SYNTHETIC_PRIVATE_MARKER",json.dumps(output))
        self.assertEqual(event["accounts"]["KAIA-A01"]["action"],"ABSTAIN")

    def test_extra_fields_never_enter_ledger(self):
        for where in ("top","quote"):
            r=candidate()
            target=r if where=="top" else r["quotes"][0]
            target["unapproved_field"]="synthetic forbidden content"
            with self.assertRaises(ValueError):process_pilot(configured(),r,NOW)

    def test_invalid_source_payload_not_persisted(self):
        r=candidate();r["quotes"][0]["source_url"]="https://example.com"
        updated,event=process_pilot(configured(),r,NOW)
        self.assertFalse(event["validated_evidence_stored"])
        self.assertNotIn(event["evidence_sha256"],updated["market_evidence"])

    def test_pre_activation_live_pair_abstains(self):
        s=activate_timeframe_trial(initialize_prospective_jct(state(),NOW-1000),NOW-500)
        _,event=process_pilot(s,candidate(),NOW)
        self.assertEqual(event["accounts"]["KAIA-A01"]["action"],"ABSTAIN")

    def test_candidate_cannot_execute_without_accounting_bridge(self):
        result=assess_pilot(candidate(),NOW)
        self.assertEqual(result["action"],"ENTRY_CANDIDATE_BLOCKED")
        self.assertFalse(result["execution_eligible"])
        self.assertTrue(result["trend_4h"]["passes"])

    def test_real_no_trade_gate(self):
        r=candidate();r["oi"][1]["quantity"]="99000.000"
        self.assertEqual(assess_pilot(r,NOW)["action"],"NO_TRADE")

    def test_ambiguous_4h_green_is_not_accepted(self):
        r=candidate();r["candles_4h"][-1]["close"]="99.00"
        self.assertEqual(assess_pilot(r,NOW)["action"],"NO_TRADE")

    def test_missing_4h_abstains(self):
        r=candidate();r.pop("candles_4h")
        self.assertEqual(assess_pilot(r,NOW)["action"],"ABSTAIN")

    def test_bad_4h_source_period_and_symbol(self):
        for field,value in (("source_url","https://example.com"),("period","1h"),("selected_symbol","JCTUSDT")):
            r=candidate();r["candles_4h"][0][field]=value
            self.assertEqual(assess_pilot(r,NOW)["status"],"INCOMPLETE")

    def test_unclosed_and_duplicate_4h_rejected(self):
        for label in ("2026/10/10 09:00","2026/10/10 01:00"):
            r=candidate();r["candles_4h"][-1]["raw_ui_time_label"]=label
            self.assertEqual(assess_pilot(r,NOW)["action"],"ABSTAIN")

    def test_stale_4h_and_future_capture_rejected(self):
        for when in (NOW-700_000,NOW+1000):
            r=candidate();r["candles_4h"][-1]["observed_at"]=iso(when)
            self.assertEqual(assess_pilot(r,NOW)["action"],"ABSTAIN")

    def test_accounts_immutable_and_run_idempotent(self):
        s=configured();r=candidate();r["oi"][1]["quantity"]="99000.000"
        updated,event=process_pilot(s,r,NOW)
        self.assertEqual(updated["accounts"],s["accounts"])
        self.assertEqual(event["accounts"]["KAIA-A01"]["action"],"NO_TRADE")
        self.assertEqual(updated["revision"],s["revision"]+1)
        again,result=process_pilot(updated,r,NOW+1)
        self.assertEqual(again,updated);self.assertEqual(result["status"],"ALREADY_RECORDED")

    def test_position_account_and_wrong_strategy_not_supported(self):
        for key,value in (("position",{"side":"long"}),("strategy_version","unknown"),("symbol","JCTUSDT")):
            s=configured();s["accounts"]["KAIA-A01"][key]=value
            with self.assertRaises(ValueError):process_pilot(s,candidate(),NOW)

    def test_invalid_state_or_chronology_is_rejected(self):
        s=configured();s["mode"]="live"
        with self.assertRaises(ValueError):process_pilot(s,candidate(),NOW)
        with self.assertRaises(ValueError):process_pilot(configured(),candidate(),NOW-70_000)

    def test_stale_quotes_abstain_with_unchanged_account(self):
        s=configured();updated,event=process_pilot(s,candidate(),NOW+70_000)
        self.assertEqual(updated["accounts"],s["accounts"])
        self.assertEqual(event["accounts"]["KAIA-A01"]["action"],"ABSTAIN")

    def test_cli_persists_before_reporting_success(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"state.json";observation=Path(d)/"observation.json"
            path.write_text(json.dumps(configured()));observation.write_text(json.dumps(candidate()))
            args=Namespace(state=str(path),ui_pilot=str(observation),record=True)
            result=run_ui_pilot(args,now=lambda:NOW)
            self.assertIn(result["run_id"],json.loads(path.read_text())["runs"])
            self.assertFalse(result["remote_persistence_verified"])
            self.assertFalse(result["paper_execution_enabled"])


if __name__=="__main__":unittest.main()
