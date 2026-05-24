"""
Indian Stock Trading Signal Generator
======================================
Generates Buy/Sell/Hold signals for NSE/BSE stocks using multiple
technical indicators: EMA Crossover, RSI, MACD, Supertrend, Bollinger Bands, VWAP.

Usage:
    python trading_signals.py                          # Scan Nifty 50 stocks (swing)
    python trading_signals.py --stock RELIANCE          # Single stock analysis
    python trading_signals.py --stock TCS INFY HDFC     # Multiple stocks
    python trading_signals.py --mode intraday            # Intraday signals
    python trading_signals.py --mode positional          # Positional signals
    python trading_signals.py --scan nifty50             # Scan Nifty 50
    python trading_signals.py --scan banknifty           # Scan Bank Nifty
    python trading_signals.py --stock RELIANCE --detail  # Detailed single-stock report
"""

import argparse
import os
import sys
from datetime import datetime, timedelta
from typing import Optional

# Fix Windows console encoding
if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import numpy as np
import pandas as pd
import yfinance as yf
from colorama import Fore, Style, init
from tabulate import tabulate

init(autoreset=True)

# ─────────────────────────────────────────────────────────────────────────────
# STOCK LISTS
# ─────────────────────────────────────────────────────────────────────────────

NIFTY_50 = [
    "ADANIENT", "ADANIPORTS", "APOLLOHOSP", "ASIANPAINT", "AXISBANK",
    "BAJAJ-AUTO", "BAJFINANCE", "BAJAJFINSV", "BPCL", "BHARTIARTL",
    "BRITANNIA", "CIPLA", "COALINDIA", "DIVISLAB", "DRREDDY",
    "EICHERMOT", "GRASIM", "HCLTECH", "HDFCBANK", "HDFCLIFE",
    "HEROMOTOCO", "HINDALCO", "HINDUNILVR", "ICICIBANK", "ITC",
    "INDUSINDBK", "INFY", "JSWSTEEL", "KOTAKBANK", "LT",
    "M&M", "MARUTI", "NESTLEIND", "NTPC", "ONGC",
    "POWERGRID", "RELIANCE", "SBILIFE", "SBIN", "SUNPHARMA",
    "TCS", "TATACONSUM", "TATAMOTORS", "TATASTEEL", "TECHM",
    "TITAN", "ULTRACEMCO", "UPL", "WIPRO", "LTIM",
]

BANK_NIFTY = [
    "HDFCBANK", "ICICIBANK", "KOTAKBANK", "AXISBANK", "SBIN",
    "INDUSINDBK", "BANDHANBNK", "FEDERALBNK", "IDFCFIRSTB", "PNB",
    "AUBANK", "BANKBARODA",
]

# ─────────────────────────────────────────────────────────────────────────────
# TIMEFRAME CONFIGS
# ─────────────────────────────────────────────────────────────────────────────

TIMEFRAME_CONFIG = {
    "intraday": {
        "interval": "15m",
        "period": "5d",
        "ema_fast": 9,
        "ema_slow": 21,
        "rsi_period": 14,
        "supertrend_period": 10,
        "supertrend_mult": 3.0,
        "bb_period": 20,
        "label": "Intraday (15m candles)",
    },
    "swing": {
        "interval": "1d",
        "period": "3mo",
        "ema_fast": 9,
        "ema_slow": 21,
        "rsi_period": 14,
        "supertrend_period": 10,
        "supertrend_mult": 2.0,
        "bb_period": 20,
        "label": "Swing (Daily candles)",
    },
    "positional": {
        "interval": "1wk",
        "period": "1y",
        "ema_fast": 10,
        "ema_slow": 30,
        "rsi_period": 14,
        "supertrend_period": 10,
        "supertrend_mult": 2.0,
        "bb_period": 20,
        "label": "Positional (Weekly candles)",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# TECHNICAL INDICATORS
# ─────────────────────────────────────────────────────────────────────────────


def calc_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def calc_rsi(close: pd.Series, period: int = 14) -> pd.Series:
    delta = close.diff()
    gain = delta.where(delta > 0, 0.0)
    loss = -delta.where(delta < 0, 0.0)
    avg_gain = gain.ewm(alpha=1 / period, min_periods=period).mean()
    avg_loss = loss.ewm(alpha=1 / period, min_periods=period).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def calc_macd(close: pd.Series, fast=12, slow=26, signal=9):
    ema_fast = calc_ema(close, fast)
    ema_slow = calc_ema(close, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calc_ema(macd_line, signal)
    histogram = macd_line - signal_line
    return macd_line, signal_line, histogram


def calc_supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0):
    """Calculate Supertrend indicator."""
    hl2 = (df["High"] + df["Low"]) / 2
    atr = calc_atr(df, period)

    upper_band = hl2 + (multiplier * atr)
    lower_band = hl2 - (multiplier * atr)

    supertrend = pd.Series(np.nan, index=df.index)
    direction = pd.Series(1, index=df.index)  # 1 = up (bullish), -1 = down (bearish)

    for i in range(1, len(df)):
        # Lower band logic
        if lower_band.iloc[i] > lower_band.iloc[i - 1] or df["Close"].iloc[i - 1] < lower_band.iloc[i - 1]:
            lower_band.iloc[i] = lower_band.iloc[i]
        else:
            lower_band.iloc[i] = lower_band.iloc[i - 1]

        # Upper band logic
        if upper_band.iloc[i] < upper_band.iloc[i - 1] or df["Close"].iloc[i - 1] > upper_band.iloc[i - 1]:
            upper_band.iloc[i] = upper_band.iloc[i]
        else:
            upper_band.iloc[i] = upper_band.iloc[i - 1]

        # Direction
        if supertrend.iloc[i - 1] == upper_band.iloc[i - 1]:
            if df["Close"].iloc[i] > upper_band.iloc[i]:
                supertrend.iloc[i] = lower_band.iloc[i]
                direction.iloc[i] = 1
            else:
                supertrend.iloc[i] = upper_band.iloc[i]
                direction.iloc[i] = -1
        else:
            if df["Close"].iloc[i] < lower_band.iloc[i]:
                supertrend.iloc[i] = upper_band.iloc[i]
                direction.iloc[i] = -1
            else:
                supertrend.iloc[i] = lower_band.iloc[i]
                direction.iloc[i] = 1

    return supertrend, direction


def calc_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    high_low = df["High"] - df["Low"]
    high_close = (df["High"] - df["Close"].shift()).abs()
    low_close = (df["Low"] - df["Close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return true_range.ewm(alpha=1 / period, min_periods=period).mean()


def calc_bollinger_bands(close: pd.Series, period: int = 20, std_dev: float = 2.0):
    sma = close.rolling(window=period).mean()
    std = close.rolling(window=period).std()
    upper = sma + (std_dev * std)
    lower = sma - (std_dev * std)
    return upper, sma, lower


def calc_vwap(df: pd.DataFrame) -> pd.Series:
    """Calculate VWAP — resets daily for intraday data."""
    typical_price = (df["High"] + df["Low"] + df["Close"]) / 3
    if "Volume" in df.columns and df["Volume"].sum() > 0:
        cum_vol = df["Volume"].cumsum()
        cum_tp_vol = (typical_price * df["Volume"]).cumsum()
        vwap = cum_tp_vol / cum_vol
        return vwap
    return typical_price


# ─────────────────────────────────────────────────────────────────────────────
# SIGNAL GENERATION
# ─────────────────────────────────────────────────────────────────────────────


def generate_signals(symbol: str, mode: str = "swing") -> Optional[dict]:
    """
    Fetch data and generate composite trading signals for a stock.
    Returns a dict with all signal info, or None on failure.
    """
    cfg = TIMEFRAME_CONFIG[mode]

    try:
        # Try NSE first, then BSE
        df = None
        for suffix in [".NS", ".BO"]:
            try:
                ticker_symbol = f"{symbol}{suffix}"
                ticker = yf.Ticker(ticker_symbol)
                df = ticker.history(period=cfg["period"], interval=cfg["interval"])
                if df is not None and not df.empty and len(df) >= 30:
                    break
                df = None
            except Exception:
                df = None
                continue

        if df is None or df.empty or len(df) < 30:
            return None

        # Remove timezone info for clean processing
        if df.index.tz is not None:
            df.index = df.index.tz_localize(None)

        close = df["Close"]
        current_price = close.iloc[-1]

        # ── Calculate all indicators ──
        ema_fast = calc_ema(close, cfg["ema_fast"])
        ema_slow = calc_ema(close, cfg["ema_slow"])
        rsi = calc_rsi(close, cfg["rsi_period"])
        macd_line, macd_signal, macd_hist = calc_macd(close)
        supertrend, st_direction = calc_supertrend(df, cfg["supertrend_period"], cfg["supertrend_mult"])
        bb_upper, bb_mid, bb_lower = calc_bollinger_bands(close, cfg["bb_period"])
        atr = calc_atr(df)
        vwap = calc_vwap(df)

        # Latest values
        latest = {
            "ema_fast": ema_fast.iloc[-1],
            "ema_slow": ema_slow.iloc[-1],
            "rsi": rsi.iloc[-1],
            "macd": macd_line.iloc[-1],
            "macd_signal": macd_signal.iloc[-1],
            "macd_hist": macd_hist.iloc[-1],
            "macd_hist_prev": macd_hist.iloc[-2] if len(macd_hist) > 1 else 0,
            "supertrend": supertrend.iloc[-1],
            "st_direction": st_direction.iloc[-1],
            "bb_upper": bb_upper.iloc[-1],
            "bb_mid": bb_mid.iloc[-1],
            "bb_lower": bb_lower.iloc[-1],
            "atr": atr.iloc[-1],
            "vwap": vwap.iloc[-1],
        }

        # ── Individual Indicator Signals ──
        # Each returns: +1 (buy), -1 (sell), 0 (neutral)
        signals = {}

        # 1. EMA Crossover
        ema_prev_fast = ema_fast.iloc[-2]
        ema_prev_slow = ema_slow.iloc[-2]
        if ema_prev_fast <= ema_prev_slow and latest["ema_fast"] > latest["ema_slow"]:
            signals["EMA Cross"] = +1  # Bullish crossover
        elif ema_prev_fast >= ema_prev_slow and latest["ema_fast"] < latest["ema_slow"]:
            signals["EMA Cross"] = -1  # Bearish crossover
        elif latest["ema_fast"] > latest["ema_slow"]:
            signals["EMA Cross"] = +0.5  # Bullish trend
        else:
            signals["EMA Cross"] = -0.5  # Bearish trend

        # 2. RSI
        if latest["rsi"] < 30:
            signals["RSI"] = +1  # Oversold — potential buy
        elif latest["rsi"] > 70:
            signals["RSI"] = -1  # Overbought — potential sell
        elif latest["rsi"] < 40:
            signals["RSI"] = +0.5
        elif latest["rsi"] > 60:
            signals["RSI"] = -0.5
        else:
            signals["RSI"] = 0

        # 3. MACD
        if latest["macd"] > latest["macd_signal"] and latest["macd_hist"] > latest["macd_hist_prev"]:
            signals["MACD"] = +1  # Bullish momentum increasing
        elif latest["macd"] > latest["macd_signal"]:
            signals["MACD"] = +0.5
        elif latest["macd"] < latest["macd_signal"] and latest["macd_hist"] < latest["macd_hist_prev"]:
            signals["MACD"] = -1  # Bearish momentum increasing
        elif latest["macd"] < latest["macd_signal"]:
            signals["MACD"] = -0.5
        else:
            signals["MACD"] = 0

        # 4. Supertrend
        if latest["st_direction"] == 1:
            signals["Supertrend"] = +1  # Bullish
        else:
            signals["Supertrend"] = -1  # Bearish

        # 5. Bollinger Bands
        if current_price <= latest["bb_lower"]:
            signals["Bollinger"] = +1  # At lower band — potential bounce
        elif current_price >= latest["bb_upper"]:
            signals["Bollinger"] = -1  # At upper band — potential reversal
        elif current_price < latest["bb_mid"]:
            signals["Bollinger"] = +0.3
        else:
            signals["Bollinger"] = -0.3

        # 6. VWAP (most useful for intraday)
        if current_price > latest["vwap"]:
            signals["VWAP"] = +0.5
        else:
            signals["VWAP"] = -0.5

        # ── Composite Score ──
        weights = {
            "EMA Cross": 2.0,
            "RSI": 1.5,
            "MACD": 1.5,
            "Supertrend": 2.0,
            "Bollinger": 1.0,
            "VWAP": 1.0 if mode == "intraday" else 0.5,
        }

        total_weight = sum(weights.values())
        composite_score = sum(signals[k] * weights[k] for k in signals) / total_weight

        # ── Determine Signal ──
        if composite_score >= 0.5:
            action = "STRONG BUY"
        elif composite_score >= 0.2:
            action = "BUY"
        elif composite_score <= -0.5:
            action = "STRONG SELL"
        elif composite_score <= -0.2:
            action = "SELL"
        else:
            action = "HOLD"

        # ── Calculate Entry, Stop-Loss, Targets ──
        atr_val = latest["atr"]

        if "BUY" in action:
            entry = current_price
            stop_loss = current_price - (1.5 * atr_val)
            target_1 = current_price + (1.0 * atr_val)
            target_2 = current_price + (2.0 * atr_val)
            target_3 = current_price + (3.0 * atr_val)
            risk = entry - stop_loss
            reward = target_2 - entry
        elif "SELL" in action:
            entry = current_price
            stop_loss = current_price + (1.5 * atr_val)
            target_1 = current_price - (1.0 * atr_val)
            target_2 = current_price - (2.0 * atr_val)
            target_3 = current_price - (3.0 * atr_val)
            risk = stop_loss - entry
            reward = entry - target_2
        else:
            entry = current_price
            stop_loss = None
            target_1 = None
            target_2 = None
            target_3 = None
            risk = 0
            reward = 0

        rr_ratio = round(reward / risk, 2) if risk > 0 else 0

        # ── Volume Analysis ──
        avg_volume = df["Volume"].rolling(20).mean().iloc[-1] if "Volume" in df.columns else 0
        current_volume = df["Volume"].iloc[-1] if "Volume" in df.columns else 0
        volume_ratio = round(current_volume / avg_volume, 2) if avg_volume > 0 else 0

        # ── Price Change ──
        prev_close = close.iloc[-2] if len(close) > 1 else current_price
        price_change = current_price - prev_close
        price_change_pct = (price_change / prev_close) * 100

        return {
            "symbol": symbol,
            "price": round(current_price, 2),
            "change": round(price_change, 2),
            "change_pct": round(price_change_pct, 2),
            "action": action,
            "score": round(composite_score, 3),
            "entry": round(entry, 2),
            "stop_loss": round(stop_loss, 2) if stop_loss else None,
            "target_1": round(target_1, 2) if target_1 else None,
            "target_2": round(target_2, 2) if target_2 else None,
            "target_3": round(target_3, 2) if target_3 else None,
            "rr_ratio": rr_ratio,
            "rsi": round(latest["rsi"], 1),
            "macd_hist": round(latest["macd_hist"], 2),
            "supertrend_dir": "UP" if latest["st_direction"] == 1 else "DOWN",
            "volume_ratio": volume_ratio,
            "atr": round(atr_val, 2),
            "signals": signals,
            "latest": latest,
        }

    except Exception as e:
        try:
            print(f"  {Fore.RED}[X] Error fetching {symbol}: {e}{Style.RESET_ALL}")
        except Exception:
            print(f"  [X] Error fetching {symbol}: {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# DISPLAY
# ─────────────────────────────────────────────────────────────────────────────


def colorize_action(action: str) -> str:
    colors = {
        "STRONG BUY": Fore.GREEN + Style.BRIGHT,
        "BUY": Fore.GREEN,
        "HOLD": Fore.YELLOW,
        "SELL": Fore.RED,
        "STRONG SELL": Fore.RED + Style.BRIGHT,
    }
    color = colors.get(action, "")
    return f"{color}{action}{Style.RESET_ALL}"


def colorize_change(val: float) -> str:
    if val > 0:
        return f"{Fore.GREEN}+{val:.2f}%{Style.RESET_ALL}"
    elif val < 0:
        return f"{Fore.RED}{val:.2f}%{Style.RESET_ALL}"
    return f"{val:.2f}%"


def print_scan_results(results: list, mode: str):
    """Print a summary table of all scanned stocks."""
    cfg = TIMEFRAME_CONFIG[mode]

    print(f"\n{'=' * 90}")
    print(f"  TRADING SIGNALS -- {cfg['label']}")
    print(f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")
    print(f"{'=' * 90}\n")

    if not results:
        print(f"  {Fore.RED}No valid results. Check your stock symbols or market may be closed.{Style.RESET_ALL}")
        return

    # Separate by signal type
    buys = [r for r in results if "BUY" in r["action"]]
    sells = [r for r in results if "SELL" in r["action"]]
    holds = [r for r in results if r["action"] == "HOLD"]

    # ── BUY Signals ──
    if buys:
        print(f"  {Fore.GREEN}{Style.BRIGHT}>>> BUY SIGNALS ({len(buys)}){Style.RESET_ALL}\n")
        table = []
        for r in sorted(buys, key=lambda x: x["score"], reverse=True):
            table.append([
                r["symbol"],
                f"Rs.{r['price']:,.2f}",
                colorize_change(r["change_pct"]),
                colorize_action(r["action"]),
                f"{r['score']:+.2f}",
                f"Rs.{r['entry']:,.2f}",
                f"Rs.{r['stop_loss']:,.2f}" if r["stop_loss"] else "-",
                f"Rs.{r['target_1']:,.2f}" if r["target_1"] else "-",
                f"Rs.{r['target_2']:,.2f}" if r["target_2"] else "-",
                f"{r['rr_ratio']}:1",
                f"{r['rsi']}",
            ])
        headers = ["Stock", "Price", "Change", "Signal", "Score", "Entry", "SL", "T1", "T2", "R:R", "RSI"]
        print(tabulate(table, headers=headers, tablefmt="rounded_outline", stralign="right"))
        print()

    # ── SELL Signals ──
    if sells:
        print(f"  {Fore.RED}{Style.BRIGHT}<<< SELL SIGNALS ({len(sells)}){Style.RESET_ALL}\n")
        table = []
        for r in sorted(sells, key=lambda x: x["score"]):
            table.append([
                r["symbol"],
                f"Rs.{r['price']:,.2f}",
                colorize_change(r["change_pct"]),
                colorize_action(r["action"]),
                f"{r['score']:+.2f}",
                f"Rs.{r['entry']:,.2f}",
                f"Rs.{r['stop_loss']:,.2f}" if r["stop_loss"] else "-",
                f"Rs.{r['target_1']:,.2f}" if r["target_1"] else "-",
                f"Rs.{r['target_2']:,.2f}" if r["target_2"] else "-",
                f"{r['rr_ratio']}:1",
                f"{r['rsi']}",
            ])
        headers = ["Stock", "Price", "Change", "Signal", "Score", "Entry", "SL", "T1", "T2", "R:R", "RSI"]
        print(tabulate(table, headers=headers, tablefmt="rounded_outline", stralign="right"))
        print()

    # ── HOLD Signals ──
    if holds:
        print(f"  {Fore.YELLOW}--- HOLD / NEUTRAL ({len(holds)}){Style.RESET_ALL}\n")
        table = []
        for r in sorted(holds, key=lambda x: x["score"], reverse=True):
            table.append([
                r["symbol"],
                f"Rs.{r['price']:,.2f}",
                colorize_change(r["change_pct"]),
                r["action"],
                f"{r['score']:+.2f}",
                f"{r['rsi']}",
                r["supertrend_dir"],
            ])
        headers = ["Stock", "Price", "Change", "Signal", "Score", "RSI", "Trend"]
        print(tabulate(table, headers=headers, tablefmt="rounded_outline", stralign="right"))
        print()

    # ── Summary ──
    print(f"{'-' * 90}")
    print(f"  Total: {len(results)} stocks scanned | "
          f"{Fore.GREEN}{len(buys)} Buy{Style.RESET_ALL} | "
          f"{Fore.RED}{len(sells)} Sell{Style.RESET_ALL} | "
          f"{Fore.YELLOW}{len(holds)} Hold{Style.RESET_ALL}")
    print(f"{'-' * 90}\n")


def print_detailed_report(result: dict, mode: str):
    """Print a detailed report for a single stock."""
    cfg = TIMEFRAME_CONFIG[mode]
    r = result

    print(f"\n{'=' * 70}")
    print(f"  DETAILED ANALYSIS: {r['symbol']}")
    print(f"  Mode: {cfg['label']}")
    print(f"  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")
    print(f"{'=' * 70}\n")

    # -- Price Info --
    print(f"  {'Price:':<20} Rs.{r['price']:,.2f}  ({colorize_change(r['change_pct'])})")
    print(f"  {'Signal:':<20} {colorize_action(r['action'])}  (Score: {r['score']:+.3f})")
    print(f"  {'Volume Ratio:':<20} {r['volume_ratio']}x vs 20-day avg")
    print()

    # ── Entry / Exit ──
    if r["stop_loss"]:
        print(f"  {'-' * 50}")
        print(f"  TRADE SETUP")
        print(f"  {'-' * 50}")
        print(f"  {'Entry:':<20} Rs.{r['entry']:,.2f}")
        print(f"  {'Stop Loss:':<20} Rs.{r['stop_loss']:,.2f}  ({Fore.RED}Risk: Rs.{abs(r['entry'] - r['stop_loss']):,.2f}{Style.RESET_ALL})")
        print(f"  {'Target 1:':<20} Rs.{r['target_1']:,.2f}  (1x ATR)")
        print(f"  {'Target 2:':<20} Rs.{r['target_2']:,.2f}  (2x ATR)")
        print(f"  {'Target 3:':<20} Rs.{r['target_3']:,.2f}  (3x ATR)")
        print(f"  {'Risk:Reward:':<20} {r['rr_ratio']}:1")
        print(f"  {'ATR:':<20} Rs.{r['atr']:,.2f}")
        print()

    # ── Indicator Breakdown ──
    print(f"  {'-' * 50}")
    print(f"  INDICATOR BREAKDOWN")
    print(f"  {'-' * 50}")

    indicator_table = []
    for name, val in r["signals"].items():
        if val >= 0.5:
            signal_str = f"{Fore.GREEN}[+] BULLISH{Style.RESET_ALL}"
        elif val > 0:
            signal_str = f"{Fore.GREEN}[~] Lean Bullish{Style.RESET_ALL}"
        elif val <= -0.5:
            signal_str = f"{Fore.RED}[-] BEARISH{Style.RESET_ALL}"
        elif val < 0:
            signal_str = f"{Fore.RED}[~] Lean Bearish{Style.RESET_ALL}"
        else:
            signal_str = f"{Fore.YELLOW}[=] Neutral{Style.RESET_ALL}"
        indicator_table.append([name, signal_str, f"{val:+.1f}"])

    print(tabulate(indicator_table, headers=["Indicator", "Signal", "Value"], tablefmt="rounded_outline"))
    print()

    # ── Key Levels ──
    lat = r["latest"]
    print(f"  {'-' * 50}")
    print(f"  KEY LEVELS")
    print(f"  {'-' * 50}")
    print(f"  {'EMA Fast:':<25} Rs.{lat['ema_fast']:,.2f}  ({cfg['ema_fast']}-period)")
    print(f"  {'EMA Slow:':<25} Rs.{lat['ema_slow']:,.2f}  ({cfg['ema_slow']}-period)")
    print(f"  {'RSI:':<25} {lat['rsi']:.1f}")
    print(f"  {'MACD Histogram:':<25} {lat['macd_hist']:.2f}")
    if not np.isnan(lat['supertrend']):
        print(f"  {'Supertrend:':<25} {r['supertrend_dir']}  (Rs.{lat['supertrend']:,.2f})")
    else:
        print(f"  {'Supertrend:':<25} {r['supertrend_dir']}")
    print(f"  {'Bollinger Upper:':<25} Rs.{lat['bb_upper']:,.2f}")
    print(f"  {'Bollinger Mid:':<25} Rs.{lat['bb_mid']:,.2f}")
    print(f"  {'Bollinger Lower:':<25} Rs.{lat['bb_lower']:,.2f}")
    print(f"  {'VWAP:':<25} Rs.{lat['vwap']:,.2f}")
    print()

    # -- Disclaimer --
    print(f"  {'-' * 50}")
    print(f"  {Fore.YELLOW}!! DISCLAIMER: This is for educational/informational")
    print(f"     purposes only. Not financial advice. Always do your")
    print(f"     own research before trading.{Style.RESET_ALL}")
    print(f"{'=' * 70}\n")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────


def main():
    parser = argparse.ArgumentParser(
        description="📊 Indian Stock Trading Signal Generator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python trading_signals.py                            Scan Nifty 50 (swing mode)
  python trading_signals.py --stock RELIANCE           Single stock
  python trading_signals.py --stock TCS INFY           Multiple stocks
  python trading_signals.py --mode intraday            Intraday signals
  python trading_signals.py --mode positional          Positional signals
  python trading_signals.py --scan banknifty           Scan Bank Nifty
  python trading_signals.py --stock RELIANCE --detail  Detailed report
        """,
    )
    parser.add_argument("--stock", "-s", nargs="+", help="Stock symbol(s) to analyze (e.g., RELIANCE TCS INFY)")
    parser.add_argument("--mode", "-m", choices=["intraday", "swing", "positional"], default="swing",
                        help="Trading mode (default: swing)")
    parser.add_argument("--scan", choices=["nifty50", "banknifty"], help="Scan a predefined stock list")
    parser.add_argument("--detail", "-d", action="store_true", help="Show detailed report (single stock only)")

    args = parser.parse_args()

    # Determine stock list
    if args.stock:
        stocks = [s.upper() for s in args.stock]
    elif args.scan == "banknifty":
        stocks = BANK_NIFTY
    else:
        stocks = NIFTY_50

    mode = args.mode

    # ── Single stock detailed ──
    if args.detail and args.stock and len(args.stock) == 1:
        symbol = args.stock[0].upper()
        print(f"\n  Analyzing {symbol}...", end="", flush=True)
        result = generate_signals(symbol, mode)
        if result:
            print(f" {Fore.GREEN}Done!{Style.RESET_ALL}")
            print_detailed_report(result, mode)
        else:
            print(f"\n  {Fore.RED}[X] Could not fetch data for {symbol}{Style.RESET_ALL}")
        return

    # ── Scan Mode ──
    total = len(stocks)
    print(f"\n  Scanning {total} stocks in {TIMEFRAME_CONFIG[mode]['label']} mode...\n")

    results = []
    for i, symbol in enumerate(stocks, 1):
        pct = int((i / total) * 30)
        bar = f"{'#' * pct}{'.' * (30 - pct)}"
        print(f"\r  [{bar}] {i}/{total} - {symbol:<15}", end="", flush=True)

        result = generate_signals(symbol, mode)
        if result:
            results.append(result)

    print(f"\r  {'[OK] Scan complete!' : <60}")
    print_scan_results(results, mode)


if __name__ == "__main__":
    main()
