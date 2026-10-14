"""Risk gates for paper trading only; does not place exchange orders."""
from math import isfinite

def size_position(equity, entry, stop, risk_budget=10.0, notional_cap=300.0, leverage=1.0):
    values=(equity,entry,stop,risk_budget,notional_cap,leverage)
    if not all(isinstance(v,(float,int)) and isfinite(v) for v in values):
        raise ValueError("Nonfinite input")
    if min(equity,entry,stop,risk_budget,notional_cap,leverage)<=0 or entry==stop:
        raise ValueError("Invalid sizing parameters")
    if leverage>1:
        raise ValueError("Leverage above paper mandate")
    distance=abs(entry-stop)
    # Round-trip execution costs must be included by callers when setting a risk budget.
    quantity=min(risk_budget/distance,notional_cap/entry,(equity*leverage)/entry)
    if quantity<=0:
        raise ValueError("No allocatable paper capacity")
    return {"quantity": quantity, "notional": quantity*entry,
            "stop_loss_budget_ex_fees":quantity*distance,
            "entry":entry,"stop":stop}

def verify_ledger(ledger):
    if ledger.get("mode")!="paper_only" or ledger.get("initial_equity",0)<=0:
        raise ValueError("Unsafe ledger configuration")
    if ledger.get("account_id") is None or not isinstance(ledger.get("trades"),list):
        raise ValueError("Malformed ledger")
    trade_ids=[t.get("trade_id") for t in ledger["trades"]]
    if any(not i for i in trade_ids) or len(trade_ids)!=len(set(trade_ids)):
        raise ValueError("Missing or duplicate trade IDs")
    return True

def realized_nav(ledger):
    verify_ledger(ledger)
    return float(ledger["initial_equity"])+float(ledger.get("realized_pnl",0))-float(ledger.get("fees_paid",0))-float(ledger.get("funding_paid",0))
