"""Public Binance USD-M market data; fail closed on stale or malformed inputs."""
import json
import math
import re
import time
from urllib.parse import urlencode
from urllib.request import urlopen

HOUR = 3_600_000
BASE = "https://fapi.binance.com"
PUBLIC_PATHS = frozenset({
    "/fapi/v1/time", "/fapi/v1/exchangeInfo", "/fapi/v1/depth",
    "/fapi/v1/premiumIndex", "/fapi/v1/klines", "/fapi/v1/fundingRate", "/fapi/v1/fundingInfo",
    "/futures/data/openInterestHist", "/futures/data/takerlongshortRatio",
})


class DataUnavailable(ValueError):
    pass


def number(value, *, positive=False):
    result = float(value)
    if not math.isfinite(result) or (positive and result <= 0):
        raise DataUnavailable("Non-finite or non-positive market value")
    return result


class PublicClient:
    """No API keys, private endpoints, order endpoints, POST or live mode."""

    def get(self, path, **params):
        if path not in PUBLIC_PATHS:
            raise DataUnavailable("Endpoint is not public-market allowlisted")
        url = BASE + path + ("?" + urlencode(params) if params else "")
        with urlopen(url, timeout=12) as response:
            return json.load(response)

    def collect(self, symbol):
        if not re.fullmatch(r"[A-Z0-9]{2,30}USDT", symbol):
            raise DataUnavailable("Invalid symbol")
        start = int(time.time() * 1000)
        info = self.get("/fapi/v1/exchangeInfo")
        contract = next((x for x in info["symbols"] if x["symbol"] == symbol), None)
        funding_info = self.get("/fapi/v1/fundingInfo")
        funding_interval = next((int(x["fundingIntervalHours"]) for x in funding_info if x["symbol"] == symbol), 8)
        data = {
            "symbol": symbol, "source": BASE, "collection_started_ms": start,
            "contract": contract,
            "funding_interval_hours": funding_interval,
            "klines": self.get("/fapi/v1/klines", symbol=symbol, interval="1h", limit=171),
            "oi": self.get("/futures/data/openInterestHist", symbol=symbol, period="1h", limit=26),
            "taker": self.get("/futures/data/takerlongshortRatio", symbol=symbol, period="1h", limit=4),
            "mark": self.get("/fapi/v1/premiumIndex", symbol=symbol),
            "funding": self.get("/fapi/v1/fundingRate", symbol=symbol, limit=1000),
            "book": self.get("/fapi/v1/depth", symbol=symbol, limit=100),
            "server_time_ms": int(self.get("/fapi/v1/time")["serverTime"]),
            "collected_at_ms": int(time.time() * 1000),
        }
        return data


def fresh(timestamp, now, maximum_age, label):
    age = now - int(timestamp)
    if age < -5_000 or age > maximum_age:
        raise DataUnavailable(f"Stale/future {label}: age {age} ms")


def contiguous(rows, key, label):
    stamps = [int(key(row)) for row in rows]
    if any(b - a != HOUR for a, b in zip(stamps, stamps[1:])):
        raise DataUnavailable(f"Missing/duplicate {label} intervals")


def validate_quote(data, now_ms):
    if data.get("source") != BASE:
        raise DataUnavailable("Unverified venue provenance")
    symbol = data["symbol"]
    fresh(data["collected_at_ms"], now_ms, 60_000, "collection")
    fresh(data["server_time_ms"], now_ms, 30_000, "server clock")
    if not 0 <= data["collected_at_ms"] - data["collection_started_ms"] <= 60_000:
        raise DataUnavailable("Collection was not temporally coherent")
    contract = data["contract"]
    if not contract or any(contract.get(k) != v for k, v in {
        "symbol": symbol, "contractType": "PERPETUAL", "quoteAsset": "USDT",
        "status": "TRADING",
    }.items()):
        raise DataUnavailable("Unverified active USDT perpetual contract")
    mark = data["mark"]
    if mark["symbol"] != symbol:
        raise DataUnavailable("Mark symbol mismatch")
    fresh(mark["time"], now_ms, 60_000, "mark")
    mark_price, index = number(mark["markPrice"], positive=True), number(mark["indexPrice"], positive=True)
    book = data["book"]
    fresh(book["T"], now_ms, 60_000, "order book")
    sides = {}
    for name, reverse in (("bids", True), ("asks", False)):
        rows = [(number(x[0], positive=True), number(x[1], positive=True)) for x in book[name]]
        if not rows or rows != sorted(rows, reverse=reverse) or len({x[0] for x in rows}) != len(rows):
            raise DataUnavailable("Empty, unsorted or duplicate order book")
        sides[name] = rows
    bid, ask = sides["bids"][0][0], sides["asks"][0][0]
    if bid >= ask:
        raise DataUnavailable("Crossed order book")
    funding_interval = number(data["funding_interval_hours"], positive=True)
    if funding_interval != int(funding_interval) or funding_interval > 8:
        raise DataUnavailable("Unverified funding interval")
    return {
        "bid": bid, "ask": ask, "mark": mark_price, "index": index,
        "basis_pct": (mark_price / index - 1) * 100,
        "funding_rate": number(mark["lastFundingRate"]),
        "next_funding_ms": int(mark["nextFundingTime"]),
        "funding_interval_ms": int(funding_interval) * HOUR,
        "spread_bps": (ask / bid - 1) * 10_000,
        "book_as_of_ms": int(book["T"]),
        "depth_imbalance": (sum(p*q for p,q in sides["bids"]) - sum(p*q for p,q in sides["asks"])) /
                           (sum(p*q for p,q in sides["bids"]) + sum(p*q for p,q in sides["asks"])),
    }


def features(data, now_ms):
    result = validate_quote(data, now_ms)
    symbol = data["symbol"]
    candles = sorted((x for x in data["klines"] if int(x[6]) < now_ms), key=lambda x: int(x[0]))
    if len(candles) < 170:
        raise DataUnavailable("Need 170 completed hourly candles")
    candles = candles[-170:]
    contiguous(candles, lambda x: x[0], "candle")
    if any(int(x[6]) != int(x[0]) + HOUR - 1 for x in candles):
        raise DataUnavailable("Unexpected candle duration")
    fresh(candles[-1][6], now_ms, HOUR + 600_000, "closed candle")
    for x in candles:
        o,h,l,c = [number(v, positive=True) for v in x[1:5]]
        volume = number(x[7])
        if min(o,c) < l or max(o,c) > h or volume < 0:
            raise DataUnavailable("Invalid OHLCV candle")
    oi = sorted(data["oi"], key=lambda x: int(x["timestamp"]))
    if len(oi) < 25:
        raise DataUnavailable("Need 25 hourly OI samples")
    oi = oi[-25:]
    contiguous(oi, lambda x: x["timestamp"], "OI")
    for row in oi:
        if row["symbol"] != symbol:
            raise DataUnavailable("OI symbol mismatch")
        number(row["sumOpenInterest"], positive=True)
    fresh(oi[-1]["timestamp"], now_ms, HOUR + 600_000, "OI")
    if int(oi[-1]["timestamp"]) != int(candles[-1][6]) + 1:
        raise DataUnavailable("OI and closed-candle windows are not aligned")
    taker = sorted((x for x in data["taker"] if int(x["timestamp"]) + HOUR <= now_ms), key=lambda x: int(x["timestamp"]))
    if len(taker) < 2:
        raise DataUnavailable("Need two completed taker intervals")
    taker = taker[-2:]
    contiguous(taker, lambda x: x["timestamp"], "taker")
    if int(taker[-1]["timestamp"]) != int(candles[-1][0]):
        raise DataUnavailable("Taker and candle windows are not aligned")
    for row in taker:
        if row["symbol"] != symbol:
            raise DataUnavailable("Taker symbol mismatch")
        number(row["buySellRatio"], positive=True)
    baseline = sum(number(x[7]) for x in candles[:-2]) / 7
    if baseline <= 0:
        raise DataUnavailable("Zero prior-seven-day volume baseline")
    volume = sum(number(x[7]) for x in candles[-2:])
    same_slot_mean = sum(sum(number(x[7]) for x in candles[168-24*d:170-24*d]) for d in range(1,8)) / 7
    result.update({
        "symbol": symbol,
        "oi_as_of_ms": int(oi[-1]["timestamp"]),
        **{f"oi_{h}h_pct": (number(oi[-1]["sumOpenInterest"]) / number(oi[-1-h]["sumOpenInterest"]) - 1) * 100 for h in (1,2,4,24)},
        "taker_ratios": [number(x["buySellRatio"]) for x in taker],
        "taker_as_of_ms": int(taker[-1]["timestamp"]) + HOUR,
        "previous_hour_high": number(candles[-1][2]),
        "previous_hour_low": number(candles[-1][3]),
        "price_2h_pct": (number(candles[-1][4]) / number(candles[-2][1]) - 1) * 100,
        "volume_2h_quote": volume,
        "mean_daily_volume_prior_7d": baseline,
        "volume_acceleration": 12 * volume / baseline,
        "volume_same_slot_ratio_7d": volume / same_slot_mean if same_slot_mean > 0 else None,
        "volume_as_of_ms": int(candles[-1][6]),
    })
    return result


def book_fill(data, side, quantity, residual_slippage_rate):
    quantity = number(quantity, positive=True)
    residual = number(residual_slippage_rate)
    if side not in ("buy", "sell") or not 0 <= residual < 1:
        raise DataUnavailable("Invalid simulated order")
    rows = data["book"]["asks" if side == "buy" else "bids"]
    left, cost = quantity, 0.0
    for raw_price, raw_size in rows:
        price, size = number(raw_price, positive=True), number(raw_size, positive=True)
        taken = min(left, size)
        cost += taken * price
        left -= taken
        if left <= quantity * 1e-12:
            break
    if left > quantity * 1e-12:
        raise DataUnavailable("Insufficient verified order-book depth")
    vwap = cost / quantity
    return vwap * (1 + residual if side == "buy" else 1 - residual)
