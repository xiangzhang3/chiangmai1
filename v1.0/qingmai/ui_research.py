"""Import official website observations for research only, never paper fills."""
from datetime import datetime
import re
from .market import DataUnavailable, number


def inspect_observation(record):
    symbol = record["symbol"]
    if not re.fullmatch(r"[A-Z0-9]{2,30}USDT", symbol):
        raise DataUnavailable("Invalid observation symbol")
    if record["source_url"] != f"https://www.binance.com/en/futures/{symbol}":
        raise DataUnavailable("Not the approved official symbol page")
    observed = datetime.fromisoformat(record["observed_at"].replace("Z", "+00:00"))
    if observed.tzinfo is None:
        raise DataUnavailable("Observation time requires explicit timezone")
    allowed = {
        "last_price", "mark_price", "index_price", "funding_rate",
        "funding_interval_hours", "open_interest_notional_usdt",
    }
    fields = record.get("fields", {})
    if set(fields) - allowed:
        raise DataUnavailable("Unexpected fields; this schema contains market data only")
    values = {k: number(v, positive=(k != "funding_rate")) for k,v in fields.items()}
    return {
        "status": "RESEARCH_ONLY", "symbol": symbol,
        "source_url": record["source_url"], "observed_at": observed.isoformat(),
        "fields": values, "execution_eligible": False,
        "reason": "Rendered observations are not a complete verified execution snapshot",
        "missing_execution_evidence": [
            "Verified venue event times for current bid/ask depth and mark",
            "25 continuous hourly OI quantity samples, not USD notional",
            "Two completed aligned hourly taker buy/sell ratios",
            "170 continuous completed hourly OHLC and quote-volume candles",
            "Verified funding schedule and any required settlement history",
            "Verified account state and one durable state writer",
        ],
    }
