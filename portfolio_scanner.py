"""
Portfolio Scanner - Multi-Stock Multi-Strategy Backtester
Scans 30 stocks × 3 best strategies, picks top signals, maximizes daily returns.
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from colorama import Fore, Style, init
from strategies import get_strategy, ALL_STRATEGIES
from fyers_data import fetch_data
import time
import argparse

init()

# ─── Top 30 Liquid Indian Stocks ───
STOCK_UNIVERSE = [
    # Nifty 50 High Volume
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
    "SBIN", "BHARTIARTL", "ITC", "KOTAKBANK", "LT",
    "AXISBANK", "HINDUNILVR", "BAJFINANCE", "MARUTI", "TATAMOTORS",
    "SUNPHARMA", "TITAN", "WIPRO", "ONGC", "NTPC",
    "POWERGRID", "HCLTECH", "TATASTEEL", "JSWSTEEL", "COALINDIA",
    "ADANIENT", "ADANIPORTS", "TECHM", "INDUSINDBK", "M&M",
]

# Best strategies from backtest results
BEST_STRATEGIES = ["vwap_rsi_vol", "bollinger_breakout", "ict_fvg_vwap"]


def fetch_all_data(stocks, period, interval):
    """Fetch data for all stocks with rate limiting."""
    data = {}
    total = len(stocks)
    for idx, symbol in enumerate(stocks):
        print(f"\r  Fetching {idx+1}/{total}: {symbol:<15}", end="", flush=True)
        try:
            df = fetch_data(symbol, period, interval)
            if df is not None and len(df) > 50:
                # Capitalize columns for strategies
                df.columns = [c.capitalize() for c in df.columns]
                if "Date" in df.columns:
                    df = df.set_index("Date")
                data[symbol] = df
        except Exception as e:
            pass
        time.sleep(0.3)  # Rate limit
    print(f"\r  Fetched {len(data)}/{total} stocks successfully" + " " * 20)
    return data


def generate_all_signals(data, strategies):
    """Generate signals for all stock-strategy combos."""
    all_signals = []
    for symbol, df in data.items():
        for strat_name in strategies:
            try:
                strategy = get_strategy(strat_name)
                sdf = strategy.generate_signals(df)

                # Vectorized: filter non-zero signals
                mask = sdf["signal"] != 0
                signal_rows = sdf[mask]

                if len(signal_rows) == 0:
                    continue

                for idx, row in signal_rows.iterrows():
                    sl = row.get("stop_loss", np.nan)
                    target = row.get("target", np.nan)
                    sig_val = int(row["signal"])
                    entry = float(row["Close"])

                    if pd.isna(sl) or pd.isna(entry):
                        continue

                    risk = abs(entry - float(sl))
                    if risk <= 0:
                        continue

                    if not pd.isna(target):
                        reward = abs(float(target) - entry)
                        rr = reward / risk if risk > 0 else 0
                    else:
                        rr = 2.0
                        if sig_val == 1:
                            target = entry + 2 * risk
                        else:
                            target = entry - 2 * risk

                    all_signals.append({
                        "date": idx,
                        "symbol": symbol,
                        "strategy": strat_name,
                        "signal": sig_val,
                        "entry": entry,
                        "stop_loss": float(sl),
                        "target": float(target),
                        "risk": risk,
                        "risk_pct": (risk / entry) * 100,
                        "rr_ratio": rr,
                    })

                print(f"    {symbol:<12} {strat_name:<20} {len(signal_rows)} signals")
            except Exception as e:
                print(f"    {symbol:<12} {strat_name:<20} ERROR: {e}")
    return pd.DataFrame(all_signals)


def run_portfolio_backtest(data, signals_df, capital=100000, max_positions=5,
                           risk_per_trade_pct=2.0, commission_pct=0.05):
    """
    Run portfolio backtest with multiple simultaneous positions.
    
    Args:
        data: dict of {symbol: DataFrame}
        signals_df: DataFrame of all signals
        capital: Starting capital
        max_positions: Maximum simultaneous positions
        risk_per_trade_pct: Max risk per trade as % of capital
        commission_pct: Commission per trade
    """
    if signals_df.empty:
        return None

    # Sort signals by date
    signals_df = signals_df.sort_values("date")

    current_capital = capital
    positions = {}  # symbol -> position dict
    trades = []
    equity_curve = [(signals_df["date"].iloc[0], capital)]
    daily_pnl = {}

    # Get all unique dates
    all_dates = sorted(set(signals_df["date"]))

    for date in all_dates:
        day_signals = signals_df[signals_df["date"] == date]

        # ── 3:15 PM exit for intraday positions ──
        if hasattr(date, 'hour') and date.hour == 15 and date.minute >= 15:
            symbols_to_close = list(positions.keys())
            for sym in symbols_to_close:
                pos = positions[sym]
                if sym in data:
                    close_price = data[sym]["Close"].loc[date] if date in data[sym].index else pos["entry_price"]
                else:
                    close_price = pos["entry_price"]

                if pos["direction"] == "LONG":
                    pnl = (close_price - pos["entry_price"]) * pos["qty"]
                else:
                    pnl = (pos["entry_price"] - close_price) * pos["qty"]

                comm = (pos["entry_price"] * pos["qty"] + close_price * pos["qty"]) * commission_pct / 100
                pnl -= comm
                current_capital += pnl

                trades.append({
                    "entry_date": pos["entry_date"],
                    "exit_date": date,
                    "symbol": sym,
                    "strategy": pos["strategy"],
                    "direction": pos["direction"],
                    "entry_price": round(pos["entry_price"], 2),
                    "exit_price": round(close_price, 2),
                    "qty": pos["qty"],
                    "pnl": round(pnl, 2),
                    "pnl_pct": round((pnl / (pos["entry_price"] * pos["qty"])) * 100, 2),
                    "exit_reason": "3:15 PM Exit",
                })
                del positions[sym]
            equity_curve.append((date, current_capital))
            continue

        # ── Check existing positions for SL/Target ──
        symbols_to_close = []
        for sym, pos in list(positions.items()):
            if sym not in data:
                continue
            df = data[sym]
            if date not in df.index:
                continue
            row = df.loc[date]

            if pos["direction"] == "LONG":
                if row["Low"] <= pos["stop_loss"]:
                    # SL hit
                    close_price = pos["stop_loss"]
                    pnl = (close_price - pos["entry_price"]) * pos["qty"]
                    comm = (pos["entry_price"] * pos["qty"] + close_price * pos["qty"]) * commission_pct / 100
                    pnl -= comm
                    current_capital += pnl
                    trades.append({
                        "entry_date": pos["entry_date"], "exit_date": date,
                        "symbol": sym, "strategy": pos["strategy"],
                        "direction": "LONG",
                        "entry_price": round(pos["entry_price"], 2),
                        "exit_price": round(close_price, 2),
                        "qty": pos["qty"], "pnl": round(pnl, 2),
                        "pnl_pct": round((pnl / (pos["entry_price"] * pos["qty"])) * 100, 2),
                        "exit_reason": f"Stop Loss (T{pos['targets_hit']})",
                    })
                    symbols_to_close.append(sym)
                elif row["High"] >= pos["current_target"]:
                    pos["targets_hit"] += 1
                    # Partial book 50% at first target
                    if pos["targets_hit"] == 1 and pos["qty"] > 1:
                        partial_qty = pos["qty"] // 2
                        partial_pnl = (pos["current_target"] - pos["entry_price"]) * partial_qty
                        comm = (pos["entry_price"] * partial_qty + pos["current_target"] * partial_qty) * commission_pct / 100
                        partial_pnl -= comm
                        current_capital += partial_pnl
                        trades.append({
                            "entry_date": pos["entry_date"], "exit_date": date,
                            "symbol": sym, "strategy": pos["strategy"],
                            "direction": "LONG",
                            "entry_price": round(pos["entry_price"], 2),
                            "exit_price": round(pos["current_target"], 2),
                            "qty": partial_qty, "pnl": round(partial_pnl, 2),
                            "pnl_pct": round((partial_pnl / (pos["entry_price"] * partial_qty)) * 100, 2),
                            "exit_reason": "Partial Book (50%)",
                        })
                        pos["qty"] -= partial_qty
                    pos["stop_loss"] = pos["current_target"]
                    pos["current_target"] += pos["risk_distance"]

            elif pos["direction"] == "SHORT":
                if row["High"] >= pos["stop_loss"]:
                    close_price = pos["stop_loss"]
                    pnl = (pos["entry_price"] - close_price) * pos["qty"]
                    comm = (pos["entry_price"] * pos["qty"] + close_price * pos["qty"]) * commission_pct / 100
                    pnl -= comm
                    current_capital += pnl
                    trades.append({
                        "entry_date": pos["entry_date"], "exit_date": date,
                        "symbol": sym, "strategy": pos["strategy"],
                        "direction": "SHORT",
                        "entry_price": round(pos["entry_price"], 2),
                        "exit_price": round(close_price, 2),
                        "qty": pos["qty"], "pnl": round(pnl, 2),
                        "pnl_pct": round((pnl / (pos["entry_price"] * pos["qty"])) * 100, 2),
                        "exit_reason": f"Stop Loss (T{pos['targets_hit']})",
                    })
                    symbols_to_close.append(sym)
                elif row["Low"] <= pos["current_target"]:
                    pos["targets_hit"] += 1
                    if pos["targets_hit"] == 1 and pos["qty"] > 1:
                        partial_qty = pos["qty"] // 2
                        partial_pnl = (pos["entry_price"] - pos["current_target"]) * partial_qty
                        comm = (pos["entry_price"] * partial_qty + pos["current_target"] * partial_qty) * commission_pct / 100
                        partial_pnl -= comm
                        current_capital += partial_pnl
                        trades.append({
                            "entry_date": pos["entry_date"], "exit_date": date,
                            "symbol": sym, "strategy": pos["strategy"],
                            "direction": "SHORT",
                            "entry_price": round(pos["entry_price"], 2),
                            "exit_price": round(pos["current_target"], 2),
                            "qty": partial_qty, "pnl": round(partial_pnl, 2),
                            "pnl_pct": round((partial_pnl / (pos["entry_price"] * partial_qty)) * 100, 2),
                            "exit_reason": "Partial Book (50%)",
                        })
                        pos["qty"] -= partial_qty
                    pos["stop_loss"] = pos["current_target"]
                    pos["current_target"] -= pos["risk_distance"]

        for sym in symbols_to_close:
            if sym in positions:
                del positions[sym]

        # ── Open new positions from signals ──
        if len(positions) < max_positions:
            # Sort by R:R ratio (best signals first)
            day_signals_sorted = day_signals.sort_values("rr_ratio", ascending=False)

            for _, sig in day_signals_sorted.iterrows():
                if len(positions) >= max_positions:
                    break
                if sig["symbol"] in positions:
                    continue  # Already have position in this stock

                # Time filter - only for intraday (skip for daily candles)
                if hasattr(sig["date"], 'hour') and hasattr(sig["date"], 'minute'):
                    h, m = sig["date"].hour, sig["date"].minute
                    # If hour is 0 and minute is 0, it's a daily candle - no filter
                    if not (h == 0 and m == 0):
                        if h < 9 or h >= 14:
                            continue

                entry_price = sig["entry"]
                risk = sig["risk"]
                risk_distance = risk

                # Position sizing: risk X% of capital per trade
                risk_amount = current_capital * (risk_per_trade_pct / 100)
                qty = int(risk_amount / risk) if risk > 0 else 0

                if qty <= 0:
                    continue

                # Cap position size to available capital
                pos_value = entry_price * qty
                if pos_value > current_capital * 0.3:  # Max 30% of capital per trade
                    qty = int((current_capital * 0.3) / entry_price)
                    if qty <= 0:
                        continue

                positions[sig["symbol"]] = {
                    "direction": "LONG" if sig["signal"] == 1 else "SHORT",
                    "entry_price": entry_price,
                    "stop_loss": sig["stop_loss"],
                    "current_target": sig["target"],
                    "risk_distance": risk_distance,
                    "targets_hit": 0,
                    "qty": qty,
                    "entry_date": sig["date"],
                    "strategy": sig["strategy"],
                }

        equity_curve.append((date, current_capital))

        # Track daily P&L
        day_key = date.date() if hasattr(date, 'date') else date
        daily_pnl[day_key] = current_capital

    # Close remaining positions
    for sym, pos in positions.items():
        if sym in data:
            close_price = data[sym]["Close"].iloc[-1]
        else:
            close_price = pos["entry_price"]
        if pos["direction"] == "LONG":
            pnl = (close_price - pos["entry_price"]) * pos["qty"]
        else:
            pnl = (pos["entry_price"] - close_price) * pos["qty"]
        comm = (pos["entry_price"] * pos["qty"] + close_price * pos["qty"]) * commission_pct / 100
        pnl -= comm
        current_capital += pnl
        trades.append({
            "entry_date": pos["entry_date"],
            "exit_date": data[sym].index[-1] if sym in data else pos["entry_date"],
            "symbol": sym, "strategy": pos["strategy"],
            "direction": pos["direction"],
            "entry_price": round(pos["entry_price"], 2),
            "exit_price": round(close_price, 2),
            "qty": pos["qty"], "pnl": round(pnl, 2),
            "pnl_pct": round((pnl / (pos["entry_price"] * pos["qty"])) * 100, 2),
            "exit_reason": "End of Data",
        })

    return {
        "trades": trades,
        "equity_curve": equity_curve,
        "final_capital": current_capital,
        "total_return_pct": ((current_capital - capital) / capital) * 100,
        "total_pnl": current_capital - capital,
        "daily_pnl": daily_pnl,
    }


def print_portfolio_report(result, capital, period_days):
    """Print comprehensive portfolio report."""
    trades = result["trades"]
    if not trades:
        print(f"  {Fore.RED}No trades generated.{Style.RESET_ALL}")
        return

    trades_df = pd.DataFrame(trades)
    wins = trades_df[trades_df["pnl"] > 0]
    losses = trades_df[trades_df["pnl"] <= 0]

    total_return = result["total_return_pct"]
    daily_return = total_return / period_days if period_days > 0 else 0
    monthly_return = daily_return * 22

    color = Fore.GREEN if total_return > 0 else Fore.RED

    print(f"\n{'=' * 80}")
    print(f"  {Fore.CYAN}PORTFOLIO SCANNER REPORT{Style.RESET_ALL}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")
    print(f"{'=' * 80}")

    print(f"\n  {Fore.YELLOW}PERFORMANCE{Style.RESET_ALL}")
    print(f"  {'─' * 50}")
    print(f"  Starting Capital:     Rs.{capital:>12,.2f}")
    print(f"  Final Capital:        Rs.{result['final_capital']:>12,.2f}")
    print(f"  {color}Total Return:          {total_return:+.2f}%{Style.RESET_ALL}")
    print(f"  {color}Total P&L:             Rs.{result['total_pnl']:+,.2f}{Style.RESET_ALL}")
    print(f"  {color}Daily Avg Return:      {daily_return:+.3f}%{Style.RESET_ALL}")
    print(f"  {color}Monthly Proj Return:   {monthly_return:+.2f}%{Style.RESET_ALL}")
    print(f"  {color}Daily Avg P&L:         Rs.{result['total_pnl']/period_days:+,.2f}{Style.RESET_ALL}")

    print(f"\n  {Fore.YELLOW}TRADE STATS{Style.RESET_ALL}")
    print(f"  {'─' * 50}")
    print(f"  Total Trades:         {len(trades)}")
    print(f"  Winning:              {len(wins)} ({len(wins)/len(trades)*100:.1f}%)")
    print(f"  Losing:               {len(losses)} ({len(losses)/len(trades)*100:.1f}%)")
    if len(wins) > 0:
        print(f"  Avg Win:              +{wins['pnl'].mean():,.2f} ({wins['pnl_pct'].mean():+.2f}%)")
    if len(losses) > 0:
        print(f"  Avg Loss:             {losses['pnl'].mean():,.2f} ({losses['pnl_pct'].mean():+.2f}%)")
    print(f"  Largest Win:          Rs.{trades_df['pnl'].max():+,.2f}")
    print(f"  Largest Loss:         Rs.{trades_df['pnl'].min():+,.2f}")

    # Per-stock breakdown
    print(f"\n  {Fore.YELLOW}PER-STOCK BREAKDOWN{Style.RESET_ALL}")
    print(f"  {'─' * 50}")
    stock_pnl = trades_df.groupby("symbol")["pnl"].sum().sort_values(ascending=False)
    stock_count = trades_df.groupby("symbol")["pnl"].count()
    for sym in stock_pnl.index:
        pnl = stock_pnl[sym]
        count = stock_count[sym]
        c = Fore.GREEN if pnl > 0 else Fore.RED
        print(f"  {sym:<15} {c}Rs.{pnl:>+10,.2f}{Style.RESET_ALL}  ({count} trades)")

    # Per-strategy breakdown
    print(f"\n  {Fore.YELLOW}PER-STRATEGY BREAKDOWN{Style.RESET_ALL}")
    print(f"  {'─' * 50}")
    strat_pnl = trades_df.groupby("strategy")["pnl"].sum().sort_values(ascending=False)
    strat_count = trades_df.groupby("strategy")["pnl"].count()
    for strat in strat_pnl.index:
        pnl = strat_pnl[strat]
        count = strat_count[strat]
        c = Fore.GREEN if pnl > 0 else Fore.RED
        print(f"  {strat:<20} {c}Rs.{pnl:>+10,.2f}{Style.RESET_ALL}  ({count} trades)")

    # Top 10 trades
    print(f"\n  {Fore.YELLOW}TOP 10 WINNING TRADES{Style.RESET_ALL}")
    print(f"  {'─' * 70}")
    top = trades_df.nlargest(10, "pnl")
    for _, t in top.iterrows():
        c = Fore.GREEN
        print(f"  {c}{t['symbol']:<12} {t['strategy']:<18} {t['direction']:<6} "
              f"Rs.{t['pnl']:>+8,.2f} ({t['pnl_pct']:+.2f}%) {t['exit_reason']}{Style.RESET_ALL}")

    print(f"\n{'=' * 80}\n")


def main():
    parser = argparse.ArgumentParser(description="Portfolio Scanner - Multi-Stock Multi-Strategy")
    parser.add_argument("--stocks", "-s", nargs="+", help="Stock symbols (default: top 30)")
    parser.add_argument("--strategies", "-st", nargs="+", help="Strategy names (default: top 3)")
    parser.add_argument("--period", "-p", default="3mo", help="Backtest period (default: 3mo)")
    parser.add_argument("--interval", "-i", default="5m", help="Candle interval (default: 5m)")
    parser.add_argument("--capital", "-c", type=float, default=100000, help="Starting capital")
    parser.add_argument("--max-pos", type=int, default=5, help="Max simultaneous positions (default: 5)")
    parser.add_argument("--risk", type=float, default=2.0, help="Risk per trade %% (default: 2)")
    parser.add_argument("--top", type=int, default=30, help="Top N stocks from universe (default: 30)")
    parser.add_argument("--long-only", action="store_true", help="Only take LONG positions (for cash market swing)")

    args = parser.parse_args()

    stocks = args.stocks if args.stocks else STOCK_UNIVERSE[:args.top]
    strategies = args.strategies if args.strategies else BEST_STRATEGIES

    print(f"\n  {Fore.CYAN}{'=' * 60}{Style.RESET_ALL}")
    print(f"  {Fore.CYAN}PORTFOLIO SCANNER{Style.RESET_ALL}")
    print(f"  {Fore.CYAN}{'=' * 60}{Style.RESET_ALL}")
    print(f"  Stocks:     {len(stocks)} stocks")
    print(f"  Strategies: {', '.join(strategies)}")
    print(f"  Period:     {args.period} | Interval: {args.interval}")
    print(f"  Capital:    Rs.{args.capital:,.0f}")
    print(f"  Max Pos:    {args.max_pos} | Risk/Trade: {args.risk}%")
    print()

    # 1. Fetch all data
    print(f"  {Fore.YELLOW}Step 1: Fetching data...{Style.RESET_ALL}")
    data = fetch_all_data(stocks, args.period, args.interval)

    if not data:
        print(f"  {Fore.RED}No data fetched. Exiting.{Style.RESET_ALL}")
        return

    # 2. Generate all signals
    print(f"  {Fore.YELLOW}Step 2: Generating signals ({len(data)} stocks × {len(strategies)} strategies)...{Style.RESET_ALL}")
    signals = generate_all_signals(data, strategies)
    print(f"  Generated {len(signals)} signals across all combos")

    if signals.empty:
        print(f"  {Fore.RED}No signals generated. Exiting.{Style.RESET_ALL}")
        return

    # Filter to LONG only if requested (cash market swing)
    if args.long_only:
        signals = signals[signals["signal"] == 1]
        print(f"  {Fore.YELLOW}LONG-ONLY mode: {len(signals)} buy signals{Style.RESET_ALL}")

    # 3. Run portfolio backtest
    print(f"  {Fore.YELLOW}Step 3: Running portfolio backtest...{Style.RESET_ALL}")
    result = run_portfolio_backtest(
        data, signals,
        capital=args.capital,
        max_positions=args.max_pos,
        risk_per_trade_pct=args.risk,
    )

    if result is None:
        print(f"  {Fore.RED}Backtest failed. Exiting.{Style.RESET_ALL}")
        return

    # Estimate trading days
    period_days = 63 if "3mo" in args.period else 126 if "6mo" in args.period else 252
    if "5m" in args.interval or "15m" in args.interval:
        period_days = period_days  # Same trading days

    # 4. Print report
    print_portfolio_report(result, args.capital, period_days)


if __name__ == "__main__":
    main()
