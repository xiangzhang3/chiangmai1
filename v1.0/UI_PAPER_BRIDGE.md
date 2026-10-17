# CHIANGMAI1 observed-quote paper bridge

Current implemented stage: `binance-rendered-flat-pilot-v0.1`. This atomically records verified
flat-account decisions locally with evidence. Remote publication requires a
separate authorized branch compare-and-swap and readback. It
cannot create fills. The API adapter and shadow validator remain unchanged in
source identity and execution permissions.

## Evidence contract

- Exact selected venue/instrument/perpetual identity, official page, raw UI labels
  and local capture start/end for each field.
- Two advancing tape and numerically changing book observations 5–30 seconds
  apart. Each capture <=10 seconds; latest <=30 seconds at evaluation.
- Visible chart timezone and progressing clock consistent with capture UTC.
  Derived label times are never called exchange event timestamps.
- Latest hourly quantity OI endpoints, two completed hourly taker intervals,
  previous completed hourly candle, two completed four-hour candles. Fields must
  have completed before capture started and history must be <=10 minutes old.
- Rounded display prices/quantities use one full displayed unit of adverse bound.
  A displayed book is an observation, not a promise of executable liquidity.
- Distinct source model, evidence digest, strategy version, decision time,
  signal completeness and blockers persisted for every prospective decision.

## Before allowing a modeled position

The bridge must additionally validate funding history and ownership across each
settlement. The predicted current-rate widget is not a settled funding record.
Official historical rows provide rate, funding interval and historical mark price;
the table's displayed settlement time currently has no explicit timezone.

A rollover observation may bound the appearance of a new dated row and corroborate
an offset. Retain before/after capture times, raw rows, chart-clock evidence, the
mapping assumption and uncertainty interval. Do not replace those fields with a
fabricated exact exchange timestamp. A correlation alone is not proof of zero
latency or historical schedule continuity.

For a later executable paper model, coverage must include every settlement the
position could own, handle duplicate/missing rows and interval changes, and avoid
assigning a funding charge when entry/exit lies inside unresolved time uncertainty.
A missing cost must stay pending/unfinalized, never become zero. Do not claim exact
net returns until the cost ledger is reconciled. Risk exits must not be silently
suppressed merely to manufacture complete performance numbers. These cases require
separate accounting design, synthetic regression tests and independent review
before positive-entry activation.

Prospective fills, once activated, must be explicitly modeled using conservative
rounded-book bounds, adverse slippage, fees, existing risk/notional/leverage caps,
observed depth participation and source-time uncertainty. No missed historical fill
may be backfilled. No real account or exchange order endpoint is part of this work.
