# 小哈 / 清迈1号 — 执行升级记录 (2026-10-10)

## Verified current state
- Existing prototype: Binance Futures REST / OI & volume acceleration / signal classification / paper-account model / unit tests.
- Created JCT-A01 independent 1,000 USDT paper ledger. No prior trades imported or fabricated.
- Added quote timestamp/price/source guardrails: stale >10 minutes, missing attribution, missing durable ledger => no simulated execution.
- Added five additional guardrail unit tests (not CI-verified).
- JCT hourly ChatGPT automation aligned to the persistent ledger. This is NOT an always-on deployed service.
- Existing STRK hourly, Binance universe 2-hourly, ARC hourly automations were found active; no runtime code changes to them in this commit.

## Priorities
P0: Prove live exchange data connectivity and alternative feed, with authoritative timestamps.
P0: Run test suite and add CI. Reconcile PaperAccount simulation balance/equity treatment and enforce position risk limits.
P0: Record verified fill snapshots and durable idempotent append-only trades, backfill only from actual records.
P1: Each strategy account isolated; track NAV / realized vs unrealized PnL / drawdown / win-rate / net PnL / benchmark.
P1: Persist radar scans + market data snapshots for genuine forward-test accuracy, not hindsight win-rates.
P1: Add error metrics, stale-data alerts, and daily reconciliation.
P2: Add research-only agent orchestration across watchlists and project knowledge.
P2: Human sign-off required before any real-money execution.

## Rule
Never present scheduling as confirmed execution, unverified quotes as current, paper fills as real orders, or hypothetical PnL as actual returns. Failed APIs must lead to fallback attempts or explicit unverifiable status rather than fabricated figures.
