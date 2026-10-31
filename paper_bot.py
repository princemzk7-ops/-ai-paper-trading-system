
import json
import os
import time
from datetime import datetime, timezone

import ccxt
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))

with open(os.path.join(ROOT, "config.json"), encoding="utf-8") as f:
    CFG = json.load(f)

exchange = ccxt.bybit({
    "enableRateLimit": True,
    "options": {"defaultType": "swap"}
})

TIMEFRAME = CFG.get("timeframe", "5m")
BALANCE = float(CFG.get("paper_balance_usdt", 100))
RISK = float(CFG.get("risk_pct", 0.005))
ATR_MULT = float(CFG.get("atr_stop_multiple", 1.5))
REWARD = float(CFG.get("reward_r", 1.0))
MAX_POSITIONS = 3
STATE_FILE = os.path.join(ROOT, "paper_state.json")


def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, encoding="utf-8") as f:
            return json.load(f)
    return {"balance": BALANCE, "positions": [], "trades": []}


def save_state(state):
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2)


def indicators(df):
    delta = df["close"].diff()
    gain = delta.clip(lower=0).ewm(
        alpha=1 / 14, adjust=False
    ).mean()
    loss = (-delta.clip(upper=0)).ewm(
        alpha=1 / 14, adjust=False
    ).mean()

    rs = gain / loss.replace(0, float("nan"))
    df["rsi"] = 100 - (100 / (1 + rs))

    previous = df["close"].shift(1)
    tr = pd.concat([
        df["high"] - df["low"],
        (df["high"] - previous).abs(),
        (df["low"] - previous).abs()
    ], axis=1).max(axis=1)

    df["atr"] = tr.rolling(14).mean()
    return df


def get_signal(symbol):
    candles = exchange.fetch_ohlcv(
        symbol, timeframe=TIMEFRAME, limit=100
    )

    df = pd.DataFrame(
        candles,
        columns=["time", "open", "high", "low", "close", "volume"]
    )

    # Last candle may still be open. Use closed candles only.
    df = df.iloc[:-1].copy()
    df = indicators(df).dropna()

    if len(df) < 30:
        return None

    last = df.iloc[-1]
    previous = df.iloc[-2]

    # Approximation of RSI pivot breakout:
    # Break above/below the previous two-candle RSI range.
    pivot_high = df["rsi"].iloc[-4:-1].max()
    pivot_low = df["rsi"].iloc[-4:-1].min()

    side = None

    if previous["rsi"] <= pivot_high and last["rsi"] > pivot_high:
        side = "LONG"
    elif previous["rsi"] >= pivot_low and last["rsi"] < pivot_low:
        side = "SHORT"

    if side is None:
        return None

    entry = float(last["close"])
    atr_value = float(last["atr"])
    distance = atr_value * ATR_MULT

    if distance <= 0:
        return None

    if side == "LONG":
        stop = entry - distance
        target = entry + distance * REWARD
    else:
        stop = entry + distance
        target = entry - distance * REWARD

    risk_amount = BALANCE * RISK
    quantity = risk_amount / distance

    return {
        "symbol": symbol,
        "side": side,
        "entry": entry,
        "stop": stop,
        "target": target,
        "quantity": quantity,
        "risk_usdt": risk_amount,
        "time": datetime.now(timezone.utc).isoformat()
    }


def scan_symbols():
    print("Loading Bybit USDT perpetual markets...")
    markets = exchange.load_markets()

    tickers = exchange.fetch_tickers()
    candidates = []

    for symbol, market in markets.items():
        if not market.get("active"):
            continue
        if market.get("swap") and market.get("linear") and market.get("quote") == "USDT":
            ticker = tickers.get(symbol, {})
            volume = ticker.get("quoteVolume") or 0
            candidates.append((symbol, float(volume)))

    candidates.sort(key=lambda x: x[1], reverse=True)

    limit = int(CFG.get("max_symbols", 20))
    return [x[0] for x in candidates[:limit]]


def update_positions(state):
    remaining = []

    for position in state["positions"]:
        try:
            ticker = exchange.fetch_ticker(position["symbol"])
            price = float(ticker["last"])

            side = position["side"]
            stop_hit = (
                price <= position["stop"] if side == "LONG"
                else price >= position["stop"]
            )
            target_hit = (
                price >= position["target"] if side == "LONG"
                else price <= position["target"]
            )

            if stop_hit or target_hit:
                result = "STOP LOSS" if stop_hit else "TAKE PROFIT"
                print(result, position["symbol"], price)
                state["trades"].append({
                    **position,
                    "exit": price,
                    "result": result,
                    "exit_time": datetime.now(timezone.utc).isoformat()
                })
            else:
                remaining.append(position)

        except Exception as error:
            print("Position check error:", error)
            remaining.append(position)

    state["positions"] = remaining


def main():
    print("=" * 60)
    print("BYBIT USDT PERPETUAL — PAPER TRADING ONLY")
    print("Time:", datetime.now(timezone.utc).isoformat())
    print("Paper balance:", BALANCE, "USDT")
    print("No real orders or API keys are used.")
    print("=" * 60)

    state = load_state()
    update_positions(state)

    symbols = scan_symbols()
    print("Symbols selected:", len(symbols))

    for symbol in symbols:
        try:
            if len(state["positions"]) >= MAX_POSITIONS:
                break

            idea = get_signal(symbol)

            if not idea:
                continue

            already_open = any(
                p["symbol"] == symbol for p in state["positions"]
            )
            if already_open:
                continue

            state["positions"].append(idea)
            print("PAPER ENTRY:", json.dumps(idea))

        except Exception as error:
            print("Scan error", symbol, error)

        time.sleep(0.15)

    save_state(state)

    print("Open paper positions:", len(state["positions"]))
    print("Closed paper trades:", len(state["trades"]))
    print("Finished. No real orders placed.")


if __name__ == "__main__":
    main()
