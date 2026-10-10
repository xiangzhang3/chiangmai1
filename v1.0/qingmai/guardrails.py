"""Strict validation for timestamped paper-trading snapshots (no live orders)."""
from datetime import datetime, timezone

MAX_AGE_SECONDS = 600

def validate_quote(quote, now=None):
    """Raise on missing/stale/invalid prices. No fallback to guessed numbers."""
    if not isinstance(quote, dict):
        raise ValueError("Missing quote")
    if quote.get("source") in (None, ""):
        raise ValueError("Unattributed quote")
    try:
        price = float(quote["price"])
        at = datetime.fromisoformat(quote["as_of"].replace("Z", "+00:00"))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Bad quote format") from exc
    if at.tzinfo is None or price <= 0:
        raise ValueError("Invalid price or timezone")
    current = now or datetime.now(timezone.utc)
    age = (current - at).total_seconds()
    if age < -60 or age > MAX_AGE_SECONDS:
        raise ValueError("Stale or future quote")
    return price

def decision_gate(quote, ledger_persistable, now=None):
    try:
        validate_quote(quote, now)
    except ValueError as exc:
        return {"allow_paper_execution": False, "reason": str(exc)}
    if not ledger_persistable:
        return {"allow_paper_execution": False, "reason": "Durable ledger unavailable"}
    return {"allow_paper_execution": True, "reason": "Quote verified; risk and signal checks still required"}
