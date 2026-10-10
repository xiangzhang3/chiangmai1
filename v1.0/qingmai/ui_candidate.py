"""Isolated shadow-only assessment of rendered UI evidence. No ledger imports.

Venue timestamps are never manufactured. Derived UI times and conservative
display-rounding bounds are explicit modelling assumptions, not execution proof.
"""
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import re
import time
from urllib.parse import urlparse, parse_qs
from .market import DataUnavailable, number

VERSION = "binance-rendered-shadow-v0.1"


def timestamp(value):
    dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if dt.tzinfo is None:
        raise DataUnavailable("Capture time needs explicit timezone")
    return int(dt.timestamp()*1000)


def decimal_display_bounds(value):
    """One whole displayed unit each side, covering round/truncate conventions.

    These are model bounds, not an assertion of an undocumented UI contract.
    """
    match = re.fullmatch(r"([0-9]+(?:\.[0-9]+)?)\s*([KMB]?)", str(value))
    if not match:
        raise DataUnavailable("Unsupported displayed number format")
    scale = {"":1,"K":1000,"M":1_000_000,"B":1_000_000_000}[match[2]]
    text = match[1]
    unit = Decimal(10) ** (-len(text.split(".")[1]) if "." in text else 0) * scale
    value = Decimal(text) * scale
    if value <= 0:
        raise DataUnavailable("Displayed value must be positive")
    lower,upper=max(value-unit,Decimal(0)),value+unit
    number(float(lower));number(float(upper))
    return lower,upper


def display_bounds(value):
    return tuple(float(x) for x in decimal_display_bounds(value))


def display_time(label, capture_ms, offset_minutes):
    """Resolve a displayed local label; output is derived, never venue time."""
    zone = timezone(timedelta(minutes=offset_minutes))
    capture = datetime.fromtimestamp(capture_ms/1000, timezone.utc).astimezone(zone)
    if re.fullmatch(r"\d{2}:\d{2}:\d{2}", label):
        parsed = datetime.strptime(label,"%H:%M:%S")
        candidates = [capture.replace(hour=parsed.hour,minute=parsed.minute,second=parsed.second,microsecond=0)+timedelta(days=d) for d in (-1,0,1)]
    elif re.fullmatch(r"\d{2}/\d{2} \d{2}:\d{2}", label):
        candidates=[]
        for year in (capture.year-1,capture.year,capture.year+1):
            try:
                candidates.append(datetime.strptime(f"{year}/{label}","%Y/%m/%d %H:%M").replace(tzinfo=zone))
            except ValueError:
                continue
    elif re.fullmatch(r"\d{4}/\d{2}/\d{2} \d{2}:\d{2}", label):
        candidates=[datetime.strptime(label,"%Y/%m/%d %H:%M").replace(tzinfo=zone)]
    else:
        raise DataUnavailable("Unsupported raw UI time label")
    if not candidates:
        raise DataUnavailable("Unresolvable UI calendar date")
    chosen=min(candidates,key=lambda dt:abs(dt.timestamp()*1000-capture_ms))
    return int(chosen.timestamp()*1000)


def assess(record, now_ms=None):
    """May produce a shadow signal; execution_eligible is always False."""
    now_ms = int(time.time()*1000) if now_ms is None else now_ms
    result = {"adapter_version":VERSION,"status":"INCOMPLETE","execution_eligible":False,
              "shadow_signal":None,"venue_event_timestamp":None,
              "time_uncertainty":"UI clock offset applied to UI labels; not verified venue event timestamps",
              "activation_blockers":["Rendered collector and time-mapping validation pending", "Funding settlement/accounting bridge pending", "Independent review and prospective paper activation required"]}
    try:
        symbol=record["symbol"]
        if record["schema_version"] != VERSION or not re.fullmatch(r"[A-Z0-9]{2,30}USDT",symbol):
            raise DataUnavailable("Unknown schema or instrument")
        base=symbol[:-4]
        raw_offset=number(record["utc_offset_minutes"])
        if isinstance(record["utc_offset_minutes"],bool) or raw_offset!=int(raw_offset):
            raise DataUnavailable("UTC offset must be an exact number of minutes")
        offset=int(raw_offset)
        if not -720 <= offset <= 840 or offset % 15:
            raise DataUnavailable("Invalid visible UTC offset")
        quotes=record["quotes"]
        if len(quotes)!=2:
            raise DataUnavailable("Need exactly two repeated visible quote captures")
        times=[]; tapes=[]; books=[]; clocks=[]
        for q in quotes:
            if q["source_url"] != f"https://www.binance.com/en/futures/{symbol}" or q["selected_symbol"]!=symbol or q["perpetual_label"] is not True:
                raise DataUnavailable("Quote source/instrument identity is unverified")
            captured=timestamp(q["observed_at"]); started=timestamp(q["capture_started_at"])
            if not 0<=captured-started<=10_000 or not -5_000<=now_ms-captured<=60_000:
                raise DataUnavailable("Quote capture is stale, future or too slow")
            clock=re.fullmatch(r"(\d{2}:\d{2}:\d{2}) UTC([+-]\d{1,2})(?::(\d{2}))?",q["chart_clock_text"])
            if not clock:
                raise DataUnavailable("Missing explicit displayed clock offset")
            if int(clock[3] or 0)>=60:
                raise DataUnavailable("Invalid displayed offset minutes")
            clock_offset=int(clock[2])*60 + (int(clock[3] or 0) * (-1 if clock[2].startswith("-") else 1))
            if clock_offset!=offset or abs(display_time(clock[1],captured,offset)-captured)>15_000:
                raise DataUnavailable("Displayed clock does not agree with capture UTC")
            clocks.append(display_time(clock[1],captured,offset))
            trade_time=display_time(q["last_trade_time_displayed"],captured,offset)
            if not -5_000<=captured-trade_time<=30_000:
                raise DataUnavailable("Latest rendered trade is not fresh")
            bid_low,bid_high=display_bounds(q["bid_price_displayed"])
            ask_low,ask_high=display_bounds(q["ask_price_displayed"])
            bid_qty,bid_qty_high=display_bounds(q["bid_quantity_displayed"])
            ask_qty,ask_qty_high=display_bounds(q["ask_quantity_displayed"])
            if bid_low<=0 or number(q["bid_price_displayed"],positive=True)>=number(q["ask_price_displayed"],positive=True) or min(bid_qty,ask_qty)<=0:
                raise DataUnavailable("Displayed price/size bounds are ambiguous or insufficient")
            for name in ("last_price","mark_price","index_price"):
                number(q[name],positive=True)
            times.append(captured);tapes.append(trade_time)
            bid_quantity_bounds=decimal_display_bounds(q["bid_quantity_displayed"])
            ask_quantity_bounds=decimal_display_bounds(q["ask_quantity_displayed"])
            books.append((Decimal(str(q["bid_price_displayed"])),Decimal(str(q["ask_price_displayed"])),sum(bid_quantity_bounds)/2,sum(ask_quantity_bounds)/2))
        if not 5_000<=times[1]-times[0]<=30_000 or not 0<=now_ms-times[1]<=30_000:
            raise DataUnavailable("Repeated captures are not within the liveness window")
        if clocks[1]<=clocks[0] or tapes[1]<=tapes[0] or books[0]==books[1]:
            raise DataUnavailable("No observed clock/tape advance and book change")
        boundary=now_ms//3_600_000*3_600_000
        if timestamp(quotes[0]["capture_started_at"])<boundary:
            raise DataUnavailable("Live pair crosses hourly decision boundary; recollect")

        def rows(name):
            output=[]
            for row in record[name]:
                source=urlparse(row["source_url"])
                if source.scheme!="https" or source.netloc!="www.binance.com" or source.path!="/en/futures/funding-history/perpetual/trading-data":
                    raise DataUnavailable("Historical source is not the official statistics page")
                if parse_qs(source.query).get("contract") != [symbol]:
                    raise DataUnavailable("Statistics URL contract is missing, ambiguous or mismatched")
                if row["selected_symbol"]!=symbol or row["quantity_unit"]!=base or row["period"]!="1h":
                    raise DataUnavailable("Historical symbol/unit/period mismatch")
                captured=timestamp(row["observed_at"])
                started=timestamp(row["capture_started_at"])
                if not 0<=now_ms-captured<=600_000 or not 0<=captured-started<=30_000:
                    raise DataUnavailable("Historical UI observation is stale/future")
                derived=display_time(row["raw_ui_time_label"],captured,offset)
                available_at=derived + (3_600_000 if name=="taker" else 0)
                if available_at>started:
                    raise DataUnavailable("Historical interval had not completed when observed")
                output.append((derived,row))
            output.sort(key=lambda item:item[0])
            if len(output)!=2 or output[1][0]-output[0][0]!=3_600_000:
                raise DataUnavailable("Need two distinct contiguous hourly observations")
            return output

        oi=rows("oi");taker=rows("taker")
        if oi[-1][0]!=boundary or taker[-1][0]!=boundary-3_600_000:
            raise DataUnavailable("OI/taker windows not aligned to the last completed hour")
        candle=record["candle"]
        if candle["source_url"]!=f"https://www.binance.com/en/futures/{symbol}" or candle["selected_symbol"]!=symbol or candle["period"]!="1h":
            raise DataUnavailable("Candle symbol/period mismatch")
        captured=timestamp(candle["observed_at"])
        started=timestamp(candle["capture_started_at"])
        if not 0<=now_ms-captured<=600_000 or not 0<=captured-started<=30_000 or display_time(candle["raw_ui_time_label"],captured,offset)!=boundary-3_600_000 or started<boundary:
            raise DataUnavailable("Need the correctly aligned completed candle")
        o,h,l,c=[number(candle[k],positive=True) for k in ("open","high","low","close")]
        if not l<=min(o,c)<=max(o,c)<=h:
            raise DataUnavailable("Invalid historical candle")
        oi_change=number((number(oi[1][1]["quantity"],positive=True)/number(oi[0][1]["quantity"],positive=True)-1)*100)
        ratios=[number(number(x[1]["buy_quantity"],positive=True)/number(x[1]["sell_quantity"],positive=True)) for x in taker]
        old_low,old_high=display_bounds(oi[0][1]["quantity"])
        new_low,new_high=display_bounds(oi[1][1]["quantity"])
        oi_lower=number((new_low/old_high-1)*100)
        ratios_lower=[number(display_bounds(x[1]["buy_quantity"])[0]/display_bounds(x[1]["sell_quantity"])[1]) for x in taker]
        high_upper=display_bounds(candle["high"])[1]
        oi_pass=decimal_display_bounds(oi[1][1]["quantity"])[0]*100 > decimal_display_bounds(oi[0][1]["quantity"])[1]*102
        taker_pass=all(decimal_display_bounds(x[1]["buy_quantity"])[0] > Decimal("1.10")*decimal_display_bounds(x[1]["sell_quantity"])[1] for x in taker)
        result.update(status="SHADOW_EVIDENCE_ACCEPTED",symbol=symbol,
                      shadow_signal="CANDIDATE_LONG" if oi_pass and taker_pass and decimal_display_bounds(quotes[-1]["bid_price_displayed"])[0]>decimal_display_bounds(candle["high"])[1] else "NO_TRADE",
                      features={"oi_1h_pct_point":oi_change,"oi_1h_pct_lower":oi_lower,"taker_ratios_point":ratios,"taker_ratios_lower":ratios_lower,"previous_hour_high":h,"previous_hour_high_upper":high_upper,"previous_hour_low":l,
                                "conservative_bid_lower":bid_low,"conservative_ask_upper":ask_high,
                                "conservative_bid_quantity_lower":bid_qty,"conservative_ask_quantity_lower":ask_qty},
                      derived_hour_boundary_ms=boundary,observed_at_ms=times[-1])
    except (ValueError,KeyError,TypeError,IndexError,AttributeError,ArithmeticError) as exc:
        result["reason"]=str(exc) if isinstance(exc,DataUnavailable) else "Malformed public market field: "+type(exc).__name__
    return result
