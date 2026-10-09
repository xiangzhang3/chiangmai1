"""Chiang Mai One v1.0 — public futures data and paper strategy engine."""
from dataclasses import dataclass, field
from datetime import datetime, timezone
import requests

BASE = "https://fapi.binance.com"

def fetch(path, **params):
    response = requests.get(BASE + path, params=params, timeout=12)
    response.raise_for_status()
    return response.json()

def snapshot(symbol="STRKUSDT"):
    return {
        "symbol": symbol,
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "oi": fetch("/futures/data/openInterestHist", symbol=symbol, period="1h", limit=30),
        "klines": fetch("/fapi/v1/klines", symbol=symbol, interval="1h", limit=170),
        "mark": fetch("/fapi/v1/premiumIndex", symbol=symbol),
        "taker": fetch("/futures/data/takerlongshortRatio", symbol=symbol, period="1h", limit=3),
    }

def pct(now, before):
    return (now / before - 1) * 100 if before > 0 else None

def oi_change(now, before):
    """Use quantity rather than price-inflated USD notional."""
    return pct(float(now["sumOpenInterest"]), float(before["sumOpenInterest"]))

def volume_acceleration(last_2h_quote_volume, seven_day_mean_daily_quote_volume):
    return 12 * last_2h_quote_volume / seven_day_mean_daily_quote_volume if seven_day_mean_daily_quote_volume > 0 else None

def classify(price_2h, oi_2h, accel, taker):
    if accel is None or taker is None or oi_2h is None:
        return "UNVERIFIED"
    if accel >= 5 and oi_2h >= 5 and abs(price_2h) <= 3:
        return "PRE_MOVE"
    if accel >= 5 and oi_2h >= 5 and price_2h > 3 and taker > 1.1:
        return "IGNITION"
    if price_2h < -3 and oi_2h < -5:
        return "DELEVERAGING"
    if price_2h < -3 and oi_2h > 5:
        return "RISK_DIVERGENCE"
    return "WATCH"

def summarize_snapshot(data):
    oi = sorted(data["oi"], key=lambda p: int(p["timestamp"]))
    candles = sorted(data["klines"], key=lambda p: int(p[0]))
    if len(oi) < 25 or len(candles) < 170:
        return {"status": "UNVERIFIED", "reason": "Insufficient history"}
    complete = candles[:-1]
    baseline = sum(float(x[7]) for x in complete[-168:]) / 7
    volume_2h = sum(float(x[7]) for x in complete[-2:])
    result = {f"oi_{h}h_pct": oi_change(oi[-1], oi[-1-h]) for h in (1, 4, 24)}
    result.update(status="OK", oi_as_of_ms=int(oi[-1]["timestamp"]),
                  volume_2h_quote=volume_2h, mean_daily_volume_7d=baseline,
                  volume_acceleration=volume_acceleration(volume_2h, baseline),
                  volume_as_of_ms=int(complete[-1][6]))
    return result

@dataclass
class PaperAccount:
    strategy: str
    cash: float = 10000
    fee_rate: float = .0005
    slippage_rate: float = .0005
    trades: list = field(default_factory=list)
    position: dict | None = None

    def open(self, symbol, side, quantity, price):
        if self.position is not None or side not in ("long", "short") or min(quantity, price) <= 0:
            raise ValueError("Invalid order")
        fill = price * (1 + self.slippage_rate if side == "long" else 1 - self.slippage_rate)
        if fill * quantity > self.cash:
            raise ValueError("Insufficient virtual cash")
        fee = fill * quantity * self.fee_rate
        self.cash -= fee
        self.position = dict(symbol=symbol, side=side, quantity=quantity, entry=fill, entry_fee=fee)

    def close(self, price, funding=0):
        p = self.position
        if p is None or price <= 0:
            raise ValueError("Invalid close")
        fill = price * (1 - self.slippage_rate if p["side"] == "long" else 1 + self.slippage_rate)
        fee = fill * p["quantity"] * self.fee_rate
        gross = (fill - p["entry"]) * p["quantity"] * (1 if p["side"] == "long" else -1)
        net = gross - p["entry_fee"] - fee - funding
        self.cash += gross - fee - funding
        trade = {**p, "exit": fill, "fee": p["entry_fee"] + fee, "funding": funding, "pnl": net}
        self.trades.append(trade)
        self.position = None
        return trade

    def stats(self):
        wins = [t for t in self.trades if t["pnl"] > 0]
        losses = [t for t in self.trades if t["pnl"] < 0]
        profit = sum(t["pnl"] for t in wins)
        loss = -sum(t["pnl"] for t in losses)
        return {"strategy": self.strategy, "closed_trades": len(self.trades),
                "win_rate": len(wins) / len(self.trades) if self.trades else None,
                "profit_factor": profit / loss if loss else None,
                "net_pnl": sum(t["pnl"] for t in self.trades), "cash": self.cash}
