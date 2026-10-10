"""Synthetic shadow-adapter tests. Never actual observations or paper fills."""
from copy import deepcopy
from datetime import datetime,timezone,timedelta
import unittest
from qingmai.ui_candidate import VERSION,assess,display_bounds,display_time
from qingmai.market import DataUnavailable

NOW=1_791_648_300_000


def iso(ms):
    return datetime.fromtimestamp(ms/1000,timezone.utc).isoformat()


def record():
    result={"schema_version":VERSION,"symbol":"KAIAUSDT","utc_offset_minutes":-420,"quotes":[],"oi":[],"taker":[]}
    for i,captured in enumerate((NOW-10_000,NOW)):
        local=datetime.fromtimestamp((captured-1000)/1000,timezone(timedelta(hours=-7)))
        result["quotes"].append({"source_url":"https://www.binance.com/en/futures/KAIAUSDT","selected_symbol":"KAIAUSDT","perpetual_label":True,
            "observed_at":iso(captured),"capture_started_at":iso(captured-1000),"chart_clock_text":local.strftime("%H:%M:%S UTC-7"),
            "last_trade_time_displayed":local.strftime("%H:%M:%S"),"bid_price_displayed":"101.00","ask_price_displayed":"101.01",
            "bid_quantity_displayed":str(100+i),"ask_quantity_displayed":"1.25K","last_price":101,"mark_price":101,"index_price":101})
    for label,qty in (("10/10 08:00","100000.000"),("10/10 09:00","103000.000")):
        result["oi"].append({"source_url":"https://www.binance.com/en/futures/funding-history/perpetual/trading-data?contract=KAIAUSDT","selected_symbol":"KAIAUSDT","quantity_unit":"KAIA","period":"1h","observed_at":iso(NOW-20_000),"capture_started_at":iso(NOW-21_000),"raw_ui_time_label":label,"quantity":qty})
    for label in ("10/10 07:00","10/10 08:00"):
        result["taker"].append({"source_url":"https://www.binance.com/en/futures/funding-history/perpetual/trading-data?contract=KAIAUSDT","selected_symbol":"KAIAUSDT","quantity_unit":"KAIA","period":"1h","observed_at":iso(NOW-20_000),"capture_started_at":iso(NOW-21_000),"raw_ui_time_label":label,"buy_quantity":120,"sell_quantity":100})
    result["candle"]={"source_url":"https://www.binance.com/en/futures/KAIAUSDT","selected_symbol":"KAIAUSDT","period":"1h","observed_at":iso(NOW-20_000),"capture_started_at":iso(NOW-21_000),"raw_ui_time_label":"10/10 08:00","open":"99.50","high":"100.00","low":"99.00","close":"99.50"}
    return result


class UICandidateTests(unittest.TestCase):
    def test_conservative_rounded_size(self):
        self.assertEqual(display_bounds("11.93K"),(11920,11940))
        self.assertEqual(display_bounds("932"),(931,933))

    def test_unsupported_display_format(self):
        with self.assertRaises(DataUnavailable): display_bounds("1e9")

    def test_valid_shadow_never_enables_execution(self):
        r=assess(record(),NOW)
        self.assertEqual(r["status"],"SHADOW_EVIDENCE_ACCEPTED")
        self.assertEqual(r["shadow_signal"],"CANDIDATE_LONG")
        self.assertFalse(r["execution_eligible"])
        self.assertIsNone(r["venue_event_timestamp"])

    def test_negative_oi_means_no_trade(self):
        r=record();r["oi"][1]["quantity"]=99
        self.assertEqual(assess(r,NOW)["shadow_signal"],"NO_TRADE")

    def test_missing_second_taker_is_incomplete(self):
        r=record();r["taker"]=r["taker"][:1]
        self.assertEqual(assess(r,NOW)["status"],"INCOMPLETE")

    def test_old_quotes_rejected(self):
        self.assertEqual(assess(record(),NOW+61_000)["status"],"INCOMPLETE")

    def test_unchanged_book_rejected(self):
        r=record();r["quotes"][1]["bid_quantity_displayed"]="100"
        self.assertEqual(assess(r,NOW)["status"],"INCOMPLETE")

    def test_unmoving_tape_rejected(self):
        r=record();r["quotes"][1]["last_trade_time_displayed"]=r["quotes"][0]["last_trade_time_displayed"]
        self.assertEqual(assess(r,NOW)["status"],"INCOMPLETE")

    def test_wrong_instrument_rejected(self):
        r=record();r["quotes"][1]["selected_symbol"]="BTCUSDT"
        self.assertEqual(assess(r,NOW)["status"],"INCOMPLETE")

    def test_missing_explicit_clock_rejected(self):
        r=record();r["quotes"][1]["chart_clock_text"]="09:05:00"
        self.assertEqual(assess(r,NOW)["status"],"INCOMPLETE")

    def test_wrong_offset_rejected(self):
        r=record();r["utc_offset_minutes"]=0
        self.assertEqual(assess(r,NOW)["status"],"INCOMPLETE")

    def test_notional_cannot_replace_oi_quantity(self):
        r=record();r["oi"][1]["quantity_unit"]="USDT"
        self.assertEqual(assess(r,NOW)["status"],"INCOMPLETE")

    def test_duplicate_history_point_rejected(self):
        r=record();r["oi"][1]["raw_ui_time_label"]=r["oi"][0]["raw_ui_time_label"]
        self.assertEqual(assess(r,NOW)["status"],"INCOMPLETE")

    def test_current_candle_rejected(self):
        r=record();r["candle"]["raw_ui_time_label"]="10/10 09:00"
        self.assertEqual(assess(r,NOW)["status"],"INCOMPLETE")

    def test_future_history_rejected(self):
        r=record();r["oi"][0]["observed_at"]=iso(NOW+1000)
        self.assertEqual(assess(r,NOW)["status"],"INCOMPLETE")

    def test_exact_threshold_conservative_bound_does_not_signal(self):
        r=record();r["oi"][0]["quantity"]="100.00";r["oi"][1]["quantity"]="102.010201"
        self.assertEqual(assess(r,NOW)["shadow_signal"],"NO_TRADE")

    def test_formatting_change_is_not_liveness(self):
        r=record();r["quotes"][1]["bid_quantity_displayed"]="100.0"
        self.assertEqual(assess(r,NOW)["status"],"INCOMPLETE")

    def test_decimal_formatting_change_is_not_liveness(self):
        r=record();r["quotes"][0]["bid_quantity_displayed"]="0.06";r["quotes"][1]["bid_quantity_displayed"]="0.060"
        self.assertEqual(assess(r,NOW)["status"],"INCOMPLETE")

    def test_invalid_clock_offset_minutes_rejected(self):
        r=record()
        for q in r["quotes"]:q["chart_clock_text"]=q["chart_clock_text"].replace("UTC-7","UTC-6:60")
        self.assertEqual(assess(r,NOW)["status"],"INCOMPLETE")

    def test_huge_display_bound_rejected(self):
        r=record();r["quotes"][1]["ask_quantity_displayed"]="9"*400
        self.assertEqual(assess(r,NOW)["status"],"INCOMPLETE")

    def test_malformed_values_fail_closed(self):
        for field,value in (("utc_offset_minutes",float("inf")),("utc_offset_minutes",-420.99)):
            r=record();r[field]=value
            self.assertEqual(assess(r,NOW)["status"],"INCOMPLETE")
        r=record();r["quotes"][1]["observed_at"]=None
        self.assertEqual(assess(r,NOW)["status"],"INCOMPLETE")

    def test_wrong_or_duplicate_contract_query_rejected(self):
        for query in ("contract=BTCUSDT","contract=KAIAUSDT&contract=KAIAUSDT"):
            r=record();r["oi"][0]["source_url"]="https://www.binance.com/en/futures/funding-history/perpetual/trading-data?"+query
            self.assertEqual(assess(r,NOW)["status"],"INCOMPLETE")

    def test_history_captured_before_completion_rejected(self):
        r=record()
        for row in r["taker"]+r["oi"]+[r["candle"]]:
            row["observed_at"]=iso(NOW-590_000);row["capture_started_at"]=iso(NOW-591_000)
        self.assertEqual(assess(r,NOW)["status"],"INCOMPLETE")

    def test_history_capture_spanning_completion_rejected(self):
        r=record();r["taker"][-1]["capture_started_at"]=iso(NOW-301_000);r["taker"][-1]["observed_at"]=iso(NOW-299_000)
        self.assertEqual(assess(r,NOW)["status"],"INCOMPLETE")

    def test_valid_leap_day_label(self):
        capture=int(datetime(2024,2,29,12,0,tzinfo=timezone.utc).timestamp()*1000)
        self.assertEqual(display_time("02/29 12:00",capture,0),capture)


if __name__=="__main__": unittest.main()
