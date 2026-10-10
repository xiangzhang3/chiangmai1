# Official website research observations

Public signed-out Binance symbol pages can sometimes be read even when the API
route is unavailable. Only use the permitted rendered website. Never bypass an
API access denial or probe its blocked requests through another route.

The research-only import path is:

```sh
python -m qingmai --ui-observation runtime/ui_observations/observation.json
```

The JSON shape is:

```json
{
  "symbol": "KAIAUSDT",
  "source_url": "https://www.binance.com/en/futures/KAIAUSDT",
  "observed_at": "2026-10-10T16:15:32Z",
  "fields": {}
}
```

The timestamp above illustrates schema only; it is not an executed observation.
Use the actual UTC capture time and the actual symbol page. Supported numeric
market fields are `last_price`, `mark_price`, `index_price`, `funding_rate`
(decimal per interval, not percent), `funding_interval_hours`, and
`open_interest_notional_usdt`. Keep a screenshot/source reference separately.
Never include account positions, balances, credentials or other private data.

Observation/capture time is not venue event time. Do not infer a timezone from a
rendered clock alone. USD OI cannot replace OI quantity history. A visible price
or funding value alone cannot establish entry eligibility. This import emits
RESEARCH_ONLY and `execution_eligible: false` unconditionally, cannot write the
ledger, and cannot open/close a paper position. A complete future UI data bridge
needs a separately reviewed adapter with timestamped depth, hourly OI quantity,
taker/OHLCV histories, funding, provenance and account-state validation.
