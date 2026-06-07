"""
Test ALL strategies on 10 stocks, 5m intraday, 1 year
Find which strategy works best for stock intraday trading
"""
import pandas as pd
import numpy as np
import requests
from datetime import datetime, timedelta
from fyers_data import _headers, resolve_symbol, HISTORY_URL, load_token
from strategies import get_strategy, ALL_STRATEGIES
import time

STOCKS = ["RELIANCE", "INFY", "HDFCBANK", "SBIN", "ICICIBANK",
          "AXISBANK", "ITC", "TCS", "BAJFINANCE", "TATASTEEL"]

def fetch_chunked(stock, total_days=365, chunk_days=85):
    symbol = resolve_symbol(stock, "NSE")
    all_dfs = []
    end_date = datetime.now()
    remaining = total_days
    while remaining > 0:
        days = min(chunk_days, remaining)
        start_date = end_date - timedelta(days=days)
        params = {"symbol": symbol, "resolution": "5", "date_format": "1",
                  "range_from": start_date.strftime("%Y-%m-%d"),
                  "range_to": end_date.strftime("%Y-%m-%d"), "cont_flag": "1"}
        try:
            resp = requests.get(HISTORY_URL, headers=_headers(), params=params, timeout=15)
            data = resp.json()
            if data.get("s") == "ok" and data.get("candles"):
                df = pd.DataFrame(data["candles"], columns=["timestamp","open","high","low","close","volume"])
                df["date"] = pd.to_datetime(df["timestamp"], unit="s")
                df = df[["date","open","high","low","close","volume"]]
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


def run_trades(df, strategy_name):
    """Run a strategy and return trades."""
    df2 = df.copy()
    df2.columns = [c.capitalize() for c in df2.columns]
    if "Date" in df2.columns:
        df2 = df2.set_index("Date")
    
    try:
        strategy = get_strategy(strategy_name)
        sdf = strategy.generate_signals(df2)
    except Exception as e:
        return []
    
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
                    pnl = ((position["sl"] - position["entry"]) / position["entry"]) * 100
                    trades.append({"pnl_pct": pnl, "direction": "LONG",
                                   "hold_bars": i - position["idx"],
                                   "entry_date": position["edate"]})
                    position = None; targets_hit = 0
                elif row["High"] >= position["tgt"]:
                    targets_hit += 1
                    if targets_hit == 1:
                        pnl = ((position["tgt"] - position["entry"]) / position["entry"]) * 100
                        trades.append({"pnl_pct": pnl, "direction": "LONG",
                                       "hold_bars": i - position["idx"],
                                       "entry_date": position["edate"]})
                    position["sl"] = position["tgt"]
                    position["tgt"] += position["risk"]
            elif d == "SHORT":
                if row["High"] >= position["sl"]:
                    pnl = ((position["entry"] - position["sl"]) / position["entry"]) * 100
                    trades.append({"pnl_pct": pnl, "direction": "SHORT",
                                   "hold_bars": i - position["idx"],
                                   "entry_date": position["edate"]})
                    position = None; targets_hit = 0
                elif row["Low"] <= position["tgt"]:
                    targets_hit += 1
                    if targets_hit == 1:
                        pnl = ((position["entry"] - position["tgt"]) / position["entry"]) * 100
                        trades.append({"pnl_pct": pnl, "direction": "SHORT",
                                       "hold_bars": i - position["idx"],
                                       "entry_date": position["edate"]})
                    position["sl"] = position["tgt"]
                    position["tgt"] -= position["risk"]

            if position and signal != 0:
                if (d == "LONG" and signal == -1) or (d == "SHORT" and signal == 1):
                    ep = row["Close"]
                    pnl = ((ep - position["entry"]) / position["entry"] * 100) if d == "LONG" else ((position["entry"] - ep) / position["entry"] * 100)
                    trades.append({"pnl_pct": pnl, "direction": d,
                                   "hold_bars": i - position["idx"],
                                   "entry_date": position["edate"]})
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

print("=" * 90)
print("STRATEGY COMPARISON: ALL STRATEGIES vs 10 STOCKS | 5m INTRADAY | 1 YEAR")
print("Investment: Rs.25,000 per stock | Brokerage: Rs.40/trade")
print("=" * 90)

# Fetch data for 10 stocks
all_data = {}
for idx, stock in enumerate(STOCKS):
    print(f"\r  [{idx+1}/10] {stock:<15}", end="", flush=True)
    df = fetch_chunked(stock, total_days=365, chunk_days=85)
    if df is not None and len(df) > 500:
        all_data[stock] = df
        print(f" {len(df)} candles")
    else:
        print(f" SKIP")

print(f"\n  Loaded {len(all_data)} stocks\n")

# Test all strategies
strategies = list(ALL_STRATEGIES.keys())
print(f"  Testing {len(strategies)} strategies: {', '.join(strategies)}\n")

PER_TRADE = 25000
BROKERAGE = 40

results = []

for sname in strategies:
    total_trades = 0
    total_wins = 0
    total_pnl = 0
    total_brokerage = 0
    stock_results = {}
    
    for stock, df in all_data.items():
        trades = run_trades(df, sname)
        if not trades:
            continue
        
        wins = sum(1 for t in trades if t["pnl_pct"] > 0)
        pnl_rs = 0
        for t in trades:
            trade_pnl = (t["pnl_pct"] / 100) * PER_TRADE - BROKERAGE
            pnl_rs += trade_pnl
        
        total_trades += len(trades)
        total_wins += wins
        total_pnl += pnl_rs
        total_brokerage += len(trades) * BROKERAGE
        stock_results[stock] = pnl_rs
    
    if total_trades > 0:
        wr = total_wins / total_trades * 100
        avg_pnl = total_pnl / total_trades
        monthly = total_pnl / 12
        results.append({
            "strategy": sname,
            "trades": total_trades,
            "win_rate": wr,
            "total_pnl": total_pnl,
            "brokerage": total_brokerage,
            "avg_pnl": avg_pnl,
            "monthly": monthly,
            "best_stock": max(stock_results, key=stock_results.get) if stock_results else "N/A",
            "best_stock_pnl": max(stock_results.values()) if stock_results else 0,
        })

# Sort by total P&L
results.sort(key=lambda r: r["total_pnl"], reverse=True)

# Print results
print("\n" + "=" * 90)
print("STRATEGY RANKING (Best to Worst for Stock Intraday)")
print("=" * 90)
print(f"\n  {'#':>2} {'Strategy':<20} {'Trades':>7} {'WR%':>6} {'Total P&L':>12} {'Avg/Trade':>10} {'Monthly':>10} {'Best Stock':<12}")
print(f"  {'─' * 88}")

for i, r in enumerate(results):
    icon = "✅" if r["total_pnl"] > 0 else "❌"
    print(f"  {i+1:>2} {r['strategy']:<20} {r['trades']:>7} {r['win_rate']:>5.1f}% Rs.{r['total_pnl']:>+10,.0f} Rs.{r['avg_pnl']:>+7,.0f} Rs.{r['monthly']:>+8,.0f} {r['best_stock']:<12} {icon}")

# Summary
print(f"\n  {'─' * 88}")
profitable = [r for r in results if r["total_pnl"] > 0]
losing = [r for r in results if r["total_pnl"] <= 0]
print(f"\n  Profitable strategies: {len(profitable)}/{len(results)}")
print(f"  Losing strategies:    {len(losing)}/{len(results)}")

if profitable:
    best = profitable[0]
    print(f"\n  🏆 BEST STRATEGY: {best['strategy']}")
    print(f"     Total P&L:    Rs.{best['total_pnl']:>+,.0f}")
    print(f"     Win Rate:     {best['win_rate']:.1f}%")
    print(f"     Trades:       {best['trades']}")
    print(f"     Monthly Avg:  Rs.{best['monthly']:>+,.0f}")
    print(f"     Best Stock:   {best['best_stock']} (Rs.{best['best_stock_pnl']:>+,.0f})")
    print(f"     Yearly Return on Rs.25K: {(best['total_pnl']/PER_TRADE)*100:+.1f}%")

print(f"\n{'=' * 90}")
