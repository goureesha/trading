"""
ORB Strategy Backtest - Nifty Options with Filters
Tests: Plain ORB vs Filtered ORB (trend + volume + time filters)
Uses: Fyers 5m data, Nifty lot size = 65, ₹20K investment
"""
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from fyers_data import fetch_fyers_data, load_token

# Config
NIFTY_LOT = 65
OPTIONS_INVEST = 20000
ORB_CANDLES = 3  # first 15 min (3 x 5min)
RR = 2.0
CLOSE_TIME = "15:15"

def fetch_nifty_5m(days=90):
    """Fetch Nifty 5m data from Fyers."""
    print(f"  Fetching NIFTY 5m data ({days} days)...")
    df = fetch_fyers_data("NIFTY50", interval="5", days=days, exchange="NSE")
    if df is None or len(df) == 0:
        # Try index symbol
        df = fetch_fyers_data("NIFTY50-INDEX", interval="5", days=days, exchange="NSE")
    if df is None:
        print("  ❌ Could not fetch Nifty 5m data")
        return None
    print(f"  ✅ Got {len(df)} candles")
    return df


def calc_vwap(df_day):
    """Calculate VWAP for the day."""
    tp = (df_day['high'] + df_day['low'] + df_day['close']) / 3
    cum_vol = df_day['volume'].cumsum()
    cum_tp_vol = (tp * df_day['volume']).cumsum()
    vwap = cum_tp_vol / cum_vol
    return vwap


def calc_prev_day_vwap(df, day_key, all_days):
    """Get previous day's closing VWAP."""
    idx = all_days.index(day_key)
    if idx == 0:
        return None
    prev_day = all_days[idx - 1]
    prev_df = df[df['day'] == prev_day].copy()
    if len(prev_df) == 0:
        return None
    vwap = calc_vwap(prev_df)
    return vwap.iloc[-1] if len(vwap) > 0 else None


def run_backtest(df, use_filters=False, label=""):
    """Run ORB backtest on Nifty 5m data."""
    if df is None:
        return None

    df = df.copy()
    df['time'] = df['date'].dt.strftime('%H:%M')
    df['day'] = df['date'].dt.date.astype(str)

    all_days = sorted(df['day'].unique())
    trades = []

    for day in all_days:
        day_df = df[df['day'] == day].copy().reset_index(drop=True)
        if len(day_df) < ORB_CANDLES + 2:
            continue

        # ORB: first 3 candles (9:15-9:30)
        orb = day_df.iloc[:ORB_CANDLES]
        orb_high = orb['high'].max()
        orb_low = orb['low'].min()
        orb_range = orb_high - orb_low

        if orb_range <= 0:
            continue

        # ── FILTERS ──
        if use_filters:
            # Filter 1: Market trend (prev day VWAP)
            prev_vwap = calc_prev_day_vwap(df, day, all_days)

            # Filter 2: Volume - ORB candles should have decent volume
            orb_vol = orb['volume'].mean()
            day_prev = all_days[all_days.index(day) - 1] if all_days.index(day) > 0 else None
            if day_prev:
                prev_df = df[df['day'] == day_prev]
                avg_vol = prev_df['volume'].mean() if len(prev_df) > 0 else orb_vol
            else:
                avg_vol = orb_vol
            vol_ok = orb_vol >= avg_vol * 0.8  # at least 80% of avg

            # Filter 3: Time - only take signals before 12:00
            time_cutoff = "12:00"

        # Scan post-ORB candles for breakout
        post = day_df.iloc[ORB_CANDLES:]
        signal = None
        entry = sl = target = None
        breakout_time = None

        for _, c in post.iterrows():
            if c['time'] >= CLOSE_TIME:
                break

            # Time filter
            if use_filters and c['time'] >= "12:00":
                break

            if c['close'] > orb_high and signal is None:
                signal = 'BUY'
                entry = c['close']
                sl = orb_low
                target = entry + (entry - sl) * RR
                breakout_time = c['time']
                break
            elif c['close'] < orb_low and signal is None:
                signal = 'SELL'
                entry = c['close']
                sl = orb_high
                target = entry - (sl - entry) * RR
                breakout_time = c['time']
                break

        if signal is None:
            continue

        # Apply trend filter
        if use_filters and prev_vwap is not None:
            open_price = day_df.iloc[0]['open']
            if signal == 'BUY' and open_price < prev_vwap:
                continue  # Skip BUY on bearish day
            if signal == 'SELL' and open_price > prev_vwap:
                continue  # Skip SELL on bullish day

        # Apply volume filter
        if use_filters and not vol_ok:
            continue

        # Simulate trade
        risk = abs(entry - sl)
        reward = abs(target - entry)

        # Simulate candle by candle after entry
        entry_idx = None
        for i, c in post.iterrows():
            if c['time'] == breakout_time:
                entry_idx = i
                break

        if entry_idx is None:
            continue

        exit_price = None
        exit_reason = "CLOSE_3:15"
        remaining = day_df.loc[entry_idx + 1:]

        for _, c in remaining.iterrows():
            if c['time'] >= CLOSE_TIME:
                exit_price = c['close']
                exit_reason = "CLOSE_3:15"
                break

            if signal == 'BUY':
                if c['low'] <= sl:
                    exit_price = sl
                    exit_reason = "SL_HIT"
                    break
                if c['high'] >= target:
                    exit_price = target
                    exit_reason = "TARGET_HIT"
                    break
            else:
                if c['high'] >= sl:
                    exit_price = sl
                    exit_reason = "SL_HIT"
                    break
                if c['low'] <= target:
                    exit_price = target
                    exit_reason = "TARGET_HIT"
                    break

        if exit_price is None:
            exit_price = day_df.iloc[-1]['close']

        # Calculate Nifty points P&L
        if signal == 'BUY':
            points_pnl = exit_price - entry
        else:
            points_pnl = entry - exit_price

        # Estimate options P&L (simplified: delta ~0.5 for ATM)
        option_delta = 0.5
        option_pnl_per_unit = points_pnl * option_delta
        option_premium = 200  # approximate ATM CE/PE price
        lot_cost = option_premium * NIFTY_LOT  # 200 * 65 = 13,000

        # Option P&L = points gained * delta * lot size
        option_pnl = option_pnl_per_unit * NIFTY_LOT

        trades.append({
            'date': day,
            'signal': signal,
            'entry': entry,
            'sl': sl,
            'target': target,
            'exit': exit_price,
            'exit_reason': exit_reason,
            'points_pnl': points_pnl,
            'option_pnl': option_pnl,
            'lot_cost': lot_cost,
            'breakout_time': breakout_time,
            'orb_range': orb_range,
        })

    if not trades:
        print(f"  {label}: No trades found")
        return None

    tdf = pd.DataFrame(trades)
    wins = tdf[tdf['option_pnl'] > 0]
    losses = tdf[tdf['option_pnl'] <= 0]

    total_pnl = tdf['option_pnl'].sum()
    win_rate = len(wins) / len(tdf) * 100
    avg_win = wins['option_pnl'].mean() if len(wins) > 0 else 0
    avg_loss = losses['option_pnl'].mean() if len(losses) > 0 else 0
    profit_factor = abs(wins['option_pnl'].sum() / losses['option_pnl'].sum()) if len(losses) > 0 and losses['option_pnl'].sum() != 0 else float('inf')
    max_win = tdf['option_pnl'].max()
    max_loss = tdf['option_pnl'].min()

    # Exit reason breakdown
    sl_count = len(tdf[tdf['exit_reason'] == 'SL_HIT'])
    tgt_count = len(tdf[tdf['exit_reason'] == 'TARGET_HIT'])
    close_count = len(tdf[tdf['exit_reason'] == 'CLOSE_3:15'])

    print(f"\n  {'='*60}")
    print(f"  {label}")
    print(f"  {'='*60}")
    print(f"  Total Trades:   {len(tdf)}")
    print(f"  Win Rate:       {win_rate:.1f}%")
    print(f"  Total P&L:      Rs. {total_pnl:,.0f}")
    print(f"  Avg Win:        Rs. {avg_win:,.0f}")
    print(f"  Avg Loss:       Rs. {avg_loss:,.0f}")
    print(f"  Profit Factor:  {profit_factor:.2f}")
    print(f"  Max Win:        Rs. {max_win:,.0f}")
    print(f"  Max Loss:       Rs. {max_loss:,.0f}")
    print(f"  {'─'*60}")
    print(f"  Exit Breakdown: Target={tgt_count} | SL={sl_count} | Close@3:15={close_count}")
    print(f"  BUY signals:    {len(tdf[tdf['signal']=='BUY'])}")
    print(f"  SELL signals:   {len(tdf[tdf['signal']=='SELL'])}")
    print(f"  {'─'*60}")
    print(f"  Lot Size: {NIFTY_LOT} | Premium: Rs.200 | Lot Cost: Rs.{NIFTY_LOT*200:,}")
    print(f"  {'='*60}")

    # Per-trade log
    print(f"\n  Trade Log:")
    print(f"  {'Date':<12} {'Sig':<5} {'Entry':>8} {'Exit':>8} {'Reason':<12} {'Pts':>7} {'Option P&L':>10}")
    print(f"  {'─'*70}")
    for _, t in tdf.iterrows():
        pnl_str = f"Rs.{t['option_pnl']:>+7,.0f}"
        pts_str = f"{t['points_pnl']:>+7.1f}"
        marker = "✅" if t['option_pnl'] > 0 else "❌"
        print(f"  {t['date']:<12} {t['signal']:<5} {t['entry']:>8.1f} {t['exit']:>8.1f} {t['exit_reason']:<12} {pts_str} {pnl_str} {marker}")

    return {
        'trades': tdf,
        'total_pnl': total_pnl,
        'win_rate': win_rate,
        'total_trades': len(tdf),
        'profit_factor': profit_factor,
    }


if __name__ == "__main__":
    print("\n" + "="*70)
    print("  ORB BACKTEST - NIFTY OPTIONS (5m Fyers Data)")
    print("  Lot Size: 65 | Investment: Rs.20,000 | Premium: ~Rs.200")
    print("="*70)

    token = load_token()
    if not token:
        print("  ❌ Fyers token not found. Please login first.")
        exit(1)

    # Fetch data - try max days available for 5m
    df = fetch_nifty_5m(days=90)
    if df is None:
        print("  ❌ No data. Exiting.")
        exit(1)

    print(f"\n  Data range: {df['date'].min()} to {df['date'].max()}")
    print(f"  Total candles: {len(df)}")

    # Backtest 1: Plain ORB
    r1 = run_backtest(df, use_filters=False, label="PLAIN ORB (No Filters)")

    # Backtest 2: Filtered ORB
    r2 = run_backtest(df, use_filters=True, label="FILTERED ORB (Trend + Volume + Time)")

    # Comparison
    if r1 and r2:
        print(f"\n  {'='*60}")
        print(f"  COMPARISON: Plain vs Filtered")
        print(f"  {'='*60}")
        print(f"  {'Metric':<20} {'Plain':>15} {'Filtered':>15}")
        print(f"  {'─'*50}")
        print(f"  {'Trades':<20} {r1['total_trades']:>15} {r2['total_trades']:>15}")
        print(f"  {'Win Rate':<20} {r1['win_rate']:>14.1f}% {r2['win_rate']:>14.1f}%")
        print(f"  {'Total P&L':<20} Rs.{r1['total_pnl']:>11,.0f} Rs.{r2['total_pnl']:>11,.0f}")
        print(f"  {'Profit Factor':<20} {r1['profit_factor']:>15.2f} {r2['profit_factor']:>15.2f}")
        saved = r1['total_pnl'] - r2['total_pnl'] if r2['total_pnl'] > r1['total_pnl'] else 0
        extra = r2['total_pnl'] - r1['total_pnl']
        print(f"  {'Filter Edge':<20} {'':>15} Rs.{extra:>+11,.0f}")
        print(f"  {'='*60}")
