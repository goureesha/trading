"""
30-Stock ORB - FIXED ₹10K per stock, ₹50K daily budget
No margin, no compounding. Realistic intraday simulation.
"""
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
from fyers_data import _headers, resolve_symbol, HISTORY_URL, load_token
from strategies import get_strategy
import time

STOCKS = [
    "RELIANCE", "TCS", "INFY", "HDFCBANK", "ICICIBANK",
    "SBIN", "BHARTIARTL", "ITC", "KOTAKBANK", "LT",
    "AXISBANK", "HINDUNILVR", "BAJFINANCE", "MARUTI", "SUNPHARMA",
    "TITAN", "WIPRO", "ONGC", "NTPC", "POWERGRID",
    "HCLTECH", "TATASTEEL", "JSWSTEEL", "COALINDIA", "ADANIENT",
    "ADANIPORTS", "TECHM", "INDUSINDBK", "M&M",
]


def fetch_chunked(stock, total_days=365, chunk_days=85):
    symbol = resolve_symbol(stock, "NSE")
    all_dfs = []
    end_date = datetime.now()
    remaining = total_days
    while remaining > 0:
        days = min(chunk_days, remaining)
        start_date = end_date - timedelta(days=days)
        params = {
            "symbol": symbol, "resolution": "5", "date_format": "1",
            "range_from": start_date.strftime("%Y-%m-%d"),
            "range_to": end_date.strftime("%Y-%m-%d"),
            "cont_flag": "1",
        }
        try:
            resp = requests.get(HISTORY_URL, headers=_headers(), params=params, timeout=15)
            data = resp.json()
            if data.get("s") == "ok" and data.get("candles"):
                df = pd.DataFrame(data["candles"], columns=["timestamp", "open", "high", "low", "close", "volume"])
                df["date"] = pd.to_datetime(df["timestamp"], unit="s")
                df = df[["date", "open", "high", "low", "close", "volume"]]
                all_dfs.append(df)
        except:
            pass
        end_date = start_date - timedelta(days=1)
        remaining -= days
        time.sleep(0.3)
    if not all_dfs:
        return None
    combined = pd.concat(all_dfs, ignore_index=True)
    combined = combined.sort_values("date").drop_duplicates(subset="date").reset_index(drop=True)
    return combined


def run_orb_trades(df):
    df.columns = [c.capitalize() for c in df.columns]
    if "Date" in df.columns:
        df = df.set_index("Date")
    strategy = get_strategy("orb")
    sdf = strategy.generate_signals(df)
    trades = []
    position = None
    targets_hit = 0

    for i in range(len(sdf)):
        row = sdf.iloc[i]
        signal = int(row.get("signal", 0))

        if position is not None:
            d = position["direction"]
            if d == "LONG":
                if row["Low"] <= position["sl"]:
                    pnl_pct = ((position["sl"] - position["entry"]) / position["entry"]) * 100
                    trades.append({"entry_date": position["edate"], "exit_date": sdf.index[i],
                                   "entry_price": position["entry"], "exit_price": position["sl"],
                                   "direction": "LONG", "pnl_pct": pnl_pct,
                                   "hold_bars": i - position["idx"], "exit_reason": f"SL(T{targets_hit})"})
                    position = None; targets_hit = 0
                elif row["High"] >= position["tgt"]:
                    targets_hit += 1
                    if targets_hit == 1:
                        pnl_pct = ((position["tgt"] - position["entry"]) / position["entry"]) * 100
                        trades.append({"entry_date": position["edate"], "exit_date": sdf.index[i],
                                       "entry_price": position["entry"], "exit_price": position["tgt"],
                                       "direction": "LONG", "pnl_pct": pnl_pct,
                                       "hold_bars": i - position["idx"], "exit_reason": "Partial(50%)"})
                    position["sl"] = position["tgt"]
                    position["tgt"] += position["risk"]
            elif d == "SHORT":
                if row["High"] >= position["sl"]:
                    pnl_pct = ((position["entry"] - position["sl"]) / position["entry"]) * 100
                    trades.append({"entry_date": position["edate"], "exit_date": sdf.index[i],
                                   "entry_price": position["entry"], "exit_price": position["sl"],
                                   "direction": "SHORT", "pnl_pct": pnl_pct,
                                   "hold_bars": i - position["idx"], "exit_reason": f"SL(T{targets_hit})"})
                    position = None; targets_hit = 0
                elif row["Low"] <= position["tgt"]:
                    targets_hit += 1
                    if targets_hit == 1:
                        pnl_pct = ((position["entry"] - position["tgt"]) / position["entry"]) * 100
                        trades.append({"entry_date": position["edate"], "exit_date": sdf.index[i],
                                       "entry_price": position["entry"], "exit_price": position["tgt"],
                                       "direction": "SHORT", "pnl_pct": pnl_pct,
                                       "hold_bars": i - position["idx"], "exit_reason": "Partial(50%)"})
                    position["sl"] = position["tgt"]
                    position["tgt"] -= position["risk"]

            if position and signal != 0:
                if (d == "LONG" and signal == -1) or (d == "SHORT" and signal == 1):
                    ep = row["Close"]
                    pnl_pct = ((ep - position["entry"]) / position["entry"] * 100) if d == "LONG" else ((position["entry"] - ep) / position["entry"] * 100)
                    trades.append({"entry_date": position["edate"], "exit_date": sdf.index[i],
                                   "entry_price": position["entry"], "exit_price": ep,
                                   "direction": d, "pnl_pct": pnl_pct,
                                   "hold_bars": i - position["idx"], "exit_reason": "ExitSignal"})
                    position = None; targets_hit = 0

        if position is None and signal != 0:
            sl = row.get("stop_loss", np.nan)
            tgt = row.get("target", np.nan)
            if not pd.isna(sl) and not pd.isna(tgt):
                position = {"direction": "LONG" if signal == 1 else "SHORT",
                            "entry": row["Close"], "sl": sl, "tgt": tgt,
                            "risk": abs(row["Close"] - sl), "edate": sdf.index[i], "idx": i}
                targets_hit = 0
    return trades


# Main
token = load_token()
if not token:
    print("No token"); exit()

print("=" * 80)
print("30-STOCK ORB - FIXED Rs.10K PER STOCK, Rs.50K DAILY BUDGET")
print("NO MARGIN | NO COMPOUNDING | 1 YEAR BACKTEST")
print("=" * 80)

# Fetch data
all_data = {}
for idx, stock in enumerate(STOCKS):
    print(f"\r  [{idx+1}/30] {stock:<15}", end="", flush=True)
    df = fetch_chunked(stock, total_days=365, chunk_days=85)
    if df is not None and len(df) > 500:
        all_data[stock] = df
        print(f" {len(df)} candles")
    else:
        print(f" SKIP")
    time.sleep(0.2)

print(f"\n  Loaded {len(all_data)} stocks")

# Run ORB on all stocks and tag trades
all_trades = []
for stock, df in all_data.items():
    trades = run_orb_trades(df)
    for t in trades:
        t["symbol"] = stock
        t["trade_date"] = str(t["entry_date"])[:10]
    all_trades.extend(trades)
    print(f"  {stock:<15} {len(trades):>4} trades")

# Sort all trades by entry time
all_trades.sort(key=lambda t: t["entry_date"])
print(f"\n  Total raw trades: {len(all_trades)}")

# PORTFOLIO SIMULATION
# Rules:
# - Rs.50K fresh capital every day
# - Rs.10K per stock max
# - Max 5 positions at same time (50K / 10K)
# - When position closes, Rs.10K freed for another stock
# - Brokerage Rs.40 per trade
# - No margin, no compounding

PER_TRADE = 25000  # Rs.25K per stock
DAILY_BUDGET = 50000
MAX_POS = 2  # 50K / 25K = 2 stocks max
BROKERAGE = 40

total_invested = 0
total_pnl = 0
total_brokerage = 0
daily_results = {}
stock_pnl = {}
stock_trades = {}
monthly_pnl = {}
executed_trades = []

# Group trades by date
from collections import defaultdict
trades_by_date = defaultdict(list)
for t in all_trades:
    trades_by_date[t["trade_date"]].append(t)

trading_days = sorted(trades_by_date.keys())
print(f"  Trading days: {len(trading_days)}")

for day in trading_days:
    day_trades = trades_by_date[day]
    day_budget = DAILY_BUDGET
    day_positions = 0
    day_pnl = 0

    for t in day_trades:
        if day_positions >= MAX_POS:
            break
        if day_budget < PER_TRADE:
            break

        # Buy Rs.10K worth of stock
        entry = t["entry_price"]
        qty = int(PER_TRADE / entry)
        if qty <= 0:
            qty = 1

        actual_investment = entry * qty

        # Calculate P&L
        if t["direction"] == "LONG":
            pnl = (t["exit_price"] - entry) * qty
        else:
            pnl = (entry - t["exit_price"]) * qty

        pnl -= BROKERAGE  # Deduct brokerage

        day_pnl += pnl
        day_budget -= PER_TRADE
        day_positions += 1
        total_brokerage += BROKERAGE

        sym = t["symbol"]
        stock_pnl[sym] = stock_pnl.get(sym, 0) + pnl
        stock_trades[sym] = stock_trades.get(sym, 0) + 1

        t["qty"] = qty
        t["pnl_rs"] = pnl
        t["invested"] = actual_investment
        executed_trades.append(t)

    total_pnl += day_pnl
    total_invested += DAILY_BUDGET
    daily_results[day] = day_pnl

    month = day[:7]
    monthly_pnl[month] = monthly_pnl.get(month, 0) + day_pnl

# Report
n = len(executed_trades)
wins = sum(1 for t in executed_trades if t["pnl_rs"] > 0)
losses = n - wins
avg_win = np.mean([t["pnl_rs"] for t in executed_trades if t["pnl_rs"] > 0]) if wins > 0 else 0
avg_loss = np.mean([t["pnl_rs"] for t in executed_trades if t["pnl_rs"] <= 0]) if losses > 0 else 0
max_win = max(t["pnl_rs"] for t in executed_trades) if executed_trades else 0
max_loss = min(t["pnl_rs"] for t in executed_trades) if executed_trades else 0

profitable_days = sum(1 for v in daily_results.values() if v > 0)
loss_days = sum(1 for v in daily_results.values() if v <= 0)
best_day = max(daily_results.values())
worst_day = min(daily_results.values())
avg_daily = total_pnl / len(trading_days) if trading_days else 0

print()
print("=" * 80)
print("RESULTS: 30-STOCK ORB | Rs.10K/STOCK | Rs.50K/DAY | NO MARGIN")
print(f"Period: {trading_days[0]} to {trading_days[-1]}")
print("=" * 80)

print(f"\n  INVESTMENT")
print(f"  {'─' * 55}")
print(f"  Per Trade:            Rs.    25,000")
print(f"  Daily Budget:         Rs.    50,000")
print(f"  Max Positions/Day:    2")

print(f"\n  P&L SUMMARY")
print(f"  {'─' * 55}")
print(f"  Total Net P&L:        Rs.{total_pnl:>+12,.0f}")
print(f"  Total Brokerage:      Rs.{total_brokerage:>12,.0f}")

print(f"\n  TRADE STATS")
print(f"  {'─' * 55}")
print(f"  Executed Trades:      {n}")
print(f"  Wins:                 {wins} ({wins/n*100:.1f}%)")
print(f"  Losses:               {losses} ({losses/n*100:.1f}%)")
print(f"  Avg Win:              Rs.{avg_win:>+,.0f}")
print(f"  Avg Loss:             Rs.{avg_loss:>+,.0f}")
print(f"  Largest Win:          Rs.{max_win:>+,.0f}")
print(f"  Largest Loss:         Rs.{max_loss:>+,.0f}")

print(f"\n  DAILY STATS")
print(f"  {'─' * 55}")
print(f"  Trading Days:         {len(trading_days)}")
print(f"  Profitable Days:      {profitable_days} ({profitable_days/len(trading_days)*100:.1f}%)")
print(f"  Loss Days:            {loss_days} ({loss_days/len(trading_days)*100:.1f}%)")
print(f"  Best Day:             Rs.{best_day:>+,.0f}")
print(f"  Worst Day:            Rs.{worst_day:>+,.0f}")
print(f"  Avg Daily P&L:        Rs.{avg_daily:>+,.0f}")

print(f"\n  PROJECTIONS (on Rs.50K daily)")
print(f"  {'─' * 55}")
print(f"  Daily Avg:            Rs.{avg_daily:>+,.0f}")
print(f"  Monthly (22 days):    Rs.{avg_daily*22:>+,.0f}")
print(f"  Yearly (252 days):    Rs.{avg_daily*252:>+,.0f}")
print(f"  Yearly Return on 50K: {(total_pnl/50000)*100/len(trading_days)*252:>+.1f}%")

print(f"\n  TOP 10 STOCKS")
print(f"  {'─' * 55}")
for sym, pnl in sorted(stock_pnl.items(), key=lambda x: x[1], reverse=True)[:10]:
    icon = "✅" if pnl > 0 else "❌"
    print(f"  {sym:<15} Rs.{pnl:>+8,.0f}  ({stock_trades[sym]} trades) {icon}")

print(f"\n  BOTTOM 5 STOCKS")
print(f"  {'─' * 55}")
for sym, pnl in sorted(stock_pnl.items(), key=lambda x: x[1])[:5]:
    icon = "✅" if pnl > 0 else "❌"
    print(f"  {sym:<15} Rs.{pnl:>+8,.0f}  ({stock_trades[sym]} trades) {icon}")

print(f"\n  MONTHLY BREAKDOWN")
print(f"  {'─' * 55}")
for month, pnl in sorted(monthly_pnl.items()):
    bar = "█" * max(1, int(abs(pnl) / 200))
    icon = "✅" if pnl > 0 else "❌"
    print(f"  {month}:  Rs.{pnl:>+10,.0f}  {icon} {bar}")

pm = sum(1 for p in monthly_pnl.values() if p > 0)
print(f"\n  Profitable Months: {pm}/{len(monthly_pnl)} ({pm/len(monthly_pnl)*100:.0f}%)")
print(f"\n{'=' * 80}")
