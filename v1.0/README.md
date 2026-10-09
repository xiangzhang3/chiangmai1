# 清迈1号 v1.0

Chiang Mai One: Binance Futures Money Radar, strategy research and paper-trading prototype.

本目录为独立的 v1.0 原型，不覆盖仓库已有内容。

## Components
- Binance public futures REST data adapter (connectivity depends on runtime/network)
- OI and volume acceleration calculations
- Pre-Move / Ignition preliminary rules
- Independent virtual strategy accounts, fee/slippage/funding assumptions
- SQLite persistence and basic tests

## Important
This is research software, not a validated profitable trading strategy. Do not use live exchange credentials or real capital. Backtesting, exchange connectivity and continuous paper trading are not yet deployed.

## Local start
```bash
pip install -r requirements.txt
python -m qingmai
python -m unittest discover -s tests
```
