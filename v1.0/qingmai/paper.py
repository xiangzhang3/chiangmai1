"""Versioned, 1x paper execution and independent-account evaluation."""
from copy import deepcopy
import hashlib
import json
import math
from .market import DataUnavailable, book_fill, features, number, validate_quote

STRATEGY_VERSION = "kaia-oi-breakout-v1.1-recovery"


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


def recovered_state(legacy):
    """Import only the verified flat KAIA ledger. Never reset an unknown account."""
    s = legacy["state"]
    if (legacy["account_id"] != "KAIA-A01" or legacy["mode"] != "paper_only" or
        legacy["instrument"] != "KAIAUSDT" or legacy["initial_balance"] != 1000 or
        s["cash"] != 1000 or s["position_side"] != "FLAT" or
        s["equity"] != 1000 or s["average_entry_price"] is not None or
        any(s[key] != 0 for key in ("position_quantity", "position_notional", "realized_pnl", "unrealized_pnl", "fees_paid", "funding_paid", "slippage_paid")) or legacy["transactions"]):
        raise ValueError("Legacy account is not the verified flat recovery checkpoint; reconcile manually")
    return {
        "schema_version": 2, "mode": "paper_only", "revision": 0,
        "legacy_source_sha256": digest(legacy), "legacy_checkpoint": deepcopy(legacy),
        "accounts": {
            "KAIA-A01": {
                "symbol": "KAIAUSDT", "strategy_version": STRATEGY_VERSION,
                "status": "VERIFIED", "initial_balance": 1000.0, "cash": 1000.0,
                "equity": 1000.0, "peak_equity": 1000.0, "max_drawdown_pct": 0.0,
                "position": None, "trades": [], "fees_paid": 0.0, "funding_paid": 0.0,
                "slippage_paid": 0.0, "equity_as_of_ms": None,
            },
            "JCT-A01": {
                "symbol": "JCTUSDT", "strategy_version": None,
                "status": "ACCOUNT_STATE_UNVERIFIED", "authorized_budget": 1000,
                "cash": None, "equity": None, "position": None, "trades": None,
                "note": "Budget is not a recovered balance. Prior positions and fills are unknown. No reset or backfill.",
            },
        }, "runs": {}, "events": [], "market_evidence": {},
    }


def metrics(account):
    if account["status"] != "VERIFIED":
        return {"status": account["status"], "net_return_pct": None, "win_rate": None}
    trades = account["trades"]
    wins = sum(t["net_pnl"] > 0 for t in trades)
    gross_wins = sum(max(t["net_pnl"], 0) for t in trades)
    gross_losses = -sum(min(t["net_pnl"], 0) for t in trades)
    current_losses = max_losses = 0
    for trade in trades:
        current_losses = current_losses + 1 if trade["net_pnl"] < 0 else 0
        max_losses = max(max_losses, current_losses)
    return {
        "status": "NO_CLOSED_TRADES" if not trades else "PAPER_ONLY",
        "strategy_version": account["strategy_version"],
        "closed_trades": len(trades), "win_rate": wins / len(trades) if trades else None,
        "profit_factor": gross_wins / gross_losses if gross_losses else None,
        "max_consecutive_losses": max_losses,
        "closed_net_pnl": sum(t["net_pnl"] for t in trades),
        "net_return_pct": (account["equity"] / account["initial_balance"] - 1) * 100,
        "cash": account["cash"], "equity": account["equity"],
        "equity_as_of_ms": account["equity_as_of_ms"],
        "max_sampled_drawdown_pct": account["max_drawdown_pct"],
        "fees_paid": account["fees_paid"], "funding_paid": account["funding_paid"],
        "slippage_paid": account["slippage_paid"],
        "mean_holding_hours": sum(t["holding_hours"] for t in trades) / len(trades) if trades else None,
        "profitability_established": False,
    }


def mark_equity(account, mark, now_ms):
    p = account["position"]
    unrealized = (mark - p["entry"]) * p["quantity"] if p else 0.0
    account["equity"] = account["cash"] + unrealized
    account["peak_equity"] = max(account["peak_equity"], account["equity"])
    account["max_drawdown_pct"] = max(account["max_drawdown_pct"],
        (1 - account["equity"] / account["peak_equity"]) * 100)
    account["equity_as_of_ms"] = now_ms


def settle_funding(account, data, now_ms):
    p = account["position"]
    if p is None or now_ms < p["next_funding_ms"]:
        return
    rows = sorted(data["funding"], key=lambda x: int(x["fundingTime"]))
    if len({int(row["fundingTime"]) for row in rows}) != len(rows):
        raise DataUnavailable("Duplicate funding settlement timestamps")
    rows = [x for x in rows if p["next_funding_ms"] <= int(x["fundingTime"]) <= now_ms]
    interval = p["funding_interval_ms"]
    if int(data["funding_interval_hours"])*3_600_000 != interval:
        raise DataUnavailable("Funding schedule changed; reconcile before accounting")
    expected = list(range(p["next_funding_ms"], now_ms+1, interval))
    if [int(row["fundingTime"]) for row in rows] != expected:
        raise DataUnavailable("Settled funding history is missing; net accounting blocked")
    upcoming = int(data["mark"]["nextFundingTime"])
    if not expected or upcoming != expected[-1] + interval:
        raise DataUnavailable("Funding schedule coverage is unverified")
    for row in rows:
        if row["symbol"] != account["symbol"]:
            raise DataUnavailable("Funding symbol mismatch")
        charge = p["quantity"] * number(row["markPrice"], positive=True) * number(row["fundingRate"])
        account["cash"] -= charge
        account["funding_paid"] += charge
        p["funding_paid"] += charge
    p["next_funding_ms"] = upcoming


def evaluate(account, data, now_ms, execute):
    """Long-side recovered rule only; short logic remains research, not invented."""
    if account["status"] != "VERIFIED":
        return {"action": "ABSTAIN", "reason": account["status"]}
    if data["symbol"] != account["symbol"]:
        raise DataUnavailable("Account symbol mismatch")
    if account.get("equity_as_of_ms") is not None and now_ms < account["equity_as_of_ms"]:
        raise DataUnavailable("Observation predates account state")
    if account.get("position") and now_ms < account["position"]["opened_at_ms"]:
        raise DataUnavailable("Observation predates position entry")
    quote = validate_quote(data, now_ms)
    settle_funding(account, data, now_ms)
    p = account["position"]
    # Fresh bid can trigger a structural stop even if OI history is unavailable.
    try:
        f = features(data, now_ms)
    except (ValueError, KeyError, TypeError, IndexError) as exc:
        if not p or quote["bid"] > p["stop"]:
            raise DataUnavailable(str(exc)) from exc
        f = quote
    mark_equity(account, quote["mark"], now_ms)
    fee_rate, residual = 0.0005, 0.0005  # Explicit model assumptions, not claimed venue tier.
    result = {"action": "HOLD" if p else "NO_TRADE", "features": f}
    if p:
        stop = quote["bid"] <= p["stop"]
        reversal = f.get("oi_1h_pct", 0) < 0 and f.get("taker_ratios", [1,1])[-1] < 1 and f.get("taker_ratios", [1,1])[-1] < f.get("taker_ratios", [1,1])[-2]
        if not (stop or reversal):
            return {**result, "reason": "Position remains within recovered invalidation rules"}
        if not execute:
            return {**result, "action": "EXIT_SIGNAL", "reason": "Observed structural stop" if stop else "OI reversal with stronger selling"}
        fill = book_fill(data, "sell", p["quantity"], residual)
        fee = fill * p["quantity"] * fee_rate
        gross = (fill - p["entry"]) * p["quantity"]
        slip = max(quote["bid"] - fill, 0) * p["quantity"]
        account["cash"] += gross - fee
        account["fees_paid"] += fee
        account["slippage_paid"] += slip
        trade = {**p, "exit": fill, "closed_at_ms": now_ms,
                 "gross_pnl": gross, "fees": p["entry_fee"] + fee,
                 "net_pnl": gross - p["entry_fee"] - fee - p["funding_paid"],
                 "holding_hours": (now_ms - p["opened_at_ms"]) / 3_600_000,
                 "slippage_paid": p["slippage_paid"] + slip,
                 "reason": "STRUCTURE_STOP_OBSERVED" if stop else "OI_TAKER_REVERSAL"}
        account["trades"].append(trade)
        account["position"] = None
        mark_equity(account, quote["mark"], now_ms)
        return {**result, "action": "PAPER_CLOSE", "trade": trade, "reason": trade["reason"]}
    if account["strategy_version"] != STRATEGY_VERSION:
        return {**result, "reason": "Unknown strategy version; no automatic migration"}
    qualifies = f["oi_1h_pct"] > 2 and min(f["taker_ratios"]) > 1.10 and f["bid"] > f["previous_hour_high"]
    if not qualifies:
        return {**result, "reason": "Need OI1h>2%, two closed taker intervals>1.10 and bid>prior1h high"}
    if f["spread_bps"] > 20 or abs(f["basis_pct"]) > 1 or abs(f["funding_rate"]) > 0.001:
        return {**result, "reason": "Recovery liquidity/basis/funding safety filter"}
    if f["next_funding_ms"] <= now_ms:
        raise DataUnavailable("Next funding timestamp is not in the future")
    stop = f["previous_hour_low"]
    if stop >= f["ask"]:
        raise DataUnavailable("No valid structural stop")
    # Reduce size until both conservative planned loss and 1x notional constraints pass.
    quantity = min(300.0, account["cash"] / (1 + fee_rate)) / (f["ask"] * (1 + residual))
    for _ in range(12):
        fill = book_fill(data, "buy", quantity, residual)
        exit_assumption = stop * (1 - residual)
        risk_per_unit = fill - exit_assumption + fee_rate * (fill + exit_assumption)
        limit = min(300.0 / fill, account["cash"] / (fill * (1 + fee_rate)), 10.0 / risk_per_unit)
        if quantity <= limit * (1 + 1e-12):
            break
        quantity = limit * (1 - 1e-9)
    else:
        raise DataUnavailable("Risk sizing failed to converge")
    if not math.isfinite(quantity) or quantity <= 0:
        raise DataUnavailable("No affordable quantity")
    entry = {"symbol": account["symbol"], "side": "long", "quantity": quantity,
             "entry": fill, "entry_fee": quantity * fill * fee_rate,
             "stop": stop, "planned_risk_usdt": risk_per_unit * quantity,
             "opened_at_ms": now_ms, "next_funding_ms": f["next_funding_ms"],
             "funding_interval_ms": f["funding_interval_ms"],
             "funding_paid": 0.0, "slippage_paid": max(fill - f["ask"], 0) * quantity,
             "strategy_version": STRATEGY_VERSION, "leverage_cap": 1}
    if not execute:
        return {**result, "action": "ENTRY_SIGNAL", "reason": "Recovered long signal", "proposed_position": entry}
    account["position"] = entry
    account["cash"] -= entry["entry_fee"]
    account["fees_paid"] += entry["entry_fee"]
    account["slippage_paid"] += entry["slippage_paid"]
    mark_equity(account, quote["mark"], now_ms)
    return {**result, "action": "PAPER_OPEN", "reason": "Recovered long signal", "position": deepcopy(entry)}


def process(state, market_by_symbol, now_ms, run_id, *, execute=False, errors=None):
    if state.get("mode") != "paper_only" or state.get("schema_version") != 2:
        raise ValueError("Unsupported state; live execution is not supported")
    if run_id in state["runs"]:
        return state, {"status": "ALREADY_RECORDED", "run_id": run_id}
    output = deepcopy(state)
    reports = {}
    for account_id, original in state["accounts"].items():
        account = deepcopy(original)
        data = market_by_symbol.get(account["symbol"])
        if account["status"] != "VERIFIED":
            result = {"action": "ABSTAIN", "reason": account["status"]}
        elif data is None:
            result = {"action": "ABSTAIN", "reason": "DATA_UNAVAILABLE", "detail": (errors or {}).get(account["symbol"], "No verified venue snapshot")}
        else:
            try:
                result = evaluate(account, data, now_ms, execute)
                output["accounts"][account_id] = account
            except (ValueError, KeyError, TypeError, IndexError, ZeroDivisionError) as exc:
                result = {"action": "ABSTAIN", "reason": "DATA_UNVERIFIED", "detail": str(exc)}
        result["account_id"] = account_id
        result["metrics"] = metrics(output["accounts"][account_id])
        result["equity_fresh"] = output["accounts"][account_id].get("equity_as_of_ms") == now_ms
        if data is not None:
            evidence_hash = digest(data)
            output["market_evidence"].setdefault(evidence_hash, data)
            result["evidence_sha256"] = evidence_hash
        reports[account_id] = result
    event = {"run_id": run_id, "observed_at_ms": now_ms, "paper_execution_enabled": execute, "accounts": reports}
    output["events"].append(event)
    output["runs"][run_id] = digest(event)
    output["revision"] += 1
    return output, event
