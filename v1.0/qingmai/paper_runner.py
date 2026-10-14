"""Scheduled JCT paper engine. Research only, never sends exchange orders."""
import json, os, sys, time
from datetime import datetime, timezone
from pathlib import Path
import requests
from qingmai.risk import size_position, verify_ledger
from qingmai.guardrails import validate_quote

ROOT=Path(__file__).resolve().parent
ACCOUNT=ROOT/"sim_accounts"/"JCT-A01.json"
HEALTH=ROOT/"sim_accounts"/"JCT-A01-health.json"
API="https://fapi.binance.com"
SYMBOL="JCTUSDT"

def now(): return datetime.now(timezone.utc)
def iso(): return now().isoformat()
def get(path, **params):
    r=requests.get(API+path, params=params,timeout=10,headers={"User-Agent":"qingmai-one-research/1.1"})
    r.raise_for_status()
    d=r.json()
    if isinstance(d,dict) and ("code" in d and int(d["code"])<0):
        raise RuntimeError(str(d))
    return d
def asof(ms): return datetime.fromtimestamp(int(ms)/1000,timezone.utc).isoformat()
def report(status,reason,details=None):
    payload={"checked_at":iso(),"status":status,"reason":str(reason)[:600],"details":details or {}}
    HEALTH.write_text(json.dumps(payload,indent=2,ensure_ascii=False)+"\n")
    print(json.dumps(payload,ensure_ascii=False))
    return payload
def exchange_snapshot():
    info=get("/fapi/v1/exchangeInfo")
    products=[s for s in info["symbols"] if s["symbol"]==SYMBOL and s["status"]=="TRADING" and s["contractType"]=="PERPETUAL" and s.get("quoteAsset")=="USDT"]
    if len(products)!=1: raise ValueError("JCTUSDT Binance USDT perpetual not verified")
    mark=get("/fapi/v1/premiumIndex",symbol=SYMBOL)
    price=float(mark["markPrice"])
    validate_quote({"source":"binance_futures_mark","price":price,"as_of":asof(mark["time"])})
    candles=get("/fapi/v1/klines",symbol=SYMBOL,interval="1h",limit=171)
    oi=get("/futures/data/openInterestHist",symbol=SYMBOL,period="1h",limit=30)
    taker=get("/futures/data/takerlongshortRatio",symbol=SYMBOL,period="1h",limit=3)
    if len(candles)<170 or len(oi)<25 or len(taker)<2: raise ValueError("Insufficient historical data")
    # Exclude currently forming candle; exchange close time must be <= current time.
    complete=[c for c in candles if int(c[6]) < int(now().timestamp()*1000)]
    if len(complete)<168: raise ValueError("Insufficient completed candles")
    if now().timestamp()*1000-int(complete[-1][6])>75*60*1000: raise ValueError("Stale completed candles")
    if now().timestamp()*1000-int(oi[-1]["timestamp"])>130*60*1000: raise ValueError("Stale OI series")
    if now().timestamp()*1000-int(taker[-1]["timestamp"])>130*60*1000: raise ValueError("Stale taker series")
    def change(a,b): return 100*(a/b-1) if b else 0
    vol2=sum(float(c[7]) for c in complete[-2:])
    mean_daily=sum(float(c[7]) for c in complete[-168:])/7
    oi2=change(float(oi[-1]["sumOpenInterest"]),float(oi[-3]["sumOpenInterest"]))
    price2=change(float(complete[-1][4]),float(complete[-3][4]))
    ratio=float(taker[-1]["buySellRatio"])
    acceleration=12*vol2/mean_daily if mean_daily>0 else 0
    high=max(float(c[2]) for c in complete[-7:-1])
    low=min(float(c[3]) for c in complete[-7:-1])
    return {"source":"binance_futures","as_of":asof(mark["time"]),"price":price,"oi_2h_pct":oi2,"price_2h_pct":price2,
            "taker_ratio":ratio,"volume_acceleration":acceleration,"prior_6h_high":high,"prior_6h_low":low,
            "funding_rate":float(mark["lastFundingRate"]),"symbol":SYMBOL}
def bybit_snapshot():
    """Independent linear USDT perpetual venue; do not splice Binance OI into Bybit data."""
    base="https://api.bybit.com"
    def by(path,**params):
        resp=requests.get(base+path,params=params,timeout=10)
        resp.raise_for_status()
        data=resp.json()
        if data.get("retCode")!=0: raise ValueError("Bybit API error: "+str(data.get("retMsg")))
        return data
    info=by("/v5/market/instruments-info",category="linear",symbol=SYMBOL)
    products=[s for s in info["result"]["list"] if s.get("symbol")==SYMBOL and s.get("status")=="Trading"
              and s.get("quoteCoin")=="USDT" and s.get("contractType")=="LinearPerpetual"]
    if len(products)!=1: raise ValueError("Bybit JCTUSDT linear perpetual not verified")
    quote=by("/v5/market/tickers",category="linear",symbol=SYMBOL)
    ticks=[x for x in quote["result"]["list"] if x.get("symbol")==SYMBOL]
    if len(ticks)!=1: raise ValueError("Bybit contract quote missing")
    price=float(ticks[0]["markPrice"])
    stamped=asof(quote["time"])
    validate_quote({"source":"bybit_linear_mark","price":price,"as_of":stamped})
    raw=by("/v5/market/kline",category="linear",symbol=SYMBOL,interval="60",limit=170)["result"]["list"]
    # Bybit candles are newest first, each record starts with bar-open ms.
    candles=sorted(raw,key=lambda a:int(a[0]))
    complete=[x for x in candles if int(x[0])+3600000<int(now().timestamp()*1000)]
    if len(complete)<168: raise ValueError("Bybit missing completed 7d candles")
    if now().timestamp()*1000-(int(complete[-1][0])+3600000)>75*60000:
        raise ValueError("Stale Bybit candle")
    oi_raw=by("/v5/market/open-interest",category="linear",symbol=SYMBOL,intervalTime="1h",limit=30)["result"]["list"]
    oi=sorted(oi_raw,key=lambda x:int(x["timestamp"]))
    if len(oi)<3 or now().timestamp()*1000-int(oi[-1]["timestamp"])>130*60000:
        raise ValueError("Stale Bybit OI history")
    def change(a,b):return 100*(a/b-1) if b else 0
    vol2=sum(float(x[6]) for x in complete[-2:])
    daily=sum(float(x[6]) for x in complete[-168:])/7
    return {"source":"bybit_linear","as_of":stamped,"price":price,
            "oi_2h_pct":change(float(oi[-1]["openInterest"]),float(oi[-3]["openInterest"])),
            "price_2h_pct":change(float(complete[-1][4]),float(complete[-3][4])),
            "taker_ratio":None,"volume_acceleration":12*vol2/daily if daily>0 else 0,
            "prior_6h_high":max(float(x[2]) for x in complete[-7:-1]),
            "prior_6h_low":min(float(x[3]) for x in complete[-7:-1]),
            "funding_rate":float(ticks[0]["fundingRate"]),"symbol":SYMBOL}

def run():
    ledger=json.loads(ACCOUNT.read_text())
    verify_ledger(ledger)
    try:
        market=exchange_snapshot()
    except Exception as primary:
        try:
            market=bybit_snapshot()
        except Exception as fallback:
            report("UNVERIFIED","Binance: "+str(primary)+"; Bybit: "+str(fallback))
            return 0
    # Do not retry the same market observation as another fill.
    previous=ledger.get("last_market_snapshot") or {}
    if market["as_of"]==previous.get("market_as_of") or market["as_of"]==previous.get("as_of"):
        report("DUPLICATE", "Market snapshot previously processed", {"as_of":market["as_of"]})
        return 0
    position=ledger.get("position")
    action="HOLD"
    if position:
        side=position["side"]
        stop=float(position["stop"])
        take=float(position["take_profit"])
        px=market["price"]
        exit_now=(px<=stop or px>=take) if side=="long" else (px>=stop or px<=take)
        if exit_now:
            qty=float(position["quantity"])
            slip=0.0005
            fill=px*(1-slip if side=="long" else 1+slip)
            gross=(fill-float(position["entry"]))*qty*(1 if side=="long" else -1)
            fee=fill*qty*0.0005
            entry_fee=float(position["entry_fee"])
            funding=0.0 # funding only when timestamped cash flow evidence is available
            trade_id=position["trade_id"]
            if any(t["trade_id"]==trade_id for t in ledger["trades"]):raise ValueError("Duplicate trade id")
            ledger["trades"].append({**position,"exit":fill,"closed_at":market["as_of"],"gross_pnl":gross,
                                     "exit_fee":fee,"net_pnl":gross-fee-entry_fee-funding})
            ledger["realized_pnl"]=float(ledger.get("realized_pnl",0))+gross
            ledger["fees_paid"]=float(ledger.get("fees_paid",0))+fee
            ledger["position"]=None
            action="PAPER_CLOSE"
    else:
        # Conservative, deterministic prototype signal. All live fields must be verified first.
        bullish=(market["oi_2h_pct"]>=5 and market["volume_acceleration"]>=5
                 and (market["taker_ratio"]>1.1 if market["taker_ratio"] is not None else market["price_2h_pct"]>3) and market["price"]>market["prior_6h_high"])
        if bullish:
            entry=market["price"]*1.0005
            stop=entry*0.98
            # reserve roundtrip fees & slippage inside the $10 mandate
            sizing=size_position(1000,entry,stop,risk_budget=9.5,notional_cap=300,leverage=1)
            qty=sizing["quantity"]
            entry_fee=qty*entry*0.0005
            trade_id="JCT-"+market["as_of"].replace(":","").replace("-","")
            ledger["position"]={"trade_id":trade_id,"symbol":SYMBOL,"side":"long","quantity":qty,
                                "entry":entry,"stop":stop,"take_profit":entry*1.04,
                                "entry_fee":entry_fee,"opened_at":market["as_of"]}
            ledger["fees_paid"]=float(ledger.get("fees_paid",0))+entry_fee
            action="PAPER_OPEN"
    ledger["last_market_snapshot"]={"market_as_of":market["as_of"],"market_source":market["source"],
                                   "mark_price_usdt":market["price"],"oi_2h_pct":market["oi_2h_pct"],
                                   "volume_acceleration":market["volume_acceleration"],"taker_ratio":market["taker_ratio"],
                                   "decision":action}
    ledger["last_reviewed_at"]=iso()
    ledger["status"]="VERIFIED_"+action
    tmp=ACCOUNT.with_suffix(".tmp")
    tmp.write_text(json.dumps(ledger,ensure_ascii=False,indent=2)+"\n")
    os.replace(tmp,ACCOUNT)
    report("OK",action,{"market_as_of":market["as_of"],"price":market["price"]})
    return 0

if __name__=="__main__":
    try: sys.exit(run())
    except Exception as e:
        report("ERROR",e)
        sys.exit(1)
