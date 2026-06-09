"""
ORB Live Scanner - Stocks + Nifty
Run after 9:30 AM to detect Opening Range Breakout signals
Usage: python orb_scanner.py [--watch] [--nifty-only] [--stocks-only]
"""
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
from fyers_data import _headers, resolve_symbol, HISTORY_URL, load_token, get_quote
import time
import sys
import os

# ── CONFIGURATION ──
STOCKS = [
    "RELIANCE", "INFY", "HDFCBANK", "SBIN", "ICICIBANK",
    "AXISBANK", "ITC", "TCS", "BAJFINANCE", "TATASTEEL",
]

INDEX = ["NIFTY50", "BANKNIFTY"]

ORB_CANDLES = 3  # First 3 five-min candles (9:15 to 9:30)
ATR_PERIOD = 14
RISK_REWARD = 2.0


def fetch_today_5m(symbol, days=5):
    """Fetch last few days of 5m data for a symbol."""
    sym = resolve_symbol(symbol, "NSE")
    end = datetime.now()
    start = end - timedelta(days=days)
    params = {
        "symbol": sym, "resolution": "5", "date_format": "1",
        "range_from": start.strftime("%Y-%m-%d"),
        "range_to": end.strftime("%Y-%m-%d"),
        "cont_flag": "1",
    }
    try:
        resp = requests.get(HISTORY_URL, headers=_headers(), params=params, timeout=10)
        data = resp.json()
        if data.get("s") == "ok" and data.get("candles"):
            df = pd.DataFrame(data["candles"], columns=["ts", "open", "high", "low", "close", "volume"])
            df["date"] = pd.to_datetime(df["ts"], unit="s")
            df["time"] = df["date"].dt.strftime("%H:%M")
            df["day"] = df["date"].dt.date
            return df
    except Exception as e:
        pass
    return None


def calc_atr(high, low, close, period=14):
    """Calculate ATR."""
    tr = []
    for i in range(len(high)):
        if i == 0:
            tr.append(high[i] - low[i])
        else:
            tr.append(max(high[i] - low[i], abs(high[i] - close[i-1]), abs(low[i] - close[i-1])))
    atr = pd.Series(tr).rolling(period).mean()
    return atr.values


def detect_orb(df, symbol):
    """
    Detect Opening Range Breakout for today.
    Returns signal dict or None.
    """
    if df is None or len(df) < 10:
        return None

    # Get today's data
    today = df["day"].max()
    today_df = df[df["day"] == today].reset_index(drop=True)

    if len(today_df) < ORB_CANDLES + 1:
        return None

    # Opening range = first N candles (9:15 to 9:30)
    orb_data = today_df.iloc[:ORB_CANDLES]
    orb_high = orb_data["high"].max()
    orb_low = orb_data["low"].min()
    orb_range = orb_high - orb_low

    if orb_range <= 0:
        return None

    # Calculate ATR from previous days for context
    prev_days = df[df["day"] < today]
    if len(prev_days) > ATR_PERIOD:
        atr_val = calc_atr(
            prev_days["high"].values[-100:],
            prev_days["low"].values[-100:],
            prev_days["close"].values[-100:],
            ATR_PERIOD
        )
        atr = atr_val[-1] if not np.isnan(atr_val[-1]) else orb_range
    else:
        atr = orb_range

    # Check for breakout in subsequent candles
    post_orb = today_df.iloc[ORB_CANDLES:]
    if len(post_orb) == 0:
        # ORB not yet formed (before 9:30)
        return {
            "symbol": symbol,
            "status": "WAITING",
            "orb_high": orb_high,
            "orb_low": orb_low,
            "orb_range": orb_range,
            "message": f"ORB forming... High={orb_high:.2f} Low={orb_low:.2f}"
        }

    # Check breakout direction
    signal = None
    breakout_candle = None
    breakout_time = None

    for i in range(len(post_orb)):
        candle = post_orb.iloc[i]

        # Time filter: skip afternoon signals (after 12:00 PM)
        if candle["time"] >= "12:00":
            break

        if candle["close"] > orb_high and signal is None:
            signal = "BUY"
            breakout_candle = candle
            breakout_time = candle["time"]
            break
        elif candle["close"] < orb_low and signal is None:
            signal = "SELL"
            breakout_candle = candle
            breakout_time = candle["time"]
            break

    if signal is None:
        # No breakout yet
        last = today_df.iloc[-1]
        dist_high = ((orb_high - last["close"]) / last["close"]) * 100
        dist_low = ((last["close"] - orb_low) / last["close"]) * 100
        return {
            "symbol": symbol,
            "status": "NO_BREAKOUT",
            "orb_high": orb_high,
            "orb_low": orb_low,
            "orb_range": orb_range,
            "ltp": last["close"],
            "dist_high_pct": dist_high,
            "dist_low_pct": dist_low,
            "message": f"Range: {orb_low:.2f}-{orb_high:.2f} | LTP: {last['close']:.2f} | Near {'HIGH' if dist_high < dist_low else 'LOW'}"
        }

    # Signal found!
    entry = breakout_candle["close"]
    if signal == "BUY":
        sl = orb_low
        target = entry + (entry - sl) * RISK_REWARD
    else:
        sl = orb_high
        target = entry - (sl - entry) * RISK_REWARD

    risk = abs(entry - sl)
    reward = abs(target - entry)
    rr = reward / risk if risk > 0 else 0

    # Check current status
    last = today_df.iloc[-1]
    current_price = last["close"]

    if signal == "BUY":
        if current_price <= sl:
            trade_status = "SL HIT ❌"
            current_pnl = ((sl - entry) / entry) * 100
        elif current_price >= target:
            trade_status = "TARGET HIT ✅"
            current_pnl = ((target - entry) / entry) * 100
        else:
            trade_status = "ACTIVE 🟢"
            current_pnl = ((current_price - entry) / entry) * 100
    else:
        if current_price >= sl:
            trade_status = "SL HIT ❌"
            current_pnl = ((entry - sl) / entry) * 100
        elif current_price <= target:
            trade_status = "TARGET HIT ✅"
            current_pnl = ((entry - target) / entry) * 100
        else:
            trade_status = "ACTIVE 🟢"
            current_pnl = ((entry - current_price) / entry) * 100

    return {
        "symbol": symbol,
        "status": "SIGNAL",
        "signal": signal,
        "entry": entry,
        "sl": sl,
        "target": target,
        "risk": risk,
        "rr": rr,
        "breakout_time": breakout_time,
        "orb_high": orb_high,
        "orb_low": orb_low,
        "orb_range": orb_range,
        "current_price": current_price,
        "current_pnl": current_pnl,
        "trade_status": trade_status,
    }


def print_header():
    os.system("cls" if os.name == "nt" else "clear")
    now = datetime.now().strftime("%H:%M:%S")
    print()
    print("  ╔══════════════════════════════════════════════════════════════════════════╗")
    print("  ║                    ORB SCANNER - STOCKS + NIFTY                         ║")
    print(f"  ║                    Last Updated: {now}                           ║")
    print("  ╚══════════════════════════════════════════════════════════════════════════╝")
    print()


def print_signals(results):
    """Print formatted signals."""
    # Separate by type
    signals = [r for r in results if r and r["status"] == "SIGNAL"]
    waiting = [r for r in results if r and r["status"] == "WAITING"]
    no_break = [r for r in results if r and r["status"] == "NO_BREAKOUT"]

    # Active signals
    if signals:
        buy_signals = [s for s in signals if s["signal"] == "BUY"]
        sell_signals = [s for s in signals if s["signal"] == "SELL"]

        if buy_signals:
            print("  ┌─ BUY SIGNALS ──────────────────────────────────────────────────────────┐")
            print(f"  │ {'Symbol':<12} {'Entry':>8} {'SL':>8} {'Target':>8} {'R:R':>5} {'Time':>6} {'P&L':>7} {'Status':<15} │")
            print(f"  │{'─' * 74}│")
            for s in buy_signals:
                print(f"  │ {s['symbol']:<12} {s['entry']:>8.2f} {s['sl']:>8.2f} {s['target']:>8.2f} {s['rr']:>4.1f}x {s['breakout_time']:>6} {s['current_pnl']:>+6.2f}% {s['trade_status']:<15} │")
            print(f"  └──────────────────────────────────────────────────────────────────────────┘")
            print()

        if sell_signals:
            print("  ┌─ SELL SIGNALS ─────────────────────────────────────────────────────────┐")
            print(f"  │ {'Symbol':<12} {'Entry':>8} {'SL':>8} {'Target':>8} {'R:R':>5} {'Time':>6} {'P&L':>7} {'Status':<15} │")
            print(f"  │{'─' * 74}│")
            for s in sell_signals:
                print(f"  │ {s['symbol']:<12} {s['entry']:>8.2f} {s['sl']:>8.2f} {s['target']:>8.2f} {s['rr']:>4.1f}x {s['breakout_time']:>6} {s['current_pnl']:>+6.2f}% {s['trade_status']:<15} │")
            print(f"  └──────────────────────────────────────────────────────────────────────────┘")
            print()

    # Summary
    total_buy = len([s for s in signals if s["signal"] == "BUY"])
    total_sell = len([s for s in signals if s["signal"] == "SELL"])
    active = len([s for s in signals if "ACTIVE" in s.get("trade_status", "")])
    target_hit = len([s for s in signals if "TARGET" in s.get("trade_status", "")])
    sl_hit = len([s for s in signals if "SL HIT" in s.get("trade_status", "")])

    print(f"  📊 Summary: {total_buy} BUY | {total_sell} SELL | {active} Active | {target_hit} Target Hit | {sl_hit} SL Hit")

    if no_break:
        print(f"\n  ⏳ No breakout yet: ", end="")
        for r in no_break:
            near = "↑" if r["dist_high_pct"] < r["dist_low_pct"] else "↓"
            print(f"{r['symbol']}{near} ", end="")
        print()

    if waiting:
        print(f"\n  🔄 ORB forming: ", end="")
        for r in waiting:
            print(f"{r['symbol']} ", end="")
        print()

    # Nifty options recommendation
    nifty_signals = [s for s in signals if s["symbol"] in ["NIFTY50", "BANKNIFTY"]]
    if nifty_signals:
        print(f"\n  {'─' * 74}")
        print("  💰 NIFTY OPTIONS TRADE:")
        for s in nifty_signals:
            if s["signal"] == "BUY":
                print(f"     BUY {s['symbol']} ATM CE @ ~Rs.200 | SL when Nifty < {s['sl']:.0f} | Target when Nifty > {s['target']:.0f}")
            else:
                print(f"     BUY {s['symbol']} ATM PE @ ~Rs.200 | SL when Nifty > {s['sl']:.0f} | Target when Nifty < {s['target']:.0f}")
        print(f"  {'─' * 74}")

    print()


def run_scan(symbols, label=""):
    """Run ORB scan on given symbols."""
    results = []
    for sym in symbols:
        df = fetch_today_5m(sym, days=5)
        result = detect_orb(df, sym)
        results.append(result)
        time.sleep(0.3)
    return results


def main():
    # Parse args
    watch_mode = "--watch" in sys.argv
    nifty_only = "--nifty-only" in sys.argv
    stocks_only = "--stocks-only" in sys.argv

    token = load_token()
    if not token:
        print("  ❌ No Fyers token. Run: python fyers_data.py RELIANCE")
        return

    # Build scan list
    scan_list = []
    if not stocks_only:
        scan_list.extend(INDEX)
    if not nifty_only:
        scan_list.extend(STOCKS)

    if watch_mode:
        print("  🔄 Watch mode: refreshing every 60 seconds. Press Ctrl+C to stop.")
        while True:
            try:
                print_header()
                results = run_scan(scan_list)
                print_signals(results)
                print(f"  Next refresh in 60 seconds... (Ctrl+C to stop)")
                time.sleep(60)
            except KeyboardInterrupt:
                print("\n  Stopped.")
                break
    else:
        print_header()
        print(f"  Scanning {len(scan_list)} symbols...\n")
        results = run_scan(scan_list)
        print_signals(results)

        # Investment advice
        signals = [r for r in results if r and r["status"] == "SIGNAL"]
        if signals:
            buy_active = [s for s in signals if s["signal"] == "BUY" and "ACTIVE" in s.get("trade_status", "")]
            sell_active = [s for s in signals if s["signal"] == "SELL" and "ACTIVE" in s.get("trade_status", "")]

            if buy_active or sell_active:
                print("  ┌─ INVESTMENT PLAN (Rs.25K per stock) ────────────────────────────────────┐")
                total_investment = 0
                for s in buy_active[:5]:
                    qty = int(25000 / s["entry"])
                    cost = qty * s["entry"]
                    potential = qty * (s["target"] - s["entry"])
                    risk_amt = qty * abs(s["entry"] - s["sl"])
                    total_investment += cost
                    print(f"  │  BUY {s['symbol']:<12} {qty:>4} shares @ {s['entry']:>8.2f} = Rs.{cost:>8,.0f}  Pot: +Rs.{potential:>6,.0f}  Risk: -Rs.{risk_amt:>6,.0f} │")
                print(f"  │{'─' * 74}│")
                print(f"  │  Total Investment: Rs.{total_investment:>10,.0f}                                        │")
                print(f"  └──────────────────────────────────────────────────────────────────────────┘")

        print("\n  ℹ️  Run with --watch for live monitoring")
        print("  ℹ️  Run with --nifty-only for index only")
        print("  ℹ️  Run with --stocks-only for stocks only")
        print()


if __name__ == "__main__":
    main()
