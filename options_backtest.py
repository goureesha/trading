"""
Nifty Options 1-Year Backtest - Fetches 5m data in quarterly chunks
"""
import pandas as pd
import requests
from datetime import datetime, timedelta
from fyers_data import _headers, resolve_symbol, HISTORY_URL, load_token
from backtester import run_backtest
from strategies import get_strategy
import time

def fetch_fyers_chunked(stock, interval="5m", total_days=365, chunk_days=85):
    """Fetch Fyers data in chunks to bypass the 90-day limit for 5m data."""
    symbol = resolve_symbol(stock, "NSE")
    resolution = {"5m": "5", "15m": "15", "1d": "D"}.get(interval, "5")
    
    all_dfs = []
    end_date = datetime.now()
    remaining = total_days
    
    while remaining > 0:
        days = min(chunk_days, remaining)
        start_date = end_date - timedelta(days=days)
        
        params = {
            "symbol": symbol,
            "resolution": resolution,
            "date_format": "1",
            "range_from": start_date.strftime("%Y-%m-%d"),
            "range_to": end_date.strftime("%Y-%m-%d"),
            "cont_flag": "1",
        }
        
        print(f"  Fetching {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}...", end="")
        
        try:
            resp = requests.get(HISTORY_URL, headers=_headers(), params=params, timeout=15)
            data = resp.json()
            
            if data.get("s") == "ok" and "candles" in data and data["candles"]:
                df = pd.DataFrame(data["candles"], columns=["timestamp", "open", "high", "low", "close", "volume"])
                df["date"] = pd.to_datetime(df["timestamp"], unit="s")
                df = df[["date", "open", "high", "low", "close", "volume"]]
                all_dfs.append(df)
                print(f" {len(df)} candles")
            else:
                print(f" No data")
        except Exception as e:
            print(f" Error: {e}")
        
        end_date = start_date - timedelta(days=1)
        remaining -= days
        time.sleep(0.5)
    
    if not all_dfs:
        return None
    
    combined = pd.concat(all_dfs, ignore_index=True)
    combined = combined.sort_values("date").drop_duplicates(subset="date").reset_index(drop=True)
    print(f"  Total: {len(combined)} candles from {combined.iloc[0]['date']} to {combined.iloc[-1]['date']}")
    return combined


def run_orb_on_data(df):
    """Run ORB strategy and return trades using the backtester engine."""
    # Capitalize columns
    df.columns = [c.capitalize() for c in df.columns]
    if "Date" in df.columns:
        df = df.set_index("Date")
    
    strategy = get_strategy("orb")
    signals_df = strategy.generate_signals(df)
    
    # Use backtester's run_backtest logic inline
    from backtester import run_backtest
    result = run_backtest("orb", "NIFTY50", period="1y", interval="5m", capital=100000, _preloaded_df=df)
    return result


# Check token
token = load_token()
if not token:
    print("No Fyers token. Run: python fyers_data.py RELIANCE")
    exit()

print("=" * 80)
print("NIFTY 5-MIN DATA - FETCHING 1 YEAR IN CHUNKS")
print("=" * 80)

df = fetch_fyers_chunked("NIFTY50", interval="5m", total_days=365, chunk_days=85)

if df is None or len(df) < 100:
    print("Not enough data. Exiting.")
    exit()

# Capitalize for strategies
df.columns = [c.capitalize() for c in df.columns]
if "Date" in df.columns:
    df = df.set_index("Date")

# Run ORB strategy
print("\nRunning ORB strategy...")
strategy = get_strategy("orb")
signals_df = strategy.generate_signals(df)

# Extract signals
signal_mask = signals_df["signal"] != 0
signal_count = signal_mask.sum()
print(f"Total signals: {signal_count}")

# Run backtest manually
from backtester import BacktestResult
import numpy as np

trades = []
capital = 100000
position = None
targets_hit = 0

for i in range(len(signals_df)):
    row = signals_df.iloc[i]
    signal = int(row.get("signal", 0))
    
    # Check existing position
    if position is not None:
        if position["direction"] == "LONG":
            if row["Low"] <= position["stop_loss"]:
                pnl_pct = ((position["stop_loss"] - position["entry"]) / position["entry"]) * 100
                trades.append({
                    "entry_date": position["entry_date"],
                    "exit_date": signals_df.index[i],
                    "entry_price": position["entry"],
                    "exit_price": position["stop_loss"],
                    "direction": "LONG",
                    "pnl_pct": pnl_pct,
                    "hold_bars": i - position["bar_idx"],
                    "exit_reason": f"Stop Loss (T{targets_hit})",
                    "targets_hit": targets_hit,
                })
                position = None
                targets_hit = 0
            elif row["High"] >= position["target"]:
                targets_hit += 1
                if targets_hit == 1:
                    pnl_pct = ((position["target"] - position["entry"]) / position["entry"]) * 100
                    trades.append({
                        "entry_date": position["entry_date"],
                        "exit_date": signals_df.index[i],
                        "entry_price": position["entry"],
                        "exit_price": position["target"],
                        "direction": "LONG",
                        "pnl_pct": pnl_pct,
                        "hold_bars": i - position["bar_idx"],
                        "exit_reason": "Partial Book (50%)",
                        "targets_hit": targets_hit,
                    })
                position["stop_loss"] = position["target"]
                position["target"] += position["risk"]
        
        elif position["direction"] == "SHORT":
            if row["High"] >= position["stop_loss"]:
                pnl_pct = ((position["entry"] - position["stop_loss"]) / position["entry"]) * 100
                trades.append({
                    "entry_date": position["entry_date"],
                    "exit_date": signals_df.index[i],
                    "entry_price": position["entry"],
                    "exit_price": position["stop_loss"],
                    "direction": "SHORT",
                    "pnl_pct": pnl_pct,
                    "hold_bars": i - position["bar_idx"],
                    "exit_reason": f"Stop Loss (T{targets_hit})",
                    "targets_hit": targets_hit,
                })
                position = None
                targets_hit = 0
            elif row["Low"] <= position["target"]:
                targets_hit += 1
                if targets_hit == 1:
                    pnl_pct = ((position["entry"] - position["target"]) / position["entry"]) * 100
                    trades.append({
                        "entry_date": position["entry_date"],
                        "exit_date": signals_df.index[i],
                        "entry_price": position["entry"],
                        "exit_price": position["target"],
                        "direction": "SHORT",
                        "pnl_pct": pnl_pct,
                        "hold_bars": i - position["bar_idx"],
                        "exit_reason": "Partial Book (50%)",
                        "targets_hit": targets_hit,
                    })
                position["stop_loss"] = position["target"]
                position["target"] -= position["risk"]
        
        # Exit signal
        if position is not None and signal != 0 and (
            (position["direction"] == "LONG" and signal == -1) or
            (position["direction"] == "SHORT" and signal == 1)
        ):
            exit_price = row["Close"]
            if position["direction"] == "LONG":
                pnl_pct = ((exit_price - position["entry"]) / position["entry"]) * 100
            else:
                pnl_pct = ((position["entry"] - exit_price) / position["entry"]) * 100
            trades.append({
                "entry_date": position["entry_date"],
                "exit_date": signals_df.index[i],
                "entry_price": position["entry"],
                "exit_price": exit_price,
                "direction": position["direction"],
                "pnl_pct": pnl_pct,
                "hold_bars": i - position["bar_idx"],
                "exit_reason": "Exit Signal",
                "targets_hit": targets_hit,
            })
            position = None
            targets_hit = 0
    
    # Open new position
    if position is None and signal != 0:
        sl = row.get("stop_loss", np.nan)
        tgt = row.get("target", np.nan)
        if not pd.isna(sl) and not pd.isna(tgt):
            risk = abs(row["Close"] - sl)
            position = {
                "direction": "LONG" if signal == 1 else "SHORT",
                "entry": row["Close"],
                "stop_loss": sl,
                "target": tgt,
                "risk": risk,
                "entry_date": signals_df.index[i],
                "bar_idx": i,
            }
            targets_hit = 0

# Close remaining position
if position is not None:
    exit_price = signals_df.iloc[-1]["Close"]
    if position["direction"] == "LONG":
        pnl_pct = ((exit_price - position["entry"]) / position["entry"]) * 100
    else:
        pnl_pct = ((position["entry"] - exit_price) / position["entry"]) * 100
    trades.append({
        "entry_date": position["entry_date"],
        "exit_date": signals_df.index[-1],
        "entry_price": position["entry"],
        "exit_price": exit_price,
        "direction": position["direction"],
        "pnl_pct": pnl_pct,
        "hold_bars": len(signals_df) - position["bar_idx"],
        "exit_reason": "End of Data",
        "targets_hit": targets_hit,
    })

print(f"Total trades: {len(trades)}")

if not trades:
    print("No trades generated. Exiting.")
    exit()

# Convert to options P&L
lot_size = 25
delta = 0.5
option_budget = 20000
option_premium = 200
option_cost = option_premium * lot_size
theta_per_unit_per_hour = 3.5
bid_ask_spread = 2.0
brokerage = 40

capital = option_budget
total_pnl = 0
total_gross = 0
total_theta = 0
wins = 0
losses = 0
monthly_pnl = {}
max_capital = option_budget
min_capital = option_budget

for t in trades:
    entry = t["entry_price"]
    exit_p = t["exit_price"]
    direction = t["direction"]
    hours = t["hold_bars"] * 5 / 60
    
    if direction == "LONG":
        spot_pts = exit_p - entry
    else:
        spot_pts = entry - exit_p
    
    opt_pnl_raw = spot_pts * delta * lot_size
    if opt_pnl_raw < -option_cost:
        opt_pnl_raw = -option_cost
    
    theta_cost = theta_per_unit_per_hour * hours * lot_size
    spread_cost = bid_ask_spread * lot_size * 2
    total_costs = theta_cost + spread_cost + brokerage
    net_pnl = opt_pnl_raw - total_costs
    
    total_pnl += net_pnl
    total_gross += opt_pnl_raw
    total_theta += theta_cost
    capital += net_pnl
    max_capital = max(max_capital, capital)
    min_capital = min(min_capital, capital)
    
    if net_pnl > 0:
        wins += 1
    else:
        losses += 1
    
    month = str(t["entry_date"])[:7]
    if month not in monthly_pnl:
        monthly_pnl[month] = 0
    monthly_pnl[month] += net_pnl

# Report
n = len(trades)
unique_days = len(set(str(t["entry_date"])[:10] for t in trades))
months = len(monthly_pnl)
first_date = str(trades[0]["entry_date"])[:10]
last_date = str(trades[-1]["entry_date"])[:10]

print()
print("=" * 80)
print("NIFTY OPTIONS 1-YEAR BACKTEST (WITH THETA + ALL COSTS)")
print(f"Period: {first_date} to {last_date} | Strategy: ORB | 1 Lot | ₹20K capital")
print("=" * 80)

print(f"\n  CAPITAL")
print(f"  {'─' * 50}")
print(f"  Starting:          Rs.{option_budget:>10,}")
print(f"  Final:             Rs.{capital:>10,.0f}")
print(f"  Peak:              Rs.{max_capital:>10,.0f}")
print(f"  Trough:            Rs.{min_capital:>10,.0f}")
print(f"  Total P&L:         Rs.{total_pnl:>+10,.0f}")
print(f"  Return:            {(total_pnl/option_budget)*100:>+10.1f}%")

print(f"\n  TRADES")
print(f"  {'─' * 50}")
print(f"  Total:             {n}")
print(f"  Wins:              {wins} ({wins/n*100:.1f}%)")
print(f"  Losses:            {losses} ({losses/n*100:.1f}%)")
print(f"  Trading Days:      {unique_days}")

print(f"\n  COSTS")
print(f"  {'─' * 50}")
print(f"  Gross P&L:         Rs.{total_gross:>+10,.0f}")
print(f"  Total Theta:       Rs.{total_theta:>10,.0f}")
print(f"  Net P&L:           Rs.{total_pnl:>+10,.0f}")

print(f"\n  AVERAGES")
print(f"  {'─' * 50}")
print(f"  Daily Avg P&L:     Rs.{total_pnl/unique_days:>+,.0f}")
print(f"  Monthly Avg P&L:   Rs.{total_pnl/months:>+,.0f}")
print(f"  Yearly Projected:  Rs.{(total_pnl/unique_days)*252:>+,.0f}")

print(f"\n  MONTHLY BREAKDOWN")
print(f"  {'─' * 50}")
for month, pnl in sorted(monthly_pnl.items()):
    bar = "█" * max(1, int(abs(pnl) / 1000))
    icon = "✅" if pnl > 0 else "❌"
    print(f"  {month}:  Rs.{pnl:>+10,.0f}  {icon} {bar}")

print(f"\n{'=' * 80}")
