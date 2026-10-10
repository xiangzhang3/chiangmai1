"""All market fixtures are synthetic. Tests never contact an exchange."""
from copy import deepcopy
from argparse import Namespace
import hashlib
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from qingmai.market import BASE, HOUR, DataUnavailable, PublicClient, features, book_fill
from qingmai.paper import process, recovered_state, metrics, digest,initialize_prospective_jct
from qingmai.__main__ import atomic_write, run
from qingmai.core import PaperAccount
from qingmai.ui_research import inspect_observation

BOUNDARY = 1_791_648_000_000
NOW = BOUNDARY + 300_000


def snapshot():
    candles = []
    for i in range(170):
        start = BOUNDARY - (170-i) * HOUR
        candles.append([start, "99.5", "100", "99", "99.5", "1", start+HOUR-1, "100", 1, "0.6", "60", "0"])
    return {
        "symbol": "KAIAUSDT", "source": BASE,
        "collection_started_ms": NOW-2_000, "collected_at_ms": NOW,
        "server_time_ms": NOW,
        "contract": {"symbol": "KAIAUSDT", "contractType": "PERPETUAL", "quoteAsset": "USDT", "status": "TRADING"},
        "funding_interval_hours": 8,
        "klines": candles,
        "oi": [{"symbol": "KAIAUSDT", "timestamp": BOUNDARY-(24-i)*HOUR, "sumOpenInterest": "103" if i==24 else "100"} for i in range(25)],
        "taker": [{"symbol": "KAIAUSDT", "timestamp": BOUNDARY-i*HOUR, "buySellRatio": "1.2"} for i in (2,1)],
        "mark": {"symbol": "KAIAUSDT", "time": NOW, "markPrice": "101", "indexPrice": "101", "lastFundingRate": "0.0001", "nextFundingTime": BOUNDARY+8*HOUR},
        "book": {"T": NOW, "bids": [["101", "100"]], "asks": [["101.01", "100"]]},
        "funding": [],
    }


def state():
    p = Path(__file__).resolve().parents[1] / "qingmai/sim_accounts/KAIA-A01.json"
    return recovered_state(json.loads(p.read_text()))


class PaperTests(unittest.TestCase):
    def test_new_jct_account_preserves_unknown_legacy(self):
        s=state();new=initialize_prospective_jct(s,NOW)
        self.assertEqual(new["accounts"]["JCT-A01"],s["accounts"]["JCT-A01"])
        self.assertEqual(new["accounts"]["JCT-P01-20261010"]["cash"],1000)
        self.assertEqual(new["accounts"]["JCT-P01-20261010"]["trades"],[])
        self.assertEqual(new["accounts"]["JCT-P01-20261010"]["created_at_ms"],NOW)
        with self.assertRaises(ValueError): initialize_prospective_jct(new,NOW+1)

    def test_jct_volume_gate_and_smaller_position(self):
        s=initialize_prospective_jct(state(),NOW)
        data=snapshot();data["symbol"]="JCTUSDT";data["contract"]["symbol"]="JCTUSDT";data["mark"]["symbol"]="JCTUSDT"
        for row in data["oi"]+data["taker"]:row["symbol"]="JCTUSDT"
        blocked,report=process(s,{"JCTUSDT":data},NOW,"jct-one",execute=True)
        self.assertIsNone(blocked["accounts"]["JCT-P01-20261010"]["position"])
        self.assertIn("volume acceleration",report["accounts"]["JCT-P01-20261010"]["reason"])
        for row in data["klines"][-2:]:row[7]="200"
        opened,report=process(s,{"JCTUSDT":data},NOW,"jct-two",execute=True)
        p=opened["accounts"]["JCT-P01-20261010"]["position"]
        self.assertLessEqual(p["entry"]*p["quantity"],100.000001)
        self.assertLessEqual(p["planned_risk_usdt"],5.000001)
        self.assertEqual(opened["accounts"]["JCT-A01"]["status"],"ACCOUNT_STATE_UNVERIFIED")

    def test_official_ui_observation_always_research_only(self):
        record={"symbol":"KAIAUSDT","source_url":"https://www.binance.com/en/futures/KAIAUSDT","observed_at":"2026-10-10T16:00:00Z","fields":{"last_price":1,"funding_rate":-0.001}}
        self.assertFalse(inspect_observation(record)["execution_eligible"])

    def test_ui_observation_rejects_other_source(self):
        record={"symbol":"KAIAUSDT","source_url":"https://example.com","observed_at":"2026-10-10T16:00:00Z","fields":{}}
        with self.assertRaises(DataUnavailable): inspect_observation(record)

    def test_ui_observation_rejects_private_fields(self):
        record={"symbol":"KAIAUSDT","source_url":"https://www.binance.com/en/futures/KAIAUSDT","observed_at":"2026-10-10T16:00:00Z","fields":{"account_balance":100}}
        with self.assertRaises(DataUnavailable): inspect_observation(record)

    def test_current_features(self):
        f = features(snapshot(), NOW)
        self.assertAlmostEqual(f["oi_1h_pct"], 3)
        self.assertAlmostEqual(f["volume_acceleration"], 1)
        self.assertAlmostEqual(f["volume_same_slot_ratio_7d"], 1)

    def test_no_default_ten_thousand_budget(self):
        with self.assertRaises(TypeError): PaperAccount("unknown")

    def test_nonfinite_order_rejected(self):
        a = PaperAccount("test", cash=1000)
        with self.assertRaises(ValueError): a.open("KAIAUSDT", "long", float("nan"), 1)

    def test_legacy_is_preserved(self):
        s = state()
        self.assertEqual(s["legacy_source_sha256"], digest(s["legacy_checkpoint"]))
        self.assertEqual(s["accounts"]["KAIA-A01"]["cash"], 1000)
        self.assertIsNone(s["accounts"]["JCT-A01"]["cash"])

    def test_nonflat_checkpoint_cannot_reset(self):
        legacy = state()["legacy_checkpoint"]
        legacy["state"]["position_side"] = "LONG"
        with self.assertRaises(ValueError): recovered_state(legacy)

    def test_hidden_checkpoint_costs_cannot_reset(self):
        for key, value in (("equity",800),("fees_paid",10),("funding_paid",200),("realized_pnl",-20),("slippage_paid",3)):
            legacy=state()["legacy_checkpoint"]; legacy["state"][key]=value
            with self.subTest(key=key):
                with self.assertRaises(ValueError): recovered_state(legacy)

    def test_negative_collection_duration_rejected(self):
        data=snapshot(); data["collection_started_ms"]=NOW+1_000_000
        with self.assertRaises(DataUnavailable): features(data,NOW)

    def test_missing_data_no_trade_and_equity_not_fresh(self):
        original = state()
        updated, report = process(original, {}, NOW, "one", execute=True)
        self.assertEqual(updated["accounts"], original["accounts"])
        self.assertEqual(report["accounts"]["KAIA-A01"]["reason"], "DATA_UNAVAILABLE")
        self.assertFalse(report["accounts"]["KAIA-A01"]["equity_fresh"])

    def test_jct_unknown_even_with_data(self):
        data = snapshot(); data["symbol"] = "JCTUSDT"
        updated, report = process(state(), {"JCTUSDT":data}, NOW, "one", execute=True)
        self.assertEqual(report["accounts"]["JCT-A01"]["reason"], "ACCOUNT_STATE_UNVERIFIED")
        self.assertIsNone(updated["accounts"]["JCT-A01"]["cash"])

    def test_stale_quote_abstains(self):
        data = snapshot(); data["book"]["T"] -= 61_000
        updated, report = process(state(), {"KAIAUSDT":data}, NOW, "one", execute=True)
        self.assertEqual(updated["accounts"]["KAIA-A01"]["cash"], 1000)
        self.assertEqual(report["accounts"]["KAIA-A01"]["action"], "ABSTAIN")

    def test_future_quote_rejected(self):
        data = snapshot(); data["book"]["T"] += 6000
        with self.assertRaises(DataUnavailable): features(data, NOW)

    def test_server_clock_skew_rejected(self):
        data = snapshot(); data["server_time_ms"] -= 31_000
        with self.assertRaises(DataUnavailable): features(data, NOW)

    def test_missing_candle_rejected(self):
        data = snapshot(); data["klines"][3][0] -= HOUR
        with self.assertRaises(DataUnavailable): features(data, NOW)

    def test_unclosed_candle_not_used(self):
        data = snapshot(); data["klines"][-1][6] = NOW+HOUR
        with self.assertRaises(DataUnavailable): features(data, NOW)

    def test_misaligned_oi_rejected(self):
        data = snapshot()
        for row in data["oi"]: row["timestamp"] -= HOUR
        with self.assertRaises(DataUnavailable): features(data, NOW)

    def test_misaligned_taker_rejected(self):
        data = snapshot()
        for row in data["taker"]: row["timestamp"] -= HOUR
        with self.assertRaises(DataUnavailable): features(data, NOW)

    def test_wrong_venue_rejected(self):
        data = snapshot(); data["source"] = "https://aggregate.example"
        with self.assertRaises(DataUnavailable): features(data, NOW)

    def test_inactive_contract_rejected(self):
        data = snapshot(); data["contract"]["status"] = "SETTLING"
        with self.assertRaises(DataUnavailable): features(data, NOW)

    def test_unsorted_book_rejected(self):
        data = snapshot(); data["book"]["asks"] += [["100.5","100"]]
        with self.assertRaises(DataUnavailable): features(data, NOW)

    def test_insufficient_depth_rejected(self):
        with self.assertRaises(DataUnavailable): book_fill(snapshot(), "buy", 101, .0005)

    def test_vwap_uses_multiple_levels(self):
        data = snapshot(); data["book"]["asks"] = [["100","1"],["102","1"]]
        self.assertAlmostEqual(book_fill(data,"buy",2,0),101)

    def test_read_only_signal_no_position(self):
        updated, report = process(state(), {"KAIAUSDT":snapshot()}, NOW, "one")
        self.assertIsNone(updated["accounts"]["KAIA-A01"]["position"])
        self.assertEqual(report["accounts"]["KAIA-A01"]["action"], "ENTRY_SIGNAL")

    def test_open_cost_risk_and_leverage_caps(self):
        updated, report = process(state(), {"KAIAUSDT":snapshot()}, NOW, "one", execute=True)
        a = updated["accounts"]["KAIA-A01"]; p = a["position"]
        self.assertEqual(report["accounts"]["KAIA-A01"]["action"], "PAPER_OPEN")
        self.assertLessEqual(p["quantity"]*p["entry"],300.000001)
        self.assertLessEqual(p["planned_risk_usdt"],10.000001)
        self.assertLess(a["cash"],1000)
        self.assertGreater(metrics(a)["max_sampled_drawdown_pct"],0)

    def test_duplicate_run_no_double_order_or_event(self):
        opened, _ = process(state(), {"KAIAUSDT":snapshot()}, NOW, "one", execute=True)
        again, report = process(opened, {"KAIAUSDT":snapshot()}, NOW, "one", execute=True)
        self.assertEqual(again,opened)
        self.assertEqual(report["status"],"ALREADY_RECORDED")

    def test_close_net_costs_and_no_backdated_fill(self):
        opened, _ = process(state(), {"KAIAUSDT":snapshot()}, NOW, "one", execute=True)
        data = snapshot(); data["book"]["bids"] = [["98","100"]]; data["book"]["asks"] = [["98.01","100"]]
        data["mark"]["markPrice"] = "98"
        closed, report = process(opened, {"KAIAUSDT":data}, NOW, "two", execute=True)
        a = closed["accounts"]["KAIA-A01"]; t = a["trades"][0]
        self.assertEqual(report["accounts"]["KAIA-A01"]["action"],"PAPER_CLOSE")
        self.assertLess(t["exit"],98)
        self.assertEqual(t["closed_at_ms"],NOW)
        self.assertAlmostEqual(a["cash"],1000+t["net_pnl"])
        self.assertLess(t["net_pnl"],t["gross_pnl"])

    def test_structure_stop_with_missing_oi_still_exits(self):
        opened, _ = process(state(), {"KAIAUSDT":snapshot()}, NOW, "one", execute=True)
        data = snapshot(); data["oi"] = []
        data["book"]["bids"] = [["98","100"]]; data["book"]["asks"] = [["98.01","100"]]
        closed, report = process(opened, {"KAIAUSDT":data}, NOW, "two", execute=True)
        self.assertEqual(report["accounts"]["KAIA-A01"]["action"],"PAPER_CLOSE")

    def test_funding_missing_never_assumed_zero(self):
        opened, _ = process(state(), {"KAIAUSDT":snapshot()}, NOW, "one", execute=True)
        opened["accounts"]["KAIA-A01"]["position"]["next_funding_ms"] = BOUNDARY
        newer, report = process(opened, {"KAIAUSDT":snapshot()}, NOW, "two", execute=True)
        self.assertEqual(newer["accounts"],opened["accounts"])
        self.assertIn("funding",report["accounts"]["KAIA-A01"]["detail"])

    def test_funding_debited_once(self):
        opened, _ = process(state(), {"KAIAUSDT":snapshot()}, NOW, "one", execute=True)
        p=opened["accounts"]["KAIA-A01"]["position"]; p["next_funding_ms"]=BOUNDARY
        data=snapshot(); data["funding"]=[{"symbol":"KAIAUSDT","fundingTime":BOUNDARY,"markPrice":"101","fundingRate":"0.001"}]
        newer,_=process(opened,{"KAIAUSDT":data},NOW,"two",execute=True)
        newest,_=process(newer,{"KAIAUSDT":data},NOW,"three",execute=True)
        self.assertGreater(newer["accounts"]["KAIA-A01"]["funding_paid"],0)
        self.assertEqual(newer["accounts"],newest["accounts"])

    def test_duplicate_funding_timestamps_rollback(self):
        opened,_=process(state(),{"KAIAUSDT":snapshot()},NOW,"one",execute=True)
        opened["accounts"]["KAIA-A01"]["position"]["next_funding_ms"]=BOUNDARY
        row={"symbol":"KAIAUSDT","fundingTime":BOUNDARY,"markPrice":"101","fundingRate":"0.001"}
        data=snapshot(); data["funding"]=[row,row]
        newer,report=process(opened,{"KAIAUSDT":data},NOW,"two",execute=True)
        self.assertEqual(newer["accounts"],opened["accounts"])
        self.assertIn("Duplicate funding",report["accounts"]["KAIA-A01"]["detail"])

    def test_missing_last_funding_rollback(self):
        opened,_=process(state(),{"KAIAUSDT":snapshot()},NOW,"one",execute=True)
        opened["accounts"]["KAIA-A01"]["position"]["next_funding_ms"]=BOUNDARY-8*HOUR
        data=snapshot(); data["funding"]=[{"symbol":"KAIAUSDT","fundingTime":BOUNDARY-8*HOUR,"markPrice":"101","fundingRate":"0.001"}]
        newer,report=process(opened,{"KAIAUSDT":data},NOW,"two",execute=True)
        self.assertEqual(newer["accounts"],opened["accounts"])
        self.assertIn("funding history is missing",report["accounts"]["KAIA-A01"]["detail"])

    def test_changed_funding_schedule_rollback(self):
        opened,_=process(state(),{"KAIAUSDT":snapshot()},NOW,"one",execute=True)
        opened["accounts"]["KAIA-A01"]["position"]["next_funding_ms"]=BOUNDARY
        data=snapshot(); data["funding_interval_hours"]=4
        newer,report=process(opened,{"KAIAUSDT":data},NOW,"two",execute=True)
        self.assertEqual(newer["accounts"],opened["accounts"])
        self.assertIn("schedule changed",report["accounts"]["KAIA-A01"]["detail"])

    def test_changed_funding_schedule_before_expected_due_rollback(self):
        opened,_=process(state(),{"KAIAUSDT":snapshot()},NOW,"one",execute=True)
        data=snapshot(); data["funding_interval_hours"]=1
        newer,report=process(opened,{"KAIAUSDT":data},NOW,"two",execute=True)
        self.assertEqual(newer["accounts"],opened["accounts"])
        self.assertIn("schedule changed",report["accounts"]["KAIA-A01"]["detail"])

    def test_close_before_open_rejected(self):
        opened,_=process(state(),{"KAIAUSDT":snapshot()},NOW,"one",execute=True)
        opened["accounts"]["KAIA-A01"]["position"]["opened_at_ms"]=NOW+1000
        data=snapshot(); data["book"]["bids"]=[["98","100"]]; data["book"]["asks"]=[["98.01","100"]]
        newer,report=process(opened,{"KAIAUSDT":data},NOW,"two",execute=True)
        self.assertEqual(newer["accounts"],opened["accounts"])
        self.assertIn("predates position",report["accounts"]["KAIA-A01"]["detail"])

    def test_old_account_observation_rejected(self):
        s=state(); s["accounts"]["KAIA-A01"]["equity_as_of_ms"]=NOW+1000
        newer,report=process(s,{"KAIAUSDT":snapshot()},NOW,"one",execute=True)
        self.assertEqual(newer["accounts"],s["accounts"])
        self.assertIn("predates account",report["accounts"]["KAIA-A01"]["detail"])

    def test_safety_filter_avoids_wide_spread(self):
        data=snapshot(); data["book"]["asks"]=[["102","100"]]
        updated, report=process(state(),{"KAIAUSDT":data},NOW,"one",execute=True)
        self.assertIsNone(updated["accounts"]["KAIA-A01"]["position"])
        self.assertIn("safety",report["accounts"]["KAIA-A01"]["reason"])

    def test_exact_two_percent_oi_does_not_open(self):
        data=snapshot();data["oi"][-1]["sumOpenInterest"]="102"
        updated,report=process(state(),{"KAIAUSDT":data},NOW,"one",execute=True)
        self.assertIsNone(updated["accounts"]["KAIA-A01"]["position"])
        self.assertEqual(report["accounts"]["KAIA-A01"]["action"],"NO_TRADE")

    def test_live_mode_rejected(self):
        s=state(); s["mode"]="live"
        with self.assertRaises(ValueError): process(s,{},NOW,"one",execute=True)

    def test_private_endpoint_rejected_before_network(self):
        with patch("qingmai.market.urlopen") as network:
            with self.assertRaises(DataUnavailable): PublicClient().get("/fapi/v1/order")
            network.assert_not_called()

    def test_atomic_compare_and_swap(self):
        with tempfile.TemporaryDirectory() as d:
            path=Path(d)/"state.json"; path.write_text("{}")
            with self.assertRaises(RuntimeError): atomic_write(path,{"bad":1},"stale")
            self.assertEqual(path.read_text(),"{}")
            atomic_write(path,{"ok":1},hashlib.sha256(b"{}").hexdigest())
            self.assertEqual(json.loads(path.read_text()),{"ok":1})

    def test_end_to_end_no_data_records_no_fills(self):
        class Offline:
            def collect(self,symbol): raise DataUnavailable("Fixture: network unavailable")
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/"state.json"; p.write_text(json.dumps(state()))
            args=Namespace(state=str(p),symbols="KAIAUSDT,JCTUSDT,STRKUSDT",record=True,paper_execute=True)
            report=run(args,client=Offline(),now=lambda:NOW)
            stored=json.loads(p.read_text())
            self.assertEqual(stored["accounts"]["KAIA-A01"]["cash"],1000)
            self.assertEqual(len(stored["events"]),1)
            self.assertEqual(report["accounts"]["KAIA-A01"]["action"],"ABSTAIN")
            self.assertEqual(run(args,client=Offline(),now=lambda:NOW)["status"],"ALREADY_RECORDED")


if __name__ == "__main__": unittest.main()
