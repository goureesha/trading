"""
Live Paper Trading Tester for Indian Stocks
=============================================
Monitors stocks in real-time (15-min delayed via Yahoo Finance) and generates
live signals based on a chosen strategy. Tracks paper trades with P&L.

Usage:
    python live_test.py --stock RELIANCE --strategy ema_crossover          # Paper trade one stock
    python live_test.py --stock RELIANCE TCS INFY --strategy supertrend    # Multiple stocks
    python live_test.py --stock RELIANCE --strategy combo --capital 200000 # Custom capital
    python live_test.py --stock RELIANCE --strategy supertrend --interval 5m  # 5-min candles
    python live_test.py --status                                            # Check open positions
"""

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

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

from strategies import ALL_STRATEGIES, get_strategy

init(autoreset=True)

# File to persist paper trading state
STATE_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "live_state.json")
TRADE_LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "trade_log.json")


# ─────────────────────────────────────────────────────────────────────────────
# STATE MANAGEMENT
# ─────────────────────────────────────────────────────────────────────────────

def load_state() -> dict:
    """Load paper trading state from file."""
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {
        "capital": 100000,
        "initial_capital": 100000,
        "positions": {},
        "closed_trades": [],
        "strategy": None,
        "stocks": [],
        "started_at": None,
    }


def save_state(state: dict):
    """Save paper trading state to file."""
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


def load_trade_log() -> list:
    if os.path.exists(TRADE_LOG_FILE):
        with open(TRADE_LOG_FILE, "r") as f:
            return json.load(f)
    return []


def save_trade_log(trades: list):
    with open(TRADE_LOG_FILE, "w") as f:
        json.dump(trades, f, indent=2, default=str)


# ─────────────────────────────────────────────────────────────────────────────
# DATA FETCHER
# ─────────────────────────────────────────────────────────────────────────────

def fetch_live_data(symbol: str, period: str = "5d", interval: str = "15m"):
    """Fetch recent data for live analysis."""
    for suffix in [".NS", ".BO"]:
        try:
            ticker = yf.Ticker(f"{symbol}{suffix}")
            df = ticker.history(period=period, interval=interval)
            if df is not None and not df.empty and len(df) >= 20:
                if df.index.tz is not None:
                    df.index = df.index.tz_localize(None)
                return df
        except Exception:
            continue
    return None


def get_current_price(symbol: str) -> float:
    """Get the latest price for a stock."""
    for suffix in [".NS", ".BO"]:
        try:
            ticker = yf.Ticker(f"{symbol}{suffix}")
            info = ticker.history(period="1d", interval="1m")
            if info is not None and not info.empty:
                return info["Close"].iloc[-1]
        except Exception:
            continue
    return 0


# ─────────────────────────────────────────────────────────────────────────────
# LIVE TRADING ENGINE
# ─────────────────────────────────────────────────────────────────────────────

def check_signals(symbol: str, strategy_name: str, interval: str = "15m"):
    """Check current signals for a stock using the given strategy."""
    # Use enough data for indicators to warm up
    period_map = {
        "1m": "1d", "2m": "1d", "5m": "5d",
        "15m": "5d", "30m": "1mo", "1h": "1mo",
        "1d": "3mo", "1wk": "1y",
    }
    period = period_map.get(interval, "5d")

    df = fetch_live_data(symbol, period=period, interval=interval)
    if df is None:
        return None

    strategy = get_strategy(strategy_name)
    signals_df = strategy.generate_signals(df)

    # Get latest signal
    latest = signals_df.iloc[-1]
    prev = signals_df.iloc[-2] if len(signals_df) > 1 else latest

    return {
        "symbol": symbol,
        "price": round(latest["Close"], 2),
        "signal": int(latest.get("signal", 0)),
        "entry_price": round(latest.get("entry_price", 0), 2) if not np.isnan(latest.get("entry_price", np.nan)) else None,
        "stop_loss": round(latest.get("stop_loss", 0), 2) if not np.isnan(latest.get("stop_loss", np.nan)) else None,
        "target": round(latest.get("target", 0), 2) if not np.isnan(latest.get("target", np.nan)) else None,
        "timestamp": str(signals_df.index[-1]),
    }


def run_live_cycle(state: dict, interval: str = "15m", commission_pct: float = 0.05):
    """Run one cycle of the live paper trading loop."""
    strategy_name = state["strategy"]
    stocks = state["stocks"]
    events = []

    for symbol in stocks:
        sig = check_signals(symbol, strategy_name, interval)
        if sig is None:
            events.append(f"  {Fore.RED}[X] Could not fetch data for {symbol}{Style.RESET_ALL}")
            continue

        current_price = sig["price"]
        signal = sig["signal"]

        # Check existing position
        if symbol in state["positions"]:
            pos = state["positions"][symbol]
            pnl_pct = 0

            if pos["direction"] == "LONG":
                pnl_pct = ((current_price - pos["entry_price"]) / pos["entry_price"]) * 100

                # Check SL/Target
                if current_price <= pos["stop_loss"]:
                    close_reason = "STOP LOSS HIT"
                    close_price = pos["stop_loss"]
                elif current_price >= pos["target"]:
                    close_reason = "TARGET HIT"
                    close_price = pos["target"]
                elif signal == -1:
                    close_reason = "EXIT SIGNAL"
                    close_price = current_price
                else:
                    # Position still open
                    color = Fore.GREEN if pnl_pct > 0 else Fore.RED
                    events.append(
                        f"  {symbol:<12} LONG @ Rs.{pos['entry_price']:,.2f} | "
                        f"Now: Rs.{current_price:,.2f} | "
                        f"{color}P&L: {pnl_pct:+.2f}%{Style.RESET_ALL} | "
                        f"SL: Rs.{pos['stop_loss']:,.2f} | T: Rs.{pos['target']:,.2f}"
                    )
                    continue

            elif pos["direction"] == "SHORT":
                pnl_pct = ((pos["entry_price"] - current_price) / pos["entry_price"]) * 100

                if current_price >= pos["stop_loss"]:
                    close_reason = "STOP LOSS HIT"
                    close_price = pos["stop_loss"]
                elif current_price <= pos["target"]:
                    close_reason = "TARGET HIT"
                    close_price = pos["target"]
                elif signal == 1:
                    close_reason = "EXIT SIGNAL"
                    close_price = current_price
                else:
                    color = Fore.GREEN if pnl_pct > 0 else Fore.RED
                    events.append(
                        f"  {symbol:<12} SHORT @ Rs.{pos['entry_price']:,.2f} | "
                        f"Now: Rs.{current_price:,.2f} | "
                        f"{color}P&L: {pnl_pct:+.2f}%{Style.RESET_ALL} | "
                        f"SL: Rs.{pos['stop_loss']:,.2f} | T: Rs.{pos['target']:,.2f}"
                    )
                    continue

            # Close position
            if pos["direction"] == "LONG":
                pnl = (close_price - pos["entry_price"]) * pos["qty"]
            else:
                pnl = (pos["entry_price"] - close_price) * pos["qty"]

            commission = (pos["entry_price"] * pos["qty"] + close_price * pos["qty"]) * commission_pct / 100
            pnl -= commission
            final_pnl_pct = (pnl / (pos["entry_price"] * pos["qty"])) * 100

            state["capital"] += pnl

            trade = {
                "symbol": symbol,
                "direction": pos["direction"],
                "entry_price": pos["entry_price"],
                "exit_price": round(close_price, 2),
                "stop_loss": pos["stop_loss"],
                "target": pos["target"],
                "qty": pos["qty"],
                "pnl": round(pnl, 2),
                "pnl_pct": round(final_pnl_pct, 2),
                "exit_reason": close_reason,
                "entry_time": pos["entry_time"],
                "exit_time": str(datetime.now()),
            }
            state["closed_trades"].append(trade)
            del state["positions"][symbol]

            # Save to trade log
            log = load_trade_log()
            log.append(trade)
            save_trade_log(log)

            color = Fore.GREEN if pnl > 0 else Fore.RED
            events.append(
                f"  {color}>>> CLOSED {pos['direction']} {symbol} | "
                f"{close_reason} | P&L: Rs.{pnl:+,.2f} ({final_pnl_pct:+.2f}%){Style.RESET_ALL}"
            )

        # Open new position
        if symbol not in state["positions"] and signal != 0 and sig["stop_loss"] and sig["target"]:
            direction = "LONG" if signal == 1 else "SHORT"
            trade_capital = state["capital"] * 0.2  # 20% per trade
            qty = int(trade_capital / current_price)

            if qty > 0:
                state["positions"][symbol] = {
                    "direction": direction,
                    "entry_price": current_price,
                    "stop_loss": sig["stop_loss"],
                    "target": sig["target"],
                    "qty": qty,
                    "entry_time": str(datetime.now()),
                }

                events.append(
                    f"  {Fore.CYAN}>>> NEW {direction} {symbol} @ Rs.{current_price:,.2f} | "
                    f"Qty: {qty} | SL: Rs.{sig['stop_loss']:,.2f} | T: Rs.{sig['target']:,.2f}{Style.RESET_ALL}"
                )
        elif symbol not in state["positions"]:
            events.append(f"  {symbol:<12} Rs.{current_price:,.2f} | No signal")

    return events


def print_portfolio_status(state: dict):
    """Print the current portfolio status."""
    print(f"\n{'=' * 75}")
    print(f"  PAPER TRADING STATUS")
    print(f"  Strategy: {state.get('strategy', 'N/A')}")
    print(f"  Started: {state.get('started_at', 'N/A')}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")
    print(f"{'=' * 75}\n")

    # Capital
    initial = state["initial_capital"]
    current = state["capital"]
    # Add unrealized P&L
    unrealized = 0
    for sym, pos in state.get("positions", {}).items():
        price = get_current_price(sym)
        if price > 0:
            if pos["direction"] == "LONG":
                unrealized += (price - pos["entry_price"]) * pos["qty"]
            else:
                unrealized += (pos["entry_price"] - price) * pos["qty"]

    total = current + unrealized
    ret = ((total - initial) / initial) * 100
    color = Fore.GREEN if ret > 0 else Fore.RED

    print(f"  {'Initial Capital:':<25} Rs.{initial:,.2f}")
    print(f"  {'Cash Available:':<25} Rs.{current:,.2f}")
    print(f"  {'Unrealized P&L:':<25} {color}Rs.{unrealized:+,.2f}{Style.RESET_ALL}")
    print(f"  {'Total Value:':<25} {color}Rs.{total:,.2f}{Style.RESET_ALL}")
    print(f"  {'Total Return:':<25} {color}{ret:+.2f}%{Style.RESET_ALL}")
    print()

    # Open positions
    positions = state.get("positions", {})
    if positions:
        print(f"  OPEN POSITIONS ({len(positions)})")
        print(f"  {'-' * 60}")
        table = []
        for sym, pos in positions.items():
            price = get_current_price(sym)
            if pos["direction"] == "LONG":
                pnl = (price - pos["entry_price"]) * pos["qty"] if price > 0 else 0
                pnl_pct = ((price - pos["entry_price"]) / pos["entry_price"]) * 100 if price > 0 else 0
            else:
                pnl = (pos["entry_price"] - price) * pos["qty"] if price > 0 else 0
                pnl_pct = ((pos["entry_price"] - price) / pos["entry_price"]) * 100 if price > 0 else 0

            color = Fore.GREEN if pnl > 0 else Fore.RED
            table.append([
                sym, pos["direction"],
                f"Rs.{pos['entry_price']:,.2f}",
                f"Rs.{price:,.2f}" if price > 0 else "N/A",
                pos["qty"],
                f"{color}Rs.{pnl:+,.2f}{Style.RESET_ALL}",
                f"{color}{pnl_pct:+.2f}%{Style.RESET_ALL}",
                f"Rs.{pos['stop_loss']:,.2f}",
                f"Rs.{pos['target']:,.2f}",
            ])
        headers = ["Stock", "Dir", "Entry", "Now", "Qty", "P&L", "P&L%", "SL", "Target"]
        print(tabulate(table, headers=headers, tablefmt="rounded_outline"))
    else:
        print(f"  No open positions.")
    print()

    # Closed trades summary
    closed = state.get("closed_trades", [])
    if closed:
        wins = [t for t in closed if t["pnl"] > 0]
        losses = [t for t in closed if t["pnl"] <= 0]
        total_pnl = sum(t["pnl"] for t in closed)
        win_rate = (len(wins) / len(closed)) * 100 if closed else 0

        print(f"  CLOSED TRADES ({len(closed)})")
        print(f"  {'-' * 60}")
        print(f"  {'Total Closed P&L:':<25} {'Rs.' + f'{total_pnl:+,.2f}'}")
        print(f"  {'Win Rate:':<25} {win_rate:.1f}%")
        print(f"  {'Winners:':<25} {len(wins)}")
        print(f"  {'Losers:':<25} {len(losses)}")
    print(f"\n{'=' * 75}\n")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Live Paper Trading Tester for Indian Stocks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python live_test.py --stock RELIANCE --strategy supertrend      Start paper trading
  python live_test.py --stock RELIANCE TCS --strategy combo       Multiple stocks
  python live_test.py --status                                    Check positions
  python live_test.py --reset                                     Reset all positions
  python live_test.py --once --stock RELIANCE --strategy combo    Run one check cycle
        """,
    )
    parser.add_argument("--stock", "-s", nargs="+", help="Stock symbol(s) to monitor")
    parser.add_argument("--strategy", "-st", help="Strategy to use")
    parser.add_argument("--interval", "-i", default="15m", help="Candle interval (default: 15m)")
    parser.add_argument("--capital", "-c", type=float, default=100000, help="Starting capital (default: 100000)")
    parser.add_argument("--refresh", "-r", type=int, default=300, help="Refresh interval in seconds (default: 300)")
    parser.add_argument("--status", action="store_true", help="Show current portfolio status")
    parser.add_argument("--reset", action="store_true", help="Reset all paper trading state")
    parser.add_argument("--once", action="store_true", help="Run one check cycle and exit")
    parser.add_argument("--list", "-l", action="store_true", help="List available strategies")

    args = parser.parse_args()

    if args.list:
        print(f"\n  Available Strategies:")
        print(f"  {'-' * 70}")
        from strategies import list_strategies
        list_strategies()
        print()
        return

    if args.reset:
        if os.path.exists(STATE_FILE):
            os.remove(STATE_FILE)
        if os.path.exists(TRADE_LOG_FILE):
            os.remove(TRADE_LOG_FILE)
        print(f"\n  {Fore.GREEN}Paper trading state reset.{Style.RESET_ALL}\n")
        return

    if args.status:
        state = load_state()
        print_portfolio_status(state)
        return

    if not args.stock or not args.strategy:
        parser.error("--stock and --strategy are required for live testing.")

    if args.strategy not in ALL_STRATEGIES:
        print(f"\n  {Fore.RED}Unknown strategy '{args.strategy}'.{Style.RESET_ALL}")
        print(f"  Available: {', '.join(ALL_STRATEGIES.keys())}")
        return

    stocks = [s.upper() for s in args.stock]

    # Initialize or load state
    state = load_state()
    state["strategy"] = args.strategy
    state["stocks"] = stocks
    if state["started_at"] is None:
        state["capital"] = args.capital
        state["initial_capital"] = args.capital
        state["started_at"] = str(datetime.now())

    print(f"\n{'=' * 75}")
    print(f"  LIVE PAPER TRADING")
    print(f"  Strategy: {args.strategy}")
    print(f"  Stocks: {', '.join(stocks)}")
    print(f"  Interval: {args.interval}")
    print(f"  Capital: Rs.{state['capital']:,.2f}")
    if not args.once:
        print(f"  Refresh: every {args.refresh}s (Ctrl+C to stop)")
    print(f"{'=' * 75}\n")

    if args.once:
        # Single cycle
        print(f"  [{datetime.now().strftime('%H:%M:%S')}] Checking signals...")
        print(f"  {'-' * 60}")
        events = run_live_cycle(state, args.interval)
        for e in events:
            print(e)
        save_state(state)
        print(f"\n  Capital: Rs.{state['capital']:,.2f}")
        print(f"  Open positions: {len(state['positions'])}")
        print()
        return

    # Continuous monitoring loop
    try:
        while True:
            print(f"\n  [{datetime.now().strftime('%H:%M:%S')}] Checking signals...")
            print(f"  {'-' * 60}")

            events = run_live_cycle(state, args.interval)
            for e in events:
                print(e)

            save_state(state)

            # Summary
            total_positions = len(state["positions"])
            total_closed = len(state["closed_trades"])
            ret = ((state["capital"] - state["initial_capital"]) / state["initial_capital"]) * 100
            color = Fore.GREEN if ret > 0 else Fore.RED

            print(f"\n  Capital: Rs.{state['capital']:,.2f} ({color}{ret:+.2f}%{Style.RESET_ALL}) | "
                  f"Open: {total_positions} | Closed: {total_closed}")
            print(f"  Next check in {args.refresh}s...")

            time.sleep(args.refresh)

    except KeyboardInterrupt:
        save_state(state)
        print(f"\n\n  {Fore.YELLOW}Paper trading paused. State saved.{Style.RESET_ALL}")
        print(f"  Run 'python live_test.py --status' to check positions.")
        print(f"  Run again to resume.\n")


if __name__ == "__main__":
    main()
