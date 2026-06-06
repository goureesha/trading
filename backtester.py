"""
Backtesting Engine for Indian Stocks
======================================
Tests trading strategies on historical data and produces performance reports.

Usage:
    python backtester.py --stock RELIANCE                              # Backtest all strategies on RELIANCE
    python backtester.py --stock RELIANCE --strategy ema_crossover     # Backtest one strategy
    python backtester.py --stock RELIANCE TCS INFY --compare           # Compare strategies across stocks
    python backtester.py --stock RELIANCE --period 1y                  # 1 year backtest
    python backtester.py --stock RELIANCE --period 2y --interval 1d    # 2 years, daily
    python backtester.py --stock RELIANCE --capital 100000             # Starting capital Rs.1,00,000
"""

import argparse
import os
import sys
from datetime import datetime
from typing import Optional

if sys.platform == 'win32':
    os.environ['PYTHONIOENCODING'] = 'utf-8'
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except Exception:
        pass

import numpy as np
import pandas as pd
from colorama import Fore, Style, init
from tabulate import tabulate

from strategies import ALL_STRATEGIES, get_strategy

init(autoreset=True)


# ─────────────────────────────────────────────────────────────────────────────
# DATA FETCHER — Fyers API (primary) + Yahoo Finance (fallback)
# ─────────────────────────────────────────────────────────────────────────────

def fetch_data(symbol: str, period: str = "1y", interval: str = "1d") -> Optional[pd.DataFrame]:
    """
    Fetch historical data for an Indian stock.
    Tries Fyers API first (supports 1m/5m/15m/1h/1d), falls back to Yahoo.
    """
    # Try Fyers first
    try:
        from fyers_data import fetch_data as fyers_fetch
        df = fyers_fetch(symbol, period=period, interval=interval)
        if df is not None and len(df) >= 30:
            # Convert to standard format with capitalized columns for strategies
            df = df.set_index("date")
            df.columns = [c.capitalize() for c in df.columns]
            return df
    except Exception:
        pass

    # Fallback to Yahoo Finance
    try:
        import yfinance as yf
        for suffix in [".NS", ".BO"]:
            try:
                ticker = yf.Ticker(f"{symbol}{suffix}")
                df = ticker.history(period=period, interval=interval)
                if df is not None and not df.empty and len(df) >= 30:
                    if df.index.tz is not None:
                        df.index = df.index.tz_localize(None)
                    return df
            except Exception:
                continue
    except ImportError:
        pass

    return None


# ─────────────────────────────────────────────────────────────────────────────
# BACKTESTING ENGINE
# ─────────────────────────────────────────────────────────────────────────────

class BacktestResult:
    """Holds the results of a single backtest run."""

    def __init__(self, strategy_name: str, symbol: str, trades: list, equity_curve: list,
                 initial_capital: float, final_capital: float, period: str):
        self.strategy_name = strategy_name
        self.symbol = symbol
        self.trades = trades
        self.equity_curve = equity_curve
        self.initial_capital = initial_capital
        self.final_capital = final_capital
        self.period = period
        self._compute_metrics()

    def _compute_metrics(self):
        """Compute all performance metrics."""
        trades = self.trades

        self.total_trades = len(trades)

        if self.total_trades == 0:
            self.win_rate = 0
            self.avg_profit_pct = 0
            self.avg_loss_pct = 0
            self.profit_factor = 0
            self.max_drawdown = 0
            self.max_drawdown_pct = 0
            self.sharpe_ratio = 0
            self.total_return_pct = 0
            self.avg_hold_days = 0
            self.winning_trades = 0
            self.losing_trades = 0
            self.largest_win = 0
            self.largest_loss = 0
            self.consecutive_wins = 0
            self.consecutive_losses = 0
            self.expectancy = 0
            return

        profits = [t["pnl_pct"] for t in trades]
        winners = [p for p in profits if p > 0]
        losers = [p for p in profits if p <= 0]

        self.winning_trades = len(winners)
        self.losing_trades = len(losers)
        self.win_rate = (self.winning_trades / self.total_trades) * 100 if self.total_trades > 0 else 0

        self.avg_profit_pct = np.mean(winners) if winners else 0
        self.avg_loss_pct = np.mean(losers) if losers else 0

        gross_profit = sum(winners) if winners else 0
        gross_loss = abs(sum(losers)) if losers else 0
        self.profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf') if gross_profit > 0 else 0

        self.total_return_pct = ((self.final_capital - self.initial_capital) / self.initial_capital) * 100

        self.largest_win = max(profits) if profits else 0
        self.largest_loss = min(profits) if profits else 0

        # Max drawdown from equity curve
        if self.equity_curve:
            eq = pd.Series(self.equity_curve)
            peak = eq.cummax()
            drawdown = (eq - peak) / peak * 100
            self.max_drawdown_pct = drawdown.min()
            self.max_drawdown = (eq - peak).min()
        else:
            self.max_drawdown_pct = 0
            self.max_drawdown = 0

        # Sharpe ratio (annualized, assuming daily returns)
        if len(profits) > 1:
            returns = np.array(profits)
            self.sharpe_ratio = (np.mean(returns) / np.std(returns)) * np.sqrt(252) if np.std(returns) > 0 else 0
        else:
            self.sharpe_ratio = 0

        # Average hold duration
        hold_days = [t.get("hold_bars", 0) for t in trades]
        self.avg_hold_days = np.mean(hold_days) if hold_days else 0

        # Consecutive wins/losses
        self.consecutive_wins = self._max_consecutive(profits, lambda x: x > 0)
        self.consecutive_losses = self._max_consecutive(profits, lambda x: x <= 0)

        # Expectancy
        self.expectancy = np.mean(profits) if profits else 0

        # Risk:Reward ratio
        if self.avg_loss_pct != 0:
            self.risk_reward = abs(self.avg_profit_pct / self.avg_loss_pct)
        else:
            self.risk_reward = float('inf') if self.avg_profit_pct > 0 else 0

        # Average R:R per trade
        rr_per_trade = []
        for t in trades:
            risk = abs(t['entry_price'] - t['stop_loss'])
            reward = abs(t['target'] - t['entry_price'])
            if risk > 0:
                rr_per_trade.append(reward / risk)
        self.avg_rr_ratio = np.mean(rr_per_trade) if rr_per_trade else 0

        # Realized R:R (actual outcome vs risk taken)
        realized_rr = []
        for t in trades:
            risk = abs(t['entry_price'] - t['stop_loss'])
            if risk > 0:
                actual_move = abs(t['exit_price'] - t['entry_price'])
                realized_rr.append(actual_move / risk)
        self.avg_realized_rr = np.mean(realized_rr) if realized_rr else 0

    @staticmethod
    def _max_consecutive(values, condition):
        max_count = 0
        current = 0
        for v in values:
            if condition(v):
                current += 1
                max_count = max(max_count, current)
            else:
                current = 0
        return max_count


def run_backtest(strategy_name: str, symbol: str, period: str = "1y",
                 interval: str = "1d", capital: float = 100000,
                 position_size_pct: float = 100, commission_pct: float = 0.05,
                 trailing_sl: bool = False, trailing_atr_mult: float = 1.5) -> Optional[BacktestResult]:
    """
    Run a backtest for a given strategy on a stock.

    Args:
        strategy_name: Key from ALL_STRATEGIES
        symbol: Stock symbol (e.g., RELIANCE)
        period: Data period (e.g., 1y, 2y, 5y)
        interval: Candle interval (e.g., 1d, 1h, 15m)
        capital: Starting capital in Rs.
        position_size_pct: % of capital to use per trade
        commission_pct: Commission per trade in %
        trailing_sl: Enable trailing stop loss
        trailing_atr_mult: ATR multiplier for trailing distance
    """
    # Fetch data
    df = fetch_data(symbol, period, interval)
    if df is None:
        return None

    # Get strategy and generate signals
    strategy = get_strategy(strategy_name)
    signals_df = strategy.generate_signals(df)

    # Simulate trades
    trades = []
    equity_curve = [capital]
    current_capital = capital
    position = None  # None = no position, dict = active trade

    for i in range(len(signals_df)):
        row = signals_df.iloc[i]
        signal = row.get("signal", 0)

        # ── 3:15 PM intraday exit ──
        if position is not None:
            try:
                bar_time = signals_df.index[i]
                if hasattr(bar_time, 'hour'):
                    if bar_time.hour == 15 and bar_time.minute >= 15:
                        close_price = row["Close"]
                        close_reason = "3:15 PM Exit"
                        # Close the trade
                        if position["direction"] == "LONG":
                            pnl = (close_price - position["entry_price"]) * position["qty"]
                        else:
                            pnl = (position["entry_price"] - close_price) * position["qty"]
                        commission = (position["entry_price"] * position["qty"] * commission_pct / 100) + \
                                     (close_price * position["qty"] * commission_pct / 100)
                        pnl -= commission
                        pnl_pct = (pnl / (position["entry_price"] * position["qty"])) * 100
                        current_capital += pnl
                        trades.append({
                            "entry_date": position["entry_date"],
                            "exit_date": signals_df.index[i],
                            "direction": position["direction"],
                            "entry_price": round(position["entry_price"], 2),
                            "exit_price": round(close_price, 2),
                            "stop_loss": round(position["stop_loss"], 2),
                            "target": round(position["current_target"], 2),
                            "qty": position["qty"],
                            "pnl": round(pnl, 2),
                            "pnl_pct": round(pnl_pct, 2),
                            "exit_reason": close_reason,
                            "hold_bars": i - position["entry_idx"],
                        })
                        position = None
                        equity_curve.append(current_capital)
                        continue
            except Exception:
                pass

        # ── Check SL / Target for open position ──
        if position is not None:
            close_price = None
            close_reason = None

            if position["direction"] == "LONG":
                # Check stop loss
                if row["Low"] <= position["stop_loss"]:
                    close_price = position["stop_loss"]
                    close_reason = f"Stop Loss (T{position['targets_hit']})"
                # Check target hit → trail SL, don't close
                elif row["High"] >= position["current_target"]:
                    position["targets_hit"] += 1
                    # Trail SL to previous target level
                    position["stop_loss"] = position["current_target"]
                    # Set new target (add another risk unit)
                    position["current_target"] += position["risk_distance"]
                    close_price = None  # DON'T close, let it run
                # Check exit signal
                elif signal == -1:
                    close_price = row["Close"]
                    close_reason = "Exit Signal"

            elif position["direction"] == "SHORT":
                if row["High"] >= position["stop_loss"]:
                    close_price = position["stop_loss"]
                    close_reason = f"Stop Loss (T{position['targets_hit']})"
                elif row["Low"] <= position["current_target"]:
                    position["targets_hit"] += 1
                    position["stop_loss"] = position["current_target"]
                    position["current_target"] -= position["risk_distance"]
                    close_price = None  # DON'T close, let it run
                elif signal == 1:
                    close_price = row["Close"]
                    close_reason = "Exit Signal"

            if close_price is not None:
                # Close the trade
                if position["direction"] == "LONG":
                    pnl = (close_price - position["entry_price"]) * position["qty"]
                else:
                    pnl = (position["entry_price"] - close_price) * position["qty"]

                commission = (position["entry_price"] * position["qty"] * commission_pct / 100) + \
                             (close_price * position["qty"] * commission_pct / 100)
                pnl -= commission

                pnl_pct = (pnl / (position["entry_price"] * position["qty"])) * 100
                current_capital += pnl

                trades.append({
                    "entry_date": position["entry_date"],
                    "exit_date": signals_df.index[i],
                    "direction": position["direction"],
                    "entry_price": round(position["entry_price"], 2),
                    "exit_price": round(close_price, 2),
                    "stop_loss": round(position["stop_loss"], 2),
                    "target": round(position["current_target"], 2),
                    "qty": position["qty"],
                    "pnl": round(pnl, 2),
                    "pnl_pct": round(pnl_pct, 2),
                    "exit_reason": close_reason,
                    "hold_bars": i - position["entry_idx"],
                })

                position = None
                equity_curve.append(current_capital)

        # ── Open new position ──
        if position is None and signal != 0:
            entry_price = row["Close"]
            sl = row.get("stop_loss", np.nan)
            target = row.get("target", np.nan)

            if np.isnan(sl) or np.isnan(entry_price):
                continue

            # Calculate risk distance from strategy SL
            risk_distance = abs(entry_price - sl)
            if risk_distance <= 0:
                continue

            # If no target from strategy, use 1:2 R:R
            if np.isnan(target):
                if signal == 1:
                    target = entry_price + 2 * risk_distance
                else:
                    target = entry_price - 2 * risk_distance

            trade_capital = current_capital * (position_size_pct / 100)
            qty = int(trade_capital / entry_price)

            if qty <= 0:
                continue

            position = {
                "direction": "LONG" if signal == 1 else "SHORT",
                "entry_price": entry_price,
                "stop_loss": sl,
                "initial_sl": sl,
                "current_target": target,
                "risk_distance": risk_distance,
                "targets_hit": 0,
                "qty": qty,
                "entry_date": signals_df.index[i],
                "entry_idx": i,
            }

    # Close any open position at the end
    if position is not None:
        close_price = signals_df["Close"].iloc[-1]
        if position["direction"] == "LONG":
            pnl = (close_price - position["entry_price"]) * position["qty"]
        else:
            pnl = (position["entry_price"] - close_price) * position["qty"]

        commission = (position["entry_price"] * position["qty"] * commission_pct / 100) + \
                     (close_price * position["qty"] * commission_pct / 100)
        pnl -= commission
        pnl_pct = (pnl / (position["entry_price"] * position["qty"])) * 100
        current_capital += pnl

        trades.append({
            "entry_date": position["entry_date"],
            "exit_date": signals_df.index[-1],
            "direction": position["direction"],
            "entry_price": round(position["entry_price"], 2),
            "exit_price": round(close_price, 2),
            "stop_loss": round(position["stop_loss"], 2),
            "target": round(position["current_target"], 2),
            "qty": position["qty"],
            "pnl": round(pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "exit_reason": "End of Data",
            "hold_bars": len(signals_df) - position["entry_idx"],
        })
        equity_curve.append(current_capital)

    return BacktestResult(
        strategy_name=strategy_name,
        symbol=symbol,
        trades=trades,
        equity_curve=equity_curve,
        initial_capital=capital,
        final_capital=current_capital,
        period=period,
    )


# ─────────────────────────────────────────────────────────────────────────────
# DISPLAY / REPORTS
# ─────────────────────────────────────────────────────────────────────────────

def print_backtest_report(result: BacktestResult, show_trades: bool = False):
    """Print a detailed backtest report."""
    r = result

    print(f"\n{'=' * 75}")
    print(f"  BACKTEST REPORT: {r.strategy_name}")
    print(f"  Stock: {r.symbol} | Period: {r.period}")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")
    print(f"{'=' * 75}\n")

    # Performance Summary
    color = Fore.GREEN if r.total_return_pct > 0 else Fore.RED
    print(f"  PERFORMANCE SUMMARY")
    print(f"  {'-' * 50}")
    print(f"  {'Starting Capital:':<30} Rs.{r.initial_capital:,.2f}")
    print(f"  {'Final Capital:':<30} {color}Rs.{r.final_capital:,.2f}{Style.RESET_ALL}")
    print(f"  {'Total Return:':<30} {color}{r.total_return_pct:+.2f}%{Style.RESET_ALL}")
    print(f"  {'Total P&L:':<30} {color}Rs.{r.final_capital - r.initial_capital:+,.2f}{Style.RESET_ALL}")
    print()

    # Trade Statistics
    print(f"  TRADE STATISTICS")
    print(f"  {'-' * 50}")
    wr_color = Fore.GREEN if r.win_rate >= 50 else Fore.RED
    print(f"  {'Total Trades:':<30} {r.total_trades}")
    print(f"  {'Winning Trades:':<30} {Fore.GREEN}{r.winning_trades}{Style.RESET_ALL}")
    print(f"  {'Losing Trades:':<30} {Fore.RED}{r.losing_trades}{Style.RESET_ALL}")
    print(f"  {'Win Rate:':<30} {wr_color}{r.win_rate:.1f}%{Style.RESET_ALL}")
    print(f"  {'Avg Win:':<30} {Fore.GREEN}+{r.avg_profit_pct:.2f}%{Style.RESET_ALL}")
    print(f"  {'Avg Loss:':<30} {Fore.RED}{r.avg_loss_pct:.2f}%{Style.RESET_ALL}")
    print(f"  {'Largest Win:':<30} {Fore.GREEN}+{r.largest_win:.2f}%{Style.RESET_ALL}")
    print(f"  {'Largest Loss:':<30} {Fore.RED}{r.largest_loss:.2f}%{Style.RESET_ALL}")
    print(f"  {'Avg Hold Duration:':<30} {r.avg_hold_days:.1f} bars")
    print()

    # Risk Metrics
    print(f"  RISK METRICS")
    print(f"  {'-' * 50}")
    pf_color = Fore.GREEN if r.profit_factor >= 1.5 else (Fore.YELLOW if r.profit_factor >= 1.0 else Fore.RED)
    sr_color = Fore.GREEN if r.sharpe_ratio >= 1.0 else (Fore.YELLOW if r.sharpe_ratio >= 0 else Fore.RED)
    print(f"  {'Profit Factor:':<30} {pf_color}{r.profit_factor:.2f}{Style.RESET_ALL}")
    print(f"  {'Sharpe Ratio:':<30} {sr_color}{r.sharpe_ratio:.2f}{Style.RESET_ALL}")
    print(f"  {'Max Drawdown:':<30} {Fore.RED}{r.max_drawdown_pct:.2f}%{Style.RESET_ALL}")
    print(f"  {'Expectancy:':<30} {r.expectancy:+.2f}% per trade")
    print(f"  {'Max Consec. Wins:':<30} {r.consecutive_wins}")
    print(f"  {'Max Consec. Losses:':<30} {r.consecutive_losses}")
    print(f"  {'Planned R:R Ratio:':<30} {r.avg_rr_ratio:.2f}:1")
    print(f"  {'Realized R:R Ratio:':<30} {r.avg_realized_rr:.2f}:1")
    print(f"  {'Avg Win / Avg Loss:':<30} {r.risk_reward:.2f}:1")
    print()

    # Rating
    print(f"  OVERALL RATING")
    print(f"  {'-' * 50}")
    rating = rate_strategy(r)
    print(f"  {rating}")
    print()

    # Trade log
    if show_trades and r.trades:
        print(f"  TRADE LOG")
        print(f"  {'-' * 50}")
        table = []
        for t in r.trades:
            pnl_color = Fore.GREEN if t["pnl"] > 0 else Fore.RED
            table.append([
                t["entry_date"].strftime("%Y-%m-%d") if hasattr(t["entry_date"], "strftime") else str(t["entry_date"])[:10],
                t["exit_date"].strftime("%Y-%m-%d") if hasattr(t["exit_date"], "strftime") else str(t["exit_date"])[:10],
                t["direction"],
                f"Rs.{t['entry_price']:,.2f}",
                f"Rs.{t['exit_price']:,.2f}",
                f"{pnl_color}Rs.{t['pnl']:+,.2f}{Style.RESET_ALL}",
                f"{pnl_color}{t['pnl_pct']:+.2f}%{Style.RESET_ALL}",
                t["exit_reason"],
            ])
        headers = ["Entry", "Exit", "Dir", "Entry Rs.", "Exit Rs.", "P&L", "P&L%", "Reason"]
        print(tabulate(table, headers=headers, tablefmt="rounded_outline"))
        print()

    print(f"{'=' * 75}\n")


def rate_strategy(r: BacktestResult) -> str:
    """Rate a strategy based on key metrics."""
    score = 0

    # Win rate scoring
    if r.win_rate >= 60:
        score += 3
    elif r.win_rate >= 50:
        score += 2
    elif r.win_rate >= 40:
        score += 1

    # Profit factor
    if r.profit_factor >= 2.0:
        score += 3
    elif r.profit_factor >= 1.5:
        score += 2
    elif r.profit_factor >= 1.0:
        score += 1

    # Sharpe ratio
    if r.sharpe_ratio >= 2.0:
        score += 3
    elif r.sharpe_ratio >= 1.0:
        score += 2
    elif r.sharpe_ratio >= 0.5:
        score += 1

    # Max drawdown
    if r.max_drawdown_pct > -10:
        score += 2
    elif r.max_drawdown_pct > -20:
        score += 1

    # Total return
    if r.total_return_pct > 20:
        score += 2
    elif r.total_return_pct > 0:
        score += 1

    # Rating
    if score >= 11:
        return f"{Fore.GREEN}{Style.BRIGHT}***** EXCELLENT - Strong edge, reliable strategy{Style.RESET_ALL}"
    elif score >= 8:
        return f"{Fore.GREEN}****  GOOD - Profitable with acceptable risk{Style.RESET_ALL}"
    elif score >= 5:
        return f"{Fore.YELLOW}***   AVERAGE - Needs optimization or better conditions{Style.RESET_ALL}"
    elif score >= 3:
        return f"{Fore.RED}**    POOR - Not recommended for live trading{Style.RESET_ALL}"
    else:
        return f"{Fore.RED}{Style.BRIGHT}*     AVOID - Losing strategy, do not trade{Style.RESET_ALL}"


def print_comparison_table(results: list):
    """Print a side-by-side comparison of strategy backtest results."""
    print(f"\n{'=' * 100}")
    print(f"  STRATEGY COMPARISON")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S IST')}")
    print(f"{'=' * 100}\n")

    table = []
    for r in sorted(results, key=lambda x: x.total_return_pct, reverse=True):
        ret_color = Fore.GREEN if r.total_return_pct > 0 else Fore.RED
        wr_color = Fore.GREEN if r.win_rate >= 50 else Fore.RED
        pf_color = Fore.GREEN if r.profit_factor >= 1.5 else Fore.RED

        table.append([
            r.strategy_name,
            r.symbol,
            f"{ret_color}{r.total_return_pct:+.2f}%{Style.RESET_ALL}",
            r.total_trades,
            f"{wr_color}{r.win_rate:.1f}%{Style.RESET_ALL}",
            f"{pf_color}{r.profit_factor:.2f}{Style.RESET_ALL}",
            f"{r.sharpe_ratio:.2f}",
            f"{Fore.RED}{r.max_drawdown_pct:.1f}%{Style.RESET_ALL}",
            f"{r.expectancy:+.2f}%",
            rate_strategy(r).split(" - ")[0].strip(),
        ])

    headers = ["Strategy", "Stock", "Return", "Trades", "Win%", "PF", "Sharpe", "MaxDD", "Expect", "Rating"]
    print(tabulate(table, headers=headers, tablefmt="rounded_outline", stralign="right"))

    # Winner
    if results:
        best = max(results, key=lambda x: x.total_return_pct)
        print(f"\n  >> Best Strategy: {Fore.GREEN}{Style.BRIGHT}{best.strategy_name}{Style.RESET_ALL} "
              f"on {best.symbol} ({best.total_return_pct:+.2f}% return)")

    print(f"\n{'=' * 100}\n")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Backtest Trading Strategies on Indian Stocks",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python backtester.py --stock RELIANCE                            Backtest all strategies
  python backtester.py --stock RELIANCE --strategy ema_crossover   Backtest one strategy
  python backtester.py --stock RELIANCE TCS INFY --compare         Compare across stocks
  python backtester.py --stock RELIANCE --period 2y --trades       Show individual trades
  python backtester.py --stock RELIANCE --capital 200000           Custom starting capital
  python backtester.py --list                                      List available strategies
        """,
    )
    parser.add_argument("--stock", "-s", nargs="+", help="Stock symbol(s) to backtest")
    parser.add_argument("--strategy", "-st", help="Strategy name (default: all)")
    parser.add_argument("--period", "-p", default="1y", help="Backtest period (default: 1y)")
    parser.add_argument("--interval", "-i", default="1d", help="Candle interval (default: 1d)")
    parser.add_argument("--capital", "-c", type=float, default=100000, help="Starting capital (default: 100000)")
    parser.add_argument("--compare", action="store_true", help="Compare all strategies side by side")
    parser.add_argument("--trades", action="store_true", help="Show individual trade log")
    parser.add_argument("--trailing-sl", action="store_true", help="Enable trailing stop loss")
    parser.add_argument("--trail-mult", type=float, default=1.5, help="ATR multiplier for trailing SL (default: 1.5)")
    parser.add_argument("--list", "-l", action="store_true", help="List available strategies")

    args = parser.parse_args()

    if args.list:
        print(f"\n  Available Strategies:")
        print(f"  {'-' * 70}")
        from strategies import list_strategies
        list_strategies()
        print()
        return

    if not args.stock:
        parser.error("--stock is required. Use --stock RELIANCE or --stock TCS INFY")

    stocks = [s.upper() for s in args.stock]
    strategies_to_test = [args.strategy] if args.strategy else list(ALL_STRATEGIES.keys())

    all_results = []

    for symbol in stocks:
        print(f"\n  Fetching data for {symbol}...", end="", flush=True)
        test_data = fetch_data(symbol, args.period, args.interval)
        if test_data is None:
            print(f" {Fore.RED}FAILED{Style.RESET_ALL}")
            continue
        print(f" {Fore.GREEN}OK ({len(test_data)} candles){Style.RESET_ALL}")

        for strat_name in strategies_to_test:
            print(f"  Testing {strat_name:<25}", end="", flush=True)
            result = run_backtest(strat_name, symbol, args.period, args.interval, args.capital,
                                   trailing_sl=args.trailing_sl, trailing_atr_mult=args.trail_mult)
            if result:
                all_results.append(result)
                color = Fore.GREEN if result.total_return_pct > 0 else Fore.RED
                print(f" {color}{result.total_return_pct:+.2f}% | "
                      f"{result.total_trades} trades | "
                      f"WR: {result.win_rate:.0f}%{Style.RESET_ALL}")
            else:
                print(f" {Fore.RED}No data{Style.RESET_ALL}")

    if not all_results:
        print(f"\n  {Fore.RED}No results to show.{Style.RESET_ALL}")
        return

    # Show comparison or individual reports
    if args.compare or len(strategies_to_test) > 1:
        print_comparison_table(all_results)

    # Show detailed reports
    if args.strategy or len(stocks) == 1:
        for result in all_results:
            print_backtest_report(result, show_trades=args.trades)


if __name__ == "__main__":
    main()
