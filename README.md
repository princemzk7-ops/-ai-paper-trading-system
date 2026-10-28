# AI Paper Trading System (US Stocks + Bybit Crypto)

**Paper trading only.** This starter project does not send real orders and does not need API keys.
It scans:
- Bybit USDT perpetual crypto symbols using public market data
- A small configurable list of US stocks using Yahoo Finance data

It calculates simple RSI + moving-average signals, simulated entries, ATR-based stop-loss and 1R take-profit. This is a learning/testing starter, not a profitable strategy guarantee or financial advice.

## Run on GitHub Actions (mobile-friendly)
1. Create a GitHub repository, e.g. `ai-paper-trading-system`.
2. Upload all files from this ZIP, including the hidden `.github` folder.
3. Open **Actions** and enable workflows if GitHub asks.
4. Run **Paper Trading Scanner** manually using **Run workflow**.
5. Read the log output. The workflow runs a one-time scan and exits; it does not stay running forever.

## Run locally
Python 3.11+
```bash
pip install -r requirements.txt
python paper_bot.py
```

## Configure
Edit `config.json`:
- `crypto_symbols`: Bybit symbols like `BTC/USDT:USDT`, `ETH/USDT:USDT`
- `stock_symbols`: US tickers like `AAPL`, `MSFT`, `NVDA`
- `risk_pct`: simulated risk per trade
- `max_symbols`: limit the scan size

## Safety
- No exchange keys are used.
- No live orders are placed.
- Do not paste API keys into GitHub files or chat.
- Treat signals as experiments; paper-test for weeks and include fees/slippage before considering anything live.
