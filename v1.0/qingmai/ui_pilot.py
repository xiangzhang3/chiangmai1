"""Observed-UI decision bridge. Flat-account audit only; never creates fills.

This is a separate source model, not a substitute API payload. Positive signals
remain blocked until the funding/position accounting bridge is reviewed.
"""
from copy import deepcopy
from .market import DataUnavailable, HOUR, number
from .paper import KAIA_TIMEFRAME_VERSION, digest, metrics
from .ui_candidate import assess, decimal_display_bounds, display_time, timestamp

VERSION = "binance-rendered-flat-pilot-v0.1"


def market_only_schema(record):
    """Reject extra fields before persisting an external normalized record."""
    top={"schema_version","symbol","utc_offset_minutes","quotes","oi","taker","candle","candles_4h"}
    quote={"source_url","selected_symbol","perpetual_label","observed_at","capture_started_at","chart_clock_text","last_trade_time_displayed","bid_price_displayed","ask_price_displayed","bid_quantity_displayed","ask_quantity_displayed","last_price","mark_price","index_price"}
    common={"source_url","selected_symbol","period","observed_at","capture_started_at","raw_ui_time_label"}
    candle=common|{"open","high","low","close"}
    schemas={"quotes":quote,"oi":common|{"quantity_unit","quantity"},"taker":common|{"quantity_unit","buy_quantity","sell_quantity"},"candles_4h":candle}
    if not isinstance(record,dict) or set(record)-top:
        raise ValueError("Unexpected fields in public market schema")
    for name,allowed in schemas.items():
        rows=record.get(name,[])
        if not isinstance(rows,list) or len(rows)>2:
            raise ValueError("Invalid public market rows")
        for row in rows:
            if not isinstance(row,dict) or set(row)-allowed or any(isinstance(v,(dict,list)) for v in row.values()):
                raise ValueError("Unexpected fields in public market row")
    row=record.get("candle",{})
    if not isinstance(row,dict) or set(row)-candle or any(isinstance(v,(dict,list)) for v in row.values()):
        raise ValueError("Unexpected fields in public candle")


def trend_4h(record, now_ms):
    """Two source-labeled completed candles, with conservative display bounds."""
    symbol=record["symbol"]
    offset=record["utc_offset_minutes"]
    boundary=now_ms//(4*HOUR)*(4*HOUR)
    bars=[]
    for row in record["candles_4h"]:
        if row["source_url"]!=f"https://www.binance.com/en/futures/{symbol}" or row["selected_symbol"]!=symbol or row["period"]!="4h":
            raise DataUnavailable("4h source/symbol/period mismatch")
        captured=timestamp(row["observed_at"]);started=timestamp(row["capture_started_at"])
        if not 0<=now_ms-captured<=600_000 or not 0<=captured-started<=30_000:
            raise DataUnavailable("4h candle capture is stale, future or too slow")
        derived=display_time(row["raw_ui_time_label"],captured,offset)
        if derived+4*HOUR>started:
            raise DataUnavailable("4h candle was still forming at capture start")
        o,h,l,c=[number(row[k],positive=True) for k in ("open","high","low","close")]
        if not l<=min(o,c)<=max(o,c)<=h:
            raise DataUnavailable("Invalid 4h OHLC")
        bars.append((derived,row))
    bars.sort(key=lambda x:x[0])
    if [x[0] for x in bars]!=[boundary-8*HOUR,boundary-4*HOUR]:
        raise DataUnavailable("Need exactly the two latest aligned completed4h candles")
    latest=bars[-1][1];prior=bars[-2][1]
    passes=(decimal_display_bounds(latest["close"])[0]>decimal_display_bounds(latest["open"])[1] and
            decimal_display_bounds(latest["close"])[0]>decimal_display_bounds(prior["close"])[1])
    return {"passes":passes,"derived_end_ms":boundary,"time_basis":"UI chart offset applied to displayed bar labels; no venue timestamp",
            "candles":[{"raw_ui_time_label":r["raw_ui_time_label"],**{k:r[k] for k in ("open","high","low","close")}} for _,r in bars]}


def assess_pilot(record, now_ms):
    result=assess(record,now_ms)
    result["pilot_version"]=VERSION
    result["action"]="ABSTAIN"
    # No path in this module can assert fill eligibility.
    result["execution_eligible"]=False
    if result["status"]!="SHADOW_EVIDENCE_ACCEPTED":
        return result
    try:
        trend=trend_4h(record,now_ms)
        result["trend_4h"]=trend
        if not trend["passes"] or result["shadow_signal"]=="NO_TRADE":
            result.update(action="NO_TRADE",reason="One or more completed1h OI/taker/breakout or4h trend gates failed")
        else:
            result.update(action="ENTRY_CANDIDATE_BLOCKED",reason="Observed-quote position and settled-funding accounting bridge is not activated")
    except (ValueError,KeyError,TypeError,IndexError,AttributeError,ArithmeticError) as exc:
        result.update(status="INCOMPLETE",reason=str(exc) if isinstance(exc,DataUnavailable) else "Malformed public market field: "+type(exc).__name__)
    return result


def process_pilot(state, record, now_ms):
    """Idempotently record one KAIA flat-account decision per UTC hour.

    A valid NO_TRADE is an actual prospective decision. A stale/partial record
    only creates an ABSTAIN audit and never alters balances or positions.
    """
    if state.get("mode")!="paper_only" or state.get("schema_version")!=2:
        raise ValueError("Unsupported paper state")
    if isinstance(now_ms,bool) or not isinstance(now_ms,int) or now_ms<=0:
        raise ValueError("Invalid observation timestamp")
    market_only_schema(record)
    run_id=f"ui-pilot:{now_ms//HOUR}:KAIA-A01"
    if run_id in state["runs"]:
        return state,{"status":"ALREADY_RECORDED","run_id":run_id}
    account=state["accounts"]["KAIA-A01"]
    chronology=max([e["observed_at_ms"] for e in state["events"]]+[account.get("equity_as_of_ms") or 0,account.get("strategy_effective_at_ms") or 0])
    if now_ms<chronology:
        raise ValueError("Pilot observation predates state or strategy")
    if (account["status"]!="VERIFIED" or account["symbol"]!="KAIAUSDT" or record.get("symbol")!="KAIAUSDT" or
        account["strategy_version"]!=KAIA_TIMEFRAME_VERSION or account["position"] is not None):
        raise ValueError("Pilot supports only the verified flat KAIA1h/4h account")
    result=assess_pilot(record,now_ms)
    if result["status"]=="SHADOW_EVIDENCE_ACCEPTED" and timestamp(record["quotes"][0]["capture_started_at"])<account.get("strategy_effective_at_ms",0):
        result.update(status="INCOMPLETE",action="ABSTAIN",reason="Live observation predates strategy activation")
    result["account_id"]="KAIA-A01"
    result["strategy_version"]=account["strategy_version"]
    result["metrics"]=metrics(account)
    output=deepcopy(state)
    evidence_sha=digest(record)
    if result["status"]=="SHADOW_EVIDENCE_ACCEPTED":
        output["market_evidence"].setdefault(evidence_sha,deepcopy(record))
    event={"run_id":run_id,"observed_at_ms":now_ms,"paper_execution_enabled":False,
           "source_model":VERSION,"accounts":{"KAIA-A01":result},"evidence_sha256":evidence_sha,
           "new_fills":0,"accounts_mutated":False,"venue_event_timestamp":None,
           "validated_evidence_stored":result["status"]=="SHADOW_EVIDENCE_ACCEPTED"}
    output["events"].append(event);output["runs"][run_id]=digest(event);output["revision"]+=1
    return output,event
