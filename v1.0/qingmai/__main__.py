"""A single hourly scan. Scheduling/publishing is intentionally external."""
import argparse
import fcntl
import hashlib
import json
import os
from pathlib import Path
import tempfile
import time

from .core import classify
from .market import PublicClient, features
from .paper import process


def atomic_write(path, value, expected_sha256):
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != expected_sha256:
        raise RuntimeError("State changed concurrently; reload and reconcile, never overwrite")
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as output:
            json.dump(value, output, ensure_ascii=False, indent=2, allow_nan=False)
            output.write("\n")
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def run(args, client=None, now=None):
    path = Path(args.state)
    client = client or PublicClient()
    now = now or (lambda: int(time.time() * 1000))
    # Shared lock + content CAS protect local concurrent writers. Remote writer
    # must additionally compare GitHub's original blob SHA when publishing.
    with open(str(path) + ".lock", "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        raw = path.read_bytes()
        expected = hashlib.sha256(raw).hexdigest()
        state = json.loads(raw)
        run_id = f"hourly:{now() // 3_600_000}"
        if run_id in state["runs"]:
            return {"status": "ALREADY_RECORDED", "run_id": run_id}
        data, errors, radar = {}, {}, {}
        # Do not report a fixture or old saved snapshot as a current venue quote.
        # This CLI only collects new public data; synthetic inputs live in tests.
        for symbol in args.symbols.split(","):
            symbol = symbol.strip().upper()
            try:
                snapshot = client.collect(symbol)
                data[symbol] = snapshot
                f = features(snapshot, now())
                radar[symbol] = {
                    "status": "VERIFIED", "features": f,
                    "repo_prototype_v1_label": classify(f["price_2h_pct"], f["oi_2h_pct"], f["volume_acceleration"], f["taker_ratios"][-1]),
                    "historical_pre_move_candidate": f["volume_acceleration"] >= 5 and f["oi_2h_pct"] >= 8 and abs(f["price_2h_pct"]) <= 5 and f["taker_ratios"][-1] > 1.3 and abs(f["funding_rate"]) <= 0.001,
                    "execution_authorized_by_radar": False,
                }
            except Exception as exc:
                # No fallback to aggregate prices, HTML, another venue or old data.
                errors[symbol] = f"{type(exc).__name__}: {exc}"
                radar[symbol] = {"status": "DATA_UNAVAILABLE", "detail": errors[symbol]}
        result, event = process(state, data, now(), run_id, execute=args.paper_execute, errors=errors)
        event["radar"] = radar
        # event is referenced by result, so finalize its digest after adding radar.
        from .paper import digest
        result["runs"][run_id] = digest(event)
        if args.record:
            atomic_write(path, result, expected)
        event["state_recorded_locally"] = args.record
        event["remote_persistence_verified"] = False
        return event


def main():
    parser = argparse.ArgumentParser(description="PAPER ONLY. No live mode or credentials.")
    parser.add_argument("--state", default="runtime/state.json")
    parser.add_argument("--symbols", default="KAIAUSDT,JCTUSDT,STRKUSDT")
    parser.add_argument("--record", action="store_true", help="Atomically save scan/state locally")
    parser.add_argument("--paper-execute", action="store_true", help="Enable only verified, recovered paper rules")
    parser.add_argument("--ui-observation", help="Inspect an official-UI market observation JSON; research only")
    args = parser.parse_args()
    if args.ui_observation:
        if args.record or args.paper_execute:
            parser.error("UI observations are research only; no ledger write or execution")
        from .ui_research import inspect_observation
        print(json.dumps(inspect_observation(json.loads(Path(args.ui_observation).read_text())), ensure_ascii=False, indent=2))
        return
    if args.paper_execute and not args.record:
        parser.error("--paper-execute requires --record; never claim unpersisted fills")
    print(json.dumps(run(args), ensure_ascii=False, indent=2, allow_nan=False))


if __name__ == "__main__":
    main()
