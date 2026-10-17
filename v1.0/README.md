# CHIANGMAI1 v1.0: paper-only recovery

Public Binance USD-M data, versioned research signals, and independently recorded
paper accounts. This is an unvalidated research prototype. Test success is not
evidence of trading profitability. No API keys, private account reads, order
endpoints, real-money trades, or live mode exist in the recovered runner.

## Status and source of truth

- Recovery source: upstream `e81c23b2d6a05f70e1b50243612804eaae8b578f`.
- `qingmai/sim_accounts/KAIA-A01.json` is an unchanged legacy checkpoint. It
  records a flat 1,000 USDT account with no historical fills. Do not rewrite it.
- `runtime/state.json` is the proposed single runtime source of truth, importing
  that checkpoint and retaining its full contents and SHA-256. Until this file
  and the runner are published and a durable writer is verified, recovery is
  local only, not an active deployment.
- KAIA-A01: Binance KAIAUSDT, 1x maximum, first tranche at most 300 USDT, planned
  stop loss including model costs at most approximately 10 USDT.
- JCT-A01: authorized paper budget 1,000 USDT, but prior account state is unknown.
  `ACCOUNT_STATE_UNVERIFIED`; cash/equity are null, never reset to 1,000.
- JCT-P01-20261010: expressly approved NEW prospective 1,000 USDT paper account,
  created 2026-10-10T16:36:27Z. Flat, no fills; does not inherit JCT-A01 history.
- STRK and other symbols can be researched but have no invented trading budget.
- Freqtrade and VectorBT were historically proposed and remain unintegrated.
  No third-party strategy engine is installed by this patch.

## Run and test

Python 3.10+ standard library only. Run from this directory:

```sh
python -m unittest discover -s tests -v
python -m qingmai                         # fresh-data scan, no state changes
python -m qingmai --record                # record observations locally
python -m qingmai --record --paper-execute # eligible paper-only execution
```

All tests use synthetic, clearly labelled fixtures and never contact an exchange.
Do not mix fixture outputs into the runtime ledger. The CLI has no saved-snapshot
execution input: every eligible fill requires newly collected venue data.

The public API must actually be reachable from the execution environment. A
blocked venue, HTTP 429, incomplete history, stale/future timestamp, mismatched
symbol or inactive contract means ABSTAIN. Do not bypass an access restriction
or substitute CoinGecko aggregate prices, website snippets, another venue or old
snapshots as Binance executable quotes. The present runner could not obtain a complete
Binance API signal/quote set; no successful API scan or trade is claimed. Public
Binance website observations are research only until their required timestamps,
OI/taker intervals and executable depth can be ingested and verified.

## Recovered strategy and explicit refinements

`kaia-oi-breakout-v1.1-recovery` operationalizes the historical long trigger:
quantity-based OI1h > 2%, two completed hourly taker ratios > 1.10, current bid
above the last completed hour's high. The historical lookback for "persistent" was not recovered. This prospective
version conservatively defines it as two closed intervals. Structural stop uses that hour's low, frozen at entry.
An observed stop breach, or negative OI1h with taker < 1 and falling versus the
previous hour, exits at the current verified bid-book fill. There is no invented
short-entry or take-profit rule.

Conservative new execution gates are separately identified refinements: spread
<= 20 bps, absolute mark/index basis <= 1%, absolute per-interval funding rate
<= 0.1%. They are safety filters, not validated alpha or original verbatim rules.
The independent historical research candidate uses volume >= 5x, OI2h >= 8%,
absolute price2h <= 5%, taker > 1.3 and moderate funding. It is labelled separately
from the repository's older 5% OI / 3% price prototype classifier. Neither radar
label independently authorizes an order. Other historical modules need precise,
versioned entry/exit rules, budgets and out-of-sample evaluation before execution.

Volume acceleration = completed latest two hours' quote volume x 12 / mean daily
quote volume over the preceding seven days, excluding the signal window.
The same-slot ratio compares that two-hour window to its seven preceding daily
counterparts. OI uses contract quantity, not price-inflated USD value. All hourly
intervals must be continuous and OI/taker/candles temporally aligned.

## New prospective JCT rule

`jct-oi-volume-breakout-p1-v0.1` is a conservative new trial definition, not a
recovered historical strategy. It reuses the versioned long-side OI/taker/high
breakout and structural-low/reversal exit, with an additional volume-acceleration
>=2x gate. Maximum leverage remains 1x, first notional <=100 USDT and planned
stop risk <=5 USDT. No short entries or scale-ins. The separate JCT-P01-20261010
account begins with explicitly approved 1,000 USDT virtual capital, without
restoring or changing the unknown JCT-A01 account. Account creation is not a fill,
and this implementation does not establish a continuously deployed runner.

## Costs, fills and evaluation limits

- Buy across visible asks and sell across visible bids for depth-weighted VWAP;
  abstain on insufficient depth. Add adverse 5 bps residual slippage per side.
- Fee assumption: 5 bps of fill notional per side, explicitly a model assumption,
  not a verified user's Binance fee tier. Spread is embedded in bid/ask fills;
  slippage is already embedded in price and must not be subtracted twice.
- Settle observed funding using the venue's actual historical funding rate and
  settlement mark. Missing expected funding blocks accounting, never assumed 0. The public funding
  interval is tracked; a schedule change is quarantined pending reconciliation.
- Track each account's net closed P&L, net equity return, closed-trade win rate,
  profit factor, holding time, consecutive losses, fees, funding and slippage.
  With no closed trades, win rate and profit factor are null.
- Drawdown is sampled at successful runs, including open mark-to-market P&L.
  It is not tick-level or intrahour max drawdown. Open equity does not deduct
  hypothetical closing costs. Stale equity is timestamped and flagged unverified.
- An hourly observer cannot guarantee a 10 USDT realized loss cap. Gaps, adverse
  execution and funding can exceed planned risk. Stops are evaluated only at an
  observed fresh quote; never backfill a stop fill at a missed historical price.
- Synthetic fills do not establish executable profitability. No win rate or
  profitable strategy is claimed from the current empty historical ledger.

## Durable hourly operation

The runner is deliberately not a daemon and creates no schedule. See
`OPERATIONS.md` for a single-writer, SHA-checked publication protocol. Local
atomic writes are not proof of remote persistence. No GitHub Actions permissions,
tokens, paid services or recurring jobs are created by this patch.

Official market-data schema:
https://developers.binance.com/en/docs/catalog/core-trading-derivatives-trading-usd-s-m-futures/api/rest-api/market-data

## Prospective rendered-UI shadow assessment

`qingmai/ui_candidate.py` is an isolated, non-executing candidate for assessing
public rendered observations. It cannot write an account and is not used by the
default paper runner. Even accepted shadow evidence always reports
`execution_eligible: false`. Its two-capture liveness limits, displayed-value
rounding bounds, and chart-offset time conversion are explicit prospective
modelling assumptions. Derived UI timestamps are never labelled exchange event
timestamps. A two-interval taker lookback is a new versioned definition, not a
claim about the original strategy's unspecified persistence period.

The candidate requires advancing visible trade times and changing book data,
correct symbol/perpetual labels, an explicit UTC-offset chart clock, fresh bounded
captures, quantity OI, two contiguous completed taker windows, and the aligned
completed candle. Unsupported/missing data yields INCOMPLETE. UI fields update
asynchronously; liveness does not prove an atomic or executable exchange quote.
Displayed quantities are discounted by one whole displayed unit, and ask/bid
prices are conservatively widened by one displayed unit. These are paper-model
assumptions, not verified exchange UI rounding guarantees. Funding settlement
coverage, an independently validated collector and explicit activation remain
required before any prospective execution bridge.

## 1h/4h prospective versions and the flat-account UI pilot

The additive `kaia-oi-breakout-v1.2-1h4h` and
`jct-oi-volume-breakout-p1-v0.2-1h4h` versions require two completed aligned
four-hour candles: the latest must close above its open and the preceding close.
They preserve existing leverage/notional/risk caps, add a 10% participation cap on
the smaller visible bid/ask quantity, and a 72-hour maximum-hold backstop at the
next valid observation. There is no minimum hold; stops/invalidation exit earlier.
These indicator details are prospective engineered definitions. Account migration
is audited and never rewrites historic fills or resets balances.

`--ui-pilot <normalized.json> --record` is a separate flat KAIA decision-only path.
It validates the rendered-UI liveness and closed1h/4h evidence, atomically records
NO_TRADE/ABSTAIN/ENTRY_CANDIDATE_BLOCKED, and cannot create fills or alter accounts.
It does not bypass the API validator or synthesize venue timestamps. Positive UI
execution remains unavailable until the source-time/funding accounting bridge is
reviewed. See [OPERATIONS.md](OPERATIONS.md) for state CAS and
[UI_PAPER_BRIDGE.md](UI_PAPER_BRIDGE.md) for the exact remaining conditions.
