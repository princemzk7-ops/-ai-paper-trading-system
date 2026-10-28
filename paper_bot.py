import json
import math
import os
from datetime import datetime, timezone

import ccxt
import numpy as np
import pandas as pd
import yfinance as yf

ROOT = os.path.dirname(os.path.abspath(__file__))
with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
    CFG = json.load(f)

def rsi(series, period=14):
    delta = series.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/period, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/period, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def atr(df, period=14):
    prev_close = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - prev_close).abs(),
        (df["low"] - prev_close).abs()
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def signal_for(df, label):
    if df is None or len(df) < 40:
        return None
    df = df.copy().dropna()
    if len(df) < 30:
        return None
    close = df["close"]
    rr = rsi(close, int(CFG["rsi_period"]))
    aa = atr(df, int(CFG["atr_period"]))
    fast = close.rolling(9).mean()
    slow = close.rolling(21).mean()
    # Use only the most recent fully formed candle provided by data source.
    price = float(close.iloc[-2])
    rv = float(rr.iloc[-2])
    av = float(aa.iloc[-2])
    f = float(fast.iloc[-2])
    s = float(slow.iloc[-2])
    if not all(math.isfinite(x) for x in [price, rv, av, f, s]) or av <= 0:
        return None
    side = None
    if f > s and rv >= 52:
        side = "LONG"
    elif f < s and rv <= 48:
        side = "SHORT"
    if not side:
        return None
    stop_dist = av * float(CFG["atr_stop_multiple"])
    stop = price - stop_dist if side == "LONG" else price + stop_dist
    target = price + stop_dist * float(CFG["reward_r"]) if side == "LONG" else price - stop_dist * float(CFG["reward_r"])
    balance = float(CFG["paper_balance_usdt"])
    risk_cash = balance * float(CFG["risk_pct"])
    qty = risk_cash / stop_dist if stop_dist > 0 else 0
    return {
        "market": label, "side": side, "price": price,
        "rsi": round(rv, 2), "atr": round(av, 6),
        "stop_loss": round(stop, 6), "take_profit": round(target, 6),
        "risk_budget": round(risk_cash, 2), "simulated_qty": round(qty, 6)
    }

def fetch_crypto():
    results = []
    ex = ccxt.bybit({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    try:
        markets = ex.load_markets()
        symbols = CFG["crypto_symbols"][:int(CFG["max_symbols"])]
        for sym in symbols:
            if sym not in markets:
                print(f"[CRYPTO] Skip {sym}: symbol not found on public Bybit markets.")
                continue
            try:
                rows = ex.fetch_ohlcv(sym, timeframe=CFG["timeframe"], limit=100)
                df = pd.DataFrame(rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
                idea = signal_for(df, f"BYBIT {sym}")
                if idea: results.append(idea)
                else: print(f"[CRYPTO] {sym}: no signal")
            except Exception as e:
                print(f"[CRYPTO] {sym}: data error: {e}")
    finally:
        ex.close()
    return results

def fetch_stocks():
    results = []
    for sym in CFG["stock_symbols"][:int(CFG["max_symbols"])]:
        try:
            raw = yf.download(sym, period=CFG["stock_period"], interval=CFG["stock_interval"],
                              auto_adjust=False, progress=False, threads=False)
            if raw is None or raw.empty:
                print(f"[STOCK] {sym}: no data (market may be closed or Yahoo data unavailable)")
                continue
            if isinstance(raw.columns, pd.MultiIndex):
                raw.columns = raw.columns.get_level_values(0)
            raw = raw.rename(columns={c: str(c).lower() for c in raw.columns})
            needed = ["open", "high", "low", "close"]
            if not all(c in raw.columns for c in needed):
                print(f"[STOCK] {sym}: unexpected data columns")
                continue
            df = raw[needed].dropna()
            idea = signal_for(df, f"US STOCK {sym}")
            if idea: results.append(idea)
            else: print(f"[STOCK] {sym}: no signal")
        except Exception as e:
            print(f"[STOCK] {sym}: data error: {e}")
    return results

def main():
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    print("=" * 70)
    print("AI PAPER TRADING SCANNER — NO REAL ORDERS")
    print("Scan time:", now)
    print("Paper balance:", CFG["paper_balance_usdt"], "(simulated units)")
    print("Risk budget per idea:", round(CFG["paper_balance_usdt"] * CFG["risk_pct"], 2))
    print("=" * 70)
    all_ideas = []
    try:
        all_ideas.extend(fetch_crypto())
    except Exception as e:
        print("[CRYPTO] Scanner error:", e)
    try:
        all_ideas.extend(fetch_stocks())
    except Exception as e:
        print("[STOCK] Scanner error:", e)
    if not all_ideas:
        print("\nNo signals this run. This is normal; do not force trades.")
    else:
        print("\nPAPER SIGNALS (not orders):")
        for x in all_ideas:
            print(json.dumps(x, ensure_ascii=False))
    print("\nFinished. No orders placed; no API keys used.")

if __name__ == "__main__":
    main()
